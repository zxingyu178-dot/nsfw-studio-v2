# basic_generate v1（ComfyUI Provider Binding）

Studio 第一套真实生图工作流绑定（Phase 2B），也是当前日用主力文生图链。

- **来源**：本机已验证可跑的 Qwen-Image 2.1 UC 文生图链（与 `projects/nightbatch` 同款节点图），
  未自行设计新链（规范 §二十八）。
- **模型**：`qwen-image-2.1-UC-Q4_0.gguf`（4.15 GB）+ `qwen3vl_8b_w4a8` 文本编码器（6.31 GB，CPU）
  + `qwen_image_2.1_vae_bf16`（675 MB），位于 `C:/ComfyUI_models/`（经 `extra_model_paths.yaml` 挂载）。
- **LoRA 链（2026-10-27 起）**：
  - `qwen_image_2.1_turbo8_lora.safetensors`（节点 9，model/clip 强度 1.0）
  - `f23gg_nsfw_qwen21.safetensors`（节点 10，model 0.8 / clip 1.0）
  - KSampler 的 model 输入来自节点 10（`LoraLoader` 串联）。
- **注入点**：见 `binding.yaml`（positive/negative → 节点 4，宽高 → 节点 5，seed → 节点 6）。
- **输出**：节点 8 `SaveImage`，前缀 `NSFWStudio/<job>/<stage>/<item>/`；Adapter 经 `/history` + `/view`
  取回字节后导入 Studio DataRoot，ComfyUI output 只作为输出来源。
- **默认采样**：`steps=8`、`cfg=1.0`、`euler/simple`、`denoise=1.0`（binding `defaults."6"` 覆盖
  workflow.json 节点值；Turbo8 配套）。**不得恢复旧的 25 步说明。**
- **版本策略（2026-10-27 用户确认，方案 A）**：`basic_generate/v1/` 是唯一目录，不新建 `v2/`；
  版本演进靠 Git 历史。代价是历史 Job 的 `workflow_hash` / `binding_hash` 可能失效，旧任务不可续跑。
  该特例只适用于 `basic_generate`，其它 binding 仍遵守 immutable + v2 规则。
- **依赖**：ComfyUI ≥ 0.37.0；`UnetLoaderGGUF`（ComfyUI-GGUF）；`TextEncodeQwenImage21`（内置）；
  `LoraLoader`（内置）；三件套模型 + 两条 LoRA 必须存在。
- **性能事实**：本链已长期用于夜间批量与日用实例；W0 未重新执行 G4 峰值测量，
  本文不提供显存峰值或耗时承诺。真实性能以 `docs/COMFY_ENV_INVENTORY.md` 与后续 G4 记录为准。
- **参考**：`docs/WORKFLOW_SUBMISSION_STANDARD.md`、`docs/WORKFLOW_INVENTORY.md`。
