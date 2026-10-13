"""安全守卫：停止脚本严禁按通配名杀 python / node（不误杀无关进程）。"""
from __future__ import annotations

from pathlib import Path

from app.core.config import CONFIG_DIR

PROJECT_ROOT = CONFIG_DIR.parent
SCRIPTS = [
    PROJECT_ROOT / "scripts" / "stop_studio.ps1",
    PROJECT_ROOT / "scripts" / "stop_studio.bat",
]

# 禁用的杀进程形态（大小写不敏感匹配）
FORBIDDEN = [
    "taskkill",
    "stop-process",
    "/im python",
    "/im node",
    "stop-service",
]


def test_stop_scripts_do_not_kill_unrelated_processes():
    for path in SCRIPTS:
        assert path.is_file(), f"缺少脚本: {path}"
        text = path.read_text(encoding="utf-8").lower()
        for bad in FORBIDDEN:
            assert bad not in text, (
                f"{path.name} 含禁止的杀进程形态 '{bad}'："
                "停止脚本只允许经 ControlHub lifecycle CLI + Studio 已知 runtime 停止，"
                "严禁 taskkill /IM python、Stop-Process -Name python/node 等通配杀进程。"
            )
