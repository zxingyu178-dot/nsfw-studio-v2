"""一键停止退出码合同测试（v0.14.1 Patch Hardening，A 路 / 任务1）。

跨平台、只读文本断言（绝不执行 .ps1），可在 Ubuntu CI 直接跑。锁定：
- stop_studio.ps1 不再"无条件 exit 0"，最终退出由变量 $exitCode 驱动；
- 决策模块 stop_decision.ps1 提供退出码 0/10-15 与分支；
- 决策优先级 14 > 15 > 13 > 12 > 10 > 11 > 0；
- 逐目标结果行（STOPPED / EXTERNAL / FAILED）与端口行（FREE / OCCUPIED）齐备；
- 只有全成功才输出"后台资源已释放"，失败分支输出"未完成"且不含"已释放/已全部停止"。
"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.config import CONFIG_DIR

PROJECT_ROOT = CONFIG_DIR.parent
SCRIPTS = PROJECT_ROOT / "scripts"
STOP_PS1 = SCRIPTS / "stop_studio.ps1"
DECISION_PS1 = SCRIPTS / "runtime" / "stop_decision.ps1"


def _text(p: Path) -> str:
    assert p.is_file(), f"缺少文件: {p}"
    return p.read_text(encoding="utf-8")


def test_decision_module_exists():
    assert DECISION_PS1.is_file(), "必须提供可单测的 scripts/runtime/stop_decision.ps1"


def test_no_unconditional_bare_exit_zero():
    text = _text(STOP_PS1)
    bare = re.findall(r"^\s*exit\s+0\s*$", text, flags=re.MULTILINE)
    assert not bare, "stop_studio.ps1 不得存在独立的 'exit 0'（无条件成功退出）"


def test_final_exit_is_variable_driven():
    text = _text(STOP_PS1)
    assert "exit $exitCode" in text, "最终退出必须由变量 $exitCode 驱动"


def test_exit_code_branches_present():
    text = _text(DECISION_PS1)
    for code in (0, 10, 11, 12, 13, 14, 15):
        assert f"return {code}" in text, f"决策模块缺少退出码 {code}"


def test_decision_priority_order():
    """14 > 15 > 13 > 12 > 10 > 11 > 0 在源码中按此顺序出现。"""
    text = _text(DECISION_PS1)
    order = [14, 15, 13, 12, 10, 11, 0]
    positions = [text.index(f"return {c}") for c in order]
    assert positions == sorted(positions), (
        f"退出码决策优先级顺序错误：应 14>15>13>12>10>11>0，实际位置 {positions}"
    )


def test_per_target_result_lines():
    text = _text(STOP_PS1)
    assert "Studio Backend :" in text
    assert "ComfyUI" in text and ":" in text
    assert "Mobile Review" in text
    for state in ("STOPPED", "FAILED", "EXTERNAL"):
        assert state in text, f"缺少目标状态 {state}"


def test_port_lines_free_occupied():
    text = _text(STOP_PS1)
    for port in (8000, 8188, 8767):
        assert f"{port} :" in text, f"缺少端口行 {port}"
    assert "FREE" in text
    assert "OCCUPIED" in text


def test_release_message_only_on_success_branch():
    text = _text(STOP_PS1)
    assert "后台资源已释放" in text
    branch_idx = text.index("if ($exitCode -eq 0)")
    success_idx = text.index("后台资源已释放")
    failure_idx = text.index("后台资源释放未完成")
    assert branch_idx < success_idx < failure_idx, (
        "'后台资源已释放' 必须位于成功分支、且在失败分支文案之前"
    )


def test_failure_summary_does_not_say_released():
    text = _text(STOP_PS1)
    assert "已全部停止" not in text, "失败路径不得出现'已全部停止'"
    assert "后台资源释放未完成" in text, "失败时必须输出明确的失败摘要"
    failure_part = text[text.index("后台资源释放未完成"):]
    assert "已释放" not in failure_part, "失败摘要不得含'已释放'"
