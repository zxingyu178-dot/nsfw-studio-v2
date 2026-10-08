# MODULE_IO_CONTRACT — WorkflowModule 输入/输出契约（Phase 4 + Phase 5 / v0.6.0）

> Task 2/3/4 的正式契约：模块能力声明是 kind / parent / seed 的**唯一判定依据**；
> 禁止再用"有 input_image 就认为是 upscaled"之类的推断。
> Phase 5 §十四：新增 `input_required / input_role`（模式判定与输入校验；第一版单图不引入 DAG Slots）。

## 1. ModuleCapabilities（能力声明）

```
module_id / module_version / title / description / parameters
+ Phase 4 输入输出语义：
  uses_seed          本模块是否真正使用随机 Seed（false → 绝不分配/展示 Seed）
  input_kind         none | image（模块是否需要输入图片）
  input_required     Phase 5：执行是否必须提供输入图片（模式判定 / 校验）
  input_role         Phase 5：输入图片在模块语义中的角色（第一版固定 source）
  output_kind        original | upscaled | processed（产出物 Image.kind → 存储目录）
  parent_policy      none | input_image（产出物是否挂到输入图片下）
  output_cardinality 单次执行输出个数（第一版固定 1）
```

### 现有模块声明（固定）

| 模块 | uses_seed | input_kind | input_required | input_role | output_kind | parent_policy | output_cardinality |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `basic_generate` | true | none | false | source | original | none | 1 |
| `upscale` | false | image | true | source | upscaled | input_image | 1 |

**Phase 5 前端 Gate（§二十）**：图片生成模式要求存在
`input_required=true 且 output_kind=processed` 的模块（未来 img2img / reference）；
Gate 判定以 `GET /api/v1/modules` 为准，禁止前端硬编码模块列表。

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
3. **未来模块**（img2img / reference / inpaint）只需声明能力即可正确落库，例如：
   `img2img: uses_seed=true, input_kind=image, input_required=true, input_role=source,
   output_kind=processed, parent_policy=input_image`。
   QueueWorker / ImageService / Pipeline Scheduler 核心**不需要修改**。
4. **输入冻结（Phase 5 §十）**：Job 创建时从 WorkbenchSnapshot 提取 `input_images`
   （max=1，role=source）→ 校验图片存在 → 写入 **Stage0 全部槽位** 的
   `JobStageItem.input_image_id`（复用既有 `_materialize_stages`，无核心改动）；
   处理型 Job 的快照输入（若携带）必须与 `input_image_ids` 一致（`PIPELINE_INVALID`）；
   Job 创建后工作台 / 图库变化不影响该 Job 的输入身份。Stage1+ 的输入仍由
   Worker 按"上一 Stage 同槽位输出"流转（`_previous_output_image_id`）。

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