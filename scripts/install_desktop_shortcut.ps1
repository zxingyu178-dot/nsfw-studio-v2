#requires -Version 5.1
<#
.SYNOPSIS
    NSFW Studio V2 —— 一次性桌面快捷方式安装 / 更新脚本。

.DESCRIPTION
    正常日用不需要每次运行本脚本；安装后双击桌面「NSFW Studio」即可启动。
    本脚本负责：
      1) 检查并创建后端 Python 虚拟环境（.venv），pip 安装 backend\requirements.txt；
      2) 前端依赖缺失时安装（npm ci / npm install），随后 npm run build；
      3) 构建成功后把 git HEAD 写入 frontend\dist\.build_commit（不在 git 仓库则写 unknown）；
      4) 在当前用户桌面创建「NSFW Studio」.lnk 快捷方式（目标为 scripts\launch_studio.bat）。

    所有路径基于脚本所在目录的上一级（项目根），不硬编码机器盘符。
    每一步失败都输出中文错误并以非零退出码结束。
#>

$ErrorActionPreference = "Stop"

# ---- 定位项目根（脚本位于 scripts\，上一级即项目根）----
$ScriptDir   = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

$BackendDir    = Join-Path $ProjectRoot "backend"
$FrontendDir  = Join-Path $ProjectRoot "frontend"
$VenvDir      = Join-Path $ProjectRoot ".venv"
$VenvPython   = Join-Path $VenvDir "Scripts\python.exe"
$Requirements = Join-Path $BackendDir "requirements.txt"

function Fail-Step([string]$msg) {
    Write-Host ""
    Write-Host "[NSFW Studio][安装失败] $msg" -ForegroundColor Red
    Write-Host "[NSFW Studio] 安装中止，请根据上方错误信息排查后重试。" -ForegroundColor Red
    exit 1
}

function Get-HeadCommit {
    if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) { return "unknown" }
    & git -C $ProjectRoot rev-parse HEAD 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { return "unknown" }
    return (& git -C $ProjectRoot rev-parse HEAD).Trim()
}

Write-Host "[NSFW Studio] 项目根：$ProjectRoot" -ForegroundColor Cyan

# ---- 1. Python 虚拟环境与后端依赖 ----
if (-not (Test-Path $VenvPython)) {
    Write-Host "[NSFW Studio] 未发现 .venv，正在创建虚拟环境（优先 py -3.11，回退 python）……"
    $created = $false
    if (Get-Command "py" -ErrorAction SilentlyContinue) {
        & py -3.11 -m venv $VenvDir
        if ($LASTEXITCODE -eq 0 -and (Test-Path $VenvPython)) { $created = $true }
    }
    if (-not $created -and (Get-Command "python" -ErrorAction SilentlyContinue)) {
        & python -m venv $VenvDir
        if ($LASTEXITCODE -eq 0 -and (Test-Path $VenvPython)) { $created = $true }
    }
    if (-not $created) {
        Fail-Step "无法创建虚拟环境：已依次尝试 'py -3.11' 与 'python' 均失败。请安装 Python 3.11 并加入 PATH。"
    }
    Write-Host "[NSFW Studio] 正在安装后端依赖（pip install -r backend\requirements.txt）……"
    & $VenvPython -m pip install -r $Requirements
    if ($LASTEXITCODE -ne 0) { Fail-Step "后端依赖安装失败（pip install 退出码 $LASTEXITCODE）。" }
} else {
    Write-Host "[NSFW Studio] 已使用现有虚拟环境：$VenvPython"
}

# ---- 2. 前端依赖（仅 node_modules 缺失时安装）----
if (-not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
    Write-Host "[NSFW Studio] 未发现 frontend\node_modules，正在安装前端依赖……"
    Push-Location $FrontendDir
    try {
        if (Test-Path (Join-Path $FrontendDir "package-lock.json")) {
            & npm ci
        } else {
            & npm install --no-audit --no-fund
        }
        if ($LASTEXITCODE -ne 0) { Fail-Step "前端依赖安装失败（npm 退出码 $LASTEXITCODE）。" }
    } finally { Pop-Location }
} else {
    Write-Host "[NSFW Studio] 已发现 frontend\node_modules，跳过依赖安装。"
}

# ---- 3. 前端构建 ----
Write-Host "[NSFW Studio] 正在构建前端（npm run build）……"
Push-Location $FrontendDir
try {
    & npm run build
    if ($LASTEXITCODE -ne 0) { Fail-Step "前端构建失败（npm run build 退出码 $LASTEXITCODE）。" }
} finally { Pop-Location }

# ---- 4. 构建戳：把 git HEAD 写入 frontend\dist\.build_commit ----
$commit   = Get-HeadCommit
$StampFile = Join-Path $FrontendDir "dist\.build_commit"
Set-Content -Path $StampFile -Value $commit -NoNewline -Encoding Ascii
Write-Host "[NSFW Studio] 构建已记录：$commit -> $StampFile" -ForegroundColor Green

# ---- 5. 桌面快捷方式（仅创建 .lnk，不复制项目到桌面）----
# 统一入口：优先指向静默启动器 .vbs（内部仍走 launch_studio.ps1 → ControlHub），
# 避免出现控制台窗口；.bat 仅作为 .vbs 缺失时的兼容回退。
$LauncherVbs = Join-Path $ScriptDir "launch_studio_hidden.vbs"
$LauncherBat = Join-Path $ScriptDir "launch_studio.bat"
if (Test-Path $LauncherVbs) {
    $ShortcutTarget = "$env:WINDIR\System32\wscript.exe"
    $ShortcutArguments = '"' + $LauncherVbs + '"'
}
elseif (Test-Path $LauncherBat) {
    $ShortcutTarget = $LauncherBat
    $ShortcutArguments = '"' + $ProjectRoot + '"'
}
else {
    Fail-Step "未找到启动器脚本：$LauncherVbs 或 $LauncherBat"
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$LnkPath = Join-Path $Desktop "NSFW Studio.lnk"

$WsShell  = New-Object -ComObject WScript.Shell
$Shortcut = $WsShell.CreateShortcut($LnkPath)
$Shortcut.TargetPath = $ShortcutTarget
# 用参数把项目根显式传进去；launch_studio.ps1 也会自行定位，这里作为显式传参。
$Shortcut.Arguments       = $ShortcutArguments
$Shortcut.WorkingDirectory = $ProjectRoot
$Shortcut.Description     = "NSFW Studio V2 本地生图工作台（FastAPI 直出 frontend/dist）"

# 图标：仓库内当前没有 .ico 文件。先在项目根下任意查找 .ico；
# 找不到就不设置 IconLocation（使用系统默认图标）。
# 后续若在仓库中放入 .ico，可在此把 $Shortcut.IconLocation 指向该图标路径。
$IcoFile = Get-ChildItem -Path $ProjectRoot -Recurse -Filter "*.ico" -ErrorAction SilentlyContinue |
    Select-Object -First 1
if ($IcoFile) {
    $Shortcut.IconLocation = $IcoFile.FullName
    Write-Host "[NSFW Studio] 使用图标：$($IcoFile.FullName)"
} else {
    Write-Host "[NSFW Studio] 仓库未发现 .ico，快捷方式使用默认图标（后续放入 .ico 后可在脚本中引用）。"
}

$Shortcut.Save()
Write-Host "[NSFW Studio] 已创建桌面快捷方式：$LnkPath" -ForegroundColor Green

# ---- 6. 「停止」快捷方式（静默，成功不打扰，失败弹退出码）----
$StopperVbs = Join-Path $ScriptDir "stop_studio_hidden.vbs"
if (Test-Path $StopperVbs) {
    $StopLnkPath = Join-Path $Desktop "NSFW Studio · 停止.lnk"
    $StopShortcut = $WsShell.CreateShortcut($StopLnkPath)
    $StopShortcut.TargetPath       = "$env:WINDIR\System32\wscript.exe"
    $StopShortcut.Arguments        = '"' + $StopperVbs + '"'
    $StopShortcut.WorkingDirectory = $ProjectRoot
    $StopShortcut.Description      = "NSFW Studio V2 一键停止（队列→Bridge→Studio→ComfyUI）"
    if ($IcoFile) { $StopShortcut.IconLocation = $IcoFile.FullName }
    $StopShortcut.Save()
    Write-Host "[NSFW Studio] 已创建桌面快捷方式：$StopLnkPath" -ForegroundColor Green
}
else {
    Write-Host "[NSFW Studio] 未找到停止包装器 $StopperVbs，跳过停止快捷方式。" -ForegroundColor Yellow
}
Write-Host ""
Write-Host "[NSFW Studio] 安装完成。双击「NSFW Studio」启动，双击「NSFW Studio · 停止」收工。" -ForegroundColor Green
exit 0
