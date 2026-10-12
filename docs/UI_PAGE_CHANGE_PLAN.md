# 页面改造清单（UI Page Change Plan）

> 项目：NSFW Studio V2 · 分支：`feature/ui-v1-redesign` · 基线：v0.8.0
> 说明：逐页列出**现状 → 目标布局 → 组件复用 / 新增 → 视觉层级 → 数据接线（字段不变）→ 状态与验收点**。
> 通用约束：不新增 / 不修改后端 API；所有字段沿用现有 Store / API；全站中文；图标按钮带 aria-label。

---

## 0. 应用外壳（App Shell） — UI-0

**现状**：`MainLayout` 顶栏 + 居中主区（max-width 1200）；`TopNav` 品牌 / 链接 / Engine 状态 / 主题切换；样式集中在 `app.css`。

**目标**：
- TopNav 采用 Token 化样式，导航当前项加 `aria-current="page"`；右侧状态区固定不挤压。
- 主区改为 `PageContainer`：生成 / 图库为宽版（填满到 ~1600），提示词 / 设置为正常宽度。
- 全局挂载 `ToastProvider`（供动作反馈）。

**组件**：复用 TopNav / EngineStatus / ThemeToggle；新增 PageContainer / PageHeader / Toast。
**验收**：双主题渲染正常；1280/1440/1920 导航不折行、当前页正确高亮；键盘 Tab 顺序合理。

---

## 1. 生成页 `/generate` — UI-1（最高优先级）

### 现状
- 顶部模式栏：生成模式（文生 / 图片）、工作流选择、队列方式（普通 / 插队）、查看队列；
- 三栏：`PromptEditorPane` | `ResultPane` | `SettingsPane`；
- 功能基本齐全，但样式类零散、状态呈现不统一（占位、进度、按钮、表单各有写法）。

### 目标布局（保持三栏，统一组件）
- **左栏 · 编辑区**：
  - Prompt 模式 `Segmented`（结构化 / 完整）；
  - 结构化：八部分按 2 列网格（窄屏单列），每字段统一 label + Textarea；
  - 完整模式：单个大 Textarea；
  - 负面词：独立 Textarea + 标签；
  - 组合预览：可折叠，只读，等宽弱底区块；
  - 输入图（图片模式）：缩略图 + 选择 / 移除，缺图显式错误；
  - 素材引用：八槽位，每槽"选择 / 清除"，已选显示名称 + 版本；来源 Prompt 徽标保留。
- **中栏 · 结果区**：
  - 当前 Job：状态 StatusBadge、阶段进度列表、总进度 ProgressBar、暂停 / 取消；
  - 结果舞台：图片或占位（空 / 加载 / 失败）；
  - 缩略图条：本 Job 全部图，HD 角标，点击切换；
  - 操作：放大 / Img2Img / 存素材 / 存配方 / 收藏 / 恢复工作台；
  - 底部提示。
- **右栏 · 参数区**：
  - 尺寸：预设 Segmented + 宽 / 高 Input（与 Slider 可选）；
  - 数量：Input + Slider；
  - Seed：模式 Segmented（随机 / 固定）+ 固定时 Seed Input；
  - 模块：勾选列表 + 主模块选择；选中模块的动态参数按 `config_schema` 渲染（int→Slider/Input、float→Slider、bool→Switch、enum→Select、string→Input）。
- **底部 / 顶部主操作**：生成（primary，lg）、队列方式切换、查看队列 Drawer（可拖拽排序）。

### 组件复用 / 新增
- 复用：workbenchStore 全部动作、jobStore、API；
- 新增 / 替换为设计系统组件：Button / Input / Textarea / Select / Slider / Switch / Checkbox / Segmented / Tabs / Badge / StatusBadge / Drawer / ProgressBar / Skeleton / EmptyState / ErrorState。

### 视觉层级
- "生成"是全局主操作，始终最醒目；编辑区标题层级统一（区块标题 lg，字段标签 sm muted）；
- 结果舞台为中栏视觉中心；进度与状态集中在舞台上方，不与操作按钮混杂。

### 数据接线（字段不变，举例）
- 提交：`workbenchStore.submit()` → `POST /jobs`（snapshot 结构不变）；
- 模块参数写入 `module_configs[module_id]`；模块身份字段（module_id/version/provider/binding*/workflow_hash/binding_hash）不变；
- SSE `/events/jobs` 与轮询由 jobStore 维护；进度取 Job / Stage / Item。

### 状态与验收
- Engine 离线：生成禁用并提示；提交中 loading 防重复；
- Job 失败 / 中断：显示错误 + 可恢复；空结果占位引导；
- 长 Prompt / 中文长串不撑破；窄屏单列顺序 编辑 → 参数 → 结果；
- 所有原有动作（暂停 / 取消 / 放大 / Img2Img / 存素材 / 存配方 / 收藏 / 队列重排）端到端可用。

---

## 2. 图库页 `/gallery` — UI-2

### 现状
- 工具栏：搜索、审查状态、仅收藏、来源、按 Job、网格 / 瀑布、刷新、导入；
- 支持按 Job 分组筛选；Grid / Masonry；详情 Drawer（预览、审阅 / 收藏、溯源、版本、操作）。

### 目标布局
- 顶部 `PageHeader`（标题 + 导入 / 刷新）+ 筛选 Toolbar（搜索占主宽，筛选收纳，避免一行过挤）；
- 主体：Grid（默认，3:4 卡片）/ Masonry（切换）；卡片角标（收藏 / 审查 / HD）；
- 详情 Drawer（宽档 640）：大图预览 → 审阅操作（保留 / 拒绝 / 重置）+ 收藏 → 溯源（默认简洁，高级折叠）→ 派生版本（父 / 子）→ 动作（放大 / Img2Img / 存素材 / 恢复工作台）。

### 组件
- 复用 api.images；新增统一 Toolbar 组合、Badge / StatusBadge / Drawer / EmptyState / Skeleton / ErrorState / Toast。

### 视觉层级
- 审图操作集中且高频：键盘 ← → 切换、J/K 或按钮保留 / 拒绝（保留现有快捷键并补提示 Tooltip）；
- 筛选当前条件可见、可一键清除。

### 数据接线（不变）
- 列表 `/images`（review_status / favorite / source / job_id / search / page）；
- review `/images/{id}/review`、favorite `/images/{id}/favorite`；
- versions / provenance / workbench / upscale 端点与字段不变。

### 状态与验收
- 空筛选结果：EmptyState + 清除筛选；加载：卡片骨架；
- 单张审阅失败不阻断其余；导入结果（导入 / 重复 / 失败）用 Toast / 汇总清晰呈现；
- 100+ 图滚动流畅；选中卡片有非颜色标识。

---

## 3. 提示词页 `/prompts` — UI-3

### 3.1 提示词 Tab
- 现状：搜索 / 标签 / 收藏筛选 + 卡片网格 + 编辑 Modal。
- 目标：统一 Tabs、Toolbar、卡片（标题 / 摘要 / 标签 / 收藏 / 更新时间）；编辑器 Modal（名称 / 标签 / 八部分或完整内容 / 备注）；新建 primary。
- 接线：`/prompts`、`/prompts/{id}`、versions；动作"发送到工作台"恢复八部分并保留 source_prompt。
- 验收：空列表 / 加载 / 失败三态；长标签换行；保存校验（名称必填）。

### 3.2 配方 Tab
- 现状：搜索 / 收藏 + 卡片 + 详情 Drawer（版本、输入图、素材快照、加载 / 版本恢复）。
- 目标：卡片显示模式 / 模块数 / 收藏；详情 Drawer 分区：概要（模式 / 尺寸 / 数量 / Seed）、输入图（**missing 显式"输入图片已丢失"**）、素材快照列表、模块、动作（加载到工作台 / 恢复此版本）。
- 接线：`/recipes`、versions、restore；字段不变。
- 验收：丢失输入图红色提示不被静默；加载后工作台完整回填。

### 3.3 历史 Tab
- 现状：状态 / 搜索 / 条数筛选；任务族（root + resumes）列表 + 详情 Drawer（阶段、条目 / 缩略图、续跑 / 补齐 / 工作台）。
- 目标：家族卡片清晰表达 root → resumes 层级（缩进 + 连接线）；详情 Drawer：阶段列表、每 Item 缩略图（含 seed / 状态）、动作（续跑 / 补齐续跑 / 恢复工作台）。
- 接线：`/history`、`/jobs/{id}`、resume / resume-remaining；字段不变。
- 验收：失败 / 中断任务有状态与错误信息；续跑后家族刷新；空历史引导去生成。

---

## 4. 素材页 `/assets` — UI-4

### 现状
- 工具栏：类型（face/clothing/pose/scene）、搜索、标签、收藏、已归档、新建；
- 素材网格 + 详情 Drawer（预览、字段、版本历史、参考图、编辑、新版本 / 上传参考图 / 恢复工作台）。

### 目标布局
- 类型用 Segmented（全部 + 四类，带中文标签 人脸 / 服装 / 姿势 / 场景）；
- 卡片：缩略图（preview 或参考图）+ 名称 + 标签 + 收藏；
- 详情 Drawer（宽档）：大图预览、字段（类型 / 名称 / 收藏 / 时间）、当前版本 prompt / notes、参考图缩略图、版本历史（可查看 / 恢复）、编辑区、动作（发送到工作台 / 新建版本 / 上传参考图 / 归档 / 恢复）。

### 组件
- 统一 Segmented / Grid / Card / Drawer / Modal / Badge / EmptyState / Skeleton / ErrorState。

### 接线（不变）
- `/assets`（type / search / tag / favorite / archived）、versions、workbench、archive / restore、preview；
- 参考图上传与版本字段不变。

### 验收
- 版本感知：选择素材时定位到具体版本；无预览有占位；
- 归档视图与恢复动作清晰；空 / 加载 / 失败三态完整。

---

## 5. 设置页 `/settings` — UI-4

### 现状
- 外观（主题 light/dark/auto）、Engine 状态（状态 / 地址 / Worker 配置 / 刷新）、Studio 状态（版本 / DataRoot / DB / 存储路径 / 计数 / 磁盘）。

### 目标布局
- 用 Section 分区，每区标题 + 描述 + 内容：
  - **外观**：主题 RadioGroup（浅色 / 深色 / 跟随系统），与 themeStore 实时联动；
  - **Engine 状态**：StatusDot + 详情（base_url、可用模块、Worker / 队列参数），刷新按钮；离线时 danger 说明；
  - **Studio 状态**：定义列表（版本、DataRoot、数据库、存储路径、对象计数、磁盘剩余），磁盘不足告警色。
- 只读信息统一 `dl/dt/dd` 样式，路径支持换行。

### 组件
- RadioGroup / Section / StatusDot / Button / Skeleton / ErrorState。

### 验收
- 主题切换即时生效并持久化；刷新状态有 loading；离线 / 错误有明确呈现；长路径不撑破。

---

## 6. 横切关注点（每页都要满足）

| 维度 | 要求 |
|---|---|
| 双主题 | 所有页面 / 组件在 Dark / Light 下对等，无硬编码颜色 |
| 分辨率 | 1280 / 1440 / 1920 布局正常，无横向滚动 |
| 数据极值 | 空 / 1 条 / 100+ 条；长文本、超长中文 / 英文串换行不溢出 |
| 异步状态 | loading（骨架 / Spinner）、empty（EmptyState）、error（ErrorState + 重试） |
| Engine 离线 | 全局可见，生成 / 续跑类动作禁用并解释 |
| 键盘 & 焦点 | 快捷键保留并提示；浮层焦点管理；焦点环可见 |
| 反馈 | 写操作结果 Toast；不可逆动作 Modal 确认 |
| 不回归 | 现有 Store / API 字段与动作全部保留，逐页走查原有功能 |

---

## 7. 实施顺序与提交节奏

| 阶段 | 内容 | 提交 / 推送 |
|---|---|---|
| UI-0 | Token 扩展 + 布局基元 + 16 组件 + 外壳 | 提交并推送 `feature/ui-v1-redesign` |
| UI-1 | 生成页（含队列 / 进度 / 结果） | 提交推送 |
| UI-2 | 图库 | 提交推送 |
| UI-3 | 提示词 / 配方 / 历史 | 提交推送 |
| UI-4 | 素材 / 设置 | 提交推送 |
| UI-5 | 全场景走查、测试补齐、文档与报告 | 提交推送，**不自行 merge main** |

每阶段完成标准：`npm run typecheck` 与 `npm run build` 通过、受影响测试通过、浏览器实际页面走查主路径与恢复路径。
