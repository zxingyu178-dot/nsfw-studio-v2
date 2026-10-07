"""system_info 版本语义（Phase 0.1 收口：version 表示**当前应用版本**）。"""
from __future__ import annotations

import dataclasses

from sqlalchemy import text


def test_system_info_tracks_current_app_version(settings):
    from app.database.base import make_engine
    from app.services.system_service import bootstrap

    report = bootstrap(settings)
    assert report.system_info_action == "created"

    # 模拟应用升级：版本变化后再次引导，system_info.version 必须同步更新
    upgraded = dataclasses.replace(
        settings,
        app=dataclasses.replace(settings.app, version="9.9.9-test"),
    )
    report2 = bootstrap(upgraded)
    assert report2.system_info_action == "updated"

    engine = make_engine(settings.storage.database_path)
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT version FROM system_info")).fetchall()
    finally:
        engine.dispose()
    assert rows == [("9.9.9-test",)], "版本升级后 system_info 必须更新为当前应用版本"


def test_system_info_unchanged_when_same_version(settings):
    from app.services.system_service import bootstrap

    bootstrap(settings)
    report = bootstrap(settings)
    assert report.system_info_action == "unchanged"
