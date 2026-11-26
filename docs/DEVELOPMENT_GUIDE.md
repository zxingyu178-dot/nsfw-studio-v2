# DEVELOPMENT_GUIDE — 开发与发布标准

> 更新：2026-11-27（v15 多模型 + Agent 统一提交落地）
> 本文是日常开发、测试、发布与移动端验收的唯一入口；更细的领域合同见文末索引。

## 1. 环境

| 工具 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.11 | 使用仓库根 `.venv`；依赖 `backend/requirements-dev.txt` |
| Node.js | ≥ 18 | `frontend/`，`npm ci && npm run build` |
| JDK 17 | 17.0.13 | Android 构建；路径 `environment/managed-tools/jdk/jdk-17.0.13+11` |
| Android SDK | 现有 SDK | 模拟器验收，**不装机** |

后端命令统一在 `backend/` 目录执行（`app` 包入口），或在仓库根加 `--app-dir backend`：

```bash
# 开发服务（8000 只监听 127.0.0.1）
cd backend && ..\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# 临时验证实例（不碰生产 DataRoot / 生产 8000）
$env:NSFW_STUDIO_DATA_ROOT='E:\AI_Gen\data\_verify'; ..\.venv\Scripts\python -m uvicorn app.main:app --port 8010

# 后端测试（临时 DataRoot，禁止连接真实 8188/8000/8877）
.venv\Scripts\python -m pytest tests/backend -q

# 前端
cd frontend && npm run test -- --run && npx tsc -b && npm run build
```

## 2. 单一事实源与工作树

- `main` 是唯一开发源；功能分支 `feature/*`、修复分支 `fix/*` 合入 `main`。
- 运行时工作树 `E:/AI_Gen/projects/nsfw-studio-v2-app`（分支 `deploy/app-instance`）只用于生产运行；
  **不要强制覆盖或强推该分支**，更新时先合入 `main`，再在 worktree 中 fast-forward。
- 生产端口：Desktop API `8000`（loopback）；Mobile Review Bridge `8877`（只读审核，独立进程）；
  ComfyUI `8188`。禁止把 8000 绑定到 `0.0.0.0`。
- 不提交：`.venv`、`node_modules`、`*.db`、日志、`handoff/`、模型权重、生成图片、凭据。
- 临时目录/验证输出放仓库外（如 `E:/AI_Gen/data/_verify`），不要留在仓库根。

## 3. 版本模型（必须遵守）

- **模块代码版本** `module_version`（如 `anime_generate v1`）与 **provider binding 版本**
  `binding_version`（如 `v15`）是两个域，禁止互相兜底。
- Binding 一旦发布即不可变；修改 `workflow.json` / `binding.yaml` 必须新建 `vN+1`。
- 每次任务固化身份：`module_id + module_version + provider + binding_version + workflow_hash + binding_hash`。
- 放行由 `workflows/release_manifest.yaml` 控制；`dependencies_ready` 与 `real_gate_passed`
  同时为真才允许创建新 Job。未放行 binding 一律拒绝，前端隐藏不是安全边界。
- 新增 binding 流程：
  1. 复制上一版目录，改 `binding.yaml` 的 `binding_version` 与 inputs/defaults；
  2. 在 manifest 增加条目（先 `real_gate_passed: false`）；
  3. 单测（参数注入/节点重写/Hash）→ 临时实例真实出图 → 回填 evidence；
  4. 通过后再置 `real_gate_passed: true`，默认档保持不变需单独评审。

## 4. AI 统一提交契约

- 唯一入口：`POST /api/v1/agent/jobs`（Bearer token，默认 30 次/分钟），旧 `/jobs` 仅本机兼容。
- 支持字段：`prompt`、`negative_prompt`、`module_id`、`module_version`、`binding_version`、
  `model`、`loras[]`（≤2，含强度）、`params{steps,cfg,sampler_name,scheduler,denoise}`、
  `width/height/count/seed/queue_mode/client_request_id`。
- 能力发现：`GET /api/v1/agent/capabilities`（需 token）返回模块、可用底模、可用 LoRA 与参数边界。
- 服务端校验链：模块解析 → 放行门禁 → binding 参数声明 → 模型/LoRA 存在性 → 模块 config 校验 → 创建 Job。
- CLI：`scripts/agent_generate.py`（`--model/--lora/--steps/--cfg/--sampler/--scheduler/--denoise`）；
  高级字段只允许走 Agent 端点（需 token）。
- 详见 `docs/AGENT_SUBMISSION.md`、`docs/AGENT_SUBMISSION_STANDARD.md`、`docs/WORKFLOW_SUBMISSION_STANDARD.md`。

## 5. 开发流程（每个改动必须走完）

1. **定义**：写清用户价值、影响面、验收标准；跨模块改动先列计划。
2. **实现**：优先复用现有服务/契约；新增 API 遵循 schema → service → router 分层。
3. **测试**：先跑定向测试，再跑全量后端；前端 `test + tsc + build`。
4. **真实证据**：涉及生成链路时，用临时实例 + 真模型出图，核对 ComfyUI history 节点值。
5. **文档**：`CHANGELOG.md` 记录行为变化；binding 变更同步 manifest evidence。
6. **合入**：`main` 通过后，再更新 app worktree 并重启生产；重启后做 8000/8877 健康检查。
7. **移动端**：只做模拟器验收（见 §7），不装机、不发邮件。

## 6. 测试门禁

| 层级 | 命令/方式 | 通过标准 |
| --- | --- | --- |
| 后端定向 | `pytest <相关文件> -q` | 全绿 |
| 后端全量 | `pytest tests/backend -q` | 全绿 |
| 前端单测 | `npm run test -- --run` | 全绿 |
| 类型/构建 | `npx tsc -b && npm run build` | 无错误 |
| 真实生成 | 临时实例 8010 + Agent CLI | COMPLETED、图片落盘、history 节点参数一致 |
| 桌面 UI | 浏览器五页 | 首页/创作/图库/词库/设置无报错 |
| 移动端 | 现有模拟器 `MediaReview_Test` | 审核流、进度、动效可用 |

Hermetic 护栏：后端测试自动设置 `NSFW_STUDIO_HERMETIC=1` 并拦截 8188/8000/8877 连接；
新增测试不得绕过该护栏。

**历史测试债（2026-11-27 已清理）**：Phase 3–7/21/22/51 旧套件已通过
`tests/backend/conftest.py::process_registry` 的“测试专用注册表”迁移完成：
产品注册表仍只暴露 `anime_generate`，测试进程额外挂载 `basic_generate` / `img2img` /
`reference_generate` / `fake_process`，并在放行清单中同步 ready 替身（硬件档位沿用各模块
历史记录）。默认模块断言统一为 `anime_generate`。全量 `pytest tests/backend -q`
（836 项）必须全绿后才可提交。

### 工具权限（Windows）

若 Node / Java 子进程出现 `EPERM`（无法创建临时文件、Vite 配置加载失败），通常是可执行文件
带 Low 完整性标签；用管理员 PowerShell 执行：

```powershell
icacls "<node.exe 或 java.exe 的绝对路径>" /setintegritylevel Medium
```

然后重开终端。不要通过关闭杀毒软件来绕过。

## 7. 移动端验收（模拟器）

- 桥 `8877` 只读：审核、进度、事件；不提供生成控制。
- 生图进度 `GET /mobile/generation/progress`（能力 `mobile_generation_progress_v1`）只返回
  `current_image / images_in_segment / remaining_segments`，不泄露 Prompt 或控制面；
  审核页顶栏显示“第 X / Y 张 · 剩余 N 段”并带呼吸动画，老桥无该能力时整行隐藏。
- 使用 AVD `MediaReview_Test`（`D:\...\projects\mediareview\android`）安装 debug APK 验证；
  不写真机安装步骤、不发邮箱。模拟器访问本机桥用 `adb reverse tcp:<port> tcp:<port>`。
- 交互变更需覆盖：冷启动、断网重连、空队列、审核操作反馈、返回栈、进度从生成中→空闲。

### 最近一次模拟器验收（2026-11-27，Alpha51 / versionCode 58）

- `assembleDebug` 后安装到 `emulator-5554`；模拟器上首次冷启动需先
  `adb shell cmd package compile -m speed -f com.mediareview.app`，否则 debug 包可能触发
  “failed to complete startup” ANR；AOT 后主界面与底部五个 Tab 正常。
- 首次启动弹出 Alpha51 更新说明（保留/淘汰/收藏触感反馈、收藏弹跳、新图与页面切换动画）；
  关闭后首页媒体墙、底部 Tab 正常。
- 生图审核图库显示 21714 张；进入审图页顶部显示“电脑端暂无生成任务”只读进度行。
- 收藏 → 保留操作后切换到 `2 / 21714` 并显示“已保留”，无崩溃、无新增错误日志。

### 最近一次模拟器验收（2026-11-27，Alpha50 / versionCode 57）

- 安装新 APK 到 `emulator-5554`；配对到临时桥 `127.0.0.1:8878`（独立 DataRoot）。
- 图库显示 v15 真实出图；审图页顶栏显示“电脑端暂无生成任务”。
- 插入 RUNNING 夹具后 5s 内显示“第 3 / 6 张 · 剩余 1 段”；标记完成后恢复“暂无生成任务”。
- 夹具已清理；临时桥与模拟器在验收后可关闭。

## 8. Git 与提交

- 提交信息：`feat:` / `fix:` / `test:` / `docs:` / `chore:` + 英文祈使句。
- 不绕过 hooks；不 force-push `main` / `deploy/app-instance`。
- 提交前检查：`git status` 无临时文件、密钥、数据库；定向测试已通过。

## 9. 文档索引

- 运行时/引擎：`ENGINE_RUNTIME_CONTRACT.md`、`COMFY_ADAPTER.md`、`MODULE_IO_CONTRACT.md`
- 工作流与放行：`WORKFLOW_SUBMISSION_STANDARD.md`、`REAL_MACHINE_GATE_PLAN.md`
- AI 提交：`AGENT_SUBMISSION.md`、`AGENT_SUBMISSION_STANDARD.md`
- 资源版本：`RESOURCE_VERSIONING_STANDARD.md`、`REGISTRY_VALIDATION_GUIDE.md`
- 前端：`DESIGN.md`、`UI_DESIGN_SYSTEM.md`、`UI_ACCEPTANCE.md`
- 移动端：`MOBILE_BRIDGE_AUTOSTART.md`、`MOBILE_W41_INTEGRATION.md`
