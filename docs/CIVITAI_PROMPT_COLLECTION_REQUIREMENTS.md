# Civitai 提示词采集通道 — 打通需求单

> 交接对象：负责打通网络通道与采集脚本的 Agent
> 整理时间：2026-11-12
> 目标：从 Civitai 采集与本地底模兼容的动漫图提示词元数据，清洗后对接本地 NSFW Studio V2 批量生图流水线。

## 1. 背景与目标

本地已搭好 ComfyUI + NSFW Studio V2 批量生图流水线，底模为 **miaomiaoHarem_v14.safetensors**（Pony 谱系 SDXL 动漫模型）。现需要从 Civitai 按底模兼容度筛选图片，提取其生成提示词（正面/负面/采样参数），整理成可直接提交的提示词清单。

**只采集提示词等文本元数据，不下载、不保存露骨图片本体。**

## 2. 本地环境与既有规范

### 2.1 服务与路径
- 后端：`http://127.0.0.1:8000`（NSFW Studio V2，FastAPI/uvicorn）
- ComfyUI：`http://127.0.0.1:8188`
- 底模：`C:\ComfyUI_models\checkpoints\miaomiaoHarem_v14.safetensors`
- 项目根：`D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-app`
- 批量提交脚本目录：项目 `scripts\` 与当前 session workspace（见第 7 节）

### 2.2 本地提示词规范（采集后套用）
- 正面词必须以完整 score 链开头：
  `score_9, score_8_up, score_7_up, score_6_up, score_5_up, score_4_up, source_anime, rating_explicit, mature female, 18 years old`
- 固定负面词：
  `worst quality, low quality, score_1, score_2, score_3, blurry, jpeg artifacts, bad anatomy, bad hands, missing fingers, extra digits, deformed, text, watermark, loli, child, young`
- 出图尺寸：832×1216；Pony/Danbooru 标签风格；成年角色，必须排除萝莉/未成年标签。

## 3. 已探测到的网络现状（避免重复探测）

### 3.1 代理
- 系统代理已开启：`ProxyEnable=1`，`ProxyServer=http://127.0.0.1:33210`
- 代理进程：`uniproxy.exe`（Athena），PID 25172，路径 `C:\Program Files\Athena\resources\libs\win32-x64\uniproxy.exe`
- 监听端口：`33210`（HTTP 代理，可用）、`33233`（隧道请求失败，疑似非 HTTP）
- **环境变量 `HTTP_PROXY` / `HTTPS_PROXY` 均为空**；命令行与 Python 进程不会自动继承系统代理，必须显式配置代理。

### 3.2 直连不可用
- 直连 `civitai.com`：DNS 被污染（解析到 `128.242.240.221` / `2a03:2880:f130:83:face:b00c:0:25de` 等无关地址），TCP 443 不通。
- 走代理 `http://127.0.0.1:33210`：Google `generate_204` 返回 204（代理翻墙正常）；Civitai API 返回 **HTTP 200**。

### 3.3 命令行调用要点（已验证）
- PowerShell：`Invoke-RestMethod -Uri <url> -Proxy "http://127.0.0.1:33210" -Headers @{"User-Agent"="Mozilla/5.0"}`
- Python `requests`：需在 `proxies={"http": "http://127.0.0.1:33210", "https": "http://127.0.0.1:33210"}` 显式传入。
- 偶发 `SSL connection could not be established`，重试即可；首次探测时曾出现 400，补 UA 后正常。

## 4. 已验证的 API 事实

### 4.1 图片接口
- `GET https://civitai.com/api/v1/images?limit=<N>`（走代理）返回 200。
- 顶层字段：`id, url, hash, width, height, nsfwLevel, type, nsfw, browsingLevel, createdAt, postId, thumbnail, stats, meta, username, baseModel, modelVersionIds`。

### 4.2 baseModel 取值（近期 100 张采样）
`Flux.1 D`、`Illustrious`、`Pony`、`SDXL 1.0`、`SDXL Lightning`、`SDXL Hyper`、`Chroma`、`OpenAI`、空值。

**与本地 Pony/SDXL 动漫底模兼容（保留）**：`Pony`、`Illustrious`、`SDXL 1.0`。
**不兼容（排除）**：`Flux.1 D`、`OpenAI`、`Chroma`、各类 Lightning/Hyper 加速底模（除非后续单独验证）。

### 4.3 meta 字段（预期）
`meta` 内预期含 `prompt, negativePrompt, steps, cfgScale, sampler, scheduler, seed` 等生成参数。**但匿名拉取的近期图中 `meta.prompt` 多为空**，需进一步排查原因（见第 5 节）。

## 5. 待打通/待确认的问题

1. **底模过滤未生效**：`?baseModel=Pony` 返回结果仍混合多种底模，参数名或用法可能不对。
   - 备选：先全量拉取，按顶层 `baseModel` 字段在本地过滤；或改走模型版本维度接口（`modelVersionIds` → 模型详情取 baseModel）。
2. **匿名提示词缺失**：近期图 `meta.prompt` 为空。需确认：
   - 是否需要 Civitai 账号 API Token（账号 Settings → API Keys）才能读取生成参数；
   - 是否与排序方式、图主是否保存参数、R18 可见性有关；
   - 带 token 后 `meta` 字段是否完整返回。
3. **NSFW 级别过滤**：确认 `nsfwLevel` / `browsingLevel` / `nsfw` 参数取值与过滤方式，按需求尺度筛选。
4. **分页**：确认 cursor/分页参数，支持批量翻页拉取。
5. **限流与重试**：记录接口限流阈值、429/超时重试策略、UA 与缓存处理。
6. **凭据安全**：API Token 只进本地配置/环境变量，不得写入代码、文档或提交到 Git。

## 6. 交付要求

### 6.1 采集脚本
- 走代理 `127.0.0.1:33210`，可配置代理地址；代理不可用时给出明确报错。
- 按兼容底模白名单过滤（Pony / Illustrious / SDXL 1.0）。
- 输出结构化清单（JSON 或 CSV），每条至少含：
  `source_url, baseModel, width, height, nsfwLevel, prompt, negativePrompt, steps, cfgScale, sampler, scheduler, seed, username, createdAt`。
- 去重（按图片 `hash` 或 `id`）；空提示词条目单独标记，不混入正式清单。

### 6.2 提示词清洗（对接本地流水线）
- 正面词前补本地 score 链前缀；负面词合并本地固定负面词。
- 校验并剔除含 `loli, child, young, toddler, infant` 等未成年标签的条目。
- 输出格式对齐现有批量提交 payload（参考第 7 节脚本），便于直接重提。

### 6.3 验收标准
- 脚本走代理稳定拉取，兼容底模过滤准确，清单字段完整。
- 抽样不少于 20 条带提示词的条目，可直接套本地规范提交出图。
- 文档记录：API 限流、分页方式、是否需要 token、匿名 vs 登录的数据完整度差异。

## 7. 可复用的现有产物与经验

- 批量提交脚本模板（payload 结构）：session workspace 下 `resubmit_v2.py`、`resubmit_zero.py`
  - 目录：`C:\Users\30566\AppData\Local\DoubaoWork\User Data\Profile 2\.doubaowork\agent_mode\workspace\.sessions\38452302412493826\agents\m_0cw3a9QehKa\`
- 后端任务提交接口：`POST /api/v1/jobs`，payload 顶层 `{"snapshot": {...}, "queue_mode": "normal", "source": "web"}`
- 经验库：`...\workspace\experience\` 下 `v2-api-job-submit-format.md`、`nsfw-batch-submit-pattern.md`、`nsfw-prompt-tag-cheatsheet.md`

## 8. 边界与合规

- 仅用于本地已搭建的成年角色动漫生图流水线；采集对象为公开可访问的元数据。
- 不下载/不导出露骨图片本体到交付物。
- 所有条目必须为成年角色，排除未成年相关标签与形象。
- 不泄露代理、账号、Token 等凭据。
