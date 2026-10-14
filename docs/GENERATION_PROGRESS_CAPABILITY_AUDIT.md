# 生成进度（sampling step）能力盘点（§11 审计）

- 分支：`feature/v0.14.1-fix-hardening`　HEAD：`1e5893e`（v0.14.0）
- 目标：沿真实数据链 **ComfyUI websocket/progress → EngineAdapter → QueueWorker → SSE JobEvent → 前端 jobStore** 逐跳核实「当前到底能不能拿到并显示真实 sampling step（如 17/30）」。
- 最高原则：只有真实有 step 的 Stage 才显示 step；**没有真实 step 就写「无」**。本轮不做 StepProgress UI、不新建 StageProgress 后端契约，只给结论 + 下一阶段最小改动点。
- 路径相对仓库根。

## 结论速览

| 问题 | 结论 | 关键证据 |
|---|---|---|
| 能否拿到 sampling step（整数 value/max） | **WS 边界能收到，但被立刻丢弃** | ComfyUI `progress` 事件的 `value`/`max` 被读入后当场除成 0~0.99 浮点，原始整数不落地 |
| step 来自哪个 WS event | **ComfyUI `progress` 事件**，字段 `data.value` / `data.max` | `comfyui.py:500-503` |
| 是否被当前 adapter 消费/转发 | **消费成 ratio，但未转发 step** | 只把 `progress=value/max` 存进实时层；`EngineJobStatus` 无 step 字段 |
| 能否绑定到当前 engine_job_id（prompt_id） | **能** | 实时层 `_live` 以 ComfyUI `prompt_id`(=engine_job_id) 为 key |
| 主采样模块（basic_generate）有 step 吗 | **WS 层有（KSampler），但当前链只暴露 ratio** | binding 含 `KSampler` 节点 |
| reference_generate 有 step 吗 | **同上（有 KSampler）** | binding 含 `KSampler` |
| upscale 有 step 吗 | **无（根本不发 progress 事件）** | upscale binding 无任何 sampler 节点 |
| SSE JobEvent 能否携带 progress payload | **传输层可以（自由 JSON），当前 payload 只放了 ratio/stage** | `ITEM_PROGRESS` payload 无 step；SSE 是透传 |

**一句话：** ComfyUI 在采样时确实会推 `progress {value,max}`，但现有链路在 adapter 边界就把它归一化成 `0~1` 的比例值，DB 列、SSE payload、前端 DTO 全都没有整数 step；且 **upscale 这类非采样模块压根不发 progress 事件**。因此当前任何地方若直接显示「17/30」都是假造——能真实显示的只有「百分比比例」。

---

## 逐跳数据链核实

### 跳 1：ComfyUI WebSocket 进度事件（真实 step 的唯一源头）

`backend/app/engine/comfyui.py` → `_handle_ws_message`（`:487-511`）：

```python
elif kind == "progress":
    value, maximum = data.get("value", 0), data.get("max", 1) or 1
    self._mark_live(prompt_id, state="running", stage="sampling",
                    progress=round(min(0.99, value / maximum), 3))
```

- 事件名：ComfyUI WS `type == "progress"`，字段 `data.value`（当前 step）、`data.max`（总 step）、`data.prompt_id`。
- **关键：`value`/`maximum` 在 `:501` 被读出后，于 `:503` 立即算成 `value/maximum` 比例（并 clamp 到 0.99），原始整数 `value`/`max` 没有被存入 `_live`、也没有任何字段承接。**
- 其他事件：`execution_start`→`stage="execution"`（`:497-499`）、`execution_success`→`stage="save_image", progress=1.0`（`:504-505`）、`execution_error`→failed（`:506-511`）。这些 `stage` 字符串是**硬编码的粗粒度阶段**，不是模块名，也不含 step。
- 实时层容器：`self._live: dict[str, dict]`（`:91`），key 为 `prompt_id`；`submit_job` 初始化 `{stage:"queued", progress:0.0, ...}`（`:301-303`）。

### 跳 2：EngineAdapter 状态契约（无 step 字段）

`backend/app/engine/base.py` → `class EngineJobStatus`（`:57-65`）：

```python
state: str                 # queued|running|succeeded|failed|canceled|unknown
progress: float | None     # 0.0 ~ 1.0  ← 只有比例
message: str = ""
stage: str = ""            # 粗粒度阶段字符串
error_type: str = ""
```

- **契约里根本没有 `step` / `max_step` / `current_step` 字段。** 即使跳 1 收到了 value/max，也无处传递。
- 绑定引擎任务：`get_job_status(engine_job_id)`（`comfyui.py:308-343`）直接 `self._live.get(engine_job_id)`（`:317`）。`engine_job_id` 就是 ComfyUI 返回的 `prompt_id`（`submit_job` 返回 `data["prompt_id"]`，`:298-305`）。**因此 step 数据若要绑定，天然能绑定到当前 engine_job_id——这一跳的 id 对齐是通的。**
- mock 引擎同样只发 ratio + 粗 stage（`backend/app/engine/mock.py:84-107`，如 `progress=0.5, stage="sampling"`），不提供整数 step。

### 跳 3：QueueWorker 轮询与落库

`backend/app/workers/queue_worker.py`：

- 轮询：`status = await self._adapter.get_job_status(engine_job_id)`（`:438`）。
- 落库 + 发事件：`_update_stage_item_progress`（`:603-622`）：
  ```python
  if status.progress is not None:
      stage_item.progress = float(status.progress)     # :609 只写比例
  ...
  job_service.record_event(
      session, job_id, "ITEM_PROGRESS", item_id=stage_item.job_item_id,
      payload={"progress": stage_item.progress, "stage": status.stage,
               "stage_index": stage_index},            # :617-620 无 step
  )
  ```
- DB 列（`backend/app/models/job.py`）：
  - `JobStageItem.progress: float | None`（`:169`）——**只有比例列，无 step/max_step 列**；
  - `JobItem.progress`（`:425`）、`JobItem.current_stage`（`:403`）——同样无 step；
  - `JobStageItem.engine_job_id`（`:168`）、`JobItem.engine_job_id`（`:402`）——绑定 id 有，但没有 step 数值列。
- worker 在 `_bind_engine_job`（`:593-601`）把 `engine_job_id` 同时写到 `stage_item` 与 `job_item`，确认 id 绑定链完整。
- stall 探测（`:455-480`）也只看 `progress`（比例）与 `stage` 字符串是否变化，与 step 无关。

### 跳 4：SSE JobEvent（传输层自由 JSON，但当前不装 step）

- 事件落库/广播：`job_service.record_event`（`backend/app/services/job_service.py:307-310`）写 `JobEvent(payload_json=json.dumps(payload))`，并 `_publish(...)`。
- 广播消息形状：`_publish`（`:56-64`）`{type, job_id, item_id, payload, time}`——**payload 是自由 dict，结构上完全可以多塞 `step`/`max_step`**。
- SSE 端点：`backend/app/api/v1/jobs.py:226-249` `/events/jobs` 直接 `yield f"data: {data}\n\n"` 透传 broker 消息。
- **结论：SSE 传输层没有任何阻碍携带 step；只是当前唯一的进度事件 `ITEM_PROGRESS`（跳 3）的 payload 里没有 step 字段。** 事件模型 `JobEvent`（`models/job.py:183-192`）本身也是 `event_type + payload_json` 的自由结构。

### 跳 5：前端 jobStore（SSE 只当唤醒信号，payload 被忽略）

`frontend/src/stores/jobStore.ts`：

- SSE 订阅：`subscribeJobEvents(() => scheduleJobRefresh(), ...)`（`:238-241`）——**回调只触发「去重拉取」，不解析事件 payload**。
- 唯一事实源 = 回源 GET：`refreshJobs()`（`:72-96`）并发 `jobApi.queue()` + `jobApi.engineStatus()`（`:76`），再按需 `jobApi.get(trackedId)`（`:85`）。
- 兜底轮询：每 10s `refreshJobs()`（`:242-244`）；SSE 唤醒后 0.3s 防抖刷新（`scheduleJobRefresh`，`:64-70`）。
- DTO 字段（`frontend/src/types/workbench.ts`）：`JobItemDTO.progress: number | null`（`:404`）、`JobStageDTO.progress`（`:447`）——**前端类型里同样没有 step/max_step**。
- 因此前端能显示的进度只有「百分比比例」（`utils/jobProgress.ts` 的 `overallProgress` 把 `progress*100` 取整），以及粗粒度 `current_stage` 文案（`STAGE_LABEL`，`types/workbench.ts:713-721`：submit/queued/execution/sampling/save_image/done/error）。

---

## 分模块 step 有无（按 provider binding 真实节点判定）

ComfyUI 的 `progress` 事件由 **KSampler 类节点**触发；无 sampler 节点的工作流不发该事件。核查 `workflows/providers/comfyui/*/v1/workflow.json`：

| 模块 | binding 关键节点 | 是否发 progress | 当前链能否给 step |
|---|---|---|---|
| `basic_generate`（基础生成） | `KSampler` + `EmptyLatentImage`/`TextEncodeQwenImage21`/`UnetLoaderGGUF`/`VAEDecode` 等 | **发** | WS 有 value/max，但被归一化成比例，**整数 step 当前拿不到** |
| `reference_generate`（参考生成） | `KSampler` + `LoadImage`（参考图）+ 同上编码链 | **发** | 同上：有采样 step 源，但链路上已丢整数 |
| `img2img` | 含 sampler（grep 命中 sampler/KSampler 关键字） | **发** | 同上 |
| `upscale`（高清放大） | 仅 `UpscaleModelLoader` + `ImageUpscaleWithModel` + `LoadImage` + `SaveImage`（**无任何 sampler**） | **不发** | **无——本模块永远没有 sampling step** |

- upscale 阶段：`ImageUpscaleWithModel`（ESRGAN 类模型放大）在 ComfyUI 里是单节点同步执行，**不产生 `progress` 事件**。此时 adapter `_live` 停留在「running 但 progress≈0」，靠 `execution_success` 一次性跳到 1.0（`comfyui.py:504-505`）。这正是 worker stall 探测（`queue_worker.py:468-480`，progress 长期为 0 → `ENGINE_STALLED`）需要在 upscale 这类无进度模块上留足余量的原因。
- **结论：upscale / 任何纯处理型（无 KSampler）模块，step = 无，UI 绝不能对它们渲染 step 数字。**

---

## 下一阶段接入真实 step 的最小改动点（仅建议，本轮不实施）

目标：对**确有 KSampler 的模块**把 `value/max` 整数端到端透传到前端，且只对有 step 的模块显示。按改动量从小到大：

1. **Adapter 边界保留整数（`comfyui.py:500-503`）**：在处理 `progress` 事件时，除 `progress=value/max` 外，把 `value`/`max` 一并 `_mark_live(..., step=value, max_steps=maximum)`（`_live` dict 加两个键）。
2. **扩展 `EngineJobStatus`（`base.py:57-65`）**：增加 `step: int | None = None`、`max_step: int | None = None`，并在 `_running_status`/`get_job_status` 中带出（注意历史/失败/无进度模块时保持 `None`）。
3. **Worker 落库与事件（`queue_worker.py:_update_stage_item_progress` `:603-622`）**：若要持久化，需要给 `job_stage_items` 增 `step`/`max_step` 列（**这会涉及 DB migration，属后续阶段**）；**若仅实时展示，可先不落库**，直接把 `status.step`/`status.max_step` 并入 `ITEM_PROGRESS` 的 payload（SSE 自由 JSON，无需 migration）。
4. **前端 DTO + jobStore**：当前 SSE 被当唤醒信号、不读 payload（`jobStore.ts:238-241`）。要在 SSE 瞬时渲染 step，需要改为**解析 `ITEM_PROGRESS` 的 payload 并就地更新 trackedJob 对应 item 的 step 字段**（而不是仅触发全量回源），并给 `JobItemDTO`/`JobStageDTO` 加 `step?`/`max_step?`。
5. **显示侧约束**：仅当 `max_step > 0`（即该模块确有采样）时才渲染 `step/max_step`；upscale 等无 step 模块（binding 无 KSampler）一律不渲染 step，只显示比例或「处理中」。

> 上述第 3 步一旦选择落库就需要 migration——这正是本轮被明确禁止的；因此下一阶段最稳妥的起点是「1+2+4（SSE payload 瞬时透传，不落库）」，先把真实 step 端到端点亮，再评估是否需要持久化列。
