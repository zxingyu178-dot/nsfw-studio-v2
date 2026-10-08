# PHASE4_REPORT — History + Provenance + Generic Module I/O Contract（v0.5.0）

> 日期：2026-10-08 ｜ 版本：0.5.0 ｜ 基线：v0.4.0 (78e7ee2) ｜ 分支：feature/phase4-history-provenance
> 目标：历史正式可用、溯源与派生图恢复正确、底层真正准备好接 Reference / Img2Img（本阶段不新增生成模型）。

## 1. 交付内容

### Task 0（P0 修复，先行）

| 问题 | 修复 |
| --- | --- |
| v0.3.x 库执行 0007 后历史 Job 没有 Stage（已复现：QUEUED Job → `job_stages=0` → Worker 领取即 FAILED，原任务完全不执行） | 新增 `0008_pipeline_backfill`：`jobs WHERE NOT EXISTS job_stages` → Stage0（身份继承 Job 列）+ 每个 JobItem 一条 StageItem（状态/engine_job_id/图片关系映射）；**不改历史 Job 本身状态**；不改 0007 |
| StageItem 无 Seed / 历史假 Seed | 新增 `0009_execution_fingerprint`：`jobs/job_stages.binding_hash` + `job_stage_items.seed`；回填 basic Stage 的 seed、清空 upscale 产出图与 process Job 的假 Seed |

### Task 1-4（执行指纹 / 通用模块契约）

- **binding_hash**：`sha256(binding.yaml)[:16]` 进入 EngineBindingRef / Job / JobStage / workflow_snapshot /
  Job & Stage API / Image metadata；改 binding.yaml（inputs/defaults/save_image_*/capabilities）→
  `BINDING_HASH_MISMATCH`；binding 自描述（module/provider/binding_version）不一致 →
  `BINDING_IDENTITY_MISMATCH`；老 Job `binding_hash=null` 兼容（comfyui 下采纳磁盘当前值）。
- **ModuleCapabilities I/O 契约**：`uses_seed / input_kind / output_kind / parent_policy /
  output_cardinality`；ImageService 判定 kind/parent **全部按能力**，"input_image 推断 upscaled"删除。
- **StageItem.seed**：执行前落库（uses_seed=false → NULL）；manual upscale Image.seed=null。
- **EngineAdapter `upload_input_image()`**：正式契约（默认 `ENGINE_INPUT_UNSUPPORTED`，系统性）；
  ComfyUI/Mock 实现；UpscaleModule 去 getattr；构建请求阶段的系统性错误与提交阶段一致（队列暂停）。

### Task 5-10（History / Provenance / 产品修复）

- `GET /api/v1/history`：来源=jobs；bucket/source 筛选；沿 `resume_of_job_id` 归组为任务族
  （`root_job_id` 计算字段，两级展示）；前端 HistoryTab（任务卡 / 筛选 / Drawer / 三操作）。
- `GET /api/v1/images/{id}/workbench`：沿 parent 链追溯**根生成 Job**（图库手动高清不再恢复空 Prompt）；
  导入图 → 404 `IMAGE_NO_GENERATION_CONTEXT`；返回根图 Seed（"使用原图 Seed"）。
- 执行身份恢复（Task9）：恢复快照携带完整身份，提交时固定原版本；指纹/provider 不一致拒绝。
- `GET /api/v1/images/{id}/provenance`：parent/root/scale/job/stage/module/双指纹/seed；图库详情简洁展示 + 折叠。
- 前端 `workflowModules: WorkflowModuleRef[]`（upscaleEnabled 降级为派生值）。

### Task 11（输入缓存治理）

- Studio Input Registry（`DataRoot/engine_inputs.json`）+ 启动 TTL 清理：只处理 `NSFWStudio_inputs/` 下、
  已登记、无 RUNNING/INTERRUPTED 引用、超过 TTL（默认 24h）的文件；未配置 `comfyui.input_dir` 安全跳过；
  本机 config.local.yaml 已补 `output_dir / input_dir / input_ttl_seconds`。

## 2. 测试证据

### 快速套件（CI 同口径）

```text
.venv\Scripts\python -m pytest tests/backend --ignore=tests/backend/test_comfyui_integration.py
结果：168 passed（v0.4.0 的 147 例 + Phase 4 新增 21 例）
```

新增/更新用例：

- `test_phase4_backfill.py`（1 例）：**真实 v0.3.2 库**四种状态 Job → 0007+0008+0009 → Stage 回填正确、
  历史 Job 状态不变、StageItem.seed 回填；启动应用后 **QUEUED Job 被同一 Worker 真实执行 → COMPLETED**。
- `test_phase4_contract.py`（12 例）：能力声明 / 能力驱动 kind（input_image_id 不再推断）/
  StageItem 与 manual Seed / EngineAdapter 输入契约（含系统性）/ binding_hash 全链路 +
  BINDING_HASH_MISMATCH / pinned 身份解析（固定原版本、指纹/provider 拒绝、老 Job 兼容）/
  Input Registry TTL 清理边界。
- `test_phase4_history_provenance.py`（8 例）：History 归组（A→B→C 一族）与筛选 / 派生图追溯根生成 Job /
  process Job 追溯 / 导入图 404 / Provenance 全链路。
- `test_comfyui_binding.py` 新增 3 例：BINDING_HASH_MISMATCH、自描述不一致拒绝、**只改 binding.yaml
  （workflow.json 不动）→ binding_hash 必变且老 Job 拒绝**。
- Phase 3 的 12 场景与 Phase 2.x 回归全部继续通过（未修改断言语义）。

### 全量套件

本阶段**未重跑**真实集成套件（3 例）——合同 Task13 明确"不再跑批量真实生图"，由下述最短 smoke 覆盖。

### 真实 ComfyUI 最短 smoke（Task13）

```text
1 张基础（768×1024，真实 Qwen-Image 2.1 UC，冷启动约 10.7 分钟，seed=1501957504）
  → 4x 高清（3072×4096，15.4MB，seed=null，parent 正确）
  → History（completed 筛选命中任务族）→ Gallery（父子互查）→ 从高清图打开工作台
  → 恢复原 full_prompt + 根图 Seed + 完整执行身份（双指纹）
```

| 检查点 | 证据 |
| --- | --- |
| Stage 身份 | basic `wf=f45c54cbd48ab058 / bd=a7911ab7a6c1d1be`；upscale `wf=8232a833dc049803 / bd=6a7a21944d428ef6` |
| StageItem.seed | stage0=1501957504；stage1=null（upscale 不使用 Seed） |
| 高清图 | kind=upscaled、`images/upscaled/`、parent=原图、**恰 4 倍**、seed=null |
| 工作台恢复 | full_prompt 原样、seed=根图 Seed、`seed_mode=random`、workflow_modules 带双指纹 |
| Provenance | stage_index=1 / module=upscale / provider=comfyui / seed=null |
| Input Registry | `engine_inputs.json` 真实记录上传（TTL 未到 → 不误删） |

smoke 使用独立临时 DataRoot（`temp/nsfw-studio-v2-p4-smoke-data`），脚本与日志在 `temp/`（不进仓库）。

### 前端

```text
npm run build → tsc --noEmit 通过 + vite build 通过（v0.5.0）
```

### CI（GitHub Actions）

```text
develop: 见 TASKS.md / DEV_LOG.md 的最终记录
main:    见 TASKS.md / DEV_LOG.md 的最终记录
```

（最终 CI run id 在发布收尾提交中记录，与 Phase 3 的流程一致。）

## 3. 验收标准对照

| 要求 | 结果 |
| --- | --- |
| 0008 修复历史 Job 无 Stage；不改 0007；不改历史 Job 状态 | ✅ 真实 v0.3.2 升级测试（含 QUEUED 可执行） |
| binding.yaml 改动必须触发 hash 变化（BINDING_HASH_MISMATCH） | ✅ 单测：只改 yaml / workflow.json 不动 |
| kind/parent/seed 由 ModuleCapabilities 决定（禁止推断） | ✅ ImageService 改造 + 回归用例 |
| EngineAdapter 输入图片正式契约（去 getattr；不支持明确报错） | ✅ `upload_input_image` + ENGINE_INPUT_UNSUPPORTED（系统性） |
| StageItem Seed 正式化（upscale=NULL；manual Image.seed=null） | ✅ 测试覆盖 |
| 历史正式接 Job（列表/筛选/Drawer/操作） | ✅ /history API + HistoryTab |
| Resume 归组（两级别，不建复杂树） | ✅ root_job_id + A→B→C 一族用例 |
| 派生图 → 工作台追溯根生成 Job | ✅ 含 process Job 追溯与导入图 404 |
| 执行身份恢复（不偷偷跑新版 Workflow） | ✅ pinned identity + 指纹拒绝用例 |
| WorkflowModules 前端列表化 | ✅ `WorkflowModuleRef[]`（保存/恢复保留身份） |
| ComfyUI 输入缓存治理（只清 Studio 自己的；不 rm -rf） | ✅ Registry + TTL（含边界单测） |
| 禁止项（Img2Img / Reference / FaceID / ControlNet / 视频 / Agent / 手机端） | ✅ 未发生；留待 Phase 5 |

## 4. 环境说明（如实记录）

- smoke 时 ComfyUI 队列为空、V1 批量任务处于取消状态；直接使用空闲 ComfyUI，未触碰用户手工任务与其他 AIHome 服务；
- smoke 使用独立临时 DataRoot，不触碰 `D:/NSFW-Studio-Data` 正式数据；
- 发布完成后按既定方针恢复夜间批量（V1 重提交 + 千问外部批量，步骤见 `temp/nightbatch_restore_notes.md`）。

## 5. 已知限制

- 历史列表按 2000 条窗口归组（本地工具规模足够；超大历史可后续分页优化）；
- History 页面为前端构建级验证 + API 级断言，未做浏览器逐步点击验收；
- Input Registry TTL 清理的"到期删除"由离线单测覆盖；真实运行已验证登记与不误删；
- `config.local.yaml` 的 `input_dir/output_dir` 为可选配置：未配置时清理/文件级恢复安全跳过。

## 6. 下一步（Phase 5 候选，未实施）

**Phase 5：Reference Image / Img2Img**。开始前先检查本机现有 Qwen/其他工作流是否真有可复用的
参考图或图生图链；没有就先讨论模型方案，不擅自下载安装。若有：只需新增 WorkflowModule
（声明 I/O 能力）+ provider binding + 输入图片 UI，不应再修改 QueueWorker / Pipeline Scheduler /
ImageService 核心——这是"积木架构"的第二次验证。