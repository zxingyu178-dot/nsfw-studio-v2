# run_frontend.ps1 — 隐藏宿主：NSFW Studio V2 前端（Vite dev server）。
#
# 由计划任务 "\AIHome\NSFWStudioV2Frontend" 调用（-WindowStyle Hidden，无控制台窗口）。

#requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Continue'
$runtimeDir = $PSScriptRoot                                  # scripts\runtime
$projectRoot = Split-Path -Parent (Split-Path -Parent $runtimeDir)
$npm = 'D:\AIHome_2.0_L1_L2\environment\managed-tools\node\node-v24.18.1-win-x64\npm.cmd'
$logDir = Join-Path $projectRoot 'temp\logs'

if (-not (Test-Path $npm)) { throw "npm not found: $npm" }
New-Item -ItemType Directory -Force $logDir | Out-Null

Set-Location (Join-Path $projectRoot 'frontend')
& $npm run dev *>> (Join-Path $logDir 'frontend.log')
exit $LASTEXITCODE