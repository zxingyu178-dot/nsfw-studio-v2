# img2img / v1（ComfyUI Provider Binding）

## 来源与选择

Phase 5.1 **零下载实验**验证通过的本机现有链（详见项目 `docs/PHASE51_REPORT.md` 与
`docs/evidence/phase51-img2img/` 实验记录）：

- Qwen-Image 2.1 UC Q4（`qwen-image-2.1-UC-Q4_0.gguf`）+ qwen3vl text encoder + Qwen VAE；
- 图结构：`LoadImage → VAEEncode → KSampler(denoise) → VAEDecode → SaveImage`；
- 与 `basic_generate/v1`（文生图）共享同一模型与采样参数（steps 25 / cfg 1.0 / euler / simple）。

**不下载新模型、不安装节点、不升级 ComfyUI；不修改用户自己的工作流。**

## 注入契约

| 标准输入 | 注入位置 | 说明 |
| --- | --- | --- |
| `input_image` | 节点 4（LoadImage.image） | 引擎侧引用名，由 `EngineAdapter.upload_input_image` 上传（subfolder=NSFWStudio_inputs） |
| `positive_prompt` | 节点 6（prompt） | |
| `negative_prompt` | 节点 6（negative_prompt） | |
| `seed` | 节点 7（seed） | 每张独立随机 Seed（StageItem 记录真实值） |
| `denoise` | 节点 7（denoise） | 变化强度 0.05~1.0，默认 0.55（模块 config 唯一来源） |

`defaults` 只包含 `resolution / steps / cfg / sampler_name / scheduler`；
**denoise 不在 defaults**（binding defaults 在 inputs 之后应用，会覆盖注入值）。

## 输出语义

- 输出尺寸 = 输入图尺寸（VAEEncode 决定；模块不接受 width/height 注入）；
- `Image.kind = processed`、`parent_image_id = 输入图`（由 ModuleCapabilities 驱动，通用层落库）；
- 保存前缀包含 Studio 身份（job/stage/item），支持崩溃恢复的文件级核对。

## 修改纪律

本目录视为 **immutable**：需要修改 workflow.json / binding.yaml 时必须新建 `v2/`，
`workflow_hash` / `binding_hash` 双指纹不一致会被拒绝执行（防止历史 Job 静默换链）。