#requires -Version 5.1
<#
.SYNOPSIS
    NSFW Studio V2 —— AIHome / ControlHub 环境解析器（可被 dot-source）。

.DESCRIPTION
    集中解析 ControlHub 官方 lifecycle CLI 所需的全部路径，消除脚本内硬编码：

      AIHOME_ROOT           AIHome 根目录（含 AIHOME.json）
      CONTROLHUB_ROOT       ControlHub 源码根（含 .venv）
      CONTROLHUB_PYTHON     ControlHub venv 的 python.exe（lifecycle CLI 解释器）
      CONTROLHUB_DATA_ROOT  ControlHub registry/data 根（作为 CLI --data-root 传入）

    解析优先级（高 -> 低，以此为准）：
      1. 环境变量注入：AIHOME_ROOT / CONTROLHUB_ROOT / CONTROLHUB_PYTHON / CONTROLHUB_DATA_ROOT
      2. 相对脚本/项目根推导（由本文件位置向上找 AIHome 根与 control-hub 兄弟目录）
      3. AIHOME.json（AIHome 根）权威登记；以及安装版权威数据目录
         %LOCALAPPDATA%\AIHomeControlHub\data
      4. configs/config.local.yaml 的 controlhub 段（仅最后兜底，且忽略 <LOCAL_ONLY> 占位）

    使用方式：
        . "$PSScriptRoot\runtime\resolve_aihome.ps1"
        if (-not $AIHOME_ENV.Ok) {
            # 失败处理：stop 归退出码 14；launch 非 0 并打印明确错误
            Write-Error "无法解析 ControlHub 环境：$($AIHOME_ENV.Error)"
        }
        $py   = $AIHOME_ENV.CONTROLHUB_PYTHON
        $data = $AIHOME_ENV.CONTROLHUB_DATA_ROOT

    失败语义：解析失败时**不抛异常**（dot-source 友好），而是设置 $AIHOME_ENV.Ok = $false
    并填入 Error；绝不静默用空路径继续。也可调用 Get-AIHomeEnv -ThrowOnFailure 让其显式 throw。
#>

# 在脚本顶层捕获本文件位置（在函数内 $MyInvocation 是函数作用域，会丢失脚本路径）。
$script:__ResolverDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Get-AIHomeEnv {
    [CmdletBinding()]
    param(
        [switch]$ThrowOnFailure
    )

    # 构造一个"失败"返回对象（Ok=$false），必要时 throw。
    function __NewError([string]$msg) {
        $o = [PSCustomObject]@{
            Ok                = $false
            Error             = $msg
            AIHOME_ROOT       = $null
            CONTROLHUB_ROOT   = $null
            CONTROLHUB_PYTHON = $null
            CONTROLHUB_DATA_ROOT = $null
            Source            = "none"
        }
        if ($ThrowOnFailure) { throw $msg }
        return $o
    }

    $pyCands    = New-Object System.Collections.Generic.List[string]
    $dataCands  = New-Object System.Collections.Generic.List[string]
    $rootCands  = New-Object System.Collections.Generic.List[string]
    $aihomeRoot = $null

    # ===== 1) 环境变量注入（最高优先级） =====
    if (-not [string]::IsNullOrWhiteSpace($env:CONTROLHUB_PYTHON)) { $pyCands.Add($env:CONTROLHUB_PYTHON) }
    if (-not [string]::IsNullOrWhiteSpace($env:CONTROLHUB_DATA_ROOT)) { $dataCands.Add($env:CONTROLHUB_DATA_ROOT) }
    if (-not [string]::IsNullOrWhiteSpace($env:CONTROLHUB_ROOT)) {
        $rootCands.Add($env:CONTROLHUB_ROOT)
        $pyCands.Add((Join-Path $env:CONTROLHUB_ROOT ".venv\Scripts\python.exe"))
        $dataCands.Add((Join-Path $env:CONTROLHUB_ROOT "data"))
    }
    if (-not [string]::IsNullOrWhiteSpace($env:AIHOME_ROOT)) { $aihomeRoot = $env:AIHOME_ROOT }

    # ===== 2) 相对脚本/项目根推导 =====
    #   <AIHOME_ROOT>/projects/<repo>/scripts/runtime/resolve_aihome.ps1
    $here        = $script:__ResolverDir            # scripts/runtime
    $scriptsDir   = Split-Path -Parent $here          # scripts
    $projectRoot = Split-Path -Parent $scriptsDir    # nsfw 仓库根
    if (-not $aihomeRoot) {
        $projectsDir = Split-Path -Parent $projectRoot   # .../projects
        $guessHome   = Split-Path -Parent $projectsDir   # AIHome 根
        if (Test-Path (Join-Path $guessHome "AIHOME.json")) { $aihomeRoot = $guessHome }
    }
    if ($aihomeRoot) {
        $homeParent  = Split-Path -Parent $aihomeRoot
        $guessChRoot = Join-Path $homeParent "control-hub"   # 与 AIHome 根同级的 control-hub
        $rootCands.Add($guessChRoot)
        $pyCands.Add((Join-Path $guessChRoot ".venv\Scripts\python.exe"))
        $dataCands.Add((Join-Path $guessChRoot "data"))
    }

    # ===== 3) AIHOME.json 权威登记 + 安装版权威数据目录 =====
    if ($aihomeRoot -and (Test-Path (Join-Path $aihomeRoot "AIHOME.json"))) {
        try {
            $json = Get-Content (Join-Path $aihomeRoot "AIHOME.json") -Raw -ErrorAction Stop |
                    ConvertFrom-Json -ErrorAction Stop
            $chNode = $null
            foreach ($p in @("controlhub", "control_hub", "ControlHub", "controlHub")) {
                if ($json.PSObject.Properties.Name -contains $p) { $chNode = $json.$p; break }
            }
            if ($chNode) {
                foreach ($pp in @("python_exe", "python", "pythonPath")) {
                    if ($chNode.PSObject.Properties.Name -contains $pp) {
                        $v = [string]$chNode.$pp
                        if (-not [string]::IsNullOrWhiteSpace($v)) { $pyCands.Add($v) }
                    }
                }
                foreach ($pd in @("data_root", "dataRoot", "data")) {
                    if ($chNode.PSObject.Properties.Name -contains $pd) {
                        $v = [string]$chNode.$pd
                        if (-not [string]::IsNullOrWhiteSpace($v)) { $dataCands.Add($v) }
                    }
                }
                foreach ($pr in @("root", "rootPath", "path")) {
                    if ($chNode.PSObject.Properties.Name -contains $pr) {
                        $v = [string]$chNode.$pr
                        if (-not [string]::IsNullOrWhiteSpace($v)) { $rootCands.Add($v) }
                    }
                }
            }
        } catch { }
    }
    # 安装版权威数据目录（不依赖 AIHOME.json 的具体 schema）
    if (-not [string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
        $dataCands.Add((Join-Path $env:LOCALAPPDATA "AIHomeControlHub\data"))
    }

    # ===== 4) configs/config.local.yaml 兜底（简单行解析，忽略 <LOCAL_ONLY> 占位） =====
    $localCfg = Join-Path $projectRoot "configs\config.local.yaml"
    if (Test-Path $localCfg) {
        try {
            $lines = Get-Content $localCfg -ErrorAction Stop
            $inBlock = $false
            foreach ($ln in $lines) {
                if ($ln -match '^\s*controlhub\s*:') { $inBlock = $true; continue }
                if ($inBlock -and $ln -match '^\S') { $inBlock = $false }  # 回到顶层
                if ($inBlock -and $ln -match '^\s*python_exe\s*:\s*(.+?)\s*$') {
                    $v = $Matches[1].Trim('"', "'", " ")
                    if ($v -notmatch 'LOCAL_ONLY') { $pyCands.Add($v) }
                }
                if ($inBlock -and $ln -match '^\s*data_root\s*:\s*(.+?)\s*$') {
                    $v = $Matches[1].Trim('"', "'", " ")
                    if ($v -notmatch 'LOCAL_ONLY') { $dataCands.Add($v) }
                }
            }
        } catch { }
    }

    # ---- 选定：第一个存在的 python / data 目录 ----
    $py = $null
    foreach ($c in $pyCands) {
        if (-not [string]::IsNullOrWhiteSpace($c) -and (Test-Path $c)) { $py = $c; break }
    }
    $data = $null
    foreach ($c in $dataCands) {
        if (-not [string]::IsNullOrWhiteSpace($c) -and (Test-Path $c)) { $data = $c; break }
    }

    if (-not $py) {
        return (__NewError "未能解析 ControlHub CLI 解释器(python)：环境变量/相对推导/AIHOME.json/local config 均未找到可执行的 python.exe")
    }
    if (-not $data) {
        return (__NewError "未能解析 ControlHub 数据目录(--data-root)：环境变量/相对推导/AIHOME.json/local config 均未找到存在的 data 目录")
    }

    # 由 python.exe 反推 CONTROLHUB_ROOT：向上找到含 .venv 的目录
    $root = $null
    $cur = Split-Path -Parent $py   # .../.venv/Scripts
    while ($cur) {
        if (Test-Path (Join-Path $cur ".venv")) { $root = $cur; break }
        $parent = Split-Path -Parent $cur
        if ($parent -eq $cur) { break }
        $cur = $parent
    }
    if (-not $root) {
        foreach ($c in $rootCands) {
            if (-not [string]::IsNullOrWhiteSpace($c) -and (Test-Path $c)) { $root = $c; break }
        }
    }

    return [PSCustomObject]@{
        Ok                = $true
        Error             = ""
        AIHOME_ROOT       = $aihomeRoot
        CONTROLHUB_ROOT   = $root
        CONTROLHUB_PYTHON = $py
        CONTROLHUB_DATA_ROOT = $data
        Source            = "resolved"
    }
}

# ---- dot-source 时自动解析，调用方直接读取下列变量 ----
$AIHOME_ENV = Get-AIHomeEnv
$AIHOME_ROOT          = $AIHOME_ENV.AIHOME_ROOT
$CONTROLHUB_ROOT      = $AIHOME_ENV.CONTROLHUB_ROOT
$CONTROLHUB_PYTHON    = $AIHOME_ENV.CONTROLHUB_PYTHON
$CONTROLHUB_DATA_ROOT = $AIHOME_ENV.CONTROLHUB_DATA_ROOT
