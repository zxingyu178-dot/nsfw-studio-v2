# W2.0 完成报告 — Runtime Guard MVP

> 基线：`74ed8a96b126f382d5b7392730953aee0e026de4`（W1.2.2 完成）。
> 执行日期：2026-10-31。
> 一次完整交付：RuntimePreflightService + Preflight API + Job/Agent Gate + 最小前端 UI + 回归测试。
> 未新增 Migration、未修改冻结 Binding、未改 release_manifest 既有证据、未新建
> runtime_requirements.yaml、未自动下载模型/安装节点、未改 EngineRuntimeService 启停与
> 进程归属、未改 ComfyUI 执行核心、未改单队列架构、未开发 VRAM 调度/分辨率预测、未启动真实 GPU。

## 1. 交付内容

| 项 | 位置 |
| --- | --- |
| RuntimePreflightService | `backend/app/services/runtime_preflight_service.py` |
| Preflight API | `POST /api/v1/engine/preflight`（`backend/app/api/v1/engine_runtime.py`） |
| `/jobs` Gate | `backend/app/api/v1/jobs.py`（创建前 + resume-remaining） |
| `/agent/jobs` Gate | `backend/app/api/v1/agent.py` |
| 前端 API | `frontend/src/api/client.ts::engineRuntimeApi.preflight` |
| 前端 UI | `frontend/src/pages/Generate/workbench/InspectorPanel.tsx` |
| 回归测试 | `tests/backend/test_runtime_preflight.py`、`InspectorPanel.workflow.test.tsx` |

## 2. 设计：复用优先

| 复用对象 | 用途 |
| --- | --- |
| `ComfyUIAdapter.health()` | `/system_stats` 在线状态与版本 |
| `ComfyUIAdapter.load_binding()` | workflow.json / binding.yaml / 双 Hash 校验 |
| `resolve_workflow_modules()` | 服务端重新解析真实执行身份（不信任客户端 Hash） |
| `scripts/validate_workflows.py` 的节点/字段模型 | 自动依赖解析采用同一套节点/字段映射 |
| `release_manifest.yaml` | 正式放行仍由既有门禁负责，W2.0 只增加运行条件检查 |

没有新增第二套引擎管理、工作流注册或依赖清单。

## 3. 检测语义

### 3.1 状态

| 状态 | 含义 | 提交处理 |
| --- | --- | --- |
| `READY` | 引擎在线、Binding/节点/模型/版本均满足 | 允许继续 |
| `BLOCKED` | 已确认缺节点、缺模型或版本不满足 | 拒绝（`RUNTIME_PREFLIGHT_BLOCKED`） |
| `UNKNOWN` | 引擎离线、Binding 无法验证、节点/模型接口失败、未知 Loader | 拒绝（`RUNTIME_PREFLIGHT_UNKNOWN`） |

`UNKNOWN` 绝不按 READY 放行。

### 3.2 动态检测

- 引擎：`ComfyUIAdapter.health()`（`/system_stats`）；
- Binding：`load_binding()`，真实 workflow_hash / binding_hash 必须一致；
- 节点：从 `workflow.json` 提取唯一 `class_type`，逐个 `GET /object_info/{class}`；
  404 → BLOCKED，请求失败 → UNKNOWN；同节点只查一次；
- 模型：从 `requirements.models`（优先）与 workflow 的 Loader 节点自动提取
  （`UnetLoaderGGUF` / `UNETLoader` / `CLIPLoader` / `VAELoader` / `LoraLoader` /
  `LoraLoaderModelOnly` / `UpscaleModelLoader`），按目录 `GET /models/{folder}` 精确比对文件名；
  目录只请求一次，不做模糊匹配；
- 未知模型加载节点（class_type 含 `Loader` 但无解析规则）→ UNKNOWN；
- 版本：Binding 声明 `comfyui_min_version` 时比较 `system_stats` 版本；
  未声明的旧 Binding 只显示提示，不臆造最低版本。

### 3.3 缓存（进程内，无 Redis/数据库）

| 缓存 | TTL |
| --- | --- |
| system_stats | 30s |
| node `/object_info` | 60s |
| model `/models/{folder}` | 30s |
| workflow 依赖解析 | 按 `(module_id, workflow_hash, binding_hash)`，Hash 变化即重新解析 |

## 4. 调用链

普通任务：
`resolve_workflow_modules → ensure_modules_released → Runtime Preflight → attach_ai_prompt → create_job → commit`

Agent / CLI：
`resolve_agent_workflow_modules → ensure_modules_released → validate_agent_primary →
Runtime Preflight → attach_ai_prompt → create_job → commit`

`/jobs/{id}/resume-remaining`：用原 Job 的固定工作流身份执行 Preflight。
检测失败发生在 Prompt 关联与 Job/JobItem/JobStage 创建之前，失败请求不产生任何残留。
既有幂等重放规则不变；PAUSED/CANCELLED/INTERRUPTED 状态机与批量恢复逻辑未改。

Mock / Unbound 兼容：`provider=mock` 直接返回 READY（跳过真实依赖检测并标注）；
非 comfyui 且非 mock（如 unbound）返回 UNKNOWN，不强制连接真实 ComfyUI。

## 5. Preflight API

`POST /api/v1/engine/preflight`

请求：`{"module_ids": ["basic_generate", "upscale"]}`

响应：`status` + `engine{online,version,detail}` + 每个模块的
`module_id / binding_version / workflow_hash / binding_hash / status /
missing_nodes / missing_models / missing_requirements / unknown_reasons / notes / cache_hit` +
`checked_at / cache_hit`。

服务端重新解析真实工作流身份，不接受客户端 Hash；该 API 仅用于 UI 诊断，
实际提交仍由后端 Gate 再次检测。

## 6. 前端最小接入

`InspectorPanel` 工作流区域新增「运行环境 / 检查运行环境」：
- 读取当前 `workflowModules`（主模块 + 可选 upscale）；
- 点击调用 `/engine/preflight`；
- 显示 READY / BLOCKED / UNKNOWN、缺失节点、缺失模型、版本/离线原因；
- 工作流或高清开关变化时清除过期结果；
- 不轮询、不做检测中心、不改变三栏结构。

## 7. 测试

### 7.1 后端 `tests/backend/test_runtime_preflight.py`（15 tests，Mock HTTP）

1. 节点与模型全部存在 → READY；
2. 缺少自定义节点 → BLOCKED；
3. 缺少模型文件 → BLOCKED；
4. ComfyUI 离线 → UNKNOWN（且不再请求节点/模型）；
5. Binding Hash 不一致 → UNKNOWN（拒绝）；
6. 未知模型加载节点 → UNKNOWN；
7. 缓存命中与 TTL 过期刷新；
8. 多模块 Pipeline 检测；
9. `/jobs` Gate 拦截时 Prompt / Job / JobStage 无残留；
10. `/agent/jobs` Gate 拦截时无残留；
11. Mock 环境 → READY；Preflight API Mock 兼容；
12. Preflight API 使用真实身份解析 + ComfyUIAdapter（HTTP 全 Mock）；
13. 静态测试：当前全部正式 Binding 的模型加载节点均有解析规则。

### 7.2 前端

`InspectorPanel.workflow.test.tsx`：READY / BLOCKED（缺节点/模型明细）/ UNKNOWN 显示正确。

## 8. 测试结果

（提交后由 CI 补记；开发期定向测试结果见交付汇报）

## 9. Git / CI

（提交后补记）

## 10. 验收 ZIP

（提交后生成轻量包：核心源码变更 + 报告 + 测试记录 + Git 信息）

## 11. 未验证 / 限制

- 未启动真实 ComfyUI、未执行 GPU 工作流；真实 `/object_info` 与 `/models` 响应格式按
  ComfyUI 官方 API 设计，但最终仍需真实环境确认；
- 第一版只验证文件名存在，不计算模型 SHA256、不自动下载；
- 分辨率/显存风险预测留给 W2.1；
- 历史 Job 恢复（PAUSED/INTERRUPTED）保持原语义，`resume-interrupted` 不新增 Preflight。
