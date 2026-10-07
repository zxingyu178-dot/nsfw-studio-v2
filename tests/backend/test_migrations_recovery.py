"""迁移失败恢复（Phase 0.1 验收：failed 不得被视为 applied，修复后可重试）。"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.database import migrations as migrations_module
from app.database.base import init_database, make_engine
from app.database.migrations import Migration, applied_migration_ids


def _patched(monkeypatch: pytest.MonkeyPatch, *migrations: Migration) -> None:
    monkeypatch.setattr(migrations_module, "MIGRATIONS", tuple(migrations))


BAD = Migration(
    migration_id="0002_phase01_marker",
    version="0.1.1",
    description="模拟执行失败的迁移",
    statements=("INSERT INTO no_such_table_phase01 VALUES (1)",),
)
GOOD = Migration(
    migration_id="0002_phase01_marker",
    version="0.1.1",
    description="修复后的迁移（同一 ID，合法 SQL）",
    statements=("CREATE TABLE phase01_marker (id INTEGER PRIMARY KEY)",),
)


def test_failed_migration_recovery(settings, monkeypatch):
    """规范场景：失败 → 记录 failed → 下次启动仍视为未完成 → 修复后重试 → 状态正确。"""
    engine = make_engine(settings.storage.database_path)

    # 1) 执行失败：抛出并记录 failed
    _patched(monkeypatch, BAD)
    with pytest.raises(Exception):
        init_database(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT migration_id, status FROM migration WHERE migration_id = '0002_phase01_marker'")
        ).fetchall()
    assert rows == [("0002_phase01_marker", "failed")]

    # 2) 下次启动：failed 不算已完成，仍会被识别为未完成并再次尝试（再次失败）
    assert "0002_phase01_marker" not in applied_migration_ids(engine)
    _patched(monkeypatch, BAD)
    with pytest.raises(Exception):
        init_database(engine)

    # 3) 修复后（同一 migration_id 换成合法 SQL）：重新执行成功
    _patched(monkeypatch, GOOD)
    applied = init_database(engine)
    assert [m.migration_id for m in applied] == ["0002_phase01_marker"]

    # 4) 最终状态正确：applied、且无主键冲突残留（同一 id 只有一条记录）
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT migration_id, status FROM migration WHERE migration_id = '0002_phase01_marker'")
        ).fetchall()
        marker = conn.execute(text("SELECT count(*) FROM phase01_marker")).scalar_one()
    assert rows == [("0002_phase01_marker", "applied")]
    assert marker == 0
    assert "0002_phase01_marker" in applied_migration_ids(engine)
    engine.dispose()


def test_only_applied_status_counts(settings):
    """手工写入 failed 记录时，applied_migration_ids 不得把它算作已完成。"""
    engine = make_engine(settings.storage.database_path)
    init_database(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO migration (migration_id, version, time, status) "
                "VALUES ('9999_fake', '0.0.0', '2026-01-01T00:00:00', 'failed')"
            )
        )
    ids = applied_migration_ids(engine)
    assert "0001_initial_schema" in ids
    assert "9999_fake" not in ids
    engine.dispose()
