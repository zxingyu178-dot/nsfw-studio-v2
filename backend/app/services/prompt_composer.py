"""结构化 Prompt 的统一定义与合成（Phase 1 规范 §八、§九）。

八部分顺序永久固定：风格 → 人脸 → 服饰 → 动作 → 场景 → 镜头/构图 → 光线 → 额外描述。
前后端共用同一套字段名与拼接规则：后端保存时统一合成（PromptComposer），
前端预览调用后端接口（POST /api/v1/prompts/compose），保证
"UI 看到的 Prompt == 真正保存的 Prompt"。
"""
from __future__ import annotations

import json
from typing import Mapping

STRUCTURED_FIELDS: tuple[str, ...] = (
    "style",
    "face",
    "clothing",
    "pose",
    "scene",
    "composition",
    "lighting",
    "extra",
)

STRUCTURED_LABELS_ZH: dict[str, str] = {
    "style": "风格",
    "face": "人脸",
    "clothing": "服饰",
    "pose": "动作",
    "scene": "场景",
    "composition": "镜头/构图",
    "lighting": "光线",
    "extra": "额外描述",
}

_SEPARATOR = ", "


def empty_structured() -> dict[str, str]:
    """返回八个字段齐全的空结构化 Prompt（顺序固定）。"""
    return {field: "" for field in STRUCTURED_FIELDS}


def normalize_structured(mapping: Mapping[str, object] | None) -> dict[str, str]:
    """归一化为固定八字段 dict：未知字段丢弃、None 视为空、去除首尾空白。"""
    result = empty_structured()
    if not mapping:
        return result
    for field in STRUCTURED_FIELDS:
        value = mapping.get(field)
        if isinstance(value, str):
            result[field] = value.strip()
    return result


def compose_structured(structured: Mapping[str, object] | None) -> str:
    """按固定顺序拼接非空字段；第一版规则为 ``", "`` 连接。"""
    normalized = normalize_structured(structured)
    parts = [normalized[field] for field in STRUCTURED_FIELDS if normalized[field]]
    return _SEPARATOR.join(parts)


def dumps_structured(structured: Mapping[str, object] | None) -> str:
    """归一化后序列化为入库 JSON（固定键序，ensure_ascii=False）。"""
    return json.dumps(normalize_structured(structured), ensure_ascii=False)


def loads_structured(raw: str | None) -> dict[str, str]:
    """解析入库 JSON；容错：解析失败或结构不符时返回空结构。"""
    if not raw:
        return empty_structured()
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return empty_structured()
    if not isinstance(data, dict):
        return empty_structured()
    return normalize_structured(data)
