"""系统级业务逻辑：启动引导（数据目录 + 日志 + 数据库）。"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select

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
    system_info_created: bool = False


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
        system_info_created = _ensure_system_info(engine, settings.app.version)
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
        system_info_created=system_info_created,
    )


def _ensure_system_info(engine, version: str) -> bool:
    """system_info 无记录时写入一条；有则不动（幂等）。"""
    factory = make_session_factory(engine)
    with factory() as session:
        existing = session.execute(select(SystemInfo).order_by(SystemInfo.id)).scalars().first()
        if existing is not None:
            return False
        session.add(SystemInfo(version=version))
        session.commit()
        total = session.execute(select(func.count()).select_from(SystemInfo)).scalar_one()
        logger.info("system_info 初始化记录 version=%s（当前共 %s 条）", version, total)
        return True
