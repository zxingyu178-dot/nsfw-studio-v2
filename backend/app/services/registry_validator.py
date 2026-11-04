"""W4.1 Registry Validator（无第三方 jsonschema 依赖的轻量 Schema 校验）。

支持项目 Schema 实际使用的 JSON Schema 子集：
type / required / properties / additionalProperties / enum / const / pattern /
minLength / maxLength / minimum / maximum / minItems / maxItems / uniqueItems / items。

未知/不支持的 Schema 关键字会被忽略（Schema 本身由项目维护，不来自外部输入）。
所有错误以统一 issue 结构返回，供 CLI、API、CI 使用。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

KINDS = ("model", "workflow", "prompt", "asset", "submission")


def schema_path(registry_root: Path, kind: str) -> Path:
    return registry_root / "schemas" / f"{kind}.schema.json"


def load_schema(registry_root: Path, kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"未知 Schema 类型: {kind}")
    return json.loads(schema_path(registry_root, kind).read_text(encoding="utf-8"))


def _issue(code: str, path: str, message: str, level: str = "error") -> dict[str, str]:
    return {"level": level, "code": code, "path": path, "message": message}


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True


def validate_document(
    document: Any, schema: dict[str, Any], *, path: str = "$"
) -> list[dict[str, str]]:
    """按 Schema 校验文档，返回 issue 列表（空 = 通过）。"""
    issues: list[dict[str, str]] = []

    expected_type = schema.get("type")
    if expected_type is not None:
        types = expected_type if isinstance(expected_type, list) else [expected_type]
        if not any(_type_ok(document, item) for item in types):
            issues.append(_issue("SCHEMA_TYPE", path, f"类型应为 {types}，实际 {type(document).__name__}"))
            return issues

    if "const" in schema and document != schema["const"]:
        issues.append(_issue("SCHEMA_CONST", path, f"必须等于 {schema['const']!r}"))
    if "enum" in schema and document not in schema["enum"]:
        issues.append(_issue("SCHEMA_ENUM", path, f"必须是 {schema['enum']} 之一"))

    if isinstance(document, str):
        if "minLength" in schema and len(document) < int(schema["minLength"]):
            issues.append(_issue("SCHEMA_MIN_LENGTH", path, f"长度不得小于 {schema['minLength']}"))
        if "maxLength" in schema and len(document) > int(schema["maxLength"]):
            issues.append(_issue("SCHEMA_MAX_LENGTH", path, f"长度不得大于 {schema['maxLength']}"))
        if "pattern" in schema and re.search(str(schema["pattern"]), document) is None:
            issues.append(_issue("SCHEMA_PATTERN", path, f"不匹配 {schema['pattern']}"))

    if isinstance(document, (int, float)) and not isinstance(document, bool):
        if "minimum" in schema and document < schema["minimum"]:
            issues.append(_issue("SCHEMA_MINIMUM", path, f"不得小于 {schema['minimum']}"))
        if "maximum" in schema and document > schema["maximum"]:
            issues.append(_issue("SCHEMA_MAXIMUM", path, f"不得大于 {schema['maximum']}"))

    if isinstance(document, list):
        if "minItems" in schema and len(document) < int(schema["minItems"]):
            issues.append(_issue("SCHEMA_MIN_ITEMS", path, f"至少 {schema['minItems']} 项"))
        if "maxItems" in schema and len(document) > int(schema["maxItems"]):
            issues.append(_issue("SCHEMA_MAX_ITEMS", path, f"最多 {schema['maxItems']} 项"))
        if schema.get("uniqueItems"):
            try:
                if len({json.dumps(item, sort_keys=True, ensure_ascii=False) for item in document}) != len(document):
                    issues.append(_issue("SCHEMA_UNIQUE_ITEMS", path, "数组元素必须唯一"))
            except TypeError:
                issues.append(_issue("SCHEMA_UNIQUE_ITEMS", path, "数组元素无法判重"))
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(document):
                issues.extend(validate_document(item, item_schema, path=f"{path}[{index}]"))

    if isinstance(document, dict):
        for name in schema.get("required") or []:
            if name not in document:
                issues.append(_issue("SCHEMA_REQUIRED", path, f"缺少必填字段 {name}"))
        properties = schema.get("properties") or {}
        additional = schema.get("additionalProperties", True)
        for name, value in document.items():
            if name in properties:
                issues.extend(validate_document(value, properties[name], path=f"{path}.{name}"))
            elif additional is False:
                issues.append(_issue("SCHEMA_ADDITIONAL_PROPERTY", path, f"未知字段 {name}"))
            elif isinstance(additional, dict):
                issues.extend(validate_document(value, additional, path=f"{path}.{name}"))
    return issues


def validate_manifest(registry_root: Path, kind: str, manifest: Any) -> list[dict[str, str]]:
    return validate_document(manifest, load_schema(registry_root, kind))


def safe_relative_path(value: str, project_root: Path) -> tuple[Path | None, str | None]:
    """校验项目相对路径：禁止绝对路径、盘符、``..`` 与项目根逃逸。"""
    raw = str(value or "").replace("\\", "/")
    if not raw:
        return None, "路径为空"
    candidate = Path(raw)
    if candidate.is_absolute() or ":" in raw.split("/")[0]:
        return None, "禁止绝对路径/盘符"
    if any(part == ".." for part in candidate.parts):
        return None, "禁止路径穿越（..）"
    resolved = (project_root / candidate).resolve()
    try:
        resolved.relative_to(project_root.resolve())
    except ValueError:
        return None, "路径逃逸出项目根"
    return resolved, None
