# TASKS — NSFW Studio V2

## Phase 1：Prompt / Asset / Recipe Core ✅（2026-10-07，v0.2.0）

- [x] 数据模型 + Migration 0002_prompt / 0003_asset / 0004_recipe（未改动 0001）
- [x] 统一 ID（prm_/prmv_/ast_/astv_/rcp_/rcpv_ + uuid4，TEXT 主键）
- [x] 统一时间工具（UTC ISO 8601，core/timeutil.py）
- [x] Prompt：结构化八栏/完整双模式、Negative、版本机制、归档/恢复、元数据不建版本
- [x] PromptComposer 后端权威合成 + compose 接口（前端预览同源）
- [x] Asset：四分类、预览图上传（四重校验）、temp→原子移动→提交 安全文件流、版本不可变
- [x] StorageManager.resolve_under 防穿越 + 安全测试
- [x] Recipe：Prompt 快照+FK、素材 slot 快照（UNIQUE 约束）、generation_settings（model_ref 占位）、workflow_snapshot 预留
- [x] Service 层（Prompt/Asset/Recipe）+ 单事务 + 并发冲突保护（VERSION_CONFLICT）
- [x] API 三组 + 统一错误格式 {"error":{code,message}} + 列表统一参数
- [x] 前端 WorkbenchStore + 生成三栏 + 提示词页三 Tab + 素材页 + 100% 恢复
- [x] 生成按钮显示"生成引擎尚未接入"（无假结果、无 Job/Worker/ComfyUI）
- [x] 测试 33 → 68 例全绿；v0.1.2 库升级测试；真实库迁移（先备份）
- [x] 浏览器人工验证（§五十九 清单：新建/保存/重开/素材/配方恢复/主题）
- [x] 文档：DATA_MODEL_V1 + WORKBENCH_STATE + 全部同步
- [x] feature/phase1 → develop → CI 绿 → main → CI 绿 → tag v0.2.0

## Phase 2（预告）：EngineAdapter 首个实现（ComfyUIAdapter）与 Job/Queue

- [ ] Job / JobItem / Image 数据模型与迁移
- [ ] QueueWorker 首个实现（消费已持久化 Job）
- [ ] ComfyUIAdapter（实现 EngineAdapter 异步契约）
- [ ] 图库页（Image 浏览）
- [ ] assets.source_image_id / recipes.cover_image_id 回填

## Phase 0.1.1：审查遗留契约修正 ✅（2026-10-07，v0.1.2）

- [x] `WorkflowModule.execute` 改为 async（与 EngineAdapter 异步契约统一；纯计算接口保持 sync）
- [x] 异步链路原则写入 docstring 与开发指南（Pipeline/WorkflowModule/EngineAdapter 全 await）
- [x] 公共 `configs/config.yaml` 机器无关化（不再设置 data_root，含防回归哨兵测试）
- [x] 新增本机配置层 `configs/config.local.yaml`（gitignore，不提交；本机 D 盘只在此声明）
- [x] 优先级链固定并测试：env > local > config.yaml > %USERPROFILE% 默认
- [x] `dev_frontend.bat` 支持 `AIHOME_ROOT` 环境变量（兼容探测默认根目录 → PATH 回退）
- [x] 测试 27 → 33 例全绿；npm run build 通过；develop/main CI 全绿；两分支同步；tag v0.1.2

## Phase 0.1：架构收口 ✅（2026-10-07，v0.1.1）

- [x] Migration 漏洞修复：仅 status=applied 视为完成；failed 下次启动重试；重试无主键冲突
- [x] 迁移失败恢复测试（失败→failed→重试→修复→applied）
- [x] SQLite 收口：WAL / busy_timeout=5000 / foreign_keys=ON（每个连接生效）
- [x] 安全备份入口：SQLite backup API（`app/database/backup.py` + `scripts/backup_db.py`）+ DataRoot/backups/
- [x] Workflow 标准契约：WorkflowInput / WorkflowOutput / WorkflowValidation / ModuleCapabilities / ParameterSpec
- [x] EngineAdapter 类型化：EngineJobRequest / EngineJobStatus（含 progress）
- [x] QueueWorker 职责收口：移除 submit()，只消费已存在 Job（process_job）
- [x] DataRoot 默认值可移植（%USERPROFILE%/NSFW-Studio-Data；config.yaml 明确声明本机盘符）
- [x] dev_frontend.bat 去硬编码（AIHome 探测 → PATH 回退 → 报错）；dev_backend.bat 补 Python 检查
- [x] 前端状态语义：Studio 在线/离线（不再显示虚假 Engine 状态）
- [x] system_info.version 语义：当前应用版本，启动时自动对齐
- [x] GitHub CI：push/PR 跑 pytest + npm ci/build
- [x] 测试 15 → 27 例全绿；npm run build 通过；CI 全绿
- [x] 文档同步 10 个文件；develop 合并回 main；tag v0.1.1

## Phase 0：工程初始化与架构搭建 ✅（2026-10-07，v0.1.0）

- [x] 项目立项与目录骨架（projects/nsfw-studio-v2，git main）
- [x] .gitignore / README / 项目级 AGENTS.md / pytest.ini
- [x] 配置系统：configs/{config,app,storage,workflow}.yaml + 环境变量覆盖
- [x] DataRoot 自动创建（15 目录，清单驱动，幂等）
- [x] 后端框架：FastAPI 工厂 / api/core/models/schemas/services/database/storage
- [x] SQLite 初始化：migration 表 + system_info 表 + 极简迁移框架
- [x] JSON 日志系统：app / jobs / errors 三路
- [x] health API（GET /api/v1/health）
- [x] WorkflowModule 接口预留（仅规范）
- [x] EngineAdapter 接口预留（仅规范，adapters/ 为空）
- [x] QueueWorker 接口占位
- [x] 前端壳：Vite + React + TS，顶部导航 + 五页面空状态
- [x] 主题系统：ThemeProvider + localStorage 持久化（深/浅）
- [x] Engine 状态指示（后端健康轮询）
- [x] 后端测试 15 例（启动/API/数据目录/数据库/接口/幂等）
- [x] 前端生产构建验证（tsc + vite build）
- [x] 浏览器 GUI 实测（导航/主题/Engine 指示/设置页）
- [x] 文档：PROJECT_STRUCTURE / DEVELOPMENT_GUIDE / DATABASE_PLAN / API_PLAN / PHASE0_REPORT
- [x] 开发与交接脚本：dev_backend / dev_frontend / init_dataroot / build_handoff
- [x] Registry 登记（projects/nsfw-studio-v2）
- [x] GitHub 推送（公开仓库 zxingyu178-dot/nsfw-studio-v2，main + develop + tag v0.1.0，2026-10-07，供三方 AI 审核）

## Phase 1：数据模型设计 + Prompt/素材/配方系统（待启动）

- [ ] 数据模型：Job / JobItem / Prompt / Recipe / Asset / Image 表设计与迁移
- [ ] PromptService / AssetService / 配方系统后端
- [ ] /api/v1/prompts、/api/v1/assets、/api/v1/recipes 接口
- [ ] 前端：提示词工作台、素材库页面（脱离空状态）
- [ ] 前端测试体系（Vitest + RTL）
- [ ] 集成冒烟测试脚本

## 更远（占位）

- [ ] Phase 2：EngineAdapter 首个实现（ComfyUIAdapter）与 QueueWorker
- [ ] 高清 / 图生图 / 参考图 / AI Agent 以 WorkflowModule 扩展
