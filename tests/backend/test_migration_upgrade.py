"""数据库升级路径：v0.1.2 库 → Phase 1 migration → 正常打开（规范 §三十、§六十二）。"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.database import migrations as migrations_module
from app.database.base import init_database, make_engine, make_session_factory
from app.database.migrations import Migration


def test_upgrade_from_v012_database(settings, monkeypatch):
    """模拟 v0.1.2 数据库（只有 0001）→ 应用 Phase 1 迁移 → 数据保留且新表可用。"""
    engine = make_engine(settings.storage.database_path)

    # 1) 构造 v0.1.2 状态：仅应用 0001
    original_migrations = migrations_module.MIGRATIONS
    monkeypatch.setattr(
        migrations_module, "MIGRATIONS",
        (Migration(
            migration_id="0001_initial_schema", version="0.1.0",
            description="仅 0001", statements=(original_migrations[0].statements[0],),
        ),),
    )
    init_database(engine)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO system_info (id, version, created_time, updated_time) VALUES (1, '0.1.2', 't', 't')")
        )

    # 2) 升级：恢复完整迁移列表 → 应用 0002-0004
    monkeypatch.setattr(migrations_module, "MIGRATIONS", original_migrations)
    applied = init_database(engine)
    assert [m.migration_id for m in applied] == ["0002_prompt", "0003_asset", "0004_recipe", "0005_job"]

    # 3) 旧数据仍在 + 新表可写
    with engine.begin() as conn:
        assert conn.execute(text("SELECT version FROM system_info")).scalar_one() == "0.1.2"
        conn.execute(text(
            "INSERT INTO prompts (id, name, favorite, archived, created_at, updated_at) "
            "VALUES ('prm_up', '升级后创建', 0, 0, 't', 't')"
        ))
        conn.execute(text(
            "INSERT INTO prompt_versions (id, prompt_id, version_no, mode, created_at) "
            "VALUES ('prmv_up', 'prm_up', 1, 'full', 't')"
        ))
        conn.execute(text("UPDATE prompts SET current_version_id = 'prmv_up' WHERE id = 'prm_up'"))

    # 4) FK / CHECK / UNIQUE 约束生效（各自独立事务，失败不互相污染）
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO prompt_versions (id, prompt_id, version_no, mode, created_at) "
                "VALUES ('prmv_orphan', 'prm_missing', 1, 'full', 't')"
            ))

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO assets (id, type, name, created_at, updated_at) VALUES ('ast_bad', 'wallpaper', 'x', 't', 't')"
            ))

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO prompt_versions (id, prompt_id, version_no, mode, created_at) "
                "VALUES ('prmv_badmode', 'prm_up', 9, 'weird', 't')"
            ))

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO prompt_versions (id, prompt_id, version_no, mode, created_at) "
                "VALUES ('prmv_dup', 'prm_up', 1, 'full', 't')"
            ))

    # 5) ORM 层可正常读写（应用层打开正常）
    from app.models import Prompt

    with make_session_factory(engine)() as session:
        prompt = session.get(Prompt, "prm_up")
        assert prompt is not None and prompt.name == "升级后创建"
        assert prompt.current_version_id == "prmv_up"
    engine.dispose()
