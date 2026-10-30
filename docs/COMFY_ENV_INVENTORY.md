# COMFY_ENV_INVENTORY — 本机 ComfyUI 环境调查

> 调查时间：2026-10-07（Phase 2B，规范 §二十五、§二十六）
> 调查方式：只读检查 + ControlHub 已批准的生命周期入口启动服务；**未修改**任何模型/节点/工作流。

## 1. 安装与运行时

| 项 | 值 |
| --- | --- |
| 安装位置 | `D:\AIHome_2.0_L1_L2\projects\comfyui\`（AIHome 受管项目 `comfyui`） |
| ComfyUI 本体 | `app\`（上游浅克隆 v0.37.0，commit c194dd0，2026-09-21） |
| Python 环境 | `venv\`（Python 3.12.13，项目内独立 venv，未污染系统） |
| torch | 2.9.1+cu128 / torchvision 0.24.1+cu128 |
| GPU | NVIDIA RTX 3060 Laptop，6 GB 显存；R7 5800H / 16 GB 内存 |
| API 地址 | `http://127.0.0.1:8188`（loopback-only UI/API） |
| WebSocket | `ws://127.0.0.1:8188/ws`（ComfyUI 标准进度通道） |
| 就绪探针 | `http://127.0.0.1:8490/health/ready`（载体身份就绪，8290 已弃用） |
| 版本 | ComfyUI 0.37.0（上游 commit c194dd0） |
| 生命周期 | 计划任务 `\AIHome\ComfyUI`（当前用户、非提权、手动启停；ControlHub 已批准，revision 13） |
| 日志 | `runtime\logs\carrier.log`、`runtime\logs\comfyui.log` |

## 2. 输出目录

- ComfyUI output：`D:\AIHome_2.0_L1_L2\projects\comfyui\app\output\`（SaveImage 默认根）。
- **规范 §三十九**：该目录只是"Engine 输出来源"，Studio 图片必须导入
  `DataRoot/images/originals/` 并登记数据库后才算正式资产。

## 3. 模型清单（实际存在的）

公共配置 `app/extra_model_paths.yaml` 指向 **`C:/ComfyUI_models/`**（Qwen 三件套已迁至 C 盘 NVMe）：

| 类型 | 路径 | 文件 |
| --- | --- | --- |
| diffusion_models | `C:/ComfyUI_models/diffusion_models/` | `qwen-image-2.1-UC-Q4_0.gguf`（Qwen-Image 2.1 UC GGUF Q4_0 量化，4.15 GB） |
| text_encoders | `C:/ComfyUI_models/text_encoders/` | `qwen3vl_8b_w4a8.safetensors`（Qwen3-VL 8B W4A8，6.31 GB） |
| vae | `C:/ComfyUI_models/vae/` | `qwen_image_2.1_vae_bf16.safetensors`（675 MB） |
| diffusion_models | `app/models/diffusion_models/` | `Anima-2.9B-preview-v1_int8_convrot.safetensors`（2.87 GB，动漫链） |
| text_encoders | `app/models/text_encoders/` | `qwen_3_06b_base.safetensors`（1.11 GB，Anima 文本编码器） |
| vae | `app/models/vae/` | `qwen_image_vae.safetensors`（0.24 GB，Anima 链） |

> **Anima 路径（W1-3 核实）**：主模型在 `C:/ComfyUI_models/diffusion_models/` 与
> `app/models/diffusion_models/` **各有一份**（名称与大小相同，约 2.87 GB）；
> `anime_generate/v1/binding.yaml` 注释写的是历史位置 `C:\ComfyUI_models`，实际加载路径由
> ComfyUI `folder_paths` 顺序决定。两份均保留，未做删除；环境清单以本节两处记录为准。

其他（`app/models/` 下）：

| 类型 | 文件 |
| --- | --- |
| loras | `qwen_image_2.1_turbo8_lora.safetensors`（913 MB，basic_generate 现役）、`f23gg_nsfw_qwen21.safetensors`（159 MB，basic_generate 现役）、`VNCCS_QI2_PoseStudioV1.1.safetensors`（159 MB，pose 实验）、`qwen2_1-femaledVaginus-nsfw-v1_3-fine_L22-31.safetensors`（637,587,392 B，pose 实验）；另有 DetailTweaker（×3）、cunnyfunky_style、ntc_*、shijinv_realistic（SD 世代，无配套底模） |
| vae | seedvr2_ema_vae(.pth/_fp16)（SeedVR2 放大链用） |
| upscale_models | 4x-UltraSharp.pth |
| checkpoints | `Counterfeit-V3.0_fix_fp16.safetensors.bad`（**损坏/弃用标记**，无可用 SD checkpoint） |
| controlnet | 空 |

> 结论：本机实际可用生图模型 = **Qwen-Image 2.1 UC（GGUF）文生图链**；无可用 SD/SDXL checkpoint
> （唯一文件带 `.bad` 标记）。Phase 2 的 `basic_generate` 以 Qwen 链为准（§二十八：以真实存在且可工作的为准）。

## 4. 自定义节点（custom_nodes，未做任何改动）

- ComfyUI-GGUF（`UnetLoaderGGUF` 依赖，Qwen GGUF 加载必需）
- ComfyUI-Manager
- ComfyUI_VNCCS_Utils（VNCCS PoseStudio / 姿势库；pose 实验已下线，正式模块不使用）
- ComfyUI-OpenPose-Studio
- ComfyUI-SeedVR2-1.4B（SeedVR2 高清/修复链依赖，Phase 2 不使用）
- cg-image-picker
- comfyui-impact-pack / impact-subpack
- websocket_image_save.py（自定义保存节点）

## 5. 启动方式（Studio 侧约定）

- Studio **不自行管理 ComfyUI 生命周期**：由计划任务 `\AIHome\ComfyUI` 承载（ControlHub 唯一事实源）。
- Studio 只消费 API：health 探测 `GET /system_stats`；不可用时任务报 `ENGINE_OFFLINE`（系统性失败，
  队列自动暂停），用户手动启动 ComfyUI 后恢复队列。
- Studio 配置（`configs/config.local.yaml`，gitignore）：

```yaml
comfyui:
  url: "http://127.0.0.1:8188"
  # output_dir 可选：SaveImage 输出根，缺省 <comfyui>/app/output
```

## 6. 环境破坏检查（规范 §二十七）

调查与接入过程**未执行**：升级 ComfyUI、更新/批量安装节点、替换/移动模型、清空 output、
修改原工作流文件。若后续发现缺失依赖，先停下汇报再行动。

## 7. 已知工作流（见 WORKFLOW_INVENTORY.md）

正式模块 5 个：`basic_generate` / `img2img` / `reference_generate` / `anime_generate` / `upscale`。
`basic_generate` 基础选型：**nightbatch 同款 Qwen-Image 2.1 UC 链**，2026-10-27 起叠加
Turbo8 + f23gg 双 LoRA、8 步。
`pose_generate` 双 LoRA 实验已于 2026-10-30 下线（6GB/16GB OOM），代码归档到
`experiment/pose-generate-20261030`，不属于正式模块。

> 说明：模型文件大小只是磁盘事实，不等于显存/内存峰值或执行耗时。真实 Gate 记录见
> `docs/WORKFLOW_TECH_DEBT.md` 与各 binding README。
