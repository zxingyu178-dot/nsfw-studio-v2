#requires -Version 5.1
<#
.SYNOPSIS
    NSFW Studio V2 —— 一次性关机 helper（Phase 0.14 Runtime Closure）。

.DESCRIPTION
    由后端 ``POST /api/v1/system/request-shutdown`` 以 detached 方式拉起。
    它**不是**长期服务、**不是**第二个 lifecycle owner，仅作为"从应用内部调用
    官方停止序列"的桥：

      1. sleep ~500ms（让 202 响应先返回给前端）；
      2. 调用 scripts/stop_studio.ps1（完整停止序列全部交给它）；
      3. 结束后自退出。

    后端自身绝不直接杀自己；所有真实启停都走 stop_studio.ps1 → ControlHub lifecycle CLI。
#>
$ErrorActionPreference = "Continue"

# scripts/runtime/shutdown_helper.ps1 -> scripts/ -> 项目根
$HelperDir   = Split-Path -Parent $MyInvocation.MyCommand.Path   # scripts/runtime
$ScriptsDir  = Split-Path -Parent $HelperDir                      # scripts
$StopScript  = Join-Path $ScriptsDir "stop_studio.ps1"

Start-Sleep -Milliseconds 500

if (Test-Path $StopScript) {
    & powershell -NoProfile -ExecutionPolicy Bypass -File $StopScript
} else {
    Write-Host "[shutdown_helper] 未找到停止脚本: $StopScript" -ForegroundColor Red
}

# 自退出（一次性 helper，不驻留）
exit 0
