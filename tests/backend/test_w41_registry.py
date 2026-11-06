"""W4.1 统一资源与资产架构测试。

覆盖：
- Registry Manifest Schema / 唯一 ID / 依赖 / Hash；
- LF 规范化 Hash 与 raw 历史 Hash 双算法；
- 0023 mobile_image_events 旧结构重建；
- /modules 的 Registry 投影、/registry/validate、/prompts/stats、资产统计 API；
- 模型多版本、模型依赖/历史覆盖负例、本机大小/SHA256 校验；
- Prompt tags/rating、Image Asset 投影与溯源。
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine, text

from app.core.resource_hash import LF_ALGORITHM, RAW_ALGORITHM, lf_hash_bytes, match_algorithm, raw_hash_bytes
from app.database.mobile_event_repair import MAIN_COLUMNS, ensure_mobile_events_w41
from app.services import asset_query_service, registry_validator
from app.services.model_registry_service import ModelRegistryService
from app.services.workflow_registry_service import WorkflowRegistryService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_ROOT = PROJECT_ROOT / "registry"


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


def test_registry_models_filter_by_compatible_workflow(client):
    response = client.get("/api/v1/registry/models", params={"workflow_id": "basic_generate"})
    assert response.status_code == 200, response.text
    ids = {item["model_id"] for item in response.json()["items"]}
    assert "qwen_image_2_1" in ids
    assert "miaomiao_harem_v14" not in ids


def test_registry_and_prompt_stats_api(client):
    report = client.get("/api/v1/registry/validate").json()
    assert report["errors"] == 0
    stats = client.get("/api/v1/prompts/stats").json()
    assert stats["prompts_total"] >= 0
    assets = client.get("/api/v1/registry/assets", params={"check_files": False}).json()
    assert assets["total"] >= 0
    assert "by_kind" in assets and "variants_total" in assets
    assert "images_without_thumbnail" in assets
    assert "with_prompt" in assets and "without_prompt" in assets


# ===== Model Center 多版本 / 依赖 / 本机校验 =====

def _model_manifest(model_id: str, version: str, filename: str = "m.safetensors", **extra) -> dict:
    return {
        "schema_version": "1.0",
        "model_id": model_id,
        "version": version,
        "display_name": model_id,
        "family": "test",
        "model_type": "vae",
        "format": "safetensors",
        "status": "released",
        "files": [{
            "filename": filename, "folder": "vae", "required": True,
            "size_bytes": 3, "sha256": "0" * 64,
        }],
        **extra,
    }


def _write_manifest(root: Path, relative: str, payload: dict) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_model_registry_supports_multiple_versions(tmp_path, settings):
    root = tmp_path / "registry"
    _write_manifest(root, "models/multi/model.yaml", _model_manifest("multi", "1.0.0"))
    _write_manifest(root, "models/multi/2.0.0/model.yaml", _model_manifest("multi", "2.0.0"))
    service = ModelRegistryService(settings, registry_root=root)
    assert service.get_model("multi")["version"] == "2.0.0"
    assert service.get_model("multi", "1.0.0")["version"] == "1.0.0"
    assert len(service.list_models()) == 2


def test_model_registry_rejects_duplicate_version(tmp_path, settings):
    root = tmp_path / "registry"
    _write_manifest(root, "models/dup/model.yaml", _model_manifest("dup", "1.0.0"))
    _write_manifest(root, "models/dup/1.0.0/model.yaml", _model_manifest("dup", "1.0.0"))
    shutil.copytree(REGISTRY_ROOT / "schemas", root / "schemas")
    service = ModelRegistryService(settings, registry_root=root)
    report = service.validate_all()
    assert any(issue["code"] == "DUPLICATE_MODEL_VERSION" for issue in report["issues"])


def test_model_registry_rejects_unknown_dependency(tmp_path, settings):
    root = tmp_path / "registry"
    manifest = _model_manifest("dep", "1.0.0")
    manifest["dependencies"] = [{"model_id": "ghost_model", "required": True}]
    _write_manifest(root, "models/dep/model.yaml", manifest)
    shutil.copytree(REGISTRY_ROOT / "schemas", root / "schemas")
    report = ModelRegistryService(settings, registry_root=root).validate_all()
    assert any(issue["code"] == "MODEL_DEPENDENCY_UNKNOWN" for issue in report["issues"])


def test_model_install_status_checks_size_and_sha256(tmp_path, settings):
    root = tmp_path / "registry"
    model_file = tmp_path / "models_root" / "vae" / "m.safetensors"
    model_file.parent.mkdir(parents=True)
    model_file.write_bytes(b"abc")
    manifest = _model_manifest("strict", "1.0.0")
    manifest["files"][0]["size_bytes"] = 999
    manifest["files"][0]["sha256"] = "f" * 64
    _write_manifest(root, "models/strict/model.yaml", manifest)
    local_settings = dataclasses.replace(
        settings, model_registry={"search_roots": [str(tmp_path / "models_root")], "verify_hash": True}
    )
    status = ModelRegistryService(local_settings, registry_root=root).install_status(
        "strict", version="1.0.0", verify_hash=True
    )
    assert status.status == "missing"
    assert status.size_mismatch and status.sha256_mismatch


def test_preflight_declared_model_size_mismatch_blocks(tmp_path, settings):
    from app.services.runtime_preflight_service import RuntimePreflightService

    root = tmp_path / "registry"
    model_file = tmp_path / "models_root" / "vae" / "m.safetensors"
    model_file.parent.mkdir(parents=True)
    model_file.write_bytes(b"abc")
    manifest = _model_manifest("strict", "1.0.0")
    manifest["files"][0]["size_bytes"] = 1
    _write_manifest(root, "models/strict/model.yaml", manifest)
    local_settings = dataclasses.replace(
        settings, model_registry={"search_roots": [str(tmp_path / "models_root")], "verify_hash": True}
    )
    service = RuntimePreflightService(local_settings, adapter=None)
    service._model_registry = ModelRegistryService(local_settings, registry_root=root)
    base = {"missing_requirements": [], "notes": []}
    checks = service._check_declared_model_files({("vae", "m.safetensors")}, base)
    assert checks and checks[0]["status"] == "missing"
    assert any("文件大小不匹配" in item for item in base["missing_requirements"])


def test_workflow_registry_rejects_unknown_model_dependency(settings):
    service = WorkflowRegistryService(settings)
    issues = service._check_models({
        "manifest_path": "test",
        "release_status": "released",
        "model_dependencies": [{"model_id": "ghost_model"}],
    })
    assert any(issue["code"] == "MODEL_DEPENDENCY_UNKNOWN" for issue in issues)


def test_workflow_registry_rejects_hash_error_and_duplicate_version(tmp_path, settings):
    source = (REGISTRY_ROOT / "workflows/basic_generate/v2/manifest.yaml").read_text(encoding="utf-8")
    manifest = yaml.safe_load(source)
    manifest["hashes"]["workflow_hash"] = "0" * 16

    root = tmp_path / "registry"
    shutil.copytree(REGISTRY_ROOT / "schemas", root / "schemas")
    _write_manifest(root, "workflows/basic_generate/v2/manifest.yaml", manifest)
    _write_manifest(root, "workflows/_history/basic_generate/v2/manifest.yaml", {
        **manifest, "hashes": yaml.safe_load(source)["hashes"],
    })
    report = WorkflowRegistryService(settings, registry_root=root).validate_all()
    codes = {issue["code"] for issue in report["issues"]}
    assert "HASH_MISMATCH" in codes
    assert "DUPLICATE_WORKFLOW_VERSION" in codes


def test_binding_loads_with_lf_hash_in_crlf_environment(tmp_path, monkeypatch):
    """LF/CRLF 双环境：磁盘 CRLF 时用 LF 标准化 Hash 仍能加载；raw 历史 Hash 也接受。"""
    from app.engine.base import EngineBindingRef, EngineError
    from app.engine.comfyui import ComfyUIAdapter

    binding_dir = tmp_path / "basic_generate" / "v1"
    binding_dir.mkdir(parents=True)
    workflow_bytes = b'{"1": {"class_type": "KSampler", "inputs": {}}}\r\n'
    binding_bytes = b"module: basic_generate\r\nprovider: comfyui\r\nbinding_version: v1\r\n"
    (binding_dir / "workflow.json").write_bytes(workflow_bytes)
    (binding_dir / "binding.yaml").write_bytes(binding_bytes)
    monkeypatch.setattr(ComfyUIAdapter, "binding_dir", staticmethod(lambda _m, _v: binding_dir))
    adapter = ComfyUIAdapter({}, {"url": "http://127.0.0.1:9"})
    lf_workflow = lf_hash_bytes(workflow_bytes)
    lf_binding = lf_hash_bytes(binding_bytes)
    raw_workflow = raw_hash_bytes(workflow_bytes)
    raw_binding = raw_hash_bytes(binding_bytes)
    assert raw_workflow != lf_workflow and raw_binding != lf_binding

    _w, _b, workflow_hash, binding_hash = adapter.load_binding(EngineBindingRef(
        module_id="basic_generate", provider="comfyui", binding_version="v1",
        workflow_hash=lf_workflow, binding_hash=lf_binding,
    ))
    assert workflow_hash == lf_workflow and binding_hash == lf_binding
    # 历史 Job 的 raw Hash 仍可执行（不因换行迁移全部失效）
    adapter.load_binding(EngineBindingRef(
        module_id="basic_generate", provider="comfyui", binding_version="v1",
        workflow_hash=raw_workflow, binding_hash=raw_binding,
    ))
    with pytest.raises(EngineError):
        adapter.load_binding(EngineBindingRef(
            module_id="basic_generate", provider="comfyui", binding_version="v1",
            workflow_hash="0" * 16,
        ))


# ===== Prompt Center / Image Asset =====

def test_prompt_center_exposes_tags_and_rating(client):
    created = client.post("/api/v1/prompts", json={
        "name": "w41-tags", "mode": "full", "positive_prompt": "tagged prompt", "tags": ["portrait", "night"],
    })
    assert created.status_code == 201, created.text
    prompt_id = created.json()["id"]
    assert created.json()["tags"] == ["portrait", "night"]
    detail = client.get(f"/api/v1/prompts/{prompt_id}/center").json()
    assert detail["tags"] == ["portrait", "night"]
    assert detail["rating"] is None
    evaluated = client.post(f"/api/v1/prompts/{prompt_id}/evaluations", json={"overall_score": 5})
    assert evaluated.status_code == 201, evaluated.text
    detail = client.get(f"/api/v1/prompts/{prompt_id}/center").json()
    assert detail["rating"] == 5


def test_asset_import_is_unified_and_has_no_permanent_delete(client, png_bytes):
    response = client.post(
        "/api/v1/images/import",
        files=[("files", ("w41.png", png_bytes, "image/png"))],
    )
    assert response.status_code == 201, response.text
    item = response.json()["imported"][0]["image"]
    image_id = item["id"]
    assert item["storage_key"].startswith("assets/images/")
    assert item["sha256"] and item["mime_type"] == "image/png"
    provenance = client.get(f"/api/v1/images/{image_id}/provenance").json()
    assert provenance["image_id"] == image_id
    assert "prompt_id" in provenance and "model_snapshot" in provenance
    # 手机端/桌面端都不得永久删除图片
    assert client.delete(f"/api/v1/images/{image_id}").status_code == 405


def test_asset_stats_report_missing_and_orphans(client, session, settings):
    from app.models import Image
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    orphan = storage.absolutize("assets/images/2099/01/asset_orphan_w41")
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"orphan")
    missing = Image(
        id="img_w41_missing", kind="original", file_path="assets/images/2099/01/img_w41_missing/original.png",
        width=1, height=1, source="comfyui", sha256="a" * 64,
    )
    session.add(missing)
    session.commit()
    stats = client.get("/api/v1/registry/assets").json()
    assert stats["missing_files"] >= 1
    orphans = client.get("/api/v1/registry/assets/orphans").json()
    assert any(item["path"].endswith("asset_orphan_w41") for item in orphans["items"])
    assert asset_query_service.image_asset_view(missing)["asset_type"] == "original"
