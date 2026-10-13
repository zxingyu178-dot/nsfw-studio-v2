"""旧 start_studio.bat 必须是纯 LEGACY SHIM（只转发，不含自己的 uvicorn/4173）。"""
from __future__ import annotations

from pathlib import Path

from app.core.config import CONFIG_DIR

PROJECT_ROOT = CONFIG_DIR.parent
BAT = PROJECT_ROOT / "scripts" / "start_studio.bat"


def test_start_studio_bat_forwards_to_launcher():
    assert BAT.is_file()
    text = BAT.read_text(encoding="utf-8")
    assert "launch_studio" in text, "legacy shim 必须转发到 launch_studio"


def test_start_studio_bat_has_no_own_server_chain():
    text = BAT.read_text(encoding="utf-8").lower()
    assert "uvicorn" not in text
    assert "4173" not in text
    assert "npm run preview" not in text
    assert "app.main:app" not in text
