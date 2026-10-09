"""Phase 7 Task5：通用图片输入 Slot 契约（source / reference / face_reference，全离线）。

- 模块在 ModuleCapabilities.input_slots 声明所需 slot（角色 / 必填 / 最大数量）；
- Job 创建期按模块声明校验：未声明角色 → UNUSED_INPUT_IMAGE；必填缺失 → INPUT_IMAGE_REQUIRED；
  超出 max_count → INPUT_SLOT_LIMIT_EXCEEDED；
- 旧 Img2Img 继续兼容 source；新增 Reference 模块只需声明 slot，不需要改 Validator；
- Recipe 能保存并保留多角色 Slot（复用现有 Face Asset 参考图数据，不另造图库）。
"""
from __future__ import annotations

import dataclasses
import json
import time

import pytest

from app.core.config import Settings, WorkflowConfig
from app.core.errors import ValidationError
from app.engine.base import EngineAdapter, EngineBindingRef
from app.main import create_app
from app.services.pipeline_validator import PipelineValidator
from app.workflows.base import (
    InputSlotSpec,
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


class _FakeReferenceModule(WorkflowModule):
    """测试替身：未来 Reference 模块（face_reference 槽），只声明能力、不改 Validator。"""

    module_id = "face_reference_generate"
    module_version = "v1"

    def capabilities(self) -> ModuleCapabilities:
        return ModuleCapabilities(
            module_id=self.module_id, module_version=self.module_version,
            title="人脸参考生成（测试替身）",
            uses_seed=True, input_kind="image", input_required=True,
            output_kind="original", parent_policy="input_image",
            input_slots=(
                InputSlotSpec("face_reference", required=True, max_count=1,
                              description="人脸/人物参考图"),
            ),
            # 声明两份参考也允许（用于验证 max_count 语义）
        )

    def validate_input(self, payload: WorkflowInput) -> WorkflowValidation:
        return WorkflowValidation(ok=True)

    async def execute(self, payload: WorkflowInput, engine: EngineAdapter,
                      *, binding: EngineBindingRef | None = None) -> WorkflowOutput:
        raise NotImplementedError


def _registry() -> ModuleRegistry:
    return ModuleRegistry([
        BasicGenerateModule(), Img2ImgModule(), UpscaleModule(), _FakeReferenceModule(),
    ])


# ===== 能力声明本身 =====

def test_module_input_slot_declarations():
    img2img_slots = Img2ImgModule().capabilities().input_slots
    assert [(slot.role, slot.required, slot.max_count) for slot in img2img_slots] == [
        ("source", True, 1),
    ]
    upscale_slots = UpscaleModule().capabilities().input_slots
    assert [(slot.role, slot.required, slot.max_count) for slot in upscale_slots] == [
        ("source", True, 1),
    ]
    assert BasicGenerateModule().capabilities().input_slots == ()


# ===== Validator：Slot 驱动（含未来 Reference 模块形状） =====

def test_validator_slot_role_required_and_limit():
    validator = PipelineValidator(registry=_registry())

    # 未来 Reference 模块：face_reference 槽必填
    validator.validate([{"module_id": "face_reference_generate"}],
                       job_kind="generate", has_input_image=True,
                       input_roles={"face_reference": 1})
    with pytest.raises(ValidationError) as error:
        validator.validate([{"module_id": "face_reference_generate"}],
                           job_kind="generate", has_input_image=False, input_roles={})
    assert error.value.code == "INPUT_IMAGE_REQUIRED"

    # 给了 source（模块未声明）→ 输入图未被消费
    with pytest.raises(ValidationError) as error:
        validator.validate([{"module_id": "face_reference_generate"}],
                           job_kind="generate", has_input_image=True, input_roles={"source": 1})
    assert error.value.code == "UNUSED_INPUT_IMAGE"

    # img2img：只声明 source → face_reference 被拒绝
    with pytest.raises(ValidationError) as error:
        validator.validate([{"module_id": "img2img"}],
                           job_kind="generate", has_input_image=True,
                           input_roles={"face_reference": 1})
    assert error.value.code == "UNUSED_INPUT_IMAGE"

    # max_count：声明 max_count=1 的模块收到 2 张 → 超量
    with pytest.raises(ValidationError) as error:
        validator.validate([{"module_id": "img2img"}],
                           job_kind="generate", has_input_image=True,
                           input_roles={"source": 2})
    assert error.value.code == "INPUT_SLOT_LIMIT_EXCEEDED"

    # 可选项不强制（构造 max_count=2 的临时模块语义由能力声明决定，此处验证 max_count=2 允许 2 张）
    class _TwoRefModule(_FakeReferenceModule):
        module_id = "two_ref"
        module_version = "v1"

        def capabilities(self) -> ModuleCapabilities:
            return dataclasses.replace(
                super().capabilities(), module_id="two_ref",
                input_slots=(InputSlotSpec("reference", required=False, max_count=2),),
            )

    registry = ModuleRegistry([BasicGenerateModule(), Img2ImgModule(), UpscaleModule(), _TwoRefModule()])
    PipelineValidator(registry=registry).validate(
        [{"module_id": "two_ref"}], job_kind="generate", has_input_image=True,
        input_roles={"reference": 2},
    )


# ===== API：旧 Img2Img 兼容 + 角色错误明确拒绝 =====

def test_img2img_source_slot_still_works_end_to_end(mock_client, png_bytes):
    source = import_one(mock_client, "slot_src.png", png_bytes)
    snapshot = make_snapshot(
        count=1,
        input_images=[{"role": "source", "image_id": source["id"]}],
        workflow_modules=[{"module_id": "img2img"}],
    )
    job = mock_client.post("/api/v1/jobs", json={"snapshot": snapshot}).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")
    stage_item = final["stages"][0]["items"][0]
    assert stage_item["input_image_id"] == source["id"]


def test_img2img_rejects_undeclared_reference_role(mock_client, png_bytes):
    source = import_one(mock_client, "slot_badrole.png", png_bytes)
    snapshot = make_snapshot(
        input_images=[{"role": "reference", "image_id": source["id"]}],
        workflow_modules=[{"module_id": "img2img"}],
    )
    response = mock_client.post("/api/v1/jobs", json={"snapshot": snapshot})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "UNUSED_INPUT_IMAGE"


def test_basic_generate_rejects_reference_role(mock_client, png_bytes):
    source = import_one(mock_client, "slot_basic.png", png_bytes)
    snapshot = make_snapshot(input_images=[{"role": "face_reference", "image_id": source["id"]}])
    response = mock_client.post("/api/v1/jobs", json={"snapshot": snapshot})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "UNUSED_INPUT_IMAGE"


# ===== Recipe：多角色 Slot 保存与往返 =====

def test_recipe_preserves_multiple_slot_roles(mock_client, png_bytes):
    source = import_one(mock_client, "slot_recipe_src.png", png_bytes)
    face = import_one(mock_client, "slot_recipe_face.png", png_bytes + b"\x03")
    snapshot = make_snapshot(
        input_images=[
            {"role": "source", "image_id": source["id"]},
            {"role": "face_reference", "image_id": face["id"]},
        ],
    )
    response = mock_client.post("/api/v1/recipes", json={"name": "双槽配方", "snapshot": snapshot})
    assert response.status_code == 201, response.text
    recipe = response.json()
    roles = {ref["role"]: ref["image_id"] for ref in recipe["current_version"]["input_images"]}
    assert roles == {"source": source["id"], "face_reference": face["id"]}

    reopened = mock_client.get(f"/api/v1/recipes/{recipe['id']}").json()
    roles_again = {ref["role"]: ref["image_id"] for ref in reopened["current_version"]["input_images"]}
    assert roles_again == roles, "配方往返必须保留 Slot 角色与图片"


# ===== /modules 暴露 input_slots =====

def test_modules_api_exposes_input_slots(client):
    modules = {item["module_id"]: item for item in client.get("/api/v1/modules").json()}
    img2img_slots = modules["img2img"]["input_slots"]
    assert img2img_slots == [{
        "role": "source", "required": True, "max_count": 1,
        "description": "图生图输入（来源图片，来自 Studio 图库）",
    }]
    assert modules["upscale"]["input_slots"][0]["role"] == "source"
    assert modules["basic_generate"]["input_slots"] == []