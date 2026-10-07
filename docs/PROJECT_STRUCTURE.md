# PROJECT_STRUCTURE — 项目结构与模块职责

> 更新：2026-10-07（Phase 0）

## 仓库结构

```text
nsfw-studio-v2/
├── backend/                    # FastAPI 后端
│   ├── app/
│   │   ├── main.py             # 应用工厂 + lifespan 启动引导
│   │   ├── api/                # 只做 HTTP 编排（v1: health）
│   │   ├── core/               # 配置加载 / DataRoot 路径 / JSON 日志
│   │   ├── models/             # SQLAlchemy 模型（SystemInfo）
│   │   ├── schemas/            # Pydantic 出入参（HealthResponse）
│   │   ├── services/           # 业务逻辑（system_service 启动引导）
│   │   ├── database/           # 引擎工厂 + 极简迁移框架
│   │   ├── workers/            # QueueWorker 接口占位（Phase 1 实现）
│   │   ├── workflows/          # WorkflowModule 接口规范（不绑定引擎）
│   │   ├── engine/             # EngineAdapter 接口规范
│   │   │   └── adapters/       # 未来 ComfyUIAdapter（Phase 0 为空）
│   │   ├── storage/            # StorageManager：DataRoot 文件系统
│   │   └── logs/               # 兜底日志占位（运行日志在 DataRoot）
│   ├── requirements.txt / requirements-dev.txt
│   └── README.md
├── frontend/                   # React 18 + TS + Vite 5
│   └── src/
│       ├── app/                # App 路由 + 全局样式
│       ├── pages/              # Generate / Gallery / Prompt / Assets / Settings
│       ├── components/         # TopNav / EngineStatus / ThemeToggle / EmptyState
│       ├── layouts/            # MainLayout
│       ├── themes/             # ThemeProvider + tokens.css（深浅主题变量）
│       ├── api/                # 后端 HTTP 封装（client.ts）
│       ├── stores/             # themeStore（localStorage 持久化）
│       └── utils/              # format.ts
├── configs/                    # config.yaml（data_root）/ app.yaml / storage.yaml / workflow.yaml
├── database/                   # 数据库设计文档（运行库在 DataRoot）
├── workflows/                  # 未来工作流定义文件（Phase 0 为空）
├── scripts/                    # dev_backend / dev_frontend / init_dataroot / build_handoff
├── tests/                      # backend（pytest）/ frontend（Phase 1）/ integration（Phase 1）
├── docs/                       # 本文档目录
└── handoff/                    # 阶段交接包输出（gitignore）
```

## 运行数据 DataRoot（不在仓库内）

默认 `D:/NSFW-Studio-Data`（`configs/config.yaml`，环境变量 `NSFW_STUDIO_DATA_ROOT` 可覆盖），
首次启动自动创建，清单由 `configs/storage.yaml` 的 `storage.layout` 定义：

```text
NSFW-Studio-Data/
├── database/studio.db          # SQLite
├── images/{originals,upscaled,processed,temp}/
├── assets/{face,clothing,pose,scene}/
├── imports/  exports/  cache/
└── logs/{app,jobs,errors}/     # JSON Lines 日志
```

## 关键设计约束

| 约束 | 实现 |
| --- | --- |
| 不提前绑定生成引擎 | `engine/base.py` 仅有抽象接口；`configs/workflow.yaml` provider=unbound |
| 模块化扩展不改核心 | 新能力 = 新 WorkflowModule / EngineAdapter 实现 |
| 单机优先 | SQLite + 本地文件系统，无云依赖 |
| 路径零硬编码 | 全部来自 configs + `core/config.py`（env 可覆盖） |
| api 不写业务 | api 只做 HTTP 编排，业务在 services |
