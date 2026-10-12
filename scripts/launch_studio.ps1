#requires -Version 5.1
<#
.SYNOPSIS
    NSFW Studio V2 —— 日常启动器（双击桌面快捷方式即调用本脚本）。

.DESCRIPTION
    正常启动【不会】重复 npm install：
      - 仅在 frontend\dist 缺失，或 dist\.build_commit 与 git HEAD 不一致时才重新构建；
      - 若工作区有未提交改动，给出中文提示但不阻断启动。
    先探测 127.0.0.1:8000 是否已在服务：已在服务则直接打开浏览器；
    否则用项目根 .venv 的 python 后台启动 uvicorn（app.main:app，127.0.0.1:8000）。
    脚本退出后后端进程继续运行（独立进程，不随脚本退出被杀掉）。

.PARAMETER ProjectRoot
    可选：显式传入项目根。默认按脚本位置（scripts 的上一级）自动定位。
#>
param(
    [string]$ProjectRoot = "",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

# ---- 定位项目根 ----
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
    $ProjectRoot = Split-Path -Parent $ScriptDir
}

$BackendDir  = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"
$VenvPython  = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$DistIndex   = Join-Path $FrontendDir "dist\index.html"
$StampFile   = Join-Path $FrontendDir "dist\.build_commit"
$BaseUrl     = "http://127.0.0.1:$Port"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[NSFW Studio] 未找到虚拟环境：$VenvPython" -ForegroundColor Red
    Write-Host "[NSFW Studio] 请先运行 scripts\install_desktop_shortcut.ps1 完成一次性安装。" -ForegroundColor Red
    exit 1
}

function Fail-Step([string]$msg) {
    Write-Host "[NSFW Studio][启动失败] $msg" -ForegroundColor Red
    exit 1
}

function Get-HeadCommit {
    if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) { return "unknown" }
    & git -C $ProjectRoot rev-parse HEAD 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { return "unknown" }
    return (& git -C $ProjectRoot rev-parse HEAD).Trim()
}

# ---- git HEAD 与工作区状态（只读）----
$head      = Get-HeadCommit
$porcelain = @()
if (Get-Command "git" -ErrorAction SilentlyContinue) {
    $porcelain = @(& git -C $ProjectRoot status --porcelain 2>$null)
}

# ---- 前端构建戳检查 ----
$stamp = ""
if (Test-Path $StampFile) { $stamp = (Get-Content $StampFile -Raw).Trim() }

$needBuild = $false
if (-not (Test-Path $DistIndex)) {
    $needBuild = $true
} elseif ($head -ne "unknown" -and $head -ne "" -and $stamp -ne $head) {
    $needBuild = $true
}

if ($porcelain.Count -gt 0) {
    Write-Host "[NSFW Studio] 检测到未提交改动，dist 可能不是最新（不阻断启动）。" -ForegroundColor Yellow
}

if ($needBuild) {
    Write-Host "[NSFW Studio] 前端构建已过期，正在重新构建……" -ForegroundColor Cyan
    if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
        Write-Host "[NSFW Studio] 未发现 node_modules，正在安装前端依赖……"
        Push-Location $FrontendDir
        try {
            if (Test-Path (Join-Path $FrontendDir "package-lock.json")) { & npm ci }
            else { & npm install --no-audit --no-fund }
            if ($LASTEXITCODE -ne 0) { Fail-Step "前端依赖安装失败（npm 退出码 $LASTEXITCODE）。" }
        } finally { Pop-Location }
    }
    Push-Location $FrontendDir
    try {
        & npm run build
        if ($LASTEXITCODE -ne 0) { Fail-Step "前端构建失败（npm run build 退出码 $LASTEXITCODE）。" }
    } finally { Pop-Location }
    # 构建成功后更新构建戳
    $newCommit = Get-HeadCommit
    Set-Content -Path $StampFile -Value $newCommit -NoNewline -Encoding Ascii
    Write-Host "[NSFW Studio] 前端构建完成：$newCommit" -ForegroundColor Green
}

# ---- v0.13.2 (d) 端口预检：三分支判定（可 dot-source 复用） ----
function Get-StudioPortStatus {
    <#
    .SYNOPSIS
        判定 127.0.0.1:<Port> 当前占用情况，返回 'Free' | 'Ours' | 'Other'。
        可 dot-source 本脚本后单独调用（此时 $Port 由调用方设置）。
    #>
    param([int]$Port)

    # 1) 无 LISTEN → Free
    $listen = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if (-not $listen) { return "Free" }

    # 2) 有 LISTEN，短超时探本应用健康特征
    $base = "http://127.0.0.1:$Port"
    try {
        $resp = Invoke-WebRequest -Uri "$base/api/v1/health" -TimeoutSec 2 -UseBasicParsing -ErrorAction Stop
        $raw = $resp.Content
        if ($raw -is [byte[]]) { $body = [System.Text.Encoding]::UTF8.GetString($raw) }
        else { $body = [string]$raw }
        if ($body -match '"app_version"' -or $body -match '"product"' -or $body -match '"status"') {
            return "Ours"
        }
    } catch { }

    # 3) 有 LISTEN 但非本应用 → Other，取占用进程信息
    return "Other"
}

function Get-PortOwnerInfo {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { return $null }
    $pid_ = $conn.OwningProcess
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $pid_" -ErrorAction Stop
        return [PSCustomObject]@{
            Pid       = $pid_
            Name      = $proc.Name
            CommandLine = $proc.CommandLine
        }
    } catch {
        return [PSCustomObject]@{ Pid = $pid_; Name = "(unknown)"; CommandLine = "" }
    }
}

# ---- 探测端口状态 ----
$portStatus = Get-StudioPortStatus -Port $Port

if ($portStatus -eq "Ours") {
    Write-Host "[NSFW Studio] 后端已在运行（$BaseUrl），直接打开浏览器。" -ForegroundColor Green
    Start-Process $BaseUrl
    exit 0
}

if ($portStatus -eq "Other") {
    $owner = Get-PortOwnerInfo -Port $Port
    Write-Host "[NSFW Studio][端口冲突] 端口 $Port 被其他程序占用：" -ForegroundColor Red
    if ($owner) {
        Write-Host ("  PID: {0}" -f $owner.Pid) -ForegroundColor Red
        Write-Host ("  程序: {0}" -f $owner.Name) -ForegroundColor Red
        Write-Host ("  命令行: {0}" -f $owner.CommandLine) -ForegroundColor Red
    }
    Write-Host "[NSFW Studio] 请先关闭占用 $Port 的程序后再启动；本程序不会静默换口或抢占端口。" -ForegroundColor Red
    exit 3
}

# Free → 继续启动 uvicorn

# ---- 后台启动 uvicorn（独立进程，脚本退出后继续运行）----
Write-Host "[NSFW Studio] 正在启动后端 uvicorn（127.0.0.1:$Port）……"
Start-Process -FilePath $VenvPython `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port") `
    -WorkingDirectory $BackendDir `
    -WindowStyle Hidden

# ---- 轮询健康检查直到通过或超时 ----
$deadline = (Get-Date).AddSeconds(40)
$ok = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 1
    if ((Get-StudioPortStatus -Port $Port) -eq "Ours") { $ok = $true; break }
}
if (-not $ok) {
    Fail-Step "后端启动超时（40 秒内健康检查未通过）。请手动查看 backend 日志排查。"
}

Write-Host "[NSFW Studio] 后端已就绪：$BaseUrl" -ForegroundColor Green
Start-Process $BaseUrl
exit 0
