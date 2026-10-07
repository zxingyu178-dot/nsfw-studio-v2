# JOB_STATE_MACHINE — Job / JobItem 状态机（Phase 2 + 2.1，v0.3.1）

> 更新：2026-10-07。权威实现在 `backend/app/services/job_service.py` 与
> `backend/app/workers/queue_worker.py`；数据库状态是唯一事实源（SSE 只是通知）。

## 1. Job 状态（固定 7 个，禁止扩展）

```text
QUEUED → RUNNING → COMPLETED
           │  ├──→ FAILED        （系统性失败或 Item 失败耗尽）
           │  ├──→ CANCELLED     （终态；已完成图片保留）
           │  └──→ PAUSED        （安全暂停：当前 Item 完成后）
QUEUED ──→ PAUSED ──→ QUEUED   （继续：已完成 Item 绝不重跑）
RUNNING ──→ INTERRUPTED         （仅启动崩溃恢复写入）
```

- 没有 `PARTIAL_COMPLETED`：部分成功由 **JobItem 统计**表达
  （例：任务 FAILED，成功 18 / 20，失败 2）；
- `COMPLETED / FAILED / CANCELLED` 为终态；`INTERRUPTED` 可经
  `POST /jobs/{id}/resume-remaining` 创建**子 Job** 续跑（§二十），原 Job 不变；
- 禁止 `CANCELLED → RUNNING`。

## 2. 暂停语义（§十七，安全暂停）

```text
POST /jobs/{id}/pause
  → pause_requested = true
  → 当前 JobItem 继续完成（不强杀正在生成的图片）
  → Worker 不再领取下一个 Item
  → Job = PAUSED（记录 JOB_PAUSED 事件）
```

- `QUEUED` 状态暂停：不经过 Worker，直接落 `PAUSED`；
- `PAUSED` 继续：`pause_requested=false`，`status=QUEUED`，重新排队（队尾）；
- 已完成的 Item（`COMPLETED`）在恢复后进入 Worker 时被 `item.status != QUEUED`
  守卫跳过，绝不重新执行。

## 3. 取消语义（§十九）

```text
POST /jobs/{id}/cancel
  → cancel_requested = true
  → QUEUED / PAUSED：立即 CANCELLED（未执行 Item → CANCELLED）
  → RUNNING：Worker 在 Item 边界处理；正在执行的 Item 请求 Adapter 安全取消
    （ComfyUI：/queue delete + /interrupt；取消失败则完成当前 Item 后结束）
  → 已经生成图片保留
  → Job 终态 CANCELLED
```

## 4. JobItem 状态（6 个，无 PAUSED）

`QUEUED → RUNNING → COMPLETED | FAILED | CANCELLED`，崩溃恢复写入 `INTERRUPTED`。
暂停发生在 Job / Worker 层，不在 Item 层。

- Item 失败：记录 `error_type / error_message / retry_count`，Job 由 `_finish_job`
  统计（存在 FAILED Item → Job FAILED）；
- 系统性失败（`_systemic_failure`）：当前 Item FAILED、未执行 Item CANCELLED、
  Job FAILED + **队列自动暂停**（等待用户处理）。

## 5. Seed 规则（§九）

- 每张图独立随机 Seed（`random.SystemRandom`），**Item 真正开始执行时**才分配；
- `seed_mode=fixed`（"使用此图 Seed"/集成测试）：`seed = base + item_index`；
- 范围校验在 EngineAdapter / binding（`seed_range`）侧完成；
- 已成功 Item 的 Seed 永远保留；未完成 Item 重跑（续跑子 Job）生成新随机 Seed。

## 6. 事件（JobEvent，仅追加）

| 事件 | 时机 |
| --- | --- |
| JOB_CREATED | JobService 创建 Job + N 个 Item |
| JOB_STARTED / JOB_PAUSED / JOB_PAUSE_REQUESTED / JOB_RESUMED | 状态操作 |
| JOB_CANCEL_REQUESTED / JOB_CANCELLED | 取消 |
| ITEM_STARTED（含 seed）/ ITEM_PROGRESS / ITEM_COMPLETED（含 image_ids）/ ITEM_FAILED / ITEM_CANCELLED | Item 生命周期 |
| JOB_COMPLETED / JOB_FAILED / JOB_INTERRUPTED / ITEM_RECOVERED | 终态与恢复 |
| JOB_UPDATED | 队列位置 / 状态变更的补充通知 |

同一事件同时：写入 `job_events` 表 + 广播到 SSE（`GET /api/v1/events/jobs`）。
客户端收到任何事件后都必须回源 GET 状态（SSE 不提供历史回放）。

## 7. 幂等（§十二）

- `(source, client_request_id)` UNIQUE：相同来源 + 相同请求 ID 重复提交
  **返回原 Job**（响应 `idempotent_replay=true`），不再创建；
- 并发窗口由 IntegrityError 兜底：回查已存在 Job 返回，不重复插入。

## 8. 磁盘空间（§五十七）

创建 Job 前检查 DataRoot：`< 严重阈值` → 拒绝（`DISK_SPACE_CRITICAL`）；
`< 警告阈值` → 允许但响应 `disk_space="warning"`（前端提示）。阈值在 storage 配置。

## 9. Item 完成条件（Phase 2.1 §一，P0 修复后固定）

```text
Engine succeeded
  ↓ 必须成功取得 outputs 且非空
  ↓ 必须成功导入 ≥1 个 Studio Image（image_ids 非空）
  → 才允许 Item = COMPLETED（image_id 必非空）
```

任一步失败一律：

```text
get_job_outputs 无结果 / 返回空     → OUTPUT_MISSING → Item FAILED
get_job_outputs 抛异常              → 按异常自身的 error_type 分类
output_importer 抛异常              → STORAGE_ERROR → Item FAILED
导入返回空 image_ids                → STORAGE_ERROR → Item FAILED
```

统一后果：Item FAILED、Job 最终 FAILED、`completed_count` 不增加、`image_id = null`。
**禁止状态：`COMPLETED` 且 `image_id = null`**（崩溃恢复的 `ITEM_RECOVERED` 路径同样遵守）。

## 10. Seed 与续跑（Phase 2.1 §五，固定）

- 每张图执行时分配 Seed（random：SystemRandom；fixed：base + item_index）；
- **续跑（resume-remaining）一律使用新随机 Seed**：子 Job 快照
  `count = remaining, seed_mode = random, seed = null`（workbench_snapshot 与
  generation_settings_json 同步重建）；
- 原 Job 的 workbench_snapshot 永不修改；已成功 Item 的 Seed 永远保留。