# TEST_REPORT — Phase 0 / 0.1 / 1 / 2（2026-10-07）

## Phase 2 测试（v0.3.0，Job Execution Core + ComfyUIAdapter + Gallery）

### 快速套件（不依赖 ComfyUI，CI 同口径）

命令：`.venv\Scripts\python -m pytest tests/backend --ignore=tests/backend/test_comfyui_integration.py -q`

**结果：91 passed**（0.2.0 的 68 例 + Phase 2 新增 23 例）。

| 测试文件 | 用例数 | 覆盖点 |
| --- | --- | --- |
| test_job_queue.py | 14 | §五十八 全清单：8 张串行 / Item 边界暂停 / 取消保留图 / 取消后 Resume 子 Job / 优先插队 / 拖拽排序 / 引擎离线（队列暂停）/ 瞬态网络重试 ≤2 恢复 / OOM 不重试 / Workflow 错误不重试 / 启动发现 INTERRUPTED / 崩溃恢复核对导入 / SSE 流 / client_request_id 幂等 / 固定 Seed |
| test_image_service.py | 5 | 输出导入（相对路径/尺寸/元数据/失败全回滚）/ 垃圾字节拒绝 / review+favorite / 列表过滤 + by-job 统计（含收藏）/ Gallery API 全链路（content/review/favorite/workbench+Seed） |
| test_comfyui_binding.py | 4 | provider binding 注入（节点 ID 只在 binding 层）/ seed 范围钳制 / 模板不被污染 / workflow_hash 与 binding_version 溯源（无需 ComfyUI） |
| test_migration_upgrade.py | 1 | v0.1.2 库 → 0002–0006 升级（含 jobs/job_items/job_events/images 约束） |
| test_interfaces.py | 8 | 契约守护更新：公共配置允许选择 comfyui（不得携带机器地址）/ Worker 只消费 Job / EngineAdapter 异步契约 |

### 真实 ComfyUI 集成（本机，离线自动 skip）

命令：`.venv\Scripts\python -m pytest tests/backend/test_comfyui_integration.py -q`

**结果：3 passed**（`test_real_generation[1]/[3]/[8]`，合计 12 张真实图片）。

- 完整生产链：POST /jobs → 单队列 → ComfyUIAdapter → Qwen-Image 2.1 UC 生成 →
  导入 DataRoot/images/originals → Gallery 查询 + content 可读；
- 断言：顺序执行（engine_job_id 各不相同）、Seed = base + item_index、completed_count 递增、
  图片元数据（尺寸 640×960 / source=comfyui / 相对路径）、Workbench Snapshot 完整；
- 实测速度：640×960 约 102–118 秒/张（模型驻留显存）；当天首张 832×1216 含模型加载约 300 秒。

前端：`npm run build`（tsc --noEmit + vite build）通过。

### 未验证 / 限制（如实标注）

- 未做浏览器 E2E 自动化（IAB 沙箱限制）；前端以 API 测试 + 构建 + dev 手动运行验证为准；
- CI 结果需在 feature → develop → main 推送后由 GitHub Actions 确认（见 GIT_COMMITS/CI 记录）；
- 队列内存态暂停、进程崩溃窗口等边界依赖 Mock 测试覆盖（真实 ComfyUI 场景不模拟崩溃）。

## 零-c、Phase 1 测试（v0.2.0，Prompt/Asset/Recipe Core）

命令：`.venv\Scripts\python -m pytest`（项目根目录）

**结果：68 passed, 1 warning（4.65s）**——0.1.1 的 33 例 + 新增 35 例。

| 测试文件 | 用例数 | 覆盖点（对应规范 §五十八） |
| --- | --- | --- |
| test_prompt_composer.py | 5 | 八栏顺序固定 / 空字段跳过 / 未知字段丢弃 / JSON 往返 / 容错 |
| test_prompt_service.py | 7 | CRUD / 版本机制 / 元数据不建版本 / 线性恢复 / 归档 / 404 / 并发冲突(VERSION_CONFLICT+回滚) / 列表过滤 |
| test_asset_service.py | 8 | 四类型创建 / 相对路径入库 / 非法类型 / 版本不可变+旧文件保留 / 非法扩展名 / 内容不符 / 超限 / 提交失败无孤儿文件 / 路径穿越防护 |
| test_recipe_service.py | 8 | 快照创建 / FK+快照双存 / 素材升级老配方不变 / 恢复制快照 / 内容不变不建版 / seed 固定 random / slot 校验 / 缺素材 404 / 列表归档 |
| test_api_phase1.py | 4 | 统一错误格式（404/422） / Prompt 全链路 / Asset 上传+预览图+版本 / Recipe 保存+恢复往返 |
| test_migration_upgrade.py | 1 | v0.1.2 库 → 0002-0004 升级 → 旧数据保留 / FK / CHECK / UNIQUE 全部生效 |

前端：`npm run build`（tsc + vite）通过。

**真实环境验证**：
- 迁移前备份（SQLite backup API）→ `studio-20261007-152712.db`；
- 真实库 0.1.2 → 0.2.0 迁移成功（0002/0003/0004 applied，system_info 自动更新，9 张表就位）；
- 浏览器人工验证（规范 §五十九）：新建结构化 Prompt→保存→重开字段一致 ✓；完整 Prompt ✓；
  选择素材→服饰字段填充（素材在前）✓；保存配方→重开 100% 恢复（Prompt/Negative/素材引用/尺寸）✓；
  素材卡片/详情/版本 ✓；深浅主题 ✓。素材文件上传的 UI 自动化受浏览器沙箱限制（IAB 不支持
  file chooser），上传/校验/版本逻辑由 API 测试全覆盖。

**GitHub CI**：feature → develop → main 推送均触发，结果见运行记录（要求全绿）。

环境事故记录：验证期间发现残留 vite 进程占用 5173 缓存旧 CSS（TaskStop 只杀 bash 包装进程），
已清理；后续停服务需核对端口释放。

---

## 零-b、Phase 0.1.1 测试（v0.1.2，审查遗留契约修正）

命令：`.venv\Scripts\python -m pytest`（项目根目录）

**结果：33 passed, 1 warning（5.70s）**——0.1 的 27 例 + 新增 6 例。

| 新增用例 | 覆盖点 |
| --- | --- |
| test_workflow_execute_is_async | `WorkflowModule.execute` 为 async（与 EngineAdapter 契约统一） |
| test_engine_adapter_methods_are_async | EngineAdapter 四个方法全部 async |
| test_pure_computation_interfaces_stay_sync | capabilities / validate_input 保持同步 |
| test_repo_public_config_is_machine_independent | 公共 config.yaml 无盘符、不设置 data_root（哨兵） |
| test_no_config_falls_back_to_portable_default / test_base_config_overrides_default | 三层缺失 → 用户目录默认；模板覆盖默认 |
| test_local_config_overrides_base_config | config.local.yaml 覆盖公共模板 |
| test_env_var_beats_all_config_layers | 环境变量最高优先级（同时存在 base+local） |
| test_local_config_is_gitignored | config.local.yaml 被 .gitignore 覆盖（防误提交） |

真实加载验证：本机 `load_settings()` 实际 DataRoot = `D:\NSFW-Studio-Data`（来自 config.local.yaml）；
仓库内 config.yaml 已无任何机器路径。
前端：`npm run build` 通过；develop / main CI 全绿。

---

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
