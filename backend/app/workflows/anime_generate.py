"""AnimeGenerateModule — 动漫生图模块（接入 miaomiaoHarem v14 单文件 SDXL 链）。

与 ``basic_generate`` 的**标准契约完全一致**（positive/negative/width/height/seed，
size_mode=explicit，无输入槽、无处理型 Job），差异：

- ``basic_generate`` → Qwen-Image 2.1（写实 / 通用场景）；
- ``anime_generate`` → miaomiaoHarem v14（SDXL 动漫底模）；
- v5 binding 起支持任务级 LoRA 叠加（0–2 条，config.loras）。

执行链：``anime_generate → EngineAdapter → workflows/providers/comfyui/anime_generate/v5``。
"""
from __future__ import annotations

import dataclasses
from typing import Any, Mapping

from app.core.errors import UnprocessableError
from app.workflows.base import (
    JobRequestContext,
    ModuleCapabilities,
    ParameterSpec,
    WorkflowValidation,
)
from app.workflows.basic_generate import BasicGenerateModule

LORA_MAX = 2
LORA_STRENGTH_MIN = -2.0
LORA_STRENGTH_MAX = 2.0


class AnimeGenerateModule(BasicGenerateModule):
    """动漫文生图模块：miaomiaoHarem v14 + 可选 LoRA 叠加。"""

    module_id = "anime_generate"
    module_version = "v1"

    def capabilities(self) -> ModuleCapabilities:
        return dataclasses.replace(
            super().capabilities(),
            module_id=self.module_id,
            title="动漫生图（MiaoMiao）",
            description=(
                "动漫 / 插画文生图：miaomiaoHarem v14（单文件 SDXL）；"
                "v5 起支持任务级 LoRA 叠加（0–2 条）"
            ),
            parameters=(
                *super().capabilities().parameters,
                ParameterSpec(
                    "loras",
                    "lora_list",
                    default=[],
                    title="LoRA 叠加",
                    description=(
                        "最多 2 条；元素为 {name, strength_model, strength_clip}，"
                        "名称需存在于 ComfyUI /models/loras"
                    ),
                    # 结构化列表，UI 暂不渲染；由 API / Agent 任务配置写入
                    configurable=False,
                ),
            ),
        )

    # ===== 任务级 LoRA 配置校验 =====
    @staticmethod
    def _normalize_loras(raw: Any) -> list[dict[str, Any]]:
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise UnprocessableError(
                "loras 必须为数组", code="LORA_PARAM_INVALID"
            )
        if len(raw) > LORA_MAX:
            raise UnprocessableError(
                f"最多叠加 {LORA_MAX} 条 LoRA（收到 {len(raw)} 条）",
                code="LORA_LIMIT_EXCEEDED",
            )
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, dict):
                raise UnprocessableError(
                    f"第 {index} 条 LoRA 必须为对象", code="LORA_PARAM_INVALID"
                )
            unknown = set(item) - {"name", "strength_model", "strength_clip"}
            if unknown:
                raise UnprocessableError(
                    f"第 {index} 条 LoRA 含未知字段: {', '.join(sorted(unknown))}",
                    code="LORA_PARAM_INVALID",
                )
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                raise UnprocessableError(
                    f"第 {index} 条 LoRA 缺少文件名", code="LORA_PARAM_INVALID"
                )
            name = name.strip()
            if "/" in name or "\\" in name:
                raise UnprocessableError(
                    f"第 {index} 条 LoRA 文件名不得包含路径", code="LORA_PARAM_INVALID"
                )
            strengths: dict[str, float] = {}
            for key in ("strength_model", "strength_clip"):
                value = item.get(key, 1.0)
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise UnprocessableError(
                        f"第 {index} 条 LoRA 的 {key} 必须为数字",
                        code="LORA_PARAM_INVALID",
                    )
                if not LORA_STRENGTH_MIN <= float(value) <= LORA_STRENGTH_MAX:
                    raise UnprocessableError(
                        f"第 {index} 条 LoRA 的 {key} 取值范围为 "
                        f"{LORA_STRENGTH_MIN:g}～{LORA_STRENGTH_MAX:g}",
                        code="LORA_STRENGTH_OUT_OF_RANGE",
                    )
                strengths[key] = float(value)
            normalized.append({"name": name, **strengths})
        return normalized

    def validate_config(self, config: Mapping[str, Any]) -> WorkflowValidation:
        if config.get("loras") is not None:
            self._normalize_loras(config.get("loras"))
        return super().validate_config(config)

    def build_engine_request(
        self,
        context: JobRequestContext,
        prepared: Mapping[str, Any] | None = None,
    ):
        request = super().build_engine_request(context, prepared)
        loras = self._normalize_loras((context.module_config or {}).get("loras"))
        if not loras:
            return request
        parameters = dict(request.parameters)
        parameters["loras"] = loras
        return dataclasses.replace(request, parameters=parameters)
