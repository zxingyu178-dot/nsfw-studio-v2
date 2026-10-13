"""固定产品端口守卫：生产 launcher 钉死 8000、无换口、无 4173/Vite。"""
from __future__ import annotations

from pathlib import Path

from app.core.config import CONFIG_DIR

PROJECT_ROOT = CONFIG_DIR.parent
PROD_PS1 = PROJECT_ROOT / "scripts" / "launch_studio.ps1"
DEV_PS1 = PROJECT_ROOT / "scripts" / "dev" / "launch_studio_dev.ps1"


def test_prod_launcher_fixed_port_8000():
    text = PROD_PS1.read_text(encoding="utf-8")
    # 固定 8000 常量赋值（红线，禁止调用方换口）
    assert "$Port = 8000" in text or "$Port      = 8000" in text
    assert "8000" in text
    # 顶层 param 块只接受 ProjectRoot，不接受 -Port（内部端口检查辅助函数可自行使用 [int]$Port）
    top = text[: text.index("# ---- 定位项目根")]
    assert "$Port" not in top, "生产顶层参数不得暴露可换口的 -Port"


def test_prod_launcher_no_uvicorn_no_4173():
    text = PROD_PS1.read_text(encoding="utf-8").lower()
    assert "uvicorn" not in text, "生产 launcher 不再自己 Popen uvicorn"
    assert "4173" not in text, "生产链不得出现 Vite Preview 4173"
    assert "npm run preview" not in text


def test_prod_launcher_uses_controlhub_start():
    text = PROD_PS1.read_text(encoding="utf-8")
    assert "lifecycle_cli" in text
    assert "nsfw-studio-v2" in text
    # 不静默换口：Other 占用时退出码 3
    assert "exit 3" in text


def test_dev_launcher_allows_port_and_uvicorn():
    """dev 启动器才允许 -Port 与直连 uvicorn（仅供开发）。"""
    assert DEV_PS1.is_file()
    text = DEV_PS1.read_text(encoding="utf-8")
    assert "[int]$Port" in text
    assert "uvicorn" in text
    # 文件头标明禁止用于生产
    assert "禁止" in text or "生产" in text
