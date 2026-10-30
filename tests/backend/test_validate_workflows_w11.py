"""W1.1-4：G0 静态检查器增强的负向测试（每类错误可被发现）。"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts/validate_workflows.py"


def base_workflow() -> dict:
    return {
        "1": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": "model.gguf"}},
        "2": {"class_type": "CLIPLoader", "inputs": {"clip_name": "clip.safetensors"}},
        "3": {"class_type": "VAELoader", "inputs": {"vae_name": "vae.safetensors"}},
        "4": {"class_type": "TextEncodeQwenImage21", "inputs": {
            "clip": ["2", 0], "prompt": "", "negative_prompt": "", "resolution": 1024,
        }},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 768, "height": 768, "batch_size": 1}},
        "6": {"class_type": "KSampler", "inputs": {
            "model": ["1", 0], "seed": 0, "steps": 8, "cfg": 1.0,
            "sampler_name": "euler", "scheduler": "simple",
            "positive": ["4", 0], "negative": ["4", 1], "latent": ["5", 0], "denoise": 1.0,
        }},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["3", 0]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "NSFWStudio/x"}},
    }


def base_binding() -> dict:
    return {
        "binding_version": "v1",
        "module": "test_generate",
        "provider": "comfyui",
        "workflow_file": "workflow.json",
        "save_image_node": "8",
        "save_image_prefix": "NSFWStudio/{job}/{stage}/{item}",
        "inputs": {
            "positive_prompt": {"node": "4", "field": "prompt"},
            "negative_prompt": {"node": "4", "field": "negative_prompt"},
            "width": {"node": "5", "field": "width"},
            "height": {"node": "5", "field": "height"},
            "seed": {"node": "6", "field": "seed"},
        },
        "defaults": {"6": {"steps": 8, "cfg": 1.0}},
        "seed_range": {"min": 0, "max": 2147483647},
        "requirements": {
            "comfyui_min_version": "0.37.0",
            "nodes": [
                {"class_type": "UnetLoaderGGUF", "source": "custom", "package": "ComfyUI-GGUF"},
            ],
            "models": [
                {"type": "diffusion_models", "filename": "model.gguf", "size_bytes": 0, "sha256": "unverified"},
                {"type": "text_encoders", "filename": "clip.safetensors", "size_bytes": 0, "sha256": "unverified"},
                {"type": "vae", "filename": "vae.safetensors", "size_bytes": 0, "sha256": "unverified"},
            ],
        },
        "performance": {
            "status": "measured",
            "batch_size": 1,
            "tested_profiles": [{
                "width": 768, "height": 768, "steps": 8, "cfg": 1.0,
                "sampler": "euler", "scheduler": "simple", "batch_size": 1,
                "sampling_seconds": 10, "source": "test",
            }],
        },
    }


def write_binding(
    root: Path,
    workflow: dict | None = None,
    binding: dict | None = None,
    module_id: str = "test_generate",
) -> None:
    data = binding or base_binding()
    data["module"] = module_id
    binding_dir = root / f"workflows/providers/comfyui/{module_id}/v1"
    binding_dir.mkdir(parents=True)
    (binding_dir / "workflow.json").write_text(json.dumps(workflow or base_workflow()), encoding="utf-8")
    (binding_dir / "binding.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    (binding_dir / "README.md").write_text("# test\n", encoding="utf-8")


def run_validator(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), "--root", str(root)],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )


def test_valid_new_binding_passes(tmp_path):
    write_binding(tmp_path)
    completed = run_validator(tmp_path)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "errors=0" in completed.stdout


def test_unknown_type_with_core_prefix_is_not_whitelisted(tmp_path):
    workflow = base_workflow()
    workflow["1"]["class_type"] = "KSamplerFake"
    write_binding(tmp_path, workflow=workflow)
    completed = run_validator(tmp_path)
    assert completed.returncode == 1
    assert "KSamplerFake 未在 requirements.nodes 声明" in completed.stdout


def test_save_image_must_connect_to_existing_node(tmp_path):
    workflow = base_workflow()
    workflow["8"]["inputs"]["images"] = ["missing", 0]
    write_binding(tmp_path, workflow=workflow)
    completed = run_validator(tmp_path)
    assert completed.returncode == 1
    assert "SaveImage.images 引用了不存在的节点" in completed.stdout


def test_output_index_out_of_range(tmp_path):
    workflow = base_workflow()
    workflow["6"]["inputs"]["positive"] = ["4", 5]
    write_binding(tmp_path, workflow=workflow)
    completed = run_validator(tmp_path)
    assert completed.returncode == 1
    assert "输出索引 5 超出" in completed.stdout


def test_missing_standard_input_mapping(tmp_path):
    binding = base_binding()
    del binding["inputs"]["seed"]
    # 标准输入映射按已登记模块名校验；basic_generate 必须包含正/负提示词、宽高、seed。
    write_binding(tmp_path, binding=binding, module_id="basic_generate")
    completed = run_validator(tmp_path)
    assert completed.returncode == 1
    assert "缺少标准输入映射" in completed.stdout


def test_model_filename_must_match_requirements(tmp_path):
    binding = base_binding()
    binding["requirements"]["models"] = [
        item for item in binding["requirements"]["models"] if item["filename"] != "model.gguf"
    ]
    write_binding(tmp_path, binding=binding)
    completed = run_validator(tmp_path)
    assert completed.returncode == 1
    assert "未在 requirements.models 声明" in completed.stdout


def test_embedded_prompt_is_rejected_for_new_binding(tmp_path):
    workflow = base_workflow()
    workflow["4"]["inputs"]["prompt"] = "my private prompt, personal photo of a real person"
    write_binding(tmp_path, workflow=workflow)
    completed = run_validator(tmp_path)
    assert completed.returncode == 1
    assert "含内置 Prompt" in completed.stdout


def test_tested_profile_requires_evidence_fields(tmp_path):
    binding = base_binding()
    del binding["performance"]["tested_profiles"][0]["batch_size"]
    write_binding(tmp_path, binding=binding)
    completed = run_validator(tmp_path)
    assert completed.returncode == 1
    assert "tested_profile 缺少 batch_size" in completed.stdout


def test_git_tracked_model_weights_are_rejected(tmp_path):
    write_binding(tmp_path)
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    weight = tmp_path / "weights.safetensors"
    weight.write_bytes(b"fake")
    subprocess.run(["git", "add", "weights.safetensors"], cwd=tmp_path, check=True, capture_output=True)
    completed = run_validator(tmp_path)
    assert completed.returncode == 1
    assert "Git 跟踪了模型权重文件" in completed.stdout
