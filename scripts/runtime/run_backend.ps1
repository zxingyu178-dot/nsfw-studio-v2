# run_backend.ps1 — 隐藏宿主：NSFW Studio V2 后端（uvicorn）。
#
# 由计划任务 "\AIHome\NSFWStudioV2" 调用（-WindowStyle Hidden，无控制台窗口）。
# 生命周期与 ComfyUI 载体同模式：手动启停、无触发器、当前用户非提权。

#requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$runtimeDir = $PSScriptRoot                                  # scripts\runtime
$projectRoot = Split-Path -Parent (Split-Path -Parent $runtimeDir)
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$logDir = Join-Path $projectRoot 'temp\logs'

if (-not (Test-Path $python)) { throw "venv python not found: $python" }
New-Item -ItemType Directory -Force $logDir | Out-Null

Set-Location (Join-Path $projectRoot 'backend')
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 *>> (Join-Path $logDir 'backend.log')
exit $LASTEXITCODE