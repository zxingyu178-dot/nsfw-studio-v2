#requires -Version 5.1
<#
.SYNOPSIS
    只读检查部署工作树 HEAD 与 frontend/dist 的一致性。
#>

[CmdletBinding()]
param(
    [string]$AppPath
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DevRoot = Split-Path -Parent $ScriptDir
if ([string]::IsNullOrWhiteSpace($AppPath)) {
    $AppPath = Join-Path (Split-Path -Parent $DevRoot) "nsfw-studio-v2-app"
}

$failures = 0

function Write-Pass([string]$Message) {
    Write-Host "PASS $Message" -ForegroundColor Green
}

function Write-Warn([string]$Message) {
    Write-Host "WARN $Message" -ForegroundColor Yellow
}

function Write-Fail([string]$Message) {
    $script:failures++
    Write-Host "FAIL $Message" -ForegroundColor Red
}

function Get-GitValue([string]$Repository, [string[]]$Arguments) {
    $output = @(& git -C $Repository @Arguments 2>&1)
    if ($LASTEXITCODE -ne 0) {
        throw (($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine)
    }
    return (($output | ForEach-Object { $_.ToString() }) -join "`n").Trim()
}

function Get-BuildCommit([string]$DistPath) {
    $stampPath = Join-Path $DistPath ".build_commit"
    if (-not (Test-Path -LiteralPath $stampPath -PathType Leaf)) {
        return $null
    }
    return (Get-Content -LiteralPath $stampPath -Raw).Trim()
}

function Test-DistAssets([string]$DistPath, [string]$Label) {
    $indexPath = Join-Path $DistPath "index.html"
    if (-not (Test-Path -LiteralPath $indexPath -PathType Leaf)) {
        Write-Fail "$Label 缺少 index.html：$indexPath"
        return
    }

    $html = Get-Content -LiteralPath $indexPath -Raw
    $pattern = '(?i)(?:src|href)\s*=\s*["''](?<path>/assets/[^"''?#]+\.(?:js|css))(?:[?#][^"'']*)?["'']'
    $references = @([regex]::Matches($html, $pattern) | ForEach-Object { $_.Groups["path"].Value } | Sort-Object -Unique)
    if ($references.Count -eq 0) {
        Write-Fail "$Label index.html 未引用任何 /assets/*.js 或 /assets/*.css。"
        return
    }

    $missing = @()
    foreach ($reference in $references) {
        $relativePath = $reference.TrimStart('/').Replace('/', [IO.Path]::DirectorySeparatorChar)
        if (-not (Test-Path -LiteralPath (Join-Path $DistPath $relativePath) -PathType Leaf)) {
            $missing += $reference
        }
    }
    if ($missing.Count -gt 0) {
        Write-Fail "$Label index.html 引用了不存在的资源：$($missing -join ', ')"
    } else {
        Write-Pass "$Label index.html 引用的 $($references.Count) 个 JS/CSS 资源均存在。"
    }
}

try {
    Write-Host "# NSFW Studio V2 部署一致性检查" -ForegroundColor Cyan
    Write-Host "- 模式: 只读"

    if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) {
        Write-Fail "未找到 git；请通过 AIHome environment 的已登记入口确认 Git 可用。"
        exit 1
    }
    if (-not (Test-Path -LiteralPath $AppPath -PathType Container)) {
        Write-Fail "部署工作树不存在：$AppPath"
        exit 1
    }

    $DevRoot = (Resolve-Path -LiteralPath $DevRoot).Path
    $AppRoot = (Resolve-Path -LiteralPath $AppPath).Path
    $AppDist = Join-Path $AppRoot "frontend\dist"
    $DevDist = Join-Path $DevRoot "frontend\dist"

    try {
        $appHead = Get-GitValue $AppRoot @("rev-parse", "HEAD")
        $originMain = Get-GitValue $AppRoot @("rev-parse", "origin/main")
        if ($appHead -eq $originMain) {
            Write-Pass "app HEAD 与 origin/main 一致：$appHead"
        } else {
            Write-Fail "app HEAD ($appHead) 与 origin/main ($originMain) 不一致。先运行 deploy_app_dist.ps1。"
        }
    } catch {
        Write-Fail "无法比较 app HEAD 与 origin/main：$($_.Exception.Message)"
        $appHead = $null
    }

    $appBuildCommit = Get-BuildCommit $AppDist
    if ([string]::IsNullOrWhiteSpace($appBuildCommit)) {
        Write-Fail "app dist 缺少 .build_commit：$AppDist"
    } elseif ($appHead -and $appBuildCommit -eq $appHead) {
        Write-Pass "app dist .build_commit 与 app HEAD 一致：$appBuildCommit"
    } elseif ($appHead) {
        Write-Fail "app dist .build_commit ($appBuildCommit) 与 app HEAD ($appHead) 不一致。"
    }

    Test-DistAssets $AppDist "app dist"

    if (-not (Test-Path -LiteralPath $DevDist -PathType Container)) {
        Write-Warn "dev frontend/dist 不存在，按约定跳过 dev/app 构建戳比较。"
    } else {
        $devBuildCommit = Get-BuildCommit $DevDist
        if ([string]::IsNullOrWhiteSpace($devBuildCommit)) {
            Write-Fail "dev dist 存在但缺少 .build_commit：$DevDist"
        } elseif ([string]::IsNullOrWhiteSpace($appBuildCommit)) {
            Write-Fail "无法比较 dev/app 构建戳：app .build_commit 缺失。"
        } elseif ($devBuildCommit -eq $appBuildCommit) {
            Write-Pass "dev/app dist .build_commit 一致：$devBuildCommit"
        } else {
            Write-Fail "dev dist .build_commit ($devBuildCommit) 与 app ($appBuildCommit) 不一致。"
        }
    }

    Write-Host ""
    if ($failures -gt 0) {
        Write-Host "## 结果: FAIL ($failures 项不一致)" -ForegroundColor Red
        exit 1
    }
    Write-Host "## 结果: PASS" -ForegroundColor Green
    exit 0
} catch {
    Write-Host "FAIL 检查脚本异常：$($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
