# 服务停摆问题排查与修复（2026-11-15）

## 现象

用户反馈「关了生图就停了」。实测：`127.0.0.1:8000`（Studio）与 `127.0.0.1:8767`（提交中转口 decode_door）均已无监听，`8188`（ComfyUI）仍在。队列停止推进。

## 根因（三层，逐层叠加）

1. **进程挂在终端窗口上**：Studio 与中转口此前由带窗口的启动方式拉起，窗口关闭后子进程随之退出。这是「关掉就停」的直接原因。
2. **carrier 启动超时中断了正常启动**：计划任务 `\AIHome\NSFWStudioV2` 的 carrier（`runtime\carrier.py`）原 `STARTUP_TIMEOUT_SEC = 90`。应用启动阶段要先做崩溃恢复：对每个 INTERRUPTED 孤儿任务逐个 `GET 8188/history/<id>` + `GET 8188/queue`（约 2s/个）。停机一次留下的孤儿动辄上百个，恢复耗时远超 90s → `FATAL startup timeout` → `CTRL_BREAK` + `taskkill /T /F`，启动被自己杀掉。
3. **一次重启＝整队作废**：启动流程 `mark_interrupted_at_startup` 会把全部 `QUEUED / RUNNING / PAUSED` 一次性转成 `INTERRUPTED`（v0.13.2 事故修复语义，不自动重排队）。因此每次 carrier 超时杀进程，队列就被清空一次，需用户显式打 `POST /api/v1/jobs/resume-interrupted` 才恢复。

## 处置

| 项 | 做法 |
|---|---|
| Studio 进程脱离窗口 | 交回计划任务 `\AIHome\NSFWStudioV2`（actions 为 `powershell -WindowStyle Hidden -File runtime\carrier.ps1`，无窗口；carrier 以 `CREATE_NO_WINDOW` 拉 uvicorn） |
| 启动超时放宽 | `runtime\carrier.py`：`STARTUP_TIMEOUT_SEC` 由 90 → 1800（30 分钟），并支持 `NSFW_STUDIO_STARTUP_TIMEOUT_SEC` 环境变量覆盖 |
| 清理孤儿现场 | 先用手动隐藏实例跑完一次崩溃恢复（清掉 RUNNING 孤儿），再停掉交回计划任务，使冷启动落在超时范围内 |
| 队列恢复 | `POST /api/v1/jobs/resume-interrupted` 一键恢复 |
| 中转口 | `python decode_door.py` 以 `Start-Process -WindowStyle Hidden` 启动，PID 独立于任何控制台窗口 |

## 验证结果

- 计划任务冷启动：`04:08:49 carrier starting` → `04:09:41 app ready version=0.37.0`，**51 秒**，未再触发超时。
- `GET /api/v1/health` → `{"status":"ok","version":"0.37.0"}`；ControlHub `lifecycle_cli status nsfw-studio-v2` → `state=online`。
- Worker 实际推进：RUNNING 任务 `completed_count` 4 → 5（50 秒），ComfyUI 队列 run=1、显存 1.2G/6.0G。
- `8767` 恢复监听，返回「纯转发模式」。
- 队列恢复后本批次统计：QUEUED 163 / COMPLETED 88 / CANCELLED 23 / FAILED 2 / INTERRUPTED 1。

## 遗留与注意

1. **计划任务无触发器（Triggers=0）**：只能按需启动（ControlHub / `scripts\launch_studio.ps1` / `Start-ScheduledTask`）。**重启电脑后不会自启**，需手动或由 ControlHub 触发。若要开机自启，属于改 ControlHub 托管生命周期配置，需走 ControlHub 合同，不在本次临时修复范围。
2. `resume-interrupted` 是**全库**恢复：本次把 2026-11-08 起的 400 余个历史 INTERRUPTED 任务一并重新排队，今日 40 段（`mx-01..40`）被排到队尾（queue_position 548–587）。若要让今日批次优先，可走 `POST /api/v1/queue/reorder`（拖拽排序唯一事实源仍是 queue_position）。
3. carrier 超时常量属于本地 runtime 偏离，`controlhub\onboarding-staging\nsfw-studio-v2\carrier\carrier.py` 模板仍是 90，后续接 ControlHub 官方更新时需把 1800 与「恢复耗时应纳入启动预算」一并回流模板，否则会被覆盖回 90。
4. 每次正常重启也会把队列打成 INTERRUPTED（产品既有语义），重启后必须记得打一次 `resume-interrupted`，否则队列是空的、表现为「停了」。
