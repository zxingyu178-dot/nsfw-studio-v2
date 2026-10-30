# WORKFLOW_INVENTORY — 本机 ComfyUI 工作流调查

> 更新：2026-10-30（W0 工作流治理）。本文只记录真实存在的 binding、模型与性能事实；
> 提交标准见 `docs/WORKFLOW_SUBMISSION_STANDARD.md`，技术债见 `docs/WORKFLOW_TECH_DEBT.md`。

## 1. 正式 binding 清单（5 个）

| Module | Binding | 模型链 | 采样默认 | 依赖 | 性能状态 |
| --- | --- | --- | --- | --- | --- |
| `basic_generate` | `comfyui/basic_generate/v1` | Qwen-Image 2.1 UC Q4 GGUF + Qwen3-VL 8B（CPU）+ VAE + Turbo8 + f23gg | 8 步 / cfg 1.0 / euler-simple / 1024 | ComfyUI-GGUF、TextEncodeQwenImage21、LoraLoader | 日用主力；W0 未重新测 G4 |
| `img2img` | `comfyui/img2img/v1` | 同三件套；LoadImage → VAEEncode → KSampler | 25 步 / cfg 1.0 / denoise 0.8 | 同上 | 768×768 真实可用；0.8 采样约 496s、0.55 约 310s（不含排队） |
| `reference_generate` | `comfyui/reference_generate/v1` | 同三件套 + TextEncodeQwenImage21 参考 latents | 25 步 / cfg 1.0 / resolution 1024 | 同上 | 已验证 640/20 步单张 60+ 分钟；1024/25 未验证 |
| `anime_generate` | `comfyui/anime_generate/v1` | Anima-2.9B INT8 + Qwen3-0.6B + VAE | 30 步 / cfg 4.0 / er_sde-simple | UNETLoader、CLIPTextEncode、KSampler | **待真实验收**；4.22GB 仅是磁盘大小 |
| `upscale` | `comfyui/upscale/v1` | 4x-UltraSharp | 4x 放大 | UpscaleModelLoader、ImageUpscaleWithModel | 轻量优先；SeedVR2 暂不接入 |

`basic_generate` 版本特例：单目录 `v1/`，不新建 v2，版本靠 Git 历史（2026-10-27 用户确认）。
其它已投入使用 binding 修改必须新建 v2。

## 2. basic_generate 真实链（2026-10-27 起）

```text
1 UnetLoaderGGUF        qwen-image-2.1-UC-Q4_0.gguf
2 CLIPLoader            qwen3vl_8b_w4a8.safetensors, type=qwen_image, device=cpu
3 VAELoader             qwen_image_2.1_vae_bf16.safetensors
4 TextEncodeQwenImage21 clip=[2,0], prompt, negative_prompt, resolution=1024
5 EmptyLatentImage      width, height, batch_size=1
9 LoraLoader            model=[1,0], clip=[2,0], turbo8, model/clip 1.0
10 LoraLoader           model=[9,0], clip=[9,1], f23gg, model 0.8 / clip 1.0
6 KSampler              model=[10,0], seed, steps=8, cfg=1.0, euler/simple,
                        positive=[4,0], negative=[4,1], latent=[5,0], denoise=1.0
7 VAEDecode             samples=[6,0], vae=[3,0]
8 SaveImage             images=[7,0], filename_prefix=NSFWStudio/<job>/<stage>/<item>
```

注入点见 `binding.yaml`：positive/negative → 节点 4，宽高 → 节点 5，seed → 节点 6。
binding 的 `defaults."6".steps=8` 覆盖 workflow.json 节点值；**不得恢复旧的 25 步说明**。

## 3. 用户工作流（`projects/comfyui/app/user/default/workflows/`）

| 文件 | 说明 | 状态 |
| --- | --- | --- |
| `official-sd15` | SD1.5 官方示例链 | 无可用 checkpoint（唯一 ckpt 带 .bad），不可跑 |
| `qwen21-UC-文生图.json` | Qwen-Image 2.1 UC 文生图 | 与 nightbatch API 链同源，真实跑通 |
| `sdxl-写实年轻化.json` | SDXL 写实 | 依赖 SDXL checkpoint，当前不可跑 |
| `sdxl-图生图.json` | SDXL 图生图 | 同上，不可跑 |
| `zxy_optimized_workflow.json` / `zxy_original_backup_workflow.json` | 用户自调链 | 引用底模/ControlNet 全部缺失，保留但不可运行 |
| `千问-4x审核放大.json` / `千问-批量审核4x可视化.json` | Qwen + 4x-UltraSharp | upscale/v1 同源，可运行 |

## 4. 依赖与模型事实

| 依赖 | 状态 |
| --- | --- |
| ComfyUI 0.37.0 + ComfyUI-GGUF | ✅ |
| `TextEncodeQwenImage21`（内置） | ✅ |
| Qwen 三件套（4.15GB + 6.31GB + 675MB） | ✅ `C:/ComfyUI_models/` |
| Turbo8 LoRA（913MB） + f23gg（159MB） | ✅ `app/models/loras/` |
| Anima 2.9B（2.87GB）+ Qwen3-0.6B（1.11GB）+ VAE（0.24GB） | ✅ 本机已就位；真实 Gate 未执行 |
| 4x-UltraSharp（67MB） | ✅ |
| VNCCS Utils 节点 + 姿势库 136 + VNCCS/femaledVaginus LoRA | ✅ 已安装，但**不属于正式工作流**（见 §5） |

## 5. 实验/下线模块

- `pose_generate`（2026-10-29 实验）：Qwen 三件套 + femaledVaginus + VNCCS LoRA，
  两张参考图（姿势 + 角色），er_sde/beta。768×12 双 LoRA 单张 20 分钟可出图；
  1024×25 在 6GB/16GB 机器上 OOM/停止推进。
  **2026-10-30 已从运行实例与 `main` 下线**，代码保留在
  `experiment/pose-generate-20261030` 分支；未通过 G3/G4 前不得注册为正式模块。
