"""Phase 6：Pipeline 可靠性收口回归（全部离线 Mock）。

锁定用户审查发现的真实缺口：
- Task1 Image → Workbench 选择"最近的生成上下文"（不再永远取树根）；
- Task2 前端身份保留（前端侧，见 frontend 测试/人工验收）；
- Task3 Recipe 固定 Seed 归一化；
- Task4 Pipeline 顺序保持 + 重复模块拒绝；
- Task5 Module Availability 收紧；
- Task6 Img2ImgModule.execute Prompt 契约；
- Task7 generation_mode 往返；
- Task8 Module 参数元数据驱动；
- Task9 size_mode / 有效尺寸语义。
"""
from __future__ import annotations

import dataclasses
import json
import time

import pytest

from app.core.config import Settings, WorkflowConfig
from app.main import create_app
from app.models import Image


# ===== 工具（与 test_phase51_img2img 同构） =====

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


def import_one(client, name: str, data: bytes) -> dict:
    response = client.post("/api/v1/images/import", files=[("files", (name, data, "image/png"))])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["imported_count"] == 1, body
    return body["imported"][0]["image"]


def gallery(client, job_id: str) -> list[dict]:
    return client.get("/api/v1/images", params={"job_id": job_id, "limit": 200}).json()["items"]


def run_generate(client, snapshot: dict) -> dict:
    response = client.post("/api/v1/jobs", json={"snapshot": snapshot})
    assert response.status_code == 201, response.text
    job = response.json()
    return wait_for(client, job["id"], lambda j: j["status"] == "COMPLETED")


def workbench_of(client, image_id: str) -> dict:
    response = client.get(f"/api/v1/images/{image_id}/workbench")
    assert response.status_code == 200, response.text
    return response.json()


# ===== Task1：Image → Workbench 最近的生成上下文 =====

def test_workbench_import_then_img2img_restores_img2img(mock_client, session, png_bytes):
    """import → img2img：旧逻辑取树根（导入图无 Job）会 404；新逻辑恢复 Img2Img Job。"""
    source = import_one(mock_client, "p6_img2img_src.png", png_bytes)
    final = run_generate(mock_client, make_snapshot(
        input_images=[{"role": "source", "image_id": source["id"]}],
        workflow_modules=[{"module_id": "img2img", "config": {"denoise": 0.55}}],
    ))
    processed_id = final["stages"][0]["items"][0]["output_image_id"]
    processed = session.get(Image, processed_id)
    assert processed.kind == "processed" and processed.parent_image_id == source["id"]

    body = workbench_of(mock_client, processed_id)
    modules = body["snapshot"]["workflow_modules"]
    assert [module["module_id"] for module in modules] == ["img2img"]
    assert modules[0]["config"] == {"denoise": 0.55}
    assert body["snapshot"]["input_images"][0]["image_id"] == source["id"], \
        "恢复的工作台必须携带原输入图（否则 Img2Img 无法重现）"
    # Seed = 生成上下文图片（img2img 输出）的真实 Seed
    assert body["seed"] == processed.seed and body["seed"] is not None
    assert body["snapshot"]["seed_mode"] == "random"


def test_workbench_img2img_then_upscale_still_restores_img2img(mock_client, session, png_bytes):
    """import → img2img → upscale（同一 generate Job 内嵌后处理）：仍恢复 Img2Img，
    Seed 取 img2img Stage 的真实 Seed（upscale 输出 Seed 为 NULL，不能拿它当上下文）。"""
    source = import_one(mock_client, "p6_chain_src.png", png_bytes)
    final = run_generate(mock_client, make_snapshot(
        input_images=[{"role": "source", "image_id": source["id"]}],
        workflow_modules=[{"module_id": "img2img", "config": {"denoise": 0.55}},
                          {"module_id": "upscale"}],
    ))
    assert [stage["module_id"] for stage in final["stages"]] == ["img2img", "upscale"]
    img2img_out_id = final["stages"][0]["items"][0]["output_image_id"]
    upscaled_id = final["stages"][1]["items"][0]["output_image_id"]
    img2img_out = session.get(Image, img2img_out_id)
    upscaled = session.get(Image, upscaled_id)
    assert upscaled.seed is None, "前置条件：upscale 输出无 Seed"

    body = workbench_of(mock_client, upscaled_id)
    modules = body["snapshot"]["workflow_modules"]
    assert [module["module_id"] for module in modules] == ["img2img", "upscale"]
    assert modules[0]["module_id"] == "img2img", "Primary 必须是 Img2Img（不是导入图 / basic）"
    assert body["seed"] == img2img_out.seed and body["seed"] is not None, \
        "Seed 必须取 img2img 的真实 Seed，而不是 upscale 的 NULL"


def test_workbench_basic_then_upscale_restores_basic(mock_client, session, png_bytes):
    """basic → upscale（同一 generate Job）：恢复 basic，Seed = 原图真实 Seed。"""
    final = run_generate(mock_client, make_snapshot(
        workflow_modules=[{"module_id": "basic_generate"}, {"module_id": "upscale"}],
    ))
    images = gallery(mock_client, final["id"])
    original = next(image for image in images if image["kind"] == "original")
    upscaled = next(image for image in images if image["kind"] == "upscaled")

    body = workbench_of(mock_client, upscaled["id"])
    modules = body["snapshot"]["workflow_modules"]
    assert [module["module_id"] for module in modules] == ["basic_generate", "upscale"]
    assert body["snapshot"]["structured_prompt"]["style"] == "anime"
    assert body["seed"] == original["seed"] and body["seed"] is not None


def test_workbench_basic_then_img2img_then_upscale_restores_img2img(mock_client, session, png_bytes):
    """basic → img2img → upscale：恢复 Img2Img（不是 basic，也不是树根），
    Seed 取 img2img 的真实 Seed（不是 basic 原图 Seed）。"""
    basic_final = run_generate(mock_client, make_snapshot(count=1))
    original = gallery(mock_client, basic_final["id"])[0]

    final = run_generate(mock_client, make_snapshot(
        input_images=[{"role": "source", "image_id": original["id"]}],
        workflow_modules=[{"module_id": "img2img", "config": {"denoise": 0.55}},
                          {"module_id": "upscale"}],
    ))
    img2img_out_id = final["stages"][0]["items"][0]["output_image_id"]
    upscaled_id = final["stages"][1]["items"][0]["output_image_id"]
    img2img_out = session.get(Image, img2img_out_id)

    body = workbench_of(mock_client, upscaled_id)
    modules = body["snapshot"]["workflow_modules"]
    assert modules[0]["module_id"] == "img2img", "距离最近的生成上下文是 img2img 输出"
    assert body["seed"] == img2img_out.seed, "不是树根（basic 原图）Seed"
    assert body["snapshot"]["input_images"][0]["image_id"] == original["id"]


def test_workbench_pure_import_still_has_no_context(mock_client, png_bytes):
    """纯外部导入图：全链无真实生成图 → 404 IMAGE_NO_GENERATION_CONTEXT。"""
    imported = import_one(mock_client, "p6_pure_import.png", png_bytes)
    response = mock_client.get(f"/api/v1/images/{imported['id']}/workbench")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "IMAGE_NO_GENERATION_CONTEXT"


# ===== Task7：generation_mode 显式往返（Job / History / Image / Recipe） =====

def test_generation_mode_roundtrip_job_history_image(mock_client, png_bytes):
    """image 模式（img2img）Job：Job 快照 / History / Image restore 都恢复 generation_mode=image。"""
    source = import_one(mock_client, "p6_mode_src.png", png_bytes)
    final = run_generate(mock_client, make_snapshot(
        generation_mode="image",
        input_images=[{"role": "source", "image_id": source["id"]}],
        workflow_modules=[{"module_id": "img2img", "config": {"denoise": 0.55}}],
    ))
    assert final["workbench_snapshot"]["generation_mode"] == "image"
    assert final["generation_settings"]["generation_mode"] == "image"

    processed_id = final["stages"][0]["items"][0]["output_image_id"]
    body = workbench_of(mock_client, processed_id)
    assert body["snapshot"]["generation_mode"] == "image", "Image → 工作台必须显式恢复模式"

    history = mock_client.get("/api/v1/history", params={"bucket": "completed"}).json()
    entry = next(item for item in history["items"] if item["root_job_id"] == final["id"])
    assert entry["root"]["workbench_snapshot"]["generation_mode"] == "image"


def test_generation_mode_recipe_roundtrip_without_image(mock_client):
    """image 模式就算暂时没有选择图片，也要随 Recipe 保留（未来 Reference 不会退回文生图）。"""
    response = mock_client.post("/api/v1/recipes", json={
        "name": "P6 图片模式",
        "snapshot": make_snapshot(generation_mode="image"),
    })
    assert response.status_code == 201, response.text
    recipe_id = response.json()["id"]
    version = mock_client.get(f"/api/v1/recipes/{recipe_id}").json()["current_version"]
    assert version["generation_settings"]["generation_mode"] == "image"

    # 旧契约（无 generation_mode 的配方）→ 返回 null（前端按输入图推断，向后兼容）
    legacy = mock_client.post("/api/v1/recipes", json={
        "name": "P6 旧快照",
        "snapshot": make_snapshot(),
    }).json()
    legacy_version = mock_client.get(f"/api/v1/recipes/{legacy['id']}").json()["current_version"]
    assert legacy_version["generation_settings"]["generation_mode"] is None


def test_generation_mode_null_for_text_job(mock_client):
    """旧调用方（无 generation_mode）提交 → 保存 null，绝不伪造模式。"""
    final = run_generate(mock_client, make_snapshot(count=1))
    assert final["workbench_snapshot"].get("generation_mode") is None
    assert final["generation_settings"]["generation_mode"] is None


# ===== Task3：Recipe 不保存固定 Seed（fixed → random 归一化，不报错） =====

def test_recipe_save_normalizes_fixed_seed_to_random(mock_client):
    """fixed Seed 工作台 → 保存 Recipe 201（不再 400）→ reopen 为 random。"""
    response = mock_client.post("/api/v1/recipes", json={
        "name": "P6 固定 Seed",
        "snapshot": make_snapshot(seed_mode="fixed", seed=12345),
    })
    assert response.status_code == 201, response.text
    recipe = response.json()
    assert recipe["current_version"]["generation_settings"]["seed_mode"] == "random"
    reopened = mock_client.get(f"/api/v1/recipes/{recipe['id']}").json()
    assert reopened["current_version"]["generation_settings"]["seed_mode"] == "random"


# ===== Task4：Pipeline 顺序保持 + 重复模块拒绝 =====

def test_resolve_workflow_modules_preserves_request_order(settings):
    """不再按硬编码 MODULE_ORDER 重排（否则未来 reference_generate→upscale 会被错误重排）。"""
    from app.engine.factory import resolve_workflow_modules

    identities = resolve_workflow_modules(
        mock_settings(settings), [{"module_id": "upscale"}, {"module_id": "basic_generate"}],
    )
    assert [item["module_id"] for item in identities] == ["upscale", "basic_generate"], \
        "Pipeline 顺序必须严格等于请求顺序"


def test_job_creation_rejects_duplicate_module(mock_client, png_bytes):
    """同一 module_id 在一个 Pipeline 中重复出现 → 400 PIPELINE_DUPLICATE_MODULE。"""
    source = import_one(mock_client, "p6_dup.png", png_bytes)
    response = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(
        input_images=[{"role": "source", "image_id": source["id"]}],
        workflow_modules=[{"module_id": "img2img"}, {"module_id": "img2img"}],
    )})
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "PIPELINE_DUPLICATE_MODULE"


def test_recipe_rejects_duplicate_module(mock_client):
    response = mock_client.post("/api/v1/recipes", json={
        "name": "P6 重复模块",
        "snapshot": make_snapshot(workflow_modules=[
            {"module_id": "upscale"}, {"module_id": "upscale"},
        ]),
    })
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "PIPELINE_DUPLICATE_MODULE"


def test_pipeline_validator_rejects_duplicate_directly():
    """Validator 是唯一合法性入口（不依赖工厂去重），内部直调路径同样拒绝。"""
    from app.core.errors import ValidationError
    from app.services.pipeline_validator import PipelineValidator

    with pytest.raises(ValidationError) as exc:
        PipelineValidator().validate(
            [{"module_id": "basic_generate", "module_version": "v1"},
             {"module_id": "basic_generate", "module_version": "v1"}],
            job_kind="generate", has_input_image=False,
        )
    assert exc.value.code == "PIPELINE_DUPLICATE_MODULE"


# ===== Task5：Module Availability 收紧 + 未注册版本创建期拒绝 =====

def test_unregistered_module_version_rejected_at_creation(mock_client):
    """未注册 module_version（完整固化身份）→ Job 创建期 400，绝不先创建再执行期炸。"""
    response = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot(
        workflow_modules=[{
            "module_id": "basic_generate", "module_version": "v99",
            "provider": "mock", "binding_version": "v1",
        }],
    )})
    assert response.status_code == 400, response.text
    assert "版本不存在" in response.json()["error"]["message"]


def test_module_availability_keeps_version_domains_separate(settings):
    """binding_version 不得用 module_version 兜底；配置了未注册版本 → available=false。"""
    from app.engine.factory import module_availability

    merged = dataclasses.replace(settings, workflow=WorkflowConfig(raw={"engine": {
        "provider": "mock", "module_id": "basic_generate",
        "module_version": "v2", "binding_version": "v1",
    }}))
    entries = {item["module_id"]: item for item in module_availability(merged)}
    basic = entries["basic_generate"]
    assert basic["module_version"] == "v2"
    assert basic["binding_version"] == "v1", "不得把 module_version 当 binding_version fallback"
    assert basic["registered"] is True
    assert basic["available"] is False
    assert basic["unavailable_reason"] == "module_version_not_registered"
    # 其余模块不受默认模块 engine 级配置影响（各自 v1）
    img2img = entries["img2img"]
    assert img2img["module_version"] == "v1" and img2img["binding_version"] == "v1"
    assert img2img["available"] is True


def test_modules_api_reports_registered_and_reason(mock_client):
    modules = {item["module_id"]: item for item in mock_client.get("/api/v1/modules").json()}
    for module_id in ("basic_generate", "img2img", "upscale"):
        module = modules[module_id]
        assert module["registered"] is True
        assert module["module_version"] == "v1"
        assert module["available"] is True  # mock：测试引擎可执行全部已注册模块
        assert module["unavailable_reason"] is None