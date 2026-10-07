# TASKS — NSFW Studio V2

## Phase 2.1：Stable Execution & Pipeline Contract Closure ✅（2026-10-07，v0.3.1）

- [x] P0：无图片不得 COMPLETED（输出非空 ∧ 导入 ≥1 Image 才 COMPLETED；OUTPUT_MISSING/STORAGE_ERROR 一律 FAILED；恢复路径同规则）
- [x] 掉线语义：/history 请求失败不再伪装 running（OFFLINE/NETWORK transient）；任务丢失有界判定 unknown；history 缺失不误判失败
- [x] BasicGenerateModule + ModuleRegistry + PipelineExecutor；QueueWorker 零模块参数（源码 token 守卫测试）
- [x] workflow_snapshot.modules 由实际模块身份写入（创建 + 续跑）
- [x] Resume 子 Job 新随机 Seed（count=remaining / random / null）；父 Job 快照只读
- [x] queue_position 唯一执行顺序事实源（Worker/GET/reorder）；next Job 拖拽后严格执行拖拽顺序
- [x] binding 目录由 module_id/binding_version 解析；BINDING_NOT_FOUND（系统性，Job 创建 4xx）；v2 fixture 可切换
- [x] Job API 严格校验（WorkbenchSnapshotModel：尺寸 64–4096 / count 1–64 / seed 范围 → 422；Prompt 长度上限 → 400）
- [x] Cancel 请求异常隔离（失败 → 当前 Item 完成后安全 CANCELLED）
- [x] Handoff ZIP 无 .git 可测（.gitignore 文本断言；ZIP 解压实测通过）
- [x] 回归测试 29 例新增（stability 22 + resilience 7）；快速套件 120 passed；前端 build 通过
- [x] 真实 ComfyUI 1 张 smoke 通过（新链路：模块 → Adapter → 导入 → Gallery）
- [ ] fix/phase2-stable-execution → develop → CI → main → CI → tag v0.3.1

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

## Phase 2：Job Execution Core + ComfyUIAdapter + Gallery ✅（2026-10-07，v0.3.0）

### 2A Job / 队列 / Mock / SSE

- [x] Migration 0005_job + Job / JobItem / JobEvent 模型（幂等 UNIQUE(source, client_request_id)）
- [x] Engine 层：输出获取接口 + 错误分类（9 类）+ 瞬态重试 ≤2 + MockEngineAdapter + 工厂
- [x] 事件总线（SSE 基础）+ JobService（创建/幂等/暂停/取消/继续/续跑剩余/队列排序）
- [x] 单队列 QueueWorker（串行、Item 边界暂停、安全取消、Seed 执行时分配、崩溃恢复）
- [x] Job API + SSE + main.py 装配 + 磁盘空间检查
- [x] Mock 故障测试套件（§五十八 全清单 14 场景，含瞬态网络重试 / Workflow 错误）

### 2B 本机 ComfyUI 调查 + ComfyUIAdapter + 第一套真实生图

- [x] docs/COMFY_ENV_INVENTORY.md + docs/WORKFLOW_INVENTORY.md（只读调查，未破坏环境）
- [x] 用 ControlHub 已批准的计划任务入口启动 ComfyUI（0.37.0，任务 `\AIHome\ComfyUI`）
- [x] basic_generate provider binding（workflows/providers/comfyui/basic_generate/v1：Qwen-Image 2.1 UC 链）
- [x] ComfyUIAdapter（/prompt + WebSocket 进度 + /history 核对 + /view 取回 + 错误分类 + 安全取消）
- [x] 第一张真实生图成功（NSFWStudio/20261007_00001_.png，832×1216，含模型加载约 300s）
- [x] binding 单测（无需 ComfyUI，CI 可跑）+ Job 记录 workflow_hash/binding_version 溯源

### 2C Image / Gallery / Review

- [x] Migration 0006_image + Image 模型（kind / review_status / favorite / source / metadata）
- [x] 引擎输出 → Studio temp → 校验 → 原子移动 DataRoot/images/originals → DB 登记（失败全回滚）
- [x] Gallery API（列表过滤 / 详情 / content / review / favorite / workbench / by-job summary 含收藏数）
- [x] WorkbenchSnapshot 支持 seed（"使用此图 Seed"；默认 random）
- [x] 从图库创建素材（POST /assets 支持 source_image_id，独立资产文件）
- [x] 前端：SSE 订阅 + jobStore（事件只通知，一律回源 GET；兜底轮询）
- [x] 前端：顶部双状态 Studio ● / Engine ●（§五十二）
- [x] 前端：右栏真实 Engine 状态 + 生成按钮（normal / 优先插队）+ 当前任务进度 + 队列（暂停/继续/取消/优先/拖拽）
- [x] 前端：中栏当前图 + 本 Job 已完成缩略图逐张显示（续跑父子合并）
- [x] 前端：图库页（筛选 / Grid / 详情 Drawer / 审核 / 收藏 / 按任务查看 / 打开工作台 / 创建素材）
- [x] 真实 ComfyUI 集成测试 1 / 3 / 8 张（3 passed，12 张图；顺序执行 / Seed=base+index / 逐张入 Gallery / 元数据 / Snapshot）
- [x] 文档：JOB_STATE_MACHINE / QUEUE_SPEC / RECOVERY_SPEC / COMFY_ADAPTER / IMAGE_MODEL 新增；DATA_MODEL_V1 / DATABASE_PLAN / API_PLAN / WORKBENCH_STATE / README / AGENTS 同步
- [x] 全量 pytest（91 快速 + 3 集成）/ 前端 build 验证；三段提交（2A/2B/2C）→ develop → CI 绿 → main → CI 绿 → tag v0.3.0

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
