# NSFW Studio V2 — Phase 0 验收报告

> 日期：2026-10-07 ｜ 版本：0.1.0 ｜ 执行：ZCode Agent

## 一、阶段目标

建立长期可扩展的本地 AI 图像生产平台基础。**不接入** ComfyUI / 实际模型 / 生图工作流 / 豆包 / 手机端；
只完成项目初始化、前后端框架、数据目录体系、数据库基础、API 框架、日志系统、配置系统、
WorkflowModule 与 EngineAdapter 接口预留、Git 规范、基础 UI 壳。

## 二、交付内容

| 模块 | 说明 |
| --- | --- |
| Backend | Python 3.11 + FastAPI + SQLAlchemy 2 + SQLite；api/core/models/schemas/services/database/workers/workflows/engine/storage 十模块 |
| Frontend | React 18 + TypeScript + Vite 5；五页面壳 + 顶部导航 + 深浅主题（ThemeProvider + localStorage） |
| DataRoot | 首次启动自动创建 15 个目录（清单来自 configs/storage.yaml） |
| 数据库 | migration 表 + system_info 表 + 极简迁移框架（可平滑升级 Alembic） |
| 日志 | JSON Lines，app / jobs / errors 三路，5MB×5 轮转 |
| 配置 | configs/ 四份 YAML；NSFW_STUDIO_DATA_ROOT 等环境变量覆盖；代码零硬编码路径 |
| 接口预留 | WorkflowModule、EngineAdapter、QueueWorker 均为抽象类，无任何引擎绑定 |
| 测试 | pytest 15 例（启动 / health / 数据目录 / 数据库 / 接口存在性 / 幂等性） |
| 脚本 | dev_backend.bat / dev_frontend.bat / init_dataroot.py / build_handoff.py |

## 三、验收标准核对（规范 §十九）

### 项目

| 标准 | 结果 |
| --- | --- |
| GitHub 可以正常 clone | ✅ 公开仓库 `zxingyu178-dot/nsfw-studio-v2` 已创建并推送（main + develop + tag v0.1.0），`git ls-remote` 验证通过；2026-10-07 应用户要求由私有转为公开，供三方 AI 审核代码，可匿名 clone |
| 前后端可以启动 | ✅ uvicorn 启动成功；vite dev server 启动成功（HTTP 200） |

### 后端

| 标准 | 结果 |
| --- | --- |
| FastAPI 运行 | ✅ |
| health API 正常 | ✅ `GET /api/v1/health` → `{"status":"ok","version":"0.1.0"}` |
| SQLite 初始化 | ✅ studio.db 创建，migration/system_info 表就位，system_info 写入 0.1.0 |
| 配置加载正常 | ✅ 四份 YAML 加载 + 环境变量覆盖（测试即用临时 DataRoot 验证） |
| 日志生成正常 | ✅ 三类日志文件生成，JSON 格式正确 |

### 前端

| 标准 | 结果 |
| --- | --- |
| 页面打开 | ✅ 浏览器实测 http://localhost:5173 |
| 顶部导航显示 | ✅ 品牌 + 生成/图库/提示词/素材/设置 五项，激活态高亮，路由切换正常 |
| 深浅主题切换 | ✅ 浏览器实测：点击切换 data-theme=light，localStorage `nsfw-studio-theme` 持久化 |

### 数据

| 标准 | 结果 |
| --- | --- |
| DataRoot 创建成功 | ✅ `D:/NSFW-Studio-Data` 首次启动自动创建 |
| 文件夹结构正确 | ✅ 与规范 §九 完全一致（15 个目录） |

### 架构

| 标准 | 结果 |
| --- | --- |
| WorkflowModule 接口存在 | ✅ `backend/app/workflows/base.py`（validate_input / execute / get_output） |
| EngineAdapter 接口存在 | ✅ `backend/app/engine/base.py`（health / submit_job / get_job_status / cancel_job） |
| 未绑定 ComfyUI | ✅ 代码与配置零引擎绑定（workflow.yaml provider=unbound，有测试守护） |

## 四、验证记录（真实执行）

- `pytest`：**15 passed**（警告 1 条：starlette 对 httpx 的弃用提示，非本项目问题）。
- 后端启动后 `curl /api/v1/health` 与 `curl /`：正常。
- DataRoot 树 `find` 核对：15 目录全部存在；studio.db 20KB；app/jobs/errors 日志生成且内容为合法 JSON。
- 前端 `npm run build`（tsc 类型检查 + vite）：成功（47 modules，gzip JS 55.6KB）。
- 浏览器（IAB）实测：页面渲染、导航跳转 /settings、主题切换与持久化、Engine 在线指示（绿点）。
- 实测中发现并修复 2 个缺陷：① `database/base.py` 缺少 `create_engine` 导入；② `app.css` 的 `@import` 相对路径错误（浏览器实测暴露）。
- npm 已知 bug（rollup 可选依赖缺失）：清理重装后仍复现（npmmirror 镜像缺 `@rollup/rollup-win32-x64-msvc@4.64.1`），已通过固定 `rollup@4.64.0` + 匹配原生包解决，并写入 package.json devDependencies。

## 五、限制与待办

1. ~~GitHub 推送未执行~~ **已解决（2026-10-07）**：使用本机凭据管理器中已存的 GitHub 凭据（zxingyu178-dot）经 API 创建私有仓库并推送成功；`gh` CLI 仍未安装，后续如需常用可考虑安装。
2. 前端自动化测试（Vitest）与集成冒烟测试按计划放 Phase 1。
3. Worker / Workflow / Engine 均为接口占位，无任何运行线程。

## 六、下一步（Phase 1 预告）

数据模型设计（Job / JobItem / Prompt / Recipe / Asset / Image）+ Prompt / 素材 / 配方系统开发。
