# W1.2 完成报告 — 工作流选择与 AI 默认工作流接入

> 基线：`01e5597aaf5bc46e0e935235e4cd724d281e7413`（W1.1 完成）。
> 执行日期：2026-10-31。
> 本阶段不新增工作流模块、不建复杂工作流管理页、不建设 GPU 监控/调度、不改单队列架构、
> 不改 ComfyUI 引擎、不下载模型、不安装节点、不启动真实 GPU 工作流、不修改冻结 binding、
> 不迁移数据库、不重构三栏工作台。

## 1. 目标与结果

| 项 | 结果 |
| --- | --- |
| W1.2-A 前端工作流选择 | ✅ 文生图 / 图片生成候选按能力区分，process 与 generate 不混用 |
| W1.2-B Agent 默认/指定工作流 | ✅ `module_id` 可选；默认走既有 settings 解析；服务端能力校验 |
| W1.2-C Agent 提交副作用 | ✅ 解析 → 放行 → 能力检查通过后才写 Prompt / 建 Job |
| W1.2-D CLI 与 AI 选择 | ✅ 不默认 anime；`--list-workflows`；输出实际模块 |
| W1.2-E 文档统一 | ✅ 提交标准 / Agent / AI 生图文档口径对齐 |

## 2. W1.2-A 前端工作流选择

### 2.1 根因

`InspectorPanel` 图片模式使用 `moduleCatalog.filter(isImageStartModule)`，而
`isImageStartModule` 要求 `allowed_job_kinds` 包含 `process`；`img2img` 与
`reference_generate` 实际只允许 `generate`，因此被错误排除。

### 2.2 修复

`frontend/src/stores/workbenchStore.ts`：

- 新增 `allowsJobKind()`：显式区分 generate / process；
- `textPrimaryCandidates()`：`available=true` + `isReleaseReady` + `is_generative=true` +
  `input_required=false` + 允许 `generate`；
- 新增 `imagePrimaryCandidates()`：`available=true` + `isReleaseReady` + `is_generative=true` +
  声明有效图片输入槽 + 允许 `generate`；
- `availableImageModuleIds()` 改为图片生成候选（process-only 的 upscale 不再混入）；
- `isImageStartModule()` 保留原 process 语义（不再被 UI 图片选择复用）；
- `defaultTextModuleId()` 只读取 `/modules` 的 `is_default`（服务端配置），
  UI 不再硬编码 `basic_generate` 作为默认；
- `normalizeModules()` 文生图分支：优先保留用户已选择的可用候选，否则切到服务端默认；
  初始工作台不再写死默认模块（空列表由服务端解析）；
- `setUpscaleEnabled()` 不再用 `basic_generate` 兜底。

`InspectorPanel.tsx`：

- 图片模式改用 `imagePrimaryCandidates()`；
- 保留 `PopoverSelect` 下拉与 `setPrimaryModule` 的输入图角色重映射（source ↔ reference）。

后端：`module_availability()` / `GET /modules` 新增 `is_default`，作为 UI 默认选择的唯一来源。

### 2.3 前端工作流选择验收记录

| 验收项 | 证据 | 结果 |
| --- | --- | --- |
| 文生图显示基础生成 + 动漫生成 | `InspectorPanel.workflow.test.tsx`：文本模式 options 含“基础生成/动漫生成”，不含图生图/参考图/高清 | ✅ |
| 图片模式显示 img2img + reference_generate | 同测试：图片模式 options 含“图生图/参考图生成”，不含文生图/高清 | ✅ |
| 未放行工作流自动隐藏 | 同测试：未放行 anime 被隐藏，唯一候选退回静态标题；`workbenchStore.releaseStatus.test.ts` 候选过滤 | ✅ |
| 手动切 reference，role 变 reference | `workbenchStore.referenceRole.test.ts`：`setPrimaryModule('reference_generate')` 后 role=reference | ✅ |
| 切回 img2img，role 变 source | 同测试：切回后 role=source，图片未丢 | ✅ |
| 默认工作流与服务端配置一致 | `workbenchStore.releaseStatus.test.ts`：`is_default=true` 的模块成为 Primary；`defaultTextModuleId` 只认服务端标记 | ✅ |
| 提交的 workflow_modules 与选择一致 | `setPrimaryModule()` 写入 `workflow_modules[0]`；`snapshotFromState()` 原样提交（既有测试覆盖） | ✅ |

说明：未启动浏览器/Studio/ComfyUI 做人工点击验收；本轮为组件级 + store 单元级验证，
不使用真实 GPU、不生成图片。

## 3. W1.2-B Agent 默认/指定工作流

### 3.1 契约

`AgentJobRequest.module_id` 从静态 `Literal["basic_generate","anime_generate"]`
改为 `str | None = None`：

- 不传 / `null` → `resolve_workflow_modules(settings, [])` 解析服务器当前默认；
- 显式传入 → 使用指定模块；
- 不再有静态枚举，后续新增工作流无需改 schema；
- `upscale=true` → 在实际选定的 Primary 后追加 `{"module_id":"upscale"}`；
- 不开放任意 Pipeline / 输入图片链路。

### 3.2 服务端校验（`backend/app/services/agent_service.py`）

| 检查 | 失败错误码 |
| --- | --- |
| 模块已注册（registry 有对应 module_version） | `AGENT_MODULE_UNKNOWN` |
| binding 可解析（comfyui 指纹校验） | `AGENT_MODULE_UNKNOWN` / `AGENT_MODULE_UNAVAILABLE` |
| `ready_to_run=true`（正式放行） | `WORKFLOW_NOT_RELEASED` |
| `available=true` | `AGENT_MODULE_UNAVAILABLE` |
| `is_generative=true` | `AGENT_MODULE_NOT_TEXT_GENERATE` |
| `input_required=false` | `AGENT_MODULE_NOT_TEXT_GENERATE` |
| `allowed_job_kinds` 含 `generate` | `AGENT_MODULE_NOT_TEXT_GENERATE` |

不自动降级、不静默切换；默认工作流未放行时直接拒绝。

### 3.3 Job 快照

`workbench_snapshot.workflow_modules` 与 `workflow_snapshot.modules` 都记录服务端解析出的
实际模块身份（含 provider / binding_version / 双指纹），不再记录空的默认选择。

## 4. W1.2-C Agent 提交副作用

原顺序：`assign_ai_prompt`（内部 `create_prompt` 会 `session.commit()`）→ 放行门禁。
新顺序：

1. 解析实际工作流；
2. 正式放行检查；
3. Agent 模块能力检查；
4. 通过后才 `assign_ai_prompt` 并关联 Prompt；
5. `job_service.create_job()`。

回归测试断言：未知模块 / 未放行默认 / process 模块三种拒绝场景，Prompt、Job、JobStage
行数均保持不变；原有 Prompt 去重、幂等、溯源逻辑不变。

## 5. W1.2-D CLI

`scripts/agent_generate.py`：

- `--module` 默认 `None`（不再默认 `anime_generate`，不再有 choices 白名单）；
- 不传 `--module`：Agent 加固路径省略 `module_id`，由服务端解析默认；
- `--list-workflows`：读取 `/modules`，只列出 `available + ready_to_run + is_generative +
  input_required=false + 允许 generate` 的模块；
- 输出打印 `实际工作流=[...]`（来自响应的 `workflow_snapshot.modules`），文件名也用实际模块；
- 旧 `/jobs` 路径若未指定模块，先从 `/modules` 的 `is_default` 解析 Primary，再按需追加 upscale。

## 6. W1.2-E 文档

- `docs/WORKFLOW_SUBMISSION_STANDARD.md`：
  - 新增 §5.1 新工作流提交清单（Python 模块 / registry / binding / README / requirements+performance /
    单元测试 / release_manifest 初始未放行）；
  - 明确 AI 不得自行声明 G3/G4 已通过；
  - §9 放行状态从“建议实现”改为“W1/W1.1 已实现”，补充新任务门禁与可信恢复通道；
  - §10 anime 改为“G3 已有证据（slow）、G4 未测”；reference 明确区分 Studio 768 与 640/20 直连 API。
- `docs/AGENT_SUBMISSION.md`：移除静态白名单，补充默认/指定工作流、错误码、检查顺序、AI 提交规范。
- `docs/AI_IMAGE_GENERATION_GUIDE.md`：CLI 示例不再默认 anime；workflow_modules 空数组 = 服务端默认；
  anime/reference 证据口径；AI 系统提示词要求先询问默认还是指定。

## 7. 测试结果

### 7.1 后端定向

```text
tests/backend/test_agent_submission.py            14 passed
W1.2 相关定向（含 gate / release / anime / img2img / reference / phase22） 47 passed
```

覆盖：不传 module_id 使用默认、显式 basic/anime、未知模块、未放行默认不降级、
process 模块拒绝、upscale 追加、拒绝无 Prompt/Job/Stage 残留、W1.1 门禁与恢复不受影响。

### 7.2 前端

```text
typecheck 通过
vitest: 97 files / 476 tests passed
build 通过（393.55 kB JS）
```

新增：`InspectorPanel.workflow.test.tsx`（3 tests）、`workbenchStore.releaseStatus.test.ts`
新增 W1.2 候选/默认用例（15 tests）。

### 7.3 G0

```text
[G0] checked=6 errors=0 warnings=14
```

## 8. 新增与修改文件

新增：

- `backend/app/services/agent_service.py`
- `frontend/src/pages/Generate/workbench/InspectorPanel.workflow.test.tsx`
- `docs/W1_2_REPORT.md`

修改：

- `backend/app/schemas/agent.py`、`backend/app/api/v1/agent.py`
- `backend/app/engine/factory.py`、`backend/app/api/v1/modules.py`
- `frontend/src/stores/workbenchStore.ts`、`frontend/src/types/workbench.ts`
- `frontend/src/pages/Generate/workbench/InspectorPanel.tsx`
- `frontend/src/stores/workbenchStore.releaseStatus.test.ts`、`workbenchStore.referenceRole.test.ts`
- `frontend/src/pages/Generate/workbench/InspectorPanel.count.test.tsx`、
  `frontend/src/pages/Generate/SettingsPane.size.test.tsx`
- `scripts/agent_generate.py`
- `tests/backend/test_agent_submission.py`
- `docs/WORKFLOW_SUBMISSION_STANDARD.md`、`docs/AGENT_SUBMISSION.md`、
  `docs/AI_IMAGE_GENERATION_GUIDE.md`
- `DEV_LOG.md`、`TASKS.md`

## 9. Git / CI

（提交后补记；最终以交付汇报为准）

## 10. 未验证 / 限制

- 未启动 Studio / ComfyUI，未做浏览器人工点击验收；前端为组件级 + store 单元级验证；
- 未执行真实 GPU 工作流；
- Agent 仍只支持单文生图模块 + 可选 upscale，不开放 img2img / reference 输入图片链路；
- 依赖探测仍为人工登记（W2）；像素预算仍为技术债。
