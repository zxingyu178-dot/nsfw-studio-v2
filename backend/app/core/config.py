"""配置加载（Phase 0 规范 §八、§十二；0.1 可移植性；0.1.1 本机配置分层）。

原则：
- 一切路径来自 ``configs/*.yaml``；代码默认值必须可移植（基于用户目录），
  不得把某台机器的盘符作为不可移植硬默认；
- 覆盖优先级（固定）::

    NSFW_STUDIO_DATA_ROOT（环境变量）
      > configs/config.local.yaml（本机私有配置，已 gitignore，不提交）
        > configs/config.yaml（公共模板，机器无关）
          > 代码默认 Path.home()/NSFW-Studio-Data

- 配置文件缺失时回落到下一层，保证最小可启动。
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

# 代码默认 DataRoot：基于当前用户目录（可移植）。
# 机器差异（如使用 D 盘）只写在 config.local.yaml（gitignore）或环境变量中。
DEFAULT_DATA_ROOT = Path.home() / "NSFW-Studio-Data"

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
    "backups",
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
    # 磁盘空间告警阈值（Phase 2 规范 §五十七）
    min_free_bytes_warning: int = 5 * 1024**3   # 5 GB：低空间警告
    min_free_bytes_severe: int = 1 * 1024**3    # 1 GB：严重不足，拒绝新任务

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
    comfyui: dict[str, Any] = field(default_factory=dict)  # 本机 ComfyUI 配置（config.local.yaml）


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(f"配置文件格式错误（顶层应为映射）: {path}")
    return data


def load_settings(config_dir: Path | None = None) -> Settings:
    """读取 configs/ 下全部配置并合并（local 覆盖公共，环境变量最高）。"""
    cfg_dir = Path(config_dir) if config_dir is not None else CONFIG_DIR

    global_cfg = _read_yaml(cfg_dir / "config.yaml")
    # 本机私有配置（config.local.yaml，gitignore）：按键覆盖公共模板
    local_cfg = _read_yaml(cfg_dir / "config.local.yaml")
    merged_cfg: dict[str, Any] = {**global_cfg, **local_cfg}

    app_file = _read_yaml(cfg_dir / "app.yaml")
    storage_cfg = _read_yaml(cfg_dir / "storage.yaml").get("storage", {})
    workflow_cfg = _read_yaml(cfg_dir / "workflow.yaml").get("workflow", {})

    app_cfg = app_file.get("app", {})
    logging_cfg = app_file.get("logging", {})

    data_root = os.environ.get(ENV_DATA_ROOT) or merged_cfg.get("data_root") or str(DEFAULT_DATA_ROOT)

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
        min_free_bytes_warning=int(storage_cfg.get("min_free_bytes_warning", 5 * 1024**3)),
        min_free_bytes_severe=int(storage_cfg.get("min_free_bytes_severe", 1 * 1024**3)),
    )

    return Settings(
        app=app,
        storage=storage,
        workflow=WorkflowConfig(raw=workflow_cfg),
        config_dir=cfg_dir,
        comfyui=merged_cfg.get("comfyui", {}) or {},
    )
