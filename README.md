# NSFW Studio V2

[![CI](https://github.com/zxingyu178-dot/nsfw-studio-v2/actions/workflows/ci.yml/badge.svg)](https://github.com/zxingyu178-dot/nsfw-studio-v2/actions/workflows/ci.yml)

本地 AI 图像生产平台（单机优先，Windows 本地运行，公司/家里经 GitHub 切换开发）。

**当前阶段：Phase 3 — Multi-stage Pipeline + Upscale（已完成，v0.4.0）。**
Phase 3 新增：多阶段管线（JobStage / JobStageItem，**生成 N 张原图全部完成后才进入高清放大**，
Stage Gate 严格门控）、第二个 WorkflowModule `upscale`（4x-UltraSharp 链，复用本机已验证资源）、
图库已有图片单独高清（upscale-only process Job，同一 Worker / 同一模块）、
Image 父子关系（高清 parent_image_id + images/upscaled 存储 + 图库切换）、
分阶段实时进度与 HD 标记、配方高清开关 100% 恢复；
Task 0 修复：Worker 意外异常 → Job INTERRUPTED + 队列暂停（§0.1）、请求级动态 binding（§0.2）、
workflow_hash 校验（§0.3）、固定 Seed 仅限单张（§0.4）。
Phase 2.2 修复：导入批次整批原子化（P0）、恢复后 Job 终态归并（P0）、Worker 取消不误写终态、
Resume 完整继承原 Workflow 身份、ComfyUI 取消不误伤其他任务。
Phase 2.1 修复：无图片不得 COMPLETED（P0）、引擎掉线不得永久 RUNNING、Worker 去模块硬编码
（BasicGenerateModule + ModuleRegistry + PipelineExecutor）、workflow_snapshot 同步真实执行、
Resume 新随机 Seed、queue_position 唯一执行顺序、binding 版本化解析、Job API 严格校验、
Cancel 异常隔离、交接包无 .git 可测。
Phase 1 已完成：Prompt（结构化八栏/完整双模式 + 版本历史 + 软删除）、素材（四分类 + 预览图上传 + 版本）、
配方（工作台快照 + 素材版本快照）、生成工作台三栏（保存/100% 恢复）。
Phase 2 已完成：Job / JobItem / 单队列 Worker（暂停 / 取消 / 续跑 / 幂等 / 崩溃恢复）、
SSE 任务事件、ComfyUIAdapter（真实对接本机 ComfyUI + provider binding）、
Image 导入 DataRoot + 图库（审核 / 收藏 / 按任务查看 / Image → 工作台 / 从图库创建素材）。
执行链路：Workbench → POST /jobs → 单队列 → Stage 顺序执行 → WorkflowModule → EngineAdapter →
ComfyUI → Image → Gallery。
本机 ComfyUI 环境事实见 `docs/COMFY_ENV_INVENTORY.md` / `docs/WORKFLOW_INVENTORY.md` /
`docs/UPSCALE_WORKFLOW_INVENTORY.md`；
仍禁止：图生图 / 参考图 / ControlNet / 视频 / 手机端 / Agent 正式接入。

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

- 健康检查：`GET http://127.0.0.1:8000/api/v1/health` → `{"status":"ok","version":"0.4.0"}`
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
- [DEV_LOG.md](DEV_LOG.md) / [TASKS.md](TASKS.md) / [CHANGELOG.md](CHANGELOG.md) / [TEST_REPORT.md](TEST_REPORT.md)

## Git 规范

- 分支：`main`（稳定）、`develop`（集成）、`feature/xxx`、`fix/xxx`
- Commit 格式：`feat: xxx` / `fix: xxx` / `docs: xxx` / `chore: xxx` / `test: xxx`
