# TEST_REPORT — Phase 0 / 0.1（2026-10-07）

## 零、Phase 0.1 测试（v0.1.1，架构收口）

命令：`.venv\Scripts\python -m pytest`（项目根目录）

**结果：27 passed, 1 warning（1.89s）**——原 15 例 + 新增 12 例，一次全绿。

新增覆盖（对应 Phase 0.1 验收）：

| 测试文件 | 用例数 | 覆盖点 |
| --- | --- | --- |
| test_migrations_recovery.py | 2 | failed 迁移不被视为 applied；下次启动仍重试；修复后重试成功且无主键冲突残留；仅 applied 计数 |
| test_sqlite_pragmas.py | 1 | WAL / busy_timeout=5000 / foreign_keys=ON，且每个新连接生效 |
| test_backup.py | 2 | 备份快照可打开且数据一致（SQLite backup API）；源库缺失报错 |
| test_config_portability.py | 4 | 默认 DataRoot 基于 Path.home()；env 覆盖；config 文件覆盖；env > 文件 |
| test_system_info.py | 2 | 版本升级后 system_info 同步更新且单行；同版本 unchanged |
| test_interfaces.py | 5 | Workflow 标准契约存在且 execute 注入 EngineAdapter；EngineJobStatus 含 progress；QueueWorker 无 submit（只消费）；provider=unbound |
| 既有测试更新 | - | health/system_info 版本断言改为动态（settings.app.version）；EXPECTED_DIRS 增加 backups |

前端：`npm run build`（tsc + vite）通过。

**真实运行验证（本机 DataRoot 升级路径）**：
- 现有 DataRoot 幂等升级成功：自动新建 `backups/`（日志：`新建目录=['backups']`）；
- `system_info` 版本自动更新 `0.1.0 → 0.1.1`（BootstrapReport.system_info_action=updated）；
- `PRAGMA journal_mode` 实测返回 `wal`；
- `scripts/backup_db.py` 实测成功产出 `backups/studio-20261007-143618.db`。

**GitHub CI**：`.github/workflows/ci.yml` 于 develop/main push 与 PR 触发（后端 pytest + 前端 npm ci/build）；本轮推送后 CI 运行结果见下方"实时记录"。

---

## 环境信息

| 项 | 值 |
| --- | --- |
| OS | Windows 10.0.26200 x64 |
| Python | 3.11.15（项目 .venv，随项目创建） |
| Node.js | v24.18.1（AIHome managed-tools，未装第二套） |
| 关键依赖 | fastapi 0.142.2 / SQLAlchemy 2.1.3 / pydantic 2.13.5 / pytest 9.1.1 / vite 5.4.21 / react 18.3.1 |

## 一、后端自动化测试（pytest）

命令：`.venv\Scripts\python -m pytest`（项目根目录，pytest.ini 指向 tests/backend）

**结果：15 passed, 1 warning（0.76s）**

| 测试文件 | 用例 | 覆盖验收点 |
| --- | --- | --- |
| test_app_startup.py | 3 | 应用工厂 / 入口可导入 / lifespan 启动引导 |
| test_health_api.py | 2 | health 响应体精确匹配 `{"status":"ok","version":"0.1.0"}`、根信息 |
| test_data_dirs.py | 3 | 15 个目录全部创建、二次引导幂等、StorageManager 白名单 |
| test_database.py | 3 | studio.db 创建、migration 记录 applied、system_info=0.1.0、不重复写行、迁移幂等 |
| test_interfaces.py | 4 | WorkflowModule / EngineAdapter / QueueWorker 抽象接口存在、workflow.yaml provider=unbound |

说明：全部用例通过 `NSFW_STUDIO_DATA_ROOT` 使用 pytest 临时目录，未触碰真实 `D:/NSFW-Studio-Data`。
警告为 starlette 对 httpx 的弃用提示（第三方库），非本项目缺陷。

## 二、运行时验证（真实启动）

| 步骤 | 命令/操作 | 结果 |
| --- | --- | --- |
| 后端启动 | `uvicorn app.main:app --port 8000 --app-dir backend` | ✅ 启动完成，无错误 |
| health API | `curl /api/v1/health` | ✅ `{"status":"ok","version":"0.1.0"}` |
| 根信息 | `curl /` | ✅ `{"name":"NSFW Studio","version":"0.1.0","api":"/api/v1/health"}` |
| DataRoot | `find /d/NSFW-Studio-Data -type d` | ✅ 15 目录与规范 §九 一致 |
| 数据库 | studio.db 存在（20KB） | ✅ |
| 日志 | logs/{app,jobs,errors} 各有文件 | ✅ JSON Lines 格式正确（time/level/module/message） |

## 三、前端验证

| 步骤 | 结果 |
| --- | --- |
| `npm run dev` 启动 | ✅ http://localhost:5173（HTTP 200） |
| `/api` 代理到后端 | ✅ 通过代理请求 health 成功 |
| 页面渲染（浏览器实测） | ✅ 品牌 + 五项导航 + 空状态卡片 |
| 导航路由 | ✅ 点击"设置"跳转 /settings，标题与主题选项正确 |
| 深浅主题切换 | ✅ data-theme=light 生效、按钮文案切换、localStorage `nsfw-studio-theme=light` 持久化 |
| Engine 指示 | ✅ 绿点"Engine 在线"（后端在线时） |
| `npm run build`（tsc + vite） | ✅ 47 modules，JS 169.6KB（gzip 55.6KB） |

测试后已恢复默认深色主题、清除测试 localStorage、关闭浏览器标签页、停止两个 dev server。

## 四、测试中发现并修复的缺陷

| # | 缺陷 | 发现方式 | 修复 |
| --- | --- | --- | --- |
| 1 | `database/base.py` 使用 `create_engine` 未导入 | pytest（NameError） | 补充导入，复测通过 |
| 2 | `app.css` `@import './themes/tokens.css'` 相对路径错误 | 浏览器实测（Vite overlay 报 ENOENT） | 改为 `../themes/tokens.css`，热更新后正常 |
| 3 | npm optional deps bug + npmmirror 缺 `@rollup/rollup-win32-x64-msvc@4.64.1` | vite 启动崩溃 | 固定 `rollup@4.64.0` + 匹配原生包（写入 devDependencies） |

## 五、未执行 / 部分验证项（如实声明）

- ~~GitHub clone 验证：未执行~~ **已补充验证（2026-10-07）**：使用本机凭据管理器已存凭据创建仓库
  `https://github.com/zxingyu178-dot/nsfw-studio-v2`（创建时私有，同日应用户要求转为公开，供三方 AI 审核代码），
  推送 main / develop / tag v0.1.0 成功，`git ls-remote origin` 确认远端引用完整，可匿名 clone。
- 前端自动化测试（Vitest）：按规范属 Phase 1 范围，未包含。
