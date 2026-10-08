# TASKS — NSFW Studio V2

## Phase 5.1：Image Pipeline Contract Closure + Qwen Img2Img ✅（2026-10-08，v0.7.0）

### A. 图片 Pipeline 契约收口

- [x] Task 1：WorkflowModuleRef 正式类型化（module_id/module_version/provider/binding_version/双 hash/config；
  前后端镜像；WorkbenchSnapshot/WorkflowSnapshot/Job 响应全部使用正式类型，不再用 list[dict]）
- [x] Task 2：Recipe 完整 Workflow 身份（P0 修复——不再丢失 provider/双 hash；旧配方不偷偷升级；
  新建工作台保存配方时尽量固化真实身份）
- [x] Task 3：config 单链唯一事实源（Workbench → Recipe → Job.workflow_snapshot → JobStage.config_json；
  PipelineExecutor 注入 module_config；Resume 保留 config；stage_configs 仅内部/测试路径）
- [x] Task 4：输入图消费校验（P0——basic_generate + 输入图 → UNUSED_INPUT_IMAGE；需要输入图却没给 →
  INPUT_IMAGE_REQUIRED；Job 创建期拒绝）
- [x] Task 5：PipelineValidator 统一合法性（Stage0 输入需求 / Stage N 链式 output→input / 处理型仅 upscale /
  未知模块创建期拒绝 / 模块 validate_config 钩子；不在 QueueWorker）
- [x] Task 6：工作台模式真正绑定 Primary Module（文生图=basic_generate；图片生成=可用图片模块；
  历史矛盾数据校正；store 9/9 断言通过）
- [x] Task 7：/modules 返回真实可用性（registered/available/provider/binding_version/unavailable_reason；
  comfyui 必须能加载 binding；前端 Gate 仅依据 available=true）
- [x] Task 8：Face Asset 参考图 clear（reference_action inherit/set/clear；UI [更换]/[移除]；旧版本保留）
- [x] Task 9：导入去重 DB 兜底（迁移 0011 images(sha256) 部分唯一索引；并发 IntegrityError → duplicate 而非 500）

### B. Qwen Img2Img 零下载实验 → Gate C

- [x] Task 10：实验 Workflow（temp/experimental/qwen_img2img/，不进入正式 providers 目录；
  未下载模型/未装节点/未升级 ComfyUI/未改用户工作流）
- [x] Task 11：最小真实实验（1 张输入 768×768 → 输出；seed/denoise/耗时/显存/错误全记录；
  另做 denoise=1.0 同 seed/prompt 对照 + 0.8 中间点）
- [x] Task 12：成功标准（上传/执行/无缺节点缺模型/无 OOM/输出有效且尺寸正确/seed 与 denoise 进入 KSampler）
  + 人工确认输入图对输出有决定性影响（0.55 结构相关 0.9993 vs 对照 0.16）
- [x] Gate C 成功 → Img2ImgModule + img2img/v1 binding + 参数/UI（图库"以此图进行图生图"+ 变化强度滑杆）
- [x] 架构验收：新增第三种 Module 未改动 QueueWorker / PipelineScheduler / ImageService 核心
- [x] 版本：v0.7.0；feature/phase51-contract-img2img → develop → main → tag

## Phase 5：Image Input Foundation + Reference / Img2Img Capability Gate ✅（2026-10-08，v0.6.0）

- [x] Task 0：只读调查本机图片条件生成能力（工作流/模型/节点；未下载/未安装/未升级/未改用户工作流）→
  **Gate B 确认**（无现成可用工作流）→ docs/IMAGE_CONDITIONING_INVENTORY.md（能力矩阵 + 候选方案，等用户选择）
- [x] §三/§六/§二十三：外部图片导入（PNG/JPG/JPEG/WEBP；校验 → temp → 原子导入 → images/originals → Image 表 → Gallery）；
  sha256 去重（不建第二份，返回已存在 image_id）；批量单张失败不整批失败；Gallery"导入"UI（多选 + 进度 n/N + 成功/已存在/失败）
- [x] §七/§八：Workbench 输入图片区（图库选择 / 上传即导入）+ 模式切换 [文生图]/[图片生成]；
  WorkbenchSnapshot.input_images（max=1，role=source，统一 image_id）
- [x] §九：Recipe 输入图快照（image_id + file hash + role；参与 signature；恢复原样；图片不存在 → 显式"输入图片已丢失"）
- [x] §十：Job 创建冻结输入图片（Stage0 全部槽位；切换工作台不影响等待 Job；缺失 404；处理型快照不一致拒绝）
- [x] §十一：ImageReferenceService + GET /images/{id}/references（Recipe/StageItem/Asset 参考/Asset 溯源/派生图）
- [x] §十二/§十三：Face Asset Reference Image（asset_reference_images 关系表；绑定/更换 = 新版本；仅 face；来源=图库）
- [x] §十四：ModuleCapabilities 增加 input_required / input_role + GET /api/v1/modules（前端图片生成 Gate 判定）
- [x] §二十/§二十一/§二十二/§二十四：模式栏与 Gate 提示、Gallery Picker（筛选/搜索/缩略图/尺寸/收藏）、
  "用作输入图片"、快捷键 ←/→/K/R/F + Ctrl+Z 撤销
- [x] §二十五 架构验收：未修改 QueueWorker / PipelineScheduler / ImageService 核心 / Job 状态机（仅新增能力字段 + 通用输入层 + UI）
- [x] §二十八：新增 test_phase5_image_input.py 18 例；快速套件 168 → **186 passed**（Phase 4 全部回归通过）；前端 build 通过
- [x] §二十九：Gate B → **零真实生图**；"Image conditioning backend: pending environment decision"
- [x] §三十一/§三十二：版本 v0.6.0（基础图片输入 + 导入完整交付，不含真实 Img2Img）；feature/phase5-image-input → develop → main → tag
- [x] Phase 5.1 已完成（见顶部）：Img2Img Module + provider binding + 真实最小实验（Gate C 成功，v0.7.0）

## Phase 4：History + Provenance + Generic Module I/O Contract ✅（2026-10-08，v0.5.0）

- [x] Task 0：迁移 0008_pipeline_backfill（不改 0007）——历史 Job 回填 Stage0/StageItem（身份继承 Job 列，
  状态映射，output_image_id=JobItem.image_id，不改历史 Job 状态）；0009_execution_fingerprint（binding_hash/StageItem.seed/历史假 Seed 修正）；
  真实 v0.3.2 库升级测试（COMPLETED/QUEUED/PAUSED/INTERRUPTED + QUEUED 升级后仍可执行）
- [x] Task 1：binding_hash 全链路（EngineBindingRef/Job/JobStage/快照/API/Image metadata）+ BINDING_HASH_MISMATCH +
  binding 自描述校验（module/provider/binding_version）+ 老 Job null 兼容
- [x] Task 2：ModuleCapabilities I/O 契约（uses_seed/input_kind/output_kind/parent_policy/output_cardinality）；
  ImageService 按能力判定 kind/parent（删除"input_image 推断 upscaled"）
- [x] Task 3：JobStageItem.seed 正式化（basic 真实 Seed / upscale NULL / manual upscale Image.seed=null）
- [x] Task 4：EngineAdapter upload_input_image 正式契约（默认 ENGINE_INPUT_UNSUPPORTED，系统性；ComfyUI/Mock 实现；去 getattr）
- [x] Task 5：历史正式接 Job（GET /history + 历史 Tab：任务卡/筛选/Drawer/三操作）
- [x] Task 6：Resume 归组（root_job_id 计算字段，A→B→C 一个任务族，两级展示）
- [x] Task 7：派生图 → 工作台追溯根生成 Job（图库高清不再恢复空 Prompt；导入图 404 IMAGE_NO_GENERATION_CONTEXT；"使用原图 Seed"）
- [x] Task 8：前端 workflowModules: WorkflowModuleRef[]（upscaleEnabled 变派生值）
- [x] Task 9：Image/History/配方恢复携带完整执行身份，提交时固定原版本（指纹不一致/provider 不匹配拒绝）
- [x] Task 10：Image Provenance API + 图库详情溯源展示（默认简洁/高级折叠）
- [x] Task 11：Studio Input Registry + TTL 清理（只清 NSFWStudio_inputs 下登记过、无活动引用文件；未配置 input_dir 安全跳过）
- [x] Task 12：新增 21 例测试；快速套件 147 → **168 passed**（Phase 3 12 场景 + Phase 2.x 回归全绿）
- [x] Task 13：最短真实 smoke（1 基础 768×1024 → 4x 3072×4096 → History → Gallery → 高清图打开工作台恢复原 Prompt+双指纹身份）
- [x] Task 14：文档 5 新增 + 12 同步；feature/phase4-history-provenance → develop → CI 绿（run 37736554279）→ main → CI 绿（run 37736733728）→ tag v0.5.0 + 交接 ZIP 邮件

## Phase 3：Multi-stage Pipeline + Upscale ✅（2026-10-08，v0.4.0）

- [x] Task 0.1：Worker 代码级意外异常 → 当前 Job/Stage INTERRUPTED + queue_paused + WORKER_INTERNAL_ERROR（CancelledError 保持原恢复逻辑）
- [x] Task 0.2：EngineBindingRef 请求级动态绑定（一个 Adapter 服务全部模块，缓存 key=(module_id,binding_version)）
- [x] Task 0.3：workflow_hash 校验（binding immutable；不一致 → WORKFLOW_HASH_MISMATCH 拒绝执行）
- [x] Task 0.4：固定 Seed 仅限单张（后端 fixed+count>1 → 400 FIXED_SEED_SINGLE_ONLY；前端自动收敛/切回随机）
- [x] §一-§五：迁移 0007 + JobStage/JobStageItem + Job 创建物化 Stage + job_kind（generate/process）
- [x] §六-§八：Stage Gate 严格门控（basic×N 全部完成 → 才进 upscale×N）；暂停/取消在 StageItem 边界；按 StageItem 崩溃恢复
- [x] §九/§十：输出命名含 Studio 身份（NSFWStudio/{job}/{stage}/{item}）+ scan_stage_outputs 文件级恢复 + execution_timeout/ENGINE_TIMEOUT
- [x] §十一/§十二：UpscaleModule + upscale/v1 binding（4x-UltraSharp 链，复用本机已验证资源；investigation → docs/UPSCALE_WORKFLOW_INVENTORY.md）
- [x] §十三/§十四：输入图片经 /upload/image 上传（Studio 唯一命名）；Image 存储泛化（originals/upscaled/processed + parent_image_id）
- [x] §十五-§十九：前端工作流开关（配方 100% 恢复）、分阶段实时进度、HD 标记、图库父子关系切换与多选高清
- [x] §二十/§廿一/§廿四：POST /api/v1/images/upscale → upscale-only process Job（同一 Worker）；Job Detail stages[]
- [x] §二十五：多阶段测试 15 场景（顺序/Gate/暂停取消恢复/父子/process Job/内部异常/hash/超时/配方）——快速套件 144 passed；全量 147 passed（含 3 真实链路）
- [x] §二十六：真实 ComfyUI 验收（1 张基础 640×960 → 1 张真实高清 2560×3840；图库 64×64 → 256×256）
- [x] §二十七：文档（PIPELINE_V2 / PIPELINE_STATE_MACHINE / UPSCALE_WORKFLOW_INVENTORY / UPSCALE_MODULE / PHASE3_REPORT 新增 + 既有同步）
- [x] feature/phase3-pipeline-upscale → develop → CI 绿（run 37724675927）→ main → CI 绿（run 37725594175）→ tag v0.4.0 + 交接 ZIP 邮件

## Phase 2.2：Data Consistency & Recovery Closure ✅（2026-10-07，v0.3.2）

- [x] §1 P0：多输出导入整批原子化（全部先校验 → 全部 temp → 全部移动 → 单事务入库；失败全回滚清残留；不再循环单图 commit 函数）
- [x] §2 P0：恢复核对后 Job 终态归并（全完成 → COMPLETED + JOB_RECOVERED_COMPLETED；否则保持 INTERRUPTED + 计数更新）
- [x] §2 附带真 bug：Worker 取消/异常不再经 finally 误写 COMPLETED 终态（保持 RUNNING 现场交启动恢复）
- [x] §3 P1：Resume 完整继承 Parent Workflow 身份（快照 + 全列），禁止静默升级；binding 缺失执行期报 BINDING_NOT_FOUND
- [x] §4 P1：ComfyUI 取消先读 /queue——pending 只 delete、running 才 interrupt、其他 running 不打扰
- [x] §5：文档同步（IMAGE_MODEL / RECOVERY_SPEC / COMFY_ADAPTER / JOB_STATE_MACHINE / QUEUE_SPEC / PHASE2_1_REPORT / TEST_REPORT / DEV_LOG / TASKS / CHANGELOG）
- [x] 回归测试新增 9 例；快速套件 129 passed；前端 build 通过（本阶段不跑真实生成）
- [x] fix/phase2-data-consistency → develop → CI 绿（d90f1b4）→ main → CI 绿（d90f1b4）→ tag v0.3.2

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
- [x] fix/phase2-stable-execution → develop → CI 绿（8448553）→ main → CI 绿（8448553）→ tag v0.3.1

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
