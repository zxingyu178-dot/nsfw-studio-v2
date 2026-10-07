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

## 3. 阶段纪律（当前 Phase 0）

禁止在本项目中接入或实现：

- ComfyUI 或任何实际生成引擎（不写引擎地址 / 节点 ID / 模型名 / Workflow JSON）；
- 实际生图工作流；
- 豆包 / 手机端 / 云服务 / 多用户 / 分布式。

所有生成相关能力只能通过两个预留接口扩展，且不得修改核心：

- `backend/app/engine/` — EngineAdapter（未来 ComfyUIAdapter 放 `engine/adapters/`）；
- `backend/app/workflows/` — WorkflowModule。

## 4. 架构红线

- `api/` 只做 HTTP 编排，业务逻辑一律放 `services/`。
- 禁止在代码中写死路径：一切路径来自 `configs/*.yaml` + `core/config.py`（DataRoot 可用 `NSFW_STUDIO_DATA_ROOT` 覆盖）。
- 运行数据（数据库 / 图片 / 日志）只放 DataRoot，禁止提交进仓库。
- 前端 `api/` 只封装后端 HTTP 调用；新增扩展不改核心。

## 5. 脚本与登记

- `scripts/` 下的长期脚本（dev_backend / dev_frontend / init_dataroot / build_handoff）已登记至 AIHome Registry；修改前先确认调用方。
- 本项目 Phase 0 不新增任何长期运行服务；dev server 均为手动临时启动，不接入 ControlHub。

## 6. 验证要求

- 改后端：必须在项目根目录跑 `.venv\Scripts\python -m pytest`，全绿才算完成。
- 改前端：必须 `npm run build` 通过。
- 汇报遵循全局规则第 10 条：未执行 / 部分验证必须如实标注。

## 7. Git

- 分支：`main`、`develop`；功能 `feature/xxx`；修复 `fix/xxx`。
- Commit 用 conventional 前缀（feat / fix / docs / chore / test）。
- 禁止把 DataRoot 数据、`node_modules`、`.venv`、交接包提交进仓库。
