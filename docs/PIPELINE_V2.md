# PIPELINE_V2 — 多阶段管线（Phase 3 / v0.4.0）

> 本文档描述 v0.4.0 起的多阶段执行架构：`基础生成 → 高清放大`，以及图库已有图片的单独高清。

## 1. 数据模型

```
Job
├─ JobItem          用户要求的第 N 个"最终逻辑结果"（槽位）
└─ JobStage         按 stage_index 顺序执行的一个阶段（固化 module/binding/hash）
   └─ JobStageItem  一个逻辑槽位在某 Stage 的实际执行记录（图片流转 + 引擎任务）
```

- `Job.job_kind`：`generate`（生成流水线）/ `process`（处理型，如图库高清）。
- `JobStage` 固化执行身份：`module_id / module_version / provider / binding_version / workflow_hash`。
- `JobStageItem`：`input_image_id`（本阶段输入）/ `output_image_id`（本阶段输出）/
  `engine_job_id`（崩溃恢复核对）/ `progress / error_type / retry_count`。
- `JobItem` 不删除：表示用户要求的最终逻辑结果；`image_id` 保存该槽位**当前最终输出**
  （Stage 1 完成后指向高清图，未完成阶段 1 时指向原图）。

迁移：`0007_pipeline_stage`（jobs.job_kind + job_stages + job_stage_items）。

## 2. Pipeline 创建（唯一真源）

Job 创建时（`JobService.create_job`）从 `workflow_snapshot.modules` 物化 Stage：

```json
{
  "modules": [
    {"module_id": "basic_generate", "module_version": "v1", "provider": "comfyui", "binding_version": "v1", "workflow_hash": "…"},
    {"module_id": "upscale",        "module_version": "v1", "provider": "comfyui", "binding_version": "v1", "workflow_hash": "…"}
  ]
}
```

- 每个模块 = 一个 Stage；每个 Stage 为全部逻辑槽位创建 StageItem。
- `job_kind=process`（图库高清）：Pipeline 必须且只能是 `upscale`，Stage 0 的 StageItem
  预置 `input_image_id`（已有图片，§二十一）。
- 工作台"② 高清放大"开关开启 → `workflow_snapshot.modules = [basic_generate, upscale]`；
  配方保存 / 恢复该结构（§十六）。

**执行真源 = JobStage + workflow_snapshot**：Job 创建后当前配置文件怎么变都不影响该 Job；
Resume（续跑）完整继承原 Stage/Binding，绝不静默升级（原 binding 不存在 → 执行时 BINDING_NOT_FOUND）。

## 3. 执行顺序（Stage Gate，§六）

```
Stage 0: basic1 → basic2 → … → basicN
   全部 StageItem COMPLETED → Stage 0 COMPLETED
   ↓ 才允许启动
Stage 1: upscale1 → upscale2 → … → upscaleN
```

- 严格禁止 `生成1 → 高清1 → 生成2 → 高清2` 交错（由 Stage 串行循环强制）。
- 任一 StageItem FAILED（非系统性）→ 继续本 Stage 剩余项 → Stage FAILED → Job FAILED，
  **后续 Stage 不启动**。
- 系统性失败（离线/OOM/工作流/模型/节点/绑定缺失）→ Stage FAILED + Job FAILED + 队列自动暂停。

## 4. 图片流转（§十四）

```
Stage 0 输出 → Image(kind=original, images/originals/<id>/)
     ↓ StageItem.input_image_id = 上一 Stage 同槽位 output_image_id（运行时落库）
Stage 1 输出 → Image(kind=upscaled, images/upscaled/<id>/, parent_image_id=原图)
```

- 高清图存储目录由 `kind` 决定：`original|upscaled|processed → images/originals|upscaled|processed`。
- 处理型 Job（图库高清）：`input_image_id` 就是用户选择的已有 Image，**不复制成新的"原图"**。
- 导入元数据记录：stage_id / stage_index / stage_item_id / module / binding / workflow_hash / parent。

## 5. 输入图片进入 ComfyUI（§十三）

- Studio DataRoot 与 ComfyUI input 目录**不共享**；
- 处理型 Stage 经 `EngineAdapter.upload_image()` → `POST /upload/image`，subfolder 隔离
  （`NSFWStudio_inputs/`），文件名使用 Studio 唯一命名（`<image_id>.png`）；
- Binding 把引擎侧引用名注入实际输入节点（`LoadImage.image`）；
- 只允许清理 Studio 自己上传的临时输入文件（当前策略：不自动删除，命名可追溯）。

## 6. 输出命名与文件级恢复（§九）

- ComfyUI SaveImage `filename_prefix` 模板（provider binding）：
  `NSFWStudio/{job_short}/{stage}/{item_short}`；
- Studio 崩溃 + ComfyUI 重启 + `/history` 丢失时，仍可按自己的命名规则扫描输出目录核对结果；
- 扫描（`ComfyUIAdapter.scan_stage_outputs`）只处理该 StageItem 自己的目录，
  且必须位于 `comfyui.output_dir`（config.local.yaml，可选配置）之内；
- 绝不扫描/接管用户普通 ComfyUI 图片。

## 7. 超时（§十）

- 每个 StageItem 有执行总超时：默认 1800 秒（30 分钟），可由 Stage
  `config_json.execution_timeout` 覆盖；
- 超时 → `ENGINE_TIMEOUT`（Item FAILED，不自动重试，best-effort 取消引擎任务）；
- 绝不无限 RUNNING。

## 8. 与旧版本的关系

- v0.3.x 的 Job 全部物化为单 Stage（basic_generate），语义兼容；
- `QueueWorker` 不包含任何模块知识（参数结构只在 WorkflowModule 内，由 provider binding 注入）；
- 新增模块（img2img / reference / face_repair 等）只需注册新 WorkflowModule + 新 binding 目录，
  QueueWorker / ComfyUIAdapter 核心不修改（§二十二）。