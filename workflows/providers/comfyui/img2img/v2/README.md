# img2img / v2（ComfyUI Provider Binding）

## 来源

从已冻结的 `img2img/v1` 派生，节点图与模型链完全相同：

- Qwen-Image 2.1 UC Q4（`qwen-image-2.1-UC-Q4_0.gguf`）+ qwen3vl text encoder（w4a8）+ Qwen VAE；
- `LoadImage → VAEEncode → KSampler(denoise) → VAEDecode → SaveImage`；
- 采样参数：25 步 / cfg 1.0 / euler / simple。

## 与 v1 的唯一差异

- 默认 `denoise`：v1 = **0.55**（冻结，历史 Job 保留）；v2 = **0.8**（与 Python `DEFAULT_DENOISE` / ParameterSpec 一致）。

W1-0 修复背景：W0 曾直接修改 v1 的 `binding.yaml` / `workflow.json`，违反 immutable 规则。
审计确认没有任何 Job 使用 W0 新指纹后，v1 已恢复为 94aa003 原始内容，0.8 配置迁入 v2；
新任务默认绑定 v2，历史 Job 仍按 v1 身份恢复。

## 注入契约

| 标准输入 | 注入位置 | 说明 |
| --- | --- | --- |
| `input_image` | 节点 4（LoadImage.image） | 引擎侧引用名，由 `upload_input_image` 上传 |
| `positive_prompt` / `negative_prompt` | 节点 6 | |
| `seed` / `denoise` | 节点 7 | denoise 由模块 config 注入，不在 defaults |

## 依赖与性能

见 `binding.yaml` 的 `requirements` / `performance`：

- 已记录 768×768 / 25 步 / denoise 0.8 的采样约 496 秒（不含排队与冷加载）；
- 输入尺寸的总像素预算尚未限制（W2）。

## 修改纪律

v2 自此视为 immutable：修改必须新建 `v3/`，双指纹不一致会被拒绝执行。
