# W1.2.1 完成报告 — Workflow Integrity

> 基线：`9830384fd5e0303d004f100776219d3d81d0f244`（W1.2 完成）。
> 执行日期：2026-10-31。本阶段只修复，不增加新产品功能。
> 未新增 WorkflowModule、未修改冻结 Binding、未新增 Migration、未改 ComfyUI 引擎、
> 未改单队列架构、未下载模型/安装节点、未执行真实 GPU 测试、未重构工作台 UI、
> 未扩大 Agent Pipeline 能力。

## 1. 缺陷修复清单

| # | 缺陷 | 根因 | 修复 |
| --- | --- | --- | --- |
| 1 | 前端默认工作流静默降级 | `defaultTextModuleId` 在无 `is_default` 命中时回落 `candidates[0]` | 只认服务端 `is_default=true` 且必须同时是已放行文生图候选；否则返回 `null` |
| 2 | 默认未放行时可能自动选择其他模块 | `normalizeModules` 无默认时回落到现有/首个候选 | 目录已加载但默认不可用时保持未选定；不自动选其他工作流 |
| 3 | UI 未提示默认不可用 | 无提示位 | 新增 `defaultWorkflowNotice()`，InspectorPanel 在未选定 Primary 时显示明确 warning |
| 4 | CLI 默认同样猜测第一个候选 | `default_module_id` 有 `candidates[0]` 兜底 | 只认 `is_default`；旧 `/jobs` 路径解析不到默认时直接失败，不提交 |
| 5 | CLI 提前保存 Prompt | 提交前调用 `POST /prompts/ensure` | 删除该调用；Prompt 由服务端在 Job 事务内统一关联 |
| 6 | Prompt 与 Job 非同一事务 | `assign_ai_prompt` 内部 `commit()` | 新增 `commit=False`（只 flush）；Agent 与旧 `/jobs` 通过 `attach_ai_prompt(commit=False)`，由 JobService 统一提交 |
| 7 | Job 校验失败仍残留 Prompt | Prompt 已单独提交 | 事务失败/幂等冲突/数据库错误统一 rollback；新增 3 类回归测试 |
| 8 | 旧 `/jobs` 路径无 Prompt 关联 | 仅 Agent 路径写 Prompt | `source in ("agent","doubao")` 时服务端统一关联并回填 `source_prompt_id/version_id` |
| 9 | 空 `module_id` 被当作“未传”走默认 | 空字符串 falsy | Pydantic `field_validator` 拒绝 `""` / 纯空白（422）；服务层二次防护 |
| 10 | 自动归一化切换 Primary 不调整图片 role | `normalizeModules` 只改模块 | 新增 `remapInputRolesForAutoPrimary`：保留 image_id，按新模块 slot 调整 role；Primary 未变则不动 |
| 11 | `--no-prompt-library` 实际无效 | CLI 端选项与服务端没有对应开关 | 删除选项并修正 `AGENTS.md` / `docs/AGENT_SUBMISSION.md` |

## 2. 新增 / 修改文件

新增：

- `tests/backend/test_agent_generate_cli.py`
- `docs/W1_2_1_REPORT.md`（本文件）

修改：

- `frontend/src/stores/workbenchStore.ts`、`frontend/src/pages/Generate/workbench/InspectorPanel.tsx`
- `frontend/src/stores/workbenchStore.releaseStatus.test.ts`、
  `frontend/src/stores/workbenchStore.referenceRole.test.ts`、
  `frontend/src/pages/Generate/workbench/InspectorPanel.workflow.test.tsx`
- `backend/app/services/prompt_service.py`、`backend/app/services/agent_service.py`
- `backend/app/schemas/agent.py`、`backend/app/api/v1/agent.py`、`backend/app/api/v1/jobs.py`
- `scripts/agent_generate.py`
- `tests/backend/test_agent_submission.py`
- `tests/frontend/workbench_store.phase6.mjs`
- `docs/AGENT_SUBMISSION.md`、`AGENTS.md`
- `DEV_LOG.md`、`TASKS.md`

## 3. 新增回归测试清单

### 3.1 后端

`tests/backend/test_agent_submission.py`：

- A：`count=2 + 固定 Seed` → 400 `FIXED_SEED_SINGLE_ONLY`，Prompt / Job / JobStage 均不增加；
- B：相同 `client_request_id` + 不同 Prompt → 409 `IDEMPOTENCY_KEY_CONFLICT`，不新增 Prompt，原 Job Prompt 不变；
- C：未知模块 / 未放行默认 / process 模块 → 原有拒绝语义保持，无 Prompt/Job/JobStage；
- 空字符串与纯空白 `module_id` → 422；`unknown` → 400 `AGENT_MODULE_UNKNOWN`；
- 旧 `/jobs`（source=doubao）成功 → 服务端关联 Prompt，快照带 `source_prompt_id`；
- 旧 `/jobs` 校验失败 → Prompt / Job / JobStage 均不增加。

`tests/backend/test_agent_generate_cli.py`：

- 无 `is_default` → `default_module_id()` 返回 None（不猜测）；
- 有 `is_default` → 返回该模块；
- 默认 `ready_to_run=false` → 返回 None（不切其他模块）；
- CLI 源码不含 `"/prompts/ensure"` 调用、不含 `--no-prompt-library`；
- `--list-workflows` 只显示 Agent 允许模块（未放行 / 输入图模块不显示）。

### 3.2 前端

- `workbenchStore.releaseStatus.test.ts`（20 tests）：
  - 默认放行 → 正常选择；
  - 默认未放行 + anime 放行 → 不自动选择 anime，`workflowModules=[]`，`defaultWorkflowNotice` 明确提示；
  - 默认未注册（available=false）→ 不自动选择其他模块；
  - 没有 `is_default` → 不猜测默认；
  - 用户显式选择其他已放行工作流 → 保留选择。
- `workbenchStore.referenceRole.test.ts`（10 tests）：
  - reference_generate 不可用 → 自动切 img2img，role reference→source，image_id 保留；
  - img2img 不可用 → 自动切 reference_generate，role source→reference；
  - 目录异步加载 → 图片不丢、Primary 未变时 role 不变；
  - 历史恢复模块不可用 → 自动切换后 role 与新 Primary 匹配；
  - 原有手动切换测试继续通过。
- `InspectorPanel.workflow.test.tsx`（4 tests）：
  - 文生图 / 图片模式候选正确；
  - 未放行隐藏；
  - 默认不可用时显示 warning，且不自动替选（仍允许用户显式选择）。

## 4. 测试结果

| 项 | 结果 |
| --- | --- |
| 后端定向（agent / CLI / prompt / anime / gate / release / img2img / reference / phase22） | 61 passed |
| 前端 typecheck | 通过 |
| 前端 vitest | 97 files / 486 tests passed |
| Store regression | 11 passed |
| 前端 build | 通过（394.43 kB JS） |
| G0 | checked=6 errors=0 warnings=14 |

## 5. 行为说明

### 5.1 默认工作流（Fail-Closed）

- 唯一默认来源 = `GET /modules` 的 `is_default=true`；
- 必须同时满足 `available=true`、`ready_to_run=true`、`is_generative=true`、
  `input_required=false`、允许 `generate`；
- 不满足时前端保持未选定并显示 warning；不自动切换到其他工作流；
- 用户手动选择其他已放行工作流后，保留用户选择；
- CLI 旧路径解析不到默认时直接失败；Agent 路径不传 module_id 时由服务端默认解析，
  未放行则 400 `WORKFLOW_NOT_RELEASED`，不会降级。

### 5.2 Prompt / Job 事务

顺序：解析工作流 → 放行门禁 → Agent 能力校验 → Prompt（flush）→ Job/Item/Stage（commit）。
失败统一 rollback；`client_request_id` 幂等规则与 Prompt 去重/溯源保持不变。

### 5.3 图片角色自动恢复

自动归一化改变 Primary 时：读取新模块 `input_slots`，保留原 `image_id`，调整 role；
Primary 未变时完整模块身份与图片数据原样保留；不静默删除图片。

## 6. Git / CI

（提交后补记）

## 7. 验收 ZIP

（提交后生成 `handoff/NSFW_Studio_W1.2.1_Handoff.zip`，路径见交付汇报）

## 8. 未验证 / 限制

- 未启动 Studio / ComfyUI，未做浏览器人工点击验收；前端为组件级 + store 单元级验证；
- 未执行真实 GPU 工作流；
- Agent 仍只支持单文生图模块 + 可选 upscale；
- 全量后端 pytest 以 GitHub CI 为准。
