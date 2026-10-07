# Changelog — NSFW Studio V2

格式参考 Keep a Changelog；版本遵循 SemVer。

## [0.3.2] — 2026-10-07

### Fixed（Phase 2.2：Data Consistency & Recovery Closure，无新功能）

- **P0 多输出导入整批原子化**：拆分为 `prepare_image_output()`（全部先校验）+
  `import_outputs_transaction()`（全部写 temp → 全部移动 → 单事务写入全部 Image）；
  任一步失败：回滚 DB + 删除本批次全部正式文件 + 清理 temp，不再出现"半成功图库资产"。
  `import_adapter_outputs()` 不再循环调用内部 commit 的单图函数。
- **P0 崩溃恢复后的 Job 终态归并**：恢复核对后重算 completed_count；全部 Item COMPLETED →
  Job COMPLETED + finished_at + `JOB_RECOVERED_COMPLETED` 事件；仍有未完成 Item → 保持
  INTERRUPTED。禁止"全部 Item COMPLETED 但 Job INTERRUPTED"。
- **附带修复（实测发现）**：Worker 任务被取消（进程退出/停机超时）或意外异常时不再经
  `finally` 写 Job 终态——此前会把仍有未完成 Item 的 Job 误标为 COMPLETED；现在保持
  RUNNING 现场，交由下次启动恢复。
- **P1 Resume 保持原 Workflow 身份**：`resume_remaining()` 完整继承 Parent 的
  workflow_snapshot + module/provider/binding/workflow_hash，不再读取当前 settings，
  禁止静默升级；原 binding 缺失时执行期报 BINDING_NOT_FOUND。升级 Workflow 属于创建新 Job。
- **P1 ComfyUI 取消不误伤其他任务**：先读 `/queue` 判断 target 位置——pending 只 delete、
  绝不 `/interrupt`；target 正是当前 running 才允许 interrupt；running 是别人的 prompt 时
  什么都不做（不再打断用户手工任务）。
- 文档同步：IMAGE_MODEL / RECOVERY_SPEC / COMFY_ADAPTER / JOB_STATE_MACHINE / QUEUE_SPEC /
  PHASE2_1_REPORT（原子化交叉引用）/ TEST_REPORT / DEV_LOG / TASKS / README。

### Tests

- 新增 9 例（批次原子 3 + 恢复归并/Resume 身份 3 + 取消边界 3）；快速套件 120 → **129 passed**；
  本阶段全部离线 Mock / stub 验证（合同不要求真实生成）；前端 build 通过。

## [0.3.1] — 2026-10-07

### Fixed（Phase 2.1：Stable Execution & Pipeline Contract Closure，无新功能）

- **P0 无图片却 COMPLETED**：Item COMPLETED 收紧为"engine succeeded ∧ 输出非空 ∧ 成功导入
  Studio Image（image_ids 非空）"；OUTPUT_MISSING / STORAGE_ERROR / 取输出异常一律
  Item FAILED + Job FAILED + `completed_count` 不增加 + `image_id=null`；崩溃恢复路径同步收紧。
- **ComfyUI 掉线后永久 RUNNING**：`/history` 请求失败不再伪装成"还在运行"——
  ConnectError → ENGINE_OFFLINE（Job FAILED + 队列暂停），其他网络错误 → ENGINE_NETWORK(transient)
  有限重试；history 可达但任务缺失时结合 `/queue` 与实时层新鲜度判定，超容忍才 unknown（任务丢失）。
- **Worker 硬编码模块参数**：新增 BasicGenerateModule + ModuleRegistry + PipelineExecutor，
  Worker 经 `PipelineExecutor.build_engine_request(job, item, seed)` 取请求，源码级守卫
  （测试）禁止 Worker 出现模块参数名。
- **Workflow Snapshot 与真实执行不一致**：Job 创建/续跑时由 module_identity 写入
  `modules:[{module_id,module_version,provider,binding_version,workflow_hash}]`。
- **Resume 复用 fixed seed**：resume-remaining 生成新快照（`count=remaining, seed_mode=random,
  seed=null`，workbench + generation_settings 同步）；父 Job 快照只读不变。
- **priority 越过拖拽顺序**：queue_position 成为唯一执行顺序事实源（Worker 领取 / GET /queue /
  reorder 统一排序）；`queue_mode=next` 仅通过插入位置实现；priority 保留但不参与排序。
- **Binding 版本硬编码**：Adapter 按 `module_id + binding_version` 解析
  `workflows/providers/comfyui/<module>/<version>/`；缺失 → 新错误类型 `BINDING_NOT_FOUND`
  （系统性；Job 创建时返回 4xx）。
- **Job API 输入过宽**：snapshot 直接复用严格 WorkbenchSnapshotModel（宽高 64–4096、
  count 1–64、seed 范围、prompt_mode/selected_assets/workflow_modules 结构 → 422）；
  Prompt 长度上限（结构化 ≤2000 / 正向 ≤10000 / 负向 ≤8000 → 400 PROMPT_TOO_LONG）。
- **Cancel 请求异常**：取消请求 try/except 隔离，失败时当前 Item 可完成、完成后 Job 安全落 CANCELLED。
- **Handoff ZIP 无 .git 可测**：gitignore 断言改为 .gitignore 文本规则（存在 .git 时才附加
  git check-ignore 核对），交接包解压后快速套件可独立运行。

### Tests

- 新增 `test_phase21_stability.py`（22 例）与 `test_comfyui_resilience.py`（7 例）；
  快速套件 91 → **120 passed**；真实 ComfyUI smoke（1 张）见 docs/PHASE2_1_REPORT.md。

## [0.3.0] — 2026-10-07

### Added（Phase 2：Job Execution Core + ComfyUIAdapter + Gallery）

- **数据模型**：jobs / job_items / job_events（migration 0005）、images（migration 0006）；
  `UNIQUE(source, client_request_id)` 外部幂等；Job 固化 WorkbenchSnapshot + Prompt + 素材/尺寸/数量 +
  Workflow 快照（后续修改 Prompt/Recipe/Asset 不影响已创建 Job）。
- **Job 执行核心（2A）**：JobService（创建 / 幂等 / 状态操作 / 续跑剩余）；单队列 SingleQueueWorker
  串行执行（唯一逻辑队列）；安全暂停（当前图完成后）、取消（终态、已完成图片保留）、
  继续（已完成 Item 绝不重跑）；每张图独立随机 Seed（执行时分配）；
  系统性失败（离线/OOM/工作流/模型/节点缺失）→ Job FAILED + 队列自动暂停；
  崩溃恢复（启动 RUNNING → INTERRUPTED，engine history 核对后导入或保持可恢复）；
  磁盘空间检查（严重不足拒绝新任务）。
- **Engine 层**：输出获取接口 + 错误分类（ENGINE_OFFLINE/NETWORK/WORKFLOW_ERROR/MODEL_MISSING/
  NODE_MISSING/OUT_OF_MEMORY/OUTPUT_MISSING/STORAGE_ERROR/UNKNOWN）+ 瞬态重试 ≤2 +
  MockEngineAdapter（success/delay/fail/offline/oom/workflow_error，仅测试用）+ 引擎工厂。
- **SSE 与 Job API**：`GET /api/v1/events/jobs`（只通知，DB 才是事实源）；
  POST/GET /jobs、pause/resume/cancel、resume-remaining、/queue、/queue/reorder、/queue/resume、
  /engine/status；`queue_mode: normal|next`。
- **真实 ComfyUI 接入（2B）**：本机环境调查（docs/COMFY_ENV_INVENTORY.md、WORKFLOW_INVENTORY.md，
  未破坏现有环境）；ComfyUIAdapter（POST /prompt + WebSocket 进度 + /history 核对 + /view 取回字节 +
  错误分类 + 安全取消）；provider binding（workflows/providers/comfyui/basic_generate/v1：
  Qwen-Image 2.1 UC 文生图链，支持 Negative，steps=25/cfg=1.0）；
  Job 记录 module/provider/binding_version/workflow_hash 溯源；机器地址只进 config.local.yaml。
- **Image / 图库（2C）**：引擎输出 → Studio temp → 校验（magic bytes + 尺寸）→ 原子移动
  DataRoot/images/originals → DB 登记；Gallery API（列表过滤/详情/content/review/favorite/
  workbench/by-job summary）；图库页（筛选 全部/未审核/保留/收藏/淘汰 + 图片 Grid + 详情 Drawer +
  按任务查看 + 保留/淘汰/收藏 + Image → 工作台 + 使用此图 Seed + 从图库创建素材 source_image_id）。
- **前端**：顶部双状态 Studio ● / Engine ●；右栏真实 Engine 状态 + 生成按钮（POST /jobs，
  normal/优先插队）+ 当前任务进度（第 N 张 / %）+ 队列（暂停/继续/取消/优先/拖拽排序）；
  中栏当前图 + 本 Job 已完成缩略图逐张显示（续跑父子合并）；SSE 实时刷新（断线回源 + 兜底轮询）；
  WorkbenchStore 支持固定 Seed。
- **测试**：新增 Job 队列与 Mock 故障套件（§五十八 全清单）、Image 服务/API 套件、
  binding 单测（无需 ComfyUI）、真实 ComfyUI 集成测试（1/3/8 张，离线自动跳过）。
- **文档**：JOB_STATE_MACHINE / QUEUE_SPEC / RECOVERY_SPEC / COMFY_ADAPTER / IMAGE_MODEL /
  COMFY_ENV_INVENTORY / WORKFLOW_INVENTORY 新增；DATA_MODEL_V1 / DATABASE_PLAN / API_PLAN /
  WORKBENCH_STATE / README / AGENTS 同步。

### Changed

- 公共默认引擎：`workflow.engine.provider = comfyui`（产品默认；测试/CI 用 mock；
  公共配置仍不得携带机器地址）。
- 版本：0.2.0 → 0.3.0（后端 / 前端 / configs/app.yaml 同步）。

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
