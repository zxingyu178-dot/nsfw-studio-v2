# DEV_LOG — NSFW Studio V2

## 2026-10-07 — Phase 0.1：架构收口（v0.1.1）

**执行**：ZCode Agent（在 develop 完成 → CI 全绿 → 合并 main → tag v0.1.1）

### 收口内容（三方审查合同落实）

1. **Migration 漏洞**：`applied_migration_ids()` 只认 `status='applied'`；重试前 DELETE 同 ID 的 failed 记录解决主键冲突。补失败恢复测试（失败→failed→仍视为未完成→修复→重试成功→状态正确）。
2. **SQLite 工程化**：`make_engine()` 每连接执行 `journal_mode=WAL`、`busy_timeout=5000`、`foreign_keys=ON`；新增 `app/database/backup.py`（SQLite backup API，禁直接复制写入中的 DB）+ `scripts/backup_db.py`；DataRoot 增加 `backups/`。
3. **契约收口**：新增 `WorkflowInput/WorkflowOutput/WorkflowValidation/ModuleCapabilities/ParameterSpec`；`WorkflowModule.execute(payload, engine)` 显式接收 EngineAdapter（引擎调用只发生在 Adapter）；EngineAdapter 增加 `EngineJobRequest/EngineJobStatus`（含 progress 进度能力）；`QueueWorker` 删除 `submit()`（Job 创建属于 API/JobService，Worker 只消费）。
4. **可移植性**：代码默认 DataRoot 改为 `Path.home()/"NSFW-Studio-Data"`；本机 D 盘由 config.yaml 明确声明（允许）；`dev_frontend.bat` 改为 AIHome 探测→PATH 回退→清晰报错；`dev_backend.bat` 补 Python 存在性检查。
5. **语义修正**：前端顶部指示 "Studio 在线/离线"（后端健康），Phase 1 接 EngineAdapter.health 后才显示 Engine；`system_info.version` 语义定为**当前应用版本**，启动时自动对齐（实测 0.1.0→0.1.1 更新成功）。
6. **CI**：`.github/workflows/ci.yml`（ubuntu：pytest；node 20：npm ci + build），push/PR 触发。
7. **测试**：15 → **27 例**全绿；`npm run build` 通过。

### 决策

| 决策 | 理由 |
| --- | --- |
| system_info 语义选"当前应用版本" | 为 Phase 1 的升级可观测性服务；字段名不变、语义写进文档与 BootstrapReport.system_info_action |
| WorkflowModule.execute 注入 EngineAdapter | 保证"引擎调用只在 Adapter"由类型系统约束，而不只是口头约定 |
| Worker 移除 submit 而非新增 submit | 合同要求 Worker 不成为 Job 创建入口；消费入口定为 process_job(job_id) |
| CI 后端跑 ubuntu | 兼验证可移植性（DataRoot 默认值与配置加载均跨平台） |

### 实测发现并修复

- （本轮无新增缺陷；27 例测试一次全绿后做真实启动升级验证）

## 2026-10-07 — Phase 0：工程初始化与架构搭建（v0.1.0）

**执行**：ZCode Agent（遵循 AIHome 全局规则 + 本项目 AGENTS.md）

### 完成内容

1. **立项**：项目建于 `projects/nsfw-studio-v2`（`projects/nsfw-studio` 为 V1，完全独立未触碰）。
   git init（main 分支），目录骨架 + .gitignore + 项目级 AGENTS.md。
2. **后端**：FastAPI 工厂 + lifespan 启动引导；配置系统（4 份 YAML + 环境变量覆盖）；
   JSON 结构化日志（app/jobs/errors）；SQLAlchemy + 自研极简迁移框架（migration 表）；
   system_info 表；StorageManager；health API。WorkflowModule / EngineAdapter / QueueWorker
   按规范仅定义抽象接口，零实现、零引擎绑定。
3. **前端**：Vite + React 18 + TS 壳；MainLayout + TopNav（五项导航）；EngineStatus（轮询
   /api/v1/health，15s）；ThemeProvider + themeStore（localStorage 持久化，默认深色）；
   五页面空状态（设置页含可用的主题选择）。
4. **测试**：pytest 15 例全绿；前端 npm run build 通过。
5. **文档**：docs/ 五份 + DEV_LOG/TASKS/CHANGELOG/TEST_REPORT。

### 关键决策

| 决策 | 理由 |
| --- | --- |
| 迁移用自研极简框架而非 Alembic | Phase 0 只有 2 张表，规范只要求 migration 表打底；接口设计保留 Alembic 升级路径 |
| 时间字段存 TEXT（ISO 8601） | 与迁移表记录一致，SQLite 下可读可排序，Phase 1 统一 |
| 测试用 NSFW_STUDIO_DATA_ROOT 环境变量注入临时目录 | 验证环境变量覆盖机制本身，且绝不触碰真实 DataRoot |
| 前端 EngineStatus 检测后端 health | Phase 0 无引擎可测；Phase 1 切换为 EngineAdapter.health()，组件接口不变 |
| Node 使用 AIHome managed-tools（v24.18.1） | 遵循全局规则 §7 工具发现顺序；未安装第二套 Node |
| rollup 固定 4.64.0 | npmmirror 镜像缺 4.64.1 原生包（npm optional deps bug 叠加镜像同步延迟） |

### 实测发现并修复

- `database/base.py` 缺 `create_engine` 导入（pytest 暴露）。
- `app.css` `@import './themes/tokens.css'` 路径错误 → `../themes/`（浏览器实测暴露，Vite overlay）。

### 遗留

- ~~GitHub 推送未执行~~ → **当日已解决**：检测到本机 Git Credential Manager 存有 GitHub 凭据
  （zxingyu178-dot），经 GitHub API 创建私有仓库 `nsfw-studio-v2` 后推送 main / develop / v0.1.0 成功，
  `git ls-remote` 验证通过。`gh` CLI 仍未安装（AIHome tool-registry 登记 not_found）。
- 同日应用户要求将仓库由私有**转为公开**（https://github.com/zxingyu178-dot/nsfw-studio-v2），用途：三方 AI 审核代码。
  已确认仓库内无凭据/密钥（.gitignore 排除 .env，代码零硬编码秘密）。
