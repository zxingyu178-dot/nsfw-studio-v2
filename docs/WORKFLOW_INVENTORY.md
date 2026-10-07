# WORKFLOW_INVENTORY — 本机 ComfyUI 工作流调查

> 调查时间：2026-10-07（Phase 2B，规范 §二十五、§二十六、§二十八）。只读调查，未修改原工作流。

## 1. 用户工作流（`projects/comfyui/app/user/default/workflows/`）

| 文件 | 说明（据名称/内容） | 状态 |
| --- | --- | --- |
| `official-sd15` | SD1.5 官方示例链 | 无可用 checkpoint（唯一 ckpt 带 .bad 标记），**当前不可跑** |
| `qwen21-UC-文生图.json` | Qwen-Image 2.1 UC 文生图 | 与 nightbatch API 链同源，**真实跑通** |
| `sdxl-写实年轻化.json` | SDXL 写实 | 依赖 SDXL checkpoint，当前不可跑 |
| `sdxl-图生图.json` | SDXL 图生图 | 同上 + 本阶段禁止图生图 |
| `zxy_optimized_workflow.json` / `zxy_original_backup_workflow.json` | 用户自调链 | 未验证 |
| `千问-4x审核放大.json` / `千问-批量审核4x可视化.json` | Qwen + 4x-UltraSharp 审核放大 | 放大链，Phase 2 禁止 |

## 2. API 构造式工作流（`projects/nightbatch/night_runner.py`，已验证）

nightbatch 夜间批量写真（已登记 Registry，真实跑通 20+ 张/晚）使用的文生图链，
即 `basic_generate` 的选型基础（规范 §二十八：不自行设计，选现有可跑的）：

```text
10 UnetLoaderGGUF        unet_name = qwen-image-2.1-UC-Q4_0.gguf
11 CLIPLoader            clip_name = qwen3vl_8b_w4a8.safetensors, type=qwen_image, device=cpu
12 VAELoader             vae_name  = qwen_image_2.1_vae_bf16.safetensors
13 TextEncodeQwenImage21 clip=[11,0], prompt, negative_prompt, resolution=1024
22 EmptyLatentImage      width, height, batch_size=1
23 KSampler              model=[10,0], seed, steps, cfg, euler/simple, positive=[13,0],
                         negative=[13,1], latent=[22,0], denoise=1.0
24 VAEDecode             samples=[23,0], vae=[12,0]
25 SaveImage             images=[24,0], filename_prefix=NSFWStudio/<date>
```

### 输入参数（= basic_generate 标准输入）

| 参数 | 注入位置 | 说明 |
| --- | --- | --- |
| positive_prompt | 节点 13 `prompt` | |
| negative_prompt | 节点 13 `negative_prompt` | **本链支持 Negative**（`supports_negative_prompt = true`） |
| width / height | 节点 22 | 生成时校验（Qwen 支持 1024 档；分辨率由 TextEncodeQwenImage21.resolution 配合） |
| seed | 节点 23 `seed` | 范围按 KSampler/ComfyUI 惯例 0 ~ 2^31-1（nightbatch 同款取模） |
| steps / cfg | 节点 23 | 默认 steps=25、cfg=1.0（nightbatch 实测值） |

### 输出节点

- 节点 25 `SaveImage`：`filename_prefix` 可注入（Studio 用 `NSFWStudio/<date>/` 前缀隔离输出），
  产物落在 `app/output/<prefix>_xxx.png`；history API 可按 prompt_id 取回文件名。

## 3. 依赖核对

| 依赖 | 状态 |
| --- | --- |
| ComfyUI-GGUF（UnetLoaderGGUF） | ✅ 已安装 |
| TextEncodeQwenImage21（ComfyUI 内置，0.37.0） | ✅ |
| 三件套模型（C:/ComfyUI_models） | ✅ 存在 |
| 6GB 显存跑 Q4_0 GGUF | ✅ nightbatch 已长期验证 |

**结论：无需安装任何缺失依赖**（规范 §二十七 无需触发"停下汇报"分支）。

## 4. basic_generate Binding 决策

- 载体：`workflows/providers/comfyui/basic_generate/v1/`（workflow.json + binding.yaml + README），
  ComfyUI 节点 ID 只存在于 provider binding 层，不污染引擎无关核心（规范 §二十九）；
- workflow.json = 上述节点图的参数化模板（SaveImage prefix、13.prompt/negative、22 尺寸、23.seed 为注入点）；
- steps/cfg 保留 nightbatch 实测默认（25 / 1.0），Module 标准输入不暴露（Phase 2 范围外）。
