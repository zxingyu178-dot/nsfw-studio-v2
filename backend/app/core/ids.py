"""统一业务 ID 规范（Phase 1 规范 §四）。

格式：``<前缀>_<uuid4>``，数据库使用 TEXT PRIMARY KEY，
不依赖数据库自增整数作为外部业务 ID。

已分配前缀：
- prm_ / prmv_  Prompt / PromptVersion
- ast_ / astv_  Asset / AssetVersion
- rcp_ / rcpv_  Recipe / RecipeVersion
- job_ / item_ / img_  （未来 Job / JobItem / Image）
"""
from __future__ import annotations

import uuid

PROMPT = "prm"
PROMPT_VERSION = "prmv"
ASSET = "ast"
ASSET_VERSION = "astv"
RECIPE = "rcp"
RECIPE_VERSION = "rcpv"
JOB = "job"
JOB_ITEM = "item"
IMAGE = "img"


def new_id(prefix: str) -> str:
    """生成带前缀的 uuid4 业务 ID，例如 ``prm_1f0e...``。"""
    return f"{prefix}_{uuid.uuid4()}"
