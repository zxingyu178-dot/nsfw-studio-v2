# REFERENCE_CAPABILITY_INVENTORY — 参考图 / 人物一致性能力重盘（Phase 7 Task3）

> 调查方式：**只读**重盘（HTTP API `system_stats`/`object_info` + 模型目录扫描 + 自定义节点目录 + 节点源码，
> 不沿用几天前的历史清单）。未下载模型、未安装节点、未升级 ComfyUI、未修改用户工作流。
> 调查时间：2026-10-09；目标：为 Phase 7 Reference Gate（Task4）提供事实依据。

## 1. 引擎与节点现状

| 项 | 值 |
| --- | --- |
| ComfyUI | 0.37.0（frontend 1.53.6 / templates 0.11.66 / embedded-docs 0.5.12） |
| 运行方式 | `main.py --port 8188 --disable-auto-launch --lowvram --cache-classic` |
| Python / Torch | 3.12.13 / 2.9.1+cu128 |
| GPU | NVIDIA GeForce RTX 3060 Laptop（**6.0 GB VRAM**，调查时空闲 ~5.2 GB） |
| 内存 | 16 GB（`ram_free` 调查时约 3.1 GB） |
| 节点总数 | 1169（`/object_info`） |
| 已装自定义节点 | `ComfyUI-GGUF`、`comfyui-impact-pack`、`comfyui-impact-subpack`、`ComfyUI-OpenPose-Studio`、`ComfyUI-SeedVR2-1.4B`、`cg-image-picker`、`ComfyUI-Manager` |

## 2. 模型现状（ComfyUI 可加载清单 = object_info 权威 + 磁盘核查）

### 2.1 实际存在且可加载

| 模型 | 文件 | 大小 | 加载器 | 位置 |
| --- | --- | --- | --- | --- |
| **Qwen-Image 2.1（UC Q4_0 GGUF）** | `qwen-image-2.1-UC-Q4_0.gguf` | 4.15 GB | `UnetLoaderGGUF` | `C:/ComfyUI_models/diffusion_models/`（extra_model_paths.yaml，NVMe SSD） |
| Qwen 文本/视觉编码器 | `qwen3vl_8b_w4a8.safetensors` | 6.31 GB | `CLIPLoader`（type=`qwen_image`, device=`cpu`） | 同上 |
| Qwen Image 2.1 VAE | `qwen_image_2.1_vae_bf16.safetensors` | 675 MB | `VAELoader` | 同上 |
| SeedVR2 1.4B / 3B + VAE | `seedvr2_*` | 2.9 GB / 13.6 GB ×2 + 0.5-1.0 GB VAE | `UNETLoader` / `VAELoader` | `app/models/`（重型 DiT 放大链） |
| 4x-UltraSharp | `4x-UltraSharp.pth` | 67 MB | `UpscaleModelLoader` | `app/models/upscale_models/`（upscale/v1 现役） |
| 面部/手部/人物检测 | `face_yolov8m.pt` / `hand_yolov8s.pt` / `person_yolov8m-seg.pt` | 52 / 22 / 55 MB | `UltralyticsDetectorProvider`（Impact Pack） | `app/models/ultralytics/` |
| SD 世代 LoRA | DetailTweaker 系列、ntc_*、cunnyfunky_style、shijinv_realistic | 9-78 MB | `LoraLoader` | `app/models/loras/`（**无配套 SD 底模，当前不可用**） |
| 负向 embedding | `EasyNegativeV2.safetensors` | 49 KB | — | `app/models/embeddings/` |

### 2.2 明确缺失（本次重点调查对象）

| 方向 | 节点（ComfyUI 原生/自定义） | 模型 | 结论 |
| --- | --- | --- | --- |
| **Qwen Image Edit**（独立 Edit 权重链） | ✅ 原生 `TextEncodeQwenImageEdit` / `TextEncodeQwenImageEditPlus` / `ReferenceLatent` | ❌ 无任何 Qwen-Image-Edit 权重文件 | 仅缺模型 |
| **Qwen-Image 2.1 原生参考图**（同模型参考编辑） | ✅ 原生 `TextEncodeQwenImage21`（`images` 最多 16 张参考图 + 参考尺寸 latent 输出）、`QwenImage21Cache`、`QwenImageDiffsynthControlnet` | ✅ 现役三件套即为该模型 | **本机现役能力，见 §4 实测** |
| **IPAdapter** | ❌ 自定义节点未安装（`comfyui-impact-pack` 只有依赖 `IPADAPTER_PIPE` 的 `ImpactIPAdapterApplySEGS`，而提供该 pipe 的 IPAdapter 节点缺失） | ❌ 无 ipadapter 权重；`models/clip_vision/` 空；`models/style_models/` 空 | 不可用（节点+模型+底模全缺） |
| **PuLID** | ❌ 无节点 | ❌ 无模型/无 insightface | 不可用 |
| **InstantID** | ❌ 无节点 | ❌ 无 ControlNet/insightface 模型 | 不可用 |
| **PhotoMaker** | ✅ 原生 `PhotoMakerLoader` / `PhotoMakerEncode` | ❌ `models/photomaker/` 为空 | 不可用（仅缺模型） |
| **ControlNet** | ✅ 原生 `ControlNetLoader` / `ControlNetApplyAdvanced` 等 | ❌ `models/controlnet/` 为空；无 Qwen 配套 ControlNet patch | 不可用（仅缺模型） |

### 2.3 历史用户工作流的现状（不能作为"可用链"）

| 工作流 | 引用模型 | 现状 |
| --- | --- | --- |
| `qwen21-UC-文生图.json` | Qwen-Image 2.1 三件套 | ✅ 可运行（Studio basic_generate 同款链） |
| `千问-批量审核4x可视化.json` | Qwen 三件套 + 4x-UltraSharp | ✅ 可运行（TextEncodeQwenImage21 仅用文本，无参考图） |
| `千问-4x审核放大.json` | 4x-UltraSharp | ✅ 可运行（upscale/v1 同款链） |
| `zxy_optimized_workflow.json` / `zxy_original_backup_workflow.json` | `majicmixRealistic_v7`（SD1.5）、`control_v11p_sd15_openpose`、`sam_vit_b_01ec64`、`RealVisXL_V5.0`、`add-detail-xl` | ❌ **引用的底模/ControlNet/SAM 全部不在磁盘**（`checkpoints/` 仅有 1 个损坏的 `.bad` 文件；`CheckpointLoaderSimple` 可加载列表为空）→ 工作流保留但不可运行 |
| `sdxl-图生图.json` / `sdxl-写实年轻化.json` | `RealVisXL_V5.0_fp16`、`add-detail-xl` | ❌ 同上（底模缺失） |

## 3. 关键节点契约（本机 0.37.0 源码核对）

- `TextEncodeQwenImage21`（`comfy_extensions/nodes_qwen.py`）：
  - 输入：`clip`、`prompt`、`negative_prompt`、`vae`（可选）、`resolution`（参考图重采样基准）、
    `images`（Autogrow，`image_1`…`image_16`，可为 0 张）；
  - 输出：`positive` / `negative` / `latent`（**以第一张参考图尺寸生成的空 latent**，
    "to match with sampling as any other size shifts the edit"）；
  - 实现：参考图经视觉塔进文本编码器（`keep_vision=false` 时），VAE 编码为 `reference_latents`
    拼接进 conditioning —— 这是 Qwen 系"参考/编辑"语义的标准条件化路径。
- `TextEncodeQwenImageEdit` / `Plus`：Qwen-Image-Edit 权重专用（本机无权重）。
- `QwenImageDiffsynthControlnet`：Qwen 系 ControlNet patch（本机无 patch 权重）。

## 4. Gate 实测（Task4：1 张真实参考图，零下载，直接 ComfyUI API）

- 方法：`LoadImage`（Phase 6 用过的真实照片，上传至 `input/p7_gate/`）→ `TextEncodeQwenImage21`
  （指令=换衣+换背景+保持身份，resolution=640）→ `KSampler`（20 步 / cfg 1.0 / euler-simple /
  denoise 1.0，沿用用户文生图已验证参数）→ `VAEDecode` → `SaveImage`；模型=现役 Qwen-Image 2.1 三件套。
- 结果：**COMPLETED**（`prompt_id=d50ba446…`，输出 `output/p7_gate/ref_check_00001_.png`）。
  人工比对（参考图 vs 输出）：
  - **身份/主体保持**：同一人物面部与发型、同一侧脸构图（参考条件生效，非普通文生图）；
  - **指令生效**：米色针织衫 → 红色连衣裙；白天咖啡馆窗景 → 夜晚城市街景（霓虹/车灯）；
  - 画面完整、无畸形或崩坏；耗时显著（16GB RAM + 6GB VRAM 低显存流式，单次约 60+ 分钟：
    模型冷加载 ~35 分钟 + 采样）。
- 证据（本地，不入库）：`temp/qwen_ref_gate.py`、`temp/qwen_ref_gate_output.png`。

## 5. 结论（Task4 Gate）

**Gate 通过——本机已存在"无需安装、真实可运行"的参考图/人物一致性链：
Qwen-Image 2.1（现役 GGUF 三件套） + 原生 `TextEncodeQwenImage21` reference latents。**

- 唯一选定方案 = 该链（Phase 7 Task6 已落地为 `reference_generate` v1 Module +
  `workflows/providers/comfyui/reference_generate/v1/` binding）；
- **未选择**：独立 Qwen-Image-Edit 权重链（缺权重，需下载）、IPAdapter（缺节点+模型+底模）、
  InstantID / PuLID（缺节点+insightface+模型）、PhotoMaker / ControlNet（缺模型）——
  全部需要新增下载/安装，本阶段一律不做（见 §2.2）；
- 6GB 显存结论：可运行但**慢**（低显存流式 + 16GB RAM 交换），适合作为"低频高质量能力"，
  不适合批量；如需提速可后续评估更大的量化/缓存参数（本阶段不动）；
- 用户既有 SD 世代工作流（ControlNet/FaceDetailer 等）因模型缺失不可运行，
  不作为本阶段候选。