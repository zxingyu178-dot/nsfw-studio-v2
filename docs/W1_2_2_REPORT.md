# W1.2.2 完成报告 — Integrity Closure

> 基线：`1b9a15b9db76f33acaaabce6db385cd93b19b045`（W1.2.1 完成）。
> 执行日期：2026-10-31。本阶段只修复 W1.2.1 剩余边界问题，不增加新功能。
> 未新增 WorkflowModule、未修改冻结 Binding、未新增 Migration、未改 ComfyUI 引擎、
> 未改单队列架构、未开发 W2 Runtime Preflight、未增加 UI 功能、未启动真实 GPU、
> 未重构 Prompt 模块。

## 1. 缺陷修复说明

### A. 所有入口严格拒绝空工作流 ID

| 层 | 修复 |
| --- | --- |
| API Schema | `WorkflowModuleRefModel.module_id` 增加 `field_validator`：去首尾空格，`""` / 纯空白直接 422 |
| factory/service | `resolve_workflow_modules` 遇到显式空/纯空白 `module_id` 抛出 `EngineError("MODULE_ID_INVALID")`，不再 `continue` 后回落默认 |
| `/jobs` | `workflow_modules=[]` 仍走服务器默认；显式空 ID 在 Prompt 关联前被拒绝 |
| Agent API | 原有 `None` / `""` / `"   "` / unknown 行为保持不变（`None` 默认、空字符串 422、unknown 400） |
| CLI | 严格区分 `args.module is None` 与显式 `""`；空白值在任何 HTTP 请求之前返回失败 |

### B. Prompt 归档与幂等指纹解耦

- `_request_fingerprint` 默认只覆盖**用户请求语义**，排除服务端生成的
  `source_prompt_id` / `source_prompt_version_id`。
- 原 Job 快照仍保留 Prompt 溯源 ID（`workbench_snapshot_json` 不改写）。
- 历史兼容：若存储指纹与新语义指纹不一致，则按旧算法 + 历史快照重建旧指纹，
  并确认历史快照的语义指纹与当前请求一致后允许重放；否则仍
  `IDEMPOTENCY_KEY_CONFLICT`。
- 无数据库迁移；`client_request_fingerprint` 列继续使用，新 Job 写入语义指纹。
- 并发重复提交：早期幂等命中直接返回原 Job；新 Prompt 仅在当前事务中 flush，
  请求结束/失败 rollback，不留下孤立 Prompt；IntegrityError 分支 rollback 后返回原 Job。

## 2. 新增回归测试清单

### 后端

`tests/backend/test_workflow_module_id_boundaries.py`：

- `/jobs` `workflow_modules=[]` → 201，使用服务器默认 `basic_generate`；
- `/jobs` `workflow_modules=[{"module_id":""}]` → 422，Prompt / Job / JobStage 均不增加；
- `/jobs` `workflow_modules=[{"module_id":"   "}]` → 422，同上；
- factory 层直接传纯空白 → `EngineError(MODULE_ID_INVALID)`（不依赖 Pydantic）；
- factory 层真正空请求 `[]` → 使用服务器默认。

`tests/backend/test_agent_submission.py`（W1.2.2 新增）：

- Prompt 归档后，相同 `client_request_id` + 相同内容重放 → 返回原 Job，不新建 Prompt；
- W1.2.2 之前的历史指纹（含 Prompt 溯源）在 Prompt 归档后仍可重放；
- 原有用例继续保持：空字符串 / 纯空白 422、未知模块 400、未放行拒绝、幂等冲突 409。

`tests/backend/test_agent_generate_cli.py`（W1.2.2 新增）：

- `--module ""` / `--module "   "` → 返回 2，且零 HTTP 调用。

### 前端

本阶段未修改前端代码；继续运行全量 typecheck / vitest / build / store regression 作为回归。

## 3. 测试结果

| 项 | 结果 |
| --- | --- |
| 后端定向（module_id / agent / CLI / phase7 guards / reference） | 49 passed |
| 后端全量（CI） | 645 passed / 3 skipped（含 G0 step 通过） |
| 前端 typecheck / vitest / build | 通过；97 files / 486 tests；build 394.43 kB |
| Store regression | 11 passed |
| G0 | checked=6 errors=0 warnings=14 |

## 4. 文档同步

- `backend/app/api/v1/agent.py` 旧注释“assign_ai_prompt（内部 commit）”已改为
  “Prompt 关联（commit=False）”。
- `AGENTS.md`、`docs/AGENT_SUBMISSION.md` 补充事务与幂等指纹语义；
- `DEV_LOG.md`、`TASKS.md` 记录本阶段。

## 5. Git / CI

| 项 | 值 |
| --- | --- |
| 基线 | `1b9a15b9db76f33acaaabce6db385cd93b19b045` |
| W1.2.2 提交 | `306139289ba112dca07e2ca6984aaf35ee6defdf` |
| CI run | `41176466877` |
| 后端 | 645 passed / 3 skipped（含 G0 step 通过） |
| 前端 | typecheck + 97 files / 486 tests + build + store regression 11 passed |
| 远端同步 | 本地 HEAD == `origin/main` |

随后仅文档提交，不改变代码；最终 HEAD 的 CI 结果见交付汇报。

## 6. 验收 ZIP

`handoff/NSFW_Studio_W1.2.2_Review.zip`（轻量包：阶段报告 + Git 信息 + 变更文件清单 + 源码 diff）。

## 7. 未验证 / 限制

- 未启动 Studio / ComfyUI，未执行真实 GPU 工作流；
- 前端未改动，仅做全量回归；
- 历史指纹兼容仅覆盖 API 创建路径（stage_configs 内部直调路径不参与对外幂等）。
