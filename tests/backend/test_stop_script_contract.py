"""一键停止脚本合同测试（读 stop_studio.ps1 文本断言，绝不执行）。"""
from __future__ import annotations

from pathlib import Path

from app.core.config import CONFIG_DIR

PROJECT_ROOT = CONFIG_DIR.parent
STOP_PS1 = PROJECT_ROOT / "scripts" / "stop_studio.ps1"


def _text() -> str:
    return STOP_PS1.read_text(encoding="utf-8")


def test_stop_script_exists():
    assert STOP_PS1.is_file(), "必须存在 scripts/stop_studio.ps1"


def test_four_step_order_and_contents():
    text = _text()
    i1 = text.index("[1/4]")
    i2 = text.index("[2/4]")
    i3 = text.index("[3/4]")
    i4 = text.index("[4/4]")
    # 顺序：队列暂停 → Mobile Bridge → nsfw-studio-v2 → comfyui
    assert i1 < i2 < i3 < i4

    # 各步内容
    assert "queue/pause" in text            # [1/4]
    assert "mobile-review/runtime/stop" in text  # [2/4]
    assert "nsfw-studio-v2" in text          # [3/4]
    assert "comfyui" in text                 # [4/4]
    # lifecycle CLI 调用
    assert "lifecycle_cli" in text


def test_three_port_verification():
    text = _text()
    for port in (8000, 8767, 8188):
        assert str(port) in text


def test_status_literals_present():
    text = _text()
    assert "FREE" in text
    assert "EXTERNAL_NOT_OWNED" in text
    assert "STOP_TIMEOUT" in text
