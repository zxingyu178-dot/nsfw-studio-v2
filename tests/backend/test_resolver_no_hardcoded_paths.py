"""路径去硬编码 + resolver 合同测试（v0.14.1 Patch Hardening，A 路 / 任务2）。

跨平台、只读文本断言（绝不执行 .ps1/.bat），可在 Ubuntu CI 直接跑。锁定：
- stop / launch 均 dot-source resolve_aihome.ps1；
- stop / launch / resolver 正文无任何写死的机器完整路径（D:\\control-hub、C:\\Users 等）；
- resolver 暴露 AIHOME_ROOT / CONTROLHUB_ROOT / CONTROLHUB_PYTHON / CONTROLHUB_DATA_ROOT，
  且失败时不静默继续（Ok=$false / Error / throw）；
- stop_studio.bat 透传 ERRORLEVEL（exit /b %ERRORLEVEL%）。
"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.config import CONFIG_DIR

PROJECT_ROOT = CONFIG_DIR.parent
SCRIPTS = PROJECT_ROOT / "scripts"
STOP_PS1 = SCRIPTS / "stop_studio.ps1"
STOP_BAT = SCRIPTS / "stop_studio.bat"
LAUNCH_PS1 = SCRIPTS / "launch_studio.ps1"
RESOLVER_PS1 = SCRIPTS / "runtime" / "resolve_aihome.ps1"


def _text(p: Path) -> str:
    assert p.is_file(), f"缺少文件: {p}"
    return p.read_text(encoding="utf-8")


def test_resolver_exists():
    assert RESOLVER_PS1.is_file(), "必须新增 scripts/runtime/resolve_aihome.ps1"


def test_launcher_and_stop_dot_source_resolver():
    for p in (STOP_PS1, LAUNCH_PS1):
        text = _text(p)
        assert "resolve_aihome.ps1" in text, f"{p.name} 必须 dot-source resolve_aihome.ps1"


def test_no_hardcoded_machine_paths():
    bad_patterns = ["D:\\control-hub", "C:\\Users", "D:\\AIHome"]
    for p in (STOP_PS1, LAUNCH_PS1, RESOLVER_PS1):
        text = _text(p)
        low = text.lower()
        for bad in bad_patterns:
            assert bad.lower() not in low, f"{p.name} 含写死的机器路径 {bad!r}"


def test_resolver_exposes_expected_variables():
    text = _text(RESOLVER_PS1)
    for var in ("AIHOME_ROOT", "CONTROLHUB_ROOT", "CONTROLHUB_PYTHON", "CONTROLHUB_DATA_ROOT"):
        assert var in text, f"resolver 未暴露 {var}"
    assert "Get-AIHomeEnv" in text
    # 失败语义：Ok=$false 且不静默继续（throw 或 Error 字段）
    assert "Ok" in text
    assert ("throw" in text.lower()) or ("Error" in text)


def test_bat_propagates_errorlevel():
    text = _text(STOP_BAT)
    assert re.search(r"exit\s+/b\s+%ERRORLEVEL%", text), (
        "stop_studio.bat 必须用 'exit /b %ERRORLEVEL%' 透传 PowerShell 退出码"
    )
