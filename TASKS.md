# TASKS — NSFW Studio V2

## Phase 0：工程初始化与架构搭建 ✅（2026-10-07）

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
- [x] GitHub 推送（私有仓库 zxingyu178-dot/nsfw-studio-v2，main + develop + tag v0.1.0，2026-10-07）

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
