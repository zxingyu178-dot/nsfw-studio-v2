# Civitai 提示词采集通道 — 实测记录

> 对应需求单：`CIVITAI_PROMPT_COLLECTION_REQUIREMENTS.md`
> 实测时间：2026-11-12　脚本：`scripts/civitai_prompt_collect.py`

## 1. 结论：可用通道由两段组成

| 环节 | 接口 | 说明 |
| --- | --- | --- |
| 列表筛选 | `GET https://civitai.com/api/v1/images` | 服务端完成底模/分级过滤 + 游标分页 |
| 生成参数 | `GET https://civitai.com/images/{id}` 的 SSR `__NEXT_DATA__.trpcState` | 唯一能拿到 `prompt` 的入口 |

`/api/v1/images` 的 `meta` 字段**已经不再返回生成参数**：匿名与带 API Key 各测 100 条，全部为 `null`。提示词只存在于图片详情页的服务端渲染数据里。

## 2. 参数事实（都是实测，不是文档抄的）

### 2.1 底模过滤：参数名是复数 `baseModels`
- `?baseModel=Pony` → 无效，返回混合底模（需求单第 5.1 条失败的根因）
- `?baseModels=Pony` → 100% Pony
- 可重复传参：`?baseModels=Pony&baseModels=SDXL%201.0`

### 2.2 分级过滤：用 `browsingLevel` 位掩码
| 值 | 含义 | 实测返回 |
| --- | --- | --- |
| 1 | None（PG） | 全部 None |
| 2 | Soft | 全部 Soft |
| 4 | Mature | 全部 Mature |
| 8 | X | 全部 X |
| 12 | Mature + X | 4/8 混合 |

`nsfw=` 是旧参数，`nsfw=true` 只给 X；`nsfw=Mature,X` 直接 400。批量采集用 `browsingLevel=12`。

### 2.3 分页：游标
- 响应 `metadata.nextCursor`（形如 `feed:4682:45729167`），回传 `&cursor=...`
- 每页 `limit` 上限 200；连续翻页 0 重复

### 2.4 排序
`sort=Most Reactions | Newest | Oldest | Most Comments | Most Collected`，配合 `period=Day|Week|Month|Year|AllTime`。

## 3. 提示词缺失的三种原因（脚本已分桶）

详情页数据里有两个关键字段：`meta` 与 `hideMeta`。

| 状态 | 含义 | 实测占比 |
| --- | --- | --- |
| `ok` | 有 prompt | 约 78–80% |
| `meta_empty` | 图主未保存生成参数 | 约 19–22% |
| `meta_hidden` | 图主主动隐藏（`hideMeta=true`） | 少量 |

按 200 条详情实测：`ok=161`、`meta_empty=38`、`prompt_empty=1`。

> 是否需要 Token：**列表接口不需要**（匿名可拉），**详情页 SSR 也不需要**（匿名可拿到 prompt）。
> 但 Token 保留在配置里用于提高配额与后续可能的接口变化，不影响当前通道。匿名与登录态的差别仅在 `/api/v1/images` 的 `meta` 字段——两者都是 `null`。

## 4. 限流与稳定性

- `/api/v1/images`：连续 12 次请求无 429；建议 ≤2 req/s
- 详情页：3 并发 + 0.1–0.45s 抖动，200 页无 403；出现 429/5xx 自动退避重试 4 次
- Cloudflare：`/api/trpc/*` 直接 403（`Just a moment...`），**不要走 tRPC**；SSR HTML 不受影响
- PowerShell 5 的 `Invoke-RestMethod` 偶发 TLS 重置，脚本统一用 Python `requests`
- 失败状态：`blocked`(403) / `network_error` / `parse_error`，均计入报告，不污染正式清单

## 5. 凭据

只放本地 `.env`（`.gitignore` 已覆盖 `.env` / `.env.*`）：

```
CIVITAI_API_KEY=<在 Civitai → Settings → API Keys 生成>
CIVITAI_PROXY=http://127.0.0.1:33210
```

脚本不打印、不落盘 Token；`--env-file` 可指向其他位置。

## 6. 使用

```powershell
# 采 100 条 Mature+X、Pony/Illustrious/SDXL 1.0 的提示词
python scripts\civitai_prompt_collect.py --target 100 --workers 3

# 换排序/周期/底模
python scripts\civitai_prompt_collect.py --target 50 --sort Newest --period Week --base-models Pony
```

默认输出到 `runtime\civitai_prompts\`：

| 文件 | 用途 |
| --- | --- |
| `civitai_raw_<ts>.jsonl` | 全部有 prompt 的原始记录 |
| `civitai_clean_<ts>.csv` / `civitai_clean_latest.json` | 清洗后正式清单（字段齐全） |
| `pending_civitai.json` | 已对齐 `resubmit_v2.py` 的 `to_resubmit` 结构，可直接重提 |
| `civitai_empty_latest.json` | 空/隐藏提示词条目，单独标记 |
| `civitai_review_latest.json` | 命中模糊标签需人工复核的条目 |
| `civitai_report_latest.json` | 本次运行统计 |

## 7. 清洗规则

1. 正面词强制以本地 score 链开头（已带 `score_9` 的会先剥掉重复前缀）
2. 负面词 = 原负面 + 本地固定负面，按逗号去重（大小写不敏感）
3. 剥离 `<lora:...>` / `<lyco:...>`（本地无对应模型，直接提交会报错）
4. 提交尺寸固定 832×1216，原图尺寸保留在记录字段里
5. 安全过滤：`loli/child/toddler/infant/shota/teen/schoolgirl/young girl…` 命中即剔除；`young`、`petite` 等模糊词进复核桶，不混入正式清单

## 8. 未验证项

- 端到端出图提交：提交接口 `POST /api/v1/jobs` 对应后端当前未在 8000 端口提供服务（`/healthz` 200，但 `/api/v1/jobs` 超时），故只做载荷结构对齐，未实际投递
- `SDXL Lightning/Hyper/Chroma/Flux.1 D/OpenAI(Krea)` 等底模未纳入，如需支持在 `DEFAULT_BASE_MODELS` 追加即可

## 9. 扩量实测（2026-11-12 下午）

首跑仅 41 条的根因不是通道枯竭，而是 `--target 30` 早停：列表拉了 200 候选，详情抓到 60 条达标即停。提高 target 后产能如下（workers=3，代理 33210）：

| 批次 | 排序/周期 | 底模 | 详情 | 有词 | clean | review |
| --- | --- | --- | --- | --- | --- | --- |
| batch1 | Most Reactions / Month | Pony+Illustrious+SDXL1.0 | 200 | 161 | 142 | 8 |
| batch2 | Newest / Week | 同上 | 200 | 180 | 71 | 27 |
| batch3 | Oldest / AllTime | Pony | 160 | 138 | 119 | 1 |

合并去重脚本：`scripts/merge_civitai_batches.py`（按图片 ID + 提示词归一化去重）。累计 **332 条**干净清单（Pony 124 / Illustrious 207 / SDXL 1.0 1），复核桶 39 条；产物在 `runtime/civitai_prompts/`，`pending_civitai.json` 已对齐提交结构，832×1216、9 张/段。

### 运行环境与踩坑
- **Python 解释器**：`requests` 只在 base 环境 `C:\Espressif\tools\python\python.exe`（2.34.2）可用；项目 `.venv` 未装 requests，直接跑会 `ModuleNotFoundError: requests`。
- **排序参数空格**：`--sort Most Collected` / `Most Reactions` 这类带空格的值经 PowerShell 传给 python.exe 会被拆成两个参数报 `unrecognized arguments`；命令行优先用无空格值 `Newest` / `Oldest`，或在脚本内以列表传参。
- **复核桶构成**：主要是 `petite`、`small breasts` 等体型词（非未成年），保守隔离不进正式清单；未成年硬拦截词命中直接 reject。
- 底模分布偏斜：热门月榜以 Illustrious 为主，Pony 需单独 `--base-models Pony` 采样补足。
