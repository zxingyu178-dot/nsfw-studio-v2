# DEVELOPMENT_GUIDE — 开发指南

> 更新：2026-10-07（Phase 0.1 收口）

## 1. 环境要求

| 工具 | 版本 | 来源 |
| --- | --- | --- |
| Python | 3.11 | 本机已装（`python --version`） |
| Node.js | ≥ 18 | 解析顺序：AIHome 统一环境（存在时）→ 系统 PATH；都没有则脚本报错退出 |

> 跨机器开发（公司/家里）：Node 解析已内建于 `scripts/dev_frontend.bat`
> （自动探测 AIHome 环境目录，不存在则回落系统 PATH），Python 只依赖系统 PATH，
> 无任何单一固定机器路径依赖。CI（GitHub Actions）会在 push/PR 时自动验证
> 非本机环境下 pytest 与前端构建可跑通。

## 2. 首次初始化

```bash
# 后端依赖
python -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements-dev.txt

# 前端依赖
cd frontend && npm install
```

或直接双击 `scripts\dev_backend.bat` / `scripts\dev_frontend.bat`（首次自动装依赖）。

## 3. 日常开发

```bash
# 后端（http://127.0.0.1:8000，Swagger /docs）
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000 --app-dir backend

# 前端（http://localhost:5173，/api 自动代理到 8000）
cd frontend && npm run dev

# 后端测试（临时 DataRoot，不触碰真实数据）
.venv\Scripts\python -m pytest

# 前端类型检查 + 生产构建
cd frontend && npm run build

# 仅初始化 DataRoot（不启动服务）
python scripts\init_dataroot.py

# 数据库安全备份（SQLite backup API -> DataRoot/backups/）
.venv\Scripts\python scripts\backup_db.py
```

## 4. 配置系统

| 文件 | 内容 |
| --- | --- |
| `configs/config.yaml` | `data_root`（DataRoot 根目录；**本机明确声明**，如 D 盘） |
| `configs/app.yaml` | 应用名 / 版本 / host / port / 日志级别 |
| `configs/storage.yaml` | DataRoot 子目录清单（含 backups/）+ 数据库文件名 |
| `configs/workflow.yaml` | 工作流配置占位（provider=unbound） |

覆盖优先级：环境变量 > config.yaml > 代码默认值。
代码默认 DataRoot 是可移植的 `%USERPROFILE%/NSFW-Studio-Data`（`core/config.py` 的
`DEFAULT_DATA_ROOT`），某台机器想用其他盘必须在 config.yaml 明确声明。
环境变量：`NSFW_STUDIO_DATA_ROOT`、`NSFW_STUDIO_HOST`、`NSFW_STUDIO_PORT`。
前端：`VITE_API_BASE_URL`（直连后端地址，缺省走 Vite 代理）、`NSFW_STUDIO_API_URL`（代理目标）。

## 5. CI

`.github/workflows/ci.yml`：push（main/develop）与 PR 时自动运行——
后端：`pip install -r backend/requirements-dev.txt` + `pytest`；
前端：`npm ci` + `npm run build`。main / develop 上的提交必须 CI 全绿。

## 5. 日志

- 位置：`{data_root}/logs/{app/app.log, jobs/jobs.log, errors/error.log}`，5MB 轮转 ×5。
- 格式：JSON Lines `{"time","level","module","message"}`；ERROR+ 同时进 `error.log`。
- 任务日志用 logger 名 `studio.jobs`（Python：`logging.getLogger("studio.jobs")`）。

## 6. Git 规范

- 分支：`main`（稳定）/ `develop`（集成）/ `feature/xxx` / `fix/xxx`。
- Commit：`feat:` / `fix:` / `docs:` / `chore:` / `test:` + 英文祈使句，如 `feat: add storage manager`。
- 禁止提交：`.venv`、`node_modules`、`*.db`、日志、`handoff/`。

## 7. 扩展方式（Phase 1+）

- **新增业务表**：`backend/app/database/migrations.py` 追加 Migration；模型放 `app/models/`。
- **新增 API**：schema 放 `app/schemas/`，逻辑放 `app/services/`，路由挂 `app/api/v1/router.py`。
- **新增生成能力**：实现 `WorkflowModule`（`app/workflows/`）+ `EngineAdapter`（`app/engine/adapters/`），经 configs 选择，不改核心。
- **任务队列**：实现 `QueueWorker`（`app/workers/`）。
