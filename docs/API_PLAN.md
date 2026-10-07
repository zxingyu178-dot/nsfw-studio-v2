# API_PLAN — API 现状与规划

> 更新：2026-10-07（Phase 1，v0.2.0）。错误格式统一为 `{"error": {"code", "message"}}`（§三十六）。

## 1. 约定

- 前缀：`/api/v1`（破坏性变更升级版本号，不做字段级兼容层）。
- 层次：api 只做 HTTP 编排（参数校验用 Pydantic schema），业务逻辑在 services。
- 交互格式：JSON；业务时间统一 UTC ISO 8601（`Z` 结尾）。
- 列表统一参数：`search / favorite / archived / limit / offset`（Asset 额外 `type`），响应含 `total`。
- 交互文档：FastAPI 自动 Swagger（`/docs`）。

## 2. 现有接口

### 健康与服务信息

- `GET /api/v1/health` → `{"status":"ok","version":"0.2.0"}`
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

## 3. 规划（Phase 2+，按需实现）

| 方法与路径 | 用途 |
| --- | --- |
| POST /api/v1/jobs | 创建生成任务（依赖 EngineAdapter 接入） |
| GET /api/v1/jobs/{id} | 任务详情（含子项状态） |
| GET /api/v1/images | 图片列表 |
| GET /api/v1/images/{id}/file | 图片文件流 |
| GET /api/v1/engine/status | 引擎状态（转发 EngineAdapter.health()） |
