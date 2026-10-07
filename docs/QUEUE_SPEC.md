# QUEUE_SPEC — 单队列规范（Phase 2，v0.3.0）

> 更新：2026-10-07。权威实现：`backend/app/workers/queue_worker.py`（SingleQueueWorker）、
> `backend/app/services/job_service.py`（排序 / 队列查询）。

## 1. 只有一个逻辑队列（§十四）

```text
系统 = 一个队列 + 一个 Worker，串行执行。
禁止：多 Worker / GPU 并行 / Job 并行 / 普通+优先双队列池。
```

- Worker 只消费**已持久化**的 Job；Job 创建只发生在 `JobService`（POST /jobs）；
- Worker 循环：`_pick_next_job()` → `process_job(job_id)` → 空转 sleep(300ms)。

## 2. 排序 = queue_position（§十五、§十六；Phase 2.1 §六 收紧）

```text
普通提交（queue_mode=normal）：追加到等待队列尾部
  当前 A │ 等待 B C │ 新 X → B C X

优先提交（queue_mode=next）：插到等待队列最前（只通过插入位置实现）
  当前 A │ 等待 B C │ 优先 X → X B C

拖拽排序（POST /queue/reorder）：仅 QUEUED Job 可排序；
  请求必须覆盖全部等待任务（一一对应校验，否则 400 REORDER_INVALID）；
  RUNNING / PAUSED 不可移动。
```

**唯一执行顺序事实源 = `queue_position`**（Phase 2.1 起）：

- Worker 领取、GET /queue、reorder 三处统一 `ORDER BY queue_position, created_at`；
- `priority` 字段保留用于历史/显示，**任何排序逻辑禁止引用它**；
- 用户把 next Job 拖到普通 Job 之后 → 队列显示与实际执行顺序都必须遵守拖拽结果。

## 3. 暂停 / 继续 / 取消的队列行为

| 操作 | 队列影响 |
| --- | --- |
| 暂停 QUEUED Job | 立即 PAUSED，从等待队列移出（`pause_job`） |
| 暂停 RUNNING Job | `pause_requested`；当前 Item 完成后 Job→PAUSED |
| 继续（resume） | `PAUSED → QUEUED`，重新排到队尾（§十八） |
| 取消 | QUEUED/PAUSED 立即 CANCELLED；RUNNING 在 Item 边界取消 |

## 4. 系统性失败 → 队列自动暂停（§二十一）

模型缺失 / Workflow 错误 / OOM / 磁盘不可写 / Engine 整体离线时：

```text
当前 Job FAILED（当前 Item FAILED，未执行 Item CANCELLED）
+ Worker 内存态 queue_paused = true（原因写入 queue_paused_reason）
+ 不再领取后续 Job（禁止把后面的队列全部跑失败）
```

- `GET /api/v1/queue` 的 `worker.queue_paused / queue_paused_reason` 暴露该状态；
- 用户处理问题后 `POST /api/v1/queue/resume` 恢复；
- 队列暂停是**内存态**（重启后自然恢复运行，Job 本身状态不受影响）。

## 5. 队列查询（GET /api/v1/queue）

```jsonc
{
  "worker": { "running": true, "queue_paused": false, "queue_paused_reason": null,
              "current_job_id": "job_...", "adapter": "comfyui" },
  "running": { /* Job（含 items） */ } | null,
  "queued":  [ { /* Job */ } ],   // 按 priority/queue_position 排序
  "paused":  [ { /* Job */ } ]
}
```

## 6. 前端（§五十四）

队列 UI 只在生成页右栏（不单独增加一级"队列"页面）：
正在执行（当前任务卡片）+ 等待任务列表（暂停 / 继续 / 取消 / 优先 / 拖拽排序）。
"优先"按钮 = 将该 Job 移到等待列表最前（等价 reorder）。

## 6.1 Worker 取消语义（Phase 2.2）

Worker 任务被取消（进程退出 / 停机超时）或意外异常时**不写 Job 终态**：
Job/Item 保持 RUNNING 落库，由下次启动恢复流程接管（详见 RECOVERY_SPEC §2.2）。
禁止经 `finally` 把仍有未完成 Item 的 Job 误标为 COMPLETED。

## 7. 并发与一致性

- `_pick_next_job` 与状态操作都在独立会话中完成；Job 状态更新是单事务；
- Worker 串行执行保证同一时刻最多一个 RUNNING Job；
- 排序接口全量校验等待列表，防止客户端基于过期列表造成位置歧义。