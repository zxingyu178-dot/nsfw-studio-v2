# DEV_LOG — NSFW Studio V2

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

- GitHub 推送未执行：本机无 `gh` CLI、无已配置远端（详见 docs/PHASE0_REPORT.md §五）。
