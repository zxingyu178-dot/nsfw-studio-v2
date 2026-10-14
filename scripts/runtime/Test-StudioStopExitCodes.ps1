#requires -Version 5.1
<#
.SYNOPSIS
    NSFW Studio V2 —— 停止退出码决策的 PowerShell 测试 harness（hermetic，无真实服务/端口）。

.DESCRIPTION
    跨平台 hermetic harness（无真实服务/端口）。已在 Linux 构建机用 PowerShell Core
    (pwsh 7.4) 执行通过：15/15（14 条退出码决策 + 1 条 resolver 不抛异常烟测）。
    Windows 发布门禁仍须在 Windows PowerShell 5.1 复跑确认（.ps1 目标运行时为 5.1）：
      powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\runtime\Test-StudioStopExitCodes.ps1

    覆盖（通过 dot-source 纯函数 Get-StudioStopExitCode，mock 掉所有外部副作用）：
        全成功            -> 0
        Studio 失败       -> 10
        ComfyUI 失败      -> 11
        Mobile(8767) 占用 -> 12
        托管端口占用      -> 13
        resolver/CLI 致命 -> 14
        外部 ComfyUI      -> 15
        以及决策优先级 14 > 15 > 13 > 12 > 10 > 11 的覆盖。

    同时对 resolve_aihome.ps1 做"不抛异常"的烟测：dot-source 后 $AIHOME_ENV 必须是
    带 Ok 布尔字段的对象（解析成功或优雅失败，绝不 throw/静默空路径）。
    在 Linux 上无 ControlHub 时 Ok=False 即"优雅失败"；在 Windows 上注入/命中真实路径
    时应 Ok=True。
#>

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path   # scripts/runtime

. (Join-Path $here "stop_decision.ps1")

$script:__pass = 0
$script:__fail = 0

function Assert-Code([int]$expected, [hashtable]$Params, [string]$label) {
    $actual = Get-StudioStopExitCode @Params
    if ($actual -eq $expected) {
        Write-Host ("  [PASS] {0} => {1}" -f $label, $actual) -ForegroundColor Green
        $script:__pass++
    } else {
        Write-Host ("  [FAIL] {0} => expected {1}, got {2}" -f $label, $expected, $actual) -ForegroundColor Red
        $script:__fail++
    }
}

Write-Host "== 停止退出码决策 harness ==" -ForegroundColor Cyan

# 全成功
Assert-Code 0 @{} "全成功"

# 各目标失败
Assert-Code 10 @{ StudioFailed = $true } "Studio 失败 -> 10"
Assert-Code 11 @{ ComfyFailed = $true } "ComfyUI 失败 -> 11"
Assert-Code 12 @{ Port8767Occupied = $true } "Mobile(8767) 占用 -> 12"

# 端口仍占用（托管端口）
Assert-Code 13 @{ Port8000Occupied = $true } "8000 仍占用 -> 13"
Assert-Code 13 @{ Port8188Occupied = $true } "8188 仍占用 -> 13"

# resolver / CLI 致命
Assert-Code 14 @{ FatalCli = $true } "resolver/CLI 致命 -> 14"

# 外部非 owned ComfyUI
Assert-Code 15 @{ ComfyExternal = $true } "外部 ComfyUI -> 15"

# ---- 决策优先级覆盖 ----
# 14 最高：即使其他全失败，致命 CLI 仍报 14
Assert-Code 14 @{ FatalCli = $true; ComfyExternal = $true; Port8000Occupied = $true; StudioFailed = $true } "14 优先于一切"
# 15 > 13：外部 ComfyUI 且 8000 也被占用，仍报 15
Assert-Code 15 @{ ComfyExternal = $true; Port8000Occupied = $true } "15 优先于 13"
# 13 > 12 > 10：托管端口占用优先于 8767，优先于 Studio 失败
Assert-Code 13 @{ Port8000Occupied = $true; Port8767Occupied = $true; StudioFailed = $true } "13 优先于 12/10"
Assert-Code 12 @{ Port8767Occupied = $true; StudioFailed = $true } "12 优先于 10"
# 10 > 11：同时 Studio 与 Comfy 失败，报 10
Assert-Code 10 @{ StudioFailed = $true; ComfyFailed = $true } "10 优先于 11"
# 外部 ComfyUI 时 8188 占用属预期，不计为 13（因 ComfyExternal 先命中返回 15）
Assert-Code 15 @{ ComfyExternal = $true; Port8188Occupied = $true } "外部 ComfyUI + 8188 占用 -> 15（非 13）"

function Assert-State([string]$expected, [string]$cliState, [bool]$portFree, [string]$label) {
    $actual = Resolve-TargetStopState -CliState $cliState -PortFree $portFree
    if ($actual -eq $expected) {
        Write-Host ("  [PASS] {0} => {1}" -f $label, $actual) -ForegroundColor Green
        $script:__pass++
    } else {
        Write-Host ("  [FAIL] {0} => expected {1}, got {2}" -f $label, $expected, $actual) -ForegroundColor Red
        $script:__fail++
    }
}

Write-Host ""
Write-Host "== CLI 回报 × 端口核验 -> 逐目标状态 调和 harness ==" -ForegroundColor Cyan
# CLI 成功 / EXTERNAL 恒成立
Assert-State "STOPPED"  "STOPPED"  $true  "CLI STOPPED + 端口 FREE"
Assert-State "STOPPED"  "STOPPED"  $false "CLI STOPPED 即使端口未及 FREE（仍按成功）"
Assert-State "EXTERNAL" "EXTERNAL" $false "外部 Comfy + 8188 占用"
Assert-State "EXTERNAL" "EXTERNAL" $true  "外部 Comfy 即使端口巧合 FREE（仍不强杀）"
# CLI adapter_failed 瞬态：端口 FREE -> 已停止；端口仍占用 -> 真失败
Assert-State "STOPPED"  "FAILED"   $true  "CLI FAILED + 端口 FREE（确认窗口瞬态）-> STOPPED"
Assert-State "FAILED"   "FAILED"   $false "CLI FAILED + 端口仍占用 -> FAILED"
# UNKNOWN 跟随端口
Assert-State "STOPPED"  "UNKNOWN"  $true  "UNKNOWN + 端口 FREE -> STOPPED"
Assert-State "UNKNOWN"  "UNKNOWN"  $false "UNKNOWN + 端口仍占用 -> UNKNOWN"

Write-Host ""
Write-Host "== resolve_aihome.ps1 烟测（不抛异常） ==" -ForegroundColor Cyan
try {
    . (Join-Path $here "resolve_aihome.ps1")
    if ($AIHOME_ENV -and ($AIHOME_ENV.Ok -is [bool])) {
        Write-Host ("  [PASS] dot-source 后 `$AIHOME_ENV.Ok 为布尔（Ok={0}）" -f ([bool]$AIHOME_ENV.Ok)) -ForegroundColor Green
        $script:__pass++
    } else {
        Write-Host "  [FAIL] `$AIHOME_ENV.Ok 不是布尔（实际类型：$($AIHOME_ENV.GetType().Name)）" -ForegroundColor Red
        $script:__fail++
    }
} catch {
    Write-Host ("  [FAIL] resolve_aihome.ps1 dot-source 抛异常: {0}" -f $_.Exception.Message) -ForegroundColor Red
    Write-Host ("         at {0}:{1}" -f $_.InvocationInfo.ScriptName, $_.InvocationInfo.ScriptLineNumber) -ForegroundColor Red
    Write-Host ("         {0}" -f $_.InvocationInfo.Line) -ForegroundColor Red
    $script:__fail++
}

Write-Host ""
Write-Host ("结果：PASS={0} FAIL={1}" -f $script:__pass, $script:__fail) -ForegroundColor Cyan
if ($script:__fail -gt 0) { exit 1 }
exit 0
