"""ComfyUI provider binding 单元测试（不需要 ComfyUI，CI 可跑）。

覆盖：
- 规范 §二十九（节点 ID / Workflow JSON 只存在于 provider binding 层）、§三十（标准输入注入）；
- Phase 2.1 §七（binding 版本由 module_id + binding_version 解析）；
- Phase 3 §0.2（一个 Adapter 服务全部模块，绑定属于每次请求）、§0.3（workflow_hash 校验）、
  §二十二（basic_generate / upscale / basic_generate 交替动态加载）。
"""
from __future__ import annotations

import hashlib
import json

import pytest

from app.engine.base import EngineBindingRef, EngineError, EngineJobRequest
from app.engine.comfyui import PROVIDERS_DIR, ComfyUIAdapter

BINDING_DIR = PROVIDERS_DIR / "basic_generate" / "v1"
UPSCALE_DIR = PROVIDERS_DIR / "upscale" / "v1"


def make_adapter() -> ComfyUIAdapter:
    # URL 指向不可达端口；本测试只做纯同步注入，不发起任何网络请求
    return ComfyUIAdapter({}, {"url": "http://127.0.0.1:9"})


def basic_ref() -> EngineBindingRef:
    return EngineBindingRef(module_id="basic_generate", provider="comfyui", binding_version="v1")


def test_workflow_template_nodes_and_empty_prompts():
    workflow = json.loads((BINDING_DIR / "workflow.json").read_text(encoding="utf-8"))
    assert workflow["4"]["class_type"] == "TextEncodeQwenImage21"
    assert workflow["5"]["class_type"] == "EmptyLatentImage"
    assert workflow["6"]["class_type"] == "KSampler"
    assert workflow["8"]["class_type"] == "SaveImage"
    # 模板不得包含具体私人 Prompt 内容（运行时由 binding 注入）
    assert workflow["4"]["inputs"]["prompt"] == ""
    assert workflow["4"]["inputs"]["negative_prompt"] == ""


def test_build_prompt_injects_standard_inputs():
    adapter = make_adapter()
    workflow, binding, _hash = adapter.load_binding(basic_ref())
    request = EngineJobRequest(
        binding=basic_ref(),
        parameters={
            "positive_prompt": "a cat on a table",
            "negative_prompt": "blurry",
            "width": 640,
            "height": 960,
            "seed": 424242,
        },
    )
    prompt = adapter._build_prompt(request, workflow, binding)
    assert prompt["4"]["inputs"]["prompt"] == "a cat on a table"
    assert prompt["4"]["inputs"]["negative_prompt"] == "blurry"
    assert prompt["5"]["inputs"]["width"] == 640
    assert prompt["5"]["inputs"]["height"] == 960
    assert prompt["6"]["inputs"]["seed"] == 424242
    # 未映射参数保持模板 / defaults 原值
    assert prompt["6"]["inputs"]["steps"] == 25
    assert prompt["4"]["inputs"]["resolution"] == 1024
    assert prompt["5"]["inputs"]["batch_size"] == 1
    assert prompt["8"]["inputs"]["filename_prefix"].startswith("NSFWStudio/")


def test_build_prompt_clamps_seed_and_does_not_mutate_template():
    adapter = make_adapter()
    workflow, binding, _hash = adapter.load_binding(basic_ref())
    over = adapter._build_prompt(
        EngineJobRequest(binding=basic_ref(), parameters={"seed": 2**40}), workflow, binding
    )
    assert over["6"]["inputs"]["seed"] == 2147483647  # binding.seed_range.max
    adapter._build_prompt(
        EngineJobRequest(binding=basic_ref(), parameters={"width": 512}), workflow, binding
    )
    again = adapter._build_prompt(EngineJobRequest(binding=basic_ref(), parameters={}), workflow, binding)
    assert again["5"]["inputs"]["width"] != 512  # 模板未被上一次注入污染


def test_workflow_hash_and_binding_version_traceable():
    adapter = make_adapter()
    expected = hashlib.sha256((BINDING_DIR / "workflow.json").read_bytes()).hexdigest()[:16]
    assert adapter.binding_identity("basic_generate", "v1") == ("v1", expected)


def test_workflow_hash_mismatch_rejected():
    """§0.3：Job 固化的 hash 与磁盘不一致（binding 被改动）→ 拒绝执行，禁止静默。"""
    adapter = make_adapter()
    tampered = EngineBindingRef(
        module_id="basic_generate", provider="comfyui", binding_version="v1",
        workflow_hash="0000000000000000",
    )
    with pytest.raises(EngineError) as excinfo:
        adapter.load_binding(tampered)
    assert excinfo.value.error_type == "WORKFLOW_HASH_MISMATCH"


def test_one_adapter_serves_all_modules_dynamically():
    """§0.2/§二十二：同一 Adapter 交替加载 basic_generate/v1、upscale/v1、basic_generate/v1。"""
    adapter = make_adapter()
    for module_id in ("basic_generate", "upscale", "basic_generate"):
        _workflow, binding, _hash = adapter.load_binding(EngineBindingRef(
            module_id=module_id, provider="comfyui", binding_version="v1",
        ))
        assert binding.get("module") == module_id
    # 缓存 key 是 (module_id, binding_version)，不是整个 Adapter 只有一个绑定
    assert ("basic_generate", "v1") in adapter._bindings
    assert ("upscale", "v1") in adapter._bindings


def test_upscale_workflow_uses_load_image_and_upscale_model():
    """upscale/v1：LoadImage → UpscaleModelLoader(4x-UltraSharp) → ImageUpscaleWithModel → SaveImage。"""
    workflow = json.loads((UPSCALE_DIR / "workflow.json").read_text(encoding="utf-8"))
    assert workflow["1"]["class_type"] == "LoadImage"
    assert workflow["2"]["class_type"] == "UpscaleModelLoader"
    assert workflow["2"]["inputs"]["model_name"] == "4x-UltraSharp.pth"
    assert workflow["3"]["class_type"] == "ImageUpscaleWithModel"
    assert workflow["3"]["inputs"]["image"] == ["1", 0]
    assert workflow["4"]["class_type"] == "SaveImage"
    binding = (UPSCALE_DIR / "binding.yaml").read_text(encoding="utf-8")
    assert "input_image" in binding