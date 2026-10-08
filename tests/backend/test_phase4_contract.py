"""Phase 4 契约测试：Module I/O 能力（Task2）、StageItem Seed（Task3）、
EngineAdapter 输入图片契约（Task4）、binding_hash 执行指纹（Task1）、
Studio Input Registry TTL 清理（Task11）。全部离线可跑（Mock 引擎）。
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text

from app.core.config import Settings, WorkflowConfig
from app.engine.base import EngineError, EngineOutputFile
from app.engine.errors import is_systemic
from app.engine.factory import make_input_registry, resolve_workflow_modules
from app.engine.input_registry import EngineInputRegistry
from app.engine.mock import MockEngineAdapter
from app.engine.unbound import UnboundEngineAdapter
from app.main import create_app
from app.workflows.base import InputImageRef, JobRequestContext
from app.workflows.basic_generate import BasicGenerateModule
from app.workflows.registry import default_registry
from app.workflows.upscale import UpscaleModule


def mock_settings(settings: Settings, **options) -> Settings:
    merged = {"worker_poll_interval_ms": 20, "engine_poll_ms": 20}
    merged.update(options)
    return dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={"engine": {"provider": "mock", "options": merged}}),
    )


def wait_for(client, job_id, predicate, timeout=30.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/api/v1/jobs/{job_id}").json()
        if predicate(last):
            return last
        time.sleep(0.05)
    raise AssertionError(f"等待任务状态超时: {json.dumps(last, ensure_ascii=False)[:500]}")


def make_snapshot(count=1, **overrides):
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


def pipeline_snapshot(count=1):
    snapshot = make_snapshot(count=count)
    snapshot["workflow_modules"] = [{"module_id": "basic_generate"}, {"module_id": "upscale"}]
    return snapshot


@pytest.fixture()
def mock_client(settings):
    from fastapi.testclient import TestClient

    app = create_app(mock_settings(settings))
    with TestClient(app) as test_client:
        yield test_client


def gallery(client, job_id: str) -> list[dict]:
    return client.get("/api/v1/images", params={"job_id": job_id, "limit": 200}).json()["items"]


# ===== Task2：ModuleCapabilities 输入/输出语义 =====

def test_module_capabilities_declare_io_semantics():
    basic = BasicGenerateModule().capabilities()
    assert (basic.uses_seed, basic.input_kind, basic.output_kind) == (True, "none", "original")
    assert (basic.parent_policy, basic.output_cardinality) == ("none", 1)
    upscale = UpscaleModule().capabilities()
    assert (upscale.uses_seed, upscale.input_kind, upscale.output_kind) == (False, "image", "upscaled")
    assert (upscale.parent_policy, upscale.output_cardinality) == ("input_image", 1)


def test_output_kind_comes_from_capabilities_not_input_image_id(mock_client, png_bytes):
    """Task2 回归：StageItem 上有 input_image_id 也不得推断为 upscaled（按能力判定）。"""
    from app.engine.base import EngineOutputFile as _Out
    from app.models import Image, Job, JobStageItem
    from app.services import image_service
    from app.storage.manager import StorageManager

    job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot()}).json()
    wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED")

    with mock_client.app.state.session_factory() as session:
        storage = StorageManager(mock_client.app.state.settings)
        job_ref = session.get(Job, job["id"])
        stage_item = session.execute(
            select(JobStageItem).where(JobStageItem.job_item_id == job["items"][0]["id"])
        ).scalars().first()
        # 人为注入 input_image_id：basic_generate 的能力声明 output_kind=original / parent_policy=none，
        # 所以结果仍然必须是 original 且无 parent（旧实现会错误推断为 upscaled + parent）
        stage_item.input_image_id = "img_fake_parent"
        session.commit()
        ids = image_service.import_adapter_outputs(
            session, storage, job_ref, stage_item,
            [_Out(filename="injected.png", data=png_bytes)],
        )
        image = session.get(Image, ids[0])
        assert image.kind == "original"
        assert image.parent_image_id is None


# ===== Task3：StageItem Seed 正式化 =====

def test_stage_item_seed_real_for_basic_null_for_upscale(mock_client):
    job = mock_client.post("/api/v1/jobs", json={"snapshot": pipeline_snapshot(count=2)}).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED", timeout=60)

    stage0_items = final["stages"][0]["items"]
    stage1_items = final["stages"][1]["items"]
    assert all(item["seed"] is not None for item in stage0_items), "basic StageItem 必须有真实 Seed"
    assert all(item["seed"] is None for item in stage1_items), "upscale StageItem.seed 必须为 NULL"
    # JobItem.seed 保留为快捷字段（仅第一个 Stage / 使用随机性时写入）
    assert all(item["seed"] is not None for item in final["items"])

    images = gallery(mock_client, job["id"])
    originals = {image["id"]: image for image in images if image["kind"] == "original"}
    upscaled = [image for image in images if image["kind"] == "upscaled"]
    for item in stage0_items:
        assert originals[item["output_image_id"]]["seed"] == item["seed"], \
            "原图 Image.seed 必须来自对应 StageItem.seed"
    assert all(image["seed"] is None for image in upscaled), "高清图绝不携带假 Seed"


def test_manual_upscale_image_seed_null(mock_client, png_bytes):
    from app.services import image_service
    from app.storage.manager import StorageManager

    with mock_client.app.state.session_factory() as session:
        storage = StorageManager(mock_client.app.state.settings)
        source = image_service.import_engine_output(
            session, storage, data=png_bytes, original_filename="seed.png", source="import",
        )
        source_id = source.id

    job = mock_client.post("/api/v1/images/upscale", json={"image_ids": [source_id]}).json()
    final = wait_for(mock_client, job["id"], lambda j: j["status"] == "COMPLETED", timeout=60)
    assert final["stages"][0]["items"][0]["seed"] is None
    assert all(item["seed"] is None for item in final["items"]), "process Job 的 JobItem.seed 必须为 NULL"
    images = gallery(mock_client, job["id"])
    assert len(images) == 1
    assert images[0]["kind"] == "upscaled" and images[0]["seed"] is None


# ===== Task4：EngineAdapter 输入图片正式契约 =====

def test_upscale_prepare_inputs_uses_formal_contract():
    module = UpscaleModule()
    image = InputImageRef(image_id="img_x", file_name="a.png", data=b"data", width=8, height=8)
    context = JobRequestContext(input_image=image)

    adapter = MockEngineAdapter({})
    prepared = asyncio.run(module.prepare_inputs(context, adapter))
    assert prepared["input_image_name"] == "mock_inputs/img_x.png"
    assert adapter.uploaded_inputs == [("a.png", "img_x")]


def test_engine_input_unsupported_is_explicit_and_systemic():
    module = UpscaleModule()
    image = InputImageRef(image_id="img_x", file_name="a.png", data=b"data")
    context = JobRequestContext(input_image=image)
    with pytest.raises(EngineError) as excinfo:
        asyncio.run(module.prepare_inputs(context, UnboundEngineAdapter()))
    assert excinfo.value.error_type == "ENGINE_INPUT_UNSUPPORTED"
    assert is_systemic("ENGINE_INPUT_UNSUPPORTED")


def test_engine_input_unsupported_fails_job_and_pauses_queue(mock_client, png_bytes):
    from app.services import image_service
    from app.storage.manager import StorageManager

    with mock_client.app.state.session_factory() as session:
        storage = StorageManager(mock_client.app.state.settings)
        source = image_service.import_engine_output(
            session, storage, data=png_bytes, original_filename="u.png", source="import",
        )
        source_id = source.id

    adapter = mock_client.app.state.adapter
    original_upload = adapter.upload_input_image

    async def unsupported(**_kwargs):
        raise EngineError("ENGINE_INPUT_UNSUPPORTED", "mock: 引擎不支持输入图片")

    adapter.upload_input_image = unsupported
    try:
        job = mock_client.post("/api/v1/images/upscale", json={"image_ids": [source_id]}).json()
        final = wait_for(mock_client, job["id"], lambda j: j["status"] == "FAILED", timeout=30)
        assert final["error_type"] == "ENGINE_INPUT_UNSUPPORTED"
        assert mock_client.get("/api/v1/queue").json()["worker"]["queue_paused"] is True
    finally:
        adapter.upload_input_image = original_upload
        mock_client.post("/api/v1/queue/resume")


# ===== Task1：binding_hash 全链路 =====

def _comfyui_settings(settings: Settings) -> Settings:
    return dataclasses.replace(
        settings, workflow=WorkflowConfig(raw={"engine": {"provider": "comfyui", "options": {}}}),
    )


def test_binding_hash_recorded_in_job_stage_snapshot_and_api(mock_client):
    from app.services import job_service

    modules = [
        {"module_id": "basic_generate", "module_version": "v1", "provider": "mock",
         "binding_version": "v1", "workflow_hash": "wf_hash_11111111", "binding_hash": "bd_hash_11111111"},
        {"module_id": "upscale", "module_version": "v1", "provider": "mock",
         "binding_version": "v1", "workflow_hash": "wf_hash_22222222", "binding_hash": "bd_hash_22222222"},
    ]
    with mock_client.app.state.session_factory() as session:
        job, _ = job_service.create_job(
            session, source="web", snapshot=pipeline_snapshot(count=1), workflow_modules=modules,
        )
        job_id = job.id
        assert job.binding_hash == "bd_hash_11111111"
        snapshot_modules = json.loads(job.workflow_snapshot_json)["modules"]
        assert snapshot_modules[0]["binding_hash"] == "bd_hash_11111111"
        assert snapshot_modules[1]["binding_hash"] == "bd_hash_22222222"

    final = wait_for(mock_client, job_id, lambda j: j["status"] == "COMPLETED", timeout=60)
    assert final["binding_hash"] == "bd_hash_11111111"
    assert final["stages"][0]["binding_hash"] == "bd_hash_11111111"
    assert final["stages"][1]["binding_hash"] == "bd_hash_22222222"


def test_binding_hash_mismatch_is_systemic_at_execution(mock_client):
    adapter = mock_client.app.state.adapter
    original_submit = adapter.submit_job

    async def tampered_submit(request):
        raise EngineError("BINDING_HASH_MISMATCH", "binding.yaml 已被改动（immutable 违约）")

    adapter.submit_job = tampered_submit
    try:
        job = mock_client.post("/api/v1/jobs", json={"snapshot": make_snapshot()}).json()
        final = wait_for(mock_client, job["id"], lambda j: j["status"] == "FAILED", timeout=30)
        assert final["error_type"] == "BINDING_HASH_MISMATCH"
        assert mock_client.get("/api/v1/queue").json()["worker"]["queue_paused"] is True
    finally:
        adapter.submit_job = original_submit
        mock_client.post("/api/v1/queue/resume")


def test_resolve_workflow_modules_pins_restored_identity(settings):
    """Task9：历史恢复携带完整身份 → 固定原版本，不静默升级（comfyui 下校验双指纹）。"""
    comfy = _comfyui_settings(settings)

    # 普通新建（只有 module_id）→ 解析当前默认身份（含真实双指纹）
    resolved = resolve_workflow_modules(comfy, [{"module_id": "basic_generate"}, {"module_id": "upscale"}])
    assert [item["module_id"] for item in resolved] == ["basic_generate", "upscale"]
    basic = resolved[0]
    assert basic["provider"] == "comfyui"
    assert basic["workflow_hash"] and basic["binding_hash"], "comfyui 必须记录双指纹"

    # 从历史恢复：携带完整身份 → 原样固定（磁盘校验通过）
    pinned_input = [{
        "module_id": "basic_generate", "module_version": basic["module_version"],
        "provider": "comfyui", "binding_version": basic["binding_version"],
        "workflow_hash": basic["workflow_hash"], "binding_hash": basic["binding_hash"],
    }]
    pinned = resolve_workflow_modules(comfy, pinned_input)
    assert pinned[0]["workflow_hash"] == basic["workflow_hash"]
    assert pinned[0]["binding_hash"] == basic["binding_hash"]

    # 指纹被改动（binding.yaml 级）→ 创建期直接拒绝
    tampered = dict(pinned_input[0], binding_hash="0" * 16)
    with pytest.raises(EngineError) as excinfo:
        resolve_workflow_modules(comfy, [tampered])
    assert excinfo.value.error_type == "BINDING_HASH_MISMATCH"

    # 老 Job（binding_hash = null）允许兼容；采纳磁盘当前指纹
    legacy = dict(pinned_input[0], binding_hash=None)
    resolved_legacy = resolve_workflow_modules(comfy, [legacy])
    assert resolved_legacy[0]["binding_hash"] == basic["binding_hash"]

    # provider 与当前引擎不一致 → 拒绝（不静默换引擎）
    wrong_provider = dict(pinned_input[0], provider="mock")
    with pytest.raises(EngineError) as excinfo:
        resolve_workflow_modules(comfy, [wrong_provider])
    assert excinfo.value.error_type == "BINDING_IDENTITY_MISMATCH"


def test_mock_pinned_identity_passes_through(mock_client):
    """mock 引擎无磁盘 binding：携带完整身份的恢复请求原样固定（workflow_hash 可为 None）。"""
    incoming = [{
        "module_id": "basic_generate", "module_version": "v1", "provider": "mock",
        "binding_version": "v1", "workflow_hash": None, "binding_hash": None,
    }]
    resolved = resolve_workflow_modules(mock_client.app.state.settings, incoming)
    assert resolved[0]["provider"] == "mock"
    assert resolved[0]["workflow_hash"] is None and resolved[0]["binding_hash"] is None


# ===== Task11：Studio Input Registry + TTL 清理 =====

def _registry_entry(file: str, image_id: str, *, age_hours: float) -> dict:
    uploaded = datetime.now(timezone.utc) - timedelta(hours=age_hours)
    return {"file": file, "image_id": image_id,
            "uploaded_at": uploaded.isoformat(timespec="milliseconds").replace("+00:00", "Z")}


def _insert_running_stage_item(session, image_id: str) -> None:
    session.execute(text(
        "INSERT INTO jobs (id, source, status, prompt_mode, workbench_snapshot_json, "
        "generation_settings_json, requested_count, created_at, updated_at) "
        "VALUES ('job_reg', 'web', 'RUNNING', 'structured', '{}', '{}', 1, 't', 't')"
    ))
    session.execute(text(
        "INSERT INTO job_items (id, job_id, item_index, status, created_at, updated_at) "
        "VALUES ('item_reg', 'job_reg', 0, 'RUNNING', 't', 't')"
    ))
    session.execute(text(
        "INSERT INTO job_stages (id, job_id, stage_index, module_id, module_version, status, "
        "created_at, updated_at) VALUES ('stg_reg', 'job_reg', 0, 'upscale', 'v1', 'RUNNING', 't', 't')"
    ))
    session.execute(text(
        "INSERT INTO job_stage_items (id, job_stage_id, job_item_id, item_index, input_image_id, "
        "status, created_at, updated_at) VALUES ('sti_reg', 'stg_reg', 'item_reg', 0, :image_id, "
        "'RUNNING', 't', 't')"
    ), {"image_id": image_id})
    session.commit()


def test_engine_input_ttl_cleanup_only_touches_registered_studio_files(tmp_path, settings, session_factory):
    from app.services.engine_input_service import cleanup_engine_inputs

    input_dir = tmp_path / "comfy_input"
    studio_dir = input_dir / "NSFWStudio_inputs"
    other_dir = input_dir / "user_files"
    studio_dir.mkdir(parents=True)
    other_dir.mkdir(parents=True)

    old_file = studio_dir / "img_old.png"
    active_file = studio_dir / "img_active.png"
    fresh_file = studio_dir / "img_fresh.png"
    user_file = other_dir / "user_keep.png"
    for path in (old_file, active_file, fresh_file, user_file):
        path.write_bytes(b"x")

    data_root = tmp_path / "data_root"
    data_root.mkdir()
    registry = EngineInputRegistry(data_root / "engine_inputs.json")
    registry._write([
        _registry_entry("NSFWStudio_inputs/img_old.png", "img_old", age_hours=2),
        _registry_entry("NSFWStudio_inputs/img_active.png", "img_active", age_hours=2),
        _registry_entry("NSFWStudio_inputs/img_fresh.png", "img_fresh", age_hours=0.001),
        _registry_entry("user_files/user_keep.png", "img_other", age_hours=99),  # 非 Studio 子目录
    ])

    with session_factory() as session:
        _insert_running_stage_item(session, "img_active")  # RUNNING 引用保护

    cleaned_settings = dataclasses.replace(
        settings,
        storage=dataclasses.replace(settings.storage, data_root=data_root),
        comfyui={"input_dir": str(input_dir), "input_ttl_seconds": 3600},
    )
    stats = cleanup_engine_inputs(cleaned_settings, session_factory)
    assert stats == {"skipped": False, "deleted": 1, "kept": 3}
    assert not old_file.exists(), "超过 TTL 且无活动引用 → 清理"
    assert active_file.exists(), "RUNNING Stage 引用中的输入绝不清理"
    assert fresh_file.exists(), "未到 TTL 不清理"
    assert user_file.exists(), "非 NSFWStudio_inputs 文件绝不触碰"
    # 登记表回收：删除项不残留；其余保留
    remaining = {entry["file"] for entry in registry.entries()}
    assert "NSFWStudio_inputs/img_old.png" not in remaining
    assert "user_files/user_keep.png" in remaining


def test_engine_input_cleanup_skips_without_input_dir(settings):
    from app.services.engine_input_service import cleanup_engine_inputs

    # 显式空 comfyui 配置：不依赖本机 config.local.yaml 是否配置了 input_dir
    bare = dataclasses.replace(settings, comfyui={})
    stats = cleanup_engine_inputs(bare, None)
    assert stats["skipped"] is True


def test_mock_upload_records_into_registry(settings):
    registry = make_input_registry(settings)
    adapter = MockEngineAdapter({}, input_registry=registry)
    asyncio.run(adapter.upload_input_image(image_id="img_r1", file_name="a.png", data=b"x"))
    entries = registry.entries()
    assert entries and entries[0]["file"] == "mock_inputs/img_r1.png"
    assert entries[0]["image_id"] == "img_r1"