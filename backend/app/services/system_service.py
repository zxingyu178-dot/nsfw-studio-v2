"""系统级业务逻辑：启动引导（数据目录 + 日志 + 数据库）与只读系统状态摘要。"""
from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.logging import setup_logging
from app.core.paths import ensure_data_root
from app.database.base import init_database, make_engine, make_session_factory
from app.models.image import Image
from app.models.image_variant import ImageVariant
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


def _latest_applied_migration(session: Session) -> str | None:
    """migration 表中最新一条 status='applied' 的 migration_id（无记录则 None）。"""
    return session.execute(
        text("SELECT migration_id FROM migration WHERE status = 'applied' "
             "ORDER BY migration_id DESC LIMIT 1")
    ).scalar()


def collect_system_status(session: Session, settings: Settings, engine_runtime) -> dict[str, Any]:
    """只读系统状态摘要（Phase 0.12 Task7 / Settings 系统维护中心）。

    - 绝不返回任何敏感配置内容（token / 密码 / config.local）；
    - database_size 用 os.stat；磁盘用量用 shutil.disk_usage（跨平台，同 jobs.check_disk_space）；
    - thumbnail_count / preview_count 从 image_variants 按 variant_type 计数；
    - engine_runtime 复用现有 EngineRuntimeService 状态摘要（不写第二套）。
    """
    database_path = settings.storage.database_path
    try:
        database_size = os.stat(database_path).st_size if database_path.is_file() else 0
    except OSError:
        database_size = 0

    data_root = settings.storage.data_root
    try:
        disk = shutil.disk_usage(data_root)
        disk_total, disk_free = disk.total, disk.free
    except OSError:
        disk_total, disk_free = 0, 0

    image_count = int(session.execute(select(func.count()).select_from(Image)).scalar_one())

    def _variant_count(variant_type: str) -> int:
        return int(session.execute(
            select(func.count()).select_from(ImageVariant)
            .where(ImageVariant.variant_type == variant_type)
        ).scalar_one())

    runtime_summary: dict[str, Any] = {}
    if engine_runtime is not None:
        try:
            runtime_summary = engine_runtime.status().to_dict()
        except Exception:  # noqa: BLE001 —— 状态摘要失败不得拖垮整个只读端点
            logger.warning("采集 engine_runtime 状态失败（忽略）", exc_info=True)
            runtime_summary = {"state": "UNKNOWN"}

    return {
        "app_version": settings.app.version,
        "data_root": str(data_root),
        "database_path": str(database_path),
        "database_size": database_size,
        "disk_total": disk_total,
        "disk_free": disk_free,
        "image_count": image_count,
        "thumbnail_count": _variant_count("thumbnail"),
        "preview_count": _variant_count("preview"),
        "latest_migration": _latest_applied_migration(session),
        "engine_runtime": runtime_summary,
    }
