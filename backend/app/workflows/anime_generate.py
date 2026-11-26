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
MODEL_MAX_LENGTH = 255
MODULE_CONFIG_KEYS = {
    "model", "loras", "steps", "cfg", "sampler_name", "scheduler", "denoise",
    "face_detailer",
}
SAMPLER_NAMES = (
    "euler", "euler_ancestral", "heun", "dpm_2", "dpm_2_ancestral", "lms",
    "dpm_fast", "dpm_adaptive", "dpmpp_2s_ancestral", "dpmpp_sde",
    "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_3m_sde", "ddpm", "lcm",
    "uni_pc", "uni_pc_bh2", "er_sde",
)
SCHEDULER_NAMES = (
    "normal", "karras", "exponential", "sgm_uniform", "simple",
    "ddim_uniform", "beta",
)


class AnimeGenerateModule(BasicGenerateModule):
    """动漫文生图模块：miaomiaoHarem v14 + 可选 LoRA 叠加。"""

    module_id = "anime_generate"
    module_version = "v1"

    def capabilities(self) -> ModuleCapabilities:
        return dataclasses.replace(
            super().capabilities(),
            module_id=self.module_id,
            title="动漫生图（多模型 / LoRA）",
            description=(
                "动漫 / 插画文生图：默认 miaomiaoHarem v14，可通过 binding v15 "
                "切换 ComfyUI 已安装底模，并叠加 0–2 条 LoRA、覆盖采样参数"
            ),
            parameters=(
                *super().capabilities().parameters,
                ParameterSpec(
                    "model",
                    "string",
                    default="",
                    title="底模",
                    description="ComfyUI /models/checkpoints 中的文件名；不传=绑定默认",
                    configurable=True,
                ),
                ParameterSpec(
                    "steps",
                    "int",
                    default=30,
                    min=1,
                    max=100,
                    title="采样步数",
                    description="KSampler steps；不传=绑定默认 30",
                    configurable=True,
                ),
                ParameterSpec(
                    "cfg",
                    "float",
                    default=4.0,
                    min=1.0,
                    max=20.0,
                    step=0.1,
                    title="CFG",
                    description="KSampler cfg；不传=绑定默认 4.0",
                    configurable=True,
                ),
                ParameterSpec(
                    "sampler_name",
                    "enum",
                    default="er_sde",
                    enum_values=SAMPLER_NAMES,
                    title="采样器",
                    description="KSampler sampler_name；不传=绑定默认 er_sde",
                    configurable=True,
                ),
                ParameterSpec(
                    "scheduler",
                    "enum",
                    default="simple",
                    enum_values=SCHEDULER_NAMES,
                    title="调度器",
                    description="KSampler scheduler；不传=绑定默认 simple",
                    configurable=True,
                ),
                ParameterSpec(
                    "denoise",
                    "float",
                    default=1.0,
                    min=0.0,
                    max=1.0,
                    step=0.01,
                    title="去噪强度",
                    description="KSampler denoise；不传=绑定默认 1.0",
                    configurable=True,
                ),
                ParameterSpec(
                    "face_detailer",
                    "bool",
                    default=True,
                    title="人脸修复（FaceDetailer）",
                    description="默认开启；关闭可显著提速，适合快速预览与大批量筛选",
                    configurable=True,
                ),
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

    @staticmethod
    def _normalize_model(raw: Any) -> str | None:
        if raw is None:
            return None
        if not isinstance(raw, str) or not raw.strip():
            raise UnprocessableError(
                "model 必须是底模文件名或 null", code="MODEL_PARAM_INVALID"
            )
        model = raw.strip()
        if "/" in model or "\\" in model:
            raise UnprocessableError(
                "model 不得包含路径，只填 ComfyUI /models/checkpoints 中的文件名",
                code="MODEL_PARAM_INVALID",
            )
        if len(model) > MODEL_MAX_LENGTH:
            raise UnprocessableError(
                f"model 最多 {MODEL_MAX_LENGTH} 个字符", code="MODEL_PARAM_INVALID"
            )
        return model

    @staticmethod
    def _normalize_sampling(config: Mapping[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        if "steps" in config and config["steps"] is not None:
            value = config["steps"]
            if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100:
                raise UnprocessableError(
                    "steps 必须是 1~100 的整数", code="SAMPLING_PARAM_INVALID"
                )
            normalized["steps"] = value
        if "cfg" in config and config["cfg"] is not None:
            value = config["cfg"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1.0 <= float(value) <= 20.0:
                raise UnprocessableError(
                    "cfg 必须是 1.0~20.0 的数字", code="SAMPLING_PARAM_INVALID"
                )
            normalized["cfg"] = float(value)
        if "denoise" in config and config["denoise"] is not None:
            value = config["denoise"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0.0 <= float(value) <= 1.0:
                raise UnprocessableError(
                    "denoise 必须是 0.0~1.0 的数字", code="SAMPLING_PARAM_INVALID"
                )
            normalized["denoise"] = float(value)
        for key, allowed in (("sampler_name", SAMPLER_NAMES), ("scheduler", SCHEDULER_NAMES)):
            if key not in config or config[key] is None:
                continue
            value = config[key]
            if not isinstance(value, str) or value not in allowed:
                raise UnprocessableError(
                    f"{key} 必须为: {', '.join(allowed)}", code="SAMPLING_PARAM_INVALID"
                )
            normalized[key] = value
        return normalized

    def _normalize_config(self, config: Mapping[str, Any]) -> dict[str, Any]:
        unknown = set(config) - MODULE_CONFIG_KEYS
        if unknown:
            raise UnprocessableError(
                f"anime_generate 不支持的 config 字段: {', '.join(sorted(unknown))}",
                code="MODULE_CONFIG_UNKNOWN",
            )
        normalized: dict[str, Any] = {}
        model = self._normalize_model(config.get("model"))
        if model is not None:
            normalized["model"] = model
        normalized.update(self._normalize_sampling(config))
        if config.get("face_detailer") is not None:
            face_detailer = config["face_detailer"]
            if not isinstance(face_detailer, bool):
                raise UnprocessableError(
                    "face_detailer 必须是布尔值", code="MODULE_CONFIG_INVALID"
                )
            normalized["face_detailer"] = face_detailer
        loras = self._normalize_loras(config.get("loras"))
        if loras:
            normalized["loras"] = loras
        return normalized

    def validate_config(self, config: Mapping[str, Any]) -> WorkflowValidation:
        self._normalize_config(config)
        return super().validate_config(config)

    def build_engine_request(
        self,
        context: JobRequestContext,
        prepared: Mapping[str, Any] | None = None,
    ):
        request = super().build_engine_request(context, prepared)
        normalized = self._normalize_config(context.module_config or {})
        if not normalized:
            return request
        parameters = dict(request.parameters)
        parameters.update(normalized)
        return dataclasses.replace(request, parameters=parameters)
