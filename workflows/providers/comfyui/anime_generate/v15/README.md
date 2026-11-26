# anime_generate / v15

统一 AI 提交 binding：在 v5 基础上把模型与采样参数变成任务级变量。

## 任务级变量（`snapshot.workflow_modules[].config`）

| 字段 | 注入点 | 说明 |
| --- | --- | --- |
| `model` | CheckpointLoaderSimple(1).ckpt_name | ComfyUI `/models/checkpoints` 文件名 |
| `loras` | LoraLoader(21/22) | 0–2 条 `{name, strength_model, strength_clip}` |
| `steps` / `cfg` / `sampler_name` / `scheduler` / `denoise` | KSampler(7) | 不传沿用默认 30 / 4.0 / er_sde / simple / 1.0 |
| `face_detailer` | FaceDetailer(20) / 检测器(18) | 默认开启；`false` 时由 adapter 移除 20/18，SaveImage 直连 VAEDecode |

FaceDetailer(20) 默认开启，参数保持 binding 默认；`face_detailer=false` 可显著提速，
适合快速预览与大批量筛选（binding 文件与 Hash 不变，off 由执行适配器按节点类型处理）。

## 默认与验收

- 默认底模 `miaomiaoHarem_v14.safetensors`，默认尺寸 832×1216；
- 2026-11-27 真实 Job：NoobAI-XL v1.1 + `cunnyfunky_noobai_v3.3_000080` @0.6，
  dpmpp_2m/karras/30/cfg5.0，1 张 COMPLETED（832×1216，冷启 266s）；
- Agent 提交示例：`scripts/agent_generate.py --binding v15 --model ... --lora ... --steps ...`；
- 放行与证据见 `workflows/release_manifest.yaml` 的 v15 条目。
