# anime_generate v4 — LoRA 版

## 来源

- 基线：`anime_generate/v3`（MiaoMiao Harem v14 + FaceDetailer）。
- 新增 LoRA：`Hentai Pussy inspection_Pony_V1.safetensors`
  - 作者：満珍楼 (COSiNE)
  - 来源：Civitai model 570883 / version 636338
  - 底模：Pony；文件大小 114,442,348 bytes
  - SHA256：`dc24ee0135af27b4c3940e06936b8533a153fddd95768e1ca961ceb7d3a373a4`

## 节点图

```
CheckpointLoaderSimple(1)
 ├─ model ─→ LoraLoader(21).model ─→ KSampler(7).model
 │                                └→ FaceDetailer(20).model
 ├─ clip  ─→ LoraLoader(21).clip  ─→ CLIPTextEncode(5/6).clip
 │                                └→ FaceDetailer(20).clip
 └─ vae   ────────────────────────→ VAEDecode(8) / FaceDetailer(20).vae

EmptyLatentImage(4) → KSampler(7) → VAEDecode(8)
  → UltralyticsDetectorProvider(18) → FaceDetailer(20) → SaveImage(9)
```

## 注入契约

| 标准输入 | 节点 | 字段 |
| --- | --- | --- |
| positive_prompt | 5 | text |
| negative_prompt | 6 | text |
| width / height | 4 | width / height |
| seed | 7 | seed |

LoRA 文件名与强度固定在 binding 的 `defaults."21"`（1.0 / 1.0），不进入模块标准输入。

## 已知限制

- LoRA 与 FaceDetailer 均为 binding 级常开；对照 v3 时把节点 21 的两个 strength 设为 0，
  或临时修改本目录副本（不提交）。
- 832×1216 / 30 步档的耗时与显存峰值见 `release_manifest.yaml` 的 G4 证据；
  未测前不得标记 `measured`。
- 不叠加第二个 LoRA、不接 ControlNet、不做 4x 放大（显存限制，项目已否决）。
