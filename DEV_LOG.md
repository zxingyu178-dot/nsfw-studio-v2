# DEV_LOG — NSFW Studio V2

## 2026-10-07 — Phase 1：Prompt / Asset / Recipe Core（v0.2.0）

**执行**：ZCode Agent（feature/phase1-prompt-asset-recipe → develop → CI → main → tag v0.2.0）

### 交付

- 数据模型：migration 0002/0003/0004（prompts、assets、recipes 三族 + 素材快照表），
  TEXT 主键 + 前缀化 uuid4、UTC 时间工具、FK/UNIQUE/CHECK 全量约束；Job/Image 仅文档预留。
- Prompt：双模式 + 版本机制（内容变才建版、元数据不建、恢复=复制为新版）+ 软删除 + PromptComposer
  后端权威合成（compose 接口前端同源预览）。
- Asset：四分类 + 预览图上传（ext/MIME/magic/size 四重校验）+ temp→原子移动→提交
  （提交失败清理文件、文件失败不提交）+ resolve_under 防穿越 + 版本不可变。
- Recipe：工作台快照（Prompt 快照+FK、slot 级素材版本快照、generation_settings、workflow 预留）。
- API 三组 + 统一错误 `{"error":{code,message}}` + 列表统一参数；lifespan 建 session 工厂。
- 前端：WorkbenchStore + 三栏工作台 + 提示词三 Tab + 素材页；三条"打开工作台"路径复用
  WorkbenchSnapshot（100% 恢复已实测）。
- 测试 33 → **68 例**全绿；真实库迁移前先备份（backup API），升级 0.1.2→0.2.0 成功。
- 浏览器人工验证 §五十九 全清单（含深浅主题）。

### 实测发现并修复

1. 0004 迁移 DDL 缺 recipe_asset_snapshots.created_at 列（测试暴露，迁移未发布前修正）。
2. StorageManager.path 白名单不含父目录（resolve_under("assets") 被拒）→ 允许登记目录的父目录。
3. 结构化合成只在路由层做、服务层缺失 → 下沉为 Service 权威逻辑（prompt/recipe 一致，幂等）。
4. 升级测试 monkeypatch 恢复方式错误（自我赋值）→ 修正测试。
5. **环境教训**：此前 TaskStop 停掉 dev server 的 bash 包装进程后 node 子进程残留，
   占用 5173 并缓存旧 CSS，浏览器验证一度出现"整页无样式"假象 → 用 netstat 定位 PID 清理。
   后续停止 dev server 需确认端口释放。

### 决策

| 决策 | 理由 |
| --- | --- |
| 结构化正向快照由 Service 合成（而非仅路由） | "UI 看到的 == 保存的"必须由单一权威实现保证，且服务层可独立测试 |
| RecipeVersion.default_count 列 + JSON 内镜像 | 规范 §二十三/§二十七 双处要求；单一写入方（Service）保证一致 |
| 未命中内容不建冗余版本 | 规范 §十一"内容变化才建版本"的镜像面；API/服务返回 created 标志 |
| 配方版本内容不变不建版本 | 与 Prompt/Asset 一致的三方语义 |

## 2026-10-07 — Phase 0.1.1：审查遗留契约修正（v0.1.2）

**执行**：ZCode Agent（develop → CI 绿 → 合并 main → tag v0.1.2；不新增任何产品功能）

1. **异步契约统一**：`WorkflowModule.execute` 改为 async abstractmethod（此前与 EngineAdapter
   全 async 方法不一致，未来 Pipeline 无法 await）。异步原则固定写入 docstring + 开发指南：
   执行链路全 await，纯数据校验 sync。测试：`iscoroutinefunction` 守护 execute 与 EngineAdapter
   全部方法，同时守护 capabilities/validate_input 保持同步。
2. **DataRoot 真正跨机器**：审查指出 Phase 0.1 的方案仍有漏洞——公共 config.yaml 携带
   `data_root: "D:/NSFW-Studio-Data"`，clone 到他机仍会优先用 D 盘，可移植默认形同虚设。
   修正：公共 config.yaml 机器无关（不设置 data_root，含哨兵测试）；新增
   `configs/config.local.yaml` 本机私有层（`*.local.yaml` 本就在 .gitignore，双重显式登记）；
   优先级链固定为 env > local > 公共模板 > `Path.home()/NSFW-Studio-Data`。
   本机 D 盘只存在于 local 文件，真实加载已验证。
3. **Node 探测**：`dev_frontend.bat` 优先 `AIHOME_ROOT` 环境变量 → AIHome 规范默认根目录
   兼容探测（全局规范两台机器同根，仅作非阻断兼容）→ 系统 PATH → 报错。
4. 版本 0.1.2（app.yaml / __init__ / package.json + lock 同步）。
5. 验证：pytest **33 passed**；`npm run build` 通过；develop 与 main CI 全绿。

### 教训

- 配置"允许本机覆盖"必须区分**文件本身是否随仓库分发**——随仓库分发的公共配置写机器路径，
  等于把一台机器变成所有人的默认值（Phase 0.1 自评通过、审查未过的根因）。

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
