# PIPELINE_STATE_MACHINE — Stage / StageItem 状态机（Phase 3 + Phase 4 / v0.5.0）

> Job / JobItem 状态机见 `JOB_STATE_MACHINE.md`；本文档只描述 Phase 3 新增的
> JobStage / JobStageItem，以及它们与 Job 的归并关系。

## 1. JobStage 状态

```text
QUEUED ──► RUNNING ──► COMPLETED      （全部 StageItem COMPLETED）
   │           │
   │           ├──────► FAILED         （任一 StageItem FAILED；含系统性失败）
   │           └──────► CANCELLED      （取消：Job 取消时所有未完成 Stage 落 CANCELLED）
   └──────► CANCELLED                  （Job 在进入本 Stage 前被取消）
RUNNING ──► INTERRUPTED               （崩溃恢复：启动时 RUNNING → INTERRUPTED）
```

- Stage 状态集**不含 PAUSED**（合同 §二）：Job PAUSED 期间 Stage 保持 RUNNING，
  用户可见状态以 Job 为准；恢复后继续执行剩余 StageItem。
- Stage Gate（§六）：`Stage N COMPLETED` 是启动 `Stage N+1` 的唯一条件；
  `FAILED / CANCELLED` 的 Stage 之后的后继 Stage **永不启动**（保持 QUEUED）。

## 2. JobStageItem 状态

```text
QUEUED ──► RUNNING ──► COMPLETED      （引擎成功 + 取回输出 + 导入 Studio Image）
   │           │
   │           ├──────► FAILED         （OUTPUT_MISSING / STORAGE_ERROR / ENGINE_TIMEOUT /
   │           │                        WORKFLOW_* / MODEL_MISSING / NODE_MISSING / OOM …）
   │           └──────► CANCELLED      （引擎返回 canceled，或 Job 取消边界）
   ├──────► CANCELLED                  （同 Stage 系统性失败：本 Stage 剩余 QUEUED 统一取消）
   └──────► INTERRUPTED                （崩溃恢复现场；核对成功可回填 COMPLETED）
```

- 已 COMPLETED 的 StageItem **绝不重跑**（暂停/取消/恢复/续跑均适用，§八）。
- 完成条件与 Phase 2.1 §一 一致：`引擎成功 + 输出非空 + 导入成功` 才允许 COMPLETED，
  禁止 `COMPLETED + output_image_id=null`。
- `FAILED` 的 StageItem 不允许自动重试（ENGINE_TIMEOUT / OUTPUT_MISSING / STORAGE_ERROR 等）；
  仅瞬态网络错误（ENGINE_NETWORK, transient=true）在轮询/提交路径自动重试 ≤ 2 次。
- **StageItem.seed（Phase 4 Task3）**：进入 RUNNING 前落库真实 Seed
  （uses_seed=false 的 Stage 恒为 NULL；按 Stage 模块能力判定，见 MODULE_IO_CONTRACT.md）。

## 3. 与 Job / JobItem 的归并规则

| 时机 | Job | JobItem |
| --- | --- | --- |
| StageItem COMPLETED | 计数更新 | 非最后 Stage：保持 RUNNING（"阶段间进行中"），`image_id` = 当前输出；最后 Stage：COMPLETED |
| Stage FAILED（含系统性） | FAILED（Gate 阻断后续 Stage） | 失败槽位 FAILED；阶段间 RUNNING 槽位 → CANCELLED（不悬空） |
| Job CANCELLED | CANCELLED | 未完成槽位 → CANCELLED；已完成输出全部保留 |
| Job PAUSED | PAUSED（Stage 保持 RUNNING） | 无 RUNNING（暂停发生在 StageItem 边界） |
| Worker 内部异常（§0.1） | INTERRUPTED（保留 engine_job_id） | RUNNING → INTERRUPTED |
| 崩溃恢复核对成功 | 全部 Stage COMPLETED 且计数齐 → COMPLETED（JOB_RECOVERED_COMPLETED） | 恢复槽位按"最后 Stage"规则回填 |

## 4. 事件（SSE / job_events）

在 Phase 2 事件基础上新增：

```text
STAGE_STARTED         {stage_index, module_id, module_version}
STAGE_ITEM_STARTED    {stage_index, module_id, seed}
STAGE_ITEM_COMPLETED  {image_ids, stage_index}
STAGE_COMPLETED       {stage_index, completed, total}
STAGE_FAILED          {stage_index, completed, total}
WORKER_INTERNAL_ERROR {message}      # §0.1：Job INTERRUPTED + 队列暂停
JOB_RECOVERED_COMPLETED              # 恢复归并完成
```

既有 `ITEM_* / JOB_*` 事件语义保持不变（前端 SSE 只做通知，数据库状态才是唯一事实源）。

## 5. 队列暂停（queue_paused）触发条件

- 系统性引擎失败（`ENGINE_OFFLINE / OUT_OF_MEMORY / WORKFLOW_ERROR / BINDING_NOT_FOUND /
  WORKFLOW_HASH_MISMATCH / BINDING_HASH_MISMATCH / BINDING_IDENTITY_MISMATCH /
  ENGINE_INPUT_UNSUPPORTED / MODEL_MISSING / NODE_MISSING`）；
  Phase 4 起"构造引擎请求"阶段的系统性错误（如上传输入图片失败/不支持）同样触发队列暂停，
  与提交阶段行为一致；
- Worker / 循环级代码异常（`WORKER_INTERNAL_ERROR`，§0.1）；
- 用户处理后经 `POST /api/v1/queue/resume` 恢复。