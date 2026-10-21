"""V1 输出一次性导入：默认只读扫描并写计划，只有 --apply 写业务数据。"""
from __future__ import annotations

import argparse
from contextlib import closing
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import sys

sys.dont_write_bytecode = True
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from PIL import Image as PILImage
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.config import load_settings
from app.models import Prompt, PromptVersion
from app.services import image_service, prompt_service
from app.storage.manager import StorageManager
from migrate_v1_legacy import recent_backup, under, write_exclusive


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_snapshot(database: Path) -> tuple[list[dict], list[dict]]:
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        images = [dict(row) for row in conn.execute(
            "SELECT id,file_path,sha256,source,imported_filename FROM images ORDER BY id")]
        prompts = [dict(row) for row in conn.execute(
            "SELECT p.id,p.archived,v.id AS version_id,v.positive_prompt,v.negative_prompt,"
            "v.structured_json FROM prompts p JOIN prompt_versions v "
            "ON v.id=p.current_version_id ORDER BY p.id")]
        return images, prompts


def make_plan(source: Path, output: Path, root: Path, limit: int | None) -> dict:
    cache_file = under(source, "runtime/prompt_cache.json")
    cache_bytes = cache_file.read_bytes()
    cache = json.loads(cache_bytes.decode("utf-8-sig"))
    if not isinstance(cache, dict):
        raise ValueError("prompt_cache 顶层必须为对象")
    images, prompts = read_snapshot(under(root, "database/studio.db"))
    hashes = {}
    missing_v2 = []
    for image in images:
        path = under(root, image["file_path"])
        if not path.is_file():
            missing_v2.append(image["id"])
            # 已有导入的 hash 仍需阻止重复，不能静默修复缺失原图。
            digest = image["sha256"]
        else:
            digest = sha256(path)
            if image["sha256"] and image["sha256"] != digest:
                raise ValueError(f"V2 原图与登记哈希不一致：{image['id']}")
        if digest:
            hashes.setdefault(digest, []).append(image["id"])
    prompt_index = {}
    for row in prompts:
        if not row["archived"]:
            prompt_index.setdefault(row["positive_prompt"], row)
    groups, skipped, texts = {}, [], set()
    exists = 0
    empty_positive = 0
    for raw_path, value in sorted(cache.items()):
        if (not isinstance(value, list) or len(value) != 2
                or not isinstance(value[1], str)
                or isinstance(value[0], bool) or not isinstance(value[0], (int, float))):
            skipped.append({"path": raw_path, "reason": "invalid_cache"})
            continue
        texts.add(value[1])
        empty_positive += not value[1].strip()
        path = Path(raw_path).resolve()
        if not Path(raw_path).is_absolute() or not path.is_relative_to(output):
            skipped.append({"path": raw_path, "reason": "outside_root"})
            continue
        if not path.is_file():
            skipped.append({"path": raw_path, "reason": "missing"})
            continue
        exists += 1
        try:
            data = path.read_bytes()
            image_service.prepare_import_image(data, filename=path.name, content_type=None)
            with PILImage.open(io.BytesIO(data)) as image:
                image.load()
        except Exception as exc:
            skipped.append({"path": raw_path, "reason": "invalid_file", "error": str(exc)})
            continue
        digest = hashlib.sha256(data).hexdigest()
        group = groups.setdefault(digest, {
            "sha256": digest, "size_bytes": len(data), "sources": [],
            "existing_image_ids": hashes.get(digest, []),
        })
        group["sources"].append({"path": raw_path, "resolved_path": str(path),
                                 "cache_timestamp": value[0], "positive_prompt": value[1]})
    new_texts, selected = set(), 0
    for group in groups.values():
        if group["existing_image_ids"]:
            group["action"] = "skip_existing"
        elif limit is not None and selected >= limit:
            group["action"] = "deferred_limit"
        else:
            group["action"] = "import"
            selected += 1
            new_texts.update(row["positive_prompt"] for row in group["sources"]
                             if row["positive_prompt"].strip() and row["positive_prompt"] not in prompt_index)
        group["prompts"] = [{"positive_prompt": text,
                             "prompt_id": prompt_index[text]["id"] if text in prompt_index else None,
                             "version_id": prompt_index[text]["version_id"] if text in prompt_index else None}
                            for text in sorted({row["positive_prompt"] for row in group["sources"]}) if text.strip()]
    migrated = [row for row in prompts if "_v1_migration" in json.loads(row["structured_json"])]
    library = {row["positive_prompt"] for row in migrated}
    stats = {
        "cache_entries": len(cache), "existing_files": exists,
        "missing_files": sum(row["reason"] == "missing" for row in skipped),
        "outside_root": sum(row["reason"] == "outside_root" for row in skipped),
        "invalid_files": sum(row["reason"] == "invalid_file" for row in skipped),
        "invalid_cache": sum(row["reason"] == "invalid_cache" for row in skipped),
        "empty_positive_entries": empty_positive,
        "unique_positive_prompts": len(texts), "v2_images": len(images),
        "v2_missing_files": len(missing_v2), "v2_prompts": len(prompts),
        "migrated_prompts": len(migrated), "exact_library_overlap": len(texts & library),
        "strict_contains_cache_texts": sum(any(t != p and (t in p or p in t)
            for p in library if p) for t in texts if t),
        "unique_source_hashes": len(groups),
        "duplicate_cache_files": sum(len(g["sources"]) - 1 for g in groups.values()),
        "existing_matches": sum(len(g["sources"]) for g in groups.values() if g["existing_image_ids"]),
        "matching_v2_images": len({i for g in groups.values() for i in g["existing_image_ids"]}),
        "will_import": selected, "will_create_prompts": len(new_texts),
        "deferred_limit": sum(g["action"] == "deferred_limit" for g in groups.values()),
        "will_copy_bytes": sum(g["size_bytes"] for g in groups.values() if g["action"] == "import"),
        "skipped_or_duplicate": len(cache) - selected,
    }
    return {"schema_version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
            "source": str(source), "output_root": str(output), "data_root": str(root),
            "cache_sha256": hashlib.sha256(cache_bytes).hexdigest(), "limit": limit,
            "stats": stats, "records": list(groups.values()), "skipped": skipped,
            "v2_missing_image_ids": missing_v2, "status": "dry-run"}


class RetainingStorage(StorageManager):
    """失败残留只登记，禁止本工具物理删除文件。"""
    def safe_delete(self, path):
        return None


def apply_plan(plan: dict, root: Path, plan_path: Path) -> None:
    # 不调用 bootstrap / make_engine，避免自动建库、迁移、改变 journal_mode。
    database = under(root, "database/studio.db")
    engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(
        database.as_uri() + "?mode=rw", uri=True, timeout=5))
    settings = load_settings()
    settings = replace(settings, storage=replace(settings.storage, data_root=root))
    storage = RetainingStorage(settings)
    try:
        with engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            conn.commit()
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            # 服务内部 commit 仅释放 SAVEPOINT；整次 apply 在外层一次提交。
            with Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False) as session:
                current_images, _ = read_snapshot(database)
                current_hashes = {}
                for row in current_images:
                    path = under(root, row["file_path"])
                    digest = sha256(path) if path.is_file() else row["sha256"]
                    if digest:
                        current_hashes[digest] = row["id"]
                index = {}
                for prompt, version in session.execute(select(Prompt, PromptVersion).join(
                        PromptVersion, Prompt.current_version_id == PromptVersion.id)
                        .where(Prompt.archived == False).order_by(Prompt.id)):
                    index.setdefault(version.positive_prompt, (prompt.id, version.id))
                for group in plan["records"]:
                    if group["action"] != "import":
                        continue
                    if group["sha256"] in current_hashes:
                        group["result"] = {"existing_image_id": current_hashes[group["sha256"]]}
                        continue
                    source_path = Path(group["sources"][0]["resolved_path"]).resolve()
                    if not source_path.is_relative_to(Path(plan["output_root"])):
                        raise ValueError("源路径在扫描后越界")
                    data = source_path.read_bytes()
                    if hashlib.sha256(data).hexdigest() != group["sha256"]:
                        raise ValueError(f"源文件在扫描后改变：{source_path}")
                    prepared = image_service.prepare_import_image(data, filename=source_path.name, content_type=None)
                    group["planned_image_id"] = prepared.image_id
                    group["planned_file_path"] = prepared.relative_path
                    # 文件意向日志在服务写入前落盘；异常/崩溃可定位残留。
                    write_exclusive(plan_path.with_name(plan_path.stem + f"-{prepared.image_id}.json"),
                                    json.dumps(group, ensure_ascii=False, indent=2).encode("utf-8"))
                    for item in group["prompts"]:
                        text = item["positive_prompt"]
                        if text not in index:
                            prompt = prompt_service.create_prompt(session, name="V1 输出 " + hashlib.sha256(
                                text.encode("utf-8")).hexdigest()[:12], mode="full", positive_prompt=text,
                                structured={"_v1_output_import": {"negative_prompt_known": False}})
                            index[text] = (prompt.id, prompt.current_version_id)
                        item["prompt_id"], item["version_id"] = index[text]
                    imported = image_service.import_outputs_transaction(session, storage, [prepared], source="import",
                        metadata={"sha256": group["sha256"], "imported_filename": source_path.name,
                                  "v1_output": {"sources": group["sources"], "prompts": group["prompts"],
                                                "negative_prompt_known": False}})
                    group["result"] = {"image_id": imported[0].id}
                    current_hashes[group["sha256"]] = imported[0].id
                session.commit()
            conn.commit()
        plan["status"] = "applied"
    finally:
        engine.dispose()


def run(source: Path, output: Path, root: Path, *, apply: bool = False, limit: int | None = None) -> dict:
    source, output, root = source.resolve(), output.resolve(), root.resolve()
    if limit is not None and limit < 1:
        raise ValueError("limit 必须为正整数")
    for a, b in ((source, root), (output, root), (source, output)):
        if a.is_relative_to(b) or b.is_relative_to(a):
            raise ValueError("source/output/DataRoot 不得相互包含")
    if not under(root, "database/studio.db").is_file():
        raise ValueError("目标数据库不存在；请使用正常初始化流程")
    backup = recent_backup(root) if apply else None
    if apply and backup is None:
        raise ValueError("拒绝执行：需 1 小时内有效备份，请先运行 scripts/backup_db.py")
    plan = make_plan(source, output, root, limit)
    plan["backup"] = str(backup) if backup else None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    plan_path = under(root, f"backups/v1-outputs-plan-{stamp}.json")
    plan["plan_path"] = str(plan_path)
    if apply:
        plan["status"] = "prepared; 文件存在不代表提交成功"
    # 即使备份目录不可写，调研统计也应可见；写清单失败必须终止，不能进入 apply。
    print(json.dumps(plan["stats"], ensure_ascii=False, indent=2), flush=True)
    write_exclusive(plan_path, json.dumps(plan, ensure_ascii=False, indent=2).encode("utf-8"))
    if apply:
        try:
            # 扫描可能超过一小时，写入前再次验证门禁。
            if recent_backup(root) is None:
                raise ValueError("备份已过期，请重新运行 scripts/backup_db.py")
            apply_plan(plan, root, plan_path)
        except BaseException:
            plan["status"] = "failed; 核查数据库与意向日志，不自动删除残留文件"
            raise
        finally:
            write_exclusive(plan_path.with_name(plan_path.stem + "-result.json"),
                            json.dumps(plan, ensure_ascii=False, indent=2).encode("utf-8"))
    print(f"{plan['status']}\n清单：{plan_path}", flush=True)
    return plan


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    home = PROJECT_ROOT.parents[1]
    parser.add_argument("--source", type=Path, default=home / "archive/projects/nsfw-studio-v1")
    parser.add_argument("--output-root", type=Path, default=PROJECT_ROOT.parent / "comfyui/app/output")
    parser.add_argument("--data-root", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--dry-run", action="store_true")
    modes.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)
    try:
        run(args.source, args.output_root, args.data_root or load_settings().storage.data_root,
            apply=args.apply, limit=args.limit)
    except Exception as exc:
        print(f"导入失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
