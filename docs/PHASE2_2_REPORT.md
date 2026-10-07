# NSFW Studio V2 — Phase 2.2 验收报告（Data Consistency & Recovery Closure）

> 日期：2026-10-07 ｜ 版本：0.3.2 ｜ 基线：v0.3.1 (86787fa) ｜ 分支：fix/phase2-data-consistency
> 执行：TRAE Code Agent。短收口任务：修数据一致性漏洞，不新增任何产品功能。
> 本阶段完成后 Phase 2.x 收口结束，正式进入 Phase 3。

## 一、修复清单（对应合同章节）

| 章节 | 缺陷 | 修复 |
| --- | --- | --- |
| §1（P0） | 多输出导入非原子：第一张落盘 + commit，第二张校验失败 → Item FAILED 但图 1 残留 | 拆分为 `prepare_image_output()`（全部先校验、只分配身份不落盘）+ `import_outputs_transaction()`（全部写 temp → 全部移动 → **单事务**写入全部 Image）；任一步失败：回滚 DB + 删除本批次全部正式文件 + 清理 temp。`import_adapter_outputs()` 不再循环调用内部 commit 的单图函数 |
| §2（P0） | 崩溃恢复后 Job 终态不归并：Item 恢复 COMPLETED 但 Job 停留 INTERRUPTED | 恢复每个 Job 后新增 `_finalize_recovery()`：全部 Item COMPLETED → Job COMPLETED + completed_count + finished_at + `JOB_RECOVERED_COMPLETED` 事件；仍有 INTERRUPTED/QUEUED → 保持 INTERRUPTED 并更新 completed_count |
| §2 附带（实测发现） | **Worker 任务被取消（进程退出/停机超时）时 `finally` 仍写 Job 终态** → 未完成 Job 被误标 COMPLETED | `process_job` 重构：执行体拆到 `_execute_job()`，终态只在正常返回时由 `_finish_job()` 写入；`asyncio.CancelledError` / 意外异常一律不写终态，保持 RUNNING 现场交由下次启动恢复（§三十七） |
| §3（P1） | Resume 可能静默升级 Workflow：Job 列 v1 而 workflow_snapshot 取自当前 settings（v2） | `resume_remaining()` 不再接收 module_identity：完整继承 Parent 的 workflow_snapshot_json + module_id/module_version/provider/binding_version/workflow_hash；原 binding 消失时执行期明确报 `BINDING_NOT_FOUND`，绝不静默升级 |
| §4（P1） | ComfyUI 取消误伤其他任务：无条件 `POST /interrupt`（全局行为） | 先读 `GET /queue` 判断 target 位置：pending → 只 delete、**绝不 interrupt**；target 正是当前 running → 才允许 interrupt；target 不在队列（或 running 是别人的 prompt）→ 什么也不做 |
| §5 | 文档措辞与实现对齐 | "导入失败全回滚 / 整批原子"在 §1 完成后成为事实；同步 PHASE2_1_REPORT（交叉引用）、IMAGE_MODEL、RECOVERY_SPEC、COMFY_ADAPTER、JOB_STATE_MACHINE、QUEUE_SPEC、TEST_REPORT、DEV_LOG、TASKS、CHANGELOG |

## 二、验证结果（如实）

```
快速套件（CI 同口径，无 ComfyUI）：129 passed
  新增 9 例：
  - test_image_service.py：批次原子 3 例（合法+损坏整批失败且无残留 / 双合法同批成功 /
    移动阶段失败时第一张也随回滚删除）
  - test_phase22_consistency.py：恢复归并 Case A（1 张崩溃→引擎已完成→Job COMPLETED 且
    JOB_RECOVERED_COMPLETED 事件）/ Case B（3 张前 2 张完成、第 3 张无法确认→Job INTERRUPTED
    + completed_count=2）/ Resume 身份继承（Parent=v1、当前=v2 → Child 全字段仍 v1，
    且数据库列 == workflow_snapshot.modules[0]）
  - test_comfyui_resilience.py：取消边界 3 例（pending 只 delete 不 interrupt /
    running 目标才 interrupt / 别人 running 时不 interrupt 且不写队列）
前端 npm run build：通过（tsc + vite）
真实 ComfyUI：本阶段不需要生成图片（合同 §6），全部用 Mock / stub 离线验证
develop / main CI：见 GitHub Actions（推送后记录）
```

## 三、关键行为契约（Phase 2.2 起固定）

```text
导入原子性：
  一个 Item 的本次输出批次 = 全部校验 → 全部 temp → 全部移动 → 单事务入库
  任一步失败 → DB 回滚 + 本批次全部正式文件删除 + temp 清理（无半成功资产）

恢复归并：
  恢复核对后重算 completed_count；
  全部 Item COMPLETED → Job COMPLETED（finished_at + JOB_RECOVERED_COMPLETED）
  否则保持 INTERRUPTED（可续跑），禁止 INTERRUPTED 覆盖已全完成的 Job

取消边界（ComfyUI）：
  pending target → 仅 POST /queue delete
  running target → 允许 POST /interrupt
  其他 running（非 target）→ 禁止任何全局打断

Cancellation（Worker 自身被取消）：
  不写 Job 终态；RUNNING 现场由下次启动恢复为 INTERRUPTED

Resume：
  完整继承 Parent 的 Workflow 身份与快照；升级 Workflow 请创建新 Job
```

## 四、限制与说明

- 恢复归并只在启动恢复路径执行；正常运行路径的终态仍由 `_finish_job` 写入；
- `priority` 字段仍仅保留不参与排序（Phase 2.1 §6 结论不变）；
- 本阶段未新增高清 / 图生图 / 参考图 / 新模型 / 新 WorkflowModule / Agent / 手机端。