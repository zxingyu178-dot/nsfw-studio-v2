# JOB_STATE_MACHINE — Job / JobItem 状态机（Phase 2 + 2.1 + 2.2 + 3，v0.4.0）

> 更新：2026-10-08。权威实现在 `backend/app/services/job_service.py` 与
> `backend/app/workers/queue_worker.py`；数据库状态是唯一事实源（SSE 只是通知）。
> Phase 3 新增 JobStage / JobStageItem，见 `PIPELINE_STATE_MACHINE.md` 与 `PIPELINE_V2.md`；
> Phase 4 起 `JobItem.seed` 仅为"基础生成的主要 Seed / UI 快捷字段"，
> **真实溯源以 `StageItem.seed` 为准**（uses_seed=false 的 Stage 为 NULL，见 MODULE_IO_CONTRACT.md）。

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

- **Phase 3 多阶段语义**：JobItem = 用户要求的"最终逻辑结果"；
  非最后 Stage 完成时保持 `RUNNING`（"阶段间进行中"，image_id = 当前输出）；
  最后 Stage 完成才 `COMPLETED`；Job FAILED/CANCELLED 时未完成槽位统一 `CANCELLED`，不悬空；
- Item 失败：记录 `error_type / error_message / retry_count`，Job 由 `_finish_job`
  统计（存在 FAILED Item → Job FAILED）；
- 系统性失败（`_systemic_failure`）：当前 Item FAILED、未执行 Item CANCELLED、
  Job FAILED + **队列自动暂停**（等待用户处理）；后续 Stage 不启动。

## 5. Seed 规则（Phase 3 §0.4，冻结）

- 默认：每张图独立随机 Seed（`random.SystemRandom`），**Item 真正开始执行时**才分配；
- `seed_mode=fixed`（"使用此图 Seed"）：**仅用于单张精确复现**——后端要求 `count == 1`
  （fixed + count>1 → 400 `FIXED_SEED_SINGLE_ONLY`）；前端选"使用此图 Seed"自动收敛 count=1，
  用户把数量改成 >1 自动切回随机；
- 固定 Seed 只作用于第一个（生成）Stage；后续 Stage 仅在模块 `uses_seed=true` 时分配新随机数，
  放大链不使用 Seed（`StageItem.seed = NULL`，Phase 4 Task3）；
- 禁止 `base_seed + item_index`（旧行为已删除）；
- 范围校验在 EngineAdapter / binding（`seed_range`）侧完成；
- 已成功 Item 的 Seed 永远保留；未完成 Item 重跑（续跑子 Job）生成新随机 Seed。

## 6. 事件（JobEvent，仅追加）

| 事件 | 时机 |
| --- | --- |
| JOB_CREATED | JobService 创建 Job + N 个 Item |
| JOB_STARTED / JOB_PAUSED / JOB_PAUSE_REQUESTED / JOB_RESUMED | 状态操作 |
| JOB_CANCEL_REQUESTED / JOB_CANCELLED | 取消 |
| ITEM_STARTED（含 seed）/ ITEM_PROGRESS / ITEM_COMPLETED（含 image_ids）/ ITEM_FAILED / ITEM_CANCELLED | Item 生命周期 |
| STAGE_STARTED / STAGE_ITEM_STARTED / STAGE_ITEM_COMPLETED / STAGE_COMPLETED / STAGE_FAILED | Phase 3 Stage 生命周期 |
| JOB_COMPLETED / JOB_FAILED / JOB_INTERRUPTED / ITEM_RECOVERED | 终态与恢复 |
| WORKER_INTERNAL_ERROR | §0.1 Worker 代码级异常（Job INTERRUPTED + 队列暂停） |
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

## 10. Seed 与续跑（Phase 2.1 §五 + 2.2 §3 + Phase 7 Task0，固定）

- 每张图执行时分配 Seed（random：SystemRandom；fixed：仅单张精确复现，见 §5）；
- **续跑（resume-remaining）使用新随机 Seed —— 但只作用于真正重新执行的 Stage**
  （Phase 7 Task0）：子 Job 快照 `count = remaining, seed_mode = random, seed = null`；
- **Stage-aware Resume（Phase 7 Task0）**：`resume_remaining()` 不再把整条 Pipeline 从
  Stage 0 重跑——对每个剩余（非 COMPLETED 的）槽位逐 Stage 检查父 Job 同槽位 StageItem：
  - 已 COMPLETED 且 `output_image_id` 非空的**上游 Stage 直接复用**：物化为子 Job 的
    COMPLETED StageItem（继承 input/output/seed/engine_job_id + `reused_from_stage_item_id`
    溯源字段），整段全复用 → Stage 直接 COMPLETED（Worker 按"绝不重跑已完成 Stage"跳过）；
  - **从第一个真正未完成的 Stage 才开始执行**；复用槽位保留原 Seed（绝不重算），
    只有重新执行的 Stage 才由 Worker 分配新 Seed；
  - 链式流转：重跑 Stage 的输入 = 复用 Stage 的 `output_image_id`（Worker 既有派生逻辑）；
  - 覆盖四种场景：basic→upscale、img2img→upscale、Stage2 失败、Stage2 取消；
- **续跑完整继承 Parent 的 Workflow 身份**（Phase 2.2 §3）：workflow_snapshot_json +
  module_id / module_version / provider / binding_version / workflow_hash 全部原样继承，
  不读取当前 settings、不静默升级；原 binding 已不存在时执行期明确报 BINDING_NOT_FOUND；
- 想"用最新版 Workflow 重做剩余内容"请创建新 Job，而不是 Resume；
- 原 Job 的 workbench_snapshot 永不修改；已成功 Item 的 Seed 永远保留。

## 10.1 幂等键冲突（Phase 7 Task7，固定）

- `(source, client_request_id)` 幂等命中时**必须比对请求指纹**
  （`jobs.client_request_fingerprint` = job_kind + 快照 + 显式输入/配置的 canonical hash）：
  - 相同 key + 相同 payload → 返回原 Job（正常重放，`idempotent_replay=true`）；
  - 相同 key + **不同 payload** → `IDEMPOTENCY_KEY_CONFLICT`（409），绝不静默返回旧 Job；
- 队列模式（queue_mode）不进入指纹：只影响排队位置，不属于任务内容；
- 历史 Job（本阶段之前创建，指纹为 NULL）保持旧兼容行为（无法比对 → 返回原 Job）。

## 11. Worker 取消 / 内部异常（Phase 2.2 + Phase 3 §0.1）

**正常取消（进程退出 / 停机超时，asyncio.CancelledError）**：

```text
process_job 不写 Job 终态（也不把仍有未完成 Item 的 Job 标成 COMPLETED）
→ Job / Item / Stage / StageItem 保持 RUNNING 原样落库
→ 下次启动恢复流程接管（RUNNING → INTERRUPTED → 核对 → 归并终态）
```

**代码级意外异常（RuntimeError 等非 EngineError 异常，§0.1）**：

```text
当前 Job → INTERRUPTED（保留 engine_job_id 等恢复信息）
Stage / StageItem / Item 的 RUNNING → INTERRUPTED
queue_paused = true（禁止领取任何新 Job）
记录 WORKER_INTERNAL_ERROR 事件；Job.error_type = WORKER_INTERNAL_ERROR
```

绝不出现"A INTERRUPTED 后 B 立刻 RUNNING"或队列继续烧后续任务。