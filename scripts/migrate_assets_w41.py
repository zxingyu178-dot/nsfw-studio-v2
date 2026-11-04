#!/usr/bin/env python3
"""W4.1 历史图片资产迁移（复制 + SHA256 校验 + DB 路径更新）。

原则：
- 只复制，不移动、不删除旧文件；
- 每个文件 Copy → SHA256 → 与源文件比对，不一致立即中止该批；
- 数据库路径更新按批事务；失败整批回滚；
- 支持 dry-run、limit、重复执行（幂等）；
- 正式 apply 前必须停止 Studio / ComfyUI（脚本会检查 8000/8188）。

目标结构：
  assets/images/YYYY/MM/<image_id>/<kind>.<ext>
  cache/thumbnails/<image_id>/thumbnail.webp
  cache/previews/<image_id>/preview.webp
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import socket
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_settings  # noqa: E402

OLD_IMAGE_DIRS = {"original": "images/originals", "processed": "images/processed", "upscaled": "images/upscaled"}
NEW_ROOT = "assets/images"
VARIANT_DIRS = {"thumbnail": "cache/thumbnails", "preview": "cache/previews"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def target_image_key(image_id: str, kind: str, suffix: str, created_at: str) -> str:
    stamp = created_at or "1970-01-01"
    return f"{NEW_ROOT}/{stamp[0:4]}/{stamp[5:7]}/{image_id}/{kind}{suffix}"


def target_variant_key(image_id: str, variant_type: str, suffix: str) -> str:
    base = VARIANT_DIRS.get(variant_type)
    if base is None:
        raise ValueError(f"未知 variant_type: {variant_type}")
    return f"{base}/{image_id}/{variant_type}{suffix}"


def port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def mime_for_suffix(suffix: str) -> str:
    return {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(
        suffix.lower(), "application/octet-stream"
    )


def build_plan(conn: sqlite3.Connection, data_root: Path, limit: int | None) -> tuple[list[dict], list[dict]]:
    images = conn.execute(
        "SELECT id, kind, file_path, created_at, sha256, metadata_json FROM images ORDER BY created_at, id"
    ).fetchall()
    variants = conn.execute(
        "SELECT id, image_id, variant_type, path, width, height, format FROM image_variants ORDER BY image_id"
    ).fetchall()
    image_plan: list[dict] = []
    for row in images:
        image_id, kind, file_path, created_at, sha256, metadata_json = row
        rel = str(file_path).replace("\\", "/")
        if rel.startswith(f"{NEW_ROOT}/"):
            continue
        source = data_root / rel
        suffix = Path(rel).suffix
        target = target_image_key(image_id, kind, suffix, created_at)
        image_plan.append({
            "image_id": image_id, "kind": kind, "source_rel": rel, "target_rel": target,
            "source": source, "target": data_root / target, "sha256": sha256,
            "created_at": created_at, "metadata_json": metadata_json,
        })
        if limit is not None and len(image_plan) >= limit:
            break
    variant_plan: list[dict] = []
    for row in variants:
        variant_id, image_id, variant_type, path, width, height, fmt = row
        rel = str(path).replace("\\", "/")
        if rel.startswith("cache/"):
            continue
        source = data_root / rel
        suffix = Path(rel).suffix or ".webp"
        target = target_variant_key(image_id, variant_type, suffix)
        variant_plan.append({
            "variant_id": variant_id, "image_id": image_id, "variant_type": variant_type,
            "source_rel": rel, "target_rel": target, "source": source,
            "target": data_root / target, "width": width, "height": height, "format": fmt,
        })
        if limit is not None and len(variant_plan) >= limit:
            break
    return image_plan, variant_plan


def copy_verified(source: Path, target: Path, expected_sha: str | None) -> tuple[str, str]:
    """单遍读源 + 写临时 + 目标复核；避免重复三次读盘（机械盘迁移耗时主因）。"""
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target_sha = sha256_file(target)
        if expected_sha and target_sha != expected_sha:
            raise RuntimeError(f"目标已存在但 Hash 不一致: {target}")
        return target_sha, "existing"
    tmp = target.with_suffix(target.suffix + ".w41tmp")
    source_hash = hashlib.sha256()
    written_hash = hashlib.sha256()
    try:
        with source.open("rb") as src, tmp.open("wb") as dst:
            for chunk in iter(lambda: src.read(1024 * 1024), b""):
                source_hash.update(chunk)
                written_hash.update(chunk)
                dst.write(chunk)
            dst.flush()
        source_sha = source_hash.hexdigest()
        if expected_sha and expected_sha != "unverified" and source_sha != expected_sha:
            raise RuntimeError(f"源文件 Hash 与数据库不一致: {source}")
        if written_hash.hexdigest() != source_sha:
            raise RuntimeError(f"写入流 Hash 不一致: {source}")
        tmp.replace(target)
        target_sha = sha256_file(target)
        if target_sha != source_sha:
            raise RuntimeError(f"复制后目标 Hash 不一致: {source} -> {target}")
        return target_sha, "copied"
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def apply_db_updates(conn: sqlite3.Connection, image_updates: list[dict], variant_updates: list[dict]) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        for item in image_updates:
            metadata = json.loads(item["metadata_json"] or "{}")
            metadata.update({
                "mime_type": mime_for_suffix(Path(item["target_rel"]).suffix),
                "file_size": item["size"],
                "asset_type": item["kind"],
            })
            conn.execute(
                "UPDATE images SET file_path=?, sha256=?, metadata_json=? WHERE id=?",
                (item["target_rel"], item["sha256"], json.dumps(metadata, ensure_ascii=False), item["image_id"]),
            )
        for item in variant_updates:
            conn.execute("UPDATE image_variants SET path=? WHERE id=?", (item["target_rel"], item["variant_id"]))
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="W4.1 历史图片资产迁移")
    parser.add_argument("--dry-run", action="store_true", help="只生成计划，不复制/不写库")
    parser.add_argument("--apply", action="store_true", help="正式复制并更新数据库")
    parser.add_argument("--limit", type=int, default=None, help="仅处理前 N 张（演练）")
    parser.add_argument("--batch-size", type=int, default=200, help="每批文件数")
    parser.add_argument("--db", default=None, help="数据库路径（默认 settings）")
    parser.add_argument("--data-root", default=None, help="DataRoot（默认 settings）")
    parser.add_argument("--allow-running", action="store_true", help="允许服务运行中执行（不推荐）")
    parser.add_argument("--report", default=None, help="报告输出路径")
    args = parser.parse_args()
    if not args.dry_run and not args.apply:
        print("必须指定 --dry-run 或 --apply", file=sys.stderr)
        return 2

    settings = load_settings()
    data_root = Path(args.data_root) if args.data_root else settings.storage.data_root
    db_path = Path(args.db) if args.db else settings.storage.database_path
    if not data_root.is_dir() or not db_path.is_file():
        print(f"DataRoot 或数据库不存在: {data_root} / {db_path}", file=sys.stderr)
        return 2

    if args.apply and not args.allow_running:
        for port in (8000, 8188):
            if port_listening(port):
                print(f"端口 {port} 仍在监听；请先停止 Studio / ComfyUI", file=sys.stderr)
                return 3

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    before = {
        "images": conn.execute("SELECT count(*) FROM images").fetchone()[0],
        "variants": conn.execute("SELECT count(*) FROM image_variants").fetchone()[0],
    }
    image_plan, variant_plan = build_plan(conn, data_root, args.limit)
    report = {
        "mode": "apply" if args.apply else "dry-run",
        "data_root": str(data_root), "database": str(db_path),
        "images_planned": len(image_plan), "variants_planned": len(variant_plan),
        "images_before": before["images"], "variants_before": before["variants"],
        "copied": 0, "existing": 0, "missing": 0, "errors": [],
    }

    if args.dry_run:
        report["sample"] = [
            {"image_id": item["image_id"], "source": item["source_rel"], "target": item["target_rel"]}
            for item in image_plan[:10]
        ]
        missing = [item["source_rel"] for item in image_plan + variant_plan if not item["source"].is_file()]
        report["missing"] = len(missing)
        report["missing_samples"] = missing[:20]
    else:
        image_updates: list[dict] = []
        variant_updates: list[dict] = []
        batch: list[dict] = []

        def flush() -> None:
            if not batch:
                return
            apply_db_updates(conn, [b for b in batch if "kind" in b], [b for b in batch if "variant_id" in b])
            batch.clear()

        for item in image_plan:
            if not item["source"].is_file():
                report["missing"] += 1
                report["errors"].append({"path": item["source_rel"], "error": "source_missing"})
                continue
            sha, state = copy_verified(item["source"], item["target"], item["sha256"])
            item["sha256"] = sha
            item["size"] = item["target"].stat().st_size
            image_updates.append(item)
            batch.append(item)
            report["copied" if state == "copied" else "existing"] += 1
            if len(batch) >= args.batch_size:
                flush()

        for item in variant_plan:
            if not item["source"].is_file():
                report["missing"] += 1
                report["errors"].append({"path": item["source_rel"], "error": "variant_source_missing"})
                continue
            sha, state = copy_verified(item["source"], item["target"], None)
            variant_updates.append(item)
            batch.append(item)
            report["copied" if state == "copied" else "existing"] += 1
            if len(batch) >= args.batch_size:
                flush()
        flush()

        after = {
            "images": conn.execute("SELECT count(*) FROM images").fetchone()[0],
            "variants": conn.execute("SELECT count(*) FROM image_variants").fetchone()[0],
        }
        report["images_after"] = after["images"]
        report["variants_after"] = after["variants"]
        if after != before:
            report["errors"].append({"error": f"行数变化: {before} -> {after}"})

    conn.close()
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "mode", "images_planned", "variants_planned", "copied", "existing", "missing",
        "images_before", "variants_before", "images_after", "variants_after",
    ) if key in report}, ensure_ascii=False, indent=2))
    if report["errors"]:
        print(f"errors={len(report['errors'])}: {report['errors'][:3]}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
