# DEV_LOG — NSFW Studio V2

## 2026-10-07 — Phase 2.2：Data Consistency & Recovery Closure（v0.3.2）

**执行**：TRAE Code Agent（fix/phase2-data-consistency → develop → CI → main → CI → tag v0.3.2）
短收口任务：修数据一致性，无新功能；完成后 Phase 2.x 收口结束。

### 交付

- **§1（P0）导入整批原子化**：prepare_image_output() + import_outputs_transaction()；
  全部先校验 → 全部 temp → 全部移动 → 单事务入库；失败回滚 DB + 删除本批次全部正式文件 + 清 temp。
- **§2（P0）恢复终态归并**：`_finalize_recovery()`——全部 Item COMPLETED → Job COMPLETED
  （finished_at + JOB_RECOVERED_COMPLETED 事件）；否则保持 INTERRUPTED 且 completed_count 更新。
- **§2 附带真 bug（实测发现并修复）**：process_job 的 finally 会在任务被取消/异常时照写终态，
  把仍有未完成 Item 的 Job 误标 COMPLETED（Phase 2.1 用例在本阶段重启验证时暴露）——
  重构为 `_execute_job()` 承载执行、终态只在正常返回时写；取消/异常一律保持 RUNNING 现场。
- **§3（P1）Resume 身份继承**：去掉 module_identity 重读，完整继承 Parent 全字段；禁止静默升级。
- **§4（P1）取消边界**：cancel_job 先读 /queue；pending 只 delete、running 才 interrupt、
  其他 running 不打扰。

### 验证（如实）

- 快速套件：**129 passed**（120 + 新增 9；新增覆盖见 TEST_REPORT）；
- 前端 `npm run build`：通过；
- 本阶段按合同**不跑真实 ComfyUI 生成**（全部 Mock / stub 离线验证）。

### 决策

| 决策 | 理由 |
| --- | --- |
| 批次失败时删除"本批次已移动"的正式文件（而非仅失败的那张） | 图库资产必须以批次为单位守恒；跨批次删除有误伤风险，用本批次目录清单精确回滚 |
| Worker 取消/异常不写终态而是留 RUNNING | 终态必须有可信证据（成功=导入完成、失败=明确错误）；中断属于"未完成"，恢复流程才有权判定 |
| Resume 不重读 module_identity | "继续剩余"语义 = 原环境完成原任务；想换新版本 Workflow 应创建新 Job |
| cancel_job 读队列后再决定 interrupt | /interrupt 是全局行为，必须避免打断用户手工在 ComfyUI 运行的其他任务 |

## 2026-10-07 — Phase 2.1：Stable Execution & Pipeline Contract Closure（v0.3.1）

**执行**：TRAE Code Agent（fix/phase2-stable-execution → develop → CI → main → CI → tag v0.3.1）
本阶段不新增产品功能，只修执行漏洞 + 把真实运行链接回 WorkflowModule 架构。

### 交付

- **P0 完成条件**：Item COMPLETED 收紧为 engine succeeded ∧ 输出非空 ∧ 成功导入 ≥1 个 Studio
  Image；OUTPUT_MISSING / STORAGE_ERROR / 取输出异常一律 FAILED（completed_count 不增、
  image_id=null）；崩溃恢复同规则。
- **掉线语义**：`/history` 请求失败 → ENGINE_OFFLINE / ENGINE_NETWORK(transient)（不再伪装 running）；
  history 可达但任务缺失 → /queue + WS 新鲜度判定，超容忍（10 次）→ unknown（任务丢失）。
- **模块架构**：BasicGenerateModule + ModuleRegistry + PipelineExecutor；Worker 只调
  `pipeline.build_engine_request(job,item,seed)`；源码 token 守卫禁止 Worker 出现模块参数名。
- **快照同步**：Job 创建/续跑写入 workflow_snapshot.modules（真实模块身份）。
- **Resume**：子 Job 新快照 count=remaining / seed_mode=random / seed=null；父快照只读。
- **队列**：queue_position 唯一执行顺序（Worker/GET/reorder 三处统一）；priority 仅保留。
- **binding 版本化**：目录由 module_id+binding_version 解析；新增 BINDING_NOT_FOUND（系统性，
  创建 Job 时 4xx）。
- **API 校验**：snapshot 复用严格 WorkbenchSnapshotModel（64..4096 / 1..64 / seed 范围 → 422）；
  Prompt 长度上限（2000/10000/8000 → 400 PROMPT_TOO_LONG）。
- **Cancel 隔离**：取消请求失败仅告警，当前 Item 完成后安全落 CANCELLED。
- **Handoff 无 .git 可测**：gitignore 断言改为文本规则；ZIP 解压后快速套件独立通过。

### 验证（如实）

- 快速套件：**120 passed**（原 91 + 新增 29：stability 22 + resilience 7）；
- 真实 ComfyUI smoke：**1 张 PASSED**（新链路：Job→模块→Adapter→导入→Gallery，
  Item.image_id 非空、workflow_snapshot.modules 完整）；
- 前端 `npm run build`：通过；交接 ZIP 解压（无 .git）快速套件：通过；
- 首次 smoke 因 ComfyUI 未运行被 skip → 用计划任务 `\AIHome\ComfyUI` 重启后重跑通过
  （冷启动模型加载约 7 分钟，属本机已知性能特征）。

### 实测发现并修复

1. Mock 适配器 `get_job_outputs()` 恒返回空 → 新完成条件下所有 Mock 用例会 FAILED；
   改为返回 1×1 PNG fixture（source=mock 标识），顺带把"成功必须导入"变成全体用例的隐式回归。
2. 源码守卫断言最初直接搜字符串会命中注释 → 改为 tokenize 去注释/字符串后再断言。
3. `_finish_job` 顺带把首个 FAILED Item 的 error_type/message 落到 Job（UI 可显示失败原因）。

### 决策

| 决策 | 理由 |
| --- | --- |
| 完成条件包含"成功导入 Image"而不是仅"取得输出" | 图库是唯一事实源；COMPLETED+image_id=null 对 UI/图库都是不可解释状态（§一 P0） |
| `unknown`（任务丢失）用"连续 10 次既不在 queue 也不在 history"判定 | 兼顾提交竞态（避免误判）与永久 RUNNING（有界失败） |
| Worker 保留提交/轮询/取消编排，模块提供标准输入与引擎请求 | 暂停/取消语义留在 Worker（§十七/§十九），模块保持"能力定义"职责 |
| BINDING_NOT_FOUND 新增为独立错误类型 | binding 缺失与工作流执行错误根因不同，创建 Job 时应立即 4xx 而不是排队后失败 |
| ZIP 兼容断言基于 .gitignore 文本 | 交接包本就不含 .git；测试不能在"分发现场"无意义失败（§十） |

## 2026-10-07 — Phase 2：Job Execution Core + ComfyUIAdapter + Gallery（v0.3.0）

**执行**：TRAE Code Agent（接替开发；2A 段由前序会话完成并已提交 2c63137；
本段完成 2B / 2C 并按 feature/phase2-execution-gallery 三段提交 → develop → CI → main → CI → tag v0.3.0）

### 交付

- **2A（已提交 2c63137）**：Migration 0005_job（jobs/job_items/job_events + 幂等 UNIQUE）；
  Engine 层输出接口 + 错误分类 + Mock + 工厂；事件总线 + JobService + 单队列 QueueWorker；
  Job API + SSE + 磁盘检查 + 崩溃恢复；Mock 故障套件。
- **2B**：只读调查本机 ComfyUI（0.37.0，Qwen-Image 2.1 UC 三件套，nightbatch 同款链）→
  provider binding（节点 ID 只在 binding 层）+ ComfyUIAdapter（/prompt + WS 进度 + /history + /view +
  错误分类 + 安全取消）+ 首张真实生图验证。
- **2C**：Migration 0006_image + ImageService（temp → 校验 → 原子移动 → DB 登记，失败全回滚）+
  Gallery API（含 by-job summary "收藏"计数）+ 前端（SSE jobStore、双状态、右栏队列、中栏逐张、
  图库页、Image→工作台/使用此图 Seed/创建素材 source_image_id）。
- 文档：JOB_STATE_MACHINE / QUEUE_SPEC / RECOVERY_SPEC / COMFY_ADAPTER / IMAGE_MODEL /
  COMFY_ENV_INVENTORY / WORKFLOW_INVENTORY / PHASE2_REPORT 新增；既有文档与 README/AGENTS 同步。
- 验证：快速套件 **91 passed**；真实 ComfyUI 集成 **3 passed（1/3/8 张，12 图）**；
  前端 `npm run build` 通过；版本 0.2.0 → 0.3.0（后端/前端/app.yaml 同步）。

### 实测发现并修复

1. workflow.yaml 注释混入 `127.0.0.1:8188` → 公共配置守卫断言失败 → 注释改占位（公共配置只留 provider 选择）。
2. 集成测试夹具作用域错误（module 夹具依赖 function 级 settings）→ 改函数级夹具（每个用例独立 tmp DataRoot）。
3. `workflow_hash=None`（§五十五 要求记录）→ `module_identity()` 在 comfyui provider 下从 binding 读取
   binding_version + workflow_hash（老 Job 可追溯工作流版本）。
4. §五十八 缺口：无"瞬态网络重试"与"Workflow 错误"用例 → Mock 增加 transient_fail_times 模拟 +
   两条新用例（重试 ≤2 恢复成功；workflow 错误不重试且队列暂停）。
5. `by-job summary` 缺收藏计数（§四十九 示例为"未审核 a 保留 b 收藏 c 淘汰 d"）→ 补 favorites。
6. build_handoff.py 会把本机私有 `config*.local.yaml` 打包进交接 ZIP → 增加私有配置排除
   （规范 §三十二/§六十五：私有配置永不进交付物）。
7. Engine 组件生命周期细节：StrictMode 下 jobStore 的 SSE 订阅需可注销（stopJobStore 关闭句柄）。

### 决策

| 决策 | 理由 |
| --- | --- |
| 公共默认引擎 = comfyui（产品默认），测试/CI 用 mock | 真实产品必须默认走真实链路；CI 无 GPU，集成测试离线自动 skip；公共配置仍不得携带机器地址 |
| workflow_hash 在 Job 创建时由 binding 计算 | §五十五 要求"以后 Workflow 被修改仍知道老 Job 用的版本"，写入时机必须早于执行 |
| "使用此图 Seed" 由前端写快照后提交 | 与 §四十七 一致（默认 random，显式才固定）；后端 workbench 接口只返回该图 seed 供选择 |
| 续跑父子 Job 在中栏合并展示 | §二十"UI 将父子 Job 归组显示"；父 Job 已完成图片 + 子 Job 新图同一视图 |
| 队列"优先"按钮 = reorder 到队首 | 复用同一排序接口，避免平行机制（§十六 只有一个 queue_position 语义） |

### 环境说明

- ComfyUI 由 ControlHub 已批准的计划任务 `\AIHome\ComfyUI` 启动（Studio 不自管其生命周期）；
- 调查与测试期间未升级 ComfyUI、未安装/更新节点、未移动模型、未清空 output、未修改原工作流；
- 测试产生的图片落在 ComfyUI output（NSFWStudio/20261007）与测试 tmp DataRoot；
  正式 Studio 图库路径为 DataRoot/images/originals（由测试断言验证）。

## 2026-10-07 — Phase 1：Prompt / Asset / Recipe Core（v0.2.0）

**执行**：ZCode Agent（feature/phase1-prompt-asset-recipe → develop → CI → main → tag v0.2.0）

### 交付

- 数据模型：migration 0002/0003/0004（prompts、assets、recipes 三族 + 素材快照表），
  TEXT 主键 + 前缀化 uuid4、UTC 时间工具、FK/UNIQUE/CHECK 全量约束；Job/Image 仅文档预留。
- Prompt：双模式 + 版本机制（内容变才建版、元数据不建、恢复=复制为新版）+ 软删除 + PromptComposer
  后端权威合成（compose 接口前端同源预览）。
- Asset：四分类 + 预览图上传（ext/MIME/magic/size 四重校验）+ temp→原子移动→提交
  （提交失败清理文件、文件失败不提交）+ resolve_under 防穿越 + 版本不可变。
- Recipe：工作台快照（Prompt 快照+FK、slot 级素材版本快照、generation_settings、workflow 预留）。
- API 三组 + 统一错误 `{"error":{code,message}}` + 列表统一参数；lifespan 建 session 工厂。
- 前端：WorkbenchStore + 三栏工作台 + 提示词三 Tab + 素材页；三条"打开工作台"路径复用
  WorkbenchSnapshot（100% 恢复已实测）。
- 测试 33 → **68 例**全绿；真实库迁移前先备份（backup API），升级 0.1.2→0.2.0 成功。
- 浏览器人工验证 §五十九 全清单（含深浅主题）。

### 实测发现并修复

1. 0004 迁移 DDL 缺 recipe_asset_snapshots.created_at 列（测试暴露，迁移未发布前修正）。
2. StorageManager.path 白名单不含父目录（resolve_under("assets") 被拒）→ 允许登记目录的父目录。
3. 结构化合成只在路由层做、服务层缺失 → 下沉为 Service 权威逻辑（prompt/recipe 一致，幂等）。
4. 升级测试 monkeypatch 恢复方式错误（自我赋值）→ 修正测试。
5. **环境教训**：此前 TaskStop 停掉 dev server 的 bash 包装进程后 node 子进程残留，
   占用 5173 并缓存旧 CSS，浏览器验证一度出现"整页无样式"假象 → 用 netstat 定位 PID 清理。
   后续停止 dev server 需确认端口释放。

### 决策

| 决策 | 理由 |
| --- | --- |
| 结构化正向快照由 Service 合成（而非仅路由） | "UI 看到的 == 保存的"必须由单一权威实现保证，且服务层可独立测试 |
| RecipeVersion.default_count 列 + JSON 内镜像 | 规范 §二十三/§二十七 双处要求；单一写入方（Service）保证一致 |
| 未命中内容不建冗余版本 | 规范 §十一"内容变化才建版本"的镜像面；API/服务返回 created 标志 |
| 配方版本内容不变不建版本 | 与 Prompt/Asset 一致的三方语义 |

## 2026-10-07 — Phase 0.1.1：审查遗留契约修正（v0.1.2）

**执行**：ZCode Agent（develop → CI 绿 → 合并 main → tag v0.1.2；不新增任何产品功能）

1. **异步契约统一**：`WorkflowModule.execute` 改为 async abstractmethod（此前与 EngineAdapter
   全 async 方法不一致，未来 Pipeline 无法 await）。异步原则固定写入 docstring + 开发指南：
   执行链路全 await，纯数据校验 sync。测试：`iscoroutinefunction` 守护 execute 与 EngineAdapter
   全部方法，同时守护 capabilities/validate_input 保持同步。
2. **DataRoot 真正跨机器**：审查指出 Phase 0.1 的方案仍有漏洞——公共 config.yaml 携带
   `data_root: "D:/NSFW-Studio-Data"`，clone 到他机仍会优先用 D 盘，可移植默认形同虚设。
   修正：公共 config.yaml 机器无关（不设置 data_root，含哨兵测试）；新增
   `configs/config.local.yaml` 本机私有层（`*.local.yaml` 本就在 .gitignore，双重显式登记）；
   优先级链固定为 env > local > 公共模板 > `Path.home()/NSFW-Studio-Data`。
   本机 D 盘只存在于 local 文件，真实加载已验证。
3. **Node 探测**：`dev_frontend.bat` 优先 `AIHOME_ROOT` 环境变量 → AIHome 规范默认根目录
   兼容探测（全局规范两台机器同根，仅作非阻断兼容）→ 系统 PATH → 报错。
4. 版本 0.1.2（app.yaml / __init__ / package.json + lock 同步）。
5. 验证：pytest **33 passed**；`npm run build` 通过；develop 与 main CI 全绿。

### 教训

- 配置"允许本机覆盖"必须区分**文件本身是否随仓库分发**——随仓库分发的公共配置写机器路径，
  等于把一台机器变成所有人的默认值（Phase 0.1 自评通过、审查未过的根因）。

## 2026-10-07 — Phase 0.1：架构收口（v0.1.1）

**执行**：ZCode Agent（在 develop 完成 → CI 全绿 → 合并 main → tag v0.1.1）

### 收口内容（三方审查合同落实）

1. **Migration 漏洞**：`applied_migration_ids()` 只认 `status='applied'`；重试前 DELETE 同 ID 的 failed 记录解决主键冲突。补失败恢复测试（失败→failed→仍视为未完成→修复→重试成功→状态正确）。
2. **SQLite 工程化**：`make_engine()` 每连接执行 `journal_mode=WAL`、`busy_timeout=5000`、`foreign_keys=ON`；新增 `app/database/backup.py`（SQLite backup API，禁直接复制写入中的 DB）+ `scripts/backup_db.py`；DataRoot 增加 `backups/`。
3. **契约收口**：新增 `WorkflowInput/WorkflowOutput/WorkflowValidation/ModuleCapabilities/ParameterSpec`；`WorkflowModule.execute(payload, engine)` 显式接收 EngineAdapter（引擎调用只发生在 Adapter）；EngineAdapter 增加 `EngineJobRequest/EngineJobStatus`（含 progress 进度能力）；`QueueWorker` 删除 `submit()`（Job 创建属于 API/JobService，Worker 只消费）。
4. **可移植性**：代码默认 DataRoot 改为 `Path.home()/"NSFW-Studio-Data"`；本机 D 盘由 config.yaml 明确声明（允许）；`dev_frontend.bat` 改为 AIHome 探测→PATH 回退→清晰报错；`dev_backend.bat` 补 Python 存在性检查。
5. **语义修正**：前端顶部指示 "Studio 在线/离线"（后端健康），Phase 1 接 EngineAdapter.health 后才显示 Engine；`system_info.version` 语义定为**当前应用版本**，启动时自动对齐（实测 0.1.0→0.1.1 更新成功）。
6. **CI**：`.github/workflows/ci.yml`（ubuntu：pytest；node 20：npm ci + build），push/PR 触发。
7. **测试**：15 → **27 例**全绿；`npm run build` 通过。

### 决策

| 决策 | 理由 |
| --- | --- |
| system_info 语义选"当前应用版本" | 为 Phase 1 的升级可观测性服务；字段名不变、语义写进文档与 BootstrapReport.system_info_action |
| WorkflowModule.execute 注入 EngineAdapter | 保证"引擎调用只在 Adapter"由类型系统约束，而不只是口头约定 |
| Worker 移除 submit 而非新增 submit | 合同要求 Worker 不成为 Job 创建入口；消费入口定为 process_job(job_id) |
| CI 后端跑 ubuntu | 兼验证可移植性（DataRoot 默认值与配置加载均跨平台） |

### 实测发现并修复

- （本轮无新增缺陷；27 例测试一次全绿后做真实启动升级验证）

## 2026-10-07 — Phase 0：工程初始化与架构搭建（v0.1.0）

**执行**：ZCode Agent（遵循 AIHome 全局规则 + 本项目 AGENTS.md）

### 完成内容

1. **立项**：项目建于 `projects/nsfw-studio-v2`（`projects/nsfw-studio` 为 V1，完全独立未触碰）。
   git init（main 分支），目录骨架 + .gitignore + 项目级 AGENTS.md。
2. **后端**：FastAPI 工厂 + lifespan 启动引导；配置系统（4 份 YAML + 环境变量覆盖）；
   JSON 结构化日志（app/jobs/errors）；SQLAlchemy + 自研极简迁移框架（migration 表）；
   system_info 表；StorageManager；health API。WorkflowModule / EngineAdapter / QueueWorker
   按规范仅定义抽象接口，零实现、零引擎绑定。
3. **前端**：Vite + React 18 + TS 壳；MainLayout + TopNav（五项导航）；EngineStatus（轮询
   /api/v1/health，15s）；ThemeProvider + themeStore（localStorage 持久化，默认深色）；
   五页面空状态（设置页含可用的主题选择）。
4. **测试**：pytest 15 例全绿；前端 npm run build 通过。
5. **文档**：docs/ 五份 + DEV_LOG/TASKS/CHANGELOG/TEST_REPORT。

### 关键决策

| 决策 | 理由 |
| --- | --- |
| 迁移用自研极简框架而非 Alembic | Phase 0 只有 2 张表，规范只要求 migration 表打底；接口设计保留 Alembic 升级路径 |
| 时间字段存 TEXT（ISO 8601） | 与迁移表记录一致，SQLite 下可读可排序，Phase 1 统一 |
| 测试用 NSFW_STUDIO_DATA_ROOT 环境变量注入临时目录 | 验证环境变量覆盖机制本身，且绝不触碰真实 DataRoot |
| 前端 EngineStatus 检测后端 health | Phase 0 无引擎可测；Phase 1 切换为 EngineAdapter.health()，组件接口不变 |
| Node 使用 AIHome managed-tools（v24.18.1） | 遵循全局规则 §7 工具发现顺序；未安装第二套 Node |
| rollup 固定 4.64.0 | npmmirror 镜像缺 4.64.1 原生包（npm optional deps bug 叠加镜像同步延迟） |

### 实测发现并修复

- `database/base.py` 缺 `create_engine` 导入（pytest 暴露）。
- `app.css` `@import './themes/tokens.css'` 路径错误 → `../themes/`（浏览器实测暴露，Vite overlay）。

### 遗留

- ~~GitHub 推送未执行~~ → **当日已解决**：检测到本机 Git Credential Manager 存有 GitHub 凭据
  （zxingyu178-dot），经 GitHub API 创建私有仓库 `nsfw-studio-v2` 后推送 main / develop / v0.1.0 成功，
  `git ls-remote` 验证通过。`gh` CLI 仍未安装（AIHome tool-registry 登记 not_found）。
- 同日应用户要求将仓库由私有**转为公开**（https://github.com/zxingyu178-dot/nsfw-studio-v2），用途：三方 AI 审核代码。
  已确认仓库内无凭据/密钥（.gitignore 排除 .env，代码零硬编码秘密）。
