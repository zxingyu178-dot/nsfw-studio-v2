#requires -Version 5.1
<#
.SYNOPSIS
    NSFW Studio V2 —— 一键停止全部后台（Phase 0.14.1 Patch Hardening，P0）。

.DESCRIPTION
    释放 NSFW Studio 整套后台资源（不是"暂停队列"），固定停止顺序：

      [1/4] best-effort 暂停队列（POST 127.0.0.1:8000/api/v1/queue/pause）
      [2/4] best-effort 停止 Mobile Review Bridge（POST .../api/v1/mobile-review/runtime/stop）
      [3/4] 调 ControlHub lifecycle CLI stop nsfw-studio-v2   （Studio 后端 8000）
      [4/4] 调 ControlHub lifecycle CLI stop comfyui          （ComfyUI     8188）

    随后逐目标打印 STOPPED / EXTERNAL / FAILED，并核验 8000 / 8188 / 8767 端口 FREE/OCCUPIED。

    退出码（务必逐字一致；任何失败绝不返回 0）：
        0  全部目标成功停止、端口符合预期
       10  Studio Backend(nsfw-studio-v2 / 8000) 停止失败
       11  ComfyUI(comfyui / 8188) 停止失败
       12  Mobile Review(8767) 子运行时未随后端退出
       13  停止后核验：托管端口(8000/8188 owned)仍被占用
       14  ControlHub 调用失败（resolver 解析失败 / lifecycle CLI 无法调用）
       15  外部非 owned ComfyUI（EXTERNAL_NOT_OWNED，partial success，非 0，绝不强杀）

    决策优先级（取第一个命中者，使行为可预测、可测）：
        14 > 15 > 13 > 12 > 10 > 11 > 0
    （详见 scripts/runtime/stop_decision.ps1 中的 Get-StudioStopExitCode。）

    安全红线（务必遵守）：
      - 严禁按进程通配名强杀 python / node（不误杀无关进程）；
      - 只通过 ControlHub lifecycle CLI + Studio 自身已知 runtime 停止；
      - ComfyUI 若非本 ControlHub owned（外部实例）→ 打印 EXTERNAL_NOT_OWNED，绝不强杀；
      - 任一 HTTP 调用失败都不中断整体停止（best-effort 标注）；
      - 端口超时未释放 → 打印 STOP_TIMEOUT / OCCUPIED，不静默。
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

# ---- 解析 ControlHub 环境（去硬编码；dot-source 后读取 $AIHOME_ENV） ----
$RuntimeDir   = Join-Path $PSScriptRoot "runtime"
$ResolveScript = Join-Path $RuntimeDir "resolve_aihome.ps1"
$DecisionScript = Join-Path $RuntimeDir "stop_decision.ps1"
. $ResolveScript
. $DecisionScript

# ---- 固定端口（红线，禁止换口） ----
$StudioPort       = 8000
$MobileBridgePort = 8767
$ComfyPort        = 8188

$BaseUrl = "http://127.0.0.1:$StudioPort"
$PortWaitTimeoutSec = 20
$CliModule = "control_hub.lifecycle_cli"

# ---- 由 resolver 提供连接参数（正文不得再写死机器完整路径） ----
$FatalCli = $false
$ControlHubPython   = $null
$ControlHubDataRoot = $null
if ($AIHOME_ENV.Ok) {
    $ControlHubPython   = $AIHOME_ENV.CONTROLHUB_PYTHON
    $ControlHubDataRoot = $AIHOME_ENV.CONTROLHUB_DATA_ROOT
} else {
    # resolver 解析失败 -> 归退出码 14（CLI 根本无法调用）
    $FatalCli = $true
    Write-Host "[stop] ControlHub 环境解析失败：$($AIHOME_ENV.Error)" -ForegroundColor Red
}

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
          @{ Ok=[bool]; ExitCode=[int]; InvocationFailed=[bool]; Output=[string] }
        只走官方 CLI，绝不按通配名强杀进程。
    #>
    Write-Step "  调用 ControlHub lifecycle CLI: stop $IntegrationId"
    if ([string]::IsNullOrWhiteSpace($ControlHubPython) -or -not (Test-Path $ControlHubPython)) {
        return @{ Ok = $false; ExitCode = -1; InvocationFailed = $true; Output = "CLI 解释器不可用: $ControlHubPython" }
    }
    $argv = @("-m", $CliModule, "stop", $IntegrationId, "--data-root", $ControlHubDataRoot)
    try {
        $output = & $ControlHubPython @argv 2>&1 | Out-String
        $code = $LASTEXITCODE
    } catch {
        return @{ Ok = $false; ExitCode = -1; InvocationFailed = $true; Output = $_.Exception.Message }
    }
    if ($null -eq $code) { $code = -1 }
    return @{ Ok = ($code -eq 0); ExitCode = $code; InvocationFailed = $false; Output = ($output | Out-String).Trim() }
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
# 逐目标状态（用于最终退出码决策与摘要）
# =====================================================================================
$StudioState   = "UNKNOWN"   # STOPPED / FAILED
$ComfyState     = "UNKNOWN"   # STOPPED / EXTERNAL / FAILED
$MobileState   = "UNKNOWN"   # STOPPED / FAILED

# =====================================================================================
# [1/4] best-effort 暂停队列
# =====================================================================================
Write-Step "[1/4] 暂停队列（best-effort）"
if ($FatalCli -or (Test-PortFree $StudioPort)) {
    Write-Warn2 "  后端 8000 已离线或 CLI 不可用，跳过队列暂停"
} else {
    Invoke-BestEffortPost "$BaseUrl/api/v1/queue/pause" "queue/pause" | Out-Null
}

# =====================================================================================
# [2/4] best-effort 停止 Mobile Review Bridge
# =====================================================================================
Write-Step "[2/4] 停止 Mobile Review Bridge（best-effort）"
if ($FatalCli -or (Test-PortFree $StudioPort)) {
    Write-Warn2 "  后端 8000 已离线或 CLI 不可用，无法经后端停止 Bridge，跳过"
} else {
    Invoke-BestEffortPost "$BaseUrl/api/v1/mobile-review/runtime/stop" "mobile-review/runtime/stop" | Out-Null
}

# =====================================================================================
# [3/4] ControlHub CLI stop nsfw-studio-v2（Studio 后端 8000）
# =====================================================================================
Write-Step "[3/4] 停止 NSFW Studio 后端（nsfw-studio-v2）"
$r = $null
if ($FatalCli) {
    Write-Warn2 "  跳过（CLI 不可用，将归入退出码 14）"
} else {
    $r = Invoke-LifecycleStop "nsfw-studio-v2"
    if ($r.InvocationFailed) {
        $FatalCli = $true
        Write-Err "  nsfw-studio-v2 lifecycle CLI 调用失败: $($r.Output)"
    } elseif ($r.Ok) {
        $StudioState = "STOPPED"
        Write-Ok "  nsfw-studio-v2 stop 返回 succeeded"
    } elseif ($r.ExitCode -eq 2) {
        # 未注册 / 未批准：本就不存在，视为已停（幂等）
        $StudioState = "STOPPED"
        Write-Warn2 "  nsfw-studio-v2 未注册/未批准（exit 2），假定已停"
    } else {
        $StudioState = "FAILED"
        Write-Err "  nsfw-studio-v2 stop 未返回成功（exit $($r.ExitCode)）: $($r.Output)"
    }
}

# =====================================================================================
# [4/4] ControlHub CLI stop comfyui（ComfyUI 8188）
# =====================================================================================
Write-Step "[4/4] 停止 ComfyUI（comfyui）"
$c = $null
if ($FatalCli) {
    Write-Warn2 "  跳过（CLI 不可用，将归入退出码 14）"
} else {
    $c = Invoke-LifecycleStop "comfyui"
    if ($c.InvocationFailed) {
        $FatalCli = $true
        Write-Err "  comfyui lifecycle CLI 调用失败: $($c.Output)"
    } elseif ($c.Ok) {
        $ComfyState = "STOPPED"
        Write-Ok "  comfyui stop 返回 succeeded"
    } elseif ($c.ExitCode -eq 2) {
        # 未注册/未批准 -> 外部非 owned 实例，绝不强杀
        $ComfyState = "EXTERNAL"
        Write-Warn2 "  comfyui 未注册/未批准（exit 2）：EXTERNAL_NOT_OWNED，外部实例不强杀"
    } else {
        $ComfyState = "FAILED"
        Write-Err "  comfyui stop 未返回成功（exit $($c.ExitCode)）: $($c.Output)"
    }
}

# =====================================================================================
# 端口释放核验
# =====================================================================================
Write-Step "`n核验端口释放……"

$port8000Free = Wait-PortFree $StudioPort $PortWaitTimeoutSec
if ($port8000Free) { Write-Ok "8000 : FREE" }
else { Write-Err "8000 : OCCUPIED（STOP_TIMEOUT）" }

Start-Sleep -Milliseconds 500
$port8767Free = Wait-PortFree $MobileBridgePort $PortWaitTimeoutSec
if ($port8767Free) { Write-Ok "8767 : FREE" }
else { Write-Err "8767 : OCCUPIED（STOP_TIMEOUT）" }

$port8188Free = Wait-PortFree $ComfyPort $PortWaitTimeoutSec
if ($port8188Free) { Write-Ok "8188 : FREE" }
else {
    if ($ComfyState -eq "EXTERNAL") {
        Write-Warn2 "8188 : OCCUPIED（外部实例 EXTERNAL_NOT_OWNED，不强杀）"
    } else {
        Write-Err "8188 : OCCUPIED（STOP_TIMEOUT）"
    }
}

# Mobile 状态由 8767 端口核验决定（子运行时随 Studio 退出）
if ($port8767Free) { $MobileState = "STOPPED" } else { $MobileState = "FAILED" }

# =====================================================================================
# 逐目标结果
# =====================================================================================
Write-Step "`n逐目标结果："
Write-Host ("Studio Backend : {0}" -f $StudioState)
Write-Host ("ComfyUI        : {0}" -f $ComfyState)
Write-Host ("Mobile Review  : {0}" -f $MobileState)

# =====================================================================================
# 决策 -> 最终退出码（纯函数，见 stop_decision.ps1）
# =====================================================================================
$studioFailed = ($StudioState -eq "FAILED")
$comfyFailed  = ($ComfyState -eq "FAILED")
$comfyExternal = ($ComfyState -eq "EXTERNAL")

$exitCode = Get-StudioStopExitCode `
    -FatalCli          $FatalCli `
    -StudioFailed      $studioFailed `
    -ComfyFailed       $comfyFailed `
    -ComfyExternal     $comfyExternal `
    -Port8000Occupied  (-not $port8000Free) `
    -Port8188Occupied  (-not $port8188Free) `
    -Port8767Occupied (-not $port8767Free)

# =====================================================================================
# 最终摘要（仅全成才输出"已释放"；失败时给明确失败摘要）
# =====================================================================================
Write-Host ""
if ($exitCode -eq 0) {
    Write-Ok "后台资源已释放。（退出码 0）"
} else {
    $reasons = New-Object System.Collections.Generic.List[string]
    if ($FatalCli)      { $reasons.Add("ControlHub 调用失败（resolver 解析失败或 lifecycle CLI 无法调用）") }
    if ($comfyExternal) { $reasons.Add("外部 ComfyUI 非本 ControlHub owned（EXTERNAL_NOT_OWNED），已保留不强杀") }
    if (-not $port8000Free) { $reasons.Add("8000 仍被占用（STOP_TIMEOUT）") }
    if ((-not $port8188Free) -and -not $comfyExternal) { $reasons.Add("8188 仍被占用（STOP_TIMEOUT）") }
    if (-not $port8767Free) { $reasons.Add("8767(Mobile Review) 仍被占用") }
    if ($studioFailed)  { $reasons.Add("Studio Backend 停止失败") }
    if ($comfyFailed)   { $reasons.Add("ComfyUI 停止失败") }
    if ($reasons.Count -eq 0) { $reasons.Add("未完全释放（见上方逐目标/端口结果）") }
    Write-Err ("后台资源释放未完成（退出码 {0}）：" -f $exitCode)
    foreach ($r_ in $reasons) { Write-Err ("  - " + $r_) }
}

exit $exitCode
