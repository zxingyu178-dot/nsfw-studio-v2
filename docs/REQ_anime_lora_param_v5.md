# 需求单：anime_generate 支持按任务选择 LoRA（v5）

| 项 | 内容 |
|---|---|
| 提出人 | 用户（运营侧） |
| 提出日期 | 2026-11-14 |
| 优先级 | 高（当前 22 个 LoRA 只有 1 个可用） |
| 前置版本 | `anime_generate/v4`（已上线，LoRA 固定写死） |

---

## 1. 背景

v4 已把 LoraLoader 接进动漫链路，链路本身验证通过（`workflow_hash 991d438209a94dd1` / `binding_hash 01b15ff2ba776e5c`，实测热跑 53s、显存峰值 5254/6144MB）。

但 v4 存在两个结构性限制：

1. **LoRA 被写死在 binding 里**：`lora_name` 固定为 `Hentai Pussy inspection_Pony_V1.safetensors`，`strength_model` / `strength_clip` 固定 1.0，任务侧无法更改。
2. **LoRA 常开、无法关闭**：没法做「同一提示词、开/关 LoRA 各出一张」的对照，也没法在不合适的题材上摘掉解剖增强。

结果：本地已经下载了 **22 个 LoRA（3.80 GB）**，实际只有 1 个能用，其余 21 个闲置，包括：

- 尺度风格：`Expressive_H-000001`（52097 赞）、`ATRex_style-10`
- 角色合集：`genshin_v4`（124 个原神角色）
- 体位/POV：12 个（`Upright_front`、`cowgirl_arm_on_knee`、`Ankle_Grab_Missionary`、`HornGrabDoggyV2`、`MIdAirCarryV2`、`Rough_Sex_1.2PONY`、`BallsDeep-PN-V3.1`、`multiple_insertions`、4 个 POV 系列）
- 特写解剖：`Hentai_Pussy_inspection2_Pony_V1`

## 2. 要做的事

**把 LoRA 变成任务级参数，允许 0～2 个 LoRA 叠加，未指定时与不带 LoRA 的链路等价。**

### 2.1 对外契约（任务侧）

`snapshot.workflow_modules[].config` 新增三个字段：

```jsonc
{
  "module_id": "anime_generate",
  "config": {
    "prompt": "…",
    "negative_prompt": "…",
    "loras": [
      { "name": "Expressive_H-000001.safetensors", "strength_model": 0.7, "strength_clip": 0.7 },
      { "name": "Upright_front_pony-000010.safetensors", "strength_model": 0.9, "strength_clip": 0.9 }
    ]
  }
}
```

规则：

- `loras` 省略或为空数组 `[]` → **完全不加载任何 LoRA**，节点图必须等价于 v3（不能只是把权重设 0，0 权重仍会走 LoraLoader 的模型包装路径）。
- `loras` 最多 2 项；超过 → `422 LORA_LIMIT_EXCEEDED`。
- `name` 必须是 ComfyUI `GET /object_info/LoraLoader` 的 `lora_name` 枚举值之一，否则 `422 LORA_NOT_FOUND`（服务端用枚举校验，不直接信任路径）。
- `strength_model` / `strength_clip` 范围 `[-2, 2]`，越界 → `422`。建议默认 1.0。
- LoRA 顺序敏感：数组顺序即串联顺序，第二个 LoRA 的输入接第一个的输出。

### 2.2 后端实现要点

1. **节点图动态改写**（关键点）：ComfyUI 的 prompt graph 没有 bypass 语义，不能只调权重。adapter 在注入阶段按 `loras` 数量改写图：
   - 0 个：删掉 LoraLoader 相关节点，把下游所有 `["21", n]` 引用改回 `["1", n]`（ckpt 直连）。
   - 1 个：现有 v4 形态。
   - 2 个：串联 `21 → 22`，下游统一取 `["22", 0]`（model）与 `["22", 1]`（clip）。
2. **节点 id 固定**：LoraLoader 用 `21`、`22` 两个保留槽位，其余节点 id 与 v3 保持一致，便于 hash 对比。
3. **FaceDetailer 必须同源**：修脸阶段的 model/clip 也要取改写后最后一个 LoraLoader 的输出，不要退回 ckpt（否则修脸会掉风格）。
4. **占位符替换**：`workflow.json` 里两个 LoraLoader 的 `lora_name` 先用占位名（如 `__LORA_1__`），由 adapter 按任务参数覆写；不要让校验脚本要求占位名必须存在。
5. **binding 声明**：`binding.yaml` 增加

```yaml
capabilities:
  lora: true
  lora_max: 2
inputs:
  loras: {kind: list, apply: lora_stack}   # 由 adapter 解释，不映射到单个节点字段
```

### 2.3 校验与放行

- `scripts/validate_workflows.py` 校验清单加入 `("anime_generate", "v5")`。
- `release_manifest.yaml` 增加 v5 条目，G0–G4 按真实证据填，禁止预填。
- **不要修改 v4**：v4 已投入使用并有历史 Job 引用，按项目规范 binding 不可改。

## 3. 验收标准（必须逐条实测，不得只做静态检查）

1. `loras: []` 出图与 v3 的同一 seed 结果**像素级一致或高度一致**（证明真正走了无 LoRA 路径）。
2. `loras` 单付与 v4 现有行为一致（同 seed 对比或权重等价说明）。
3. 两段 LoRA 串联出图成功，且第二段风格确实生效（例如 ExpressiveH 0.7 + 体位 LoRA 0.9，姿势按体位 LoRA、画风带 ExpressiveH 特征）。
4. 非法输入全部被挡住并返回正确错误码：不存在的 lora_name、3 个以上、strength 越界。
5. 性能：832×1216 单张热跑 ≤ 120s；显存峰值 ≤ 6144MB 且无 OOM（贴 `/system_stats` 采样数据）。
6. 任务 `binding_version` 记录为 `v5`，`workflow_hash` / `binding_hash` 与 manifest 一致。

## 4. 明确不做

- 不自动下载/管理 LoRA 文件（下载由运营侧脚本负责）。
- 不做「按提示词自动选 LoRA」的智能推荐。
- 不支持 `Power Lora Loader`、`LoraLoaderModelOnly` 等其它节点形态（第一版只用标准 `LoraLoader`）。
- 不处理非 Pony/SDXL 底模的 LoRA（`Spread pussy_Illustrious_v1` 这类需要换底模，另开需求）。

## 5. 交付物

- `workflows/providers/comfyui/anime_generate/v5/{workflow.json, binding.yaml, README.md}`
- `release_manifest.yaml` v5 条目（含真实 G3/G4 证据与 job id）
- `scripts/validate_workflows.py` 登记 v5
- README 里必须写清：LoRA 列表如何映射到节点、0/1/2 个 LoRA 的三种图形态、已知限制

## 6. 测试触发词（验收用）

```
Expressiveh, 1girl, solo, asian, looking at viewer, bedroom
```
```
cowgirl_knee, 1boy, sex, vaginal, girl on top, straddling, spread legs
```
```
deep penetration, 1girl, 1boy, close-up
```

以上三个配 `score_9, score_8_up, score_7_up, source_anime, rating_explicit, mature female, 18 years old` 前缀即可直接跑。
