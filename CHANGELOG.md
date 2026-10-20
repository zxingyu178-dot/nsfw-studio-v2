# Changelog — NSFW Studio V2

格式参考 Keep a Changelog；版本遵循 SemVer。

## [0.20.3] — 2026-10-20

> Patch：DESIGN.md 落地 D —— 提示词 / 素材 / 设置页收口。DESIGN.md 四批（A–D）全部落地。

### Changed

- **提示词卡片改为「图片优先」**：预览图铺满卡片顶部（16:9、无内边距出血），文本/评分/
  生成图缩略行/操作区依次在下方；评分数字 20px 等宽字体；状态徽章按语义色（保留=绿、
  淘汰=红、候选=中性）统一为胶囊样式。
- **设置页**：分区标题改为 13px 大写 + 字距，数值/路径/版本/Migration 统一等宽字体，
  面板内边距与圆角收敛到 8px 体系。
- **素材卡片**：hover 右下角出现「打开」提示，与图库 hover 语言一致。
- 同步更新 `PromptTab` 注释与封面测试描述（DOM 顺序不变，视觉由 CSS `order` 置顶）。

### Notes

- 本地 vitest：Prompt / Settings / Assets / themes / noBom **14 文件 46 用例**全过（含封面 9 例）；
  `tsc -b`、`npm run build` 通过。
- DESIGN.md 四批落地完成；后续视觉调整以该文档为唯一事实源。

## [0.20.2] — 2026-10-20

> Patch：DESIGN.md 落地 C —— 图库改为瀑布流 + hover 操作层，图片按原始比例排布。

### Changed

- **图库瀑布流**：网格改为 CSS columns（230px 列宽 / 12px 间距 / 8px 圆角卡片），
  图片按原始宽高比自然排列，不再固定高度裁切拉伸；密度切换对应列宽 170 / 230 / 280px。
- **卡片左上比例标签**：等宽字体显示化简比例（如 `3:4`、`1:1`），非标准比例回退 `W×H`。
- **hover 底部操作层**：黑色渐变升起，展示 `尺寸 · 状态`（等宽字体）与「收藏 ★ / 下载 ↓」
  两个操作；选中态为 2px accent 描边 + 对勾（沿用多选逻辑）。
- 卡片改为容器 + 内嵌真实操作按钮（下载为 `<a download>` 原图），收藏切换调用
  `imageApi.favorite` 并即时更新列表项。
- 新增 `ratioLabel` 单测（3 例）。

### Notes

- 本地 vitest：Gallery 相关 10 文件 39 用例 + 比例单测全过；`tsc -b`、`npm run build` 通过；
  Generate 裸控件守卫仍绿。
- 下一步：D 提示词 / 素材 / 设置页收口。

## [0.20.1] — 2026-10-20

> Patch：DESIGN.md 落地 B —— 生成工作台改为扁平三栏（ComfyUI 式），去掉卡片套卡片。

### Changed

- 工作台默认宽度对齐规范：左生成控制台 **280px**、右参数/详情 **320px**（拖拽范围
  左 240–360、右 280–420，仍可收起为 44px 竖栏）。
- 三栏改为**扁平分区**：左栏 `surface` + 右分隔线、右栏 `surface` + 左分隔线、中间画布纯黑；
  去掉栏间距、圆角卡片与卡片阴影，任务坞改为贴底 + 上分隔线。
- 左栏头部控件紧凑化（`结构化 / 完整` 分段按钮 11px），`PROMPT` 标题在 280px 内不再折行/截断。
- Canvas 舞台去边框圆角，纯黑背景，图片成为唯一视觉中心。

### Notes

- 本地 vitest：Generate 相关 27 文件 109 用例全过；`tsc -b` 通过；`npm run build` 通过。
- 下一步：C 图库瀑布流 + 卡片 hover 操作层。

## [0.20.0] — 2026-10-20

> Minor：采纳用户提供的 `DESIGN.md`（深色 ComfyUI / Runway 气质）作为视觉权威，并完成
> 第一批 Foundation 对齐。只改视觉与排版，不改业务逻辑 / API。

### Added

- `docs/DESIGN.md` 入库（含项目落地说明：技术栈不变、字体回退、业务结构不因视觉删减）。

### Changed

- **全局 Token 对齐 DESIGN.md**：近黑页面 `#0a0a0b` / 纯黑画布 / 面板 `#141416` /
  卡片与输入 `#1a1a1d` / 描边 `#27272a` / 单一靛蓝 accent `#5b6cff`；
  圆角收敛为 6 / 8 / 10 / 12；页面级阴影清零（仅弹层保留深阴影）；
  正文 Inter（缺失回退 system-ui），数字 / seed / 尺寸 / 进度统一 JetBrains Mono（回退 ui-monospace）。
- **顶栏**：52px 高、单像素分隔、无阴影；链接 pill 式 hover/active。
- **控件**：主按钮改实心 accent、6px 圆角、无渐变无投影；输入 / 下拉 8px 圆角、聚焦 accent 描边；
  选择瓦片 8px 圆角、选中用 accent 浅底 + 描边。
- **页面**：生成页去掉装饰渐变与卡片重阴影，Canvas 改纯黑舞台；提示词 / 图库 / 素材 / 设置卡片
  统一 8px 圆角、1px 边框、零阴影、hover 不再抬升。
- 生成页左栏标题改为 `PROMPT`（不再在窄栏内折行）。

### Notes

- 后续分批：B 生成工作台三栏结构（280 / 320、可折叠右详情）；C 图库瀑布流 + 卡片 hover 操作层；
  D 提示词 / 素材 / 设置页收口。

## [0.19.3] — 2026-10-20

> Patch：视觉升级第三批（图库 / 素材 / 设置）。沿用前两批的 Token 与卡片语言，把剩余三个页面
> 拉到同一视觉水平；只改样式与布局，不改业务。

### Changed

- **图库**：筛选栏从「三个下拉各占一整行」改为紧凑单行工具条（下拉按内容收缩 132px 起，
  分段控件收进圆角容器），操作按钮右对齐；卡片改为表面色 + 细边框 + 圆角 + hover 抬升。
- **素材**：工具栏单行化（搜索框 flex 320–520px）；卡片 3:4 统一比例、圆角与 hover 抬升，
  标题层级 13/600。
- **设置**：宽屏改为两列卡片网格（≤1100px 回落单列），卡片统一表面色/边框/14px 圆角/18-20
  padding；面板标题 14/600 + 字距；`st-dl` 行距与 label/value 层级校准。

### Notes

- 截图验证：Chrome headless（1600×1000）逐页对比；同时修了预览服务器的 `/assets` 路由与
  静态目录同名冲突（仅本地验证工具，不进仓库）。
- 视觉三批结束；后续如需继续打磨，建议先给具体对标产品与偏好（密度/圆角/品牌色）。

## [0.19.2] — 2026-10-20

> Patch：视觉升级第二批（全局 Token + 顶部导航 + 生成工作台）。仍然只改样式与布局，不改业务。
> 目标延续用户要求「更美观、有设计、像大厂手笔」。

### Changed

- **全局 Token 校准**：更深的背景层级（#090b10 / #0e1117 / #12161f）、更克制的边框（#212836）、
  品牌色收敛为 #6f5bf6、圆角提升（8/10/14/18）、阴影更柔和；浅色主题同步校准。
- **顶部导航**：链接改为 pill 式 hover/active 状态，品牌字重与字距加强，导航高度 58px，
  去掉重阴影，改为单像素分隔线。
- **生成工作台**：三栏改为统一卡片（表面色 + 1px 边框 + 14px 圆角），栏间距 12px；
  Canvas 舞台加边框/圆角与内高光；画幅瓦片统一单元格高度与选中内描边；任务坞与工作台条
  对齐卡片风格；Prompt 槽位增加 hover / focus-within 高亮。
- **按钮质感**：主按钮改为纵向渐变 + 内高光 + 品牌色投影；secondary / ghost 的 hover 收敛为中性表面色。
- 提示词页工具栏单行化：搜索框不再独占整行（flex 1 1 360px，上限 560px）。

### Notes

- 截图验证：vite build → 本地 mock API → Chrome headless（1600×1000），逐页对比通过。
- 第三批继续：图库 / 素材 / 设置页 + 排版 Token 收口。

## [0.19.1] — 2026-10-20

> Patch：视觉升级第一批（提示词页）。用户要求「更美观、有设计、像大厂手笔」，本轮先做提示词页的
> 布局密度、卡片层级与操作区排版，并建立可复用的截图验证流程。不改业务逻辑 / API。

### Changed

- **/prompts 容器由 960px 放宽到 wide（1600px 上限）**，卡片网格改为 300px 起自适应（1600 宽下 4 列），
  消除右侧大片空白。
- **提示词卡片**：改为表面色 + 细边框 + 大圆角 + hover 轻抬升/阴影；标题 14/600，
  摘要 12/1.65，评分数字 18；状态徽章与评分说明对齐到两端。
- **卡片底部操作区**：改为「时间一行 + 操作一行」的垂直结构，修复时间在窄列里被挤成竖排折行的问题；
  操作按钮改为带 hover 背景的 chip，整行均分。

### Notes

- 新增本地视觉验证链路（不属于仓库交付物）：`vite build` → 静态 mock API 预览服务器 →
  Chrome headless 截图，用于逐页对比设计效果；后续批次覆盖生成页 / 图库 / 导航与全局排版。

## [0.19.0] — 2026-10-20

> Minor：提示词评分系统（手动）—— 7 维评分 + 保留/候选/淘汰，卡片直接展示状态与分数。
> 后端 API 在 PR #20 已合入 develop；本版补前端 UI；低分不自动淘汰（用户决定手动淘汰）。

### Added

- **Prompt 卡片状态与评分**：头部显示状态徽章（保留 / 候选 / 已淘汰）、摘要下方显示最近评分
  `x / 5` 与状态说明（status_reason）。
- **评分弹窗**（`PromptScoringDialog`）：总分 1–5 + 人物/服饰/场景/构图/光影/风格/画质
  7 维各 1–5 分（默认取最近一次评分，否则 3 分）+ 备注；状态按钮（保留/候选/已淘汰）与状态说明；
  保存时创建评估记录（`POST /prompts/{id}/evaluations`），状态变化再调
  `POST /prompts/{id}/status`。
- 列表请求自动携带 `include_evaluation=true`；前端 API 增加 `createEvaluation` /
  `listEvaluations` / `setStatus`；DTO 增加 `PromptStatus`、`PromptEvaluationDTO` 与 7 维常量。
- 回归测试：`PromptTab.scoring.test.tsx` 4 例（请求参数、徽章与评分、无评分入口、弹窗保存）。

### Notes

- AI 优化迭代（0.17.4）仍后置，等手动评分用一段时间后再决定模型通道。
- 视觉风格迭代（0.17.5）待用户给方向。

## [0.18.0] — 2026-10-20

> Minor：提示词库卡片 —— 每条提示词下面直接看到它生成过的图（Phase 0.17.2 前后端打通）。
> 只改前端展示与请求参数；后端聚合 API 在 v0.17.0 已上线；无数据库迁移。

### Added

- **Prompt 卡片生成图缩略行**：卡片内新增最多 3 张缩略图（默认 `images_limit=3`），
  超出部分显示 `+N`（总数来自 `images_total`）；点击缩略图打开该图 preview 大图。
- 列表请求自动携带 `include_images=true&images_limit=3`；DTO 增加 `PromptImageDTO`、
  `PromptDTO.images/images_total`；`PromptListParams` 增加两个可选参数。
- 回归测试：`PromptTab.gallery.test.tsx` 4 例（请求参数、缩略行与 +N、无图不渲染、点击看大图）。

### Notes

- 提示词评分系统（0.17.3）下一步；AI 优化（0.17.4）按用户决定后置（先手动评分）。
- 完整设计见 `docs/PHASE017_UI_REDESIGN_PLAN.md`。

## [0.17.0] — 2026-10-20

> Minor：Phase 0.17 第一批 —— 一屏工作台骨架 + 提示词→生成图聚合只读 API。
> 给「注意力被三栏切碎」「队列进度不直观」「提示词与产出图分离」三个用户反馈痛点提供直接解法。
> 不改 Job / 队列 / 图片业务语义；无数据库迁移。

### Added

- **左右栏可收起**：Prompt 栏 / 参数栏各有一个收起按钮，收起后保留 44px 竖栏（点击展开），
  状态持久化到 localStorage（`workbench.leftCollapsed` / `workbench.rightCollapsed`）；
  收起后 `--left-w/--right-w` 切到 44px，宽度让给 Canvas。
- **队列条常驻阶段与 Step**：TaskDock 收起态新增「阶段 x/y · 阶段名」与真实采样
  「Step x/y」；非采样阶段（如高清放大）不伪造 Step（沿用 v0.15.1 语义）。
- 回归测试：GeneratePage 收起/展开 3 例、TaskDock 阶段与 Step 2 例。
- **提示词 → 生成图聚合 API（只读，Phase 0.17.2 后端）**：
  - `GET /api/v1/prompts/{id}/images?limit&offset&version_id` → `items/total`，图片摘要复用
    `ImageResponse` 并补 `job_status/module_id/thumbnail_url/preview_url`；
  - `GET /api/v1/prompts` 新增 `include_images`（默认 false）与 `images_limit`（默认 3，1–10）：
    窗口函数一次聚合每个提示词的最近 N 张图 + 总数，提示词列表固定 4 次查询（无 N+1）；
    默认响应字段保持不变；
  - 新增 `tests/backend/test_prompt_images.py` 11 例（空/排序分页/版本过滤/批量聚合/无 N+1/404/422）。

### Notes

- 提示词聚合 API 由 Codex 子智能体（gpt-6-astra）实现，人工审查后合入；CI pytest 全绿。
- 参数分层沿用 v0.15 的「常用项常驻 + 高级参数折叠」；提示词库与评分系统分别在 0.17.2 / 0.17.3。
- 本版本是 Phase 0.17 的第一批；完整设计见 `docs/PHASE017_UI_REDESIGN_PLAN.md`。

## [0.16.1] — 2026-10-20

> Patch：修复画幅选择瓦片的尺寸预览（Phase 0.17.1 首个切片，用户反馈"选择尺寸的预览图都是一样的"）。
> 不改业务模型 / API / 队列语义。

### Fixed

- **画幅预览全部相同**：`ChoiceTile` 此前把 `"3:4"` 直接塞进 CSS `aspect-ratio`（冒号格式非法、被忽略），
  且 `.ui3-tile__shape-inner` 固定 `width/height:100%` + `max 28px`，导致所有画幅都渲染成 28×28。
  现改为按比例计算真实像素尺寸内联渲染：1:1=28×28、16:9=28×16、9:16=16×28、3:4=21×28 等，
  选择前即可看出构图差异；新增 `ChoiceTile` 回归测试（4 例）。

## [0.16.0] — 2026-10-20

> Minor：Anima 动漫生图模块上线。把 2026-10-10 完成并离线验收（Mock 5 例 + 真实探针出图）的
> `anime_generate` 从 v0.9.0 归档分支 `archive/anime-module-v0.9.1` 移植到 v0.15.1 基线。
> 不新增模型 / 节点 / AI 能力（模型为本机已就位的 Anima-2.9B）；无数据库迁移；
> 核心执行链（QueueWorker / PipelineExecutor / 单队列）零改动。

### Added

- **`anime_generate` 模块（第五个正式 WorkflowModule）**：动漫 / 插画文生图，模型为
  **Anima-2.9B（preview-v1 int8）** + Qwen3-0.6B 文本编码器 + Qwen Image VAE
  （本机已就位，零下载接入；合计 4.22 GB，加载与显存压力低于 Qwen-Image 2.1 写实链）；
- provider binding `workflows/providers/comfyui/anime_generate/v1/`
  （按 ComfyUI 官方蓝图 `Text to Image (Anima)`：UNETLoader + CLIPTextEncode×2 +
  KSampler 30 步 / cfg 4 / er_sde / simple + VAEDecode；workflow_hash / binding_hash 双指纹固化）；
- 与 `basic_generate` 标准契约完全一致（复用同一实现，仅覆写能力身份）——
  前端模块选择器（/modules 驱动）自动出现"动漫生图（Anima）"选项；
- 离线 Mock 回归 5 例（`tests/backend/test_anime_generate_module.py`）；
- 《AI 生图指南》（`docs/AI_IMAGE_GENERATION_GUIDE.md`）与 Agent 调用示例
  （`scripts/agent_generate.py`）随模块一并纳入版本库。

### Notes

- 官方说明：Anima 擅长动漫 / 艺术风格，**写实主体表现差**（写实请继续用 `basic_generate`）；
- `models/diffusion_models/anima-turbo-v1.0.safetensors`（15 字节）是失败下载占位
  （内容 "Entry not found"），不可用；如需要 turbo 变体请重新下载后新建 v2 binding；
- 真机 Gate（ComfyUI 8188）本轮未执行：引擎当前离线，需恢复后补跑动漫链真实出图并归档证据。

## [0.15.1] — 2026-10-15

> Patch / Workbench Live Hardening：修复 v0.15 代码审计发现的 1 个 P0（CI 工具链）、
> 8 个 P1（Canvas 几何、多阶段进度、采样 Step 语义、SSE 去重、resume 链、review 串行、
> 任务坞忙碌态、预览失败占位、队列语义）与 4 个 P2（采样 stall、增量刷新、legacy 清理、
> active slot 守卫）。
> 不改业务模型 / 单队列语义，不新增模型 / 节点 / AI 能力；无数据库迁移。

### Fixed

- **P0 CI 工具链**：CI 固定 Node 22.22.2（`.nvmrc` / `.node-version` / `engines.node`），
  修复 main 前端 CI 因 Node 版本漂移导致的失败。
- **Canvas 逻辑尺寸（#17）**：CanvasViewport 不再用 preview naturalWidth 覆盖几何，
  改用逻辑尺寸 `FALLBACK_IMAGE{1024,1024}`，Fit/100% 不再随 rendition 错误伸缩，100% 反映真实像素。
- **多阶段 liveProgress（#18）**：进度按 `stage_item_id` 分键存储与清理，终态只清自己的
  StageItem，不再误伤相邻阶段；LiveProgress 携带 `stageItemId`。
- **sampler-only Step（#19）**：后端仅在当前节点命中采样器白名单
  （KSampler/KSamplerAdvanced/SamplerCustom/SamplerCustomAdvanced）时输出 step/max_step，
  model load / VAE / upscale / save 阶段不再伪造 Step。
- **SSE 去重（#20）**：广播签名变化才发、否则 2s heartbeat；DB 持久化签名 330ms 节流、
  stage 切换立即写；生命周期事件 payload 补 `stage_item_id`。
- **完整 resume family（#21）**：Canvas 用 jobApi 沿 `resume_of_job_id` 取 root→current
  完整链（visited set + max-depth 16），合并整条链图片，A→B→C 多层 resume 图片全可见。
- **review mutation 串行化（#22）**：图片收藏/保留/弃用 per-image 串行队列，成功用响应 DTO
  校正、失败重取权威并显式报错（不静默），动作进行中禁用按钮。
- **TaskDock busyJobId（#23）**：暂停/继续/取消只在忙碌任务上禁用并显示“正在…”与 aria-busy，
  忙碌别的任务不误伤当前任务按钮。
- **Prompt 预览失败占位（#24）**：PromptCard 预览失败统一“暂未生成”占位（不裂图），
  Editor 小封面改用 1536 preview 并在失败时回退“无封面”。
- **QUEUED/RUNNING 分离（#25）**：进度 HUD 仅 RUNNING 渲染；QUEUED 显示排队横幅
  （前方 N 个任务 + 查看当前运行任务），空结果占位区分运行/排队/完成三态。
- **采样 stall 看门狗（#26）**：仅采样阶段 step 冻结超过阈值才判 ENGINE_STALLED；
  非采样阶段不套短 stall，交执行总超时 ENGINE_TIMEOUT，避免模型加载/VAE 被误判卡死。
- **Canvas 增量刷新（#26）**：按图片 id 去重，图片集合不变则跳过 setImages，
  避免每完成一张全量重排抖动。
- **active slot 守卫（#26）**：localStorage 记忆值必须命中合法 slot，非法值回退第一个
  有内容 slot，再否则 style，杜绝 8 个槽位全不 active。

### Changed

- **SSE 心跳节流**：`QueueWorker` 新增 `progress_broadcast_heartbeat_ms=2000`，
  瞬态广播与持久化写库分别签名节流，降低空转期 SSE 与数据库压力。

### Removed

- 删除 0.14 的 `ResultPane`（含 lightbox 测试）与 `components/GenerationControls`
  （含 count 测试），二者已被 Workbench 4.0 的 CanvasStage / InspectorPanel 取代；
  旧测试迁移到生产路径，并新增 `legacy.guard` 防止生产代码再次引用旧模块。

## [0.15.0] — 2026-10-14

> Minor：Workbench Layout 4.0（Canvas First）、真实进度（Job / Stage / Step）、可视化 Prompt 库、
> Glass 设计体系与性能守卫。前端重构 Generate 工作台为三栏 + 底部任务坞；后端把进度事件分流为
> 瞬态 SSE 与持久 job_events，并透传 ComfyUI 真实 step/max_step。
> 不改业务模型 / 单队列语义，不新增模型 / 节点 / AI 能力；无数据库迁移。

### Added

- **Workbench Layout 4.0（Canvas First）**：Generate 重排为左 Prompt Console、中深色哑光 Canvas、
  右参数 Inspector 三栏 + 底部 TaskDock。左右栏可拖拽（`ResizablePane`，pointer capture +
  方向键 8/24px + Home/双击复位），宽度经 `--left-w/--right-w` 持久化；三档断点（≥1200 可调、
  1024–1199 固定 280/270 隐藏手柄、<1024 Workspace Tabs），整页零纵向滚动。
- **WorkbenchBar 玻璃顶栏**：模式切换、来源上下文（配方/Prompt/当前工作台）、重置、保存为
  Prompt/配方（下拉菜单，带名称与收藏）。
- **Prompt Console 单槽位聚焦**：8 个结构化槽位折叠为 label + chip + 单行摘要，仅激活槽位展开
  编辑；素材槽位带 chip 与 AssetPicker；active slot 记忆；Negative/Preview 默认收起。
- **参数 Inspector + 拆分生成**：右栏只负责“怎么生成”（工作流、高清放大 `Switch` 并标注
  “原图全部完成后处理”、数量、Seed、高级参数）；`SplitGenerateAction` 拆主生成与
  “优先生成（插入当前任务之后）”，Gate 与旧 GenerateAction 一致。
- **TaskDock 底部任务坞**：当前 Job / Queue 从右栏迁出；收起态显示状态点、第 N/M、总进度、
  队列数，展开态两列（CompactCurrentJob + QueuePanel）；tooltip 明确“只暂停任务调度，
  不停止 Python/ComfyUI 引擎”。
- **CanvasStage / ProgressHUD 真实进度**：中栏自包含拉取家族图片、filmstrip、ActionDock、Lightbox；
  顶部 HUD 显示跨 stage 加权总进度、Elapsed、第 N/M 张、阶段 x/y、真实 Step x/y（仅采样型），
  无 step 的阶段显示“处理中…”，**高清放大不伪造 Step**。
- **CanvasViewport 产品化**：ResizeObserver fit-to-container、滚轮以光标为锚点缩放、pointer 拖拽、
  缩放边界钳制、preview/content/thumbnail 三级 rendition、自然尺寸 onLoad 校正。
- **可视化 Prompt 库卡片**：名称/摘要 → 预览图（文本下方）→ 时间 → 使用/复制/编辑/收藏；
  预览用 thumbnail（lazy），点击放大；无图为固定 16:9 低对比“暂未生成”占位（不裂图），
  已归档仍显示；不自动覆盖封面。
- **Glass 设计体系**：Dark/Light 双主题 glass token（bg/strong/border/highlight/shadow/blur/
  saturate）+ `.glass/.glass--strong`，`@supports not` 回退较不透明 surface；性能守卫保证玻璃层
  ≤8、Canvas 绝不 blur、slot/input 不撒 blur。
- **CI**：PR 闸门加入前端 `test:ci`（Vitest）。

### Changed

- **后端进度事件分流**：`JobService.publish_transient_event` 只发 SSE 不写 `job_events`；
  queue worker 每轮发瞬态 `ITEM_PROGRESS`，仅签名变化 / 节流 / 切 stage 才落库，进度 tick 不再刷库。
- **真实 Step 合同**：`EngineJobStatus` 增加 `step/max_step`；ComfyUI 适配器把 progress value 映射为
  step/max_step，`execution_start/success/error` 清空 step；保留归一化 progress。
- **前端 liveProgress 瞬态层**：`jobStore.liveProgressByItem` 仅存内存，`handleJobEvent` 消费
  ITEM_PROGRESS，终态清理，不触发整页每 tick 全量刷新。

### Removed

- 移除旧 `proto/` 原型、已迁移的 SettingsPane 队列/紧凑测试，以及无 DOM 匹配的
  `.generate__columns` / `.generate__modebar` / 1319px 旧布局死 CSS。

## [0.14.1] — 2026-10-14

> Fix / Hardening（patch）：一键停止失败状态真实化、运行时路径去硬编码、画幅外部同步、
> 结果图 rendition 分层、GenerateAction CSS 去重、控件语义化，并补齐 3 份能力审计 +
> Canvas 拖拽/缩放原型。
> 不改业务模型 / Job / Queue / Image，不新增模型 / 节点 / AI 能力；无数据库迁移（沿用 0018）。

### Fixed

- **一键停止退出码真实化**（`scripts/stop_studio.ps1`）：修复"失败也可能 exit 0"。
  最终退出码 0=全部成功停止；10=Studio Backend 失败；11=ComfyUI 失败；12=Mobile Review(8767) 失败；
  13=停止后端口仍占用；14=ControlHub 调用失败（resolver 解析失败同归此类）；
  15=外部非 owned ComfyUI 未停（EXTERNAL_NOT_OWNED，partial success，非 0、绝不强杀）。
  决策优先级 14>15>13>12>10>11>0；逐目标打印 STOPPED/EXTERNAL/FAILED 与端口 FREE/OCCUPIED；
  仅全部符合预期才输出"后台资源已释放"，失败绝不返回 0；`.bat` 透传退出码。
  决策逻辑抽到 `scripts/runtime/stop_decision.ps1` 的纯函数 `Get-StudioStopExitCode`（可 dot-source 单测）。
- **运行时路径去硬编码**：新增 `scripts/runtime/resolve_aihome.ps1`，统一解析
  AIHOME_ROOT / CONTROLHUB_ROOT / CONTROLHUB_PYTHON / CONTROLHUB_DATA_ROOT；优先级
  环境变量注入 > 相对脚本/项目根推导 > AIHOME.json/Registry 权威路径 > local config 兜底；
  解析失败显式报错、绝不静默用空路径（stop 归 14、launch 非 0）。`launch_studio.ps1`/
  `stop_studio.ps1` 统一 dot-source，正文不再写死任何机器完整路径。
- **AspectRatioPicker 外部状态同步**：新增纯函数 `deriveTier(width,height)`；以 `useEffect`
  跟随外部 width/height，仅在派生值与当前 state 不一致时才 set（杜绝循环 set）；custom 输入
  聚焦/本地编辑期间加焦点脏标记保护、失焦后再对齐。修复 Recipe / History / Image→Workbench /
  hydrate 后画幅与分辨率 UI 高亮和真实提交宽高不一致。
- **ResultPane 结果图分层**：Canvas 主预览改用 preview rendition（1536）、filmstrip 改用
  thumbnail（512，`loading="lazy"`），原图仅用于 Lightbox / 查看 100%；preview/thumb 加载失败
  时 onError 清晰回退原图，避免无谓加载整张大图。
- **GenerateAction CSS 去重**：合并 `generate.css` 中重复的 `.generate-action` 主声明与
  :hover/:active/:disabled 等规则为唯一权威样式，responsive override 只保留在 `@media` 内；
  新增静态 guard（核心 selector 主声明出现 ≥2 次即测试失败）。
- **控件语义化（修正错误静态规则）**：静态规则改为"业务页禁止无 DS wrapper 的裸 `<button>`/
  `<select>`、要求 DS 大写组件，`components/ui`、`components/ui/ui3` 等 primitive 目录内部允许
  原生控件"；新增 ui3 `DisclosureButton`（原生 `<button aria-expanded aria-controls>`）；
  `CollapsibleSection` 改为语义 disclosure、`GalleryCard` 错误重试块与 `AssetPickerDrawer`
  素材项由 `div role=button` 改回 `<button>`、`GeneratePage` 自造 tab 收口到现有
  `components/ui/Tabs`（标准 WAI-ARIA tablist/tab/tabpanel，primitive 本身未改动）。

### Added

- **Lightbox 嵌套滚动锁自动化测试**：覆盖 Case C——Lightbox 内再开 Confirm Modal，关闭内层
  后外层锁仍在（ref-count 不提前释放），关闭外层才恢复底层 scrollTop。
- **审计与原型（不落地为正式 UI）**：
  - `docs/GENERATE_INFORMATION_DUPLICATION_AUDIT.md`（§9 信息重复 inventory）；
  - `docs/PROMPT_PREVIEW_CONTRACT_AUDIT.md`（§10 Prompt 预览图合同核实）；
  - `docs/GENERATION_PROGRESS_CAPABILITY_AUDIT.md`（§11 真实生成进度能力盘点）；
  - `frontend/src/pages/Generate/proto/CanvasViewport.tsx`（§12 独立 pan/zoom 技术原型，
    未接入任何生产页面）。

### Tests

- 后端：在 v0.14.0（452 collected = 449 passed / 3 skipped）基础上新增 runtime 停止退出码 /
  resolver 路径合同测试 14 个，全量 **466 collected = 463 passed / 3 skipped / 0 失败**；
  PowerShell 退出码 harness（`scripts/runtime/Test-StudioStopExitCodes.ps1`，mock CLI/端口）
  在 Windows 门禁执行；延续 hermetic 护栏，测试禁连真实 8188 / 8000 / 8767。
- 前端：新增画幅外部同步、ResultPane rendition 分层与回退、CSS 重复 selector guard、
  语义控件 / 嵌套 overlay 锁、CanvasViewport 原型等测试，全量串行 **58 文件 / 284 用例全绿**；
  test:store 11 passed；typecheck 0 错误；build 140 modules。

### Notes

- 审计结论（基于真实代码，逐行可追溯）：
  - **Prompt 预览图合同已满足**：API 稳定返回 `preview_image_id`；`image_reference_service`
    已统计 `prompt_preview_ids` 引用，物理删除在存在引用时跳过（封面图不会被误删）；归档可读、
    复用 rendition；当前仓库无 duplicate/copy Prompt 功能。**本轮未改后端、未加 migration。**
  - **生成进度当前只有 0~1 比例**：ComfyUI `progress` 事件的 `value/max` 在引擎适配器即被
    折算为 0~0.99，整数 step 未保留；可绑定 engine_job_id(prompt_id)；SSE 传输层可携带 step
    但当前未填；upscale 绑定无 KSampler、不发 progress 事件。**无真实 step 不做 UI 假造**，
    StageProgress 正式契约留待下一阶段。
  - Generate 业务页无原生 `<select>`（唯一实现位于 primitive 层 `components/ui/Select.tsx`），
    本轮不做全站迁移。
- 不做：Workbench Layout 4.0、Prompt 最终 UI、Canvas 最终交互、完整 StepProgress、MediaReview、
  新模型 / Anime / FaceID / IPAdapter / ControlNet；不升级 torch。

## [0.14.0] — 2026-10-13

> Runtime 收口 + Lightbox 滚动隔离 + Generate UI 3.0（minor）。
> 不新增模型 / 节点 / AI 能力；无数据库迁移（沿用 0018）。
> 生产生命周期统一交由 ControlHub 官方 lifecycle CLI（nsfw-studio-v2=8000、comfyui=8188 均为已批准对象）；8767 为随 Studio 退出的子运行时。

### Added

- **Runtime 收口（ControlHub 单一生命周期 owner）**
  - 新增 `backend/app/services/controlhub_lifecycle.py`：封装官方 lifecycle CLI
    （`python -m control_hub.lifecycle_cli <verb> <id> --data-root <root>`，`--data-root`
    为子解析器参数，置于 verb+id 之后），退出码 / JSON state 映射为引擎状态语义。
  - `EngineRuntimeService` 新增 `ControlHubEngineRuntime` 适配器与 `create_engine_runtime()`
    工厂（按 `engine_runtime.mode` 选择 controlhub / direct，默认 controlhub）；**引擎目标恒为
    `comfyui`(8188)，构造时若误传 `nsfw-studio-v2` 直接 RuntimeError**，绝不去 start Studio 本体。
    v0.13.2 的直接 Popen 实现整体保留为 direct 适配器。
  - 新增 `POST /api/v1/system/request-shutdown`：loopback 校验后立即 202，由一次性
    detached helper（`scripts/runtime/shutdown_helper.ps1`，延迟约 500ms）转调一键停止脚本；
    幂等（`app.state.shutdown_pending`），后端自身绝不杀自己。
  - 新增 `scripts/stop_studio.ps1` / `stop_studio.bat`：best-effort 暂停队列 → 停 8767 →
    经官方 CLI 停 nsfw-studio-v2(8000) → 经官方 CLI 停 owned comfyui(8188) → 核验三端口
    释放与 owned Python 退出；分步日志，FREE / EXTERNAL_NOT_OWNED / STOP_TIMEOUT 不静默；
    严禁全局 taskkill / 杀所有 python。
  - 生产 launcher 收口为 CLI shim（`scripts/launch_studio.ps1`，固定 127.0.0.1:8000，
    不再自己 Popen uvicorn、不再出现 Vite Preview / 4173 生产链）；旧 `start_studio.bat`
    改为纯转发 shim；可自定义端口的旧开发启动器迁移到 `scripts/dev/launch_studio_dev.ps1`。
- **应用内统一 Power Control**：TopNav 电源区新增 `PowerMenu`，分「生图引擎」（复用
  EngineRuntimeBody，保留 v0.13.2 七态中文文案；RUNNING_EXTERNAL 不提供停止/重启）与
  「Studio 后台」（停止全部后台带二次确认）两段；队列暂停属调度、留在 Generate，Power/Queue
  语义分离。
- **Lightbox 滚动隔离**：`useOverlayScrollLock` 锁 html/body/.app-shell__main，ref-count
  支持嵌套 overlay，关闭恢复 overflow/scrollTop；`.lb-stage` 改 native non-passive wheel
  （preventDefault + stopPropagation），滚轮以鼠标位置为锚点缩放、双击 Fit↔100%、ESC 关闭、
  拖动边界限制；overlay/stage `overscroll-behavior=none`、side-wrap=contain；底部浮动 Icon Dock。
- **Generate UI 3.0（仅视觉与组件结构，不改业务数据模型与任何 API）**
  - 三栏重做：Prompt Console（结构化 8 字段 / 完整 Prompt / Negative / 预览折叠）、
    Canvas Stage（中性画布 + 悬浮 ActionDock + 底部缩略条）、Parameter Console。
  - 新增专属 `GenerateAction` 主按钮（46px、克制 gradient/glow、细线 loading、disabled 可见
    Gate 原因；count=1「生成」、count>1「生成 N 张」）。
  - UI3 共享设计层 `components/ui/ui3/`：IconButton / ToolbarIcon / ActionButton / ActionDock /
    PopoverSelect（ARIA combobox/listbox、↑↓/Enter/Esc/typeahead）/ ChoiceTile / ChoiceGrid /
    NumberStepper / PowerButton / StatusPill / Tooltip + 统一 SVG icon（无 emoji/系统字符）。
  - 画幅形状 Tile、分辨率分段、数量 NumberStepper+快捷 chips、Seed 一行；Queue 紧凑化。
  - tokens.css 扩展 Light/Dark 双主题 token；Generate 主链静态扫描禁裸 `<button>`/`<select>`
    （primitive 内部例外）；不引入 Ant / MUI / Element / Bootstrap。

### Fixed

- **Lightbox 视口高度收敛**：`.lb-body/.lb-stage` 被图片自然尺寸撑到超出视口（cross 轴 flex
  stretch 未约束内部高度），导致 Lightbox 高度溢出；修复 `.lb-overlay{overflow:hidden}`、
  `.lb-body{height:100%;min-height:0}`、`.lb-stage{min-height:0}`、`.lb-side-wrap{height:100%}`。

### Tests

- 后端：在 v0.13.2（418 passed / 3 skipped）基础上新增 Runtime 收口测试（运行权合同、
  controlhub 目标恒为 comfyui、停止脚本合同 / 不得杀无关 python、固定生产端口、launcher 为
  shim、request-shutdown），全量 452 collected（449 passed / 3 skipped）；延续 hermetic 护栏，
  测试全程禁止连接真实 8188/8000/8767。
- 前端：UI3 基础层 + Lightbox 隔离（滚动锁 / native wheel / overscroll / 嵌套锁 / 视口高度收敛）
  + Generate UI 3.0 契约（无裸控件 / GenerateAction / 一屏布局）+ PowerMenu，全量 55 文件 /
  252 用例；typecheck 0 错误、build 139 modules。

### Notes

- ControlHub 接入：`nsfw-studio-v2`(8000) 已通过官方提交 + 桌面两次人工审批，registry 为
  approved（capabilities open/start/stop/restart）；`comfyui`(8188) 此前已在册 approved；
  详见 `controlhub/handoffs/nsfw-studio-v2-2026-10-13.md`。
- 真机验收：runtime 7 Case 全 PASS（一键启动→引擎 start comfyui 不 start Studio→8767→
  一键停止三端口 FREE + 内存释放；无关 python / hermes / weixin 进程存活；生成中停止可恢复、
  已完成图保留、重启不重放陈旧任务）；Gallery / Generate Lightbox 滚动隔离 Chrome / Edge 均 PASS；
  6 分辨率一屏不滚 + Light/Dark 截图矩阵通过。
- 不做：Runtime Lease R5、torch cu128→cu130 升级（待用户拍板）、Anime/FaceID/IPAdapter/
  ControlNet/新模型/新节点、手机生图、AI 自动 Prompt、公网/云。
- 8767 Mobile Review 为随 Studio 退出的子运行时，非 ControlHub 对象。

## [0.13.2] — 2026-10-12

> 真机“一键启动生图引擎”闭环补丁，并修复一次线上队列事故暴露的根因（patch）。
> 不新增模型 / 节点 / AI 能力；无数据库迁移（沿用 0018）。

### Fixed

- **引擎一键启动健壮化**：进程归属改为跟随真正 LISTEN 8188 的进程，可跨 uv
  创建的 venv“6MB 启动桩 → 基础解释器”重定向（无论监听者在受管进程树第几层、
  是否为 uv 基础解释器），修复冷启后被误判 `RUNNING_EXTERNAL`(owned=false)；就绪
  以 HTTP `/system_stats` 200 为充分条件，容忍启动期监听 pid 变化与短暂连接拒绝，
  冷启窗口内状态为 `STARTING`（“引擎启动中（冷启约数分钟，可后台等待）”），不再
  过早弹“启动失败”；探活恢复后状态自动回在线；停止时终止实际监听进程整棵树
  （含 uv 子孙）并复核端口释放；外部已健康的 ComfyUI 识别为 `RUNNING_EXTERNAL`，
  绝不重复拉起、也不可由 Studio 停止。默认健康等待 240s → 300s（可配
  `engine_runtime.health_timeout_seconds`）。
- **启动不再自动重放陈旧任务（事故根因）**：跨进程重启遗留的
  QUEUED/RUNNING/PAUSED 任务在启动时一律标记为 INTERRUPTED，不再自动重新提交
  引擎，需用户在界面显式续跑 / 重试；新增“清理陈旧任务”入口
  （`POST /api/v1/queue/clear-stale`，仅置状态、不删图）。
- **卡死收敛**：item 在引擎 running 但 progress 持续为 0 超过可配
  `engine_runtime.stall_timeout_seconds`（默认 600s）判 `ENGINE_STALLED` 失败，
  best-effort `/interrupt` 释放 worker 并推进队列头，禁止无限轮询 `/history`
  阻塞后续；prompt 从队列与历史同时消失同样判失败。
- **端口占用显式化**：启动器 `launch_studio` 预检 8000，被非本应用程序占用时
  打印占用 PID / 程序 / 命令行并非零退出，不再静默端口错乱；本应用已在运行时
  仅打开浏览器。
- **前端**：引擎弹泡 STARTING / 托管 / 外部 / 端口冲突中文态收敛（外部实例禁用
  停止 / 重启）；队列面板新增“清理陈旧任务”按钮（二次确认、明确不删图）；
  `ENGINE_STALLED` 给出可读中文文案。
- **测试 hermetic 护栏**：后端测试全程禁止连接真实 8188/8000/8767（httpx send
  拦截 + 真机集成测试强制 skip），杜绝测试向真机引擎提交 prompt。

### Notes

- 真机确认所谓“re-exec 到 uv python”实为 uv 0.12 创建的 Windows venv“启动桩 →
  基础解释器”正常重定向（`pyvenv.cfg` 的 home 指向 uv cpython），并非
  comfy-aimdo / comfy-kitchen 等原生节点 re-exec；故保持默认 venv 解释器，归属 /
  健康逻辑改为跨“桩 → base”跟随真实监听者。
- ComfyUI 0.37 在当前 torch cu128 下仅 eager、优化 CUDA 后端关闭（日志提示需
  cu130+）。是否升级 torch cu130 属较大环境变更，本补丁不执行，另行评估交用户决定。

## [0.13.1] — 2026-10-12

> 真机日用反馈补丁（patch）。不新增模型 / 节点 / AI 能力；无数据库迁移（沿用 0018）。

### Fixed

- **生成数量支持任意张数**：Generate 右栏“输出-数量”从写死下拉档
  [1,2,4,6,8] 改为可自由输入的整数控件，允许 **1–64 的任意整数**（与后端
  `WorkbenchSnapshotModel.count` 的 `ge=1, le=64` 口径一致），保留 1/2/4/6/8
  常用档快捷 chips；输入非数字或越界时在失焦 / 回车时钳制到 1–64 并给出
  “1–64 张”内联提示。新增 4 个前端测试。

### Notes

- 经真机复测（物理 2048×1152、Windows 125% 显示缩放，有效 CSS≈1638×922；
  并覆盖 100/125/150% DPR、800–1920 非最大化宽度、600–1080 高度），v0.13 的
  一屏布局在所有档位 `scrollHeight==clientHeight`、无横向溢出、[生成] 钮常驻
  视口——“仍要滑动 / 界面问题 / 未接入原图库”确认为**桌面入口仍指向旧
  v0.11.0 实例与临时空库**的部署问题，非代码缺陷；本次通过建立稳定桌面实例
  并固定快捷方式解决。

## [0.13.0] — 2026-10-12

> Phase 0.13 — Generate 一屏工作台收口 + 局域网 Mobile Review Bridge。
> 不新增模型 / 节点 / AI 能力；无数据库迁移（沿用 0017，启动自动应用 0018 仅
> 元数据补全）。

### Added

- **Generate 真正一屏工作台**：根节点锁定高度（`100dvh` / 内部各自滚动），
  任何宽度下整页不再出现外层文档滚动；紧凑三栏在 ≥1024 完整保留（左栏素材
  Chip + 中栏舞台 + 右栏四组折叠），<1024 自动降级为 Workspace Tabs 模式，
  极低高度（≤600px）下进一步压缩顶栏与 modebar；[生成] 按钮在所有断点都常驻
  sticky action footer 内，永不被裁切到视口外。
- **Mobile Review Bridge（独立 8767 端口）**：新增审核专用 FastAPI 服务，与主
  站 8010 完全解耦；局域网手机（MediaReview Android 客户端）扫码 / 配对码配对
  后获得短期 Token，针对 Desktop 冻结出的 review session 做只读图审。配对采用
  6 位数字配对码 + 倒计时窗口，配对成功后撤销 / 设备管理在 Settings“手机审核”
  区集中操作。
- **冻结式 Review Session**：Desktop ReviewMode 迁移到 `/review/*` 会话语义——
  一次会话绑定 `job_id` + 图片快照（可选），服务端下发全局统计 / 剩余待审 /
  已审计数，决策走 `POST /review/{session_id}/decision`（A 保留 / D 淘汰 / F 收藏），
  会话并发冲突返回 409，Ctrl+Z 撤销、结束态汇总与跨端一致；手机端与桌面端共享
  同一套 review service，不再各自维护本地队列。
- **Settings“手机审核”区**：Bridge 运行状态 / 端口（默认 8767）/ 局域网访问
  提示 / 已配对设备列表 / 生成配对码（含倒计时）/ 撤销配对 / 启停开关。
- **MediaReview 对接文档五份**（`docs/integration/`）：
  - `MEDIAREVIEW_COMPATIBILITY_AUDIT.md` — ba19d01 客户端与本桥的兼容性审计；
  - `MEDIAREVIEW_NSFW_CONTRACT_V1.md` — 桥对外 REST 契约 v1；
  - `MEDIAREVIEW_STATE_MAPPING.md` — NSFW 审核语义 ↔ MediaReview 状态映射；
  - `MEDIAREVIEW_ANDROID_IMPLEMENTATION_GUIDE.md` — Android 端接入指南；
  - `MEDIAREVIEW_TEST_MATRIX.md` — 端到端测试矩阵；
  另附 `openapi-mobile-review.json` 作为机器可读契约。

### Changed

- **Gallery 联合刷新（T18）**：focus / visible 事件触发静默重拉首页 + stats，
  避免从 ReviewMode / Lightbox 返回后看到旧计数。
- **安全硬化**：移动端 8767 与桌面 8010 的 `/docs` `/redoc` `/openapi.json`
  统一 404（不在局域网暴露文档面）；未知路由错误信封强制 `error.code=NOT_FOUND`，
  便于前端桥接层做稳定分支。

## [0.12.0] — 2026-10-12

> Phase 0.12 — Product UX & Existing Capability Closure：产品体验收口、UI 体系修复、
> 现有能力补齐。**不新增模型 / 节点 / AI 能力**。无数据库迁移（沿用 0017）。

### Added

- **全局统计接口** `GET /api/v1/images/stats`：与图库同口径过滤（job_id / status /
  favorite / search / 日期等），服务端单行聚合返回 `{total,new,keep,reject,archived,
  favorites}`，修正此前“分母为服务端总数、分子为本地已加载列表”的假全局统计。
- **系统状态接口** `GET /api/v1/system/status`：只读返回 app_version / data_root /
  database_path / database_size / disk_total / disk_free / image_count /
  thumbnail_count / preview_count / latest_migration / engine_runtime，不泄露敏感配置。
- **模块执行超时策略**：`ModuleCapabilities.recommended_timeout_seconds`（不对前端
  暴露），QueueWorker 按“Stage 显式 override > 模块推荐 > 全局 1800s”三级解析，
  reference_generate 推荐 7200s；移除按 module_id 的硬编码 if。
- **工作台 Recipe 来源（Provenance）**：WorkbenchSnapshot 增加可选
  source_recipe_id / source_recipe_version_id，从 Recipe 打开工作台时记录、Job
  冻结 snapshot 保留、图片 provenance 可读；语义为“最初从哪个 Recipe 打开（生成前
  可能已修改）”，非 Recipe 来源为空、不产生假信息。
- **Reference 能力驱动的输入角色**：前端按模块 input_slots 的 requiredInputSlot
  决定输入图 role（source / reference / face_reference），切换主模块时自动重映射、
  不接受当前输入时明确提示而非静默丢图；输入标题与描述随能力动态显示。
- **UI 偏好持久化（localStorage）**：图库密度、适应/填充、Lightbox 信息栏可见性、
  Generate 分组折叠态；不写入数据库、不保存生产数据。

### Changed

- **Design Token 闭合**：tokens.css 增加统一 alias（--text / --text-secondary /
  --text-tertiary / --success / --success-soft / --danger-soft / --on-accent /
  --radius-xs / --weight-* / --font-mono / --leading-relaxed / --favorite 等），
  收藏色停止写死 `#f5a623`；新增 design-token 守卫测试，未定义全局 token 即失败。
- **App Shell / Sticky / 响应式**：新增 `--topnav-height:56px`，TopNav 层级高于
  页内 sticky，Generate modebar 下移且不再遮盖一级导航；工作台锁定 100dvh、三栏
  各自内部滚动、整页不随右栏变长；响应式 ≥1320 三栏、1180–1319 压缩三栏（中心
  预览保留最小宽）、<1180 堆叠。
- **Generate UI 2.0**：右栏收敛为工作流 / 画面 / 输出 / 任务与队列四组可折叠，
  [生成][优先生成] 用 sticky action footer 随处可见；左栏紧凑素材 Chip、输入图用
  缩略图、Negative 与最终 Preview 视觉区分；中栏舞台增大、生成中简洁状态、完成后
  可收藏/保留/淘汰/去图库、HD/processed 统一 Badge；队列紧凑固定高度内滚。
- **Gallery UI 2.0**：Toolbar 改两层（浏览模式 / 筛选操作），清理废片收进“更多/
  维护”；默认“适应”模式完整展示横 / 方 / 竖图（object-fit:contain，不再 3:4 强裁），
  提供 适应|填充 切换；网格密度 小/中/大（130/180/250）；多选使用 sticky 选择条
  复用批量审核接口。
- **Review Mode 2.0**：顶部使用服务端全局统计、显示“剩余待审 N”，新增 Ctrl+Z
  撤销上一条（自维护 undo stack），结束态汇总 保留/淘汰/收藏 并可继续下一批；
  保留 A / D / F / ←→ / Space 快捷键与跨分页预取。
- **Lightbox / Detail**：右栏分组（生成信息 / 审核 / 复用 / 危险操作），信息栏可
  折叠（折叠后图占满宽）；Recipe 行仅在存在来源 Recipe 时显示，否则移除；删除
  沿用“普通图=淘汰、REJECT=永久删”语义。
- **Settings 升级为系统与维护中心**：外观 / 生图引擎（复用 Engine Runtime API）/
  图片缓存（计数 + 补齐缩略图/预览图 + 进度 + 停止）/ 存储（DataRoot、库大小、
  剩余空间与阈值）/ 关于（版本、当前 migration）。
- **取消隐形上限**：Prompt / Recipe 由 50 改为 offset 分页 + 加载更多；Assets 移除
  前端 limit 100，改为分页 + 搜索 stale guard，AssetPickerDrawer 同步；History 移除
  limit 100 假全集、按 root family 稳定分页；ResultPane 移除硬编码 limit 200、
  分页拉全 Job family 图片。
- **组件拆分（只重构不改行为）**：GalleryPage 拆为 Toolbar / Grid / Card /
  GroupView / SelectionBar / DetailDrawer / CleanupDialog + hooks；SettingsPane 拆为
  GenerationControls / CurrentJobCard / QueuePanel / ModuleParameterField；AssetsPage
  拆为 Grid / Card / DetailDrawer / Editor。

## [0.11.0] — 2026-10-12

### Added（Phase 0.11：图片资产管理系统）

- **图库分页与无限滚动**：`GET /api/v1/images` 标准分页（`page` / `page_size=40` /
  `sort=created_desc|created_asc|favorite|size` / `status`），返回
  `{items,total,page,page_size,has_next}`；前端 IntersectionObserver 哨兵无限滚动，
  图片进入 viewport+300px 才懒加载，含占位与错误态；历史图片可完整翻到最早。
- **Image Variant 与 Thumbnail 系统（迁移 0015）**：新增 `image_variants` 表
  （同一逻辑 Image 的 thumbnail / preview rendition，不污染 Image 表）；新增
  `images/thumbnails` 目录，规格 512px / WebP / q80；图库只载 thumbnail，
  Lightbox 才载 original；历史缺失缩略图按需/回填生成、不阻塞浏览。
- **图片审核状态（迁移 0016）**：Image 增加 `status / reviewed_at / review_note`；
  Gallery 提供「全部 / 待审核 / 收藏 / 归档」筛选。
- **Review Mode**：摄影选片式全屏大图，←/→ 切换、A 保留、D 淘汰、F 收藏、
  Space 放大；顶部进度与 待审/保留/收藏/淘汰 统计；工具栏与任务分组均有「开始审核」。
- **Job 审核入口**：生成完成后「开始审核」，显示本次 总数/未审核/保留/淘汰 统计。
- **废片清理**：两阶段 NEW→REJECT→「清理废片」批量确认；预览数量/占用/预计释放；
  删除 original+thumbnail+DB；删除前经 ImageReferenceService 检查，被
  Prompt/Asset/Recipe 引用的图片禁止删除。
- **图片→素材 / Prompt 联动 / 详情增强**：图片详情「创建素材」（复用 Asset API、
  记录 source_image_id）、「设为 Prompt 封面」；在现有 Lightbox 上扩展右侧信息栏
  （尺寸/时间/Seed/Prompt/来源 Job/Recipe）与 复制 Prompt / 打开 Workbench /
  创建素材 / 删除 操作。

### Changed（Phase 0.11.1：加固与发布收口）

- **统一审核状态语义（迁移 0017）**：收敛为审核状态 `NEW/KEEP/REJECT/ARCHIVED`
  + 独立 `favorite:bool`（允许 KEEP+favorite、ARCHIVED+favorite、NEW+favorite）；
  `status=FAVORITE` 归一为 KEEP 且 favorite=1，应用层停止写 FAVORITE（传 FAVORITE
  到 status 接口返回 400 `IMAGE_STATUS_DEPRECATED`）；旧 `/review`、`/favorite`
  与新 `/status` 走同一领域写入口，消除双系统分裂；Job summary / ReviewMode /
  Badge / Detail 状态一致。
- **单图删除语义**：普通图按钮为「淘汰此图」（置 REJECT、保留文件）；仅 REJECT
  显示「永久删除此废片」，核对 `deleted_count===1` 才从 UI 移除，杜绝假成功。
- **物理删除事务安全（trash staging）**：文件先 `os.replace` 原子移入
  `images/temp/delete_staging/<cleanup_id>/<image_id>/`，再开 DB 事务清指针→删
  variants→删 Image→commit；commit 成功才清 staging，失败 rollback 并把文件原子
  移回；启动时清理/报告 stale staging；不再用吞 OSError 的 safe_delete 做关键删除。
- **全历史导航闭环**：Lightbox / Review / Job Review / ImagePicker 支持分页跨页与
  接近末尾预取（移除 Job page_size=100、Picker limit=120 上限）；Job 分组改后端
  聚合 `GET /images/job-groups`，避免 N+1；ImagePicker 改标准分页 + thumbnail。
- **Thumbnail 生产链**：新图入库后 best-effort 主动生成；历史图经
  `POST /images/thumbnails/backfill`（单 worker、可停、进度查询）低并发回填；
  `get_or_create` 加 per-image 锁、临时文件 + 原子替换、唯一冲突后 re-read；
  新增 preview rendition（长边 1536 / WebP q85），ReviewMode/Lightbox 默认 preview、
  放大才载 original，实现快速切图。
- **分页竞态与清理 UI**：loadNext 增加 request sequence 守卫、append 前按 id 去重、
  排序补稳定 tie-breaker；清理预览展示 candidate/deletable/protected/占用，确认按钮
  按实际可删数计数、protected 可查看原因。
- **连接池**：SQLite 引擎连接池扩至 pool_size=10 / max_overflow=20，避免突发
  rendition 请求排队超时被误报为 500。
- **版本收口**：`configs/app.yaml` 与 `frontend/package.json` 及关于页统一为 0.11.0。

## [0.9.0] — 2026-10-09

### Added（Phase 7：可靠性收口 + Reference 能力 Gate）

- **Stage-aware Resume（Task0）**：`resume_remaining()` 不再把整条 Pipeline 从 Stage 0 重跑——
  对每个剩余槽位逐 Stage 检查父 Job 同槽位 StageItem，已 COMPLETED 且产出非空的上游 Stage
  直接复用（output/seed/engine 溯源继承，物化为 COMPLETED StageItem +
  新增 `job_stage_items.reused_from_stage_item_id` 溯源字段），从第一个未完成 Stage 才开始执行；
  **只有真正重新执行的 Stage 才重新分配 Seed**；覆盖 basic→upscale / img2img→upscale /
  Stage2 失败 / Stage2 取消四种场景（离线 Mock 回归 4 例）；
- **通用图片输入 Slot 契约（Task5）**：`ModuleCapabilities.input_slots`
  （role=source/reference/face_reference + required + max_count）；Workbench 快照
  `input_images` 支持多角色（上限 4）；Job 创建期由 PipelineValidator 按模块声明校验
  （未声明角色 → `UNUSED_INPUT_IMAGE`、必填缺失 → `INPUT_IMAGE_REQUIRED`、
  超量 → `INPUT_SLOT_LIMIT_EXCEEDED`）；img2img/upscale 继续兼容 source；
  Recipe 输入图快照保留多角色；
- **Reference Module（Task6，Gate 通过后）**：新增 `reference_generate` v1
  （Qwen-Image 2.1 原生 reference latents 参考图条件生成；slot=reference 单张；
  kind=original、parent=参考图；configurable `resolution` 512–2048）；
  provider binding `workflows/providers/comfyui/reference_generate/v1/`
  （`TextEncodeQwenImage21` 参考图链 + 参考尺寸 latent；双指纹固化）；
- **Reference 能力重盘（Task3）**：`docs/REFERENCE_CAPABILITY_INVENTORY.md`
  （零下载只读重盘：可加载模型清单 / 缺失方向逐项结论 / Gate 实测）；
- **幂等请求指纹（Task7）**：`jobs.client_request_fingerprint`——
  相同 (source, client_request_id) + 相同 payload 返回原 Job；
  相同 key + 不同 payload → `IDEMPOTENCY_KEY_CONFLICT`（409），不再静默返回旧 Job；
  队列模式变更不视为冲突（兼容历史 Job 的 NULL 指纹）；
- **Capability 扩展（Task2/Task8）**：`allowed_job_kinds` / `can_start_from_image` /
  `is_generative` / `input_slots` 四个能力字段（`/modules` 同步返回）；
  `size_mode` 之外的前向兼容语义全部由 ModuleCapabilities 驱动。

### Changed

- **处理型 Job 校验能力驱动（Task2）**：移除 PipelineValidator 的
  "process 必须且只能是 upscale" 硬编码——改为模块声明 `allowed_job_kinds`（含 process）
  且首个模块 `can_start_from_image=true`；未来 Face Repair / 背景移除等处理模块
  只需声明能力，不再修改 Validator；
- **`/modules` capabilities 按实际选中的 module_version 获取（Task8）**：
  不再固定读取注册表默认版本；
- **Image → Workbench 生成上下文语义化（Task8）**：判定依据从 `seed != null` 改为
  产出 Stage 的模块语义（`is_generative`），未来非 ComfyUI 引擎 / 未记录 Seed 的生成路径
  仍可恢复工作台；
- **图片来源标注（Task8）**：`Image.source` 增加 `engine`——
  非 comfyui/mock 的未来引擎产出绝不错标成 `import`（import 只表示外部导入）。

### 仓库与工具（Task1）

- 大型验收 input/output/screenshots 移出 Git 跟踪（完整图片只进 Handoff ZIP）；
  `.gitignore` 增加 `docs/evidence/**/*.{png,jpg,jpeg,webp,gif}` 与 `temp/`；
- 长期脚本迁移：`temp/` → `scripts/acceptance/`（check_ci / send_handoff_mail /
  inspect_jobs / inspect_recipes）与 `tests/manual/`（smoke_phase51 / smoke_phase6_photo /
  acceptance_phase6(_browser) / probe_engine_upscale）；
- 每阶段交付邮件改为参数化工具 `scripts/acceptance/send_handoff_mail.py`
  （--phase/--source/--handoff/--subject(-file)/--body-file + IMAP SHA-256 复核）。

## [0.8.0] — 2026-10-09

### Fixed（Phase 6：Pipeline 可靠性收口）

- **Image → Workbench 生成上下文（Task1）**：从当前图沿父链找"距离最近、由 generate Job 产出、
  且使用 Seed"的图及其 Job（import→img2img→upscale 恢复 Img2Img，不再回到导入图）；
  `seed` 返回该生成上下文图片的真实 Seed（不再无条件树根 Seed）；
- **前端工作流身份保留（Task2）**：`normalizeModules()` 不再重建裸 `{module_id:'upscale'}`——
  从 History / Recipe / Image 恢复的 7 字段身份（含双 hash）与 config 在目录到达 / 模式切换后
  仍原样保留；只有用户手动开启高清才创建裸模块；
- **Recipe 固定 Seed（Task3）**：Recipe 不保存固定 Seed——"使用此图 Seed"的工作台保存配方时
  归一化为 `seed_mode=random / seed=null`（不再 400，也不强制改工作台状态）；
- **Pipeline 顺序与重复模块（Task4）**：移除硬编码 `MODULE_ORDER` 执行重排（严格保持
  用户/Recipe/Workbench 提供的顺序）；同一 module_id 重复出现 → `PIPELINE_DUPLICATE_MODULE`；
- **Module Availability 收紧（Task5）**：`module_version` 与 `binding_version` 不再互相 fallback；
  新 Job 将使用的 module 版本必须真实注册（否则 `available=false / module_version_not_registered`）；
  `/modules` 返回 `registered / available / module_version / provider / binding_version / unavailable_reason`；
  未注册 module_version 在 Job 创建期即拒绝（fail fast）；
- **Img2ImgModule.execute 契约（Task6）**：直接执行路径补齐 positive/negative Prompt
  （不再提交空 Prompt）；
- **generation_mode 显式化（Task7）**：WorkbenchSnapshot / Recipe / Job / History / Image restore
  全程保存与恢复 `text | image`（旧快照无该字段时按 input_images 推断，向后兼容）；
- **Module 参数元数据驱动（Task8）**：`ParameterSpec` 增加 `title / min / max / step / configurable`；
  前端按 schema 渲染 float/int/bool/enum 控件 + Primary Module 轻量选择器（denoise 滑杆
  不再按 module_id 硬编码）；
- **有效尺寸语义（Task9）**：`ModuleCapabilities.size_mode`（basic_generate=explicit、
  img2img/upscale=input）；图片生成模式 UI 不显示假宽高；History 任务详情显示
  "跟随输入图 W×H"（实际 Stage 输入尺寸）而不是 Workbench 遗留的 1024×1024。

### Changed

- **Img2Img 默认 denoise 0.55 → 0.8**（Task10 真实照片实测：0.55 即使给出不同场景 Prompt
  也"几乎没变化"（精修档）；0.8 在真实人像上人物保留良好且场景级 Prompt 明显生效。
  见 `docs/PHASE6_REPORT.md` §2）。滑杆仍为 0.05–1.0；binding.yaml / workflow.json
  指纹文件未改（历史 Job 的 hash 校验不受影响）；
- 素材 → 工作台快照显式标记 `generation_mode=text`；工作台"用作输入图 / 以此图进行图生图"
  显式进入图片模式。

### Tests

- 新增 `tests/backend/test_phase6_pipeline_reliability.py`（19 用例：Task1/3/4/5/6/7/8/9 回归，
  含 import→img2img→upscale 上下文、pinned 身份、重复/未注册模块、参数 schema、
  generation_mode 往返、execute 契约）；
- 新增 `tests/frontend/workbench_store.phase6.mjs`（11 断言，Playwright 之外零新依赖：
  用 vite SSR 加载真实 store；`npm run test:store` 已接入 CI）；
- 保持：全量快速套件 227 passed（208 基线 + 19 新增）。

### Chore

- 交接包：Qwen 实验证据迁至 `docs/evidence/phase51-img2img/`；新增
  `docs/evidence/phase6-img2img/`（真实照片验收输入/输出/报告/浏览器截图）；
  Source 包由 git tracked 维护（缓存文件确认未跟踪）；
- 版本 0.7.0 → 0.8.0（后端 / 前端 / configs 同步）。

## [0.7.0] — 2026-10-08

### Added（Phase 5.1：Image Pipeline Contract Closure + Qwen Img2Img）

- **WorkflowModuleRef 正式类型化（Task1）**：核心工作流契约从 `list[dict]` 升级为正式模型
  `WorkflowModuleRefModel`（module_id / module_version / provider / binding_version /
  workflow_hash / binding_hash / config），前后端（`frontend/src/types/workbench.ts`）双侧镜像；
  Job 响应 `workflow_snapshot` 同步使用正式类型。
- **Recipe 完整 Workflow 身份（Task2，P0 修复）**：`RecipeService._validate_workflow_snapshot`
  不再丢弃 provider / binding_version / 双 hash——历史 Job → 工作台 → 保存 Recipe → 重新打开，
  身份 100% 一致；**旧配方不会偷偷升级到新版 Workflow**；普通新建工作台保存配方时
  尽可能固化当前真实身份（与 Job 创建同一解析器；模块暂不可用时不阻塞保存）。
- **模块 config 单链（Task3）**：`Workbench.workflow_modules[].config` → `Recipe.workflow_snapshot`
  → `Job.workflow_snapshot` → `JobStage.config_json` 唯一事实源；`PipelineExecutor` 把
  `JobStage.config_json` 注入 `JobRequestContext.module_config`；Resume 完整保留 config；
  `stage_configs` 参数仅保留为内部/测试直调路径。
- **PipelineValidator（Task4/Task5，P0 修复）**：Job 创建前依据 ModuleCapabilities 统一校验
  Pipeline——`input_required=false` 携带输入图 → `UNUSED_INPUT_IMAGE`（输入图片不得被静默忽略）；
  需要输入图却没给 → `INPUT_IMAGE_REQUIRED`；Stage N 必须能接收 Stage N-1 输出（链式检查）；
  处理型 Job 仅 upscale；未知模块创建期拒绝；模块 `validate_config` 钩子（默认无约束）。
  判断不在 QueueWorker；`resume_remaining` 同样复核并重新冻结生成型输入图。
- **Img2ImgModule + img2img/v1 binding（Gate C 成功）**：第三套 WorkflowModule
  （uses_seed=true / input_kind=image / input_required=true / output_kind=processed /
  parent_policy=input_image），参数仅 `denoise`（0.05–1.0）；provider binding
  `workflows/providers/comfyui/img2img/v1/`（LoadImage → VAEEncode → KSampler denoise →
  VAEDecode → SaveImage，复用现有 Qwen-Image 2.1 三件套）。输出 = `kind=processed` +
  `parent_image_id=输入图` + StageItem 真实 Seed；**QueueWorker / PipelineScheduler /
  ImageService 核心零改动**。
- **工作台模式 ↔ Primary Module 绑定（Task6）**：文生图自动确保 `basic_generate`；
  图片生成自动切换到**可用**的图片条件模块（img2img）；禁止"图片生成 + basic_generate +
  输入图"自相矛盾状态；历史矛盾数据（Phase 5 旧配方）在模块可用时自动校正；
  图片生成 UI 新增"变化强度"滑杆（0.05–1.0）。
- **`/modules` 真实可用性（Task7）**：响应新增 `registered / available / provider /
  binding_version / unavailable_reason`；comfyui 下必须能加载 provider binding 才
  `available=true`（`binding_not_configured` / `binding_invalid`）；前端 Gate 只依据
  `available=true`（不因"代码里注册了模块"就显示可用）。
- **Face Asset 参考图清除（Task8）**：`POST /assets/{id}/versions` 新增
  `reference_action: inherit | set | clear`（缺省兼容旧语义）；UI [更换] / [移除]；
  clear = 新版本 reference=none，旧版本保留原参考图。
- **导入去重 DB 兜底（Task9）**：迁移 `0011_image_import_dedup_unique`——
  `images(sha256)` 部分唯一索引（source='import'）；并发 IntegrityError → 重新查询并返回
  已存在图片（duplicate），不是 500；迁移前防御性去重历史重复行（保留最早，不删数据）。
- **图库"以此图进行图生图"**：图片详情新增入口 → 打开图片生成工作台
  （mode=image、input_image=当前图、Primary Module=可用图生图模块）；
  有生成上下文恢复原 Prompt，外部导入 Prompt 为空（不伪造）。

### 实验（零下载 Qwen Img2Img，Gate C 成功）

- `docs/evidence/phase51-img2img/`：实验 Workflow（**不进入正式 providers 目录**）+
  spike 脚本 + 输入/输出/元数据。**未下载模型、未安装节点、未升级 ComfyUI、
  未修改用户工作流**。
- 实测（ComfyUI 0.37.0 / RTX 3060 Laptop 6GB / 768×768 / steps 25 / seed 20261008）：
  denoise 0.55 → 输出结构 ≈ 输入（像素 MAE 2.25/255，粗结构相关 0.9993）；
  denoise 1.0（同 seed/同 Prompt 对照）→ 完全由 Prompt 驱动的新图（结构相关 0.16）；
  无缺节点 / 无缺模型 / 无 OOM；输出尺寸正确、Seed 与 denoise 确实进入 KSampler。
  **结论：输入图对输出有决定性影响，未退化为文生图。**
- 详见 `docs/PHASE51_REPORT.md`。

### Changed

- **架构验收**：新增第三种 Module 仅需 `Img2ImgModule` + `img2img/v1` binding + 参数/UI——
  QueueWorker / PipelineScheduler / ImageService / Job 状态机零改动（与 Phase 5 §二十五 结论一致）。
- 迁移 `0011_image_import_dedup_unique`；版本 0.6.0 → 0.7.0（后端 / 前端 / configs/app.yaml 同步）。
- 文档：新增 PHASE51_REPORT；同步 README / AGENTS / CHANGELOG / TASKS / DEV_LOG /
  TEST_REPORT / WORKBENCH_STATE / MODULE_IO_CONTRACT / IMAGE_MODEL / API_PLAN /
  DATABASE_PLAN / DATA_MODEL_V1 / IMAGE_CONDITIONING_INVENTORY。

### Tests

- 新增 `tests/backend/test_phase51_contract.py`（15 用例：身份/配置单链/输入校验/
  /modules 可用性/参考图 clear/唯一索引与并发兜底）与
  `tests/backend/test_phase51_img2img.py`（7 用例：能力/config/processed 输出/
  parent/Seed/链式/Resume//modules）；
- Phase 5 专项测试更新：`basic_generate + 输入图 → UNUSED_INPUT_IMAGE`（原"允许"行为纠正）、
  `/modules` Gate C 断言（img2img registered + available）；
- 前端：`npm run build`（tsc + vite）通过；工作台 store 逻辑经
  临时 esbuild 断言脚本验证 9/9 PASS（Phase 6 起该脚本由 `tests/frontend/workbench_store.phase6.mjs`
  + CI `npm run test:store` 取代，临时目录已删除）。

## [0.6.0] — 2026-10-08

### Added（Phase 5：Image Input Foundation + Reference / Img2Img Capability Gate）

- **外部图片导入正式产品化（§三/§四/§五）**：`POST /api/v1/images/import`（PNG / JPG / JPEG / WEBP，
  单张 / 多张）；流程 = 选择本地文件 → 校验（扩展名 + MIME + magic bytes + 尺寸 + ≤10MB）→ Studio temp
  → 原子导入 → `DataRoot/images/originals/` → Image 数据库 → Gallery。**绝不引用用户原始文件路径**；
  来源统一 `kind=original / source=import / job_id=null`；外部导入的 Provenance 如实标记
  "外部导入"，无生成 Job 时返回 `IMAGE_NO_GENERATION_CONTEXT`（不伪造生成历史）。
- **sha256 去重（§六）**：新增 `images.sha256`（+索引）与 `images.imported_filename`；
  重复文件不创建第二份（返回已存在 image_id）；批量导入单张失败不影响整批
  （成功 / 已存在 / 失败 三类明细）；WEBP 尺寸解析（VP8 / VP8L / VP8X，无第三方依赖）。
- **图库批量导入 UI（§二十三）**：Gallery"导入"（多选 + 进度 n / N + 结果摘要"成功 N · 已存在 N · 失败 N"）。
- **工作台"输入图片"（§七/§八）**：生成页顶部模式切换 [文生图] / [图片生成]（不增加一级导航）；
  图片生成模式显示独立"输入图片"区（[+ 从图库选择] / [上传新图片 → 先行导入 Gallery 再引用]）；
  `WorkbenchSnapshot.input_images`（max=1，role=source，统一 `image_id`，禁止临时外部路径）。
- **Gallery Picker（§二十一）**：筛选（最近 / 未审核 / 保留 / 收藏）+ 搜索导入文件名；
  卡片 = 缩略图 / 尺寸 / 收藏；工作台与 Face Asset 参考图共用同一 Picker。
- **Gallery 快捷入口（§二十二）**：图片详情 Drawer"用作输入图片"→ 打开生成工作台并设置 input_image
  （当前工作台其它配置保留）。
- **Recipe 输入图快照（§九）**：recipe_versions 新增 `input_images_json`
  （image_id + file hash + role）；恢复配方原样恢复输入图关系；图片不存在 → 响应显式
  `missing=true`（界面显示"输入图片已丢失"，**绝不静默清空**）；input_images 参与
  "内容无变化不建新版本"的 signature 比较。
- **Job 创建冻结图片输入（§十）**：创建 Job 时从 WorkbenchSnapshot 冻结输入图片 →
  `JobStageItem.input_image_id`（Stage0 全部槽位）；**Job 创建后切换工作台图片不影响等待中的 Job**；
  输入图片不存在 → 创建期 404 `IMAGE_NOT_FOUND`；处理型 Job 快照与 input_image_ids 不一致 → 拒绝。
- **Face Asset Reference Image（§十二/§十三）**：新增正式关系表 `asset_reference_images`
  （asset_version_id / image_id / role / sort_order）；Face Asset 可绑定 1 张图库参考图
  （来源 = Gallery，不复制外部文件；绑定 / 更换 = 新版本，旧版本保留自己的参考图）。
- **ModuleCapabilities 输入声明（§十四）**：新增 `input_required / input_role`；
  `GET /api/v1/modules` 能力列表 → 前端图片生成 Gate 判定（无可用工作流时明确显示
  "图片生成：尚未配置可用工作流"并禁用提交，不猜测、不硬编码）。
- **ImageReferenceService（§十一）**：`GET /api/v1/images/{id}/references` 返回
  Recipe / StageItem（含活跃 Job）/ Asset 参考图 / Asset 溯源 / 派生图 的引用计数与明细
  （图片生命周期的删除前检查，Phase 5 不实现删除 UI）。
- **审图快捷键（§二十四）**：← / → 上一张 / 下一张，K 保留，R 淘汰，F 收藏；
  Ctrl+Z 或页面内"撤销"按钮撤销最近一次审核 / 收藏操作（栈深 20），不做复杂快捷键设置页。

### 能力 Gate（§二：本机调查结论 = Gate B，真实 Module 接入暂停）

- **Task 0 只读调查**（docs/IMAGE_CONDITIONING_INVENTORY.md；**未**下载模型 / 安装节点 /
  升级 ComfyUI / 更新 Manager / 移动模型 / 修改用户工作流）：本机**不存在**"现成、稳定、
  无需新增关键依赖"的参考图 / 图生图工作流 —— 唯一现成 Img2Img 工作流（`sdxl-图生图.json`，
  LoadImage→VAEEncode→KSampler denoise 0.55→VAEDecode）依赖的 `RealVisXL_V5.0_fp16` 与
  `add-detail-xl` 均不在磁盘；Reference / Face Reference / ControlNet / Qwen-Edit 均缺节点或模型
  （IPAdapter / PuLID / InstantID 节点不存在；controlnet / clip_vision / photomaker 目录为空）。
- **结论：需要新增模型/节点，已停止**；候选方案（方案 0 零下载 Qwen-2.1 latent Img2Img /
  方案 1 恢复 SDXL 链 / 方案 2 Qwen-Edit / 方案 3 IPAdapter）含模型、体积、显存、节点与
  ComfyUI 影响评估，见文档 §6，**等待用户选择**，未执行任何下载或安装。
- **本阶段零真实生图**（Gate B，§二十九）；"输入图片 → 新 Module → 现有 Pipeline → ComfyUI →
  Processed Image"链路待用户选定方案后接入（Phase 5.1）。

### Changed

- **架构验收（§二十五）**：未修改 QueueWorker / PipelineScheduler / ImageService 核心 /
  Job 状态机；输入图片冻结复用既有通用机制（快照 → StageItem.input_image_id + `_materialize_stages`），
  新增内容仅 = Module 能力字段（input_required/input_role）+ 通用图片输入层（导入/快照/引用检查）+ UI。
- 迁移 **`0010_image_inputs`**：`images.sha256/imported_filename`（+idx_images_sha256）、
  `recipe_versions.input_images_json`、`asset_reference_images` 关系表（+2 索引）。
- 版本：0.5.0 → 0.6.0（后端 / 前端 / configs/app.yaml 同步）。
- 文档：新增 IMAGE_CONDITIONING_INVENTORY（Task 0）与 PHASE5_REPORT；
  同步 API_PLAN / DATABASE_PLAN / DATA_MODEL_V1 / WORKBENCH_STATE / IMAGE_MODEL /
  MODULE_IO_CONTRACT / README / AGENTS / TASKS / DEV_LOG / TEST_REPORT。

### Tests

- 新增 `tests/backend/test_phase5_image_input.py` 18 例：导入（单张 / WEBP 尺寸 / 超限 / 非法类型）、
  sha256 去重（按内容不按文件名）、批量部分失败、Job 输入冻结（多槽位 / 缺失 404 / 多图 422 /
  处理型快照不一致）、Recipe 输入图快照（hash / 无变化不建版 / 恢复 / 丢失标记 / 未知图 404）、
  Face Asset 参考图（绑定 / 更换 / 沿用 / 非 face 拒绝 / 缺失 404）、引用保护（5 类来源计数与 0 引用）、
  Modules 能力（Gate B 判定）、迁移 0010 结构与幂等。
- 快速套件 168 → **186 passed**（Phase 4 全部回归继续通过）；前端 `npm run build`（tsc + vite）通过。

## [0.5.0] — 2026-10-08

### Added（Phase 4：History + Provenance + Generic Module I/O Contract）

- **历史正式可用**：`GET /api/v1/history`（来源 = jobs 表，不另建 History 表）+
  提示词页"历史"Tab：任务卡（时间/来源/Prompt 摘要/状态/数量/Pipeline/续跑标记）、
  基础筛选（全部/进行中/完成/失败/取消 + 来源）、右侧 Drawer（完整 Prompt / Negative /
  结构化字段 / 尺寸 / Seed / Workflow stages 与版本 / 错误 / 生成图片缩略图 +
  在生成工作台打开 / 在图库查看 / 继续剩余图片）。
- **续跑归组（Task6）**：沿 `resume_of_job_id` 归组为任务族（`root_job_id` 计算字段），
  A → B → C 续跑链在历史中显示为一个任务族（两级展示，不建复杂树）。
- **Image Provenance（Task10）**：`GET /api/v1/images/{id}/provenance` 返回
  parent/root/scale/job/stage/module/版本/双指纹/Seed；图库详情简洁展示 + 高级信息折叠。
- **派生图 → 工作台追溯根生成 Job（Task7）**：任何派生图（原图/高清/未来处理图）都恢复
  **根生成图所属 generate Job** 的配置；图库手动高清后的高清图不再恢复到 process Job 的空 Prompt；
  外部导入图明确返回 `IMAGE_NO_GENERATION_CONTEXT`（"没有可恢复的生成配置"）；
  "使用此图 Seed"改为"使用原图 Seed"（根图 Seed，高清图自身 seed 为 null）。
- **执行身份恢复（Task9）**：Image / History / 配方恢复出的 `workflow_modules` 携带完整身份
  （module/version/provider/binding_version/双指纹）；提交时按**原版本固定执行**，
  指纹不一致或 provider 不匹配直接拒绝（400），绝不静默升级到当前默认 Workflow。
- **前端 WorkflowModuleRef[] 列表化（Task8）**：工作台状态由 `upscaleEnabled` 布尔升级为
  `workflowModules: WorkflowModuleRef[]`（开关为派生值）；Phase 5 增加 Reference 只需列表加一项。
- **Module I/O 正式契约（Task2）**：ModuleCapabilities 新增
  `uses_seed / input_kind / output_kind / parent_policy / output_cardinality`；
  basic_generate `uses_seed=true, none→original, 无 parent`；upscale `uses_seed=false,
  image→upscaled, parent=input_image`；ImageService 按能力落库，**删除"有 input_image 就推断
  upscaled"的规则**（docs/MODULE_IO_CONTRACT.md）。
- **StageItem.seed（Task3）**：JobStageItem 新增真实 Seed（执行前落库；uses_seed=false 的 Stage
  为 NULL）；`JobItem.seed` 保留为基础生成快捷字段；图库手动高清不再产生"假 Seed"。
- **EngineAdapter 输入图片正式契约（Task4）**：`upload_input_image()` 进入基类契约
  （默认 `ENGINE_INPUT_UNSUPPORTED`，系统性）；ComfyUI / Mock 实现；UpscaleModule 删除 getattr
  duck typing；"构造引擎请求"阶段的系统性错误与提交阶段一致触发队列暂停。
- **binding_hash 执行指纹（Task1）**：`sha256(binding.yaml)[:16]` 与 workflow_hash 并列，
  进入 EngineBindingRef / Job / JobStage / workflow_snapshot / API / Image metadata；
  binding.yaml 改动（inputs/defaults/save_image_node/save_image_prefix 等）→
  `BINDING_HASH_MISMATCH` 拒绝执行；binding 自描述（module/provider/binding_version）一致性校验。
- **Studio Input Registry + TTL 清理（Task11）**：输入上传登记 `DataRoot/engine_inputs.json`；
  启动时只清理 NSFWStudio_inputs 下、已登记、无 RUNNING/INTERRUPTED 引用、超过 TTL（默认 24h）
  的文件；未配置 `comfyui.input_dir` 时安全跳过；绝不触碰其他 input 文件。

### Fixed

- **P0 历史 Job 无 Stage（Task0）**：v0.3.x 库执行 0007 后历史 Job 没有 Stage，
  Worker 领取后直接 FAILED（已复现）。新增 **`0008_pipeline_backfill`**：
  扫描 `jobs WHERE NOT EXISTS job_stages`，为每个旧 Job 回填 Stage0（basic_generate，身份继承
  Job 列）+ 对应 StageItem（状态/engine_job_id/图片关系从 JobItem 映射），**不改变历史 Job 本身状态**；
  并新增 **`0009_execution_fingerprint`**（jobs/job_stages.binding_hash + job_stage_items.seed +
  历史假 Seed 修正）。升级测试使用真实 v0.3.2 数据库（COMPLETED/QUEUED/PAUSED/INTERRUPTED），
  并验证 QUEUED Job 升级后仍可被同一 Worker 真实执行。
- **P1/P0 workflow_hash 覆盖不全（Task1）**：此前只校验 workflow.json，
  修改 binding.yaml（inputs/defaults/save_image_* 等）不会触发 hash 变化 → 已由 binding_hash 补齐。
- **P1 历史页面假空态（Task5）**："任务系统接入后自动记录"占位删除，历史正式接 Job 系统。
- **P1 派生图工作台恢复错误（Task7）**：高清处理 Job 的空 Prompt 不再被当作恢复源。

### Tests

- 新增 21 例：真实 v0.3.2 升级（含 QUEUED 可执行）、双指纹/自描述拒绝、能力驱动 kind/parent/seed、
  StageItem/manual Seed、EngineAdapter 输入契约（含不支持→系统性）、History 筛选与归组、
  派生图追溯、导入图无上下文、Provenance 全链路、Input Registry TTL 清理；
  快速套件 147 → **168 passed**；Phase 3 的 12 场景与 Phase 2.x 回归全部继续通过。
- 真实 ComfyUI 最短 smoke（Task13）：1 张基础图（768×1024，seed=1501957504）
  → 4x 高清（3072×4096，seed=null，parent 正确）→ History 任务族 → Gallery 父子 →
  从高清图打开工作台（恢复原 Prompt + 完整双指纹身份）；证据见 docs/PHASE4_REPORT.md。

### Changed

- 版本：0.4.0 → 0.5.0（后端 / 前端 / configs/app.yaml 同步）。
- 文档新增 PROVENANCE_SPEC / HISTORY_SPEC / MODULE_IO_CONTRACT / MIGRATION_0008_BACKFILL / PHASE4_REPORT；
  同步 PIPELINE_V2 / PIPELINE_STATE_MACHINE / UPSCALE_MODULE / COMFY_ADAPTER / IMAGE_MODEL /
  WORKBENCH_STATE / DATA_MODEL_V1 / DATABASE_PLAN / API_PLAN / JOB_STATE_MACHINE / RECOVERY_SPEC。

## [0.4.0] — 2026-10-08

### Added（Phase 3：Multi-stage Pipeline + Upscale）

- **多阶段管线**：新增 JobStage / JobStageItem（迁移 0007 + jobs.job_kind）；
  Job 创建时从 `workflow_snapshot.modules` 物化 Stage，**执行真源 = JobStage + workflow_snapshot**；
  Stage Gate 严格门控：`basic×N 全部 COMPLETED` 才启动 `upscale×N`，禁止交错与跨 Stage 抢跑。
- **UpscaleModule（第二套正式 WorkflowModule）**：标准输入只有 `input_image`；
  provider binding `upscale/v1`（4x-UltraSharp 链，复用本机已验证资源，见
  docs/UPSCALE_WORKFLOW_INVENTORY.md）；输入图片经 `POST /upload/image` 上传（Studio 唯一命名）。
- **图库已有图片单独高清**：`POST /api/v1/images/upscale` 创建 upscale-only `process` Job，
  与生成流水线共用同一 QueueWorker / UpscaleModule（禁止两套高清代码）。
- **Image 父子关系**：高清 `kind=upscaled` 存 `images/upscaled/`，`parent_image_id` 指向原图；
  `GET /images/{id}/versions` 支持原图 ↔ 高清切换；图库 HD 标记与多选"高清放大"。
- **前端**：工作台"② 高清放大"开关（配方保存/恢复 100% 一致）；分阶段实时进度
  （原图生成 x/y ✓、高清放大 m/n · 第 k 张 · p%）；缩略图 HD 标记。
- **Job API**：Job Detail 返回 `stages[]`（module/status/total/completed/current_item/progress）。

### Fixed（Task 0 执行漏洞修复）

- **§0.1 Worker 意外异常必须停队列**：代码级意外异常（非 EngineError）→ 当前 Job/Stage
  INTERRUPTED（保留 engine_job_id）+ `queue_paused=true` + WORKER_INTERNAL_ERROR，绝不继续领取
  下一个 Job；正常 shutdown 的 CancelledError 仍按原崩溃恢复逻辑（不写终态）。
- **§0.2 Binding 改为每次请求动态选择**：取消 Adapter 实例级绑定；新增 `EngineBindingRef`
  （module/module_version/provider/binding_version/workflow_hash），Adapter 按
  `(module_id, binding_version)` 缓存动态加载——一个 Adapter 服务全部模块。
- **§0.3 Workflow Hash 必须校验**：Job 固化的 workflow_hash 与磁盘不一致 →
  `WORKFLOW_HASH_MISMATCH`（系统性）拒绝执行；binding 目录视为 immutable，改 Workflow 必须新建 v2。
- **§0.4 修正固定 Seed**：恢复"每张独立随机 Seed"；`seed_mode=fixed` 仅用于单张精确复现
  （后端 fixed+count>1 → 400 FIXED_SEED_SINGLE_ONLY；前端"使用此图 Seed"自动 count=1，
  数量改 >1 自动切回随机）；删除 `base_seed + item_index`。
- **§十 执行总超时**：StageItem `execution_timeout`（默认 1800s，可由 Stage config 覆盖）→
  `ENGINE_TIMEOUT`，不无限 RUNNING。
- **§九 文件系统恢复**：ComfyUI SaveImage 输出前缀含 Studio 身份
  （`NSFWStudio/{job_short}/{stage}/{item_short}`）；history 丢失时按命名规则扫描自有输出兜底
  （绝不触碰用户普通图片）。

### Changed

- `WorkflowModule.execute()` / `build_engine_request()` 契约扩展：binding 来自 context（请求级）；
  `prepare_inputs()` 可选钩子（处理型模块的引擎侧输入准备）。
- `JobService.create_job`：workflow_modules / job_kind / input_image_ids / stage_configs；
  未知模块在创建期拒绝（400 WORKFLOW_ERROR）。
- 文档新增 PIPELINE_V2 / PIPELINE_STATE_MACHINE / UPSCALE_MODULE / UPSCALE_WORKFLOW_INVENTORY；
  同步 JOB_STATE_MACHINE / RECOVERY_SPEC / COMFY_ADAPTER / IMAGE_MODEL / WORKBENCH_STATE /
  DATA_MODEL_V1 / DATABASE_PLAN / API_PLAN / README / AGENTS。

## [0.3.2] — 2026-10-07

### Fixed（Phase 2.2：Data Consistency & Recovery Closure，无新功能）

- **P0 多输出导入整批原子化**：拆分为 `prepare_image_output()`（全部先校验）+
  `import_outputs_transaction()`（全部写 temp → 全部移动 → 单事务写入全部 Image）；
  任一步失败：回滚 DB + 删除本批次全部正式文件 + 清理 temp，不再出现"半成功图库资产"。
  `import_adapter_outputs()` 不再循环调用内部 commit 的单图函数。
- **P0 崩溃恢复后的 Job 终态归并**：恢复核对后重算 completed_count；全部 Item COMPLETED →
  Job COMPLETED + finished_at + `JOB_RECOVERED_COMPLETED` 事件；仍有未完成 Item → 保持
  INTERRUPTED。禁止"全部 Item COMPLETED 但 Job INTERRUPTED"。
- **附带修复（实测发现）**：Worker 任务被取消（进程退出/停机超时）或意外异常时不再经
  `finally` 写 Job 终态——此前会把仍有未完成 Item 的 Job 误标为 COMPLETED；现在保持
  RUNNING 现场，交由下次启动恢复。
- **P1 Resume 保持原 Workflow 身份**：`resume_remaining()` 完整继承 Parent 的
  workflow_snapshot + module/provider/binding/workflow_hash，不再读取当前 settings，
  禁止静默升级；原 binding 缺失时执行期报 BINDING_NOT_FOUND。升级 Workflow 属于创建新 Job。
- **P1 ComfyUI 取消不误伤其他任务**：先读 `/queue` 判断 target 位置——pending 只 delete、
  绝不 `/interrupt`；target 正是当前 running 才允许 interrupt；running 是别人的 prompt 时
  什么都不做（不再打断用户手工任务）。
- 文档同步：IMAGE_MODEL / RECOVERY_SPEC / COMFY_ADAPTER / JOB_STATE_MACHINE / QUEUE_SPEC /
  PHASE2_1_REPORT（原子化交叉引用）/ TEST_REPORT / DEV_LOG / TASKS / README。

### Tests

- 新增 9 例（批次原子 3 + 恢复归并/Resume 身份 3 + 取消边界 3）；快速套件 120 → **129 passed**；
  本阶段全部离线 Mock / stub 验证（合同不要求真实生成）；前端 build 通过。

## [0.3.1] — 2026-10-07

### Fixed（Phase 2.1：Stable Execution & Pipeline Contract Closure，无新功能）

- **P0 无图片却 COMPLETED**：Item COMPLETED 收紧为"engine succeeded ∧ 输出非空 ∧ 成功导入
  Studio Image（image_ids 非空）"；OUTPUT_MISSING / STORAGE_ERROR / 取输出异常一律
  Item FAILED + Job FAILED + `completed_count` 不增加 + `image_id=null`；崩溃恢复路径同步收紧。
- **ComfyUI 掉线后永久 RUNNING**：`/history` 请求失败不再伪装成"还在运行"——
  ConnectError → ENGINE_OFFLINE（Job FAILED + 队列暂停），其他网络错误 → ENGINE_NETWORK(transient)
  有限重试；history 可达但任务缺失时结合 `/queue` 与实时层新鲜度判定，超容忍才 unknown（任务丢失）。
- **Worker 硬编码模块参数**：新增 BasicGenerateModule + ModuleRegistry + PipelineExecutor，
  Worker 经 `PipelineExecutor.build_engine_request(job, item, seed)` 取请求，源码级守卫
  （测试）禁止 Worker 出现模块参数名。
- **Workflow Snapshot 与真实执行不一致**：Job 创建/续跑时由 module_identity 写入
  `modules:[{module_id,module_version,provider,binding_version,workflow_hash}]`。
- **Resume 复用 fixed seed**：resume-remaining 生成新快照（`count=remaining, seed_mode=random,
  seed=null`，workbench + generation_settings 同步）；父 Job 快照只读不变。
- **priority 越过拖拽顺序**：queue_position 成为唯一执行顺序事实源（Worker 领取 / GET /queue /
  reorder 统一排序）；`queue_mode=next` 仅通过插入位置实现；priority 保留但不参与排序。
- **Binding 版本硬编码**：Adapter 按 `module_id + binding_version` 解析
  `workflows/providers/comfyui/<module>/<version>/`；缺失 → 新错误类型 `BINDING_NOT_FOUND`
  （系统性；Job 创建时返回 4xx）。
- **Job API 输入过宽**：snapshot 直接复用严格 WorkbenchSnapshotModel（宽高 64–4096、
  count 1–64、seed 范围、prompt_mode/selected_assets/workflow_modules 结构 → 422）；
  Prompt 长度上限（结构化 ≤2000 / 正向 ≤10000 / 负向 ≤8000 → 400 PROMPT_TOO_LONG）。
- **Cancel 请求异常**：取消请求 try/except 隔离，失败时当前 Item 可完成、完成后 Job 安全落 CANCELLED。
- **Handoff ZIP 无 .git 可测**：gitignore 断言改为 .gitignore 文本规则（存在 .git 时才附加
  git check-ignore 核对），交接包解压后快速套件可独立运行。

### Tests

- 新增 `test_phase21_stability.py`（22 例）与 `test_comfyui_resilience.py`（7 例）；
  快速套件 91 → **120 passed**；真实 ComfyUI smoke（1 张）见 docs/PHASE2_1_REPORT.md。

## [0.3.0] — 2026-10-07

### Added（Phase 2：Job Execution Core + ComfyUIAdapter + Gallery）

- **数据模型**：jobs / job_items / job_events（migration 0005）、images（migration 0006）；
  `UNIQUE(source, client_request_id)` 外部幂等；Job 固化 WorkbenchSnapshot + Prompt + 素材/尺寸/数量 +
  Workflow 快照（后续修改 Prompt/Recipe/Asset 不影响已创建 Job）。
- **Job 执行核心（2A）**：JobService（创建 / 幂等 / 状态操作 / 续跑剩余）；单队列 SingleQueueWorker
  串行执行（唯一逻辑队列）；安全暂停（当前图完成后）、取消（终态、已完成图片保留）、
  继续（已完成 Item 绝不重跑）；每张图独立随机 Seed（执行时分配）；
  系统性失败（离线/OOM/工作流/模型/节点缺失）→ Job FAILED + 队列自动暂停；
  崩溃恢复（启动 RUNNING → INTERRUPTED，engine history 核对后导入或保持可恢复）；
  磁盘空间检查（严重不足拒绝新任务）。
- **Engine 层**：输出获取接口 + 错误分类（ENGINE_OFFLINE/NETWORK/WORKFLOW_ERROR/MODEL_MISSING/
  NODE_MISSING/OUT_OF_MEMORY/OUTPUT_MISSING/STORAGE_ERROR/UNKNOWN）+ 瞬态重试 ≤2 +
  MockEngineAdapter（success/delay/fail/offline/oom/workflow_error，仅测试用）+ 引擎工厂。
- **SSE 与 Job API**：`GET /api/v1/events/jobs`（只通知，DB 才是事实源）；
  POST/GET /jobs、pause/resume/cancel、resume-remaining、/queue、/queue/reorder、/queue/resume、
  /engine/status；`queue_mode: normal|next`。
- **真实 ComfyUI 接入（2B）**：本机环境调查（docs/COMFY_ENV_INVENTORY.md、WORKFLOW_INVENTORY.md，
  未破坏现有环境）；ComfyUIAdapter（POST /prompt + WebSocket 进度 + /history 核对 + /view 取回字节 +
  错误分类 + 安全取消）；provider binding（workflows/providers/comfyui/basic_generate/v1：
  Qwen-Image 2.1 UC 文生图链，支持 Negative，steps=25/cfg=1.0）；
  Job 记录 module/provider/binding_version/workflow_hash 溯源；机器地址只进 config.local.yaml。
- **Image / 图库（2C）**：引擎输出 → Studio temp → 校验（magic bytes + 尺寸）→ 原子移动
  DataRoot/images/originals → DB 登记；Gallery API（列表过滤/详情/content/review/favorite/
  workbench/by-job summary）；图库页（筛选 全部/未审核/保留/收藏/淘汰 + 图片 Grid + 详情 Drawer +
  按任务查看 + 保留/淘汰/收藏 + Image → 工作台 + 使用此图 Seed + 从图库创建素材 source_image_id）。
- **前端**：顶部双状态 Studio ● / Engine ●；右栏真实 Engine 状态 + 生成按钮（POST /jobs，
  normal/优先插队）+ 当前任务进度（第 N 张 / %）+ 队列（暂停/继续/取消/优先/拖拽排序）；
  中栏当前图 + 本 Job 已完成缩略图逐张显示（续跑父子合并）；SSE 实时刷新（断线回源 + 兜底轮询）；
  WorkbenchStore 支持固定 Seed。
- **测试**：新增 Job 队列与 Mock 故障套件（§五十八 全清单）、Image 服务/API 套件、
  binding 单测（无需 ComfyUI）、真实 ComfyUI 集成测试（1/3/8 张，离线自动跳过）。
- **文档**：JOB_STATE_MACHINE / QUEUE_SPEC / RECOVERY_SPEC / COMFY_ADAPTER / IMAGE_MODEL /
  COMFY_ENV_INVENTORY / WORKFLOW_INVENTORY 新增；DATA_MODEL_V1 / DATABASE_PLAN / API_PLAN /
  WORKBENCH_STATE / README / AGENTS 同步。

### Changed

- 公共默认引擎：`workflow.engine.provider = comfyui`（产品默认；测试/CI 用 mock；
  公共配置仍不得携带机器地址）。
- 版本：0.2.0 → 0.3.0（后端 / 前端 / configs/app.yaml 同步）。

## [0.2.0] — 2026-10-07

### Added（Phase 1：Prompt / Asset / Recipe Core）

- **数据模型**：prompts/prompt_versions、assets/asset_versions、recipes/recipe_versions/recipe_asset_snapshots
  （migration 0002/0003/0004；TEXT 主键 + `<前缀>_<uuid4>`；FK/UNIQUE/CHECK 全量约束；业务时间统一 UTC ISO 8601）。
- **Prompt**：结构化（固定八栏）/完整双模式；Negative Prompt 独立字段；内容变化建版本、元数据不建；
  版本 immutable；恢复旧版本 = 复制为新最新版；归档/恢复（软删除）；PromptComposer 后端权威合成
  + `/api/v1/prompts/compose` 前端同源预览。
- **Asset**：face/clothing/pose/scene 四分类；预览图上传（扩展名+MIME+magic bytes+大小≤10MB 校验）；
  temp → 校验 → 原子移动 → 提交 的安全文件流（提交失败清理文件）；DataRoot 相对路径入库；
  `StorageManager.resolve_under()` 防路径穿越；版本 immutable。
- **Recipe**：完整工作台快照（Prompt 快照+来源 FK、素材按 slot 锁定 asset_version 并复制内容快照、
  generation_settings（model_ref 占位槽位）、workflow_snapshot 预留 modules 结构、seed 固定 random）。
- **API**：/api/v1/prompts、/api/v1/assets、/api/v1/recipes 全套 CRUD+版本+归档+预览图+compose；
  统一错误格式 `{"error":{"code","message"}}`；列表统一 search/favorite/archived/limit/offset。
- **前端**：WorkbenchStore 统一工作台状态；生成工作台三栏（左 Prompt 编辑/中 预览占位/右 基础配置）；
  提示词页（我的 Prompt / 配方 / 历史 三 Tab + 编辑抽屉 + 版本历史）；素材页（分类 Tabs + 卡片网格 +
  上传 + 详情抽屉 + 用于生成）；"在生成工作台打开" 100% 恢复（Prompt / Recipe / Asset 三条注入路径复用
  WorkbenchSnapshot）；生成按钮明确显示"生成引擎尚未接入"。
- **测试**：33 → 68 例（Composer/服务/事务回滚/约束/迁移升级/文件安全/API 全链路）。
- **文档**：docs/DATA_MODEL_V1.md、docs/WORKBENCH_STATE.md 新增。

## [0.1.2] — 2026-10-07

### Changed（Phase 0.1.1：审查合同遗留契约修正）

- **统一异步契约**：`WorkflowModule.execute()` 改为 async（执行链路固定为
  Pipeline → WorkflowModule → EngineAdapter → 具体引擎，全部 await）；
  `validate_input()` / `capabilities()` 纯计算接口保持同步；异步原则写入模块 docstring 与开发指南。
- **DataRoot 配置分层**：公共 `configs/config.yaml` 不再携带任何机器路径（不设置 data_root）；
  新增本机私有层 `configs/config.local.yaml`（已 gitignore，不提交）。
  优先级固定：`NSFW_STUDIO_DATA_ROOT` > `config.local.yaml` > `config.yaml` > `%USERPROFILE%/NSFW-Studio-Data`。
  换电脑 clone 后零修改即可启动；本机 D 盘只存在于 local 文件。
- **Node 探测**：`dev_frontend.bat` 优先读取 `AIHOME_ROOT` 环境变量定位 AIHome Node，
  兼容探测规范默认根目录，最后回落系统 PATH。

### Added

- 新增 6 个测试（execute 为 async / EngineAdapter 全方法 async / 纯计算接口保持 sync /
  公共配置机器无关哨兵 / local 覆盖 / env 最高优先级 / config.local.yaml 被 gitignore），共 33 例。

## [0.1.1] — 2026-10-07

### Fixed（Phase 0.1：架构收口）

- **迁移失败恢复**：`applied_migration_ids()` 只把 `status='applied'` 视为已完成；failed 迁移下次启动仍按未完成重试；重试前清除同 ID failed 记录，避免主键冲突。
- **跨机器可移植**：代码默认 DataRoot 改为 `%USERPROFILE%/NSFW-Studio-Data`（本机盘符只在 configs/config.yaml 明确声明）；`dev_frontend.bat` 不再写死 AIHome 路径（AIHome 存在则用，否则回落系统 PATH，均无则清晰报错）。
- **状态语义**：前端顶部指示改为 "Studio 在线/离线"（只反映后端健康，不再显示虚假的 Engine 连接状态）。

### Added

- SQLite 工程化：`make_engine()` 统一 `journal_mode=WAL`、`busy_timeout=5000`、`foreign_keys=ON`。
- 数据库安全备份：`app/database/backup.py`（SQLite backup API）+ `scripts/backup_db.py`；DataRoot 新增 `backups/`。
- Workflow 标准契约：`WorkflowInput` / `WorkflowOutput` / `WorkflowValidation` / `ModuleCapabilities` / `ParameterSpec`；`WorkflowModule.execute()` 接收 EngineAdapter（引擎调用只发生在 EngineAdapter）。
- EngineAdapter 类型化：`EngineJobRequest` / `EngineJobStatus`（含进度字段）。
- GitHub CI（`.github/workflows/ci.yml`）：push/PR 自动跑 pytest 与 `npm ci && npm run build`。
- 新增 12 个测试（迁移失败恢复 / PRAGMA 生效 / 备份一致性 / 路径可移植 / 环境变量覆盖 / 契约存在性 / system_info 版本更新），共 27 例。

### Changed

- `QueueWorker` 移除 `submit(job)`：Job 的创建与持久化属于 API/JobService，Worker 只消费已存在的 Job（`process_job(job_id)`）。
- `system_info.version` 语义明确为**当前应用版本**：启动时与应用版本对齐，不一致自动更新。

## [0.1.0] — 2026-10-07

### Added（Phase 0：工程初始化与架构搭建）

- 后端骨架：FastAPI 应用工厂、lifespan 启动引导、health API（`GET /api/v1/health`）。
- 配置系统：`configs/{config,app,storage,workflow}.yaml`，支持 `NSFW_STUDIO_DATA_ROOT` / `NSFW_STUDIO_HOST` / `NSFW_STUDIO_PORT` 环境变量覆盖。
- DataRoot 系统：首次启动按 `storage.yaml` 清单自动创建 15 个目录（幂等）。
- 数据库基础：SQLAlchemy 2 + SQLite；`migration` 表、`system_info` 表、极简迁移框架。
- 日志系统：JSON Lines，app / jobs / errors 三路文件 + 控制台，5MB×5 轮转。
- 接口预留（仅规范，无实现、无引擎绑定）：`WorkflowModule`、`EngineAdapter`、`QueueWorker`。
- 存储管理：`StorageManager`（DataRoot 白名单路径解析）。
- 前端壳：React 18 + TypeScript + Vite 5；顶部导航（生成/图库/提示词/素材/设置）、
  Engine 健康指示、ThemeProvider 深浅主题（localStorage 持久化）、五页面空状态。
- 测试：pytest 15 例（后端启动 / API / 数据目录 / 数据库 / 接口存在性 / 幂等性）。
- 脚本：`dev_backend.bat`、`dev_frontend.bat`、`init_dataroot.py`、`build_handoff.py`。
- 文档：`docs/` 五份 + `DEV_LOG.md` / `TASKS.md` / `TEST_REPORT.md`。
