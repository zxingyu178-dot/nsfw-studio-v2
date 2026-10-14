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


def test_port_reconciliation_helper_exists():
    """决策模块必须提供纯函数 Resolve-TargetStopState（CLI 回报 × 端口核验 -> 状态）。"""
    text = _text(DECISION_PS1)
    assert "function Resolve-TargetStopState" in text, (
        "必须提供 Resolve-TargetStopState，以端口核验为最终事实调和 CLI 瞬态 adapter_failed"
    )
    # 该函数须同时考虑 CLI 状态与端口是否 FREE（参数在定义中为 $CliState / $PortFree）
    assert "$CliState" in text and "$PortFree" in text
    for state in ("STOPPED", "FAILED", "EXTERNAL", "UNKNOWN"):
        assert f'"{state}"' in text, f"Resolve-TargetStopState 缺少状态 {state}"


def test_reconciliation_downgrades_transient_cli_failure_when_port_free():
    """Resolve-TargetStopState：FAILED + 端口 FREE 必须返回 STOPPED；FAILED + 占用仍 FAILED。"""
    text = _text(DECISION_PS1)
    # 切片 FAILED case 到下一个 switch 标签 default 之间（含内层 if 花括号，不能用非贪婪到首个 }）
    i_failed = text.index('"FAILED"')
    i_default = text.index("default", i_failed)
    block = text[i_failed:i_default]
    port_free_pos = block.index("$PortFree")
    stop_return_pos = block.index('return "STOPPED"')
    fail_return_pos = block.index('return "FAILED"')
    assert port_free_pos < stop_return_pos < fail_return_pos, (
        "FAILED 分支必须先判 $PortFree：端口 FREE 返回 STOPPED，否则返回 FAILED"
    )
    # EXTERNAL 恒为 EXTERNAL（无论端口）
    m_ext = re.search(r'"EXTERNAL"\s*\{\s*return\s+"EXTERNAL"', text)
    assert m_ext, "EXTERNAL 必须恒为 EXTERNAL（外部实例不强杀）"


def test_stop_script_reconciles_after_port_verification():
    """stop_studio.ps1 必须在端口核验之后对 Studio/Comfy 调 Resolve-TargetStopState。"""
    text = _text(STOP_PS1)
    last_wait = text.rfind("Wait-PortFree")
    assert last_wait != -1, "必须先做端口核验"
    assert text.count("Resolve-TargetStopState") >= 2, (
        "Studio 与 Comfy 都必须经 Resolve-TargetStopState 调和（至少 2 次调用）"
    )
    first_reconcile = text.index("Resolve-TargetStopState")
    assert last_wait < first_reconcile, (
        "端口核验必须在 Resolve-TargetStopState 调和之前（端口为最终事实）"
    )
    # 调和须同时传入端口结果
    assert "$port8000Free" in text and "$port8188Free" in text
    # 瞬态降级须有显式告警（不静默吞掉非 0 回报）
    assert "确认窗口瞬态" in text, "CLI 瞬态失败被降级时必须显式告警"

