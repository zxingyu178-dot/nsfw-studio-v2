"""数据库基础设施：Base、引擎工厂、初始化入口。"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.database.migrations import Migration, apply_pending_migrations


class Base(DeclarativeBase):
    """全局声明基类；Phase 1 的业务模型（Job / Prompt / Asset / Image 等）都继承这里。"""


def make_engine(database_path: Path) -> Engine:
    """按路径创建 SQLite 引擎（父目录自动创建）。"""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},  # FastAPI 线程池中使用
        future=True,
    )


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_database(engine: Engine) -> list[Migration]:
    """建 ``migration`` 表并应用全部未执行迁移（幂等）。"""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS migration (
                    migration_id TEXT PRIMARY KEY,
                    version      TEXT NOT NULL,
                    time         TEXT NOT NULL,
                    status       TEXT NOT NULL
                )
                """
            )
        )
    return apply_pending_migrations(engine)
