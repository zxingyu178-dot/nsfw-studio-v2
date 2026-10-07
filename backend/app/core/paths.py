"""DataRoot 目录体系（Phase 0 规范 §九）。

目录清单来自 ``configs/storage.yaml`` 的 ``storage.layout``，
本模块只负责"按清单创建"，不感知具体业务含义。
"""
from __future__ import annotations

from pathlib import Path

from app.core.config import Settings


def data_subdirs(settings: Settings) -> dict[str, Path]:
    """返回 {相对路径: 绝对路径} 映射。"""
    return {rel: settings.storage.data_root / rel for rel in settings.storage.layout}


def ensure_data_root(settings: Settings) -> set[str]:
    """创建 DataRoot 及全部登记子目录（幂等）。

    返回本次**新建**的相对路径集合；已存在的不动、不报错。
    """
    created: set[str] = set()
    for rel, path in data_subdirs(settings).items():
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.add(rel)
    return created
