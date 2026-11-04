"""W4.1 统一资源与资产架构测试。

覆盖：
- Registry Manifest Schema / 唯一 ID / 依赖 / Hash；
- LF 规范化 Hash 与 raw 历史 Hash 双算法；
- 0023 mobile_image_events 旧结构重建；
- /modules 的 Registry 投影、/registry/validate、/prompts/stats、资产统计 API。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest
from sqlalchemy import create_engine, text

from app.core.resource_hash import LF_ALGORITHM, RAW_ALGORITHM, lf_hash_bytes, match_algorithm, raw_hash_bytes
from app.database.mobile_event_repair import MAIN_COLUMNS, ensure_mobile_events_w41
from app.services import registry_validator
from app.services.model_registry_service import ModelRegistryService
from app.services.workflow_registry_service import WorkflowRegistryService


def test_lf_hash_is_cross_platform_stable():
    lf = b'{"a": 1}\n'
    crlf = b'{"a": 1}\r\n'
    assert raw_hash_bytes(lf) != raw_hash_bytes(crlf)
    assert lf_hash_bytes(lf) == lf_hash_bytes(crlf)
    assert match_algorithm(raw_hash_bytes(crlf), raw_hash_bytes(crlf), lf_hash_bytes(crlf)) == RAW_ALGORITHM
    assert match_algorithm(lf_hash_bytes(lf), raw_hash_bytes(lf), lf_hash_bytes(lf)) == LF_ALGORITHM
    assert match_algorithm("0" * 16, raw_hash_bytes(lf), lf_hash_bytes(lf)) is None


def test_model_registry_has_six_active_models(settings):
    service = ModelRegistryService(settings)
    active = service.list_models(include_archived=False)
    assert {item["model_id"] for item in active} == {
        "qwen_image_2_1", "qwen3vl_8b_w4a8", "texture_fix_vae_qwen_image_2_1",
        "qwen_image_2_1_turbo8_lora", "f23gg_nsfw_qwen21", "miaomiao_harem_v14",
    }
    assert all(item["status"] == "released" for item in active)
    assert all(item["files"][0]["sha256"] != "unverified" for item in active)


def test_workflow_registry_four_active_versions(settings):
    service = WorkflowRegistryService(settings)
    active = service.active_workflows()
    assert {item["workflow_id"]: item["version"] for item in active} == {
        "basic_generate": "v2", "anime_generate": "v2",
        "img2img": "v3", "reference_generate": "v2",
    }
    for item in active:
        assert item["binding_valid"] is True
        assert item["hash_algorithm"] == "lf-normalized-v1"
        assert and_no_error(item["issues"])


def and_no_error(issues):
    return not any(issue["level"] == "error" for issue in issues)


def test_registry_validation_has_no_errors(settings):
    report = WorkflowRegistryService(settings).validate_all()
    assert report["checked"] >= 40
    assert report["errors"] == 0


def test_schema_rejects_missing_and_unknown_fields():
    from pathlib import Path

    registry_root = Path(__file__).resolve().parents[2] / "registry"
    schema = registry_validator.load_schema(registry_root, "model")
    issues = registry_validator.validate_document({"schema_version": "1.0", "model_id": "x"}, schema, path="$")
    assert any(issue["code"] == "SCHEMA_REQUIRED" for issue in issues)
    issues = registry_validator.validate_document(
        {
            "schema_version": "1.0", "model_id": "x", "version": "1.0.0", "display_name": "X",
            "family": "x", "model_type": "vae", "format": "safetensors", "status": "released",
            "files": [{"filename": "x", "folder": "vae", "required": True}], "unexpected": 1,
        }, schema,
    )
    assert any(issue["code"] == "SCHEMA_ADDITIONAL_PROPERTY" for issue in issues)


def _create_legacy_db(path):
    con = sqlite3.connect(path)
    con.executescript("""
    CREATE TABLE images (id TEXT PRIMARY KEY, updated_at TEXT);
    INSERT INTO images VALUES ('img_a', '2026-10-01T00:00:00Z');
    CREATE TABLE mobile_image_events (
        seq INTEGER PRIMARY KEY AUTOINCREMENT,
        image_id TEXT,
        event TEXT NOT NULL
    );
    INSERT INTO mobile_image_events (image_id, event) VALUES ('img_a', 'UPSERT');
    INSERT INTO mobile_image_events (image_id, event) VALUES ('img_a', 'UPSERT');
    INSERT INTO mobile_image_events (image_id, event) VALUES ('img_a', 'REMOVE');
    """)
    con.commit()
    con.close()


def test_0023_rebuilds_legacy_event_table(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        ensure_mobile_events_w41(conn)
    con = sqlite3.connect(db_path)
    columns = {row[1] for row in con.execute("PRAGMA table_info(mobile_image_events)")}
    assert columns >= MAIN_COLUMNS and "event" not in columns
    assert con.execute("SELECT count(*) FROM mobile_image_events").fetchone()[0] == 3
    # 新代码只写 event_type，不再需要 legacy event
    con.execute(
        "INSERT INTO mobile_image_events (event_id, event_type, image_id, revision, payload_json, created_at) "
        "VALUES ('mevt_new', 'IMAGE_CREATED', NULL, NULL, '{}', '2026-11-04T00:00:00Z')"
    )
    con.commit()
    assert con.execute("SELECT count(*) FROM mobile_image_events").fetchone()[0] == 4
    con.close()
    engine.dispose()


def test_0023_is_idempotent(tmp_path):
    db_path = tmp_path / "legacy.db"
    _create_legacy_db(db_path)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.begin() as conn:
        ensure_mobile_events_w41(conn)
    with engine.begin() as conn:
        ensure_mobile_events_w41(conn)
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT count(*) FROM mobile_image_events").fetchone()[0] == 3
    con.close()
    engine.dispose()


def test_modules_exposes_registry_projection(client):
    response = client.get("/api/v1/modules")
    assert response.status_code == 200
    modules = {item["module_id"]: item for item in response.json()}
    manifest = modules["basic_generate"]["registry"]
    assert manifest["workflow_id"] == "basic_generate"
    assert manifest["version"] == "v2"
    assert manifest["hashes"]["algorithm"] == "lf-normalized-v1"


def test_registry_and_prompt_stats_api(client):
    report = client.get("/api/v1/registry/validate").json()
    assert report["errors"] == 0
    stats = client.get("/api/v1/prompts/stats").json()
    assert stats["prompts_total"] >= 0
    assets = client.get("/api/v1/registry/assets", params={"check_files": False}).json()
    assert assets["total"] >= 0
    assert "by_kind" in assets and "variants_total" in assets
