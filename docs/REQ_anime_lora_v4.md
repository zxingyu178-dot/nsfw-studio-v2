# 需求：动漫链路接入 LoRA（anime_generate / v4）

- 提出日期：2026-11-14
- 优先级：中（不阻塞现有队列）
- 影响范围：新增工作流模块，**不修改** `anime_generate` v1 / v2 / v3 任何文件

---

## 1. 背景

当前动漫出图走 `anime_generate`，提示词只能靠 Danbooru 标签表达。标签对「颜色」还能勉强控制，对「解剖形状」（如耻丘饱满程度、小阴唇形态）基本失控，6 张里只有 1–3 张符合预期。

已确认一个对口的现成 LoRA，能从标签层面补上这块能力，触发词里直接带形状词表（`fat mons` / `clitoral hood` / `gaping` / `clitoris` 等）。

LoRA 文件已下载完成，放在：

```
D:\AIHome_2.0_L1_L2\projects\comfyui\app\models\loras\Hentai Pussy inspection_Pony_V1.safetensors
```

- 大小 109 MB
- 底模：Pony
- 作者：満珍楼 (COSiNE)
- 来源：Civitai model 570883 / version 636338

**障碍**：`anime_generate` 现有三版 workflow 均无 `LoraLoader` 节点（Checkpoint → CLIP ×2 → KSampler → VAEDecode，v3 多了 FaceDetailer），因此该 LoRA 目前无法被队列加载。项目规范要求「已投入使用的 binding 不可修改」，所以走**新增 v4**。

---

## 2. 要做的事

### 2.1 新增工作流

目录：`workflows/providers/comfyui/anime_generate/v4/`

- `workflow.json`：在 `CheckpointLoaderSimple` 与两个 `CLIPTextEncode` 之间插入 `LoraLoader`
  - `model` ← `["<checkpoint>", 0]`
  - `clip` ← `["<checkpoint>", 1]`
  - `lora_name` ← 上述 safetensors 文件名（含空格，原样写）
  - `strength_model` / `strength_clip` 默认 `1.0` / `1.0`
  - `LoraLoader` 的 `model` 输出接 `KSampler.model`，`clip` 输出接两个 `CLIPTextEncode.clip`
- 采样参数沿用 v3：`steps 30 / cfg 5.5 / dpmpp_2m / karras`
- `FaceDetailer` 可保留，但**必须可关闭**（见验收 3）
- `SaveImage` 的 `filename_prefix` 沿用 `NSFWStudio`

### 2.2 binding

`binding.yaml` 需要声明：

- `requirements.models` 包含该 LoRA 文件（用于 preflight 校验）
- 可配置参数：
  - `lora_name`（枚举或固定默认值）
  - `strength_model`、`strength_clip`（建议范围 0–1.5，默认 1.0）
  - `steps` / `cfg` / `width` / `height` / `count`（与 v3 保持一致）
- 能力声明与 v3 一致：文生图、`input_required=false`

### 2.3 登记

- 在 `workflows/release_manifest.yaml` 按 `docs/WORKFLOW_SUBMISSION_STANDARD.md` 登记 v4 的真实 G0–G4 证据
- 未通过的项如实标注，不要填「已通过」

### 2.4 生效

- 后端重载后，`GET /api/v1/modules` 应出现 `anime_generate` 的 `v4` 条目，`available=true`、`release_status.ready_to_run=true`
- v1 / v2 / v3 行为不变，现有队列任务不受影响

---

## 3. 验收标准

1. **跑通**：用 3 条不同提示词各出 1 张，尺寸 832×1216，全部 `COMPLETED`，无报错。
2. **性能**：单张 ≤ 120 秒（本机 RTX 3060 Laptop，6144 MiB，ComfyUI 以 `--lowvram` 启动）。
3. **LoRA 可关闭**：`strength_model=0` 时输出应接近 v3（肉眼看不出明显风格漂移），证明 LoRA 是可控开关而非硬编码进链路。
4. **不 OOM**：生成期间显存不得越过 6.1 GB，不得因显存失败中断队列。
5. **不阻塞**：验证期间队列保持可提交、可继续，不得长时间 pause。

---

## 4. 明确不做的

- 不修改 v1 / v2 / v3 的 workflow 或 binding
- 不新增 4x 放大、不叠加多个 LoRA、不加 ControlNet（显存不够，本项目已否决）
- 不动 `D:\NSFW-Studio-Data` 数据目录、不改数据库
- 不改 `extra_model_paths.yaml`（LoRA 放在 ComfyUI 默认 `app\models\loras`，无需额外映射）

---

## 5. 交付物

- `anime_generate/v4/workflow.json`、`binding.yaml`
- `release_manifest.yaml` 登记条目
- 3 张样图 + 实测单张耗时 + 生成时显存峰值
- 一句话说明：v4 与 v3 的实际差异、已知未验证项

---

## 6. 测试用触发词（供验收参考）

```
pussy, fat mons, clitoral hood, gaping, close-up, spread legs, presenting
```

对比组：同一提示词在 v3（无 LoRA）下的输出，用于确认形状差异是否真实存在。
