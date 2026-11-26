# anime_generate v3 — FaceDetailer 修脸版

## 与 v2 的差异

在 v2 纯底模直出链路的最后追加自动修脸：

```
CheckpointLoaderSimple → EmptyLatentImage → CLIPTextEncode(正/负)
→ KSampler (30步/cfg4/er_sde/simple) → VAEDecode
→ UltralyticsDetectorProvider (bbox/face_yolov8m.pt)
→ FaceDetailer (guide 512 / denoise 0.5 / 同主采样参数)
→ SaveImage
```

- FaceDetailer 自动检测画面中的人脸，放大到 512px 导向尺寸重绘（denoise 0.5），再贴回原图（feather 5 羽化）。
- 检测模型：`app/models/ultralytics/bbox/face_yolov8m.pt`（Impact Subpack）。
- 脸部重绘 seed 固定为 0（workflow.json 节点 "20"），主图 seed 仍由 Module 标准输入注入节点 "7"。

## 实测记录（R3，2026-11-09，seed 314159）

- 修脸链路稳定：检测正常、重绘无边界痕迹、手部不受影响。
- 基线本身脸部质量好时提升细微；脸部小崩（常见于复杂构图）时收益明显。
- 耗时：v2 直出约 33s/张 → v3 约 50-60s/张（模型常驻）。

## 维护注意

- 本机已实测移除的组件，勿再加回：turboANIMA LoRA（CFG1 出图发灰）、SageAttention 1.x（3060 负优化）。
- v2 保留冻结，可随时切回对照（`configs/workflow.yaml` 的 binding_version）。
