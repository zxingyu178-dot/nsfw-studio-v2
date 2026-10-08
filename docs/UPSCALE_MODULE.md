# UPSCALE_MODULE — 高清放大模块契约（Phase 3 §十一）

## 1. 模块身份

```text
module_id      = "upscale"
module_version = "v1"
provider       = "comfyui"（由 Job/Stage 固化身份决定）
```

实现：`backend/app/workflows/upscale.py`（`UpscaleModule`）。

## 2. 标准输入（WorkflowInput）

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `input_image` | InputImageRef | 是 | 待放大的已有图片（image_id / file_name / bytes / width / height） |

- 核心输入只有 `input_image` + 少量模块参数；**模块禁止知道任何 ComfyUI Node ID**
  （节点注入位置只存在于 provider binding，`workflows/providers/comfyui/upscale/v1/binding.yaml`）；
- 放大倍率由 provider binding 决定（v1 = 4x-UltraSharp，固定 4 倍；见
  `UPSCALE_WORKFLOW_INVENTORY.md`）。

## 3. 执行契约

```text
PipelineExecutor.build_engine_request(job, stage, stage_item, seed, adapter, input_image)
  → UpscaleModule.prepare_inputs(context, adapter)      # 上传输入图片（§十三）
      adapter.upload_image("<image_id>.png", bytes) → 引擎侧引用名
  → UpscaleModule.build_engine_request(context, prepared)
      parameters = {"input_image": <引擎侧引用名>}
      binding    = context.binding（来自 JobStage 固化身份，§0.2）
  → 提交 / 轮询 / 取输出（语义留在 QueueWorker，模块不实现队列语义）
```

- 输出导入为 Image：`kind = upscaled`、`parent_image_id = input_image.image_id`、
  存储于 `images/upscaled/<img_id>/`（§十四）；
- 失败分类与其它模块一致：`BINDING_NOT_FOUND / WORKFLOW_HASH_MISMATCH / ENGINE_OFFLINE /
  ENGINE_TIMEOUT / OUTPUT_MISSING / STORAGE_ERROR / …`。

## 4. 两种使用方式（同一模块、同一 Worker）

| 场景 | Job | Pipeline | 输入来源 |
| --- | --- | --- | --- |
| 生成流水线 Stage 2（工作台开启"② 高清放大"） | `job_kind=generate` | `basic_generate → upscale` | Stage 1 同槽位 output_image_id |
| 图库已有图片单独高清 | `job_kind=process` | 仅 `upscale` | 用户选择的已有 Image（`POST /api/v1/images/upscale`） |

**禁止维护"两套高清代码"**：两个场景共用 UpscaleModule + upscale/v1 binding + 同一 QueueWorker。

## 5. 与其它层的关系

- Worker 不感知 `input_image` 参数名（模块知识只在模块内）；
- Adapter 不感知模块身份（一个 ComfyUIAdapter 按请求动态加载 basic_generate/v1、upscale/v1…）；
- 新增放大链（如 SeedVR2 / 2x / 8x）= 新增 `upscale/v2` binding 目录 + 配置切换，
  不改动本模块与 Worker。

## 6. 测试覆盖

- 单测/离线：`tests/backend/test_phase3_pipeline.py`（Stage 顺序、Gate、暂停/取消/恢复、
  父子关系、process Job、ENGINE_TIMEOUT 等 12 场景）；
- 绑定单测：`tests/backend/test_comfyui_binding.py`（upscale/v1 图结构 + 动态加载 + hash 校验）；
- 真实链路：`tests/backend/test_comfyui_integration.py`
  （1 张基础 → 1 张真实高清；图库单张高清 → 4 倍尺寸）。