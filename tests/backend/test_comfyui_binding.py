"""ComfyUI provider binding 单元测试（不需要 ComfyUI，CI 可跑）。

覆盖规范 §二十九（节点 ID / Workflow JSON 只存在于 provider binding 层）、
§三十（标准输入注入与默认值）、§五十五（binding_version / workflow_hash 溯源）。
"""
from __future__ import annotations

import hashlib
import json

from app.engine.base import EngineJobRequest
from app.engine.comfyui import PROVIDERS_DIR, ComfyUIAdapter

BINDING_DIR = PROVIDERS_DIR / "basic_generate" / "v1"


def make_adapter() -> ComfyUIAdapter:
    # URL 指向不可达端口；本测试只做纯同步注入，不发起任何网络请求
    return ComfyUIAdapter({}, {"url": "http://127.0.0.1:9"})


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
    request = EngineJobRequest(
        job_type="basic_generate",
        parameters={
            "positive_prompt": "a cat on a table",
            "negative_prompt": "blurry",
            "width": 640,
            "height": 960,
            "seed": 424242,
        },
    )
    prompt = adapter._build_prompt(request)
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
    over = adapter._build_prompt(EngineJobRequest(job_type="basic_generate", parameters={"seed": 2**40}))
    assert over["6"]["inputs"]["seed"] == 2147483647  # binding.seed_range.max
    adapter._build_prompt(EngineJobRequest(job_type="basic_generate", parameters={"width": 512}))
    again = adapter._build_prompt(EngineJobRequest(job_type="basic_generate", parameters={}))
    assert again["5"]["inputs"]["width"] != 512  # 模板未被上一次注入污染


def test_workflow_hash_and_binding_version_traceable():
    adapter = make_adapter()
    expected = hashlib.sha256((BINDING_DIR / "workflow.json").read_bytes()).hexdigest()[:16]
    assert adapter.workflow_hash == expected
    assert adapter.binding_version == "v1"