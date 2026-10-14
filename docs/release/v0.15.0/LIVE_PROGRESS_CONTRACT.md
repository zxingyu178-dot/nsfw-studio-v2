# LIVE_PROGRESS_CONTRACT — v0.15.0（真实 Job / Stage / Step）

本文档定义前端 HUD 与后端引擎之间的**实时进度合同**（Task 6/9/13）。

## 1. 数据流

```
ComfyUI（每 ~200ms 轮询）
  └─ EngineJobStatus { progress, stage, step, max_step }
       └─ queue_worker 每轮发 ITEM_PROGRESS（transient SSE）
            └─ SSE JobEvent {type, job_id, item_id, payload, time}
                 └─ jobStore.handleJobEvent → liveProgressByItem[item_id]（纯内存）
                      └─ CanvasStage 取 hudSnapshot(job, liveByItem)
                           └─ ProgressHUD 渲染 overall / stage / step / elapsed
```

持久事实源仍是 **JobDTO**（Job / Stage / Item 计数），实时 step/progress 仅来自瞬态层。

## 2. SSE 事件结构

```json
{
  "type": "ITEM_PROGRESS",
  "job_id": "<job uuid>",
  "item_id": "<job_item uuid>",
  "payload": {
    "progress": 0.57,
    "stage": "sampling",
    "stage_index": 0,
    "step": 17,
    "max_step": 30
  },
  "time": "2026-10-14T10:00:00Z"
}
```

- `item_id` = `job_item_id`，前端按此挂到对应 Stage Item。
- `progress`：0.0~1.0 归一化；引擎不支持时为 `null`。
- `step` / `max_step`：**仅采样型工作流有值**（如 KSampler 17/30）。

## 3. 后端真实 Step 合同（`EngineJobStatus`）

`backend/app/engine/base.py`：

- `progress: float | None`：0.0~1.0；step 存在时 = step/max_step。
- `step: int | None` / `max_step: int | None`：采样当前/总步数；非采样阶段为 `None`。
- ComfyUI 适配器把 progress value 映射为 step/max_step；
  `execution_start / execution_success / execution_error` 时**清空 step/max_step**，
  避免 UI 终态停在 25/25。
- 由 `tests/backend/test_progress_step_contract.py`（+292 行）契约保证。

## 4. 前端 LiveProgress（瞬态）

`stores/jobStore.ts`：

```ts
interface LiveProgress {
  progress?: number | null      // 0~1
  engineStage?: string | null   // sampling / save_image / upscale …
  stageIndex?: number | null
  step?: number | null
  maxStep?: number | null
  updatedAt: number
  jobId?: string
}
```

- 存于 `liveProgressByItem: Record<itemId, LiveProgress>`，**纯内存**，不持久化。
- `ITEM_PROGRESS` 只更新该 map，**不触发** GET /queue、/engine/status、/job 的整页刷新。
- Item 终态 → `clearLiveProgressItem`；Job 终态 → `clearLiveProgressForJob`；
  回源后 `pruneLiveProgress` 清理已不在活跃集合的条目。

## 5. HUD 总进度加权（`workbenchProgress.ts`）

- **总进度不能用“当前 running stage 的 progress”冒充整个 Job。**
- `total = Σ stage.total_count`；
  `done = Σ stage.completed_count + 当前 RUNNING item 的 clamp(progress,0,1)`；
  `overall = round(done/total*100)`。
- `hudSnapshot` 输出：overall、第 N/M 张、阶段 x/y、阶段名、真实 step/maxStep、
  startedAt（用于 Elapsed）。

## 6. Upscale 不伪造 Step（硬约束）

- `UPSCALE_MODULES = {'upscale'}`；
- 当 running stage 是 upscale，或 step/maxStep 缺失 / maxStep<=0，`indeterminate=true`；
- HUD 对该阶段只显示“**高清放大 · 处理中**”，**不显示任何编造的 Step x/y**。
- 由 `workbenchProgress.test.ts` 专测覆盖（含 9.2/16 浮点边界）。

## 7. 覆盖

- 后端：`test_progress_step_contract.py`（5 个契约：映射、清空、归一化、事件分流等）。
- 前端：`jobStore.liveProgress.test.ts`、`workbenchProgress.test.ts`。
- 真机：未执行（ComfyUI offline），见 `UI_VISUAL_ACCEPTANCE.md` §5。
