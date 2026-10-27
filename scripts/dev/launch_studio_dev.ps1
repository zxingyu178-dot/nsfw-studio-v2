#requires -Version 5.1
<#
.SYNOPSIS
    NSFW Studio V2 —— **开发用**直连启动器（禁止用于生产）。

.DESCRIPTION
    把 v0.13.2 旧的"自定义端口 / 自己 Popen uvicorn"开发行为收口到这里。
    允许 -Port 指定任意端口，仅供本地开发调试。

    ⚠ 红线：本脚本【禁止用于生产】。生产启动必须走 scripts\launch_studio.ps1
      → ControlHub lifecycle CLI（固定 127.0.0.1:8000，不经本脚本 Popen）。
      本脚本不经过 ControlHub、不注册、不负责生命周期托管。

.PARAMETER ProjectRoot
    可选：显式传入项目根。默认按脚本位置自动定位。

.PARAMETER Port
    开发用端口（默认 8100）。生产端口 8000 受保护，需显式 -AllowProductionPort 才能占用。

.PARAMETER AllowProductionPort
    仅在确需临时接管 8000 时使用；平时禁止，避免出现 ControlHub 无法托管的游离实例。
#>
param(
    [string]$ProjectRoot = "",
    [int]$Port = 8100,
    [switch]$AllowProductionPort
)

$ErrorActionPreference = "Stop"
Write-Host "[DEV] launch_studio_dev.ps1 —— 仅限开发，禁止用于生产启动链。" -ForegroundColor Magenta

# scripts/dev/launch_studio_dev.ps1 -> scripts/dev -> scripts -> 项目根
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path   # scripts/dev
    $ScriptsDir = Split-Path -Parent $ScriptDir                      # scripts
    $ProjectRoot = Split-Path -Parent $ScriptsDir
}

$BackendDir = Join-Path $ProjectRoot "backend"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$BaseUrl    = "http://127.0.0.1:$Port"

if (-not (Test-Path $VenvPython)) {
    Write-Host "[DEV] 未找到虚拟环境：$VenvPython" -ForegroundColor Red
    exit 1
}

# 统一入口保护：8000 只允许 ControlHub 托管，防止出现"能开不能停"的游离实例
if ($Port -eq 8000 -and -not $AllowProductionPort) {
    Write-Host "[DEV] 拒绝启动：生产端口 8000 仅由 ControlHub 托管。" -ForegroundColor Red
    Write-Host "[DEV] 启动：scripts\\launch_studio.ps1    停止：scripts\\stop_studio.ps1" -ForegroundColor Red
    Write-Host "[DEV] 开发请用默认端口 8100，并设置 NSFW_STUDIO_API_URL=http://127.0.0.1:8100" -ForegroundColor Red
    exit 2
}

Write-Host "[DEV] 直连后台 uvicorn：127.0.0.1:$Port（生产请用 launch_studio.ps1）" -ForegroundColor Yellow
Start-Process -FilePath $VenvPython `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port") `
    -WorkingDirectory $BackendDir `
    -WindowStyle Hidden

Start-Process $BaseUrl
exit 0
