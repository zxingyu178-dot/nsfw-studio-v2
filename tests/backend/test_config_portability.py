"""DataRoot 可移植性与配置优先级链（Phase 0.1 / 0.1.1 收口）。

优先级（固定）：环境变量 > config.local.yaml > config.yaml > Path.home() 默认。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from app.core.config import CONFIG_DIR, DEFAULT_DATA_ROOT, ENV_DATA_ROOT, load_settings


def test_default_data_root_is_portable():
    """代码默认值必须基于当前用户目录，而不是某台机器的盘。"""
    assert DEFAULT_DATA_ROOT == Path.home() / "NSFW-Studio-Data"


def test_repo_public_config_is_machine_independent():
    """公共 config.yaml 不得携带机器特定配置（防回归哨兵，Phase 0.1.1）。"""
    raw = (CONFIG_DIR / "config.yaml").read_text(encoding="utf-8")
    assert "D:/" not in raw, "公共模板不得出现机器盘符"
    parsed = yaml.safe_load(raw) or {}
    assert "data_root" not in parsed, "公共模板不得设置 data_root（留给本机 local 配置）"


def test_no_config_falls_back_to_portable_default(tmp_path, monkeypatch):
    """无任何配置（无环境变量 / 无 local / 无模板设置）→ 用户目录默认。"""
    monkeypatch.delenv(ENV_DATA_ROOT, raising=False)
    settings = load_settings(config_dir=tmp_path)  # 空目录：三层配置全部缺失
    assert settings.storage.data_root == Path.home() / "NSFW-Studio-Data"


def test_base_config_overrides_default(tmp_path, monkeypatch):
    monkeypatch.delenv(ENV_DATA_ROOT, raising=False)
    (tmp_path / "config.yaml").write_text('data_root: "Y:/from-config-file"\n', encoding="utf-8")
    assert load_settings(config_dir=tmp_path).storage.data_root == Path("Y:/from-config-file")


def test_local_config_overrides_base_config(tmp_path, monkeypatch):
    """存在本机 local 配置时覆盖公共模板（Phase 0.1.1）。"""
    monkeypatch.delenv(ENV_DATA_ROOT, raising=False)
    (tmp_path / "config.yaml").write_text('data_root: "Y:/from-base"\n', encoding="utf-8")
    (tmp_path / "config.local.yaml").write_text('data_root: "L:/from-local"\n', encoding="utf-8")
    assert load_settings(config_dir=tmp_path).storage.data_root == Path("L:/from-local")


def test_env_var_beats_all_config_layers(tmp_path, monkeypatch):
    """环境变量最高优先级（同时存在 base 与 local 配置时仍然生效）。"""
    (tmp_path / "config.yaml").write_text('data_root: "Y:/from-base"\n', encoding="utf-8")
    (tmp_path / "config.local.yaml").write_text('data_root: "L:/from-local"\n', encoding="utf-8")
    monkeypatch.setenv(ENV_DATA_ROOT, "Z:/from-env")
    assert load_settings(config_dir=tmp_path).storage.data_root == Path("Z:/from-env")


def test_local_config_is_gitignored():
    """config.local.yaml 必须被 .gitignore 覆盖（防误提交机器路径）。

    Phase 2.1 §十：断言基于 .gitignore 文本本身，不依赖 Git 元数据——
    Handoff ZIP 解压后（无 .git）也必须能独立跑通快速测试。
    """
    project_root = CONFIG_DIR.parents[0]
    gitignore_text = (project_root / ".gitignore").read_text(encoding="utf-8")
    patterns = [
        line.strip() for line in gitignore_text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    required = {"*.local.yaml", "configs/config.local.yaml"}
    assert required & set(patterns), \
        f".gitignore 必须以文本规则覆盖本机私有配置（当前规则: {patterns}）"

    # 仓库环境（存在 .git）下再做一次真实核对；ZIP 解压环境自动跳过 git 命令
    if (project_root / ".git").exists():
        import subprocess

        result = subprocess.run(
            ["git", "check-ignore", "-v", "configs/config.local.yaml"],
            capture_output=True, text=True, cwd=project_root,
        )
        assert result.returncode == 0, "configs/config.local.yaml 应被 .gitignore 覆盖"
