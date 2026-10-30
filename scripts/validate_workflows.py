#!/usr/bin/env python3
"""G0 工作流静态校验器（W1-2）。

遍历 workflows/providers/<provider>/<module>/<binding>/，检查：
API JSON 合法性、节点引用、binding 映射、SaveImage、Seed 范围、依赖/性能声明、
机器绝对路径与禁止文件。不启动 ComfyUI、不使用 GPU、不下载模型。

Legacy 冻结 binding（见 LEGACY_BINDINGS）允许缺少 requirements/performance，
但结构错误仍然报错；新 binding 必须完整声明。

用法：
    python scripts/validate_workflows.py [--root <repo-root>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

LEGACY_BINDINGS = {
    ("basic_generate", "v1"),
    ("img2img", "v1"),
    ("reference_generate", "v1"),
    ("anime_generate", "v1"),
    ("upscale", "v1"),
}
CORE_TYPE_PREFIXES = (
    "KSampler",
    "CLIPLoader",
    "VAELoader",
    "VAEEncode",
    "VAEDecode",
    "EmptyLatentImage",
    "LoadImage",
    "SaveImage",
    "TextEncodeQwenImage21",
    "CLIPTextEncode",
    "UNETLoader",
    "UpscaleModelLoader",
    "ImageUpscaleWithModel",
    "LoraLoader",
    "LoraLoaderModelOnly",
)
ABSOLUTE_PATH = re.compile(r"(?:[A-Za-z]:[\\/]|/home/|/Users/|\\\\[A-Za-z])")
FORBIDDEN_SUFFIXES = {
    ".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".onnx",
    ".png", ".jpg", ".jpeg", ".webp", ".mp4", ".log", ".db", ".sqlite", ".zip",
}
SAVE_PREFIX_REQUIRED = "NSFWStudio"
SEED_MAX = 2147483647


class Result:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checked: int = 0

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warning(self, message: str) -> None:
        self.warnings.append(message)


def _scan_strings(value: Any, path: str, result: Result) -> None:
    if isinstance(value, str):
        if ABSOLUTE_PATH.search(value):
            result.error(f"{path}: 含机器绝对路径: {value[:120]}")
    elif isinstance(value, dict):
        for key, item in value.items():
            _scan_strings(item, f"{path}.{key}", result)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scan_strings(item, f"{path}[{index}]", result)


def _is_core_type(class_type: str) -> bool:
    return any(class_type.startswith(prefix) for prefix in CORE_TYPE_PREFIXES)


def _validate_requirements(binding: dict, legacy: bool, result: Result, label: str) -> None:
    requirements = binding.get("requirements")
    performance = binding.get("performance")
    if legacy:
        if requirements is None:
            result.warning(f"{label}: legacy binding 未声明 requirements（允许，按兼容政策）")
        if performance is None:
            result.warning(f"{label}: legacy binding 未声明 performance（允许，按兼容政策）")
        return
    if not isinstance(requirements, dict):
        result.error(f"{label}: 新 binding 必须声明 requirements")
        return
    if not requirements.get("comfyui_min_version"):
        result.error(f"{label}: requirements 缺少 comfyui_min_version")
    if not isinstance(requirements.get("nodes"), list) or not requirements["nodes"]:
        result.error(f"{label}: requirements 缺少 nodes 依赖清单")
    if not isinstance(requirements.get("models"), list) or not requirements["models"]:
        result.error(f"{label}: requirements 缺少 models 依赖清单")
    if not isinstance(performance, dict):
        result.error(f"{label}: 新 binding 必须声明 performance")
        return
    status = performance.get("status")
    if status not in {"unverified", "measured", "failed"}:
        result.error(f"{label}: performance.status 必须为 unverified/measured/failed")
    if status == "measured" and not performance.get("tested_profiles"):
        result.error(f"{label}: performance.status=measured 但没有 tested_profiles")
    for profile in performance.get("tested_profiles") or []:
        if not isinstance(profile, dict):
            result.error(f"{label}: tested_profiles 条目必须是对象")
            continue
        missing = [key for key in ("width", "height", "steps") if key not in profile]
        if missing:
            result.error(f"{label}: tested_profile 缺少 {', '.join(missing)}")


def _validate_node_graph(
    workflow: dict, binding: dict, legacy: bool, requirements: dict | None, result: Result, label: str
) -> None:
    if not isinstance(workflow, dict) or not workflow:
        result.error(f"{label}: workflow.json 必须是非空对象")
        return
    nodes = {}
    for node_id, node in workflow.items():
        if not isinstance(node, dict):
            result.error(f"{label}: 节点 {node_id} 必须是对象")
            continue
        class_type = node.get("class_type")
        if not isinstance(class_type, str) or not class_type:
            result.error(f"{label}: 节点 {node_id} 缺少 class_type")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            result.error(f"{label}: 节点 {node_id} 缺少 inputs 对象")
            continue
        nodes[node_id] = node

    declared_types = set()
    if isinstance(requirements, dict):
        for item in requirements.get("nodes") or []:
            if isinstance(item, dict) and isinstance(item.get("class_type"), str):
                declared_types.add(item["class_type"])

    for node_id, node in nodes.items():
        class_type = node.get("class_type") or ""
        if not _is_core_type(class_type) and class_type not in declared_types:
            message = f"{label}: 节点 {node_id} 的 class_type {class_type} 未在 requirements.nodes 声明"
            (result.warning if legacy else result.error)(message)
        for field, value in (node.get("inputs") or {}).items():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                if value[0] not in nodes:
                    result.error(f"{label}: 节点 {node_id}.{field} 引用了不存在的节点 {value[0]}")

    # binding 注入点
    for key, mapping in (binding.get("inputs") or {}).items():
        if not isinstance(mapping, dict):
            result.error(f"{label}: inputs.{key} 必须是对象")
            continue
        node_id = str(mapping.get("node"))
        field = mapping.get("field")
        if node_id not in nodes:
            result.error(f"{label}: inputs.{key} 指向不存在的节点 {node_id}")
            continue
        if field not in (nodes[node_id].get("inputs") or {}):
            result.error(f"{label}: inputs.{key} 指向节点 {node_id} 不存在的字段 {field}")

    # defaults 注入点
    for node_id, values in (binding.get("defaults") or {}).items():
        node_id = str(node_id)
        if node_id not in nodes:
            result.error(f"{label}: defaults 指向不存在的节点 {node_id}")
            continue
        if not isinstance(values, dict):
            result.error(f"{label}: defaults.{node_id} 必须是对象")
            continue
        for field in values:
            if field not in (nodes[node_id].get("inputs") or {}):
                result.error(f"{label}: defaults.{node_id}.{field} 不存在于节点输入")

    save_node = str(binding.get("save_image_node") or "")
    if save_node not in nodes:
        result.error(f"{label}: save_image_node {save_node} 不存在")
    else:
        if nodes[save_node].get("class_type") != "SaveImage":
            result.error(f"{label}: save_image_node {save_node} 不是 SaveImage")
        if not (nodes[save_node].get("inputs") or {}).get("filename_prefix"):
            result.error(f"{label}: SaveImage 缺少 filename_prefix")
    prefix = str(binding.get("save_image_prefix") or "")
    if SAVE_PREFIX_REQUIRED not in prefix:
        result.error(f"{label}: save_image_prefix 必须包含 {SAVE_PREFIX_REQUIRED}")

    # Seed 范围
    seed_range = binding.get("seed_range")
    if not isinstance(seed_range, dict):
        result.error(f"{label}: 缺少 seed_range")
    else:
        low, high = seed_range.get("min"), seed_range.get("max")
        if not isinstance(low, int) or not isinstance(high, int):
            result.error(f"{label}: seed_range min/max 必须是整数")
        elif not 0 <= low < high <= SEED_MAX:
            result.error(f"{label}: seed_range 必须在 0 <= min < max <= {SEED_MAX}")

    # 未连接的孤立节点仅警告（legacy 可能保留辅助节点）
    if save_node in nodes:
        reachable = set()
        stack = [save_node]
        while stack:
            current = stack.pop()
            if current in reachable:
                continue
            reachable.add(current)
            for value in (nodes[current].get("inputs") or {}).values():
                if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                    stack.append(value[0])
        orphan = sorted(set(nodes) - reachable)
        if orphan:
            result.warning(f"{label}: 存在未连接到 SaveImage 的节点 {orphan}")


def validate_binding(binding_dir: Path, root: Path, result: Result) -> None:
    rel = binding_dir.relative_to(root)
    parts = rel.parts
    if len(parts) != 5 or parts[0] != "workflows" or parts[1] != "providers":
        result.error(f"{rel}: 目录层级必须为 workflows/providers/<provider>/<module>/<version>")
        return
    _, _, provider, module_id, version = parts
    label = f"{module_id}/{version}"
    result.checked += 1

    workflow_path = binding_dir / "workflow.json"
    binding_path = binding_dir / "binding.yaml"
    readme_path = binding_dir / "README.md"
    for path, name in ((workflow_path, "workflow.json"), (binding_path, "binding.yaml"), (readme_path, "README.md")):
        if not path.is_file():
            result.error(f"{label}: 缺少 {name}")

    if not workflow_path.is_file() or not binding_path.is_file():
        return

    try:
        workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        result.error(f"{label}: workflow.json 非法: {exc}")
        return
    try:
        binding = yaml.safe_load(binding_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        result.error(f"{label}: binding.yaml 非法: {exc}")
        return
    if not isinstance(binding, dict):
        result.error(f"{label}: binding.yaml 必须是对象")
        return

    if str(binding.get("module")) != module_id:
        result.error(f"{label}: binding.module={binding.get('module')} 与目录 {module_id} 不一致")
    if str(binding.get("provider")) != provider:
        result.error(f"{label}: binding.provider={binding.get('provider')} 与目录 {provider} 不一致")
    if str(binding.get("binding_version")) != version:
        result.error(f"{label}: binding.binding_version={binding.get('binding_version')} 与目录 {version} 不一致")
    if str(binding.get("workflow_file") or "workflow.json") != "workflow.json":
        result.error(f"{label}: workflow_file 必须指向 workflow.json")

    requirements = binding.get("requirements")
    legacy = (module_id, version) in LEGACY_BINDINGS
    _validate_requirements(binding, legacy, result, label)
    _validate_node_graph(
        workflow, binding, legacy, requirements if isinstance(requirements, dict) else None, result, label
    )
    _scan_strings(workflow, f"{label}.workflow", result)
    _scan_strings(binding, f"{label}.binding", result)

    for path in binding_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in FORBIDDEN_SUFFIXES:
            result.error(f"{label}: 禁止把模型/图片/日志放入 binding 目录: {path.name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="G0 workflow static validator")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    providers = root / "workflows" / "providers"
    if not providers.is_dir():
        print(f"[G0] workflows/providers not found under {root}", file=sys.stderr)
        return 2

    result = Result()
    binding_dirs = sorted(
        path for path in providers.glob("*/*/*") if path.is_dir()
    )
    for binding_dir in binding_dirs:
        validate_binding(binding_dir, root, result)

    for warning in result.warnings:
        print(f"[WARN] {warning}")
    for error in result.errors:
        print(f"[ERROR] {error}")
    print(f"[G0] checked={result.checked} errors={len(result.errors)} warnings={len(result.warnings)}")
    if result.errors:
        return 1
    if result.checked == 0:
        print("[G0] no bindings found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
