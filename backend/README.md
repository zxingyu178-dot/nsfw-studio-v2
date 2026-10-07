# backend

NSFW Studio V2 后端：Python 3.11 + FastAPI + SQLAlchemy 2 + SQLite。

## 运行

```bash
# 项目根目录执行（推荐）
scripts\dev_backend.bat

# 或手动
python -m venv .venv
.venv\Scripts\python -m pip install -r backend\requirements.txt
.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000 --app-dir backend
```

- 健康检查：<http://127.0.0.1:8000/api/v1/health>
- Swagger 文档：<http://127.0.0.1:8000/docs>

## 模块职责

| 目录 | 职责 |
| --- | --- |
| `app/api/` | 只做 HTTP 编排，禁止业务逻辑 |
| `app/core/` | 配置加载、路径、JSON 日志 |
| `app/models/` | SQLAlchemy 数据库模型 |
| `app/schemas/` | Pydantic 请求/响应结构 |
| `app/services/` | 业务逻辑（启动引导等） |
| `app/database/` | 引擎工厂、极简迁移框架 |
| `app/workers/` | Worker 接口占位（Phase 1 实现 QueueWorker） |
| `app/workflows/` | WorkflowModule 接口规范（不绑定引擎） |
| `app/engine/` | EngineAdapter 接口规范（未来 ComfyUIAdapter 放 adapters/） |
| `app/storage/` | DataRoot 文件系统管理 |

## 环境变量

| 变量 | 说明 |
| --- | --- |
| `NSFW_STUDIO_DATA_ROOT` | 覆盖 DataRoot（默认 `D:/NSFW-Studio-Data`） |
| `NSFW_STUDIO_HOST` / `NSFW_STUDIO_PORT` | 覆盖监听地址/端口 |

## 测试

项目根目录：`.venv\Scripts\python -m pytest`（全部用例使用临时 DataRoot，不触碰真实数据目录）。
