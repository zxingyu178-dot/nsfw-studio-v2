# 动漫链路 LoRA 组合预设：一个体位 + 厚涂画风

> **2026-11-26 实机检查**：本机 ComfyUI 当前只安装 `cunnyfunky_v5.0_000008`、
> `cunnyfunky_noobai_v3.3_000080`、`Hentai Pussy inspection_Pony_V1`、
> `Spread pussy_Illustrious_v1`。本文 Horn/Faux 两个预设文件在本机不存在，
> 直接照抄“提交载荷”会因 LoRA 名称不存在而失败。实机 v5 链路验证使用
> `cunnyfunky_v5.0_000008` @0.6/0.6，任务 `job_df27e301...` 已 COMPLETED。
> 如需恢复本预设，请先补齐两个 LoRA 文件，再按下方载荷提交。

> 适用模块：`anime_generate` / binding `v5`（LoRA 任务级参数化）
> 底模：`miaomiaoHarem_v14.safetensors`（Pony 谱系，832×1216，30 步 / cfg 4.0 / er_sde / simple，FaceDetailer 常开）
> 上限：每个任务最多 2 条 LoRA —— 本预设用满 2 个槽位：**体位 1 条 + 画风 1 条**

---

## 一、组合定义

| 槽位 | 文件 | 权重 | 作用 |
|---|---|---|---|
| 体位 | `HornGrabDoggyV2-000014.safetensors` | 0.8 | 后入 + 抓发/抓角，肢体张力强，服饰可完整保留 |
| 画风 | `Faux Oil Painting Style LoRA_Pony XL v6.safetensors` | 0.55 | 厚涂油画质感，笔触明显、色彩浓郁 |

**触发词必须写进正向提示词，否则 LoRA 不激活：**

- 体位：`HornGrabDoggyV2, horn grab`
- 画风：`painterly, faux traditional media, realistic`

> 画风这条的 `realistic` 会削弱动漫感，所以权重压在 0.55，并且正向必须保留 `source_anime`。
> 想要更浓的油画笔触可以升到 0.65；超过 0.7 脸容易糊，FaceDetailer 的 denoise 0.5 救不回来。

---

## 二、体位 × 画风的等价替换

同一套厚涂画风，换体位只换第一条 LoRA 和对应触发词：

| 场景 | 体位 LoRA | 权重 | 触发词 |
|---|---|---|---|
| 后入抓发（本预设默认） | `HornGrabDoggyV2-000014` | 0.8 | `HornGrabDoggyV2, horn grab` |
| 正面骑乘 | `Upright_front_pony-000010` | 0.8 | `upright straddle, girl on top` |
| 骑乘撑膝 | `cowgirl_arm_on_knee_pony-10` | 0.8 | `cowgirl_knee` |
| 传教士抓脚踝 | `Ankle_Grab_Missionary-000013` | 0.8 | `AnkleGrabmissionaryV1` |
| 抱起悬空 | `MIdAirCarryV2` | 0.8 | `midaircarryposition` |
| 两女一男多插 | `multiple_insertions_v0.2-pony` | 0.7 | `multiple penetrations` |

备选画风（二选一，别三条一起挂）：

- `Niji_semi-realismv3.safetensors` @0.7，触发词 `Semi-realism` —— 半写实，皮肤和光影更有质感，比厚涂更"干净"
- `Expressive_H-000001.safetensors` @0.7，触发词 `Expressiveh` —— 表情张力，可以替掉体位槽位做纯画风段

---

## 三、提示词模板

```
score_9, score_8_up, score_7_up, score_6_up, source_anime, rating_explicit,
mature female, 18 years old, 1girl, 1boy, [发色], [瞳色], slender, [表情],
HornGrabDoggyV2, horn grab, doggystyle, from behind, [服饰],
[场景], painterly, faux traditional media, realistic, cinematic lighting, detailed face
```

结构固定为：质量前缀 → 人数与人物 → **体位触发词 + 体位标签** → 服饰 → 场景 → **画风触发词** → 光影。

标准负面词（不要加 `nsfw` / `explicit` / `nude`）：

```
worst quality, low quality, score_1, score_2, score_3, blurry, jpeg artifacts,
bad anatomy, bad hands, missing fingers, extra digits, deformed, text, watermark,
cropped, out of frame, multiple girls, loli, child, young, flat chest
```

---

## 四、提交载荷

锁定 v5 必须带完整身份三件套（`module_version` + `provider` + `binding_version`），只传 `binding_version` 会被服务端忽略并按默认配置提交。

```json
{
  "source": "web",
  "client_request_id": "<每次唯一>",
  "queue_mode": "normal",
  "snapshot": {
    "prompt_mode": "full",
    "full_prompt": "<完整正向>",
    "negative_prompt": "<完整负面>",
    "count": 6,
    "width": 832,
    "height": 1216,
    "seed_mode": "random",
    "seed": null,
    "workflow_modules": [{
      "module_id": "anime_generate",
      "module_version": "v1",
      "provider": "comfyui",
      "binding_version": "v5",
      "workflow_hash": null,
      "binding_hash": null,
      "config": {
        "prompt": "<完整正向>",
        "negative_prompt": "<完整负面>",
        "loras": [
          { "name": "HornGrabDoggyV2-000014.safetensors", "strength_model": 0.8, "strength_clip": 0.8 },
          { "name": "Faux Oil Painting Style LoRA_Pony XL v6.safetensors", "strength_model": 0.55, "strength_clip": 0.55 }
        ]
      }
    }],
    "input_images": []
  }
}
```

---

## 五、性能预期（RTX 3060 Laptop 6GB / `--lowvram`）

| 阶段 | 单张耗时 |
|---|---|
| 换配置后的第一次（模型重挂 722 patches） | 200–275 s |
| 同配置连续出图 | 30–55 s |

**正确用法：一段一批锁死同一组合。** 在段与段之间换 LoRA 组合，每换一次多付 2–3 分钟重挂成本。

显存峰值未采样过 LoRA 组合路径，跑第一张时建议盯一次 `/system_stats`。

---

## 六、验收标准

1. 任务 `COMPLETED`，`count=6` 张齐全
2. ComfyUI `/history` 里该 prompt 的 `LoraLoader` 节点显示两条 LoRA 且权重正确
3. 画风对比无 LoRA 的 v3 版本：笔触明显更厚、边缘有油画感，而不是单纯"更糊"
4. 服饰完整保留，没有因为体位 LoRA 变成全裸
