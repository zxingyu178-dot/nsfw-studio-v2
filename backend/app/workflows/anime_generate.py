"""AnimeGenerateModule — 动漫生图模块（接入 miaomiaoHarem v14 单文件 SDXL 链）。

与 ``basic_generate`` 的**标准契约完全一致**（positive/negative/width/height/seed，
size_mode=explicit，无输入槽、无处理型 Job），差异只在执行身份与 provider binding：

- ``basic_generate`` → Qwen-Image 2.1（写实 / 通用场景）；
- ``anime_generate`` → miaomiaoHarem v14（SDXL 动漫底模，CheckpointLoaderSimple，
  CLIP 与 VAE 由 checkpoint 自带；历史 v1 为 Anima 2.9B，已冻结保留）。

因此本模块直接复用 BasicGenerateModule 的标准输入 / 引擎请求构造（同一契约不重复实现），
仅覆写能力身份（module_id / 标题 / 描述）。执行链：
``anime_generate → EngineAdapter → workflows/providers/comfyui/anime_generate/v2``。
"""
from __future__ import annotations

import dataclasses

from app.workflows.base import ModuleCapabilities
from app.workflows.basic_generate import BasicGenerateModule


class AnimeGenerateModule(BasicGenerateModule):
    """动漫文生图模块：miaomiaoHarem v14（单文件 SDXL checkpoint，自带 CLIP/VAE）。"""

    module_id = "anime_generate"
    module_version = "v1"

    def capabilities(self) -> ModuleCapabilities:
        return dataclasses.replace(
            super().capabilities(),
            module_id=self.module_id,
            title="动漫生图（MiaoMiao）",
            description=(
                "动漫 / 插画文生图：miaomiaoHarem v14（SDXL 单文件底模，自带 CLIP/VAE）；"
                "写实人物请使用 basic_generate"
            ),
        )