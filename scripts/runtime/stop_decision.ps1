#requires -Version 5.1
<#
.SYNOPSIS
    NSFW Studio V2 —— 停止结果 -> 退出码 的纯决策函数（无副作用，可单测）。

.DESCRIPTION
    将"逐目标停止结果 + 端口核验结果"映射为 stop_studio.ps1 的最终退出码。
    把决策逻辑从真实 CLI/端口副作用中抽离出来，便于在 mock 环境下穷举测试。

    退出码（务必逐字一致）：
        0  全部目标成功停止、端口符合预期
        10 Studio Backend(nsfw-studio-v2 / 8000) 停止失败
        11 ComfyUI(comfyui / 8188) 停止失败
        12 Mobile Review(8767) 子运行时未随后端退出（端口仍占用）
        13 停止后核验：托管端口(8000/8188)仍被占用
        14 ControlHub 调用失败（resolver 解析失败 / lifecycle CLI 无法调用）
        15 外部非 owned ComfyUI（EXTERNAL_NOT_OWNED，partial success，非 0，绝不强杀）

    决策优先级（从高到低，取第一个命中者；使行为可预测、可测）：
        14  resolver / CLI 致命
      > 15  外部非 owned ComfyUI 未停
      > 13  托管端口(8000 / 8188 owned)仍被占用
      > 12  Mobile Review(8767) 仍被占用
      > 10  Studio Backend CLI 明确失败
      > 11  ComfyUI CLI 明确失败
      >  0  全成功

    注：当 ComfyExternal(15) 命中时，8188 被外部实例占用属预期，不再计入 13。
#>

function Get-StudioStopExitCode {
    [CmdletBinding()]
    param(
        [bool]$FatalCli,          # resolver 失败 / python 缺失 / CLI 进程无法启动 -> 14
        [bool]$StudioFailed,      # nsfw-studio-v2 stop 返回非 0 且非未注册(exit 2) -> 10
        [bool]$ComfyFailed,       # comfyui stop 返回非 0 且非未注册(exit 2) -> 11
        [bool]$ComfyExternal,     # comfyui 未注册/未批准(exit 2)，外部非 owned -> 15
        [bool]$Port8000Occupied,  # 停止核验后 8000 仍监听 -> 13
        [bool]$Port8188Occupied,  # 停止核验后 8188 仍监听（owned 场景）-> 13
        [bool]$Port8767Occupied   # 停止核验后 8767(Mobile) 仍监听 -> 12
    )

    if ($FatalCli)         { return 14 }
    if ($ComfyExternal)     { return 15 }
    if ($Port8000Occupied -or $Port8188Occupied) { return 13 }
    if ($Port8767Occupied) { return 12 }
    if ($StudioFailed)     { return 10 }
    if ($ComfyFailed)      { return 11 }
    return 0
}

# 退出码常量（供脚本与测试引用，避免魔法数字散落）
$script:EXIT_OK            = 0
$script:EXIT_STUDIO_FAIL  = 10
$script:EXIT_COMFY_FAIL    = 11
$script:EXIT_MOBILE_FAIL   = 12
$script:EXIT_PORT_OCCUPIED = 13
$script:EXIT_CLI_FATAL     = 14
$script:EXIT_EXTERNAL_COMFY = 15
