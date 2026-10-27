# NSFW Studio V2 项目规则

> 本规则服从 `D:\AIHome_2.0_L1_L2\AGENTS.md`（全局规则），只做更严格的补充，不做削弱。

## 0. AI 快速操作卡：启动生图（用户说「查看 nsfwv2 项目，帮我启动生图」时先看这里）

**不要自己写 uvicorn / npm 启动链，不要换端口。** 唯一生产链已固定，照下面执行即可。

固定事实：

- 日常生图实例（部署实例）：`projects\nsfw-studio-v2-app`，分支 `deploy/app-instance`（跟踪 `origin/main`）。
- 唯一启动链：桌面「NSFW Studio」→ `scripts\launch_studio_hidden.vbs` → `scripts\launch_studio.ps1` → ControlHub lifecycle CLI。
- 端口：Studio `127.0.0.1:8000`、ComfyUI `8188`、Mobile Review `8767`（随 Studio 退出）。
- 业务数据：DataRoot `D:\NSFW-Studio-Data`（提示词 / 图片 / 人脸库 / 数据库）；工作流目录不含数据。
- 当前工作流：`basic_generate/v1` 含 turbo8 LoRA，采样 8 步（binding `defaults."6".steps`）。

步骤（在 `projects\nsfw-studio-v2-app` 下执行）：

1. **查现状**（只读，先看再动）：
   `Invoke-RestMethod http://127.0.0.1:8000/api/v1/health`
   `Invoke-RestMethod http://127.0.0.1:8000/api/v1/engine/status`
   `Invoke-RestMethod http://127.0.0.1:8188/system_stats`
2. **启动 Studio**：`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\launch_studio.ps1`
   - 已在运行 → 只打开浏览器，**不要重复起进程**；端口被非 Studio 占用 → 脚本会报 PID 并退出 3。
3. **启动 ComfyUI（8188 未在线时）**，二选一：
   - 首选：`Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/engine/runtime/start -TimeoutSec 300`
     （UI 里「启动生图引擎」按钮调用同一接口，只作用于 comfyui）；停止/重启把末段换成 `stop` / `restart`。
   - 备选（Studio 也离线、或 API 无响应时）：`. scripts\runtime\resolve_aihome.ps1`
     `& $AIHOME_ENV.CONTROLHUB_PYTHON -m control_hub.lifecycle_cli start comfyui --data-root $AIHOME_ENV.CONTROLHUB_DATA_ROOT`
   - **冷启动可能耗时数分钟（加载模型），必须轮询 `/system_stats` 直到返回，不要用 30 秒级短超时误判失败。**
4. **确认可生图**：`/api/v1/health` 正常；`GET /api/v1/modules` 中目标模块 `available=true`；
   ComfyUI `/system_stats` 可访问。
5. **队列若处于暂停**（历史 `WORKFLOW_HASH_MISMATCH` / 手动暂停会留下暂停态）：
   `Invoke-RestMethod -Method Post http://127.0.0.1:8000/api/v1/queue/resume`
   - 需要续跑被中断的旧任务时：`POST /api/v1/jobs/resume-interrupted`；
     返回的 `skipped[].reason=WORKFLOW_CHANGED` 表示该任务的工作流指纹已过期（工作流改版后不可续跑），
     **不要反复重试**，改用 `POST /api/v1/queue/clear-stale` 归档后再按新工作流重新生成。
6. **生图**：`.venv\Scripts\python scripts\agent_generate.py --module basic_generate --prompt "…" --out D:\ai_out`
   （`anime_generate` 用于动漫；`agent/jobs` 端点默认关闭，优先用本机 CLI）
7. **停止**：`powershell -NoProfile -ExecutionPolicy Bypass -File scripts\stop_studio.ps1`
   （依次暂停队列 → 停 Bridge → 停 Studio → 停 ComfyUI，并核验端口；桌面「NSFW Studio · 停止」等价）

红线：禁止手工 `uvicorn` 占 8000；禁止 8001/8002 自动换口；禁止前端直连 ComfyUI 建 Job；
禁止在 `basic_generate/v1` 之外再建同模块目录（版本靠 git 历史）。

详细生图与编码避坑：`docs/AI_IMAGE_GENERATION_GUIDE.md`；Agent 接入安全：`docs/AGENT_SUBMISSION.md`。

## 1. 项目身份

- 项目 ID：`nsfw-studio-v2`，位于 `D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2`。
- 与旧项目 `projects/nsfw-studio`（V1）**完全独立**：未经当前任务明确要求，禁止读取、修改、复制或覆盖 V1 的任何内容。

## 2. 技术栈声明

- 后端：Python 3.11 + FastAPI + SQLAlchemy 2 + SQLite。
- 前端：React 18 + TypeScript + Vite 5。
- 用户界面语言：中文；代码标识符 / API 字段：英文。
- 不得擅自替换以上技术栈。

## 3. 阶段纪律（当前 v0.36.1，2026-10-27）

**当前状态**：v0.36.1（2026-10-27）= `basic_generate` 工作流正式纳入 turbo8 LoRA 链并把采样
默认改为 8 步；功能基线沿用 v0.36.0（重启/更新后「一键继续全部中断任务」）、v0.35.0（图库
删除入口 +「我的 Prompt」整行列表 + 列表 gzip/预热性能）与 v0.16.0 Anima 动漫模块。

**工作流版本策略（2026-10-27 用户确认，方案 A：单目录）**：
`workflows/providers/comfyui/basic_generate/v1/` 是唯一目录，不新建 v2。workflow.json 内含
`qwen_image_2.1_turbo8_lora` + `f23gg_nsfw_qwen21` 两个 LoraLoader；采样步数由 binding 的
`defaults."6".steps = 8` 决定（binding defaults 覆盖 workflow 节点值）。版本演进靠 git 历史，
不再按目录分版本；代价是历史 Job 的 workflow_hash/binding_hash 不再匹配，旧任务不可续跑。

**历史基线 v0.16.0**：Anima 动漫生图模块上线（从 v0.9.0 归档分支移植到 v0.15.1 基线，
`anime_generate` + `comfyui/anime_generate/v1` binding，核心执行逻辑零改动）。
基线 v0.15.1 = Workbench Layout 4.0（Canvas First 三栏 + TaskDock）、真实进度
（Job / Stage / Step）、可视化 Prompt 库、Glass 设计体系；后端进度事件分流为瞬态 SSE 与
持久 `job_events`，`EngineJobStatus` 透传 `step/max_step`，采样 stall 与执行总超时分离；
Canvas 逻辑尺寸 / Fit / 100%、多阶段 progress 按 `stage_item_id` 分键、完整 resume family、
SSE 签名去重 + 心跳节流、review 动作 per-image 串行化。5 个正式 WorkflowModule：
`basic_generate` / `anime_generate` / `img2img` / `reference_generate` / `upscale`。
生产生命周期交 ControlHub official lifecycle CLI（`nsfw-studio-v2`=8000、`comfyui`=8188），
部署/日用实例为 `projects/nsfw-studio-v2-app`（分支 `deploy/app-instance`，跟踪 `origin/main`）。
逐版真相 = `CHANGELOG.md`；发布报告 = `docs/release/`、`docs/phase011/`。
Anima 已上线：动漫/插画请用 `anime_generate`（官方说明写实主体表现差），写实继续用
`basic_generate`；归档分支 `archive/anime-module-v0.9.1` 仅作历史证据保留。

以下为历史阶段（Phase 0 → 7，v0.1.0–v0.9.0）记录：

已完成 Phase 0 / 0.1 / 0.1.1 / 1（Prompt-Asset-Recipe Core）/
2（Job Execution Core + ComfyUIAdapter + Gallery）/
2.1 / 2.2（执行稳定性与数据一致性收口）/
3（Multi-stage Pipeline + Upscale：JobStage/JobStageItem、Stage Gate、UpscaleModule、
图库高清 process Job、Image 父子关系）/
4（History + Provenance + Generic Module I/O Contract：0008 历史 Stage 回填、
binding_hash 双指纹、能力驱动 I/O、StageItem Seed、输入图片正式契约、历史页、溯源、
工作台追溯根生成 Job、执行身份固定恢复）/
5（Image Input Foundation + Capability Gate：0010 迁移、外部图片导入 + sha256 去重、
工作台输入图片 / 文生图-图片生成模式、Recipe 输入图快照、Job 冻结输入图、
Face Asset Reference Image 关系表、ImageReferenceService、模块 input_required/input_role、
Gallery Picker / 导入进度 / 审图快捷键 + Ctrl+Z 撤销）/
5.1（Image Pipeline Contract Closure + Qwen Img2Img：WorkflowModuleRef 正式类型化、
Recipe 完整 Workflow 身份（不丢 provider/双 hash）、config 单链唯一事实源、
PipelineValidator（UNUSED_INPUT_IMAGE / INPUT_IMAGE_REQUIRED / 链式校验）、
工作台模式绑定 Primary Module、`/modules` 真实可用性（registered ≠ available）、
Face 参考图 clear 语义、0011 导入 sha256 部分唯一索引；**Img2ImgModule 正式落地**
（Qwen-Image 2.1 零下载 latent Img2Img，img2img/v1 binding，Gate C 成功，v0.7.0））/
6（Pipeline 可靠性收口：Image→Workbench 最近生成上下文（不再找树根）、前端工作流身份完整保留、
Recipe 固定 Seed 归一化、移除执行重排 + PIPELINE_DUPLICATE_MODULE、未注册 module_version
创建期拒绝、availability 版本域修正、Img2Img execute Prompt 契约、generation_mode 显式化、
ParameterSpec 元数据驱动 + size_mode、真实照片验收（默认 denoise 0.55→0.8）与浏览器全链路，v0.8.0）。

**v0.16.0 当前能力**：5 个 WorkflowModule（`basic_generate` 文生图 / `anime_generate` 动漫生图 /
`img2img` 图生图 / `reference_generate` 参考图 / `upscale` 高清），`GET /api/v1/modules` 返回能力与
ParameterSpec + `size_mode`，`available=true` 是前端 Gate 唯一依据；
`WorkbenchSnapshot.generation_mode`（text|image）显式保存与恢复；文生图 / 动漫 / 图片生成 / 高清 /
参考图可组合为合法链；Job/Stage/Step 真实进度经 SSE + `job_events` 双通道对外。

仍禁止扩大范围实现：

- 扩展参考能力：IPAdapter 类、ControlNet、FaceID、InstantID、局部重绘、蒙版编辑器、视频；
- 豆包正式接入 / Agent 正式接入 / 全局搜索；
- 手机端 App（局域网 Mobile Review Bridge 8767 是既有子运行时，不扩展为新端）；
- 多 GPU / 多 Worker / 多队列（系统永远只有一个逻辑队列 + 一个 Worker）。

生成链路约束：

- 执行链路：Workbench → `POST /api/v1/jobs`（JobService 固化快照 + PipelineValidator 校验 +
  物化 JobStage）→ 单队列 Worker → Stage 顺序执行（Stage Gate：前一 Stage 全部完成才进下一 Stage）→
  WorkflowModule → EngineAdapter → ComfyUI → Image（导入 DataRoot）→ Gallery；
- 前端绝不直连 ComfyUI；Job 创建只发生在 `JobService`，Worker 只消费已持久化 Job；
- **执行真源 = JobStage + workflow_snapshot**（§二十三）：Job 创建后当前配置变化不影响该 Job，
  Resume 完整继承原 Stage/Binding，禁止静默升级；
- **模块 config 单链（Phase 5.1）**：`Workbench.workflow_modules[].config` →
  `Recipe.workflow_snapshot` → `Job.workflow_snapshot` → `JobStage.config_json`；
  禁止另建第二事实源（`stage_configs` 仅保留为内部/测试直调路径）；
- **输入图片不得被静默忽略（Phase 5.1）**：Job 创建前由 `PipelineValidator` 依据
  ModuleCapabilities 校验（`input_required=false` 携带输入图 → UNUSED_INPUT_IMAGE；
  需要输入图却没给 → INPUT_IMAGE_REQUIRED；Stage N 必须能接收 Stage N-1 输出）；
  **禁止把这些判断写进 QueueWorker**；
- ComfyUI 节点 ID / Workflow JSON 只存在于 `workflows/providers/comfyui/<module>/<binding>/` 层，
  禁止污染引擎无关层；**已投入使用的 binding 目录视为 immutable**（workflow.json / binding.yaml 改动
  必须新建 v2；workflow_hash / binding_hash 双指纹不一致会被拒绝执行）；
  处理型模块的输入图片只走 `EngineAdapter.upload_input_image()` 正式契约（禁止 getattr duck typing）；
- 绑定属于每次请求：QueueWorker / ComfyUIAdapter 不得固化单一模块身份（§0.2/§二十二），
  新增模块（reference 等）只注册 WorkflowModule + 新增 binding 目录，核心执行逻辑零改动；
- 机器信息（ComfyUI URL / 安装路径 / 输出路径）只进 `configs/config.local.yaml`（gitignore）
  或环境变量；公共配置不得出现 `127.0.0.1` / `localhost`（守卫测试会失败）；
- 错误分类 / 重试 / 恢复语义见 `docs/JOB_STATE_MACHINE.md`、`PIPELINE_STATE_MACHINE.md`、
  `QUEUE_SPEC.md`、`RECOVERY_SPEC.md`，修改状态机前必须先同步文档。

数据纪律（Phase 1 起生效）：

- 业务对象 ID 一律 `<前缀>_<uuid4>`（TEXT 主键）；业务时间一律 UTC ISO 8601（`core/timeutil.py`）；
- Version 表 immutable：只 INSERT 不 UPDATE；恢复旧版本 = 复制为新最新版；
- 软删除：普通 UI 禁止物理删除（archived 标记）；
- 文件路径入库只存 DataRoot 相对路径；结构化 Prompt 合成以后端 PromptComposer 为权威。

## 4. 架构红线

- `api/` 只做 HTTP 编排，业务逻辑一律放 `services/`。
- 路径可移植性（Phase 0.1 / 0.1.1）：配置优先级固定为
  `NSFW_STUDIO_DATA_ROOT` > `configs/config.local.yaml`（本机私有，已 gitignore，禁止提交）
  > `configs/config.yaml`（公共模板，**机器无关，不得设置 data_root**）> 代码默认 `%USERPROFILE%/NSFW-Studio-Data`；
  禁止把某台机器的盘符写进公共配置或代码默认值；启动脚本必须自带回退与清晰报错。
- 流水线契约：`Pipeline → WorkflowModule → EngineAdapter → 具体引擎`。
  WorkflowModule 只做能力定义（标准契约类型 WorkflowInput / WorkflowOutput /
  WorkflowValidation / ModuleCapabilities），真正的引擎调用只发生在 EngineAdapter 实现；
  Worker 只消费已存在的 Job，Job 的创建与持久化属于 API / JobService。
- 顶部状态指示是两个独立状态（Phase 2 起）：**Studio ●**（后端 `/health`）与
  **Engine ●**（`/api/v1/engine/status` → EngineAdapter.health()，如本机 ComfyUI）；
  禁止用一个圆点混淆两者。
- 运行数据（数据库 / 图片 / 日志 / 备份）只放 DataRoot，禁止提交进仓库。
  数据库备份必须走 SQLite backup API（`app/database/backup.py`），禁止直接复制写入中的 DB 文件。
- 前端 `api/` 只封装后端 HTTP 调用；新增扩展不改核心。

## 5. 脚本与登记

- `scripts/` 下的长期脚本（dev_backend / dev_frontend / init_dataroot / backup_db / build_handoff /
  launch / stop 等）已登记至 AIHome Registry；修改前先确认调用方。
- **生产运行时接入 ControlHub**（v0.14 起）：`nsfw-studio-v2`(8000) 与 `comfyui`(8188) 是
  独立已批准对象，生命周期只走官方 lifecycle CLI（`python -m control_hub.lifecycle_cli start|stop <id>
  --data-root <controlhub-data>`）；应用内「启动/停止生图引擎」只作用于 `comfyui`，
  **绝不**对 `nsfw-studio-v2` 执行 start/stop。8767 Mobile Review Bridge 是随 Studio 退出的
  子运行时，不是独立 ControlHub 对象。
- 部署/日用实例 = `projects/nsfw-studio-v2-app`（worktree，分支 `deploy/app-instance`
  跟踪 `origin/main`）；开发主工作树 = `projects/nsfw-studio-v2`（main/develop）。
  两者都不得提交 DataRoot、`.venv`、`frontend/dist`、`configs/config.local.yaml`。
- 部署实例发布 = `git pull` + `scripts/deploy_app_dist.ps1`；禁止只 pull 不构建、不同步
  gitignored 的 `frontend/dist`。发布后运行 `scripts/check_app_dist.ps1` 做只读一致性检查。

## 6. 验证要求

- 改后端：必须在项目根目录跑 `.venv\Scripts\python -m pytest`，全绿才算完成。
- 改前端：必须 `npm run build` 通过。
- GitHub CI（.github/workflows/ci.yml）在 push / PR 时自动运行 pytest 与前端构建；
  **main / develop 上的提交必须 CI 全绿**，不允许只依赖某台电脑"本地说能跑"。
- 汇报遵循全局规则第 10 条：未执行 / 部分验证必须如实标注。

## 7. Git

- 分支：`main`、`develop`；功能 `feature/xxx`；修复 `fix/xxx`。
- 每个阶段在 `develop` 完成、测试通过后合并回 `main` 并保持两分支一致。
- Commit 用 conventional 前缀（feat / fix / docs / chore / test）。
- 禁止把 DataRoot 数据、`node_modules`、`.venv`、交接包提交进仓库。

## 8. Codex 子智能体分工（用户指令 2026-10-20）

> 用户明确要求：「多调用 codex 干活」。默认把可独立完成的工作交给 Codex 子智能体，
> Lead（主智能体）负责拆分任务、审查 diff、跑验证、提交与发布。

- **常规任务** → `subagent_codex_lite`（`gpt-5.6-sol`，medium 思考）。适用于：后端服务/测试、
  前端组件与样式、文档整理、refactor、CI 修复等边界清楚的任务。
- **复杂任务** → `subagent_codex`（`gpt-6-astra`，**medium 思考强度**）。仅用于跨模块设计、
  难 bug、性能/并发等需要强推理的工作。Plus 会员有 5 小时额度，注意节省。
  astra 一律保持原生 `model_reasoning_effort=medium`，**禁止调高思考强度**（用户 2026-10-21 明确要求，
  否则额度很快用完）；任务本身也该拆小、给足上下文，避免长链思考。
- Codex 只改代码、不提交：禁止 `git commit / push / tag`，交付后由 Lead 审查并提交。
- **每次执行任务前先检查 Codex 额度（用户 2026-10-22 要求）**：先派一个最小空任务探测
  （例如 `subagent_codex_lite` 仅回复 `OK`，不读文件/不改代码）；成功则本轮优先用 Codex，
  返回 limit/失败则改用 Lead 执行，不得把大面积工作押在可能失败的派单上。探测任务必须极小，
  禁止用真实任务做额度探测。
- 派单必须写清：工作目录、允许改动的范围、验收标准（`pytest` / `vitest` / `tsc -b` / `npm run build`）、
  禁止事项（新增依赖、改技术栈、动 DataRoot、写 BOM、修改 `docs/DESIGN.md` 之外的设计约定）。
- 视觉任务必须遵守 `docs/DESIGN.md`；业务任务必须遵守本文件第 3/4 节架构红线。
- Lead 合入前必须：跑对应测试与构建、检查 diff 无越界、检查无 BOM、必要时截图验证 UI。
