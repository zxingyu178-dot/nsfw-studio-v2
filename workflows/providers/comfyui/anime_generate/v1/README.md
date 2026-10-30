# anime_generate / v1（ComfyUI Provider Binding — Anima 2.9B 动漫链）

## 来源

- 官方蓝图：本机 ComfyUI `blueprints/Text to Image (Anima).json`（comfy-core 内置）；
- 模型仓库：`circlestone-labs/Anima`（动漫 / 插画向扩散模型）；
- 本机模型（已就位，零下载接入，位于 `C:\ComfyUI_models` 与 ComfyUI 自身模型目录）：

| 角色 | 文件 | 大小 |
| --- | --- | --- |
| 主模型 | `Anima-2.9B-preview-v1_int8_convrot.safetensors` | 2.87 GB |
| 文本编码器 | `qwen_3_06b_base.safetensors`（CLIPLoader `type=stable_diffusion`，按官方蓝图） | 1.11 GB |
| VAE | `qwen_image_vae.safetensors` | 0.24 GB |

> 官方蓝图原话：本模型擅长动漫 / 艺术风格，**写实主体表现很差**——写实人物请用 `basic_generate`。

## 性能与验收（2026-10-30）

- 上表 4.22 GB 只是**磁盘模型文件大小**，不是显存/内存峰值，也不能据此推断“轻量/快速”。
- `CLIPLoader` 使用 `device=default`，未针对 6GB 显存做加载策略验证；
- 移植到当前 v0.37.0 基线后，**真实 ComfyUI G3 Gate 尚未执行**；
- 正式状态：**待真实验收**。未通过 G3/G4 前不得宣传“轻量、快速、批量首选”，
  也不得安排批量生成。详见 `docs/WORKFLOW_TECH_DEBT.md`。

## 图结构（与 basic_generate/v1 的差异）

```
UNETLoader(Anima) → CLIPTextEncode(正/负) → KSampler(EmptyLatent, denoise=1.0) → VAEDecode → SaveImage
```

- 使用标准 `CLIPTextEncode`（非 Qwen 系 `TextEncodeQwenImage21`）；
- 采样参数：**30 步 / cfg 4.0 / er_sde / simple**（官方蓝图原值，`defaults` 固定）。

## 注入契约

| 标准输入 | 注入位置 |
| --- | --- |
| `positive_prompt` | 节点 5（CLIPTextEncode.text） |
| `negative_prompt` | 节点 6（CLIPTextEncode.text；默认蓝图负向词在绑定里，可由工作台覆盖） |
| `width` / `height` | 节点 4（EmptyLatentImage） |
| `seed` | 节点 7（KSampler.seed，每张独立随机） |

## 输出语义

- 输出尺寸 = 显式宽高（`size_mode=explicit`）；`Image.kind = original`，无 parent；
- 保存前缀包含 Studio 身份（job/stage/item），支持崩溃恢复的文件级核对。

## 修改纪律

本目录视为 **immutable**：修改必须新建 `v2/`（`workflow_hash` / `binding_hash` 双指纹校验，
防止历史 Job 静默换链）。

## 已知本机事项（2026-10-10）

- `anima-turbo-v1.0.safetensors`（ComfyUI models/diffusion_models 下）是 **15 字节的失败下载
  占位文件**（内容 "Entry not found"），不可用；如需 turbo 变体请重新下载正确文件后新建
  binding 版本，不要直接改本目录。
- Anima 主模型文件在 `C:\ComfyUI_models` 与 ComfyUI 自身 `models/diffusion_models` 下各有一份
  （约 2.87 GB ×2），确认无引用后可删除其中一份。