# NSFW Studio V2

本地 AI 图像生产平台（单机优先，Windows 本地运行）。

**当前阶段：Phase 0 — 工程初始化与架构搭建（已完成）。**
本阶段只建立长期可扩展的架构骨架，不接入 ComfyUI / 实际模型 / 生图工作流 / 豆包 / 手机端。
生成能力全部通过 `backend/app/engine/`（EngineAdapter）与 `backend/app/workflows/`（WorkflowModule）接口预留，未来扩展不改核心。

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

- 健康检查：`GET http://127.0.0.1:8000/api/v1/health` → `{"status":"ok","version":"0.1.0"}`
- 测试：`.venv\Scripts\python -m pytest`（在项目根目录执行）
- 仅初始化数据目录（不启动服务）：`python scripts\init_dataroot.py`

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

程序首次启动会自动创建（默认 `D:/NSFW-Studio-Data`，可用环境变量 `NSFW_STUDIO_DATA_ROOT` 覆盖）：

```text
NSFW-Studio-Data/
├── database/         # studio.db（SQLite）
├── images/{originals,upscaled,processed,temp}/
├── assets/{face,clothing,pose,scene}/
├── imports/  exports/  cache/
└── logs/{app,jobs,errors}/
```

代码中禁止写死任何路径，一律由 `configs/storage.yaml` + `backend/app/core/config.py` 提供。

## 文档索引

- [docs/PROJECT_STRUCTURE.md](docs/PROJECT_STRUCTURE.md) — 结构与模块职责
- [docs/DEVELOPMENT_GUIDE.md](docs/DEVELOPMENT_GUIDE.md) — 开发环境与流程
- [docs/DATABASE_PLAN.md](docs/DATABASE_PLAN.md) — 数据库现状与规划
- [docs/API_PLAN.md](docs/API_PLAN.md) — API 现状与规划
- [docs/PHASE0_REPORT.md](docs/PHASE0_REPORT.md) — Phase 0 验收报告
- [DEV_LOG.md](DEV_LOG.md) / [TASKS.md](TASKS.md) / [CHANGELOG.md](CHANGELOG.md) / [TEST_REPORT.md](TEST_REPORT.md)

## Git 规范

- 分支：`main`（稳定）、`develop`（集成）、`feature/xxx`、`fix/xxx`
- Commit 格式：`feat: xxx` / `fix: xxx` / `docs: xxx` / `chore: xxx` / `test: xxx`
