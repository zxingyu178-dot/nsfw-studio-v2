# HISTORY_SPEC — 历史任务（Phase 4 / v0.5.0）

> Task 5/6：历史页面正式接 Job 系统。**历史来源 = jobs 表，不另建 History 表。**

## 1. 数据来源与归组

- 全部历史条目来自 `jobs`（Web / Resume / Agent / Doubao 统一入此表）；
- **任务族两级归组**（Task 6）：

```
原任务（root，resume_of_job_id = null）
└─ 续跑任务（resume，resume_of_job_id = 原任务）
   └─ 再次续跑 → 仍归入同一任务族（展示不建复杂树）
```

- `root_job_id` 为**计算字段**（沿 `resume_of_job_id` 向上找到最初 Job），不额外入库；
- 筛选语义：任务族内**任一** Job 命中筛选即保留整族——续跑任务永远不会被显示成无关任务。

## 2. API

```
GET /api/v1/history?bucket=all|active|completed|failed|cancelled&source=web|resume|agent|doubao&limit&offset
→ {items: [{root_job_id, root: Job, resumes: [Job…]}], total, limit, offset}
```

- `bucket`：`all` / 进行中（QUEUED,RUNNING,PAUSED,INTERRUPTED）/ 完成 / 失败 / 取消；
- `source`：web / resume / agent / doubao；
- 任务族按族内最新 created_at 倒序；族内续跑按创建时间升序；
- 第一版**不做**复杂全文搜索（Prompt 摘要由前端从 `positive_prompt_snapshot` 截取）。

## 3. 页面（提示词页 → 历史 Tab，`HistoryTab.tsx`）

任务卡至少显示：创建时间 / 来源 / Prompt 摘要 / 状态 / 任务数量（完成 x/y）/ Pipeline
（`基础生成 → 高清放大`）/ 是否续跑（"续跑"标记 + 缩进归组）/ 是否有剩余可续跑。

筛选：`全部 / 进行中 / 完成 / 失败 / 取消` + 来源下拉。

点击任务 → 右侧 Drawer：

- 完整 Prompt / Negative / 结构化 Prompt / 尺寸 / Seed（真实 StageItem Seed，无则为"—"）、
  数量、错误（如有）、续跑自（如有）；
- Workflow stages：每 Stage 的模块 / 状态 / 完成数 / 版本（module_version、binding_version、
  workflow_hash/binding_hash 短码）；
- 生成图片缩略图（按 job_id 查询图库）；
- 操作：
  - **在生成工作台打开**：用 Job 的 workbench_snapshot + 完整执行身份注入工作台（Task9 固定原版本）；
  - **在图库查看**：`/gallery?job=<id>`；
  - **继续剩余图片**：状态为 FAILED/CANCELLED/INTERRUPTED 且 `completed_count < requested_count`
    时可用（沿用既有 `POST /jobs/{id}/resume-remaining`，子 Job 继承原 Workflow 身份）。

## 4. 与状态机的关系

- 历史只读展示，不改变 Job 状态；暂停/取消/续跑等操作仍走既有 Job API（见 JOB_STATE_MACHINE.md）；
- SSE 只负责通知刷新，数据库（jobs）永远是唯一事实源。