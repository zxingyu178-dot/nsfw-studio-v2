# RECOVERY_SPEC — 崩溃恢复规范（Phase 2，v0.3.0）

> 更新：2026-10-07。权威实现：`queue_worker.recover_interrupted()` 与
> `job_service.mark_interrupted_at_startup()`（应用启动时由 main.py 调用）。

## 1. 原则

```text
后端启动 → 检测遗留 RUNNING Job / JobItem → 一律转 INTERRUPTED
→ 禁止直接重新排队（绝不自动重跑）
→ 用 engine_job_id + 引擎 history + 实际输出文件核对（§三十八）
```

## 2. 启动流程（§三十七）

```text
lifespan 启动：
  1. mark_interrupted_at_startup(session)
       RUNNING Job   → INTERRUPTED（记录 JOB_INTERRUPTED 事件）
       RUNNING Item  → INTERRUPTED
  2. worker.recover_interrupted()
       对每个有 engine_job_id 的 INTERRUPTED Item：
         adapter.get_job_status(engine_job_id)
           ├─ succeeded → get_job_outputs（必须非空）→ 导入 DataRoot（必须返回 image_id）
           │              → 才落 Item COMPLETED（IMAGE_RECOVERED，job.completed_count 重算）
           │              §一：无输出 / 导入失败 / image_ids 为空 → 保持 INTERRUPTED 可再核对
           └─ 其他（running/failed/unknown/查询异常）→ 保持 INTERRUPTED
       无 engine_job_id 的 Item → 保持 INTERRUPTED
  3. 启动日志输出 recovered_items=N
```

恢复的 COMPLETED 与正常执行共享同一完成条件（Phase 2.1 §一）：拿到输出 **且** 成功导入
Studio Image 才允许 COMPLETED，否则保持可恢复状态。

注意：`get_job_status` 依赖 ComfyUI `/history`（只存已结束任务）——
引擎重启后丢失的任务返回 `unknown`，按"无法确认成功"处理。

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

## 5. 测试覆盖（tests/backend/test_job_queue.py）

- `test_worker_restart_marks_interrupted`：模拟遗留 RUNNING → 启动转 INTERRUPTED；
- `test_recover_imports_finished_item`：history 确认成功 → 导入图片 → Item COMPLETED；
- 恢复后不自动重排（不给后续 Job 造成误伤）。

## 6. 不变量

- 恢复流程**绝不**修改已完成 Item 的 Seed、image_id、图片文件；
- 恢复导入走与正常执行相同的 `output_importer`（DataRoot 原子落盘 + DB 登记）；
- INTERRUPTED 是唯一由恢复写入的状态；其余状态语义见 docs/JOB_STATE_MACHINE.md。