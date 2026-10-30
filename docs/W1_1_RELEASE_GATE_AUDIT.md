# 正式放行机制审计报告（W1.1-1）

> 审计对象：NSFW Studio V2 服务端新任务放行门禁。
> 审计日期：2026-10-30；基线 `1cf05e5`。
> 审计方式：源码只读审查 + 定向 API 测试（Mock 引擎，不启动 ComfyUI、不使用 GPU）。

## 1. 事实源

| 项 | 结论 |
| --- | --- |
| 唯一放行事实源 | `workflows/release_manifest.yaml`（服务端文件） |
| 读取方 | `backend/app/engine/release.py::load_release_manifest()`（`lru_cache`） |
| 状态计算 | `release_status(module_id, binding_version, binding_valid)` |
| 放行条件 | `registered && binding_valid && dependencies_ready && real_gate_passed && hardware_status != unsupported` |
| 未登记 binding | `entry is None` → `ready_to_run=false`（fail-closed） |
| 客户端 `release_status` | 不读取、不信任；仅按服务端解析出的真实身份判断 |

`default_profile_verified` 是独立语义：它只用于 UI 提示（慢速/未验证），**不参与** `ready_to_run`，
避免错误限制 `basic_generate` 等主力能力。

## 2. 入口清单与调用顺序

`ensure_modules_released()` 都在 `job_service.create_job()` 之前调用：

| # | 入口 | 代码位置 | 身份来源 | 结果 |
| --- | --- | --- | --- | --- |
| 1 | `POST /api/v1/jobs` | `backend/app/api/v1/jobs.py:63-66` | `resolve_requested_modules(settings, snapshot.workflow_modules)` | ✅ 创建前拒绝 |
| 2 | `POST /api/v1/agent/jobs` | `backend/app/api/v1/agent.py:130-134` | 同上 | ✅ 创建前拒绝 |
| 3 | `POST /api/v1/images/upscale` | `backend/app/api/v1/images.py:377-393` | `resolve_requested_modules(settings, [{"module_id": "upscale"}])` | ✅ 创建前拒绝 |
| 4 | `POST /api/v1/jobs/{id}/resume-remaining` | `backend/app/api/v1/jobs.py:153-161` | 原 Job `workflow_snapshot.modules`（服务端数据） | ✅ 子 Job 创建前拒绝 |
| 5 | `POST /api/v1/jobs/resume-interrupted` | `backend/app/services/job_service.py` | 已存在 Job 的原始身份 | ⚪ 可信恢复，不经过门禁 |

补充核查：`grep create_job(` 在 `backend/app` 中只有上述 3 处 API 调用；
`resume_remaining()` 仅被 API 4 与 `resume_interrupted_jobs()` 调用；
没有其他 API 能直接创建 Job。

## 3. 历史任务恢复语义

| 场景 | 行为 | 是否受新门禁 |
| --- | --- | --- |
| PAUSED 任务继续（`/jobs/{id}/resume`） | 原 Job 状态机内继续，不创建新 Job | 否（不需要） |
| INTERRUPTED 一键恢复（`/jobs/resume-interrupted`） | 原 Job 重排队或按原 Stage 续跑 | 否（可信路径） |
| History “继续剩余图片”（`/jobs/{id}/resume-remaining`） | 创建子 Job（新的任务身份） | ✅ 是 |
| Recipe / History 重新创建任务（`/jobs`） | 新 Job | ✅ 是 |

可信恢复路径保留原始 `module_id / module_version / binding_version / workflow_hash / binding_hash`，
不会为了新门禁升级或重写历史 Job 身份；因此不会破坏 `PAUSED / INTERRUPTED / RECOVERABLE` 流程。

## 4. 客户端绕过面

| 绕过尝试 | 结果 |
| --- | --- |
| 客户端传 `release_status.ready_to_run=true` | 无效：门禁不读取该字段 |
| 客户端只传 `module_id`，不传 binding | 无效：服务端 `resolve_requested_modules` 解析真实 binding |
| Agent 使用未放行模块 | 400 `WORKFLOW_NOT_RELEASED`（与 Web 同源） |
| 图库放大改用其他模块 | 入口固定 `upscale`，仍走门禁 |
| 用 History 子 Job 绕过 | `resume-remaining` 已加门禁 |
| 客户端携带完整 binding 身份走恢复 | 只影响 `resume-interrupted` 的原 Job，不能新建任务 |

## 5. 数据库残留

测试 `test_unreleased_anime_rejected_without_job_residue` 与
`test_unregistered_binding_rejected` 在拒绝前后统计 `Job` 行数，断言数量不变；
`test_history_resume_remaining_is_gated` 断言无新的 `resume_of_job_id` 子 Job。
门禁发生在 `job_service.create_job()` 之前，且 `ValidationError` 在请求事务内抛出，
不会 flush Job/Stage。

## 6. 定向测试证据

```text
tests/backend/test_workflow_release_gate_w11.py
tests/backend/test_agent_submission.py
tests/backend/test_anime_generate_module.py
tests/backend/test_workflow_release_w1.py
...
46 passed
```

关键用例：

- 临时 manifest 将 anime 标为未放行 → Web 提交 400 `WORKFLOW_NOT_RELEASED`，Job 数不变；
- 空 manifest → `basic_generate` 也被拒绝（未登记 fail-closed）；
- 生产 manifest → `basic_generate` 201 / binding v1；`img2img` 201 / binding v2；
- Agent 在空 manifest 下提交 anime → 400；
- `resume-remaining` 在空 manifest 下 400，且不产生子 Job；
- `resume-interrupted` 对 anime INTERRUPTED 任务仍可重排队（不受门禁破坏）。

## 7. 残余风险

1. `load_release_manifest()` 使用进程级 `lru_cache`：修改 manifest 后需重启后端
   （或未来提供显式刷新入口）。当前可接受，W2 可评估按 mtime 失效。
2. `dependencies_ready` 仍是人工登记，不是实际探测；本阶段按指令不做环境探测。
3. `workflow_hash` / `binding_hash` 变化不会自动使放行状态失效；依赖
   `resolve_requested_modules` 的 binding 合法性检查与 G0/CI。
4. anime 的 `real_gate_passed=true` 与审查前提冲突，等待独立审查决定是否隐藏（见
   `docs/W1_1_REPORT.md` §7）。
