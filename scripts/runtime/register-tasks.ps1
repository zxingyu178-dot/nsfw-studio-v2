# register-tasks.ps1 — 注册 NSFW Studio V2 后端/前端的计划任务身份。
#
# 模式与 projects/comfyui/runtime/register-task.ps1 一致：
#   - 手动生命周期（无触发器）、当前用户、非提权、隐藏窗口；
#   - MultipleInstances=IgnoreNew（重复触发安全）；
#   - 幂等（-Force）。
# 用途：解决"手动启动的进程随宿主会话被静默回收"的反复掉线问题。

#requires -Version 5.1
[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$runtimeDir = $PSScriptRoot
$powershell = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe'

function Register-StudioTask {
    param([string]$TaskName, [string]$ScriptPath)
    if (-not (Test-Path $ScriptPath)) { throw "script not found: $ScriptPath" }
    $argumentString = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}"' -f $ScriptPath
    $action = New-ScheduledTaskAction -Execute $powershell -Argument $argumentString -WorkingDirectory $runtimeDir
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet `
        -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 0 `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable:$false
    $task = New-ScheduledTask -Action $action -Principal $principal -Settings $settings
    if ($null -ne $task.Triggers) { $task.Triggers.Clear() }
    Register-ScheduledTask -TaskPath '\AIHome\' -TaskName $TaskName -InputObject $task -Force | Out-Null
    $registered = Get-ScheduledTask -TaskPath '\AIHome\' -TaskName $TaskName
    "Registered: \AIHome\{0}  State={1}" -f $TaskName, $registered.State
}

Register-StudioTask -TaskName 'NSFWStudioV2' -ScriptPath (Join-Path $runtimeDir 'run_backend.ps1')
Register-StudioTask -TaskName 'NSFWStudioV2Frontend' -ScriptPath (Join-Path $runtimeDir 'run_frontend.ps1')