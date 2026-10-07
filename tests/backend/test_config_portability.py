"""DataRoot 可移植性（Phase 0.1 验收：默认路径不得绑定特定机器盘符）。"""
from __future__ import annotations

from pathlib import Path

from app.core.config import DEFAULT_DATA_ROOT, ENV_DATA_ROOT, load_settings


def test_default_data_root_is_portable():
    """代码默认值必须基于当前用户目录，而不是某台机器的 D:/ 盘。"""
    assert DEFAULT_DATA_ROOT == Path.home() / "NSFW-Studio-Data"
    assert Path("D:/NSFW-Studio-Data") != DEFAULT_DATA_ROOT  # 防回归哨兵


def test_env_var_overrides_data_root(tmp_path, monkeypatch):
    custom = tmp_path / "custom-root"
    monkeypatch.setenv(ENV_DATA_ROOT, str(custom))
    assert load_settings().storage.data_root == custom


def test_config_file_overrides_data_root(tmp_path):
    (tmp_path / "config.yaml").write_text(
        'data_root: "Y:/from-config-file"\n', encoding="utf-8"
    )
    settings = load_settings(config_dir=tmp_path)
    assert settings.storage.data_root == Path("Y:/from-config-file")


def test_env_var_beats_config_file(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text('data_root: "Y:/from-file"\n', encoding="utf-8")
    monkeypatch.setenv(ENV_DATA_ROOT, "Z:/from-env")
    assert load_settings(config_dir=tmp_path).storage.data_root == Path("Z:/from-env")
