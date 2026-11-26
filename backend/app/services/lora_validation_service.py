"""任务级 LoRA 名称校验（创建 Job 前，返回 422）。"""
from __future__ import annotations

from collections.abc import Sequence

from app.core.errors import UnprocessableError


def validate_task_loras(adapter, modules: Sequence[dict] | None) -> None:
    """校验任务配置中的 LoRA 是否都存在于 ComfyUI /models/loras。

    - 未配置 loras 的模块直接跳过；
    - 引擎不可达时不阻断（preflight 已负责引擎可用性），执行期还有二次校验；
    - 缺失名称 → LORA_NOT_FOUND（422）。
    """
    names: list[str] = []
    for module in modules or []:
        config = module.get("config") or {}
        if not isinstance(config, dict):
            continue
        loras = config.get("loras") or []
        if not isinstance(loras, list):
            continue
        names.extend(
            str(item["name"])
            for item in loras
            if isinstance(item, dict) and item.get("name")
        )
    if not names:
        return
    getter = getattr(adapter, "available_lora_names", None)
    if getter is None:
        return
    available = getter()
    if available is None:
        return
    missing = sorted({name for name in names if name not in available})
    if missing:
        raise UnprocessableError(
            f"LoRA 不存在: {', '.join(missing)}",
            code="LORA_NOT_FOUND",
        )
