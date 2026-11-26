# 「可爱」怎么写而不显幼：数据与写法（2026-11-15）

样本：`studio.db` 中 `review_status = KEPT / REJECTED` 的 2071 张已审阅图（958 留 / 1113 淘），关联其任务的正向提示词，统计单个标签的留用率。样本量小的标签已标注。

## 一、实测留用率

| 标签 | 样本 | 留用率 | 读法 |
|---|---|---|---|
| `shy` | 43 | 72% | 最高。羞的反应比"可爱"形容词有效 |
| `twin tails` | 120 | 68% | 造型件稳定，且不牵涉年龄 |
| `school uniform` | 147 | 65% | 制服在你这套模型里命中率高 |
| `heavy blush` | 66 | 62% | 浓腮红比淡腮红留用高 |
| `ribbon` | 162 | 56% | 发饰类稳 |
| `soft smile` | 22 | 55% | 小样本，但比裸 `smile` 好 |
| `innocent` | 15 | 53% | 小样本，语义偏幼，慎用 |
| `blush` | 799 | 50% | 主力项，量最大 |
| `open mouth` / `embarrassed` | 108 / 33 | 48% | 中性偏好 |
| `grin` / `tongue out` | 33 / 51 | 42% / 41% | 俏皮向，可用但别当主表情 |
| `petite` | 63 | 37% | 偏幼词，掉分 |
| `small breasts` | 504 | 35% | 高频但留用一般 |
| `round face` | 30 | 33% | 圆脸易滑向幼态 |
| `smile` | 308 | 26% | 裸词效果差，不加限定会变营业笑 |
| `cute` | 11 | 18% | 直接写 cute 基本无效 |
| `young adult` | 46 | 13% | 年龄串里这条几乎不帮忙 |
| `big eyes` | 10 | 10% | 只放大眼睛 → 幼态或崩脸 |
| `freckles` / `mole under eye` | 9 / 9 | 0% | 你已明确否决的"脏点"路线 |

结论：起作用的不是"可爱"形容词，而是**羞的反应 + 造型件 + 腮红浓度 + 眼型设计**。

## 二、拆解：可爱由四层构成

1. **眼型设计**（不是尺寸）——`upturned eyes` / `droopy eyes` / `hooded eyes` + `detailed eyelashes` + `moist eyes`（湿润反光）+ `catchlight`。用眼型做出"软"，不用 `big eyes` 放大。
2. **表情反应**——`shy, looking up at viewer` / `soft smile, gently parted lips` / `biting lower lip` / `half-closed eyes` / `hands near mouth`。可爱是"被看见的反应"，不是五官尺寸。
3. **造型件**——`hair ribbon` / `half updo` / `twin tails` / `frilled collar` / `round-framed glasses` / `loose knit sweater` / `ankle socks`。
4. **体态与光**——`head tilt` / `shoulders relaxed` / `hugging pillow` / `one knee bent`；光走 `soft lighting, warm backlight, pastel tone, film grain, shallow depth of field`。

## 三、会往幼态滑的词（避开）

`petite`、`small body`、`flat chest`、`baby fat`、`chibi`、`big round eyes`、`childlike`、`little`、`young girl`、`innocent/naive`（语义偏幼）、大头身比（3-4 头身）、`oversized sweater covering hands`（手被遮住是最典型的幼态信号）、`pajamas` 单穿。

年龄串固定写 `adult woman, 22 years old, mature female`，不要用 `young adult`（实测 13%）。

## 四、可直接用的两段

**A. 甜系可爱（成年、日常）**
```
adult woman, 22 years old, 1girl, solo, soft facial features, upturned eyes, moist eyes, catchlight, detailed eyelashes, gently parted lips, soft smile, shy, heavy blush on cheeks, head tilt, hair ribbon, twin tails, loose knit sweater, shoulders relaxed, hands near chest, indoors, window light, soft lighting, warm backlight, pastel tone, film grain, shallow depth of field
```

**B. 色气可爱（反差向）**
```
adult woman, 22 years old, 1girl, solo, hooded eyes, half-closed eyes, moist eyes, biting lower lip, heavy blush, looking up at viewer, arched back, collarbone, loose blouse slipping off one shoulder, thigh-high socks, sitting on bed edge, one knee raised, dim light, rim light, bokeh, film grain
```

## 五、注意事项

- `smile` 单独用掉分（26%），必须配 `soft` / `slight` / `gentle` 这类限定。
- 腮红要走浓：`heavy blush` 62% vs `blush` 50%，`light blush` 更低。
- 可爱元素别超过 3 个（眼型 + 表情 + 一个造型件），堆多了会糊成"通用萌系脸"，也就是之前那批同质化脸的成因之一。
- 以上留用率是**你个人审阅口径**下的统计，样本量小于 30 的标签只作方向参考。
