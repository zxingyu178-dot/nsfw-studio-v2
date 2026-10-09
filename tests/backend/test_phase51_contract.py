"""Phase 5.1 测试：图片 Pipeline 契约收口（Task1-Task9）。

覆盖：
- Recipe 完整 Workflow 身份（provider / 双 hash）不丢失、不偷偷升级；
- Recipe / Job / JobStage config 单链（模块参数唯一事实源）；
- 输入图片不得被静默忽略（UNUSED_INPUT_IMAGE / INPUT_IMAGE_REQUIRED / 链式校验）；
- /modules 真实可用性（registered ≠ available，Gate 依据 available=true）；
- Face Asset 参考图可清除（clear 语义，旧版本保留）；
- 导入去重 DB 唯一索引兜底（并发 IntegrityError → 返回已存在图片，不是 500）。
"""
from __future__ import annotations

import dataclasses
import json
import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings, WorkflowConfig
from app.core.errors import ValidationError
from app.database import init_database, make_engine
from app.main import create_app
from app.models import JobStage
from app.services import image_service
from app.services.pipeline_validator import PipelineValidator
from app.storage.manager import StorageManager


# ===== 工具 =====

def make_snapshot(count: int = 1, **overrides) -> dict:
    snapshot = {
        "prompt_mode": "structured",
        "structured_prompt": {"style": "anime", "scene": "cafe"},
        "full_prompt": "",
        "negative_prompt": "blurry",
        "selected_assets": {},
        "width": 512,
        "height": 768,
        "count": count,
        "seed_mode": "random",
        "workflow_modules": [],
    }
    snapshot.update(overrides)
    return snapshot


def mock_settings(settings: Settings, **options) -> Settings:
    merged = {"worker_poll_interval_ms": 20, "engine_poll_ms": 20}
    merged.update(options)
    return dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={"engine": {"provider": "mock", "options": merged}}),
    )


@pytest.fixture()
def mock_client(settings):
    from fastapi.testclient import TestClient

    app = create_app(mock_settings(settings))
    with TestClient(app) as test_client:
        yield test_client


def wait_for(client, job_id: str, predicate, timeout: float = 60.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/api/v1/jobs/{job_id}").json()
        if predicate(last):
            return last
        time.sleep(0.05)
    raise AssertionError(f"等待任务状态超时: {json.dumps(last, ensure_ascii=False)[:500]}")


def import_one(client, name: str, data: bytes, content_type: str = "image/png") -> dict:
    response = client.post(
        "/api/v1/images/import",
        files=[("files", (name, data, content_type))],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["imported_count"] == 1, body
    return body["imported"][0]["image"]


# ===== Task1/Task2：Recipe 完整工作流身份 =====

FULL_IDENTITY = {
    "module_id": "basic_generate",
    "module_version": "v1",
    "provider": "mock",
    "binding_version": "v1",
    "workflow_hash": "wfh_abc123",
    "binding_hash": "bnh_def456",
    "config": {},
}


def test_recipe_preserves_full_workflow_identity(mock_client):
    """Task2（P0）：Recipe 保存不得丢失 provider / binding_version / 双 hash。"""
    response = mock_client.post("/api/v1/recipes", json={
        "name": "身份配方",
        "snapshot": make_snapshot(workflow_modules=[FULL_IDENTITY]),
    })
    assert response.status_code == 201, response.text
    modules = response.json()["current_version"]["workflow_snapshot"]["modules"]
    assert len(modules) == 1
    stored = modules[0]
    for key, value in FULL_IDENTITY.items():
        assert stored.get(key) == value, f"字段 {key} 丢失或被改写: {stored}"

    # 关闭 → 重新打开：身份完全一致（Version immutable）
    recipe_id = response.json()["id"]
    reopened = mock_client.get(f"/api/v1/recipes/{recipe_id}").json()
    assert reopened["current_version"]["workflow_snapshot"]["modules"][0] == stored


def test_recipe_identity_never_silently_upgrades(mock_client):
    """Task2 关键场景：Recipe 保存 basic_generate/v1；系统默认切到 v2 → 旧 Recipe 仍是 v1 + 原双 hash。"""
    recipe = mock_client.post("/api/v1/recipes", json={
        "name": "旧版配方",
        "snapshot": make_snapshot(workflow_modules=[FULL_IDENTITY]),
    }).json()

    # 模拟系统默认升级（仅改内存配置）
    engine_cfg = mock_client.app.state.settings.workflow.raw["engine"]
    engine_cfg["module_version"] = "v2"
    engine_cfg["binding_version"] = "v2"
    try:
        reopened = mock_client.get(f"/api/v1/recipes/{recipe['id']}").json()
        stored = reopened["current_version"]["workflow_snapshot"]["modules"][0]
        assert stored["module_version"] == "v1", "旧 Recipe 不得静默升级到 v2"
        assert stored["workflow_hash"] == "wfh_abc123"
        assert stored["binding_hash"] == "bnh_def456"

        # 用该 Recipe 的模块身份提交 Job：必须固定原 v1 身份
        snapshot = make_snapshot(workflow_modules=[stored])
        job = mock_client.post("/api/v1/jobs", json={"snapshot": snapshot}).json()
        assert job["module_version"] == "v1"
        assert job["workflow_hash"] == "wfh_abc123"
        wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")
    finally:
        engine_cfg.pop("module_version", None)
        engine_cfg.pop("binding_version", None)


def test_recipe_config_roundtrip(mock_client):
    """Task3：config 必须随 Recipe 保存 / 恢复（模块参数唯一入口）。"""
    module = {**FULL_IDENTITY, "config": {"denoise": 0.55}}
    recipe = mock_client.post("/api/v1/recipes", json={
        "name": "参数配方",
        "snapshot": make_snapshot(workflow_modules=[module]),
    }).json()
    stored = recipe["current_version"]["workflow_snapshot"]["modules"][0]
    assert stored["config"] == {"denoise": 0.55}

    # 内容一致（含 config）→ 不产生新版本
    again = mock_client.post(
        f"/api/v1/recipes/{recipe['id']}/versions",
        json={"name": "参数配方", "snapshot": make_snapshot(workflow_modules=[module])},
    ).json()
    assert again["version_no"] == 1

    # config 改变 → 新版本，身份保留
    changed = {**FULL_IDENTITY, "config": {"denoise": 0.7}}
    newer = mock_client.post(
        f"/api/v1/recipes/{recipe['id']}/versions",
        json={"name": "参数配方", "snapshot": make_snapshot(workflow_modules=[changed])},
    ).json()
    assert newer["version_no"] == 2
    assert newer["workflow_snapshot"]["modules"][0]["config"] == {"denoise": 0.7}


def test_recipe_unpinned_module_resolves_identity_at_save(mock_client):
    """Task2：普通新建工作台只带 module_id 时，保存 Recipe 尽量固化当前真实身份。"""
    recipe = mock_client.post("/api/v1/recipes", json={
        "name": "未固化配方",
        "snapshot": make_snapshot(workflow_modules=[{"module_id": "basic_generate"}]),
    }).json()
    stored = recipe["current_version"]["workflow_snapshot"]["modules"][0]
    assert stored["module_version"] == "v1"
    assert stored["provider"] == "mock"
    assert stored["binding_version"] == "v1"


# ===== Task3：config 单链 → JobStage.config_json =====

def test_job_stage_config_json_materialized(mock_client, session):
    """Task3：Workbench workflow_modules[].config → Job.workflow_snapshot → JobStage.config_json。"""
    snapshot = make_snapshot(count=1, workflow_modules=[
        {"module_id": "basic_generate", "config": {"marker": "a"}},
        {"module_id": "upscale", "config": {"marker": "b"}},
    ])
    response = mock_client.post("/api/v1/jobs", json={"snapshot": snapshot})
    assert response.status_code == 201, response.text
    job = response.json()

    modules = job["workflow_snapshot"]["modules"]
    assert modules[0]["config"] == {"marker": "a"}
    assert modules[1]["config"] == {"marker": "b"}

    stages = list(session.query(JobStage).filter(JobStage.job_id == job["id"]).order_by(JobStage.stage_index))
    assert [json.loads(stage.config_json) for stage in stages] == [{"marker": "a"}, {"marker": "b"}]
    wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")


# ===== Task4/Task5：输入图消费校验 =====

def test_generate_job_rejects_unused_input_image(mock_client, png_bytes):
    """P0：basic_generate 不消费输入图 → 携带输入图必须被拒绝。"""
    image = import_one(mock_client, "src.png", png_bytes)
    response = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(input_images=[{"role": "source", "image_id": image["id"]}]),
    })
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "UNUSED_INPUT_IMAGE"


def test_generate_job_requires_input_for_input_module(mock_client):
    """P0：Pipeline 需要输入图（upscale 为首模块）却没有输入图 → 必须拒绝。"""
    response = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(workflow_modules=[{"module_id": "upscale"}]),
    })
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "INPUT_IMAGE_REQUIRED"


def test_pipeline_validator_rules():
    """Task5：PipelineValidator 统一规则（Stage0 输入需求 / 链式接收 / 未知模块）。"""
    validator = PipelineValidator()

    # 合法：纯文生图；文生图 → 高清（链式接收上一 Stage 输出）
    validator.validate([{"module_id": "basic_generate"}], job_kind="generate", has_input_image=False)
    validator.validate(
        [{"module_id": "basic_generate"}, {"module_id": "upscale"}],
        job_kind="generate", has_input_image=False,
    )
    # 合法：处理型 Job（upscale-only + 输入图）
    validator.validate([{"module_id": "upscale"}], job_kind="process", has_input_image=True)

    # 非法：输入图片没人消费
    with pytest.raises(ValidationError) as error:
        validator.validate([{"module_id": "basic_generate"}], job_kind="generate", has_input_image=True)
    assert error.value.code == "UNUSED_INPUT_IMAGE"

    # 非法：需要输入图却没有
    with pytest.raises(ValidationError) as error:
        validator.validate([{"module_id": "upscale"}], job_kind="generate", has_input_image=False)
    assert error.value.code == "INPUT_IMAGE_REQUIRED"

    # 非法：同一模块重复出现（Phase 6 Task4：第一版明确禁止，专用错误码）
    with pytest.raises(ValidationError) as error:
        validator.validate(
            [{"module_id": "basic_generate"}, {"module_id": "basic_generate"}],
            job_kind="generate", has_input_image=False,
        )
    assert error.value.code == "PIPELINE_DUPLICATE_MODULE"

    # 非法：中间 Stage 不消费上一 Stage 输出（链式执行无意义）
    with pytest.raises(ValidationError) as error:
        validator.validate(
            [{"module_id": "upscale"}, {"module_id": "basic_generate"}],
            job_kind="generate", has_input_image=True,
        )
    assert error.value.code == "PIPELINE_INVALID"

    # 非法：未知模块（创建期拒绝）
    with pytest.raises(ValidationError) as error:
        validator.validate([{"module_id": "nope"}], job_kind="generate", has_input_image=False)
    assert error.value.code == "WORKFLOW_ERROR"

    # 非法：处理型 Job 混入非 upscale 模块
    with pytest.raises(ValidationError) as error:
        validator.validate(
            [{"module_id": "basic_generate"}, {"module_id": "upscale"}],
            job_kind="process", has_input_image=True,
        )
    assert error.value.code == "PIPELINE_INVALID"


def test_legal_chain_job_completes(mock_client):
    """合法链（basic_generate → upscale）在新校验下照常执行。"""
    job = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(count=1, workflow_modules=[
            {"module_id": "basic_generate"}, {"module_id": "upscale"},
        ]),
    }).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")
    assert [stage["module_id"] for stage in final["stages"]] == ["basic_generate", "upscale"]


# ===== Task7：/modules 真实可用性 =====

def test_modules_api_reports_real_availability(client):
    """comfyui provider：binding 在磁盘 → available=true；报告 provider/binding_version。"""
    modules = {item["module_id"]: item for item in client.get("/api/v1/modules").json()}
    for module_id in ("basic_generate", "upscale"):
        info = modules[module_id]
        assert info["registered"] is True
        assert info["available"] is True, info
        assert info["provider"] == "comfyui"
        assert info["binding_version"] == "v1"
        assert info["unavailable_reason"] is None


def test_modules_api_unavailable_when_binding_missing(client, monkeypatch, tmp_path):
    """registered ≠ available：binding 缺失 → available=false + binding_not_configured。"""
    from app.engine import comfyui as comfyui_module

    monkeypatch.setattr(comfyui_module, "PROVIDERS_DIR", tmp_path / "empty_providers")
    modules = {item["module_id"]: item for item in client.get("/api/v1/modules").json()}
    for module_id in ("basic_generate", "upscale"):
        info = modules[module_id]
        assert info["registered"] is True
        assert info["available"] is False
        assert info["unavailable_reason"] == "binding_not_configured"


def test_modules_api_unavailable_without_engine(settings):
    """unbound provider：模块不可执行 → available=false（绝不因注册了就显示可用）。"""
    from fastapi.testclient import TestClient

    unbound = dataclasses.replace(
        settings, workflow=WorkflowConfig(raw={"engine": {"provider": "unbound"}})
    )
    app = create_app(unbound)
    with TestClient(app) as test_client:
        modules = {item["module_id"]: item for item in test_client.get("/api/v1/modules").json()}
        assert modules["basic_generate"]["available"] is False
        assert modules["basic_generate"]["unavailable_reason"] == "engine_not_configured"


# ===== Task8：Face Asset 参考图清除 =====

def test_face_asset_reference_can_be_cleared(mock_client, png_bytes):
    image = import_one(mock_client, "ref.png", png_bytes)
    asset = mock_client.post("/api/v1/assets", data={
        "name": "人脸A", "type": "face", "reference_image_id": image["id"],
    }).json()
    assert asset["current_version"]["reference_images"] == [image["id"]]

    # clear → 新版本 reference=none；旧版本保持原参考图
    cleared = mock_client.post(
        f"/api/v1/assets/{asset['id']}/versions",
        data={"reference_action": "clear"},
    )
    assert cleared.status_code == 201, cleared.text
    cleared_version = cleared.json()
    assert cleared_version["version_no"] == 2
    assert cleared_version["reference_images"] == []

    versions = mock_client.get(f"/api/v1/assets/{asset['id']}/versions").json()
    v1 = next(version for version in versions if version["version_no"] == 1)
    assert v1["reference_images"] == [image["id"]], "旧版本必须保留原参考图（immutable）"

    # 已无参考图时再次 clear → 内容无变化，不产生新版本
    again = mock_client.post(
        f"/api/v1/assets/{asset['id']}/versions",
        data={"reference_action": "clear"},
    ).json()
    assert again["version_no"] == 2

    # set 必须携带图片；非法 action 值直接拒绝
    bad_set = mock_client.post(
        f"/api/v1/assets/{asset['id']}/versions",
        data={"reference_action": "set"},
    )
    assert bad_set.status_code == 400
    assert bad_set.json()["error"]["code"] == "ASSET_REFERENCE_INVALID"
    bad_action = mock_client.post(
        f"/api/v1/assets/{asset['id']}/versions",
        data={"reference_action": "drop"},
    )
    assert bad_action.status_code == 400
    assert bad_action.json()["error"]["code"] == "ASSET_REFERENCE_ACTION_INVALID"


# ===== Task9：导入去重 DB 唯一约束 =====

def test_migration_0011_unique_index(settings, session):
    index_names = {
        row[0] for row in session.execute(text("SELECT name FROM sqlite_master WHERE type = 'index'"))
    }
    assert "uq_images_import_sha256" in index_names

    engine = make_engine(settings.storage.database_path)
    try:
        assert init_database(engine) == [], "重复启动不得重复应用迁移"
    finally:
        engine.dispose()


def test_import_duplicate_sha_guard(session, settings, png_bytes, monkeypatch):
    """Task9：应用层去重被绕过的并发竞态 → DB 唯一索引兜底，返回已存在图片而不是 500。"""
    storage = StorageManager(settings)
    first = image_service.import_images_batch(session, storage, [("a.png", "image/png", png_bytes)])
    assert len(first.imported) == 1
    existing_id = first.imported[0].id

    # 1) DB 兜底：直接插入同 sha256 行必须被唯一索引拒绝
    sha = first.imported[0].sha256
    assert sha
    with pytest.raises(IntegrityError):
        session.execute(text(
            "INSERT INTO images (id, kind, file_path, width, height, source, metadata_json, "
            "created_at, updated_at, sha256) VALUES "
            "('img_dup', 'original', 'images/originals/img_dup/original.png', 1, 1, 'import', "
            "'{}', '2026-01-01T00:00:00', '2026-01-01T00:00:00', :sha)"
        ), {"sha": sha})
    session.rollback()

    # 2) 并发竞态：模拟"应用层查重时不存在，写入时已被别的请求抢先"
    real_find = image_service.find_image_by_sha256
    calls = {"count": 0}

    def race_find(db_session, digest):
        if calls["count"] == 0:
            calls["count"] += 1
            return None  # 第一次查重"没看见"（模拟并发窗口）
        return real_find(db_session, digest)

    monkeypatch.setattr(image_service, "find_image_by_sha256", race_find)
    second = image_service.import_images_batch(session, storage, [("b.png", "image/png", png_bytes)])
    assert second.imported == []
    assert second.failed == []
    assert len(second.duplicates) == 1
    assert second.duplicates[0]["image_id"] == existing_id

    # 库中只有一行该 sha256
    count = session.execute(
        text("SELECT COUNT(*) FROM images WHERE sha256 = :sha"), {"sha": sha}
    ).scalar_one()
    assert count == 1