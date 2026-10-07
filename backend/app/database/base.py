"""数据库基础设施：Base、引擎工厂、初始化入口（Phase 0.1 收口）。

make_engine() 统一配置 SQLite 基础规范：
- ``journal_mode=WAL``：读写并发友好；
- ``busy_timeout=5000``：写锁等待 5 秒，缓解偶发 database is locked；
- ``foreign_keys=ON``：启用外键约束（SQLite 默认关闭）。
"""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.database.migrations import Migration, apply_pending_migrations

SQLITE_BUSY_TIMEOUT_MS = 5000


class Base(DeclarativeBase):
    """全局声明基类；Phase 1 的业务模型（Job / Prompt / Asset / Image 等）都继承这里。"""


def make_engine(database_path: Path) -> Engine:
    """按路径创建 SQLite 引擎（父目录自动创建，连接统一应用基础 PRAGMA）。"""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{database_path.as_posix()}",
        connect_args={"check_same_thread": False},  # FastAPI 线程池中使用
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _configure_sqlite(dbapi_connection, connection_record):  # noqa: ANN001 - SQLAlchemy 签名
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_database(engine: Engine) -> list[Migration]:
    """建 ``migration`` 表并应用全部未执行迁移（幂等；failed 迁移视为未完成会重试）。"""
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
