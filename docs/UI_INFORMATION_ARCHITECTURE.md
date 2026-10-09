# UI 信息架构（UI Information Architecture）

> 项目：NSFW Studio V2 · 分支：`feature/ui-v1-redesign` · 基线：v0.8.0（commit `1b8286be`）
> 范围：仅前端表现层。本文档只描述**现有契约下**的信息组织、页面职责、状态归属与跨页流转，不新增后端能力。

---

## 1. 产品定位与核心任务

NSFW Studio 是本地桌面端 Web 应用（React 18 + TS + Vide + FastAPI），围绕"AI 图片生产流水线"组织。用户的核心任务链：

1. **组织输入**：编写 Prompt（结构化八部分 / 完整文本）、负面词、引用素材、选择输入图；
2. **配置生成**：选择工作流与模块、模块参数、尺寸、数量、Seed、生成模式与队列方式；
3. **执行与跟踪**：提交 Job、查看队列与多阶段进度、暂停 / 取消 / 续跑；
4. **审阅与沉淀**：图库审图（保留 / 拒绝 / 收藏）、派生（放大 / Img2Img）、保存素材与配方、恢复工作台复现。

UI 的职责是把这条链路按"编辑区 → 结果区 → 参数区"清晰分区，并让每个对象在任意状态（空 / 加载 / 成功 / 失败 / 离线）下都有明确、可理解的呈现。

---

## 2. 全局导航

顶部固定导航（`TopNav`），自左向右：

| 区域 | 内容 |
|---|---|
| 品牌 | `NSFW Studio` |
| 主导航 | 生成 `/generate` · 图库 `/gallery` · 提示词 `/prompts` · 素材 `/assets` · 设置 `/settings` |
| 右侧操作 | Engine 连接状态（`EngineStatus`）· 主题切换（`ThemeToggle`） |

- 当前项高亮（视觉状态 + `aria-current="page"`），不仅靠颜色区分。
- 导航在窄宽度下可横向滚动，不折行、不遮挡右侧状态。
- Engine 状态与主题切换为**全局常驻**，在任何页面都可见。

---

## 3. 页面职责清单

| 页面 | 路由 | 核心任务 | 主要数据来源 | 关键动作 |
|---|---|---|---|---|
| 生成 | `/generate` | 组织输入、配置参数、提交并跟踪 Job、查看当前结果 | `workbenchStore`、`jobStore`、`api.modules/jobs/images` | 生成、排队、暂停、取消、放大、Img2Img、存素材、存配方、收藏 |
| 图库 | `/gallery` | 浏览 / 筛选 / 审阅全部图片，查看溯源与派生版本 | `api.images`、`jobStore`（队列） | 保留 / 拒绝、收藏、放大、Img2Img、存素材、恢复工作台、导入 |
| 提示词 | `/prompts` | 管理可复用 Prompt、配方、按 Job 查看历史 | `api.prompts/recipes/jobs/history` | 新建 / 编辑 Prompt、加载配方、版本恢复、续跑 / 补齐续跑、恢复工作台 |
| 素材 | `/assets` | 管理人脸 / 服装 / 姿势 / 场景四类素材及版本、参考图 | `api.assets` | 新建素材、新版本、上传参考图、恢复工作台、归档 / 恢复 |
| 设置 | `/settings` | 外观、Engine 状态、Studio 状态与存储信息 | `themeStore`、`api.health/engineStatus` | 切换主题、刷新状态 |

`/prompts` 内部用 Tab 组织三个子视图（URL query `tab=prompts|recipes|history`）：

- **提示词**：可复用 Prompt 模板（含标签、收藏、版本）；
- **配方**：一次完整生成配置的快照（含模块、输入图、素材快照）；
- **历史**：按 Job 任务族（root + resumes）组织的执行记录。

---

## 4. 全局对象模型与关系

```
Prompt（可复用模板）
  └─ PromptVersion（多版本，含八部分结构化内容）

StructuredPrompt（八部分，顺序永久固定）
  style · face · clothing · pose · scene · composition · lighting · extra

Asset（素材：face/clothing/pose/scene）
  ├─ AssetVersion（prompt_text / notes / tags / preview）
  └─ ReferenceImage（参考图，多对多）

Recipe（配方）
  └─ RecipeVersion
       ├─ WorkbenchSnapshot（Prompt + 负面词 + 素材引用 + 输入图 + 生成设置 + 模块）
       ├─ RecipeAssetSnapshot（素材槽位快照）
       └─ InputImage 快照（可能 missing，必须显式提示"已丢失"）

Job（任务）
  ├─ JobItem（逻辑图片槽位，1..count）
  │    └─ Image（输出图，image_id）
  ├─ JobStage（多阶段管线的阶段）
  │    └─ JobStageItem（槽位在某阶段的执行记录，含 input/output image、seed）
  └─ WorkflowSnapshot（模块执行身份：module_id + 双指纹 + config）

Image（图片）
  ├─ parent_image_id（派生来源：原图 → 高清 / Img2Img）
  ├─ review_status（UNREVIEWED / KEPT / REJECTED）
  ├─ favorite
  └─ provenance（完整溯源：job/stage/module/seed/scale）

WorkflowModule（模块）
  ├─ 执行身份：module_id + module_version + provider + binding_version + workflow_hash + binding_hash
  ├─ config_schema（动态参数表单：type/label/default/min/max/step/choices/required）
  └─ accepts_input_images / primary / enabled
```

关键关系：

- **工作台是编辑中枢**：Prompt / Asset / Recipe / Image / History 都可"恢复到工作台"，回填 `workbenchStore`；
- **Job 是执行与历史的唯一来源**：历史不另建表，`/history` 由 Job 按 root/resume 归组；
- **Image 是产物与再加工起点**：可派生放大 / Img2Img，也可反查生成上下文（含真实 Seed）。

---

## 5. 状态归属（权威来源）

| 状态 | 所有者 | 说明 |
|---|---|---|
| 工作台编辑态 | `workbenchStore`（Zustand） | Prompt、素材引用、输入图、模式、尺寸、数量、Seed、模块及参数；服务端快照为恢复来源 |
| 队列 / 运行态 | `jobStore`（Zustand） | Queue、Running Job、进度；经 SSE `/events/jobs` 与轮询更新，服务端为权威 |
| 主题 | `themeStore`（Zustand + localStorage） | `light` / `dark` / `auto`；持久化，`auto` 跟随系统 |
| 列表 / 详情数据 | 服务端（FastAPI） | 图库、Prompt、Recipe、Asset、History 均以 API 返回为准，前端不做权威缓存 |

原则：

- 前端只做**编辑态与视图态**，不臆造字段、不改变语义；所有字段名与后端 Schema 双侧镜像；
- 写操作以服务端响应 / SSE 为准，本地乐观反馈不作为结果依据；
- 跨页恢复时，用 API 返回的快照整体替换工作台内容，并保留来源标识（source prompt / recipe / image / job）。

---

## 6. 跨页流转

| 来源 | 入口动作 | 目标 | 携带 / 回填 |
|---|---|---|---|
| 图库 Image | 发送到工作台 | `/generate` | 最近生成上下文快照 + 真实 Seed（`/images/{id}/workbench`） |
| 图库 Image | Img2Img / 放大 | `/generate` 或直接建 Job | 输入图 image_id、对应模式与模块 |
| 素材 Asset | 发送到工作台 | `/generate` | 对应 slot 填入 prompt_text（`/assets/{id}/workbench`） |
| 配方 Recipe | 加载到工作台 | `/generate` | RecipeVersion 完整快照；输入图丢失时显式标记 |
| 提示词 Prompt | 使用 / 版本恢复 | `/generate` | 八部分 / 完整内容回填，保留 source_prompt 标识 |
| 历史 History | 恢复工作台 | `/generate` | 该 Job 的 workbench_snapshot |
| 历史 History | 续跑 / 补齐续跑 | 留在 `/prompts/history` | 创建 resume Job，刷新家族 |
| 任意结果 | 保存为素材 / 配方 | 抽屉 / `/assets` | 从当前 Job 快照创建 |

所有跳转在跳转前完成数据写入（先恢复快照，再切路由），避免目标页出现空闪。

---

## 7. URL 结构

使用 `HashRouter`（本地静态文件友好）：

```
#/generate
#/gallery
#/prompts?tab=prompts
#/prompts?tab=recipes
#/prompts?tab=history
#/assets
#/settings
```

- Tab 状态反映在 query，刷新后保持所在子视图；
- 抽屉 / 模态为上下文操作，第一版不强制写入 URL（保持现有行为）。

---

## 8. 响应式与宽度策略

目标桌面分辨率：**1280 / 1440 / 1920** 宽度。

- **生成页**：三栏网格 `编辑区(5) : 结果区(4) : 参数区(3)`；
  - ≥1280：三栏并排；
  - <1280：退化为单栏堆叠，顺序固定为 编辑 → 参数 → 结果（保证提交前能完成配置与审阅）；
- **图库 / 素材 / 卡片列表**：`auto-fill` 自适应网格，卡片最小宽度固定，宽屏自动增加列数；
- **内容页（提示词 / 设置）**：阅读型容器设置最大宽度，避免长文本在超宽屏过散；
- 顶部导航与右侧状态在各宽度下保持可达，不依赖 hover 才能操作。

---

## 9. 全局状态呈现原则

每个数据区域都必须覆盖以下状态，且组件统一、不各自另起：

| 状态 | 呈现 |
|---|---|
| 初次加载 | 骨架屏（`Skeleton`），结构与真实内容一致 |
| 空数据 | `EmptyState`：说明 + 主动作按钮 |
| 成功 | 正常内容 |
| 加载失败 | `ErrorState`：错误信息 + 重试 |
| Engine 离线 | 全局状态点 + 生成类动作禁用并解释原因 |
| Job 失败 / 中断 | 状态徽标 + 错误信息 + 恢复 / 重试路径 |
| 长文本 / 中文长串 | 换行、截断（带 title）、不撑破布局 |
