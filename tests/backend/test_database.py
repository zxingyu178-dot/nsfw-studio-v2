"""SQLite 初始化与迁移框架（Phase 0 规范 §十）。"""
from __future__ import annotations

from sqlalchemy import text


def test_database_initialized(settings):
    from app.database.base import make_engine
    from app.services.system_service import bootstrap

    bootstrap(settings)

    db_path = settings.storage.database_path
    assert db_path.exists(), f"数据库未创建: {db_path}"

    engine = make_engine(db_path)
    try:
        with engine.connect() as conn:
            migrations = conn.execute(
                text("SELECT migration_id, status FROM migration ORDER BY migration_id")
            ).fetchall()
            info = conn.execute(text("SELECT version FROM system_info")).fetchall()
    finally:
        engine.dispose()

    assert ("0001_initial_schema", "applied") in migrations
    assert info and info[0][0] == "0.1.0"


def test_system_info_not_duplicated(settings):
    from sqlalchemy import func, select

    from app.database.base import make_engine, make_session_factory
    from app.models.system import SystemInfo
    from app.services.system_service import bootstrap

    bootstrap(settings)
    bootstrap(settings)

    engine = make_engine(settings.storage.database_path)
    try:
        with make_session_factory(engine)() as session:
            total = session.execute(select(func.count()).select_from(SystemInfo)).scalar_one()
    finally:
        engine.dispose()
    assert total == 1


def test_migrations_idempotent(settings):
    from app.database.base import init_database, make_engine
    from app.services.system_service import bootstrap

    bootstrap(settings)
    engine = make_engine(settings.storage.database_path)
    try:
        assert init_database(engine) == [], "重复初始化不应再应用迁移"
    finally:
        engine.dispose()
