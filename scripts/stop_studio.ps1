#requires -Version 5.1
<#
.SYNOPSIS
    NSFW Studio V2 —— 一键停止全部后台（Phase 0.14 Runtime Closure，P0）。

.DESCRIPTION
    释放 NSFW Studio 整套后台资源（不是"暂停队列"），固定停止顺序：

      [1/4] best-effort 暂停队列（POST 127.0.0.1:8000/api/v1/queue/pause）
      [2/4] best-effort 停止 Mobile Review Bridge（POST .../api/v1/mobile-review/runtime/stop）
      [3/4] 调 ControlHub lifecycle CLI stop nsfw-studio-v2   （Studio 后端 8000）
      [4/4] 调 ControlHub lifecycle CLI stop comfyui          （ComfyUI     8188）

    随后核验 8000 / 8767 / 8188 端口释放，逐端口打印 FREE。

    安全红线（务必遵守）：
      - 严禁按进程通配名强杀 python / node（不误杀无关进程）；
      - 只通过 ControlHub lifecycle CLI + Studio 自身已知 runtime 停止；
      - ComfyUI 若非本 ControlHub owned（外部实例）→ 打印 EXTERNAL_NOT_OWNED，绝不强杀；
      - 任一 HTTP 调用失败都不中断整体停止（best-effort 标注）；
      - 端口超时未释放 → 打印 STOP_TIMEOUT，不静默。
#>
param(
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Continue"

# ---- 定位项目根 ----
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
    $ProjectRoot = Split-Path -Parent $ScriptDir
}

# ---- ControlHub 官方 lifecycle CLI 连接（冻结，不使用项目 .venv） ----
$ControlHubPython = "D:\control-hub\.venv\Scripts\python.exe"
$ControlHubDataRoot = "C:\Users\30566\AppData\Local\AIHomeControlHub\data"
$CliModule = "control_hub.lifecycle_cli"

# ---- 固定端口（红线，禁止换口） ----
$StudioPort     = 8000
$MobileBridgePort = 8767
$ComfyPort      = 8188

$BaseUrl = "http://127.0.0.1:$StudioPort"
$PortWaitTimeoutSec = 20

function Write-Step([string]$msg) { Write-Host $msg -ForegroundColor Cyan }
function Write-Ok([string]$msg)   { Write-Host $msg -ForegroundColor Green }
function Write-Warn2([string]$msg) { Write-Host $msg -ForegroundColor Yellow }
function Write-Err([string]$msg)   { Write-Host $msg -ForegroundColor Red }

function Test-PortFree([int]$Port) {
    $listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return (-not $listen)
}

function Wait-PortFree([int]$Port, [int]$TimeoutSec) {
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortFree $Port) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return (Test-PortFree $Port)
}

function Invoke-LifecycleStop([string]$IntegrationId) {
    <#
        调官方 CLI stop <id> --data-root <...>。返回 hashtable：
          @{ Ok=[bool]; ExitCode=[int]; Output=[string] }
        只走官方 CLI，绝不按通配名强杀进程。
    #>
    Write-Step "  调用 ControlHub lifecycle CLI: stop $IntegrationId"
    $argv = @("-m", $CliModule, "stop", $IntegrationId, "--data-root", $ControlHubDataRoot)
    $output = & $ControlHubPython @argv 2>&1 | Out-String
    $code = $LASTEXITCODE
    return @{ Ok = ($code -eq 0); ExitCode = $code; Output = ($output | Out-String).Trim() }
}

function Invoke-BestEffortPost([string]$Url, [string]$Label) {
    <# best-effort HTTP 调用：失败只警告，绝不中断停止序列。 #>
    try {
        Invoke-WebRequest -Uri $Url -Method Post -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop | Out-Null
        Write-Ok "  [$Label] 已发送"
        return $true
    } catch {
        Write-Warn2 "  [$Label] 不可达/失败（best-effort，忽略）: $($_.Exception.Message)"
        return $false
    }
}

# =====================================================================================
# [1/4] best-effort 暂停队列
# =====================================================================================
Write-Step "[1/4] 暂停队列（best-effort）"
if (Test-PortFree $StudioPort) {
    Write-Warn2 "  后端 8000 已离线，跳过队列暂停"
} else {
    Invoke-BestEffortPost "$BaseUrl/api/v1/queue/pause" "queue/pause" | Out-Null
}

# =====================================================================================
# [2/4] best-effort 停止 Mobile Review Bridge
# =====================================================================================
Write-Step "[2/4] 停止 Mobile Review Bridge（best-effort）"
if (Test-PortFree $StudioPort) {
    Write-Warn2 "  后端 8000 已离线，无法经后端停止 Bridge，跳过"
} else {
    Invoke-BestEffortPost "$BaseUrl/api/v1/mobile-review/runtime/stop" "mobile-review/runtime/stop" | Out-Null
}

# =====================================================================================
# [3/4] ControlHub CLI stop nsfw-studio-v2（Studio 后端 8000）
# =====================================================================================
Write-Step "[3/4] 停止 NSFW Studio 后端（nsfw-studio-v2）"
$r = Invoke-LifecycleStop "nsfw-studio-v2"
if ($r.Ok) {
    Write-Ok "  nsfw-studio-v2 stop 返回 succeeded"
} elseif ($r.ExitCode -eq 2) {
    # 未注册 / 未批准：本就不存在，不视为失败（第二阶段才审批）
    Write-Warn2 "  nsfw-studio-v2 未注册/未批准（exit 2），假定已停"
} else {
    Write-Warn2 "  nsfw-studio-v2 stop 未返回成功（exit $($r.ExitCode)）: $($r.Output)"
}

# =====================================================================================
# [4/4] ControlHub CLI stop comfyui（ComfyUI 8188）
# =====================================================================================
Write-Step "[4/4] 停止 ComfyUI（comfyui）"
$c = Invoke-LifecycleStop "comfyui"

# =====================================================================================
# 端口释放核验
# =====================================================================================
Write-Step "`n核验端口释放……"

# ---- 8000 ----
if (Wait-PortFree $StudioPort $PortWaitTimeoutSec) {
    Write-Ok ("8000: FREE")
} else {
    Write-Err ("8000: STOP_TIMEOUT")
}

# ---- 8767（随后端退出；后端停了 Bridge 通常随之释放） ----
Start-Sleep -Milliseconds 500
if (Wait-PortFree $MobileBridgePort $PortWaitTimeoutSec) {
    Write-Ok ("8767: FREE")
} else {
    Write-Err ("8767: STOP_TIMEOUT")
}

# ---- 8188：区分 owned 已停 vs 外部非 owned ----
if (Wait-PortFree $ComfyPort $PortWaitTimeoutSec) {
    Write-Ok ("8188: FREE")
} else {
    # 8188 仍在监听：若非 CLI owned 成功，视为外部实例，绝不强杀
    if ($c.Ok) {
        Write-Err ("8188: STOP_TIMEOUT（CLI 报告成功但端口未释放）")
    } elseif ($c.ExitCode -eq 2) {
        Write-Warn2 ("8188: EXTERNAL_NOT_OWNED（comfyui 未在本 ControlHub 注册/未批准，外部实例不强杀）")
    } else {
        Write-Warn2 ("8188: EXTERNAL_NOT_OWNED（非本 ControlHub owned，外部实例不强杀）")
    }
}

Write-Ok "`n后台资源释放流程结束（详见上方端口核验）。"
exit 0
