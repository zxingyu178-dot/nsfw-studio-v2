# basic_generate v1（ComfyUI Provider Binding）

Studio 第一套真实生图工作流绑定（Phase 2B）。

- **来源**：本机已验证可跑的 Qwen-Image 2.1 UC 文生图链（与 `projects/nightbatch` 同款节点图），
  未自行设计新链（规范 §二十八）。
- **模型**：`qwen-image-2.1-UC-Q4_0.gguf` + `qwen3vl_8b_w4a8` 文本编码器 + `qwen_image_2.1_vae_bf16`，
  位于 `C:/ComfyUI_models/`（经 `extra_model_paths.yaml` 挂载）。
- **注入点**：见 `binding.yaml`（positive/negative → 节点 4，宽高 → 节点 5，seed → 节点 6）。
- **输出**：节点 8 SaveImage，前缀 `NSFWStudio/<日期>/`；Adapter 经 `/history` + `/view`
  取回字节后导入 Studio DataRoot，ComfyUI output 目录只作为输出来源（规范 §三十九）。
- **默认采样**：steps=25，cfg=1.0，euler/simple，denoise=1.0（nightbatch 实测值）。
- **升级约定**：修改本链任何节点 → 复制新目录 `v2/` 并更新 `binding_version`；
  旧 Job 通过 `jobs.workflow_hash / binding_version` 溯源（规范 §五十五）。
