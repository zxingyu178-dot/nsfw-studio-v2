# MODULE_IO_CONTRACT — WorkflowModule 输入/输出契约（Phase 4 ~ Phase 7 / v0.9.0）

> Task 2/3/4 的正式契约：模块能力声明是 kind / parent / seed 的**唯一判定依据**；
> 禁止再用"有 input_image 就认为是 upscaled"之类的推断。
> Phase 5 §十四：新增 `input_required / input_role`（模式判定与输入校验；第一版单图不引入 DAG Slots）。
> **Phase 5.1：PipelineValidator 统一校验（Job 创建前）；模块 `validate_config` 钩子；
> config 单链唯一事实源（Workflow → Recipe → Job → JobStage.config_json → module_config）；
> Img2ImgModule 正式接入（第三个模块，核心零改动）。**
> **Phase 6：`ParameterSpec` 元数据化（title / min / max / step / configurable——前端按 schema
> 渲染控件，不按 module_id 硬编码）；`size_mode`（explicit | input）声明输出尺寸语义；
> PipelineValidator 拒绝重复 module_id（PIPELINE_DUPLICATE_MODULE）与未注册 module_version；
> Img2ImgModule.execute 补齐 Prompt/Negative 契约。**
> **Phase 7：能力驱动 Job kind 校验（`allowed_job_kinds` / `can_start_from_image`——移除
> "process 必须 upscale" 硬编码）；通用输入 Slot 契约（`input_slots`，role=source/reference/
> face_reference + required + max_count）；`is_generative`（Image → Workbench 生成上下文锚点
> 语义）；ReferenceGenerateModule 正式接入（第四个模块，核心零改动）。**

## 1. ModuleCapabilities（能力声明）

```
module_id / module_version / title / description / parameters
+ Phase 4 输入输出语义：
  uses_seed          本模块是否真正使用随机 Seed（false → 绝不分配/展示 Seed）
  input_kind         none | image（模块是否需要输入图片）
  input_required     Phase 5：执行是否必须提供输入图片（模式判定 / 校验）
  input_role         Phase 5：输入图片在模块语义中的角色（旧版固定 source）
  output_kind        original | upscaled | processed（产出物 Image.kind → 存储目录）
  parent_policy      none | input_image（产出物是否挂到输入图片下）
  output_cardinality 单次执行输出个数（第一版固定 1）
+ Phase 6：
  size_mode          explicit（工作台显式宽高）| input（输出尺寸跟随输入图片）
+ Phase 7：
  allowed_job_kinds    允许的 Job 类型（generate / process；能力驱动，Validator 不硬编码）
  can_start_from_image 能否作为"以已有图片为起点"的 Pipeline 首模块（处理型 Job Stage0 语义）
  is_generative        产出是否构成"生成上下文"（Image → Workbench 恢复锚点；不依赖 seed 数据）
  input_slots          通用输入槽声明（role / required / max_count / description）
```

### 现有模块声明（固定）

| 模块 | uses_seed | input_kind | input_required | output_kind | parent_policy | cardinality | size_mode | job kinds | slots |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `basic_generate` | true | none | false | original | none | 1 | explicit | generate | — |
| `img2img`（Phase 5.1） | true | image | true | processed | input_image | 1 | input | generate | source(必填×1) |
| `reference_generate`（Phase 7） | true | image | true | original | input_image | 1 | input | generate | reference(必填×1) |
| `upscale` | false | image | true | upscaled | input_image | 1 | input | generate + process | source(必填×1) |

`is_generative`：`basic_generate / img2img / reference_generate = true`；`upscale = false`
（后处理产出不构成生成上下文，Workbench 恢复继续向上追溯）。
`can_start_from_image`：`img2img / reference_generate / upscale = true`；`basic_generate = false`。

Phase 6 `size_mode`：`basic_generate=explicit`；`img2img=input`（输出=输入尺寸）；`upscale=input`
（×N 由 provider binding 决定）；`reference_generate=input`（输出跟随重采样后的参考图）。
`ParameterSpec` 中 `configurable=true` 的参数（如 `img2img.denoise`、`reference_generate.resolution`）
才由前端按 type/min/max/step/enum 渲染控件并写入模块 config。

**前端 Gate（§二十；Phase 5.1 Task7；Phase 7 Task5）**：图片生成模式要求存在
`available=true 且 input_required=true` 的 Image-conditioned 模块（当前 = img2img / reference_generate）；
输入角色/数量以 `/modules` 返回的 `input_slots` 为准；
`registered ≠ available`（binding 不可加载的模块不得显示可用）；
Gate 判定以 `GET /api/v1/modules` 为准，禁止前端硬编码模块列表。

### 模块参数（config）与 `validate_config`

- 模块参数（如 `img2img.denoise`）只经 **config** 传递：
  `Workbench.workflow_modules[].config → Recipe.workflow_snapshot → Job.workflow_snapshot →
  JobStage.config_json → JobRequestContext.module_config → build_engine_request`；
- `WorkflowModule.validate_config(config)`（Phase 5.1 Task5，默认无约束）在 **Job 创建前**
  由 PipelineValidator 调用；非法 → `MODULE_CONFIG_INVALID`（400）；
- binding `defaults` 在 `inputs` 之后应用，因此**受模块控制的参数不得写进 defaults**
  （img2img 的 denoise 不在 defaults）。

### PipelineValidator（Phase 5.1 Task4/Task5；Phase 7 Task2/Task5）

Job 创建前（JobService / resume_remaining）统一校验，**禁止写进 QueueWorker**：

| 规则 | 错误码 |
| --- | --- |
| Stage0 提供了模块**未声明**的输入槽（含旧模块携带输入图） | `UNUSED_INPUT_IMAGE` |
| Stage0 必填输入槽缺失（旧模块：`input_required=true` 却无输入图） | `INPUT_IMAGE_REQUIRED` |
| 输入槽数量超出模块声明的 `max_count` | `INPUT_SLOT_LIMIT_EXCEEDED` |
| 模块的 `allowed_job_kinds` 不含当前 Job 类型 | `PIPELINE_INVALID` |
| 处理型 Job 的首个模块 `can_start_from_image=false` | `PIPELINE_INVALID` |
| Stage N 不消费 Stage N-1 输出 / 上游输出非图片产物 | `PIPELINE_INVALID` |
| 同一 module_id 重复出现 | `PIPELINE_DUPLICATE_MODULE` |
| 模块未注册 / module_version 未注册 | `WORKFLOW_ERROR` |
| 模块 config 非法 | `MODULE_CONFIG_INVALID` |

顺序语义：Validator 只判断合法性，**绝不重排**（顺序由用户/Recipe/Workbench 提供）。

## 2. 判定规则（ImageService / Worker 必须遵守）

1. **输出导入**（`image_service.import_adapter_outputs`）：
   - `kind = 当前 Stage 模块的 output_kind`；
   - `parent_image_id = StageItem.input_image_id` 当且仅当 `parent_policy == input_image`；
   - `seed = StageItem.seed`（不再取 JobItem.seed）。
2. **Seed 分配**（`QueueWorker._run_stage_item`）：
   - `uses_seed == true` → 执行前分配 Seed 并写入 `StageItem.seed`（默认每张独立随机；
     `seed_mode=fixed` 仅单张精确复现、只作用于第一个 Stage）；
   - `uses_seed == false` → `StageItem.seed = null`，绝不产生"假 Seed"；
   - `JobItem.seed` 保留为**基础生成的主要 Seed / UI 快捷字段**（仅 uses_seed 且 stage 0 时写入），
     真实溯源以 `StageItem.seed` 为准。
3. **未来模块**（reference / inpaint）只需声明能力 + 新增 binding 即可正确落库；
   QueueWorker / ImageService / Pipeline Scheduler 核心**不需要修改**
   ——Phase 5.1 的 img2img 接入已验证该结论（零核心改动）。
4. **输入冻结（Phase 5 §十；Phase 5.1 Resume 修复）**：Job 创建时从 WorkbenchSnapshot 提取
   `input_images`（max=1，role=source）→ 校验图片存在 → 写入 **Stage0 全部槽位** 的
   `JobStageItem.input_image_id`；`resume_remaining` 把生成型 Job 的输入图从 Parent 快照
   **重新冻结**到全部剩余槽位（img2img 续跑不丢输入图）；处理型 Job 的快照输入（若携带）
   必须与 `input_image_ids` 一致（`PIPELINE_INVALID`）；Stage1+ 的输入仍由 Worker 按
   "上一 Stage 同槽位输出"流转（`_previous_output_image_id`）。

## 3. EngineAdapter 输入图片正式契约（Task 4）

```
async def upload_input_image(*, image_id: str, file_name: str, data: bytes) -> str
    → 返回引擎侧引用名（由 binding 注入实际输入节点）
    → 默认实现（基类）明确拒绝：ENGINE_INPUT_UNSUPPORTED（系统性、不重试、队列暂停）
```

- 实现：`ComfyUIAdapter`（`POST /upload/image` → `NSFWStudio_inputs/<image_id>.<ext>`）、
  `MockEngineAdapter`（测试替身，同一契约 + 同一登记）。
- 处理型模块（upscale 及未来 img2img/reference）必须经该契约上传输入，
  **禁止 `getattr(engine, "upload_image", …)` 之类的 duck typing**。
- 名称由 Studio 决定（`{image_id}{suffix}`），保证"只清理 Studio 自己上传的文件"。

## 4. Studio Input Registry（Task 11）

- 每次上传登记到 `DataRoot/engine_inputs.json`（file / image_id / uploaded_at）；
- 启动时 TTL 清理（默认 24h，`comfyui.input_ttl_seconds` 可配）：
  只删除 **NSFWStudio_inputs/ 下、已登记、无 RUNNING/INTERRUPTED Stage 引用、超过 TTL** 的文件；
- 未配置 `comfyui.input_dir` 时安全跳过；绝不触碰其他 input 文件（禁止 `rm -rf input`）。

## 5. 错误码（本契约相关）

| 错误码 | 含义 | 分类 |
| --- | --- | --- |
| `ENGINE_INPUT_UNSUPPORTED` | 引擎不支持输入图片契约 | 系统性（队列暂停） |
| `BINDING_HASH_MISMATCH` | binding.yaml 指纹不一致（immutable 违约） | 系统性 |
| `BINDING_IDENTITY_MISMATCH` | binding 自描述与请求身份不符 / 恢复时引擎不匹配 | 系统性 |
| `WORKFLOW_HASH_MISMATCH` | workflow.json 指纹不一致 | 系统性 |
| `BINDING_NOT_FOUND` | provider binding 目录缺失 | 系统性 |