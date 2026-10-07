# API_PLAN — API 现状与规划

> 更新：2026-10-07（Phase 0）

## 1. 约定

- 前缀：`/api/v1`（破坏性变更升级版本号，不做字段级兼容层）。
- 层次：api 只做 HTTP 编排（参数校验用 Pydantic schema），业务逻辑在 services。
- 交互格式：JSON；时间统一 ISO 8601 字符串。
- 交互文档：FastAPI 自动 Swagger（`/docs`）。

## 2. 现有接口

### GET /api/v1/health

健康检查（Phase 0 规范 §十五）。

```json
{ "status": "ok", "version": "0.1.2" }
```

### GET /

服务基本信息：`{"name":"NSFW Studio","version":"0.1.0","api":"/api/v1/health"}`。

## 3. 规划（Phase 1+，按需实现）

| 方法与路径 | 用途 |
| --- | --- |
| POST /api/v1/jobs | 创建生成任务（CreateJobRequest → JobResponse） |
| GET /api/v1/jobs | 任务列表（分页） |
| GET /api/v1/jobs/{id} | 任务详情（含子项状态） |
| POST /api/v1/jobs/{id}/cancel | 取消任务 |
| GET /api/v1/images | 图片列表（分页/过滤） |
| GET /api/v1/images/{id}/file | 图片文件流 |
| GET /api/v1/assets | 素材列表（face/clothing/pose/scene） |
| POST /api/v1/assets/import | 导入素材 |
| GET/POST /api/v1/prompts | 提示词 CRUD |
| GET/POST /api/v1/recipes | 配方 CRUD |
| GET /api/v1/engine/status | 引擎状态（转发 EngineAdapter.health()，未接入时返回 unbound） |

- 错误响应统一：`{"detail": {"code": "...", "message": "..."}}`（Phase 1 定稿）。
- 分页约定：`?page=1&page_size=50`，响应含 `total`。
- 引擎相关接口只依赖 `EngineAdapter` 抽象，接入 ComfyUI 时无需改 API 层。
