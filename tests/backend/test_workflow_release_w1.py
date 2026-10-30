"""W1 工作流治理回归：版本冻结、放行状态与 G0 静态校验。"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import yaml

from app.engine.release import release_status
from app.workflows.img2img import Img2ImgModule, _default_binding

ROOT = Path(__file__).resolve().parents[2]
IMG2IMG_V1 = ROOT / "workflows/providers/comfyui/img2img/v1"
IMG2IMG_V2 = ROOT / "workflows/providers/comfyui/img2img/v2"


def _sha16(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def test_img2img_v1_is_frozen_with_original_hashes():
    # 原始 94aa003 v1 的字节在 Windows（CRLF）与 Linux（LF）下有两种历史指纹：
    # LF=92132d/ca978（1 个更早 Job），CRLF=7c1156/2f2d5（12 个本地 Job）。
    # 两者都属于原始冻结内容；明确禁止 W0 修改后的指纹。
    workflow_hash = _sha16(IMG2IMG_V1 / "workflow.json")
    binding_hash = _sha16(IMG2IMG_V1 / "binding.yaml")
    assert workflow_hash in {"92132d53229d9bea", "7c11569529d4e653"}
    assert binding_hash in {"ca978ab11e07ca4a", "2f2d5c06055c623a"}
    assert workflow_hash != "9c7d1a1f1113391d", "v1 不得保留 W0 的 0.8 工作流"
    assert binding_hash != "2d8bae7af79c8bd3", "v1 不得保留 W0 的 0.8 binding"


def test_img2img_v2_is_new_default_and_has_dependencies():
    binding = yaml.safe_load((IMG2IMG_V2 / "binding.yaml").read_text(encoding="utf-8"))
    workflow = json.loads((IMG2IMG_V2 / "workflow.json").read_text(encoding="utf-8"))
    assert binding["binding_version"] == "v2"
    assert binding["capabilities"]["denoise_range"]["default"] == 0.8
    assert workflow["7"]["inputs"]["denoise"] == 0.8
    assert binding["requirements"]["models"]
    assert binding["performance"]["status"] == "measured"
    assert _default_binding(Img2ImgModule()).binding_version == "v2"


def test_release_status_is_binding_version_aware_and_fail_closed():
    basic = release_status("basic_generate", "v1", binding_valid=True)
    assert basic["ready_to_run"] is True and basic["hardware_status"] == "normal"

    anime = release_status("anime_generate", "v1", binding_valid=True)
    assert anime["real_gate_passed"] is False
    assert anime["ready_to_run"] is False
    assert anime["hardware_status"] == "experimental"

    reference = release_status("reference_generate", "v1", binding_valid=True)
    assert reference["ready_to_run"] is True
    assert reference["hardware_status"] == "slow"
    assert reference["default_profile_verified"] is False

    unknown = release_status("img2img", "v9", binding_valid=True)
    assert unknown["ready_to_run"] is False
    assert "未在" in unknown["notes"]

    assert release_status("basic_generate", "v1", binding_valid=False)["ready_to_run"] is False


def test_g0_validator_passes_current_repository():
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_workflows.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "errors=0" in completed.stdout


def test_g0_validator_rejects_broken_graph(tmp_path: Path):
    binding_dir = tmp_path / "workflows/providers/comfyui/bad_generate/v1"
    binding_dir.mkdir(parents=True)
    (binding_dir / "workflow.json").write_text(
        json.dumps({"1": {"class_type": "KSampler", "inputs": {"model": ["missing", 0]}}}),
        encoding="utf-8",
    )
    (binding_dir / "binding.yaml").write_text(
        yaml.safe_dump(
            {
                "binding_version": "v1",
                "module": "bad_generate",
                "provider": "comfyui",
                "workflow_file": "workflow.json",
                "save_image_node": "9",
                "save_image_prefix": "NSFWStudio/x",
                "inputs": {},
                "seed_range": {"min": 0, "max": 2147483647},
            }
        ),
        encoding="utf-8",
    )
    (binding_dir / "README.md").write_text("# bad\n", encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_workflows.py"), "--root", str(tmp_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 1
    assert "不存在的节点" in completed.stdout
