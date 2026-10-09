# NSFW Studio V2

[![CI](https://github.com/zxingyu178-dot/nsfw-studio-v2/actions/workflows/ci.yml/badge.svg)](https://github.com/zxingyu178-dot/nsfw-studio-v2/actions/workflows/ci.yml)

本地 AI 图像生产平台（单机优先，Windows 本地运行，公司/家里经 GitHub 切换开发）。

**当前阶段：Phase 6 — Pipeline 可靠性收口（已完成，v0.8.0）。**
不扩模型，解决"能生成之后如何可靠继续编辑、可靠复现、可靠扩第四个 Module"：
Image → Workbench 生成上下文改为"距离最近的 generate 上下文"（import→img2img→upscale 恢复
Img2Img，Seed 用该图真实 Seed）；前端工作流身份完整保留（规范模块顺序，不再重建裸 upscale）；
Recipe 固定 Seed 归一化（"使用此图 Seed"可保存配方）；移除执行重排 + 重复模块拒绝
（`PIPELINE_DUPLICATE_MODULE`）+ 未注册 module_version 创建期拒绝；
`/modules` 返回参数 Schema（ParameterSpec：min/max/step/configurable/title）与 `size_mode`
（explicit|input），前端按 schema 渲染控件（denoise 滑杆不再硬编码）；`generation_mode`
（text|image）显式进入 Snapshot/Recipe/Job/History/Image restore；Img2Img 模式不显示假宽高，
History 显示"跟随输入图 W×H"；**Img2Img 默认 denoise 0.55 → 0.8**（真实照片实测：0.55≈精修
近乎不变，0.8 人物保留良好且场景级 Prompt 生效）；默认套件 227 passed + 前端 store 断言 11
（CI `test:store`）+ 真实照片 4 轮验收 + Playwright 浏览器全链路（证据
`docs/evidence/phase6-img2img/`，报告 `docs/PHASE6_REPORT.md`）。

**Phase 5.1（已完成，v0.7.0）**：契约收口——WorkflowModuleRef 正式类型化（module_id / module_version /
provider / binding_version / 双 hash / config，前后端镜像）、Recipe 保存完整 Workflow 身份
（不再丢失 provider / 双 hash，旧配方不会偷偷升级到新版 Workflow）、模块 config 单链
（Workbench → Recipe → Job.workflow_snapshot → JobStage.config_json 唯一事实源）、
PipelineValidator 统一校验（输入图片不得被静默忽略：`UNUSED_INPUT_IMAGE` /
`INPUT_IMAGE_REQUIRED` / 链式 output→input 检查，Job 创建期拒绝）、工作台模式与 Primary Module
真正绑定（文生图 = basic_generate；图片生成 = 可用图片条件模块）、`GET /api/v1/modules`
返回真实可用性（registered / available / unavailable_reason，Gate 依据 available=true）、
Face Asset 参考图可清除（`reference_action: inherit/set/clear`）、导入 sha256 部分唯一索引
（迁移 `0011`，并发 IntegrityError → 返回已存在图片而不是 500）。
零下载实验 → Gate C 成功：复用现有 Qwen-Image 2.1 三件套完成 latent Img2Img
真实实验（denoise 0.55 ≈ 保留输入结构 / 1.0 完全由 Prompt 驱动，无 OOM），正式落地
**Img2ImgModule**（第三套 WorkflowModule）+ provider binding `img2img/v1`
（LoadImage → VAEEncode → KSampler denoise → VAEDecode → SaveImage），输出
`kind=processed` + `parent_image_id=输入图`；核心调度（QueueWorker / PipelineScheduler /
ImageService）**零改动**。图库详情新增"以此图进行图生图"（有生成上下文恢复原 Prompt；
外部导入 Prompt 为空）。
Phase 5 已完成：外部图片导入正式产品化（`POST /api/v1/images/import`，PNG/JPG/JPEG/WEBP，
sha256 去重，批量部分失败继续，来源统一 `source=import`）、工作台"输入图片"（模式切换
[文生图]/[图片生成] + 图库 Picker / 上传即导入，`WorkbenchSnapshot.input_images` max=1）、
Recipe 输入图快照（image_id + hash + role；丢失显式标记）、Job 创建冻结输入图
（Stage0 StageItem.input_image_id）、Face Asset Reference Image（`asset_reference_images` 关系表，
仅人脸，来源=图库）、ImageReferenceService（删除前引用检查）、ModuleCapabilities
`input_required/input_role`、图库导入进度 / "用作输入图片" / 审图快捷键（←→/K/R/F + Ctrl+Z 撤销）。
Phase 4 已完成：历史正式可用（`GET /api/v1/history` + 历史 Tab：任务族归组 / 筛选 / Drawer）、
Image Provenance API（来源任务/Stage/模块/双指纹/Seed）、派生图 → 工作台追溯根生成 Job、
恢复路径携带完整执行身份并固定原版本、前端 WorkflowModuleRef[] 列表、
ModuleCapabilities I/O 契约、StageItem 真实 Seed、EngineAdapter `upload_input_image` 正式契约、
binding_hash 执行指纹、Studio Input Registry + TTL 清理；
P0 修复：`0008_pipeline_backfill`（历史 Job 回填 Stage，QUEUED 升级后仍可执行）+
`0009_execution_fingerprint`（binding_hash / StageItem.seed / 历史假 Seed 修正）。
Phase 3：多阶段管线（JobStage / JobStageItem，**生成 N 张原图全部完成后才进入高清放大**，
Stage Gate 严格门控）、第二个 WorkflowModule `upscale`（4x-UltraSharp 链，复用本机已验证资源）、
图库已有图片单独高清（upscale-only process Job，同一 Worker / 同一模块）、
Image 父子关系（高清 parent_image_id + images/upscaled 存储 + 图库切换）、
分阶段实时进度与 HD 标记、配方高清开关 100% 恢复。
Phase 1 已完成：Prompt（结构化八栏/完整双模式 + 版本历史 + 软删除）、素材（四分类 + 预览图上传 + 版本）、
配方（工作台快照 + 素材版本快照）、生成工作台三栏（保存/100% 恢复）。
Phase 2 已完成：Job / JobItem / 单队列 Worker（暂停 / 取消 / 续跑 / 幂等 / 崩溃恢复）、
SSE 任务事件、ComfyUIAdapter（真实对接本机 ComfyUI + provider binding）、
Image 导入 DataRoot + 图库（审核 / 收藏 / 按任务查看 / Image → 工作台 / 从图库创建素材）。
执行链路：Workbench → POST /jobs → 单队列 → Stage 顺序执行 → WorkflowModule → EngineAdapter →
ComfyUI → Image → Gallery。
本机 ComfyUI 环境事实见 `docs/COMFY_ENV_INVENTORY.md` / `docs/WORKFLOW_INVENTORY.md` /
`docs/UPSCALE_WORKFLOW_INVENTORY.md` / `docs/IMAGE_CONDITIONING_INVENTORY.md`；
Phase 5.1 起 Img2Img 已接入（Qwen-Image 2.1 latent Img2Img，见 `docs/PHASE51_REPORT.md`）；
仍禁止（后续阶段评估）：Reference（IPAdapter 类）/ ControlNet / FaceID / InstantID /
局部重绘 / 蒙版编辑器 / 视频 / 手机端 / 豆包正式接入 / Agent 正式接入。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python 3.11 + FastAPI + SQLAlchemy 2 + SQLite |
| 前端 | React 18 + TypeScript + Vite |
| 配置 | YAML（`configs/`），DataRoot 可用环境变量覆盖 |
| 日志 | JSON Lines（app / jobs / errors 三类） |

## 快速开始

```bash
# 后端（首次运行自动创建 .venv 并安装依赖）
scripts\dev_backend.bat
# 或手动：
#   python -m venv .venv
#   .venv\Scripts\python -m pip install -r backend\requirements.txt
#   .venv\Scripts\python -m uvicorn app.main:app --reload --port 8000 --app-dir backend

# 前端（使用 AIHome 统一 Node 环境）
scripts\dev_frontend.bat
# 打开 http://localhost:5173
```

- 健康检查：`GET http://127.0.0.1:8000/api/v1/health` → `{"status":"ok","version":"0.8.0"}`
- 测试：`.venv\Scripts\python -m pytest`（在项目根目录执行；GitHub CI 在 push/PR 时自动运行同样检查）
- 仅初始化数据目录（不启动服务）：`python scripts\init_dataroot.py`
- 数据库安全备份：`.venv\Scripts\python scripts\backup_db.py`（SQLite backup API，输出到 `DataRoot/backups/`）

## 目录结构

```text
nsfw-studio-v2/
├── backend/          # FastAPI 后端（api / core / models / schemas / services / database / workers / workflows / engine / storage）
├── frontend/         # React + TS 前端壳（主题系统、顶部导航、空状态页面）
├── configs/          # YAML 配置（config / app / storage / workflow）
├── database/         # 数据库设计文档（运行库在 DataRoot/database/studio.db）
├── workflows/        # 未来工作流定义文件（Phase 0 为空，不绑定任何引擎）
├── scripts/          # 开发与交接脚本
├── tests/            # backend / frontend / integration 三层测试
├── docs/             # 项目文档（结构、开发指南、数据库/API 规划、阶段报告）
└── handoff/          # 阶段交接包输出（gitignore）
```

## 运行数据（DataRoot）

程序首次启动会自动创建。配置优先级（固定）：

```text
NSFW_STUDIO_DATA_ROOT（环境变量）
  > configs/config.local.yaml（本机私有，已 gitignore，不提交）
    > configs/config.yaml（公共模板，机器无关，不设置 data_root）
      > 代码默认 %USERPROFILE%/NSFW-Studio-Data（可移植）
```

本机想把数据放其他盘：新建 `configs/config.local.yaml`（如 `data_root: "D:/NSFW-Studio-Data"`），
不要提交。换电脑 clone 后无需任何修改即可启动。

```text
NSFW-Studio-Data/
├── database/         # studio.db（SQLite，WAL + foreign_keys）
├── backups/          # 数据库安全备份（SQLite backup API 生成）
├── images/{originals,upscaled,processed,temp}/
├── assets/{face,clothing,pose,scene}/
├── imports/  exports/  cache/
└── logs/{app,jobs,errors}/
```

代码与启动脚本不得依赖任何单一固定机器路径；路径一律由 `configs/` + `backend/app/core/config.py` 提供。

## 文档索引

- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) — 结构与模块职责
- [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md) — 开发环境与流程
- [docs/DATABASE_PLAN.md](docs/DATABASE_PLAN.md) — 数据库现状与规划
- [docs/API_PLAN.md](docs/API_PLAN.md) — API 现状与规划
- [docs/PHASE0_REPORT.md](docs/PHASE0_REPORT.md) — Phase 0 / 0.1 验收报告
- [docs/PHASE1_REPORT.md](docs/PHASE1_REPORT.md) — Phase 1 验收报告
- [docs/DATA_MODEL_V1.md](docs/DATA_MODEL_V1.md) — 数据模型（ER / 版本 / 快照 / 软删除 / Job / Image）
- [docs/WORKBENCH_STATE.md](docs/WORKBENCH_STATE.md) — 工作台状态契约
- [docs/JOB_STATE_MACHINE.md](docs/JOB_STATE_MACHINE.md) — Job / JobItem 状态机
- [docs/QUEUE_SPEC.md](docs/QUEUE_SPEC.md) — 单队列规范（排序 / 暂停 / 系统性失败）
- [docs/RECOVERY_SPEC.md](docs/RECOVERY_SPEC.md) — 崩溃恢复规范
- [docs/COMFY_ENV_INVENTORY.md](docs/COMFY_ENV_INVENTORY.md) — 本机 ComfyUI 环境调查
- [docs/WORKFLOW_INVENTORY.md](docs/WORKFLOW_INVENTORY.md) — 本机工作流调查与 basic_generate 选型
- [docs/COMFY_ADAPTER.md](docs/COMFY_ADAPTER.md) — ComfyUIAdapter 设计与契约
- [docs/IMAGE_MODEL.md](docs/IMAGE_MODEL.md) — Image / Gallery 模型与流程
- [docs/PHASE2_1_REPORT.md](docs/PHASE2_1_REPORT.md) — Phase 2.1 验收报告（执行稳定性收口）
- [docs/PHASE2_2_REPORT.md](docs/PHASE2_2_REPORT.md) — Phase 2.2 验收报告（数据一致性收口）
- [docs/PIPELINE_V2.md](docs/PIPELINE_V2.md) — 多阶段管线架构（JobStage / Stage Gate / 图片流转）
- [docs/PIPELINE_STATE_MACHINE.md](docs/PIPELINE_STATE_MACHINE.md) — Stage / StageItem 状态机
- [docs/UPSCALE_MODULE.md](docs/UPSCALE_MODULE.md) — 高清放大模块契约
- [docs/UPSCALE_WORKFLOW_INVENTORY.md](docs/UPSCALE_WORKFLOW_INVENTORY.md) — 本机高清链调查与选型
- [docs/PHASE3_REPORT.md](docs/PHASE3_REPORT.md) — Phase 3 验收报告（多阶段管线 + 高清）
- [docs/HISTORY_SPEC.md](docs/HISTORY_SPEC.md) — 历史任务（来源=jobs / 任务族归组 / 页面）
- [docs/PROVENANCE_SPEC.md](docs/PROVENANCE_SPEC.md) — 图片溯源与工作台恢复（根生成 Job / 完整身份）
- [docs/MODULE_IO_CONTRACT.md](docs/MODULE_IO_CONTRACT.md) — Module I/O 契约（能力驱动 kind/parent/seed / 输入图片契约 / Input Registry）
- [docs/MIGRATION_0008_BACKFILL.md](docs/MIGRATION_0008_BACKFILL.md) — 历史 Job Stage 回填 + 执行指纹迁移
- [docs/PHASE4_REPORT.md](docs/PHASE4_REPORT.md) — Phase 4 验收报告（历史 / 溯源 / 通用模块契约）
- [docs/IMAGE_CONDITIONING_INVENTORY.md](docs/IMAGE_CONDITIONING_INVENTORY.md) — 本机图片条件生成能力调查（Gate B / 候选方案）
- [docs/PHASE5_REPORT.md](docs/PHASE5_REPORT.md) — Phase 5 验收报告（图片输入基建 / 能力 Gate）
- [DEV_LOG.md](DEV_LOG.md) / [TASKS.md](TASKS.md) / [CHANGELOG.md](CHANGELOG.md) / [TEST_REPORT.md](TEST_REPORT.md)

## Git 规范

- 分支：`main`（稳定）、`develop`（集成）、`feature/xxx`、`fix/xxx`
- Commit 格式：`feat: xxx` / `fix: xxx` / `docs: xxx` / `chore: xxx` / `test: xxx`
