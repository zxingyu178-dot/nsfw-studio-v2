#requires -Version 5.1
<#
.SYNOPSIS
    构建开发工作树的前端，并同步到部署工作树。

.EXAMPLE
    powershell -File scripts/deploy_app_dist.ps1 [-SkipBuild] [-DryRun]
#>

[CmdletBinding()]
param(
    [switch]$SkipBuild,
    [switch]$DryRun,
    [string]$AppPath
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DevRoot = Split-Path -Parent $ScriptDir
$DefaultAppPath = Join-Path (Split-Path -Parent $DevRoot) "nsfw-studio-v2-app"
if ([string]::IsNullOrWhiteSpace($AppPath)) {
    $AppPath = $DefaultAppPath
}

function Fail-Deploy([string]$Message) {
    throw $Message
}

function Format-Command([string]$Command, [string[]]$Arguments) {
    $formatted = @($Command)
    foreach ($argument in $Arguments) {
        if ($argument -match '[\s"]') {
            $formatted += ('"' + ($argument -replace '"', '\"') + '"')
        } else {
            $formatted += $argument
        }
    }
    return ($formatted -join ' ')
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Command,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage,
        [switch]$Capture
    )

    Write-Host ("$ " + (Format-Command $Command $Arguments)) -ForegroundColor DarkGray
    if ($Capture) {
        $output = @(& $Command @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            $details = ($output | ForEach-Object { $_.ToString() }) -join [Environment]::NewLine
            Fail-Deploy "$FailureMessage（退出码 $exitCode）。`n$details"
        }
        return $output
    }

    & $Command @Arguments
    $exitCode = $LASTEXITCODE
    if ($exitCode -ne 0) {
        Fail-Deploy "$FailureMessage（退出码 $exitCode）。"
    }
}

function Get-GitValue([string]$Repository, [string[]]$Arguments, [string]$FailureMessage) {
    $allArguments = @("-C", $Repository) + $Arguments
    $output = Invoke-CheckedCommand -Command "git" -Arguments $allArguments -FailureMessage $FailureMessage -Capture
    return (($output | ForEach-Object { $_.ToString() }) -join "`n").Trim()
}

function Get-ReferencedAssets([string]$DistPath) {
    $indexPath = Join-Path $DistPath "index.html"
    if (-not (Test-Path -LiteralPath $indexPath -PathType Leaf)) {
        Fail-Deploy "未找到部署入口文件：$indexPath。请确认 Vite 构建已生成 frontend\dist。"
    }

    $html = Get-Content -LiteralPath $indexPath -Raw
    $pattern = '(?i)(?:src|href)\s*=\s*["''](?<path>/assets/[^"''?#]+\.(?:js|css))(?:[?#][^"'']*)?["'']'
    $references = @([regex]::Matches($html, $pattern) | ForEach-Object { $_.Groups["path"].Value } | Sort-Object -Unique)
    if ($references.Count -eq 0) {
        Fail-Deploy "$indexPath 未引用任何 /assets/*.js 或 /assets/*.css 文件，无法确认构建产物完整性。"
    }
    return $references
}

function Assert-AssetsExist([string]$DistPath) {
    $references = @(Get-ReferencedAssets $DistPath)
    $missing = @()
    foreach ($reference in $references) {
        $relativePath = $reference.TrimStart('/').Replace('/', [IO.Path]::DirectorySeparatorChar)
        $assetPath = Join-Path $DistPath $relativePath
        if (-not (Test-Path -LiteralPath $assetPath -PathType Leaf)) {
            $missing += $reference
        }
    }
    if ($missing.Count -gt 0) {
        Fail-Deploy ("index.html 引用了不存在的资源：" + ($missing -join ", ") + "。请重新构建后再部署。")
    }
    return $references
}

try {
    if (-not (Get-Command "git" -ErrorAction SilentlyContinue)) {
        Fail-Deploy "未找到 git。请先通过 AIHome environment 的已登记入口确认 Git 可用。"
    }

    $DevRoot = (Resolve-Path -LiteralPath $DevRoot).Path
    if (-not (Test-Path -LiteralPath (Join-Path $DevRoot ".git"))) {
        Fail-Deploy "开发目录不是 Git 工作树：$DevRoot"
    }
    if (-not (Test-Path -LiteralPath $AppPath -PathType Container)) {
        Fail-Deploy "部署工作树不存在：$AppPath。可用 -AppPath 指定正确路径。"
    }
    $AppRoot = (Resolve-Path -LiteralPath $AppPath).Path
    if (-not (Test-Path -LiteralPath (Join-Path $AppRoot ".git"))) {
        Fail-Deploy "部署目录不是 Git 工作树：$AppRoot"
    }
    if ($DevRoot -eq $AppRoot) {
        Fail-Deploy "开发工作树与部署工作树不能是同一目录：$DevRoot"
    }

    $DevFrontend = Join-Path $DevRoot "frontend"
    $DevDist = Join-Path $DevFrontend "dist"
    $AppFrontend = Join-Path $AppRoot "frontend"
    $AppDist = Join-Path $AppFrontend "dist"
    $ViteCommand = Join-Path $DevFrontend "node_modules\.bin\vite.cmd"

    Write-Host "# NSFW Studio V2 前端部署" -ForegroundColor Cyan
    Write-Host "- dev: $DevRoot"
    Write-Host "- app: $AppRoot"
    Write-Host "- mode: $(if ($DryRun) { 'DryRun（只读计划）' } else { '执行' })"

    $devHead = Get-GitValue $DevRoot @("rev-parse", "HEAD") "无法读取 dev HEAD"
    $devStatus = Get-GitValue $DevRoot @("status", "--porcelain") "无法检查 dev 工作树状态"
    if (-not [string]::IsNullOrWhiteSpace($devStatus)) {
        Write-Warning "dev 工作树存在未提交改动；构建内容可能不完全对应 HEAD $devHead。将按要求继续。"
    } else {
        Write-Host "PASS dev 工作树干净。" -ForegroundColor Green
    }

    if ($DryRun) {
        Write-Host ""
        Write-Host "## 计划执行的命令"
        Write-Host ("$ " + (Format-Command "git" @("-C", $AppRoot, "fetch", "origin")))
        Write-Host ("$ " + (Format-Command "git" @("-C", $AppRoot, "status", "-sb")))
        Write-Host ("$ " + (Format-Command "git" @("-C", $AppRoot, "pull", "--ff-only")))
        if ($SkipBuild) {
            Write-Host "- 跳过 Vite 构建；要求现有 $DevDist 可用。"
        } else {
            Write-Host ("$ CI=true " + (Format-Command $ViteCommand @("build")))
        }
        Write-Host "- 写入 $DevDist\.build_commit = $devHead"
        Write-Host "- 删除 $AppDist"
        Write-Host "- 复制 $DevDist -> $AppDist"
        Write-Host "- 校验 app index.html 引用的 JS/CSS 资源均存在"
        Write-Host ""
        Write-Host "## DryRun 摘要"
        Write-Host "- dev HEAD: $devHead"
        Write-Host "- app HEAD: $(Get-GitValue $AppRoot @('rev-parse', 'HEAD') '无法读取 app HEAD')"
        Write-Host "- 文件修改: 0"
        exit 0
    }

    Invoke-CheckedCommand -Command "git" -Arguments @("-C", $AppRoot, "fetch", "origin") -FailureMessage "git fetch origin 失败；请检查网络、凭据和远端配置"
    $appStatus = Get-GitValue $AppRoot @("status", "-sb") "无法检查 app 工作树状态"
    Write-Host $appStatus
    $behindText = Get-GitValue $AppRoot @("rev-list", "--count", "HEAD..origin/main") "无法判断 app HEAD 是否落后 origin/main"
    $behindCount = 0
    if (-not [int]::TryParse($behindText, [ref]$behindCount)) {
        Fail-Deploy "git rev-list 返回了无法解析的落后提交数：$behindText"
    }
    if ($behindCount -gt 0) {
        Write-Warning "app 工作树落后 origin/main $behindCount 个提交；即将执行 fast-forward pull。"
    } else {
        Write-Host "PASS app 工作树未落后 origin/main。" -ForegroundColor Green
    }
    Invoke-CheckedCommand -Command "git" -Arguments @("-C", $AppRoot, "pull", "--ff-only") -FailureMessage "git pull --ff-only 失败；请检查 app 工作树是否有冲突、分支是否分叉"
    $appHead = Get-GitValue $AppRoot @("rev-parse", "HEAD") "无法读取更新后的 app HEAD"

    $buildWatch = [Diagnostics.Stopwatch]::StartNew()
    if ($SkipBuild) {
        if (-not (Test-Path -LiteralPath $DevDist -PathType Container)) {
            Fail-Deploy "使用 -SkipBuild 时要求 dev 构建目录已存在：$DevDist"
        }
        Write-Warning "已使用 -SkipBuild；脚本信任现有 dist 属于当前 dev HEAD，并将刷新 .build_commit。"
    } else {
        if (-not (Test-Path -LiteralPath $ViteCommand -PathType Leaf)) {
            Fail-Deploy "未找到 Vite：$ViteCommand。请先在 frontend 安装既有依赖。"
        }
        $hadCI = Test-Path Env:CI
        $oldCI = $env:CI
        $env:CI = "true"
        Push-Location $DevFrontend
        try {
            Invoke-CheckedCommand -Command $ViteCommand -Arguments @("build") -FailureMessage "Vite 前端构建失败"
        } finally {
            Pop-Location
            if ($hadCI) { $env:CI = $oldCI } else { Remove-Item Env:CI -ErrorAction SilentlyContinue }
        }
    }
    $buildWatch.Stop()

    if (-not (Test-Path -LiteralPath $DevDist -PathType Container)) {
        Fail-Deploy "构建结束后仍未找到 dev dist：$DevDist"
    }
    [IO.File]::WriteAllText((Join-Path $DevDist ".build_commit"), $devHead, [Text.Encoding]::ASCII)
    $null = Assert-AssetsExist $DevDist

    if (-not (Test-Path -LiteralPath $AppFrontend -PathType Container)) {
        Fail-Deploy "部署工作树缺少 frontend 目录：$AppFrontend"
    }
    if (Test-Path -LiteralPath $AppDist) {
        Remove-Item -LiteralPath $AppDist -Recurse -Force
    }
    Copy-Item -LiteralPath $DevDist -Destination $AppFrontend -Recurse -Force

    $assetReferences = @(Assert-AssetsExist $AppDist)
    $copiedFileCount = @(Get-ChildItem -LiteralPath $AppDist -Recurse -File).Count
    $resourceHashes = @()
    foreach ($reference in $assetReferences) {
        $relativePath = $reference.TrimStart('/').Replace('/', [IO.Path]::DirectorySeparatorChar)
        $assetPath = Join-Path $AppDist $relativePath
        $hash = (Get-FileHash -LiteralPath $assetPath -Algorithm SHA256).Hash.Substring(0, 12).ToLowerInvariant()
        $resourceHashes += "$(Split-Path -Leaf $assetPath)=$hash"
    }

    Write-Host ""
    Write-Host "## 部署摘要" -ForegroundColor Cyan
    Write-Host "- dev HEAD: $devHead"
    Write-Host "- app HEAD: $appHead"
    Write-Host ("- 构建耗时: {0:N2}s{1}" -f $buildWatch.Elapsed.TotalSeconds, $(if ($SkipBuild) { "（SkipBuild）" } else { "" }))
    Write-Host "- 资源 hash (SHA256/12): $($resourceHashes -join ', ')"
    Write-Host "- copied 文件数: $copiedFileCount"
    Write-Host "- 结果: PASS" -ForegroundColor Green
    exit 0
} catch {
    Write-Host ""
    Write-Host "[deploy_app_dist][FAIL] $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "请根据错误修复后重新运行；app frontend\dist 只有在构建成功后才会被替换。" -ForegroundColor Red
    exit 1
}
