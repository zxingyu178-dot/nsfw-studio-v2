# PROGRESS_EVENT_STORAGE_REPORT — v0.15.0（Task 7：瞬态 vs 持久分流）

## 1. 背景问题

采样阶段引擎每 **~200ms** 轮询一次。v0.15 之前每次轮询都 `INSERT ITEM_PROGRESS + COMMIT`，
导致：

- SQLite 写入被放大（单次任务可达数百次进度写入）；
- `job_events` 表被纯实时 tick 永久膨胀；
- 历史事件流里混入大量无审计价值的进度噪声。

## 2. 分流策略（v0.15）

| 通道 | 内容 | 是否写库 | 用途 |
|---|---|---|---|
| **瞬态 SSE**（`publish_transient_event`） | 每轮 `ITEM_PROGRESS`（含 step/progress） | **否**，只广播 | 前端 liveProgress 即时刷新 |
| **持久 `job_events`**（`record_event`） | 状态迁移、阶段开始/完成、Item 终态、取消、失败 | 是 | 审计、历史、恢复 |
| **`JobStageItem.progress` 列** | 最后归一化进度 | 是，但**节流** | 页面刷新 / 崩溃恢复后的最后进度 |

关键：**实时刷新走 SSE，恢复兜底走节流列，job_events 只记关键变化。**

## 3. 后端实现要点

`services/job_service.py`：

```python
def publish_transient_event(event_type, job_id, *, item_id=None, payload=None):
    """只广播 SSE，不写 job_events。"""
    _publish(event_type, job_id, item_id=item_id, payload=payload)
```

`workers/queue_worker.py`（每次轮询）：

1. **无条件**调 `publish_transient_event("ITEM_PROGRESS", ...)` 广播实时进度；
2. 维护 `_progress_state[item_id] = {"signature": (progress, step, stage), "last_write": ...}`；
3. 决定是否把 `progress` 列落库：
   - **签名相同** → 不写；
   - **节流窗口内**（默认 `progress_persist_interval_ms=330`，≈3 次/秒）且**未切 stage**
     → 暂不落库（实时层已广播，下次轮询补）；
   - **stage 切换** → 立即写；
   - 超过窗口 → 写；
4. Item 终态后 `_clear_progress_state` 清理节流状态。

即：progress 列持久化最多约 3 次/秒，而 SSE 维持 ~5 次/秒的实时观感，`job_events` 零 tick。

## 4. 前端配合

- `ITEM_PROGRESS` 仅更新内存 `liveProgressByItem`，不触发整页/列表回源；
- 页面刷新或 SSE 重连后，瞬态层为空，随下一次回源（JobDTO 的 progress 列）重建；
- 终态由持久事件驱动清理瞬态条目。

## 5. 收益

- 采样期间 `job_events` 不再写入 ITEM_PROGRESS（写入量从「每 tick 一行」降到「0 行」）；
- progress 列写入从 ~5/秒 降到 ≤3/秒；
- 实时观感不变（SSE 仍每 tick 推送），恢复能力不丢（节流列 + 终态事件）。

## 6. 验证

- 后端契约测试 `tests/backend/test_progress_step_contract.py` 断言：
  瞬态事件不产生 `job_events` 行；stage 切换/终态仍落库；progress 列节流。
- 前端 `jobStore.liveProgress.test.ts` 断言 ITEM_PROGRESS 不引发回源刷新、终态清理。
- 后端全量 **475 / 0 failures / 3 skipped**；前端 **311 passed**。

## 7. 无迁移

不新增表/列（`JobStageItem.progress` 已存在），仅改变写入策略，故无数据库迁移，沿用 schema 0018。
