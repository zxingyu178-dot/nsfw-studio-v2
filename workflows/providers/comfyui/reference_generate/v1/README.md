# reference_generate / v1（ComfyUI Provider Binding）

## 来源与选择

Phase 7 Task3 只读重盘 + Task4 Gate 实测（详见 `docs/REFERENCE_CAPABILITY_INVENTORY.md`）
选定的本机现有链：

- Qwen-Image 2.1 UC Q4（`qwen-image-2.1-UC-Q4_0.gguf`）+ qwen3vl text encoder（w4a8）+ Qwen VAE；
- 图结构：`LoadImage(参考图) → TextEncodeQwenImage21（reference latents）→
  KSampler(latent=参考尺寸空 latent, denoise=1.0) → VAEDecode → SaveImage`；
- 与 `basic_generate/v1`（文生图）/ `img2img/v1` 共享同一模型与采样参数
  （steps 25 / cfg 1.0 / euler / simple）。

**不下载新模型、不安装节点、不升级 ComfyUI；不修改用户自己的工作流。**

## 与 img2img 的语义差异（命名依据）

参考图**不经 VAEEncode、没有 denoise 编辑语义**：参考图经视觉塔进文本编码器
（CLIPLoader device=cpu），VAE 编码为 `reference_latents` 拼接进 conditioning；
`latent_image` 使用 `TextEncodeQwenImage21` 的 latent 输出（以重采样后的第一张参考图尺寸为准，
官方注释明确"换尺寸会移位 edit"）。因此本模块命名 `reference_generate`（参考条件生成），
而不是 Img2Img。

## 注入契约

| 标准输入 | 注入位置 | 说明 |
| --- | --- | --- |
| `input_image` | 节点 4（LoadImage.image） | 引擎侧引用名，由 `EngineAdapter.upload_input_image` 上传（subfolder=NSFWStudio_inputs） |
| `positive_prompt` | 节点 5（prompt） | |
| `negative_prompt` | 节点 5（negative_prompt） | |
| `resolution` | 节点 5（resolution） | 参考图重采样基准 512~2048（模块 config，默认 1024） |
| `seed` | 节点 6（seed） | 每张独立随机 Seed（StageItem 记录真实值） |

`images.image_1`（Autogrow 动态输入，点号路径）在 workflow.json 中静态链接
`LoadImage → TextEncodeQwenImage21`；`defaults` 固定采样参数（含 `denoise: 1.0`）。

## 输出语义

- 输出尺寸 = 重采样后的参考图尺寸（模块不接受 width/height 注入）；
- `Image.kind = original`、`parent_image_id = 参考图`（由 ModuleCapabilities 驱动，通用层落库）；
- 保存前缀包含 Studio 身份（job/stage/item），支持崩溃恢复的文件级核对。

## 修改纪律

本目录视为 **immutable**：需要修改 workflow.json / binding.yaml 时必须新建 `v2/`，
`workflow_hash` / `binding_hash` 双指纹不一致会被拒绝执行（防止历史 Job 静默换链）。