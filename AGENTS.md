# NSFW Studio V2 项目规则

> 本规则服从 `D:\AIHome_2.0_L1_L2\AGENTS.md`（全局规则），只做更严格的补充，不做削弱。

## 1. 项目身份

- 项目 ID：`nsfw-studio-v2`，位于 `D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2`。
- 与旧项目 `projects/nsfw-studio`（V1）**完全独立**：未经当前任务明确要求，禁止读取、修改、复制或覆盖 V1 的任何内容。

## 2. 技术栈声明

- 后端：Python 3.11 + FastAPI + SQLAlchemy 2 + SQLite。
- 前端：React 18 + TypeScript + Vite 5。
- 用户界面语言：中文；代码标识符 / API 字段：英文。
- 不得擅自替换以上技术栈。

## 3. 阶段纪律（当前 Phase 5 完成，v0.6.0）

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
Gallery Picker / 导入进度 / 审图快捷键 + Ctrl+Z 撤销；**真实图片条件工作流 = Gate B 暂停**）。

**Phase 5 能力 Gate（当前生效）**：本机无现成可用图片条件工作流（见
`docs/IMAGE_CONDITIONING_INVENTORY.md`）；真实 Img2Img / Reference Module 接入**等待用户选择方案**
（Phase 5.1），禁止自行下载模型 / 安装节点 / 升级 ComfyUI；前端图片生成模式在无可用模块时
显示"尚未配置可用工作流"并禁用提交（Gate 判定以 `GET /api/v1/modules` 为准，禁止前端硬编码）。

本阶段仍禁止扩大范围实现：

- 真实图生图 / 参考图模型接入（Gate B：待用户选定方案）/ ControlNet / FaceID / InstantID /
  局部重绘 / 蒙版编辑器 / 视频；
- 手机端 / 豆包正式接入 / Agent 正式接入 / 全局搜索；
- 多 GPU / 多 Worker / 多队列（系统永远只有一个逻辑队列 + 一个 Worker）。

生成链路约束：

- 执行链路：Workbench → `POST /api/v1/jobs`（JobService 固化快照并物化 JobStage）→
  单队列 Worker → Stage 顺序执行（Stage Gate：前一 Stage 全部完成才进下一 Stage）→
  WorkflowModule → EngineAdapter → ComfyUI → Image（导入 DataRoot）→ Gallery；
- 前端绝不直连 ComfyUI；Job 创建只发生在 `JobService`，Worker 只消费已持久化 Job；
- **执行真源 = JobStage + workflow_snapshot**（§二十三）：Job 创建后当前配置变化不影响该 Job，
  Resume 完整继承原 Stage/Binding，禁止静默升级；
- ComfyUI 节点 ID / Workflow JSON 只存在于 `workflows/providers/comfyui/<module>/<binding>/` 层，
  禁止污染引擎无关层；**已投入使用的 binding 目录视为 immutable**（workflow.json / binding.yaml 改动
  必须新建 v2；workflow_hash / binding_hash 双指纹不一致会被拒绝执行）；
  处理型模块的输入图片只走 `EngineAdapter.upload_input_image()` 正式契约（禁止 getattr duck typing）；
- 绑定属于每次请求：QueueWorker / ComfyUIAdapter 不得固化单一模块身份（§0.2/§二十二），
  新增模块（img2img 等）只注册 WorkflowModule + 新增 binding 目录，核心执行逻辑零改动；
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

- `scripts/` 下的长期脚本（dev_backend / dev_frontend / init_dataroot / backup_db / build_handoff）
  已登记至 AIHome Registry；修改前先确认调用方。
- 本项目不新增任何长期运行服务；dev server 均为手动临时启动，不接入 ControlHub。

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
