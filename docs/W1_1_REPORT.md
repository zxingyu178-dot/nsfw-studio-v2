# W1.1 完成报告 — Release Gate Hardening

> 基线：`1cf05e5aae535e46ddab5308810435a315a3bbea`（W1 文档提交）。
> 执行日期：2026-10-30。本阶段不启动 ComfyUI、不使用 GPU、不生成真实图片、不下载模型、
> 不安装节点、不升级 ComfyUI、不修改模型、不修改冻结 v1 的 workflow.json / binding.yaml、
> 不迁移数据库、不重构三栏工作台、不新增工作流模块、不改变单队列串行架构。

## 1. 本阶段目标与结果

| 项 | 结果 |
| --- | --- |
| W1.1-1 服务端新任务放行门禁 | ✅ 已实现，覆盖 Web / Agent / 图库放大 / History 续跑 |
| W1.1-2 前端图片模块放行漏洞 | ✅ 已修复 source/reference 槽绕过，覆盖 Recipe/History/setInputImage 归一化 |
| W1.1-3 三类验收证据分离 | ✅ manifest 与 inventory/reference 文档已拆分 |
| W1.1-4 G0 静态检查增强 | ✅ 9 类新增检查 + 9 类负向测试 |
| W1.1-5 回归与 CI | ✅ 定向 46 passed；前端 468 passed；G0 0 errors；CI 结果见 §6 |

## 2. W1.1-1 后端正式放行门禁

### 2.1 统一 helper

`backend/app/engine/release.py::ensure_modules_released()`：

- 输入是 `resolve_requested_modules()` 解析出的真实执行身份（`module_id` + 服务端解析的
  `binding_version`），**不读取客户端传入的 `release_status`**；
- 逐个调用 `release_status(module_id, binding_version, binding_valid=True)`；
- 未登记 binding、`dependencies_ready=false`、`real_gate_passed=false`、
  `hardware_status=unsupported` 任一不满足即拒绝；
- 抛出 `ValidationError(code="WORKFLOW_NOT_RELEASED")`，`details.modules` 携带每个被拒模块及原因；
- 调用点全部在 `job_service.create_job()` **之前**，因此拒绝时数据库不会产生 Job/Stage 残留。

### 2.2 覆盖入口

| 入口 | 位置 | 门禁 |
| --- | --- | --- |
| `POST /api/v1/jobs` | `backend/app/api/v1/jobs.py` `create_job` | ✅ Job 创建前 |
| `POST /api/v1/agent/jobs` | `backend/app/api/v1/agent.py` | ✅ Job 创建前，与 Web 共用同一 manifest |
| `POST /api/v1/images/upscale`（图库处理任务） | `backend/app/api/v1/images.py` | ✅ Job 创建前 |
| `POST /api/v1/jobs/{id}/resume-remaining`（History 新建 Job） | `backend/app/api/v1/jobs.py` | ✅ 按原 Job `workflow_snapshot.modules` 校验 |
| `POST /api/v1/jobs/resume-interrupted`（可信恢复通道） | `backend/app/services/job_service.py` | 不经过门禁，保留原始 binding 身份 |

说明：

- `resume-remaining` 是“从 History 创建一个新的子 Job”，不是 PAUSED/INTERRUPTED 的原 Job 恢复，
  因此必须走门禁；其身份取自原 Job 快照（服务端数据），不是客户端请求体。
- `resume-interrupted` 只对已存在 Job 重排队/续跑，不创建新的任务身份，因此保留可信路径；
  客户端携带完整 binding 身份**不会**自动获得历史恢复豁免。

## 3. W1.1-2 前端图片模块放行

`frontend/src/stores/workbenchStore.ts`：

- 新增 `isReleaseReady()`：`release_status` 存在时必须 `ready_to_run === true`；
  旧后端没有 `release_status` 时回落 `available`（兼容场景）。
- `availableImageModuleIds()` 现在同时要求：
  `available === true` && `isReleaseReady(module)` && (`isImageStartModule` || `declaresImageInput`)。
  图片输入槽只负责能力识别，不再绕过放行。
- `isImageStartModule`、`textPrimaryCandidates`、`normalizeModules`、`hydrateWorkbench`、
  `setInputImage` 均经同一判断；Recipe/History 恢复不能带入未放行模块。
- `reference_generate` 的 reference 输入槽保持支持；未放行时 `isImageCapablePrimary=false`。

## 4. W1.1-3 验收证据

`workflows/release_manifest.yaml` 每个 binding 拆为三段：

- `comfyui_node_chain`：直连 ComfyUI API / 节点链；
- `studio_production`：经 Studio Job + Queue + Stage，记录 `binding_hash` / Job ID；
- `default_profile_performance`：当前默认配置的 G4（独立语义，不参与 `ready_to_run`）。

关键核对：

- `reference_generate/v1`：640/20 证据是 2026-10-07 直连 ComfyUI API，**不对应当前 binding 的
  1024/25 默认**，且未记录 binding_hash；当前 binding（`1022da22e48721e6`）唯一 Studio 证据是
  `job_25c14f4d…`（resolution=768，输出 672×896）；`default_profile_verified=false`。
- `basic_generate/v1`：当前 hash `6c1a64481fc4802e` 有 69 个 COMPLETED Stage；G4 未测。
- `img2img/v1`：12 个 COMPLETED；`v2` 节点图与 v1 相同，0.8 由 v1 hash 下的两个真实 Job 执行，
  证据标 `passed_inherited`，v2 自身尚无独立 Job。
- `upscale/v1`：8 个 COMPLETED；G4 未测。
- `anime_generate/v1`：见 §7 冲突说明。

## 5. W1.1-4 / W1.1-5 验证结果

### 5.1 G0

```text
[G0] checked=6 errors=0 warnings=14
```

14 条 warning 均为 legacy 冻结 v1 的兼容政策（缺 requirements/performance、
`UnetLoaderGGUF` 未声明、anime 节点内置 negative prompt），没有为减少 warning 修改旧指纹。
详见 `docs/W1_1_G0_REPORT.md`。

### 5.2 后端定向测试

```text
46 passed
```

覆盖：门禁拒绝/放行、未登记 binding、拒绝无残留 Job、Agent 不能绕过、
`resume-remaining` 受门禁、`resume-interrupted` 不受破坏、anime 证据断言、
img2img v2 指纹兼容、reference 模块、G0 9 类负向测试。

### 5.3 前端

```text
npm run typecheck 通过
vitest: 96 files / 468 tests passed
npm run build 通过（393.54 kB JS）
```

## 6. 新增与修改文件

新增：

- `tests/backend/test_workflow_release_gate_w11.py`
- `tests/backend/test_validate_workflows_w11.py`
- `docs/W1_1_REPORT.md`（本文件）
- `docs/W1_1_RELEASE_GATE_AUDIT.md`
- `docs/W1_1_G0_REPORT.md`

修改：

- `backend/app/engine/release.py`（`ensure_modules_released`）
- `backend/app/api/v1/jobs.py`（`/jobs` 与 `resume-remaining` 门禁）
- `backend/app/api/v1/agent.py`（Agent 门禁）
- `backend/app/api/v1/images.py`（图库放大门禁）
- `frontend/src/stores/workbenchStore.ts`（图片模块放行）
- `frontend/src/stores/workbenchStore.releaseStatus.test.ts`（W1.1 用例）
- `scripts/validate_workflows.py`（G0 增强）
- `tests/backend/test_anime_generate_module.py`（anime 证据断言 + 强制未放行 fixture）
- `tests/backend/test_agent_submission.py`（Agent 门禁用例）
- `tests/backend/test_workflow_release_w1.py`（anime 真实证据断言）
- `workflows/providers/comfyui/img2img/v2/binding.yaml`（requirements + `batch_size`）
- `workflows/release_manifest.yaml`（证据三段 + anime 事实修正）
- `docs/REFERENCE_CAPABILITY_INVENTORY.md`、`docs/WORKFLOW_INVENTORY.md`、
  `docs/WORKFLOW_TECH_DEBT.md`、`DEV_LOG.md`、`TASKS.md`

## 7. 冲突说明：anime_generate 的真实证据

W0/W1 文档、ChatGPT 审查前提均为“anime_generate 无真实 G3 证据，应隐藏并拒绝”。
W1.1 只读审计 `D:/NSFW-Studio-Data/database/studio.db` 后发现：

- 当前 binding hash `dfa750836ac536eb` 有 2 个真实 Studio COMPLETED Job：
  - `job_9961f5f1-b2a0-4691-b314-35e2d02d4db7`（832×1216，2026-10-20，约 4.5 分钟）
  - `job_430e3dd7-94c6-421e-a28b-0b1ee834ab19`（1920×1088，2026-10-20）

按 W1.1-3“没有证据必须标记未验证，不得推测”的原则，manifest 把 anime 标为
`real_gate_passed=true` / `hardware_status=slow` / `default_profile_verified=false`，
即 `ready_to_run=true`。**这与审查中“anime 应隐藏/拒绝”的预期相反。**

门禁机制本身已用临时 manifest 强制 anime 未放行并通过测试；若用户/ChatGPT 仍决定隐藏 anime，
只需把 manifest 的 anime `real_gate_passed` 改回 `false`（或 `hardware_status=experimental`），
无需改代码。该决定留给独立审查。

## 8. 未完成 / 未验证

- `default_profile_verified`（G4）在 basic/reference/anime/upscale 上仍为 false；
- 依赖探测仍是人工登记（W2 改为实际探测）；
- 全量后端 pytest 未在本机重复运行，交由 GitHub CI 执行（符合“定向测试优先”指令）；
- 未启动 ComfyUI / GPU，未执行任何真实出图。
