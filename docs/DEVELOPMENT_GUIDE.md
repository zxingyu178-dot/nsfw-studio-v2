# DEVELOPMENT_GUIDE — 开发指南

> 更新：2026-10-07（Phase 0）

## 1. 环境要求

| 工具 | 版本 | 来源 |
| --- | --- | --- |
| Python | 3.11 | 本机已装（`python --version`） |
| Node.js | ≥ 18（AIHome 统一环境为 v24.18.1） | `D:\AIHome_2.0_L1_L2\environment\managed-tools\node\` |
| npm | 随 Node | 同上（registry 为 npmmirror） |

Node 未进系统 PATH 时，Git Bash 中先执行：

```bash
export PATH="/d/AIHome_2.0_L1_L2/environment/managed-tools/node/node-v24.18.1-win-x64:$PATH"
```

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
```

## 4. 配置系统

| 文件 | 内容 |
| --- | --- |
| `configs/config.yaml` | `data_root`（DataRoot 根目录） |
| `configs/app.yaml` | 应用名 / 版本 / host / port / 日志级别 |
| `configs/storage.yaml` | DataRoot 子目录清单 + 数据库文件名 |
| `configs/workflow.yaml` | 工作流配置占位（Phase 0 provider=unbound） |

环境变量覆盖（优先级最高）：`NSFW_STUDIO_DATA_ROOT`、`NSFW_STUDIO_HOST`、`NSFW_STUDIO_PORT`。
前端：`VITE_API_BASE_URL`（直连后端地址，缺省走 Vite 代理）、`NSFW_STUDIO_API_URL`（代理目标）。

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
