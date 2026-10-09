"""Phase 7 Task2 / Task7 / Task8 回归：能力驱动校验 + 幂等指纹 + 三个未来兼容点。

- Task2：process Job 校验从 "必须且只能是 upscale" 改为 ModuleCapabilities 驱动
  （allowed_job_kinds / can_start_from_image）——新增处理模块不再修改 PipelineValidator；
- Task7：(source, client_request_id) 相同 + payload 不同 → IDEMPOTENCY_KEY_CONFLICT；
- Task8-①：/modules 的 capabilities 按实际选中的 module_version 获取；
- Task8-②：Image → Workbench 生成上下文按模块语义（is_generative）判定，不依赖 seed 数据；
- Task8-③：非 comfyui/mock 引擎输出不得被 Image.source 错标成 import。
"""
from __future__ import annotations

import dataclasses
import json
import time

import pytest

from app.core.config import Settings, WorkflowConfig
from app.core.errors import ValidationError
from app.engine.base import EngineAdapter, EngineBindingRef, EngineOutputFile
from app.main import create_app
from app.models import Image, Job, JobItem, JobStage, JobStageItem
from app.services.pipeline_validator import PipelineValidator
from app.workflows.base import (
    ModuleCapabilities,
    WorkflowInput,
    WorkflowModule,
    WorkflowOutput,
    WorkflowValidation,
)
from app.workflows.basic_generate import BasicGenerateModule
from app.workflows.img2img import Img2ImgModule
from app.workflows.registry import ModuleRegistry
from app.workflows.upscale import UpscaleModule


# ===== 工具（与其他 Phase 测试同构） =====

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
    raise AssertionError(f"等待任务状态超时: {json.dumps(last, ensure_ascii=False)[:400]}")


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


def import_one(client, name: str, data: bytes) -> dict:
    response = client.post("/api/v1/images/import", files=[("files", (name, data, "image/png"))])
    assert response.status_code == 201, response.text
    return response.json()["imported"][0]["image"]


class _FakeProcessModule(WorkflowModule):
    """测试替身：未来处理模块（Face Repair 形状）——只需声明能力，无需修改 Validator。"""

    module_id = "face_repair"
    module_version = "v1"

    def capabilities(self) -> ModuleCapabilities:
        return ModuleCapabilities(
            module_id=self.module_id, module_version=self.module_version,
            title="面部修复（测试替身）",
            uses_seed=False, input_kind="image", input_required=True,
            output_kind="processed", parent_policy="input_image",
            allowed_job_kinds=("process",), can_start_from_image=True,
        )

    def validate_input(self, payload: WorkflowInput) -> WorkflowValidation:
        return WorkflowValidation(ok=True)

    async def execute(self, payload: WorkflowInput, engine: EngineAdapter,
                      *, binding: EngineBindingRef | None = None) -> WorkflowOutput:
        raise NotImplementedError


def _extended_registry() -> ModuleRegistry:
    return ModuleRegistry([
        BasicGenerateModule(), Img2ImgModule(), UpscaleModule(), _FakeProcessModule(),
    ])


# ===== Task2：process Job 校验能力驱动 =====

def test_process_validation_is_capability_driven_not_upscale_hardcode():
    validator = PipelineValidator(registry=_extended_registry())

    # 既有行为保持：upscale 处理型合法；basic/img2img 混入处理型仍被拒绝
    validator.validate([{"module_id": "upscale"}], job_kind="process", has_input_image=True)
    with pytest.raises(ValidationError) as error:
        validator.validate([{"module_id": "basic_generate"}, {"module_id": "upscale"}],
                           job_kind="process", has_input_image=True)
    assert error.value.code == "PIPELINE_INVALID"
    with pytest.raises(ValidationError) as error:
        validator.validate([{"module_id": "img2img"}], job_kind="process", has_input_image=True)
    assert error.value.code == "PIPELINE_INVALID"

    # 新处理模块（Face Repair 形状）声明能力后立即合法——Validator 未做任何修改：
    # 单个处理模块；以及 处理模块 → upscale 的链式处理 Pipeline
    validator.validate([{"module_id": "face_repair"}], job_kind="process", has_input_image=True)
    validator.validate(
        [{"module_id": "face_repair"}, {"module_id": "upscale"}],
        job_kind="process", has_input_image=True,
    )

    # 仅处理型模块不允许用于生成型 Job（allowed_job_kinds 能力驱动）
    with pytest.raises(ValidationError) as error:
        validator.validate([{"module_id": "face_repair"}], job_kind="generate", has_input_image=True)
    assert error.value.code == "PIPELINE_INVALID"


def test_module_capabilities_declare_job_kinds():
    """能力声明本身：basic/img2img 仅生成型；upscale 生成型+处理型；img2img 可以从图片起步。"""
    assert BasicGenerateModule().capabilities().allowed_job_kinds == ("generate",)
    assert Img2ImgModule().capabilities().allowed_job_kinds == ("generate",)
    assert Img2ImgModule().capabilities().can_start_from_image is True
    upscale = UpscaleModule().capabilities()
    assert upscale.allowed_job_kinds == ("generate", "process")
    assert upscale.can_start_from_image is True
    # Task8-②：生成语义声明（basic/img2img 是生成型；upscale 不是）
    assert BasicGenerateModule().capabilities().is_generative is True
    assert Img2ImgModule().capabilities().is_generative is True
    assert upscale.is_generative is False


# ===== Task7：幂等请求指纹 =====

def test_idempotent_same_key_same_payload_returns_original(mock_client):
    body = {"snapshot": make_snapshot(count=1), "client_request_id": "req-same"}
    first = mock_client.post("/api/v1/jobs", json=body).json()
    second = mock_client.post("/api/v1/jobs", json=body).json()
    assert second["id"] == first["id"]
    assert second["idempotent_replay"] is True


def test_idempotent_same_key_different_payload_conflicts(mock_client):
    first_body = {"snapshot": make_snapshot(count=1), "client_request_id": "req-conflict"}
    first = mock_client.post("/api/v1/jobs", json=first_body).json()

    # 数量变化 → 冲突
    changed_count = {"snapshot": make_snapshot(count=3), "client_request_id": "req-conflict"}
    response = mock_client.post("/api/v1/jobs", json=changed_count)
    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    # Prompt 变化 → 冲突
    changed_prompt = {
        "snapshot": make_snapshot(count=1, structured_prompt={"style": "photo", "scene": "beach"}),
        "client_request_id": "req-conflict",
    }
    response = mock_client.post("/api/v1/jobs", json=changed_prompt)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    # 原 Job 未受任何影响
    assert mock_client.get(f"/api/v1/jobs/{first['id']}").json()["structured_prompt"]["style"] == "anime"


def test_idempotent_queue_mode_change_is_not_a_conflict(mock_client):
    """queue_mode 只影响排队位置，不属于请求语义 → 不构成幂等冲突（返回原 Job）。"""
    first = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(count=1), "client_request_id": "req-queue",
    }).json()
    replay = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(count=1), "client_request_id": "req-queue", "queue_mode": "next",
    }).json()
    assert replay["id"] == first["id"] and replay["idempotent_replay"] is True


def test_idempotent_legacy_job_without_fingerprint_replays(mock_client, session):
    """Phase 7 之前创建的历史 Job（fingerprint 为 NULL）保持旧兼容行为（返回原 Job）。"""
    body = {"snapshot": make_snapshot(count=1), "client_request_id": "req-legacy"}
    first = mock_client.post("/api/v1/jobs", json=body).json()
    job = session.get(Job, first["id"])
    job.client_request_fingerprint = None  # 模拟历史 Job
    session.commit()

    replay = mock_client.post("/api/v1/jobs", json={
        "snapshot": make_snapshot(count=2), "client_request_id": "req-legacy",
    })
    assert replay.status_code == 201
    assert replay.json()["id"] == first["id"]


# ===== Task8-①：/modules capabilities 按实际选中的 module_version =====

def test_modules_api_capabilities_follow_selected_module_version(client, monkeypatch):
    from app.workflows.img2img import Img2ImgModule as _Img2Img

    class Img2ImgV2(_Img2Img):
        module_version = "v2"

        def capabilities(self) -> ModuleCapabilities:
            return dataclasses.replace(
                super().capabilities(), module_version="v2", title="图生图 V2（测试）",
            )

    registry = ModuleRegistry([
        BasicGenerateModule(), _Img2Img(), Img2ImgV2(), UpscaleModule(),
    ])
    # modules.py 顶层 import 与 factory 运行时 import 都要指向带 v2 的注册表
    monkeypatch.setattr("app.api.v1.modules.default_registry", lambda: registry)
    monkeypatch.setattr("app.workflows.registry.default_registry", lambda: registry)

    engine_cfg = client.app.state.settings.workflow.raw["engine"]
    engine_cfg.setdefault("modules", {}).setdefault("img2img", {})["module_version"] = "v2"
    try:
        modules = {item["module_id"]: item for item in client.get("/api/v1/modules").json()}
        img2img = modules["img2img"]
        # 配置选中 v2 → module_version 与 capabilities 都必须来自 v2，而不是注册表默认 v1
        assert img2img["module_version"] == "v2"
        assert img2img["title"] == "图生图 V2（测试）"
        # 其余模块不受影响
        assert modules["upscale"]["module_version"] == "v1"
    finally:
        engine_cfg["modules"].pop("img2img", None)


# ===== Task8-②：生成上下文按模块语义（不依赖 seed 数据） =====

def test_workbench_context_survives_missing_seed_on_generation_output(mock_client, session, png_bytes):
    """img2img 输出图 Seed 被清空（模拟未来引擎未记录 Seed）→ 仍必须恢复 Img2Img 上下文。"""
    source = import_one(mock_client, "p7_semantics_src.png", png_bytes)
    snapshot = make_snapshot(
        count=1,
        input_images=[{"role": "source", "image_id": source["id"]}],
        workflow_modules=[{"module_id": "img2img"}, {"module_id": "upscale"}],
    )
    job = mock_client.post("/api/v1/jobs", json={"snapshot": snapshot}).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")

    stage0_output_id = final["stages"][0]["items"][0]["output_image_id"]
    processed = session.get(Image, stage0_output_id)
    processed.seed = None  # 旧逻辑（seed != null）在这一刻就会失效
    session.commit()

    images = mock_client.get("/api/v1/images", params={"job_id": job["id"]}).json()["items"]
    upscaled = next(image for image in images if image["kind"] == "upscaled")

    # 从 upscaled 恢复 → 沿父链找到 img2img 输出（is_generative=true），而不是 404
    response = mock_client.get(f"/api/v1/images/{upscaled['id']}/workbench")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["snapshot"]["workflow_modules"][0]["module_id"] == "img2img"


def test_workbench_context_still_404_for_pure_import(mock_client, png_bytes):
    source = import_one(mock_client, "p7_pure_import.png", png_bytes)
    response = mock_client.get(f"/api/v1/images/{source['id']}/workbench")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "IMAGE_NO_GENERATION_CONTEXT"


# ===== Task8-③：非 comfyui/mock 引擎输出不得错标成 import =====

def test_non_comfyui_engine_output_source_is_engine_not_import(session, settings, png_bytes):
    from app.core.ids import JOB, JOB_ITEM, JOB_STAGE, JOB_STAGE_ITEM, new_id
    from app.services.image_service import import_adapter_outputs
    from app.storage.manager import StorageManager

    job_id, item_id = new_id(JOB), new_id(JOB_ITEM)
    stage_id, stage_item_id = new_id(JOB_STAGE), new_id(JOB_STAGE_ITEM)
    session.add(Job(
        id=job_id, source="web", status="RUNNING", job_kind="generate",
        prompt_mode="structured", positive_prompt_snapshot="p", negative_prompt_snapshot="",
        structured_prompt_snapshot="{}", workbench_snapshot_json="{}",
        generation_settings_json="{}", workflow_snapshot_json='{"modules":[]}',
        requested_count=1, module_id="basic_generate", module_version="v1",
        provider="future_engine",  # 未来引擎：绝不能被标成 import
    ))
    session.add(JobStage(
        id=stage_id, job_id=job_id, stage_index=0, module_id="basic_generate",
        module_version="v1", provider="future_engine", binding_version="v1",
        status="RUNNING", total_count=1, config_json="{}",
    ))
    session.add(JobItem(id=item_id, job_id=job_id, item_index=0, status="RUNNING"))
    session.add(JobStageItem(
        id=stage_item_id, job_stage_id=stage_id, job_item_id=item_id, item_index=0,
        status="RUNNING", seed=7,
    ))
    session.commit()

    stage_item = session.get(JobStageItem, stage_item_id)
    job = session.get(Job, job_id)
    storage = StorageManager(settings)
    image_ids = import_adapter_outputs(
        session, storage, job, stage_item,
        [EngineOutputFile(filename="future.png", data=png_bytes)],
    )
    image = session.get(Image, image_ids[0])
    assert image.source == "engine", "非 comfyui/mock 引擎输出不得被错标成 import"
    # provenance 仍保留真实 provider
    metadata = json.loads(image.metadata_json)
    assert metadata["actual_provider"] == "future_engine"