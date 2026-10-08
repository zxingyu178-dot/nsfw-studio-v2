# TEST_REPORT — Phase 0 / 0.1 / 1 / 2 / 2.1 / 2.2 / 3 / 4 / 5（2026-10-08）

## Phase 5 测试（v0.6.0，Image Input Foundation + Reference / Img2Img Capability Gate）

### 快速套件（CI 同口径，无 ComfyUI）

命令：`.venv\Scripts\python -m pytest tests/backend --ignore=tests/backend/test_comfyui_integration.py`

**结果：186 passed**（v0.5.0 的 168 例 + Phase 5 新增 18 例；Phase 4 全部回归全绿）。

| 新增用例 | 覆盖点 |
| --- | --- |
| test_phase5_image_input.py 18 例 | ① **导入**：单张 PNG 全链路（source=import / kind=original / job_id=null / file_path 相对路径 / DB sha256=64hex / 文件落在 images/originals / source 过滤 / Provenance=外部导入 / workbench 404 IMAGE_NO_GENERATION_CONTEXT）；WEBP（VP8L）尺寸解析 200×100；超限 FILE_TOO_LARGE；伪造扩展名与非法内容单张失败；② **去重**：同内容不同文件名 → duplicate + 返回已存在 image_id，总数不增（API 级 + 服务级）；③ **Job 冻结**：count=2 的 Job 全部 Stage0 StageItem 冻结同一输入图、各槽位独立产出（Mock 引擎真实跑完 COMPLETED）；缺失输入图 404；>1 张输入图 422；处理型 Job 快照与 input_image_ids 不一致 → PIPELINE_INVALID；④ **Recipe**：input_images 快照（role/image_id/sha256=64hex/missing=false）；内容一致不建新版本；restore 复制输入图关系；删除图片行后 missing=true（引用保留不静默清空）；未知图 404；⑤ **Face Asset**：绑定参考图（reference_images 返回 image_id）；更换 = v2（旧版本各自保留）；不传沿用当前版本；非 face → ASSET_REFERENCE_TYPE_INVALID；缺失 → 404；关系行（role=face_reference, sort_order=0）落库；⑥ **引用保护**：5 类来源（Recipe/StageItem/Face 参考/Asset 溯源/派生图）全部识别 total=5 且 derived 精确；未引用图片 total=0；完成后 active_job_ids=[]；⑦ **Modules**：basic_generate input_required=false；upscale=true/source/upscaled；Gate B 判定断言（无 input_required+processed 模块）；⑧ **迁移 0010**：images.sha256/imported_filename、recipe_versions.input_images_json、asset_reference_images、idx_images_sha256 存在；重复启动 0 迁移 |

### 本阶段零真实生图（合同 §29 Gate B）

Task 0 调查确认本机无可用图片条件工作流（详见 docs/IMAGE_CONDITIONING_INVENTORY.md），
真实 Img2Img / Reference 接入暂停；"输入图片 → Module → Pipeline → ComfyUI"链路待用户选定方案后
在 Phase 5.1 执行 1 次真实最小测试。

### 前端

`npm run build`：tsc --noEmit 通过 + vite build 通过（v0.6.0，60 modules，JS 259.7KB / gzip 78.3KB）。

### 未验证 / 限制（如实标注）

- 真实浏览器 GUI 验收未执行：导入进度、模式切换、Picker、快捷键 / Ctrl+Z 撤销为构建级 +
  代码级验证（后端 API 行为由 18 例离线测试覆盖）；建议验收方按 Phase 5 验收清单人工检查；
- 图片引用保护只做"检查"（§十一 明确 Phase 5 不实现永久删除 UI）；
- 撤销为前端会话内栈（刷新后清空），符合"不做复杂设置页"的合同约束。

### GitHub CI

```text
develop: run 37747872243 → success（sha be64144，pytest + 前端构建两个 job 全绿）
main:    run 37749969875 → success（sha be64144，pytest + 前端构建两个 job 全绿）
```

## Phase 4 测试（v0.5.0，History + Provenance + Generic Module I/O Contract）

### 快速套件（CI 同口径，无 ComfyUI）

命令：`.venv\Scripts\python -m pytest tests/backend --ignore=tests/backend/test_comfyui_integration.py`

**结果：168 passed**（v0.4.0 的 147 例 + Phase 4 新增 21 例；Phase 3 12 场景与 Phase 2.x 回归全绿）。

| 新增用例 | 覆盖点 |
| --- | --- |
| test_phase4_backfill.py 1 例 | **真实 v0.3.2 库**（0001~0006）含 COMPLETED / QUEUED / PAUSED / INTERRUPTED 四种 Job：升级 0007+0008+0009 后每个 Job 有 1 个 Stage（身份继承 job 列）+ 对应 StageItem；状态/图片关系/engine_job_id 映射正确；StageItem.seed 回填；**历史 Job 状态不被改变**；启动应用后 QUEUED Job 被同一 Worker 真实执行 → COMPLETED |
| test_phase4_contract.py 12 例 | ① 能力声明（basic/upscale 的 uses_seed/input_kind/output_kind/parent_policy/output_cardinality）；② StageItem 上有 input_image_id 也按能力落 original（回归删除推断）；③ basic StageItem 真实 Seed / upscale StageItem 与 manual upscale Image.seed 为 NULL；④ EngineAdapter 正式输入契约（Mock 上传 + 登记；Unbound → ENGINE_INPUT_UNSUPPORTED 且系统性；执行路径 Job FAILED + 队列暂停）；⑤ binding_hash 进入 Job/Stage/快照/API；⑥ BINDING_HASH_MISMATCH 执行期系统性；⑦ resolve_workflow_modules：普通新建解析当前身份 / 完整身份固定原版本 / 指纹被改拒绝 / 老 Job null 兼容 / provider 不匹配拒绝 / mock 下 pinned 透传；⑧ Input Registry：TTL 清理只删登记过且无 RUNNING 引用的 Studio 文件、非 Studio 路径与未到期文件保留、未配置 input_dir 跳过、Mock 上传登记 |
| test_phase4_history_provenance.py 8 例 | ① History：Web+两级续跑链（A→B→C）归组为同一任务族；bucket（all/active/completed/failed/cancelled）与 source（web/resume/agent）筛选；非法筛选 4xx；② 续跑操作聚合仍归族；③ 派生图（高清）打开工作台 → 恢复根生成 Job 的 Prompt + 完整模块身份 + 根图 Seed；④ 图库手动高清（process Job）→ 追溯原生成配置而非空 Prompt；⑤ 外部导入图 → 404 IMAGE_NO_GENERATION_CONTEXT；⑥ Provenance 全链路（高清：stage_index=1/upscale/seed=null；原图：stage_index=0/basic/真实 seed；导入图：全空） |
| test_comfyui_binding.py（更新 + 新增 3 例） | 双指纹溯源（binding_identity 返回 3 元组）；BINDING_HASH_MISMATCH；binding 自描述不一致拒绝；**只改 binding.yaml（workflow.json 不动）→ binding_hash 必变且老 Job 拒绝**；一个 Adapter 动态加载 |
| test_comfyui_resilience.py / test_migration_upgrade.py（更新） | load_binding 返回 4 元组（v2 fixture 含 binding_hash）；升级路径补 0008/0009 |

### 全量套件

本阶段**未重跑**真实集成套件（test_comfyui_integration.py 3 例）——合同 Task13 明确"不再跑批量
3/8 张"，真实链路由下述最短 smoke 覆盖（如实标注）。

### 真实 ComfyUI 最短 smoke（Task13：1 基础 → 1 真实高清 → History → Gallery → 高清图打开工作台）

| 检查点 | 结果 |
| --- | --- |
| 1 张基础生成（768×1024） | ✅ 真实 Qwen-Image 2.1 UC（冷启动约 10.7 分钟）；seed=1501957504；StageItem.seed 落库 |
| 4x 高清 | ✅ 3072×4096（15.4MB）；StageItem.seed=null；Image.seed=null；parent 指向原图 |
| Stage 双指纹 | ✅ basic f45c54cbd48ab058/a7911ab7a6c1d1be；upscale 8232a833dc049803/6a7a21944d428ef6 |
| History | ✅ completed 筛选命中任务族（root=job_80aa15cb…） |
| Gallery 父子 | ✅ versions.children=[高清]；高清入 images/upscaled/ |
| 高清图 → 工作台 | ✅ 恢复原 full_prompt + 根图 Seed + 完整执行身份（双指纹）；seed_mode=random |
| Provenance | ✅ stage_index=1 / module=upscale / provider=comfyui / seed=null |
| 输入登记 | ✅ DataRoot/engine_inputs.json 记录 NSFWStudio_inputs/<img_id>.png（Task11 真实生效） |

smoke 脚本与日志：`temp/smoke_phase4.py`、`temp/smoke_phase4.log`（临时证据，不进仓库）。

### 前端

`npm run build`：tsc --noEmit 通过 + vite build 通过（v0.5.0）。

### 未验证 / 限制（如实标注）

- 真实集成套件 3 例未重跑（见上；smoke 已覆盖真实生成+高清主链路）；
- History 页面 / 图库溯源 UI 为前端构建级验证 + API 级断言，未做浏览器逐步点击验收；
- Input Registry TTL 清理在真实运行中已验证"登记 + 不误删"（无到期文件可删），
  到期删除行为由离线单测覆盖。

### GitHub CI

```text
develop: run 37736554279 → success（sha 0cce473，pytest + 前端构建两个 job 全绿）
main:    run 37736733728 → success（sha 0cce473，pytest + 前端构建两个 job 全绿）
```

## Phase 3 测试（v0.4.0，Multi-stage Pipeline + Upscale）

### 快速套件（CI 同口径，无 ComfyUI）

命令：`.venv\Scripts\python -m pytest tests/backend --ignore=tests/backend/test_comfyui_integration.py`

**结果：144 passed**（v0.3.2 的 132 例 + Phase 3 新增 12 例）。

| 新增用例 | 覆盖点 |
| --- | --- |
| test_phase3_pipeline.py 12 例 | basic-only 单 Stage；basic+upscale 严格顺序（提交序列 basic×3→upscale×3 + StageItem 输入=上一 Stage 输出 + parent/kind/存储目录）；Stage 0 失败 → Stage 1 不启动；Stage 2 第 2 张失败 → 原图全保留；Stage 2 暂停/继续；Stage 2 取消保留已生成；Stage 2 崩溃恢复（高清挂回原图 + 不重跑已完成 Stage + JOB_RECOVERED_COMPLETED）；图库 3 张 → upscale-only process Job（同一模块、input_image_id 对应）；Worker 内部 RuntimeError → Job INTERRUPTED + 队列暂停 + 第二 Job 不启动；hash 不一致系统性失败；ENGINE_TIMEOUT（不重试、不暂停队列）；Recipe 高清开关往返 |
| test_comfyui_binding.py（重写 + 新增） | EngineBindingRef 注入；hash 溯源；hash 不一致拒绝（WORKFLOW_HASH_MISMATCH）；一个 Adapter 动态加载 basic_generate/v1 与 upscale/v1；upscale/v1 图结构（LoadImage→UpscaleModelLoader(4x-UltraSharp)→ImageUpscaleWithModel→SaveImage） |
| test_comfyui_resilience.py（更新） | binding 版本切换改为请求级 `load_binding`（v2 目录可切换、v9 → BINDING_NOT_FOUND） |
| test_job_queue.py / test_phase21_stability.py（更新） | 固定 Seed 语义：fixed 单张使用该 Seed；fixed+count>1 → 400 `FIXED_SEED_SINGLE_ONLY`；续跑子 Job 新随机 Seed 且不复用父 Seed |
| test_image_service.py（更新） | 导入回调按 StageItem 判定（阶段输入 → upscaled + parent；否则 original） |
| test_migration_upgrade.py（更新） | 升级路径补 `0007_pipeline_stage` |

### 全量套件（含真实 ComfyUI 链路）

命令：`.venv\Scripts\python -m pytest tests/backend`

**结果：147 passed（144 快速 + 3 真实），退出码 0。**

### 真实 ComfyUI 验收（§二十六：只跑最短链路）

| 场景 | 结果 |
| --- | --- |
| 1 张基础生成（test_real_basic_generation_smoke） | ✅ 640×960 真实图（931KB）；ComfyUI history `success`；输出 `NSFWStudio/<job>/0/<item>` |
| 1 张基础 → 1 张真实高清（test_real_pipeline_basic_then_upscale） | ✅ 原图 640×960 → 高清 **2560×3840**（11.0MB，4 倍）；Stage 0/1 COMPLETED；parent 指向原图 |
| 图库 1 张 → 单独高清（test_real_gallery_upscale_only） | ✅ 64×64 → **256×256**；kind=upscaled 入 `images/upscaled/`；versions 父子互查通过 |

### 前端

`npm run build`：tsc --noEmit 通过 + vite build 通过（v0.4.0）。

### 环境说明（如实记录）

真实验收期间 ComfyUI 队列存在用户夜间批量；按用户当日指令暂停（现场已保存，恢复步骤见
`temp/nightbatch_restore_notes.md`）后完成上述真实链路。未触碰用户手工任务。

## Phase 2.2 测试（v0.3.2，Data Consistency & Recovery Closure）

### 快速套件（CI 同口径，无 ComfyUI）

命令：`.venv\Scripts\python -m pytest tests/backend --ignore=tests/backend/test_comfyui_integration.py`

**结果：129 passed**（0.3.1 的 120 例 + 新增 9 例）。

| 新增用例 | 覆盖点 |
| --- | --- |
| test_image_service.py 批次原子 3 例 | ① 合法 PNG + 损坏 PNG → 整批失败、images=0、originals/temp 无残留；② 双合法 → 同批同时成功；③ 移动阶段第 2 张失败 → 第 1 张已移动的正式文件也随整批回滚删除 |
| test_phase22_consistency.py 3 例 | Case A：1 张崩溃→重启后引擎可确认 → Item COMPLETED + Job COMPLETED + completed_count=1 + finished_at + JOB_RECOVERED_COMPLETED 事件；Case B：3 张前 2 张完成、第 3 张无法确认 → Job INTERRUPTED + completed_count=2 + 无 RUNNING Item；Resume 身份：Parent=v1、当前系统升级 v2 后，Child 全字段（快照 + 列）仍为 v1 且两处一致，新 Job 才用 v2 |
| test_comfyui_resilience.py 取消边界 3 例 | pending target → 只 delete、无 interrupt；running target → 允许 interrupt；别人 running（target 不在队列）→ 无 interrupt 且零队列写操作 |

### 本阶段不跑真实 ComfyUI 生成（合同 §6）

批次原子 / 恢复归并 / Resume 身份 / 取消边界全部通过 Mock 引擎与 httpx stub 离线验证；
真实链路已在 2.1 由 1 张 smoke 证据支撑。

### 未验证 / 限制（如实标注）

- 恢复归并（`_finalize_recovery`）仅在启动恢复路径生效，正常运行路径终态仍由 `_finish_job` 写入；
- 取消边界测试为 stub 级验证（合同明确不做破坏性真实取消测试）。

**GitHub CI**（fix/phase2-data-consistency → develop → main）：
develop 与 main 推送后 GitHub Actions 均 **success**（head d90f1b4，pytest + 前端构建两个 job 全绿）。

## Phase 2.1 测试（v0.3.1，Stable Execution & Pipeline Contract Closure）

### 快速套件（CI 同口径）

命令：`.venv\Scripts\python -m pytest tests/backend --ignore=tests/backend/test_comfyui_integration.py -q`

**结果：120 passed**（0.3.0 的 91 例 + 新增 29 例）。

| 新增测试文件 | 用例数 | 覆盖点 |
| --- | --- | --- |
| test_phase21_stability.py | 22 | 无输出/取输出异常/导入异常/导入空结果都不得 COMPLETED（4 类故障 + 成功对照）；掉线后有限时间 FAILED + 队列暂停；Worker 零模块知识（tokenize 源码断言）；真实模块被执行 + 快照同步；模块/注册表/Pipeline 单测；fixed Seed Resume → random（父快照不动）；next Job 拖拽后队列与实际执行顺序；API 范围校验 7 组 + Prompt 超长；Cancel 请求异常安全降级 |
| test_comfyui_resilience.py | 7 | /history ConnectError → ENGINE_OFFLINE；其他网络错误 → ENGINE_NETWORK(transient)；history 缺失但在队列中 → running（不误判）；任务丢失 → 有界轮询后 unknown；WS 新鲜不误判丢失；binding v2 fixture 可切换；缺失版本 → BINDING_NOT_FOUND |

### 真实 ComfyUI smoke（1 张，§十二）

命令：`.venv\Scripts\python -m pytest "tests/backend/test_comfyui_integration.py::test_real_generation[1]" -q`

**结果：1 passed**（图片 NSFWStudio/20261007_00013_.png，冷启动模型加载约 7 分钟 + 采样，
ComfyUI 0.37.0 / RTX 3060）。

- 断言：Item.image_id 非空（§一）、workflow_snapshot.modules 记录 basic_generate/comfyui/hash（§四）、
  图片入 DataRoot 且 content 可读、Workbench Snapshot 完整；
- 链路：Workbench → Job → BasicGenerateModule（PipelineExecutor）→ ComfyUIAdapter → Image → Gallery。

### 交接包独立运行（§十）

`build_handoff.py` 生成 ZIP → 解压到临时目录（无 .git）→ 快速套件全绿（120 例），
证明 Handoff ZIP 解压后不依赖 Git 元数据。

### 未验证 / 限制（如实标注）

- 真实集成只跑 1 张 smoke（合同 §十二 明确不重跑 1/3/8 整套）；
- Mock 的 fixture PNG 为 1×1（source=mock 标识），不代表真实画质；真实链路由 smoke 证据支撑。

**GitHub CI**（fix/phase2-stable-execution → develop → main）：
develop 与 main 推送后 GitHub Actions 均 **success**（head 8448553，pytest + 前端构建两个 job 全绿）。

## Phase 2 测试（v0.3.0，Job Execution Core + ComfyUIAdapter + Gallery）

### 快速套件（不依赖 ComfyUI，CI 同口径）

命令：`.venv\Scripts\python -m pytest tests/backend --ignore=tests/backend/test_comfyui_integration.py -q`

**结果：91 passed**（0.2.0 的 68 例 + Phase 2 新增 23 例）。

| 测试文件 | 用例数 | 覆盖点 |
| --- | --- | --- |
| test_job_queue.py | 14 | §五十八 全清单：8 张串行 / Item 边界暂停 / 取消保留图 / 取消后 Resume 子 Job / 优先插队 / 拖拽排序 / 引擎离线（队列暂停）/ 瞬态网络重试 ≤2 恢复 / OOM 不重试 / Workflow 错误不重试 / 启动发现 INTERRUPTED / 崩溃恢复核对导入 / SSE 流 / client_request_id 幂等 / 固定 Seed |
| test_image_service.py | 5 | 输出导入（相对路径/尺寸/元数据/失败全回滚）/ 垃圾字节拒绝 / review+favorite / 列表过滤 + by-job 统计（含收藏）/ Gallery API 全链路（content/review/favorite/workbench+Seed） |
| test_comfyui_binding.py | 4 | provider binding 注入（节点 ID 只在 binding 层）/ seed 范围钳制 / 模板不被污染 / workflow_hash 与 binding_version 溯源（无需 ComfyUI） |
| test_migration_upgrade.py | 1 | v0.1.2 库 → 0002–0006 升级（含 jobs/job_items/job_events/images 约束） |
| test_interfaces.py | 8 | 契约守护更新：公共配置允许选择 comfyui（不得携带机器地址）/ Worker 只消费 Job / EngineAdapter 异步契约 |

### 真实 ComfyUI 集成（本机，离线自动 skip）

命令：`.venv\Scripts\python -m pytest tests/backend/test_comfyui_integration.py -q`

**结果：3 passed**（`test_real_generation[1]/[3]/[8]`，合计 12 张真实图片）。

- 完整生产链：POST /jobs → 单队列 → ComfyUIAdapter → Qwen-Image 2.1 UC 生成 →
  导入 DataRoot/images/originals → Gallery 查询 + content 可读；
- 断言：顺序执行（engine_job_id 各不相同）、Seed = base + item_index、completed_count 递增、
  图片元数据（尺寸 640×960 / source=comfyui / 相对路径）、Workbench Snapshot 完整；
- 实测速度：640×960 约 102–118 秒/张（模型驻留显存）；当天首张 832×1216 含模型加载约 300 秒。

前端：`npm run build`（tsc --noEmit + vite build）通过。

### 未验证 / 限制（如实标注）

- 未做浏览器 E2E 自动化（IAB 沙箱限制）；前端以 API 测试 + 构建 + dev 手动运行验证为准；
- 队列内存态暂停、进程崩溃窗口等边界依赖 Mock 测试覆盖（真实 ComfyUI 场景不模拟崩溃）。

**GitHub CI**（feature/phase2-execution-gallery → develop → main）：
develop 与 main 推送后 GitHub Actions 均 **success**（head 9da5821，pytest + 前端构建两个 job 全绿）。

## 零-c、Phase 1 测试（v0.2.0，Prompt/Asset/Recipe Core）

命令：`.venv\Scripts\python -m pytest`（项目根目录）

**结果：68 passed, 1 warning（4.65s）**——0.1.1 的 33 例 + 新增 35 例。

| 测试文件 | 用例数 | 覆盖点（对应规范 §五十八） |
| --- | --- | --- |
| test_prompt_composer.py | 5 | 八栏顺序固定 / 空字段跳过 / 未知字段丢弃 / JSON 往返 / 容错 |
| test_prompt_service.py | 7 | CRUD / 版本机制 / 元数据不建版本 / 线性恢复 / 归档 / 404 / 并发冲突(VERSION_CONFLICT+回滚) / 列表过滤 |
| test_asset_service.py | 8 | 四类型创建 / 相对路径入库 / 非法类型 / 版本不可变+旧文件保留 / 非法扩展名 / 内容不符 / 超限 / 提交失败无孤儿文件 / 路径穿越防护 |
| test_recipe_service.py | 8 | 快照创建 / FK+快照双存 / 素材升级老配方不变 / 恢复制快照 / 内容不变不建版 / seed 固定 random / slot 校验 / 缺素材 404 / 列表归档 |
| test_api_phase1.py | 4 | 统一错误格式（404/422） / Prompt 全链路 / Asset 上传+预览图+版本 / Recipe 保存+恢复往返 |
| test_migration_upgrade.py | 1 | v0.1.2 库 → 0002-0004 升级 → 旧数据保留 / FK / CHECK / UNIQUE 全部生效 |

前端：`npm run build`（tsc + vite）通过。

**真实环境验证**：
- 迁移前备份（SQLite backup API）→ `studio-20261007-152712.db`；
- 真实库 0.1.2 → 0.2.0 迁移成功（0002/0003/0004 applied，system_info 自动更新，9 张表就位）；
- 浏览器人工验证（规范 §五十九）：新建结构化 Prompt→保存→重开字段一致 ✓；完整 Prompt ✓；
  选择素材→服饰字段填充（素材在前）✓；保存配方→重开 100% 恢复（Prompt/Negative/素材引用/尺寸）✓；
  素材卡片/详情/版本 ✓；深浅主题 ✓。素材文件上传的 UI 自动化受浏览器沙箱限制（IAB 不支持
  file chooser），上传/校验/版本逻辑由 API 测试全覆盖。

**GitHub CI**：feature → develop → main 推送均触发，结果见运行记录（要求全绿）。

环境事故记录：验证期间发现残留 vite 进程占用 5173 缓存旧 CSS（TaskStop 只杀 bash 包装进程），
已清理；后续停服务需核对端口释放。

---

## 零-b、Phase 0.1.1 测试（v0.1.2，审查遗留契约修正）

命令：`.venv\Scripts\python -m pytest`（项目根目录）

**结果：33 passed, 1 warning（5.70s）**——0.1 的 27 例 + 新增 6 例。

| 新增用例 | 覆盖点 |
| --- | --- |
| test_workflow_execute_is_async | `WorkflowModule.execute` 为 async（与 EngineAdapter 契约统一） |
| test_engine_adapter_methods_are_async | EngineAdapter 四个方法全部 async |
| test_pure_computation_interfaces_stay_sync | capabilities / validate_input 保持同步 |
| test_repo_public_config_is_machine_independent | 公共 config.yaml 无盘符、不设置 data_root（哨兵） |
| test_no_config_falls_back_to_portable_default / test_base_config_overrides_default | 三层缺失 → 用户目录默认；模板覆盖默认 |
| test_local_config_overrides_base_config | config.local.yaml 覆盖公共模板 |
| test_env_var_beats_all_config_layers | 环境变量最高优先级（同时存在 base+local） |
| test_local_config_is_gitignored | config.local.yaml 被 .gitignore 覆盖（防误提交） |

真实加载验证：本机 `load_settings()` 实际 DataRoot = `D:\NSFW-Studio-Data`（来自 config.local.yaml）；
仓库内 config.yaml 已无任何机器路径。
前端：`npm run build` 通过；develop / main CI 全绿。

---

## 零、Phase 0.1 测试（v0.1.1，架构收口）

命令：`.venv\Scripts\python -m pytest`（项目根目录）

**结果：27 passed, 1 warning（1.89s）**——原 15 例 + 新增 12 例，一次全绿。

新增覆盖（对应 Phase 0.1 验收）：

| 测试文件 | 用例数 | 覆盖点 |
| --- | --- | --- |
| test_migrations_recovery.py | 2 | failed 迁移不被视为 applied；下次启动仍重试；修复后重试成功且无主键冲突残留；仅 applied 计数 |
| test_sqlite_pragmas.py | 1 | WAL / busy_timeout=5000 / foreign_keys=ON，且每个新连接生效 |
| test_backup.py | 2 | 备份快照可打开且数据一致（SQLite backup API）；源库缺失报错 |
| test_config_portability.py | 4 | 默认 DataRoot 基于 Path.home()；env 覆盖；config 文件覆盖；env > 文件 |
| test_system_info.py | 2 | 版本升级后 system_info 同步更新且单行；同版本 unchanged |
| test_interfaces.py | 5 | Workflow 标准契约存在且 execute 注入 EngineAdapter；EngineJobStatus 含 progress；QueueWorker 无 submit（只消费）；provider=unbound |
| 既有测试更新 | - | health/system_info 版本断言改为动态（settings.app.version）；EXPECTED_DIRS 增加 backups |

前端：`npm run build`（tsc + vite）通过。

**真实运行验证（本机 DataRoot 升级路径）**：
- 现有 DataRoot 幂等升级成功：自动新建 `backups/`（日志：`新建目录=['backups']`）；
- `system_info` 版本自动更新 `0.1.0 → 0.1.1`（BootstrapReport.system_info_action=updated）；
- `PRAGMA journal_mode` 实测返回 `wal`；
- `scripts/backup_db.py` 实测成功产出 `backups/studio-20261007-143618.db`。

**GitHub CI**：`.github/workflows/ci.yml` 于 develop/main push 与 PR 触发（后端 pytest + 前端 npm ci/build）；本轮推送后 CI 运行结果见下方"实时记录"。

---

## 环境信息

| 项 | 值 |
| --- | --- |
| OS | Windows 10.0.26200 x64 |
| Python | 3.11.15（项目 .venv，随项目创建） |
| Node.js | v24.18.1（AIHome managed-tools，未装第二套） |
| 关键依赖 | fastapi 0.142.2 / SQLAlchemy 2.1.3 / pydantic 2.13.5 / pytest 9.1.1 / vite 5.4.21 / react 18.3.1 |

## 一、后端自动化测试（pytest）

命令：`.venv\Scripts\python -m pytest`（项目根目录，pytest.ini 指向 tests/backend）

**结果：15 passed, 1 warning（0.76s）**

| 测试文件 | 用例 | 覆盖验收点 |
| --- | --- | --- |
| test_app_startup.py | 3 | 应用工厂 / 入口可导入 / lifespan 启动引导 |
| test_health_api.py | 2 | health 响应体精确匹配 `{"status":"ok","version":"0.1.0"}`、根信息 |
| test_data_dirs.py | 3 | 15 个目录全部创建、二次引导幂等、StorageManager 白名单 |
| test_database.py | 3 | studio.db 创建、migration 记录 applied、system_info=0.1.0、不重复写行、迁移幂等 |
| test_interfaces.py | 4 | WorkflowModule / EngineAdapter / QueueWorker 抽象接口存在、workflow.yaml provider=unbound |

说明：全部用例通过 `NSFW_STUDIO_DATA_ROOT` 使用 pytest 临时目录，未触碰真实 `D:/NSFW-Studio-Data`。
警告为 starlette 对 httpx 的弃用提示（第三方库），非本项目缺陷。

## 二、运行时验证（真实启动）

| 步骤 | 命令/操作 | 结果 |
| --- | --- | --- |
| 后端启动 | `uvicorn app.main:app --port 8000 --app-dir backend` | ✅ 启动完成，无错误 |
| health API | `curl /api/v1/health` | ✅ `{"status":"ok","version":"0.1.0"}` |
| 根信息 | `curl /` | ✅ `{"name":"NSFW Studio","version":"0.1.0","api":"/api/v1/health"}` |
| DataRoot | `find /d/NSFW-Studio-Data -type d` | ✅ 15 目录与规范 §九 一致 |
| 数据库 | studio.db 存在（20KB） | ✅ |
| 日志 | logs/{app,jobs,errors} 各有文件 | ✅ JSON Lines 格式正确（time/level/module/message） |

## 三、前端验证

| 步骤 | 结果 |
| --- | --- |
| `npm run dev` 启动 | ✅ http://localhost:5173（HTTP 200） |
| `/api` 代理到后端 | ✅ 通过代理请求 health 成功 |
| 页面渲染（浏览器实测） | ✅ 品牌 + 五项导航 + 空状态卡片 |
| 导航路由 | ✅ 点击"设置"跳转 /settings，标题与主题选项正确 |
| 深浅主题切换 | ✅ data-theme=light 生效、按钮文案切换、localStorage `nsfw-studio-theme=light` 持久化 |
| Engine 指示 | ✅ 绿点"Engine 在线"（后端在线时） |
| `npm run build`（tsc + vite） | ✅ 47 modules，JS 169.6KB（gzip 55.6KB） |

测试后已恢复默认深色主题、清除测试 localStorage、关闭浏览器标签页、停止两个 dev server。

## 四、测试中发现并修复的缺陷

| # | 缺陷 | 发现方式 | 修复 |
| --- | --- | --- | --- |
| 1 | `database/base.py` 使用 `create_engine` 未导入 | pytest（NameError） | 补充导入，复测通过 |
| 2 | `app.css` `@import './themes/tokens.css'` 相对路径错误 | 浏览器实测（Vite overlay 报 ENOENT） | 改为 `../themes/tokens.css`，热更新后正常 |
| 3 | npm optional deps bug + npmmirror 缺 `@rollup/rollup-win32-x64-msvc@4.64.1` | vite 启动崩溃 | 固定 `rollup@4.64.0` + 匹配原生包（写入 devDependencies） |

## 五、未执行 / 部分验证项（如实声明）

- ~~GitHub clone 验证：未执行~~ **已补充验证（2026-10-07）**：使用本机凭据管理器已存凭据创建仓库
  `https://github.com/zxingyu178-dot/nsfw-studio-v2`（创建时私有，同日应用户要求转为公开，供三方 AI 审核代码），
  推送 main / develop / tag v0.1.0 成功，`git ls-remote origin` 确认远端引用完整，可匿名 clone。
- 前端自动化测试（Vitest）：按规范属 Phase 1 范围，未包含。
