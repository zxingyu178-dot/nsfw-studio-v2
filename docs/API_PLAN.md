# API_PLAN — API 现状与规划

> 更新：2026-10-07（Phase 2，v0.3.0）。错误格式统一为 `{"error": {"code", "message"}}`。

## 1. 约定

- 前缀：`/api/v1`（破坏性变更升级版本号，不做字段级兼容层）。
- 层次：api 只做 HTTP 编排（参数校验用 Pydantic schema），业务逻辑在 services。
- 交互格式：JSON；业务时间统一 UTC ISO 8601（`Z` 结尾）。
- 列表统一参数：`search / favorite / archived / limit / offset`（Asset 额外 `type`），响应含 `total`。
- 交互文档：FastAPI 自动 Swagger（`/docs`）。

## 2. 现有接口

### 健康与服务信息

- `GET /api/v1/health` → `{"status":"ok","version":"0.3.0"}`
- `GET /` → 服务基本信息

### Prompt（`app/api/v1/prompts.py`）

```
GET    /api/v1/prompts                       列表（search/favorite/archived/limit/offset）
POST   /api/v1/prompts                       创建（+v1；结构化模式正向由后端合成）
GET    /api/v1/prompts/{id}                  详情（含 current_version）
PATCH  /api/v1/prompts/{id}                  元数据（名称/收藏，不建版本）
POST   /api/v1/prompts/{id}/versions         新内容版本（内容不变则不建）
GET    /api/v1/prompts/{id}/versions         版本历史
POST   /api/v1/prompts/{id}/versions/{vid}/restore   恢复旧版本（复制为新最新版）
POST   /api/v1/prompts/{id}/archive | /restore       软删除/恢复
POST   /api/v1/prompts/compose               结构化合成预览（与保存同源）
```

### Asset（`app/api/v1/assets.py`）

```
GET    /api/v1/assets                        列表（额外支持 type 过滤）
POST   /api/v1/assets                        创建（multipart，支持预览图上传；v1）
GET    /api/v1/assets/{id}                   详情
PATCH  /api/v1/assets/{id}                   元数据
POST   /api/v1/assets/{id}/versions          新版本（multipart，可选新预览图）
GET    /api/v1/assets/{id}/versions          版本历史
GET    /api/v1/assets/{id}/preview[?version=]  预览图文件流
GET    /api/v1/assets/{id}/workbench         素材 → 工作台快照（prompt 填入对应 slot）
POST   /api/v1/assets/{id}/archive | /restore
```

创建素材额外支持可选表单字段 `source_image_id`（图库 → 素材溯源，§四十八）。

### Recipe（`app/api/v1/recipes.py`）

```
GET    /api/v1/recipes                       列表
POST   /api/v1/recipes                       保存配方（body: {name, favorite, snapshot: WorkbenchSnapshot}）
GET    /api/v1/recipes/{id}                  详情（含 current_version + asset_snapshots）
PATCH  /api/v1/recipes/{id}                  元数据
POST   /api/v1/recipes/{id}/versions         新版本（快照变化才创建）
GET    /api/v1/recipes/{id}/versions         版本历史
POST   /api/v1/recipes/{id}/versions/{vid}/restore   恢复（快照原样复制）
POST   /api/v1/recipes/{id}/archive | /restore
```

### Job / Queue / SSE（`app/api/v1/jobs.py`）

```
POST   /api/v1/jobs                        创建生成任务（body: {snapshot, client_request_id?,
                                           queue_mode: normal|next, source}；幂等返回原 Job）
GET    /api/v1/jobs                        列表（status/limit/offset）
GET    /api/v1/jobs/{id}                   详情（含 items 子项 + stages 多阶段进度，§二十四）
POST   /api/v1/jobs/{id}/pause             安全暂停（当前图完成后暂停）
POST   /api/v1/jobs/{id}/resume            继续暂停任务（已完成 Item 不重跑）
POST   /api/v1/jobs/{id}/cancel            取消（终态；已完成图片保留）
POST   /api/v1/jobs/{id}/resume-remaining  继续剩余图片（创建子 Job）
GET    /api/v1/queue                       当前队列（worker/running/queued/paused）
POST   /api/v1/queue/reorder               拖拽排序（仅等待任务，全量一一对应）
POST   /api/v1/queue/resume                恢复队列（系统性失败自动暂停后）
GET    /api/v1/engine/status               引擎健康（Adapter.health()，独立于 Studio 状态）
GET    /api/v1/events/jobs                 SSE 任务事件（只通知；事实源永远是数据库）
```

### Image / Gallery（`app/api/v1/images.py`）

```
GET    /api/v1/images                      列表（job_id/review_status/favorite/source/kind/
                                           date_from/date_to/limit/offset）
GET    /api/v1/images/{id}                 详情
GET    /api/v1/images/{id}/content         图片文件流
GET    /api/v1/images/{id}/versions        父子关系 {image,parent,children}（§十九）
PATCH  /api/v1/images/{id}/review          审核：KEPT / REJECTED / UNREVIEWED
PATCH  /api/v1/images/{id}/favorite        收藏切换
GET    /api/v1/images/{id}/workbench       Image → 工作台快照 + 该图 Seed（§四十七）
POST   /api/v1/images/upscale              图库已有图片高清放大（body: {image_ids:[…]}，§二十四）
                                           → 创建 job_kind=process 的普通 Job（仅 upscale Stage）
GET    /api/v1/images/by-job/{id}/summary  按 Job 统计（§四十九）
```

约定：状态机与暂停/取消/续跑语义见 docs/JOB_STATE_MACHINE.md；队列行为见 docs/QUEUE_SPEC.md；
崩溃恢复见 docs/RECOVERY_SPEC.md。

创建 Job 的输入校验（Phase 2.1 §八 + Phase 3 §0.4/§五，固定）：

```
snapshot 直接复用严格 WorkbenchSnapshotModel：
  width / height  64..4096
  count           1..64
  seed            0..2147483647（seed_mode=fixed 时必须提供，且 count 必须 = 1，
                  §0.4 固定 Seed 仅用于单张精确复现：fixed + count>1 → 400 FIXED_SEED_SINGLE_ONLY）
  prompt_mode     structured | full（Literal）
  selected_assets 结构化类型；workflow_modules 为对象数组
                   （[basic_generate] 或 [basic_generate, upscale]；process Job 必须 == [upscale]）
Prompt 长度上限：结构化单字段 ≤2000 / 正向 ≤10000 / 负向 ≤8000（400 PROMPT_TOO_LONG）
workflow_snapshot.modules 由后端按实际模块身份写入（§四/§五），客户端无需传递
未知 WorkflowModule → 400 WORKFLOW_ERROR（创建期拒绝，不是执行期才炸）
```

## 3. 规划（Phase 4+，按需实现）

| 方法与路径 | 用途 |
| --- | --- |
| 图生图 / 参考图 / 人脸修复 | 新增 WorkflowModule + provider binding 目录即可复用同一 Job API |
| Agent / 豆包 / 手机端接入 | 复用同一 Job API（source=agent/doubao 已预留） |
