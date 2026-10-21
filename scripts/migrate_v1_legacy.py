"""一次性 V1 数据迁移；默认只读计划，只有 --apply 才允许 INSERT。

不启动应用、不初始化数据库、不运行归档代码。失败时回滚整笔事务；
已新增的文件保留，由提交前持久化的映射追踪，绝不删除或覆盖已有数据。
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import time

sys.dont_write_bytecode = True
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

import yaml
from PIL import Image

from app.core.ids import ASSET, ASSET_VERSION, PROMPT, PROMPT_VERSION, new_id
from app.core.filetypes import validate_image_upload
from app.core.timeutil import utc_now_iso

DEFAULT_SOURCE = Path("D:/AIHome_2.0_L1_L2/archive/projects/nsfw-studio-v1")
FACE_FILES = {f"face_{i:03d}": f"temp/face_input/face_{i}.jpg" for i in range(1, 4)}
MARKER = "nsfw-studio-v1"
TABLES = {"prompts", "prompt_versions", "assets", "asset_versions"}
OMITTED = [
    {"source": "temp/face_input/face_4.jpg", "reason": "没有对应的人脸记录，暂不迁移"},
    {"source": "runtime/prompt_cache.json", "reason": "历史路径提示词缓存，后续可选"},
    {"source": "runtime/history.json", "reason": "历史记录，后续可选"},
]


def resolve_data_root(explicit: str | None, config_dir: Path | None = None) -> Path:
    """本次工具按用户指定的优先级解析，不更改项目全局配置。"""
    value = explicit or os.environ.get("NSFW_STUDIO_DATA_ROOT")
    if not value:
        local = (config_dir or PROJECT_ROOT / "configs") / "config.local.yaml"
        config = yaml.safe_load(local.read_text(encoding="utf-8")) if local.is_file() else {}
        if config is not None and not isinstance(config, dict):
            raise ValueError("config.local.yaml 顶层必须是映射")
        value = (config or {}).get("data_root") or "D:/NSFW-Studio-Data"
    return Path(value).expanduser().resolve()


def under(root: Path, relative: str) -> Path:
    """拒绝符号链接或路径穿越造成的读写越界。"""
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f"路径越界：{relative}")
    return path


def read_rows(source: Path, filename: str) -> list[dict]:
    rows = json.loads(under(source, f"runtime/{filename}").read_text(encoding="utf-8-sig"))
    if not isinstance(rows, list):
        raise ValueError(f"{filename} 顶层必须是数组")
    seen = set()
    for position, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            raise ValueError(f"{filename} 含非对象记录")
        original_id = row.get("id")
        if filename == "promptlib.json" and original_id is None:
            digest = hashlib.sha256(json.dumps(
                row, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
            row["id"] = f"missing-id-row-{position}-{digest}"
        row["_original_id"] = original_id
        for key in ("id", "name"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise ValueError(f"{filename} 的 {key} 必须是非空字符串")
        if row["id"] in seen:
            raise ValueError(f"{filename} 含重复 ID：{row['id']}")
        seen.add(row["id"])
    return rows


def load_source(source: Path) -> tuple[list[dict], list[dict]]:
    prompts = read_rows(source, "promptlib.json")
    faces = read_rows(source, "faces.json")
    for row in prompts:
        if not all(isinstance(row.get(k), str) for k in ("positive", "negative")):
            raise ValueError("提示词 positive/negative 必须是字符串")
    for row in faces:
        if row["id"] not in FACE_FILES:
            raise ValueError(f"未授权的人脸映射：{row['id']}")
        tags = row.get("tags")
        if not isinstance(tags, list) or not all(isinstance(tag, str) for tag in tags):
            raise ValueError("人脸 tags 必须是字符串数组")
        # 在任何落盘前完整解码；复制使用内存中的同一份字节，避免源文件变化。
        content = under(source, FACE_FILES[row["id"]]).read_bytes()
        with Image.open(io.BytesIO(content)) as image:
            suffix = {"JPEG": ".jpg", "WEBP": ".webp", "PNG": ".png"}.get(image.format)
            if suffix is None:
                raise ValueError(f"{row['id']} 源图格式不受 V2 支持")
            validate_image_upload(f"preview{suffix}", None, content)
            image.load()
        row["_bytes"] = content
        row["_suffix"] = suffix
    return prompts, faces


def recent_backup(root: Path) -> Path | None:
    """时效之外校验 SQLite 完整性与目标结构；不能替代来源确认和恢复演练。"""
    now = time.time()
    database = under(root, "database/studio.db")
    candidates = [
        p for p in under(root, "backups").glob("studio-*.db")
        if p.is_file() and p.resolve().is_relative_to(root)
        and not p.samefile(database)
        and p.stat().st_size > 0 and 0 <= now - p.stat().st_mtime <= 3600
    ]
    if not candidates:
        return None
    schema_sql = ("SELECT name,sql FROM sqlite_master WHERE type='table' "
                  "AND name IN ('prompts','prompt_versions','assets','asset_versions','migration') "
                  "ORDER BY name")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as target:
        expected = target.execute(schema_sql).fetchall()
    for candidate in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            with closing(sqlite3.connect(candidate.resolve().as_uri() + "?mode=ro", uri=True)) as saved:
                if (saved.execute("PRAGMA quick_check").fetchall() == [("ok",)]
                        and not saved.execute("PRAGMA foreign_key_check").fetchall()
                        and len(expected) == 5
                        and saved.execute(schema_sql).fetchall() == expected):
                    return candidate
        except sqlite3.DatabaseError:
            continue
    return None


def connect(database: Path, apply: bool) -> sqlite3.Connection:
    # mode=rw 不会误建新数据库；mode=ro + query_only 保证 dry-run 不能写 SQL。
    conn = sqlite3.connect(database.as_uri() + f"?mode={'rw' if apply else 'ro'}",
                           uri=True, isolation_level=None, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    if not apply:
        conn.execute("PRAGMA query_only=ON")

    def authorize(action, table, column, db_name, trigger):
        # 包括触发器在内，只允许对四张目标表 INSERT，禁止 DDL/UPDATE/DELETE。
        if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION,
                      sqlite3.SQLITE_TRANSACTION):
            return sqlite3.SQLITE_OK
        if apply and action == sqlite3.SQLITE_INSERT and table in TABLES and trigger is None:
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    conn.set_authorizer(authorize)
    return conn


def make_plan(conn: sqlite3.Connection, prompts: list[dict], faces: list[dict]) -> dict:
    prompt_keys = {}
    for row in conn.execute(
        "SELECT p.id,p.name,v.positive_prompt,v.negative_prompt,v.structured_json "
        "FROM prompts p JOIN prompt_versions v ON v.prompt_id=p.id ORDER BY p.id"
    ):
        structured = json.loads(row["structured_json"])
        marker = structured.get("_v1_migration") if isinstance(structured, dict) else None
        if isinstance(marker, dict) and marker.get("source") == MARKER:
            key = (row["name"], row["positive_prompt"], row["negative_prompt"])
            prompt_keys.setdefault(key, row["id"])
    asset_keys = {}
    for row in conn.execute(
        "SELECT a.id,a.name,v.tags_json FROM assets a "
        "JOIN asset_versions v ON v.id=a.current_version_id WHERE a.type='face' ORDER BY a.id"
    ):
        asset_keys.setdefault((row["name"], frozenset(json.loads(row["tags_json"]))), row["id"])
    plan = {"prompts": [], "faces": [], "skipped": []}
    for kind, rows, index, prefix, version_prefix in (
        ("prompts", prompts, prompt_keys, PROMPT, PROMPT_VERSION),
        ("faces", faces, asset_keys, ASSET, ASSET_VERSION),
    ):
        for row in rows:
            name = row["name"][:255]
            key = ((name, row["positive"], row["negative"]) if kind == "prompts"
                   else (name, frozenset(row["tags"])))
            exists = key in index
            object_id = index[key] if exists else new_id(prefix)
            item = {"source_id": row["id"], "id": object_id, "name": name,
                    "original_id": row["_original_id"],
                    "original_name": row["name"], "action": "skip" if exists else "insert"}
            if exists:
                plan["skipped"].append({"kind": kind, "source_id": row["id"],
                                        "id": object_id, "reason": "幂等匹配"})
            else:
                item["version_id"] = new_id(version_prefix)
                if kind == "faces":
                    item["preview_path"] = f"assets/face/{object_id}/v0001/preview{row['_suffix']}"
                    item["source_path"] = FACE_FILES[row["id"]]
                    item["sha256"] = hashlib.sha256(row["_bytes"]).hexdigest()
                index[key] = object_id
            plan[kind].append(item)
    return plan


def write_exclusive(path: Path, content: bytes) -> None:
    """独占创建并刷盘，绝不覆盖；失败的部分文件也保留以供人工核查。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def insert_rows(conn: sqlite3.Connection, plan: dict, prompts: list[dict], faces: list[dict]) -> None:
    now = utc_now_iso()
    for item, row in zip(plan["prompts"], prompts):
        if item["action"] == "skip":
            continue
        conn.execute(
            "INSERT INTO prompts "
            "(id,name,current_version_id,favorite,archived,created_at,updated_at) VALUES (?,?,?,0,0,?,?)",
            (item["id"], item["name"], item["version_id"], now, now))
        marker = {"_v1_migration": {"source": MARKER, "source_id": row["id"],
                                  "original_id": row["_original_id"],
                                  "original_name": row["name"]}}
        conn.execute(
            "INSERT INTO prompt_versions "
            "(id,prompt_id,version_no,mode,positive_prompt,negative_prompt,structured_json,created_at) "
            "VALUES (?,?,1,'full',?,?,?,?)",
            (item["version_id"], item["id"], row["positive"], row["negative"],
             json.dumps(marker, ensure_ascii=False), now))
    for item, row in zip(plan["faces"], faces):
        if item["action"] == "skip":
            continue
        conn.execute(
            "INSERT INTO assets "
            "(id,type,name,current_version_id,favorite,archived,created_at,updated_at) "
            "VALUES (?,'face',?,?,0,0,?,?)",
            (item["id"], item["name"], item["version_id"], now, now))
        notes = {"_v1_migration": {"source": MARKER, "source_id": row["id"],
                                  "original": {k: v for k, v in row.items() if not k.startswith("_")}}}
        conn.execute(
            "INSERT INTO asset_versions "
            "(id,asset_id,version_no,prompt_text,notes,preview_path,reference_images_json,tags_json,created_at) "
            "VALUES (?,?,1,'',?,?,'[]',?,?)",
            (item["version_id"], item["id"], json.dumps(notes, ensure_ascii=False),
             item["preview_path"], json.dumps(row["tags"], ensure_ascii=False), now))


def migrate(source: Path, root: Path, *, apply: bool = False, force: bool = False) -> dict:
    source, root = source.resolve(), root.resolve()
    if root == source or root.is_relative_to(source) or source.is_relative_to(root):
        raise ValueError("源目录与 DataRoot 不得相同或相互包含")
    database = under(root, "database/studio.db")
    if not database.is_file():
        raise ValueError(f"目标数据库不存在，请先通过 V2 正常初始化：{database}")
    backup = recent_backup(root) if apply else None
    if apply:
        if force:
            print("危险警告：--force 已启用，绕过最近一小时备份门禁；可能无法安全回滚。")
        elif backup is None:
            raise ValueError("拒绝执行：最近一小时内无有效 studio-*.db 备份"
                             "（需完整性和结构校验通过，且不是当前数据库）。"
                             "请先运行 scripts/backup_db.py。")
    prompts, faces = load_source(source)
    print(f"源目录：{source}\nDataRoot：{root}")
    conn = connect(database, apply)
    map_path = None
    try:
        # 先获取写锁再查重，避免两个迁移进程同时通过幂等检查。
        conn.execute("BEGIN IMMEDIATE" if apply else "BEGIN")
        plan = make_plan(conn, prompts, faces)
        created = len(prompts) + len(faces) - len(plan["skipped"])
        print(f"迁移计划：prompts={len(prompts)} faces={len(faces)} "
              f"待新增={created} skipped={len(plan['skipped'])}")
        truncated = sum(item["name"] != item["original_name"]
                        for kind in ("prompts", "faces") for item in plan[kind])
        print(f"名称截断：{truncated}（最多 255 字符，完整名称保留在映射中）")
        print(f"缺失提示词 ID：{sum(r['_original_id'] is None for r in prompts)}"
              "（使用源记录位置＋内容哈希作为映射键）")
        formats = ", ".join(f"{r['id']}→preview{r['_suffix']}" for r in faces)
        print(f"人脸预览格式：{formats}（按实际格式命名，原字节复制）")
        print(f"未迁移项：{len(OMITTED)}")
        for item in OMITTED:
            print(f"  - {item['source']}：{item['reason']}")
        if not apply:
            print("dry-run：只读检查完成；未写数据库、图片或映射文件。")
            return plan
        # 在生成文件、写库之前持久化意向映射。即使进程崩溃，也可定位残留文件。
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        map_path = under(root, f"backups/v1-migration-map-{stamp}.json")
        mapping = {
            "schema_version": 1, "created_at": utc_now_iso(), "source": str(source),
            "data_root": str(root), "backup": str(backup) if backup else None,
            "forced": force,
            "transaction_status": "prepared; 必须核对数据库中的 ID，映射文件存在不代表提交成功",
            "prompt_id_map": {i["source_id"]: i["id"] for i in plan["prompts"]},
            "asset_id_map": {i["source_id"]: i["id"] for i in plan["faces"]},
            "records": plan, "skipped": plan["skipped"], "omitted": OMITTED,
        }
        write_exclusive(map_path, json.dumps(mapping, ensure_ascii=False, indent=2).encode("utf-8"))
        for item, row in zip(plan["faces"], faces):
            if item["action"] == "insert":
                write_exclusive(under(root, item["preview_path"]), row["_bytes"])
        insert_rows(conn, plan, prompts, faces)
        conn.commit()
        print(f"提交成功：created={created} skipped={len(plan['skipped'])}")
        print(f"迁移映射：{map_path}")
        return plan
    except BaseException:
        conn.rollback()
        if map_path is not None:
            print(f"事务未完成；新增文件未删除，请按意向映射核查：{map_path}", file=sys.stderr)
        raise
    finally:
        if conn.in_transaction:
            conn.rollback()
        conn.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="V1 一次性迁移工具（默认 dry-run）")
    parser.add_argument("--source", default=str(DEFAULT_SOURCE), help="只读 V1 归档根目录")
    parser.add_argument("--data-root", help="目标 V2 DataRoot")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true", help="只打印计划（默认）")
    modes.add_argument("--apply", action="store_true", help="正式写入")
    parser.add_argument("--force", action="store_true", help="危险：绕过备份门禁，不隐含 --apply")
    args = parser.parse_args(argv)
    try:
        migrate(Path(args.source), resolve_data_root(args.data_root), apply=args.apply, force=args.force)
    except Exception as exc:
        print(f"迁移失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
