"""迁移测试只使用临时数据，不读取真实归档。"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

import pytest
from PIL import Image

from app.database.backup import backup_database

PROJECT = Path(__file__).resolve().parents[2]
SCRIPT = PROJECT / "scripts" / "migrate_v1_legacy.py"


@pytest.fixture()
def migration_data(tmp_path, settings, session_factory):
    source = tmp_path / "legacy"
    (source / "runtime").mkdir(parents=True)
    (source / "temp/face_input").mkdir(parents=True)
    prompts = [
        {"id": "旧一", "name": "名称一", "positive": " 原文\npositive ", "negative": " 原负向 "},
        {"id": "旧二", "name": "长" * 260, "positive": "second", "negative": ""},
    ]
    faces = [{"id": "face_001", "filename": "characters/missing.png",
              "name": "测试人脸", "tags": ["标签二", "标签一"],
              "created_at": 1700000000.25, "source": "fixture"}]
    for name, rows in (("promptlib", prompts), ("faces", faces)):
        (source / f"runtime/{name}.json").write_text(
            json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    Image.new("RGB", (24, 24), "blue").save(source / "temp/face_input/face_1.jpg")
    root = settings.storage.data_root
    return source, root, settings.storage.database_path


def run_cli(data, *args):
    source, root, _ = data
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--source", str(source), "--data-root", str(root), *args],
        cwd=PROJECT, env=env, capture_output=True, text=True, encoding="utf-8",
        timeout=30,
    )


def snapshot(root):
    # SQLite 只读 WAL 连接也可能创建共享内存/空 WAL；它们不是业务数据。
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob("*") if p.is_file()
            and not p.name.endswith("-shm")
            and not (p.name.endswith("-wal") and p.stat().st_size == 0)}


def counts(database):
    with sqlite3.connect(database) as conn:
        return tuple(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                     for table in ("prompts", "prompt_versions", "assets", "asset_versions"))


def backup(data):
    return backup_database(data[2], data[1] / "backups")


def test_default_and_explicit_dry_run_do_not_write(migration_data):
    before = snapshot(migration_data[1])
    for args in ((), ("--dry-run",), ("--dry-run", "--force")):
        result = run_cli(migration_data, *args)
        assert result.returncode == 0, result.stderr
        assert "prompts=2 faces=1" in result.stdout
        assert snapshot(migration_data[1]) == before
    assert counts(migration_data[2]) == (0, 0, 0, 0)


def test_apply_and_repeat_are_idempotent(migration_data):
    source, root, database = migration_data
    backup(migration_data)
    result = run_cli(migration_data, "--apply")
    assert result.returncode == 0, result.stderr
    assert "created=3 skipped=0" in result.stdout
    assert counts(database) == (2, 2, 1, 1)
    with sqlite3.connect(database) as conn:
        row = conn.execute(
            "SELECT mode,positive_prompt,negative_prompt,version_no,structured_json "
            "FROM prompt_versions WHERE positive_prompt LIKE '%positive%'").fetchone()
        assert row[:4] == ("full", " 原文\npositive ", " 原负向 ", 1)
        assert json.loads(row[4])["_v1_migration"]
        assert conn.execute("SELECT max(length(name)) FROM prompts").fetchone()[0] == 255
        name, tags, preview = conn.execute(
            "SELECT a.name,v.tags_json,v.preview_path FROM assets a "
            "JOIN asset_versions v ON a.current_version_id=v.id").fetchone()
        assert name == "测试人脸"
        assert set(json.loads(tags)) == {"标签一", "标签二"}
        assert not Path(preview).is_absolute()
        assert preview.startswith("assets/face/") and preview.endswith("/v0001/preview.jpg")
        assert (root / preview).read_bytes() == (source / "temp/face_input/face_1.jpg").read_bytes()
    maps = list((root / "backups").glob("v1-migration-map-*.json"))
    assert len(maps) == 1
    mapping = json.loads(maps[0].read_text(encoding="utf-8"))
    assert len(mapping["prompt_id_map"]) == 2
    assert len(mapping["asset_id_map"]) == 1
    result = run_cli(migration_data, "--apply")
    assert result.returncode == 0, result.stderr
    assert "created=0 skipped=3" in result.stdout
    assert counts(database) == (2, 2, 1, 1)


@pytest.mark.parametrize("age", [None, 3601, -60])
def test_apply_requires_recent_backup(migration_data, age):
    if age is not None:
        path = backup(migration_data)
        stamp = time.time() - age
        os.utime(path, (stamp, stamp))
    before = snapshot(migration_data[1])
    result = run_cli(migration_data, "--apply")
    assert result.returncode != 0
    assert "backup_db.py" in result.stderr
    assert snapshot(migration_data[1]) == before


def test_force_warns_and_does_not_mean_apply(migration_data):
    result = run_cli(migration_data, "--force")
    assert result.returncode == 0
    assert counts(migration_data[2]) == (0, 0, 0, 0)
    result = run_cli(migration_data, "--apply", "--force")
    assert result.returncode == 0, result.stderr
    assert "危险" in result.stdout
    assert counts(migration_data[2]) == (2, 2, 1, 1)


def test_invalid_image_leaves_database_and_files_unchanged(migration_data):
    (migration_data[0] / "temp/face_input/face_1.jpg").write_bytes(b"broken")
    backup(migration_data)
    before = snapshot(migration_data[1])
    result = run_cli(migration_data, "--apply")
    assert result.returncode != 0
    assert "迁移失败" in result.stderr
    assert "image" in result.stderr.lower()
    assert snapshot(migration_data[1]) == before
    assert counts(migration_data[2]) == (0, 0, 0, 0)


def test_missing_database_is_not_created(migration_data):
    missing = migration_data[1] / "missing"
    result = run_cli(migration_data, "--data-root", str(missing))
    assert result.returncode != 0
    assert not missing.exists()


def load_tool():
    import importlib.util
    spec = importlib.util.spec_from_file_location("migrate_v1_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_config_priority(tmp_path, monkeypatch):
    tool = load_tool()
    local = tmp_path / "config.local.yaml"
    local.write_text("data_root: 'local-data'\n", encoding="utf-8")
    monkeypatch.delenv("NSFW_STUDIO_DATA_ROOT", raising=False)
    assert tool.resolve_data_root(None, tmp_path) == Path("local-data").resolve()
    monkeypatch.setenv("NSFW_STUDIO_DATA_ROOT", "env-data")
    assert tool.resolve_data_root(None, tmp_path) == Path("env-data").resolve()
    assert tool.resolve_data_root("cli-data", tmp_path) == Path("cli-data").resolve()
    monkeypatch.delenv("NSFW_STUDIO_DATA_ROOT")
    local.write_text("{}\n", encoding="utf-8")
    assert tool.resolve_data_root(None, tmp_path) == Path("D:/NSFW-Studio-Data").resolve()


def test_unmarked_prompt_not_skipped_and_asset_tags_are_sets(migration_data):
    backup(migration_data)
    assert run_cli(migration_data, "--apply").returncode == 0
    with sqlite3.connect(migration_data[2]) as conn:
        conn.execute("UPDATE prompt_versions SET structured_json='{}'")
        conn.execute("UPDATE asset_versions SET tags_json=?", ('["标签一", "标签二", "标签一"]',))
    result = run_cli(migration_data, "--apply")
    assert result.returncode == 0, result.stderr
    assert "created=2 skipped=1" in result.stdout
    assert counts(migration_data[2]) == (4, 4, 1, 1)


def test_sql_failure_rolls_back_all_inserts_and_keeps_trace(migration_data):
    backup(migration_data)
    with sqlite3.connect(migration_data[2]) as conn:
        conn.execute("CREATE TRIGGER fail_asset BEFORE INSERT ON assets "
                     "BEGIN SELECT RAISE(ABORT, 'injected failure'); END")
    result = run_cli(migration_data, "--apply")
    assert result.returncode != 0
    assert counts(migration_data[2]) == (0, 0, 0, 0)
    maps = list((migration_data[1] / "backups").glob("v1-migration-map-*.json"))
    assert len(maps) == 1
    mapping = json.loads(maps[0].read_text(encoding="utf-8"))
    preview = mapping["records"]["faces"][0]["preview_path"]
    assert (migration_data[1] / preview).exists()
    assert "prepared" in mapping["transaction_status"]


def test_map_failure_prevents_any_database_insert(migration_data):
    backup(migration_data)
    (migration_data[1] / "backups").rename(migration_data[1] / "saved-backups")
    (migration_data[1] / "backups").write_text("阻止创建映射", encoding="utf-8")
    result = run_cli(migration_data, "--apply", "--force")
    assert result.returncode != 0
    assert counts(migration_data[2]) == (0, 0, 0, 0)
    assert not list((migration_data[1] / "assets").rglob("*.jpg"))


def test_insert_only_authorizer_blocks_mutation(migration_data):
    tool = load_tool()
    conn = tool.connect(migration_data[2], True)
    try:
        for sql in ("DELETE FROM prompts", "UPDATE prompts SET name='changed'",
                    "CREATE TABLE bad(id)", "INSERT INTO migration VALUES ('bad','bad','bad','bad')"):
            with pytest.raises(sqlite3.DatabaseError):
                conn.execute(sql)
    finally:
        conn.close()


def test_missing_legacy_prompt_id_is_traceable_and_idempotent(migration_data):
    source = migration_data[0] / "runtime/promptlib.json"
    rows = json.loads(source.read_text(encoding="utf-8"))
    rows[0].pop("id")
    rows[1]["id"] = None
    source.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    backup(migration_data)
    first = run_cli(migration_data, "--apply")
    assert first.returncode == 0, first.stderr
    assert "缺失提示词 ID：2" in first.stdout
    mapping_file = next((migration_data[1] / "backups").glob("v1-migration-map-*.json"))
    mapping = json.loads(mapping_file.read_text(encoding="utf-8"))
    records = mapping["records"]["prompts"]
    assert all(item["original_id"] is None for item in records)
    assert len(set(item["source_id"] for item in records)) == 2
    assert run_cli(migration_data, "--apply").returncode == 0
    assert counts(migration_data[2]) == (2, 2, 1, 1)


def test_mislabeled_webp_uses_real_format_without_reencoding(migration_data):
    image = migration_data[0] / "temp/face_input/face_1.jpg"
    Image.new("RGB", (24, 24), "blue").save(image, format="WEBP")
    backup(migration_data)
    result = run_cli(migration_data, "--apply")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(migration_data[2]) as conn:
        preview = conn.execute("SELECT preview_path FROM asset_versions").fetchone()[0]
    assert preview.endswith("/preview.webp")
    assert (migration_data[1] / preview).read_bytes() == image.read_bytes()


def test_backup_restore_roundtrip_preserves_existing_prompt(migration_data, session_factory):
    from app.services.prompt_service import create_prompt
    with session_factory() as session:
        existing = create_prompt(session, name="已有记录", mode="full", positive_prompt="不可覆盖")
        existing_id = existing.id
    saved = backup(migration_data)
    result = run_cli(migration_data, "--apply")
    assert result.returncode == 0, result.stderr
    assert counts(migration_data[2]) == (3, 3, 1, 1)
    # 仅在临时测试库演练 SQLite backup API 恢复；不物理删除任何图片。
    with sqlite3.connect(saved) as source, sqlite3.connect(migration_data[2]) as target:
        source.backup(target)
    assert counts(migration_data[2]) == (1, 1, 0, 0)
    with sqlite3.connect(migration_data[2]) as conn:
        assert conn.execute("SELECT id,name FROM prompts").fetchone() == (existing_id, "已有记录")
        assert conn.execute("SELECT positive_prompt FROM prompt_versions").fetchone()[0] == "不可覆盖"
    assert len(list((migration_data[1] / "assets/face").rglob("preview.jpg"))) == 1


@pytest.mark.parametrize("kind", ["text", "wrong_schema", "live_hardlink"])
def test_invalid_backup_cannot_unlock_apply(migration_data, kind):
    path = migration_data[1] / "backups/studio-invalid.db"
    if kind == "text":
        path.write_text("这不是数据库备份", encoding="utf-8")
    elif kind == "wrong_schema":
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE unrelated (id)")
    else:
        os.link(migration_data[2], path)
    result = run_cli(migration_data, "--apply")
    assert result.returncode != 0
    assert "backup_db.py" in result.stderr
    assert counts(migration_data[2]) == (0, 0, 0, 0)
