# IMAGE_CONDITIONING_INVENTORY — 本机图片条件生成能力调查（Phase 5 Task 0）

> 调查时间：2026-10-08 ｜ 方式：**只读检查**（文件系统 + ComfyUI `/object_info`），
> **未**下载模型 / 安装节点 / 升级 ComfyUI / 更新 Manager / 移动模型 / 修改用户原 Workflow。
> 基线：环境背景见 docs/COMFY_ENV_INVENTORY.md（Phase 2B 调查）与本文件差异说明。

## 1. 调查范围

- `projects/comfyui/app/user/default/workflows/`（7 个用户工作流，逐节点解析）
- 模型目录：`app/models/*`（checkpoints / loras / controlnet / clip_vision / photomaker /
  diffusion_models / vae / upscale_models / embeddings …）+ `C:/ComfyUI_models/`（extra_model_paths）
- `custom_nodes/`（与 Phase 2B 对比是否有新增节点）
- ComfyUI 启动链与模型搜索路径（`extra_model_paths.yaml`、`runtime/carrier.ps1`）
- ComfyUI `/object_info`（1169 个节点）：逐项核对图片条件相关节点是否存在

## 2. 能力矩阵（结论）

| 能力 | 是否可用 | 模型 | Workflow | 缺什么 |
| --- | --- | --- | --- | --- |
| Img2Img（SDXL 现成工作流） | ❌ 不可用 | `RealVisXL_V5.0_fp16.safetensors` **不在磁盘** | `sdxl-图生图.json` 存在且依赖齐全（LoadImage→VAEEncode→KSampler denoise 0.55→VAEDecode） | checkpoint + `add-detail-xl.safetensors` lora 均缺失 |
| Reference（IPAdapter 类） | ❌ 不可用 | 无 | 无 | IPAdapter 节点不存在（/object_info False）+ `clip_vision/` 空 + 无 IPAdapter 模型 |
| Face Reference（PuLID/InstantID/PhotoMaker） | ❌ 不可用 | Photomaker 目录空 | 无 | PuLID/InstantID 节点不存在；PhotoMaker 节点在但无模型 |
| ControlNet | ❌ 不可用 | `controlnet/` 空 | zxy 工作流引用 `control_v11p_sd15_openpose_fp16`（缺失）；ComfyUI-OpenPose-Studio 节点在 | ControlNet 模型缺失（节点 `ControlNetLoader` 在） |
| Qwen-Image-Edit（原生编辑链） | ❌ 不可用 | 仅 Qwen-Image **2.1 base**（无 Edit 模型） | 无 | Edit diffusion model 缺失（`TextEncodeQwenImageEdit` / `ReferenceLatent` 节点在） |
| Qwen latent Img2Img（**可构造候选**） | ⚠️ 依赖齐全、未验证 | ✅ 现有 Qwen 三件套（nightbatch 已真实批量跑通） | 需 Studio 构造 provider binding（标准 latent img2img 图式） | 无新增依赖；质量需 1 次真实最小测试确认 |

## 3. 结论（明确）

> **需要新增模型/节点，已停止（Gate B）。**
> 本机**不存在**任何"现成、稳定、无需新增关键依赖"的参考图/图生图工作流：
> 唯一现成的 Img2Img 工作流（`sdxl-图生图.json`）缺少 checkpoint 与 lora；
> Reference / Face Reference / ControlNet / Qwen-Edit 均缺节点或模型。
> **真实 Module 接入暂停**，等待用户在 §6 候选方案中选择；Phase 5 其余产品功能继续完成。
> 本阶段**零真实生图**（合同 §29 Gate B）。

## 4. 详细证据

### 4.1 用户工作流逐节点解析（7 个）

| 工作流 | 类型 | 依赖模型 | 磁盘现状 |
| --- | --- | --- | --- |
| `qwen21-UC-文生图.json` | 文生图 | qwen GGUF 三件套 | ✅ 全部存在（= 现有 basic_generate 同款链） |
| `千问-4x审核放大.json` | 放大 | 4x-UltraSharp.pth | ✅（= 现有 upscale/v1 同源） |
| `千问-批量审核4x可视化.json` | 批量文生+放大 | qwen 三件套 + 4x | ✅ 模型齐；依赖循环/开关类节点（StartLoop/ComfySwitchNode/Preview Chooser 等）已随节点包存在 |
| `sdxl-图生图.json` | **Img2Img** | RealVisXL_V5.0_fp16 + add-detail-xl | ❌ 两个模型都不在磁盘 |
| `sdxl-写实年轻化.json` | 文生图 | RealVisXL_V5.0_fp16 + add-detail-xl | ❌ 同上 |
| `zxy_optimized_workflow.json` | 文生图+ControlNet+FaceDetailer | majicmixRealistic_v7 + control_v11p_sd15_openpose + vae-ft-mse + DetailTweaker_v2 + 4x-UltraSharp | ❌ checkpoint/controlnet/vae 缺失（lora 与 4x 在） |
| `zxy_original_backup_workflow.json` | 同上（旧版） | 同上 | ❌ 同上 |

### 4.2 模型磁盘清单（实际存在）

```text
app/models/checkpoints/     Counterfeit-V3.0_fix_fp16.safetensors.bad（损坏/弃用，无可用 checkpoint）
app/models/loras/           DetailTweaker ×3 / cunnyfunky_style / ntc_×4 / shijinv_realistic
                            （无 add-detail-xl）
app/models/controlnet/      空
app/models/clip_vision/     空
app/models/photomaker/      空
app/models/diffusion_models/ seedvr2 三个变体（放大/修复链用）
app/models/vae/             seedvr2_ema_vae(.pth/_fp16)
app/models/upscale_models/  4x-UltraSharp.pth
app/models/embeddings/      EasyNegativeV2
C:/ComfyUI_models/          diffusion_models/qwen-image-2.1-UC-Q4_0.gguf
                            text_encoders/qwen3vl_8b_w4a8.safetensors
                            vae/qwen_image_2.1_vae_bf16.safetensors
```

模型搜索路径（决定"ComfyUI 能否看到"）：
`extra_model_paths.yaml` 仅配置 `C:/ComfyUI_models/`（diffusion_models / vae / text_encoders），
启动链（`runtime/carrier.ps1`）未追加其他 `--extra-model-paths-config`；
即 **ComfyUI 实际可见模型 = app/models + C:/ComfyUI_models**——两处均无 RealVisXL / add-detail /
任何 ControlNet / IPAdapter / PuLID / InstantID / PhotoMaker / Qwen-Edit 模型。

### 4.3 节点可用性（/object_info，ComfyUI 0.37.0，共 1169 节点）

| 节点 | 存在 | 说明 |
| --- | --- | --- |
| `IPAdapterModelLoader` / `IPAdapterAdvanced` | ❌ | IPAdapter 节点包未安装 |
| `PulidModelLoader` / `InstantIDModelLoader` | ❌ | PuLID / InstantID 未安装 |
| `PhotoMakerLoader` / `PhotoMakerEncode` | ✅ | 核心节点在，但 photomaker 模型目录为空 |
| `ControlNetLoader` | ✅ | 核心节点在，但 controlnet 模型目录为空 |
| `TextEncodeQwenImageEdit` / `ReferenceLatent` | ✅ | Qwen-Edit 原生节点在（0.37.0），但无 Edit 模型 |
| `VAEEncode` / `KSampler` / `TextEncodeQwenImage21` / `VAEDecode` | ✅ | 现有 Qwen 链全部核心节点 |

### 4.4 用户后来自行安装内容（与 Phase 2B 调查对比）

- custom_nodes：**无新增**（仍为 GGUF / Manager / OpenPose-Studio / SeedVR2 / cg-image-picker /
  impact-pack / impact-subpack / websocket_image_save）。
- 模型：新增少量 lora（ntc 系列扩充、shijinv_realistic）与 EasyNegativeV2、SeedVR2 变体；
  **无任何图片条件类新模型**（无 SDXL checkpoint、无 ControlNet、无 IPAdapter 系）。
- 推断：`RealVisXL_V5.0` / `add-detail-xl` 是用户曾用过（工作流存在）但当前磁盘已不存在；
  若用户希望恢复该链，需重新获取模型（见 §6 方案 1）。

## 5. 对 Studio 的直接影响

- Gate B：不实现真实 Img2Img / Reference Module；`ModuleCapabilities` 的
  `input_required / input_role` 与通用输入图片冻结机制仍按通用层实现（为未来 Module 就绪）。
- Phase 5 完成全部"图片作为输入"产品能力：外部导入 → Gallery → 工作台输入图 → Recipe 快照 →
  Job 冻结输入关系 → Face Asset Reference（数据关系，不依赖任何模型）。

## 6. 候选方案（不下载，等待用户决定）

### 方案 0（零下载 / 零安装，最优先验证）— 现有 Qwen-Image 2.1 链构造 latent Img2Img

> **✅ Phase 5.1 已验证通过（2026-10-08）**：1 张 768×768 真实实验 + denoise 1.0 对照，
> 无缺节点/缺模型/无 OOM，输入图对输出有决定性影响（详见 docs/PHASE51_REPORT.md），
> 已正式落地 `Img2ImgModule` + `img2img/v1` binding（v0.7.0）。

| 项 | 内容 |
| --- | --- |
| 模型 | 无需下载（qwen-image-2.1-UC-Q4_0.gguf + qwen3vl_8b_w4a8 + qwen vae；nightbatch 已真实批量跑通） |
| 用途 | 通用 Img2Img（输入图 + Prompt + strength/denoise → 新图，`kind=processed`，parent=输入图） |
| 节点 | 全部核心节点已存在（VAEEncode / KSampler / TextEncodeQwenImage21 / VAEDecode / SaveImage） |
| 显存 | 与现有 basic_generate 相同（Qwen 2.1 UC Q4 在本机 6GB 已稳定运行） |
| 对现有 ComfyUI 的影响 | **零**（只新增 Studio 自己的 provider binding 目录，不改用户工作流/模型/节点） |
| 风险 | Q4 量化 + 中等 denoise 下的编辑质量需实测确认；需批准后做 **1 次真实最小测试** |
| 工作量 | 新增 `img2img/v1` binding + `Img2ImgModule`（不修改 QueueWorker / Pipeline / ImageService 核心） |

### 方案 1（恢复用户原 SDXL 图生图链）

| 项 | 内容 |
| --- | --- |
| 模型 | `RealVisXL_V5.0_fp16.safetensors`（≈6.5GB）→ `app/models/checkpoints/`；`add-detail-xl.safetensors`（≈0.2GB）→ `app/models/loras/` |
| 用途 | 恢复 `sdxl-图生图.json` 原貌（denoise 0.55，Standard Img2Img；也恢复 `sdxl-写实年轻化`） |
| 节点 | 无需新增（全为核心节点） |
| 显存 | SDXL fp16 在 6GB Laptop 需分块/–lowvram；832×1216 可行性需实测（比 Qwen 轻） |
| 对现有 ComfyUI 的影响 | 低（仅新增两个模型文件；不移动、不替换任何现有文件） |
| 风险 | 下载体积 ~6.7GB；磁盘 D 剩 143GB、C 剩 39GB（建议放 D 的 app/models） |

### 方案 2（备选，暂不推荐）— Qwen-Image-Edit 原生编辑链

需确认 ComfyUI 0.37.0 对 Edit 模型的完整支持并获取 Edit 模型（GGUF Q4 约 12GB 级）；
20B 在 6GB 上推理慢、版本匹配风险高、体积大。仅在方案 0 质量不满足且用户要更强编辑时评估。

### 方案 3（Reference 路线，组合成本最高，暂不推荐）

IPAdapter 系需要：安装节点包（ComfyUI_IPAdapter_plus）+ `clip_vision`（≈2.5GB）+
IPAdapter 模型（≈1GB），且本机无可用 SDXL checkpoint，三者叠加方可运行。

> 所有方案均等待用户选择；**本阶段不执行任何下载或安装**。