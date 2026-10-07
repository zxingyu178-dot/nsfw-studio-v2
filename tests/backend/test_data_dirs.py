"""DataRoot 目录体系（Phase 0 规范 §九）。"""
from __future__ import annotations

EXPECTED_DIRS = [
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
]


def test_bootstrap_creates_full_layout(settings):
    from app.services.system_service import bootstrap

    report = bootstrap(settings)
    root = settings.storage.data_root
    for rel in EXPECTED_DIRS:
        assert (root / rel).is_dir(), f"缺少目录: {rel}"
    assert report.data_root == root


def test_bootstrap_is_idempotent(settings):
    from app.services.system_service import bootstrap

    first = bootstrap(settings)
    second = bootstrap(settings)
    assert len(first.created_dirs) == len(EXPECTED_DIRS)
    assert second.created_dirs == set(), "二次引导不应再新建目录"


def test_storage_manager_whitelist(settings):
    import pytest

    from app.core.errors import ValidationError
    from app.storage import StorageManager

    manager = StorageManager(settings)
    assert manager.path("database") == settings.storage.data_root / "database"
    with pytest.raises(ValidationError):
        manager.path("../escape")
