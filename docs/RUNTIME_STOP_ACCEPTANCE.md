# NSFW Studio v0.14.1 — 真机启停 / 失败路径 / 恢复 验收报告（RUNTIME STOP ACCEPTANCE）

- 验收日期：2026-10-14（UTC+8）
- 验收对象：日用实例 `projects/nsfw-studio-v2-app`，代码 `6459163`（分支 `feature/v0.14.1-fix-hardening`）
- 运行环境：Windows 本机，PowerShell 5.1；NVIDIA GeForce RTX 3060 Laptop GPU（6GB VRAM），系统内存 16GB
- 运行对象：`nsfw-studio-v2`=Studio Backend（8000）；`comfyui`=ComfyUI（8188，owned）；8767=Mobile Review Bridge（随 Studio 退出，按需启动）
- 生命周期唯一 owner：ControlHub 官方 lifecycle CLI（`D:\control-hub\.venv\Scripts\python.exe -m control_hub.lifecycle_cli <verb> <id> --data-root C:\Users\30566\AppData\Local\AIHomeControlHub\data`）

## 总体结论

| 用例 | 内容 | 结果 |
|---|---|---|
| R1 | 一键启动：Studio + Comfy 在线，/health=0.14.1，ControlHub 两对象 online | PASS |
| R2 | 健康停止：三端口 FREE，exit 0，输出"后台资源已释放" | PASS |
| R3 | 失败注入（CLI 无法执行）：exit 13，无"已释放"，服务真实存活（PID 不变） | PASS |
| R4 | 外部非 owned Comfy（15）：纯逻辑由 PS harness 覆盖；真机未制造第二实例 | COVERED（harness） |
| R5 | 恢复健康 + 一次真实生成：出图成功，renditions 齐备，健康 0.14.1，记录 PID/RSS | PASS |

## R1：一键启动（健康）

- 经生产计划任务 `\AIHome\NSFWStudioV2` 启动 Studio Backend；暖启动约 **48–65s** 就绪。
- `/api/v1/health`：`{"status":"ok","version":"0.14.1"}`。
- 端口核验：8000 LISTEN（pid=186196 / 后一次启动 pid=182424），8188 owned Comfy LISTEN（pid=163660 / 后一次 pid=182856），8767 平时 FREE（移动审核桥按需起）。
- ControlHub status：`nsfw-studio-v2 state=online`、`comfyui state=online`。
- 备注：首次冷启动在内存压力（系统可用内存一度 ~2.3GB，load 85%）下，Studio 后端在 ~97s 才进入启动引导，被 carrier 内置 90s 启动超时杀过一次；缓存转暖后重试约 50–65s 稳定就绪。属环境性冷启动时序，未改 carrier.py。

## R2：健康停止

- 运行 `scripts/stop_studio.ps1`（v0.14.1）：best-effort 队列暂停 / 手机桥停止 → lifecycle `stop nsfw-studio-v2` → lifecycle `stop comfyui`。
- 端口核验：**8000 FREE / 8767 FREE / 8188 FREE**。
- 逐目标：Studio Backend STOPPED、ComfyUI STOPPED、Mobile Review STOPPED。
- 最终输出：`后台资源已释放。（退出码 0）`，**exit 0**。
- 复跑多次均稳定 exit 0。

## R3：失败注入（用户红线，真机实测）

- 以 `CONTROLHUB_PYTHON` 指向项目 venv python（其中无 `control_hub` 模块，实测 `ModuleNotFoundError`，exit 1）运行 `stop_studio.ps1`。
- 逐目标：Studio Backend FAILED、ComfyUI FAILED。
- 端口：`8000 OCCUPIED（STOP_TIMEOUT）`、`8188 OCCUPIED（STOP_TIMEOUT）`、`8767 FREE`。
- 最终输出：`后台资源释放未完成（退出码 13）`，并逐条列出 8000/8188 仍占用、Studio/Comfy 停止失败；**全文无"已释放"**。
- 注入后核验：8000/8188 仍 LISTEN，且 PID 与注入前完全一致（186196 / 163660）→ 服务真实存活，失败 CLI 未造成任何误停。
- 另有隔离测试（脚本拷到无 AIHOME 引导、无环境变量的 scratch 目录）：resolver 找不到解释器 → 干净返回 **exit 14**。

## R4：外部非 owned Comfy（15）

- 真机未制造第二个 Comfy 实例（避免 GPU OOM 与端口冲突）。
- 退出码 15 的纯逻辑（`ComfyExternal` 恒为 15、此时 8188 被外部占用属预期不计 13、外部实例不强杀）已由 PowerShell harness 的多条用例覆盖（"外部 Comfy -> 15"、"15 优先于 13"、"外部 Comfy + 8188 占用 -> 15（非 13）"）。
- 红线"不强杀外部实例"由 stop 脚本 EXTERNAL 分支（exit 2 → EXTERNAL_NOT_OWNED → 不调任何 kill）保证。

## R5：恢复健康 + 一次真实生成

- 失败注入后重新启动生产计划任务，Studio 暖启动约 48s，/health=0.14.1。
- 启动 Comfy（`\AIHome\ComfyUI`），提交一次真实文生图任务（832×1216，count=1，structured prompt，seed 随机）。
- 结果：任务 **COMPLETED**，生成图 `img_3479793b-4385-46ce-aecc-81895b8f9358`（832×1216）。
- Comfy 历史：`status_str=success, completed=True`；采样 25/25 步（约 1m39s），随后 VAE 解码。
- renditions 实测：preview HTTP 200（webp，136KB）、thumbnail HTTP 200（webp，28KB）、content HTTP 200（原始 PNG，1.73MB）。
- 生成后 PID/RSS：8000 pid=182424 RSS≈63.6MB（生成后回落）；8188 pid=182856 RSS≈3.4GB（模型仍驻留）。
- 时序如实记录：GGUF Q4 扩散模型与文本编码器的冷加载占了主要时间（本次冷加载约 10 分钟，系统内存压力下文本编码器驻 CPU 较慢），实际采样约 1m39s；这是已知 GGUF Q4 / 6GB LOW_VRAM 行为。

## 真机验收过程中发现并修复的两个仅真机可暴露的 runtime 缺陷

1. **resolver data-root 错位**（commit `97e8fd6`）：resolver 相对推导曾把源码树 `D:\control-hub\data`（仅 12 对象、不含 nsfw-studio-v2）作为 data 首选，压过安装版 `%LOCALAPPDATA%\AIHomeControlHub\data`（13 对象、含已审批 v2），导致 CLI 返回 unknown_integration。修复：data-root 与源码根解耦，安装版 LOCALAPPDATA 优先、源码根 data 仅作便携兜底；新增合同测试锁定候选顺序。
2. **stop 误报 Comfy 失败**（commit `6459163`）：v0.14.1 重写把 CLI 非 0 一律当 FAILED，但 ControlHub `stop` 偶发 `adapter_failed`（其内部确认窗口早于进程真正退出），随后端口核验已 FREE、再查 status 为 offline，脚本却误报 exit 11。修复：新增纯函数 `Resolve-TargetStopState`，以"端口核验为最终事实"调和——CLI FAILED + 端口 FREE → STOPPED（仅告警），CLI FAILED + 端口仍占用 → FAILED；Studio/Comfy 均在端口核验后调和。

## 未覆盖 / 如实说明

- 真机未制造第二个 Comfy 实例来验证 exit 15（R4 由 harness 覆盖）。
- 真机未重复完整的 pause/resume 长流程；未真实点"清理陈旧任务"。
- 冷启动在内存压力下接近 carrier 90s/Comfy 420s 临界值（本次暖启动均通过，首次冷启 Studio 被 90s 杀过、一次 Comfy 冷启被 420s 判 timeout），属环境性时序，未改 carrier.py / control-hub.json（后者为注册清单，改动涉审批）。
