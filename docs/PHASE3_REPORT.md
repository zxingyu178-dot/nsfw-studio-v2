# PHASE3_REPORT — Multi-stage Pipeline + Upscale（v0.4.0）

> 日期：2026-10-08 ｜ 版本：0.4.0 ｜ 基线：v0.3.2 (b45c0e2) ｜ 分支：feature/phase3-pipeline-upscale
> 目标：正式加入第二个 WorkflowModule（高清放大），实现"生成 N 张原图全部完成后统一进入高清"，
> 并支持图库已有图片的单独高清。

## 1. 交付内容

### Task 0（执行漏洞修复，先行）

| # | 修复 | 实现 |
| --- | --- | --- |
| 0.1 | Worker 意外异常必须停队列 | 代码级异常（非 EngineError）→ 当前 Job/Stage INTERRUPTED（保留 engine_job_id）+ queue_paused + WORKER_INTERNAL_ERROR；CancelledError 保持原恢复逻辑 |
| 0.2 | Binding 每次请求动态选择 | `EngineBindingRef(module_id/module_version/provider/binding_version/workflow_hash)`；Adapter 按 `(module_id, binding_version)` 缓存加载 |
| 0.3 | Workflow Hash 必须校验 | Job 固化 hash ≠ 磁盘 `sha256(workflow.json)[:16]` → `WORKFLOW_HASH_MISMATCH`（系统性拒绝）；binding 目录 immutable，改 Workflow 必须新建 v2 |
| 0.4 | 固定 Seed 仅限单张 | 恢复"每张独立随机"；fixed+count>1 → 400 `FIXED_SEED_SINGLE_ONLY`；前端"使用此图 Seed"自动 count=1、数量改 >1 自动回随机 |

### 多阶段管线（§一-§十）

- 迁移 `0007_pipeline_stage`：`jobs.job_kind` + `job_stages` + `job_stage_items`；
- Job 创建物化 Stage（执行真源 = JobStage + workflow_snapshot）；Stage Gate 严格门控；
- 暂停/取消在 StageItem 边界；崩溃恢复按 StageItem（engine_job_id + **文件级兜底扫描**）；
- 输出命名含 Studio 身份 `NSFWStudio/{job_short}/{stage}/{item_short}`；`execution_timeout`（默认 1800s）→ ENGINE_TIMEOUT。

### 高清放大（§十一-§廿一）

- `UpscaleModule`（标准输入仅 `input_image`）+ provider binding `upscale/v1`
  （4x-UltraSharp 链，复用本机已验证资源；选型见 UPSCALE_WORKFLOW_INVENTORY.md）；
- 输入图片经 `POST /upload/image` 上传（Studio 唯一命名 + subfolder 隔离）；
- Image 存储泛化：`images/originals|upscaled|processed` + `parent_image_id`；
- `POST /api/v1/images/upscale` → upscale-only `process` Job（同一 Worker / 同一模块，禁止两套高清代码）；
- Job Detail `stages[]`；图库父子关系（`/images/{id}/versions`）、HD 标记、多选高清。

### 前端（§十五-§十九）

- 工作台"② 高清放大"开关；配方保存/恢复 100% 一致（含开关状态）；
- 分阶段实时进度（`原图生成 x/y ✓` / `高清放大 m/n · 第 k 张 · p%`）；
- 缩略图 HD 标记（完成一张显示一张，不等待全 Job）；
- 图库：HD 徽标、多选模式 +「高清放大」、详情抽屉"来源原图 / 派生版本"点击切换、单张高清按钮；
- "使用此图 Seed" 自动 count=1（§0.4）。

## 2. 测试证据

### 快速套件（CI 同口径）

```text
.venv\Scripts\python -m pytest tests/backend --ignore=tests/backend/test_comfyui_integration.py
结果：144 passed（v0.3.2 的 132 例 + Phase 3 新增 12 例）
```

新增/更新用例：

- `test_phase3_pipeline.py`（12 例）：basic-only 单 Stage；basic+upscale 严格顺序
  （提交序列 `basic×3 → upscale×3`、StageItem 输入=上一 Stage 同槽位输出、父子关系与
  `images/upscaled/` 路径）；Stage 0 失败 → Stage 1 不启动（gate）；Stage 2 第 2 张失败 →
  原图全部保留；Stage 2 暂停/继续；Stage 2 取消保留已生成；Stage 2 崩溃恢复（高清挂回原图、
  已完成 Stage 不重跑、JOB_RECOVERED_COMPLETED）；图库 3 张 → upscale-only process Job；
  Worker 内部 RuntimeError → Job INTERRUPTED + 队列暂停 + 第二 Job 不启动；
  WORKFLOW_HASH_MISMATCH 系统性；ENGINE_TIMEOUT；Recipe 高清开关往返。
- `test_comfyui_binding.py` 重写：动态多模块加载 / hash 校验 / hash 不一致拒绝 / upscale/v1 图结构。
- `test_job_queue.py` / `test_phase21_stability.py`：固定 Seed 语义更新（fixed 单张；
  fixed+count>1 → 400；续跑新随机 Seed）。
- `test_migration_upgrade.py`：升级路径补 0007。

### 全量套件（含真实 ComfyUI）

```text
.venv\Scripts\python -m pytest tests/backend
结果：147 passed（144 快速 + 3 真实链路），退出码 0
```

### 真实 ComfyUI 验收（§二十六：只跑最短链路）

| 场景 | 证据 |
| --- | --- |
| 1 张基础生成 | ComfyUI history `status=success`；产物 640×960（931KB）；输出 `NSFWStudio/<job>/0/<item>` |
| 1 张基础 → 1 张真实高清 | 原图 640×960（929KB）→ 高清 **2560×3840（11.0MB，恰 4 倍）**；`parent_image_id` 指向原图；Stage 0/1 均 COMPLETED |
| 图库 1 张（64×64 导入）→ 单独高清 | 高清 **256×256（4 倍）**；`kind=upscaled` 入 `images/upscaled/`；`/images/{id}/versions` 父子互查通过 |

结论：ComfyUI binding 正确切换（basic → upscale 交替）；原图不被覆盖；高清进入
`images/upscaled`；`parent_image_id` 正确；Gallery 可见父子关系。

### 前端

```text
npm run build → tsc --noEmit 通过 + vite build 通过（v0.4.0）
```

### CI（GitHub Actions）

```text
develop: run 37724675927 → success（sha 9357891）
main:    run 37725594175 → success（sha 9357891）
```

## 3. 验收标准对照

| 要求 | 结果 |
| --- | --- |
| 生成 N 张原图全部完成后才进入高清（禁止交错） | ✅ 提交序列断言 + Stage Gate 实现 |
| 图库已有图片 → upscale-only Job，同一 Worker / 同一 UpscaleModule | ✅ `POST /images/upscale` → process Job |
| 不能维护两套高清代码 | ✅ 单模块 + 单 binding + 单 Worker 路径 |
| 原图与高清保持父子关系 | ✅ parent_image_id + versions API（含真实链路） |
| Task 0.1-0.4 四项修复 | ✅ 全部实现并有测试 |
| 多阶段暂停/取消/崩溃恢复 | ✅ 边界语义 + StageItem 粒度恢复 |
| Recipe 高清开关往返 | ✅ 测试覆盖 |
| 文档 | ✅ 新增 4 份 + 同步 JOB_STATE_MACHINE / RECOVERY_SPEC / COMFY_ADAPTER / IMAGE_MODEL / WORKBENCH_STATE / DATA_MODEL_V1 / DATABASE_PLAN / API_PLAN / README / AGENTS + 根级日志 |
| 禁止项（升级 ComfyUI / 装节点 / 下模型 / 改用户工作流 / 破坏性 cancel 测试） | ✅ 未发生；高清链复用本机既有资源 |

## 4. 环境说明（如实记录）

- 真实验收期间，ComfyUI 队列中同时存在用户夜间批量（V1 内部批量 + 千问外部批量）；
  按用户当前指令"取消夜间任务，开发验收优先"，已通过 V1 自带的批量控制接口暂停并保存现场
  （详见 `temp/nightbatch_restore_notes.md`），验收结束按同一说明恢复；
- 未触碰任何用户手工提交的 ComfyUI 任务或其他 AIHome 服务。

## 5. 已知限制

- 并发路径（多 Item 并行执行）不在本阶段范围（系统固定单队列 + 单 Worker）；
- `queue_paused` 为进程内存态：重启后队列自然恢复（Job 状态不受影响，与 Phase 2 一致）；
- 文件级恢复扫描需在 `config.local.yaml` 配置 `comfyui.output_dir`（可选；不配置则退化为
  history 核对，行为与之前一致）；
- Stage 在 Job PAUSED 期间保持 RUNNING（Stage 状态集不含 PAUSED，合同 §二），用户可见状态以 Job 为准。

## 6. 下一步（Phase 4 候选，未实施）

Img2Img / Reference / FaceRepair 模块（只需新增 WorkflowModule + binding 目录）；
Agent API 接入；手机端。