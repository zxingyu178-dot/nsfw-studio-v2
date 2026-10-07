# Changelog — NSFW Studio V2

格式参考 Keep a Changelog；版本遵循 SemVer。

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
