# upscale / v1（ComfyUI Provider Binding）

## 来源

复用本机已验证的高清链（用户工作流「千问-4x审核放大.json」的 API 化）：

```text
LoadImage → UpscaleModelLoader(4x-UltraSharp) → ImageUpscaleWithModel → SaveImage
```

- 模型：`4x-UltraSharp.pth`（67 MB，本机 `app/models/upscale_models/`）；
- 不升级 ComfyUI、不安装新节点、不下载新模型。

## 注入契约

| 标准输入 | 注入位置 |
| --- | --- |
| `input_image` | 节点 1（LoadImage.image，引擎侧引用名） |

- 无 Prompt / Seed / 宽高注入；输出固定 4 倍；
- `Image.kind = upscaled`，parent = 输入图；
- SaveImage 前缀包含 Studio 身份，支持崩溃恢复核对。

## 性能与验收

- 现役轻量放大链，日常使用；
- 放大后的内存占用与输出尺寸 G4 尚未单独记录（见 `docs/WORKFLOW_TECH_DEBT.md`）；
- SeedVR2 仍是重型备选，暂不接入。

## 修改纪律

本目录视为 immutable：修改必须新建 `v2/`，双指纹不一致会被拒绝执行。
