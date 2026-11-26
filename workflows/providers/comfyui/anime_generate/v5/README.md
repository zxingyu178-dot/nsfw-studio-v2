# anime_generate v5 — 动态 LoRA 叠加（0–2 条）

## 契约

任务创建时在 `snapshot.workflow_modules[].config` 传入：

```json
{
  "loras": [
    {"name": "Hentai Pussy inspection_Pony_V1.safetensors", "strength_model": 1.0, "strength_clip": 1.0},
    {"name": "Expressive_H-000001.safetensors", "strength_model": 0.5, "strength_clip": 0.5}
  ]
}
```

- 最多 2 条；强度范围 `-2～2`；
- `name` 必须存在于 ComfyUI `/models/loras`（不存在 → `422 LORA_NOT_FOUND`）；
- 超过 2 条 → `422 LORA_LIMIT_EXCEEDED`；
- 字段/类型/范围错误 → `422 LORA_PARAM_INVALID` / `LORA_STRENGTH_OUT_OF_RANGE`；
- 不传 `loras` 或空数组 = 直接使用底模，0 条时节点被移除。

## 节点图重写

模板中固定存在 `LoraLoader(21)` 与 `LoraLoader(22)`：

| 配置 | 结果 |
| --- | --- |
| 0 条 | 删除 21/22，下游引用 checkpoint |
| 1 条 | 使用 21，删除 22，下游引用 21 |
| 2 条 | 21 → 22 串联，下游引用 22 |

由 `ComfyUIAdapter._apply_lora_stack()` 按 `parameters.loras` 动态改写；
抽象层不感知具体 LoRA 文件名，v1–v4 binding 行为不变。

## 校验时机

1. 创建 Job：`PipelineValidator → AnimeGenerateModule.validate_config`（数量/字段/范围）；
2. 创建 Job：`validate_task_loras()` 调 ComfyUI `/models/loras`（存在性，60s 缓存）；
3. 提交引擎前：adapter 再校验一次，防止文件在校验后被移走。

## 实测（2026-11-14）

- 同一 Prompt / Seed `20261114`，0/1/2 条各一张，全部 `COMPLETED`：
  - 0 条：90s，`img_ce734c5f…`
  - 1 条：202s，`img_0d79664f…`
  - 2 条：275s，`img_d15f7b65…`
- 0 vs 1 像素差 44.97，1 vs 2 像素差 15.75 → 栈确实生效；
- 0 条与 v4 strength=0 / v3 同构图一致（节点移除，图结构等价）。

## 已知限制

- 1 条 202s、2 条 275s，超过需求 ≤180s；FaceDetailer 常开，显存峰值未采样；
- LoRA 列表暂不进入工作台 UI，仅 API / Agent 任务配置可用。
