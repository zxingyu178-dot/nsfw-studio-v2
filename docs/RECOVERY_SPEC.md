# RECOVERY_SPEC — 崩溃恢复规范（Phase 2 + 3，v0.4.0）

> 更新：2026-10-08。权威实现：`queue_worker.recover_interrupted()` 与
> `job_service.mark_interrupted_at_startup()`（应用启动时由 main.py 调用）。
> Phase 3：恢复粒度从 JobItem 提升到 **JobStageItem**（§八），并新增文件级兜底（§九）。

## 1. 原则

```text
后端启动 → 检测遗留 RUNNING Job / Stage / StageItem / Item → 一律转 INTERRUPTED
→ 禁止直接重新排队（绝不自动重跑）
→ 用 engine_job_id + 引擎 history + 实际输出文件核对（§三十八）
```

## 2. 启动流程（§三十七；Phase 3 §八）

```text
lifespan 启动：
  1. mark_interrupted_at_startup(session)
       RUNNING Job        → INTERRUPTED（记录 JOB_INTERRUPTED 事件）
       RUNNING Stage      → INTERRUPTED
       RUNNING StageItem  → INTERRUPTED
       RUNNING Item       → INTERRUPTED
  2. worker.recover_interrupted()   # 覆盖全部 INTERRUPTED Job（含上次 Worker 内部异常留下的现场）
       对每个 INTERRUPTED StageItem：
         ├─ 有 engine_job_id → adapter.get_job_status(engine_job_id)
         │    └─ succeeded → get_job_outputs（必须非空）
         │                  → 导入 DataRoot（必须返回 image_id）
         │                  → 才落 StageItem COMPLETED（ITEM_RECOVERED，计数重算）
         ├─ 无输出 / 引擎 unknown / 查询异常 / history 丢失
         │    → §九 文件级兜底：按 Studio 自己的输出命名扫描该 StageItem 的输出目录
         └─ 仍无法确认 → 保持 INTERRUPTED（可再核对，绝不自动重跑）
       无 engine_job_id 的 StageItem → 保持 INTERRUPTED
  3. 启动日志输出 recovered_items=N（= 恢复的 StageItem 数）
```

恢复的 COMPLETED 与正常执行共享同一完成条件（Phase 2.1 §一）：拿到输出 **且** 成功导入
Studio Image 才允许 COMPLETED，否则保持可恢复状态。

### 2.0 文件级兜底（Phase 3 §九）

- 输出命名包含 Studio 身份：`NSFWStudio/{job_short}/{stage}/{item_short}`（SaveImage 前缀，
  模板在 provider binding）；
- 只在 `comfyui.output_dir`（config.local.yaml，可选）之内扫描；目录不存在/未配置 → 空结果；
- **绝不扫描/接管用户普通 ComfyUI 图片**（只处理绑定模板推导出的 Studio 目录）；
- 即使 Studio 崩溃 + ComfyUI 重启 + `/history` 丢失，只要文件已写完仍可核对；
- 文件未写完（崩溃在生成中途）→ 扫描为空 → 保持 INTERRUPTED。

### 2.1 恢复后的 Job 终态归并（Phase 2.2 §2，P0；Phase 3 按 Stage 归并）

每个 Job 核对完成后执行 `_finalize_recovery()`：

```text
全部 Stage COMPLETED 且 completed_count == requested_count
    → Job COMPLETED + finished_at + JOB_RECOVERED_COMPLETED 事件
仍有 INTERRUPTED / QUEUED / FAILED → Job 保持 INTERRUPTED，completed_count 更新
```

禁止状态：**全部 Item COMPLETED 但 Job 仍 INTERRUPTED**；**已完成 Stage 被重新执行**。

### 2.2 运行中的取消 / 内部异常（Phase 2.2 + Phase 3 §0.1）

| 触发 | 行为 |
| --- | --- |
| 进程退出 / 停机超时（CancelledError） | 不写终态 → 现场保持 RUNNING → 下次启动恢复 |
| 代码级意外异常（非 EngineError） | Job/Stage/StageItem/Item 的 RUNNING → INTERRUPTED + queue_paused + WORKER_INTERNAL_ERROR |

禁止：取消/异常路径经 `finally` 把仍有未完成 Item 的 Job 误标为 COMPLETED。

注意：`get_job_status` 依赖 ComfyUI `/history`（只存已结束任务）——
引擎重启后丢失的任务返回 `unknown`，按"无法确认成功"处理（进入文件级兜底）。

## 3. 无法确认成功时的恢复路径（§三十八）

保持 INTERRUPTED（可恢复、不自动重跑）。用户在 UI 选择：

```text
POST /jobs/{id}/resume-remaining
  → 创建子 Job（source=resume, resume_of_job_id=原 Job）
  → 只创建「requested_count - completed」数量对应的新 Item
  → 重新执行使用新的随机 Seed（未完成 Item 的旧 Seed 不复用）
  → 已完成 Item 不重跑、图片不重复导入
```

UI 侧：右栏"当前任务"卡片对 FAILED / CANCELLED / INTERRUPTED 且未完成的任务
显示「继续剩余图片」按钮；支持取消 / 失败 / 中断三种来源。

## 4. 崩溃窗口的边界情况

| 场景 | 处理 |
| --- | --- |
| 提交后引擎已接单、进程崩溃 | engine_job_id 已持久化 → 恢复核对；succeeded 则导入图片 |
| 图片已生成但未入库（导入前崩溃） | history 仍可取回输出 → 恢复导入 |
| 引擎重启，任务丢失 | `unknown` → 保持 INTERRUPTED，用户续跑 |
| Worker 被强杀，Item 停在 RUNNING | 启动转 INTERRUPTED（Seed 保留但不复用） |
| 队列内存态暂停丢失 | 重启后队列自然恢复（Job 状态不受影响） |

## 5. 测试覆盖

- `tests/backend/test_job_queue.py`：遗留 RUNNING → 启动转 INTERRUPTED → 续跑子 Job；
- `tests/backend/test_phase22_consistency.py`：恢复归并（Case A 全部完成 → Job COMPLETED /
  Case B 无法确认 → Job INTERRUPTED + completed_count 正确）；
- `tests/backend/test_phase3_pipeline.py::test_stage2_crash_recovery`：Stage 2 崩溃恢复
  （按 StageItem 核对、高清正确挂回原图、已完成 Stage 不重跑）。

## 6. 不变量

- 恢复流程**绝不**修改已完成 Item 的 Seed、image_id、图片文件；
- 恢复导入走与正常执行相同的 `output_importer`（DataRoot 原子落盘 + DB 登记）；
- INTERRUPTED 是唯一由恢复写入的状态；其余状态语义见 docs/JOB_STATE_MACHINE.md。