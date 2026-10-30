"""工作流正式放行状态（W1-1）。

`available` 只表示模块注册与 binding 合法，不能代表依赖齐全或真实 Gate 已通过。
本模块读取 `workflows/release_manifest.yaml`，按 module_id + binding_version 给出
正式放行状态；未登记的新 binding 一律 fail-closed（ready_to_run=false）。

状态与硬件适配分离：hardware_status 只描述当前机器适配程度，不固化到模块全局。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from app.core.errors import ValidationError

MANIFEST_PATH = Path(__file__).resolve().parents[3] / "workflows" / "release_manifest.yaml"
VALID_HARDWARE_STATUS = {"normal", "slow", "experimental", "unsupported"}


@lru_cache(maxsize=1)
def load_release_manifest() -> dict[str, Any]:
    """读取放行清单；文件缺失/非法时返回空清单（调用方 fail-closed）。"""
    try:
        raw = MANIFEST_PATH.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _binding_entry(module_id: str, binding_version: str) -> dict[str, Any] | None:
    modules = load_release_manifest().get("modules") or {}
    module = modules.get(module_id) or {}
    bindings = module.get("bindings") or {}
    entry = bindings.get(binding_version)
    return entry if isinstance(entry, dict) else None


def release_status(
    module_id: str,
    binding_version: str,
    *,
    binding_valid: bool,
    registered: bool = True,
) -> dict[str, Any]:
    """计算正式放行状态；未登记的 binding 一律不可运行。"""
    entry = _binding_entry(module_id, binding_version)
    if entry is None:
        return {
            "registered": registered,
            "binding_valid": binding_valid,
            "dependencies_ready": False,
            "real_gate_passed": False,
            "hardware_status": "unverified",
            "default_profile_verified": False,
            "ready_to_run": False,
            "notes": "该 binding 未在 workflows/release_manifest.yaml 登记，禁止正式运行",
        }

    dependencies_ready = bool(entry.get("dependencies_ready", False))
    real_gate_passed = bool(entry.get("real_gate_passed", False))
    hardware_status = str(entry.get("hardware_status") or "unverified")
    if hardware_status not in VALID_HARDWARE_STATUS:
        hardware_status = "unverified"
    default_profile_verified = bool(entry.get("default_profile_verified", False))
    ready = (
        registered
        and binding_valid
        and dependencies_ready
        and real_gate_passed
        and hardware_status != "unsupported"
    )
    return {
        "registered": registered,
        "binding_valid": binding_valid,
        "dependencies_ready": dependencies_ready,
        "real_gate_passed": real_gate_passed,
        "hardware_status": hardware_status,
        "default_profile_verified": default_profile_verified,
        "ready_to_run": ready,
        "notes": str(entry.get("notes") or ""),
    }


def ensure_modules_released(modules: list[dict[str, Any]]) -> None:
    """服务端新任务放行门禁（W1.1-1）。

    以已解析的真实执行身份（module_id + binding_version）为准，不信任客户端字段。
    未登记 binding、未通过真实 Gate、依赖未就绪或 hardware=unsupported 时一律拒绝，
    且在数据库写入任何 Job/Stage 之前抛出。
    """
    rejected: list[dict[str, str]] = []
    for module in modules:
        module_id = str(module.get("module_id") or "")
        binding_version = str(module.get("binding_version") or "")
        status = release_status(module_id, binding_version, binding_valid=True)
        if status["ready_to_run"] is not True:
            rejected.append({
                "module_id": module_id,
                "binding_version": binding_version,
                "reason": str(status.get("notes") or "not released"),
            })
    if rejected:
        detail = "；".join(
            f"{item['module_id']}/{item['binding_version']}（{item['reason']}）" for item in rejected
        )
        raise ValidationError(
            f"工作流未通过正式放行，已拒绝新任务：{detail}",
            code="WORKFLOW_NOT_RELEASED",
            details={"modules": rejected},
        )
