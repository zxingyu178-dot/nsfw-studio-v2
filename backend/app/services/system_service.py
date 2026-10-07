"""系统级业务逻辑：启动引导（数据目录 + 日志 + 数据库）。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import select

from app.core.config import Settings
from app.core.logging import setup_logging
from app.core.paths import ensure_data_root
from app.database.base import init_database, make_engine, make_session_factory
from app.models.system import SystemInfo

logger = logging.getLogger(__name__)


@dataclass
class BootstrapReport:
    data_root: Path
    database_path: Path
    created_dirs: set[str] = field(default_factory=set)
    applied_migrations: list[str] = field(default_factory=list)
    # system_info 动作：created（首建）/ updated（应用版本变化）/ unchanged
    system_info_action: str = "unchanged"


def bootstrap(settings: Settings) -> BootstrapReport:
    """启动引导（幂等）：创建数据目录 → 初始化日志 → 初始化数据库 → 写入 system_info。"""
    created = ensure_data_root(settings)
    setup_logging(settings.storage.data_root, console_level=settings.app.log_level)
    logger.info("启动引导开始 data_root=%s 新建目录=%s", settings.storage.data_root, sorted(created) or "无")

    database_path = settings.storage.database_path
    engine = make_engine(database_path)
    try:
        applied = init_database(engine)
        for migration in applied:
            logger.info("数据库迁移完成 %s -> %s", migration.migration_id, migration.version)
        system_info_action = _ensure_system_info(engine, settings.app.version)
    finally:
        engine.dispose()

    if created:
        logger.info("DataRoot 初始化完成，共新建 %s 个目录", len(created))
    logger.info("启动引导完成 database=%s", database_path)
    return BootstrapReport(
        data_root=settings.storage.data_root,
        database_path=database_path,
        created_dirs=created,
        applied_migrations=[m.migration_id for m in applied],
        system_info_action=system_info_action,
    )


def _ensure_system_info(engine, version: str) -> str:
    """system_info.version 语义：**当前应用版本**（非首次创建版本）。

    无记录 → 写入（created）；记录版本与当前应用版本不一致 → 更新（updated，
    updated_time 自动刷新）；一致 → 不动（unchanged）。
    """
    factory = make_session_factory(engine)
    with factory() as session:
        existing = session.execute(select(SystemInfo).order_by(SystemInfo.id)).scalars().first()
        if existing is None:
            session.add(SystemInfo(version=version))
            session.commit()
            logger.info("system_info 初始化 version=%s", version)
            return "created"
        if existing.version != version:
            logger.info("system_info 版本更新 %s -> %s", existing.version, version)
            existing.version = version  # onupdate 自动刷新 updated_time
            session.commit()
            return "updated"
        return "unchanged"
