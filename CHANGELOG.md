# Changelog — NSFW Studio V2

格式参考 Keep a Changelog；版本遵循 SemVer。

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
