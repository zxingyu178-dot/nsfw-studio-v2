"""配置加载（Phase 0 规范 §八、§十二）。

原则：
- 一切路径来自 ``configs/*.yaml``，代码中禁止写死路径；
- DataRoot 可用环境变量 ``NSFW_STUDIO_DATA_ROOT`` 覆盖（测试用临时目录即依赖此机制）；
- 配置文件缺失时回落到内置默认值，保证最小可启动。
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# backend/app/core/config.py -> parents: [core, app, backend, 项目根]
PROJECT_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = PROJECT_ROOT / "configs"

# 规范 §八：默认 DataRoot（可被 config.yaml / 环境变量覆盖）
DEFAULT_DATA_ROOT = Path("D:/NSFW-Studio-Data")

ENV_DATA_ROOT = "NSFW_STUDIO_DATA_ROOT"
ENV_HOST = "NSFW_STUDIO_HOST"
ENV_PORT = "NSFW_STUDIO_PORT"

# 规范 §九：DataRoot 默认目录布局（storage.yaml 缺失时的兜底）
DEFAULT_LAYOUT: tuple[str, ...] = (
    "database",
    "images/originals",
    "images/upscaled",
    "images/processed",
    "images/temp",
    "assets/face",
    "assets/clothing",
    "assets/pose",
    "assets/scene",
    "imports",
    "exports",
    "cache",
    "logs/app",
    "logs/jobs",
    "logs/errors",
)


@dataclass(frozen=True)
class AppConfig:
    name: str = "NSFW Studio"
    version: str = "0.1.0"
    host: str = "127.0.0.1"
    port: int = 8000
    debug: bool = False
    log_level: str = "INFO"


@dataclass(frozen=True)
class StorageConfig:
    data_root: Path
    layout: tuple[str, ...] = DEFAULT_LAYOUT
    database_filename: str = "studio.db"

    @property
    def database_path(self) -> Path:
        return self.data_root / "database" / self.database_filename


@dataclass(frozen=True)
class WorkflowConfig:
    """workflow.yaml 的原始内容，Phase 0 只透传，不做解释。"""

    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Settings:
    app: AppConfig
    storage: StorageConfig
    workflow: WorkflowConfig
    config_dir: Path


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误（顶层应为映射）: {path}")
    return data


def load_settings(config_dir: Path | None = None) -> Settings:
    """读取 configs/ 下全部配置并合并环境变量覆盖。"""
    cfg_dir = Path(config_dir) if config_dir is not None else CONFIG_DIR

    global_cfg = _read_yaml(cfg_dir / "config.yaml")
    app_file = _read_yaml(cfg_dir / "app.yaml")
    storage_cfg = _read_yaml(cfg_dir / "storage.yaml").get("storage", {})
    workflow_cfg = _read_yaml(cfg_dir / "workflow.yaml").get("workflow", {})

    app_cfg = app_file.get("app", {})
    logging_cfg = app_file.get("logging", {})

    data_root = os.environ.get(ENV_DATA_ROOT) or global_cfg.get("data_root") or str(DEFAULT_DATA_ROOT)

    app = AppConfig(
        name=str(app_cfg.get("name", "NSFW Studio")),
        version=str(app_cfg.get("version", "0.1.0")),
        host=str(os.environ.get(ENV_HOST) or app_cfg.get("host", "127.0.0.1")),
        port=int(os.environ.get(ENV_PORT) or app_cfg.get("port", 8000)),
        debug=bool(app_cfg.get("debug", False)),
        log_level=str(logging_cfg.get("level", "INFO")),
    )

    layout_raw = storage_cfg.get("layout", DEFAULT_LAYOUT)
    storage = StorageConfig(
        data_root=Path(str(data_root)),
        layout=tuple(str(item) for item in layout_raw),
        database_filename=str(storage_cfg.get("database_filename", "studio.db")),
    )

    return Settings(
        app=app,
        storage=storage,
        workflow=WorkflowConfig(raw=workflow_cfg),
        config_dir=cfg_dir,
    )
