# Changelog — NSFW Studio V2

格式参考 Keep a Changelog；版本遵循 SemVer。

## [0.8.0] — 2026-10-09

### Fixed（Phase 6：Pipeline 可靠性收口）

- **Image → Workbench 生成上下文（Task1）**：从当前图沿父链找"距离最近、由 generate Job 产出、
  且使用 Seed"的图及其 Job（import→img2img→upscale 恢复 Img2Img，不再回到导入图）；
  `seed` 返回该生成上下文图片的真实 Seed（不再无条件树根 Seed）；
- **前端工作流身份保留（Task2）**：`normalizeModules()` 不再重建裸 `{module_id:'upscale'}`——
  从 History / Recipe / Image 恢复的 7 字段身份（含双 hash）与 config 在目录到达 / 模式切换后
  仍原样保留；只有用户手动开启高清才创建裸模块；
- **Recipe 固定 Seed（Task3）**：Recipe 不保存固定 Seed——"使用此图 Seed"的工作台保存配方时
  归一化为 `seed_mode=random / seed=null`（不再 400，也不强制改工作台状态）；
- **Pipeline 顺序与重复模块（Task4）**：移除硬编码 `MODULE_ORDER` 执行重排（严格保持
  用户/Recipe/Workbench 提供的顺序）；同一 module_id 重复出现 → `PIPELINE_DUPLICATE_MODULE`；
- **Module Availability 收紧（Task5）**：`module_version` 与 `binding_version` 不再互相 fallback；
  新 Job 将使用的 module 版本必须真实注册（否则 `available=false / module_version_not_registered`）；
  `/modules` 返回 `registered / available / module_version / provider / binding_version / unavailable_reason`；
  未注册 module_version 在 Job 创建期即拒绝（fail fast）；
- **Img2ImgModule.execute 契约（Task6）**：直接执行路径补齐 positive/negative Prompt
  （不再提交空 Prompt）；
- **generation_mode 显式化（Task7）**：WorkbenchSnapshot / Recipe / Job / History / Image restore
  全程保存与恢复 `text | image`（旧快照无该字段时按 input_images 推断，向后兼容）；
- **Module 参数元数据驱动（Task8）**：`ParameterSpec` 增加 `title / min / max / step / configurable`；
  前端按 schema 渲染 float/int/bool/enum 控件 + Primary Module 轻量选择器（denoise 滑杆
  不再按 module_id 硬编码）；
- **有效尺寸语义（Task9）**：`ModuleCapabilities.size_mode`（basic_generate=explicit、
  img2img/upscale=input）；图片生成模式 UI 不显示假宽高；History 任务详情显示
  "跟随输入图 W×H"（实际 Stage 输入尺寸）而不是 Workbench 遗留的 1024×1024。

### Changed

- **Img2Img 默认 denoise 0.55 → 0.8**（Task10 真实照片实测：0.55 即使给出不同场景 Prompt
  也"几乎没变化"（精修档）；0.8 在真实人像上人物保留良好且场景级 Prompt 明显生效。
  见 `docs/PHASE6_REPORT.md` §2）。滑杆仍为 0.05–1.0；binding.yaml / workflow.json
  指纹文件未改（历史 Job 的 hash 校验不受影响）；
- 素材 → 工作台快照显式标记 `generation_mode=text`；工作台"用作输入图 / 以此图进行图生图"
  显式进入图片模式。

### Tests

- 新增 `tests/backend/test_phase6_pipeline_reliability.py`（19 用例：Task1/3/4/5/6/7/8/9 回归，
  含 import→img2img→upscale 上下文、pinned 身份、重复/未注册模块、参数 schema、
  generation_mode 往返、execute 契约）；
- 新增 `tests/frontend/workbench_store.phase6.mjs`（11 断言，Playwright 之外零新依赖：
  用 vite SSR 加载真实 store；`npm run test:store` 已接入 CI）；
- 保持：全量快速套件 227 passed（208 基线 + 19 新增）。

### Chore

- 交接包：Qwen 实验证据迁至 `docs/evidence/phase51-img2img/`；新增
  `docs/evidence/phase6-img2img/`（真实照片验收输入/输出/报告/浏览器截图）；
  Source 包由 git tracked 维护（缓存文件确认未跟踪）；
- 版本 0.7.0 → 0.8.0（后端 / 前端 / configs 同步）。

## [0.7.0] — 2026-10-08

### Added（Phase 5.1：Image Pipeline Contract Closure + Qwen Img2Img）

- **WorkflowModuleRef 正式类型化（Task1）**：核心工作流契约从 `list[dict]` 升级为正式模型
  `WorkflowModuleRefModel`（module_id / module_version / provider / binding_version /
  workflow_hash / binding_hash / config），前后端（`frontend/src/types/workbench.ts`）双侧镜像；
  Job 响应 `workflow_snapshot` 同步使用正式类型。
- **Recipe 完整 Workflow 身份（Task2，P0 修复）**：`RecipeService._validate_workflow_snapshot`
  不再丢弃 provider / binding_version / 双 hash——历史 Job → 工作台 → 保存 Recipe → 重新打开，
  身份 100% 一致；**旧配方不会偷偷升级到新版 Workflow**；普通新建工作台保存配方时
  尽可能固化当前真实身份（与 Job 创建同一解析器；模块暂不可用时不阻塞保存）。
- **模块 config 单链（Task3）**：`Workbench.workflow_modules[].config` → `Recipe.workflow_snapshot`
  → `Job.workflow_snapshot` → `JobStage.config_json` 唯一事实源；`PipelineExecutor` 把
  `JobStage.config_json` 注入 `JobRequestContext.module_config`；Resume 完整保留 config；
  `stage_configs` 参数仅保留为内部/测试直调路径。
- **PipelineValidator（Task4/Task5，P0 修复）**：Job 创建前依据 ModuleCapabilities 统一校验
  Pipeline——`input_required=false` 携带输入图 → `UNUSED_INPUT_IMAGE`（输入图片不得被静默忽略）；
  需要输入图却没给 → `INPUT_IMAGE_REQUIRED`；Stage N 必须能接收 Stage N-1 输出（链式检查）；
  处理型 Job 仅 upscale；未知模块创建期拒绝；模块 `validate_config` 钩子（默认无约束）。
  判断不在 QueueWorker；`resume_remaining` 同样复核并重新冻结生成型输入图。
- **Img2ImgModule + img2img/v1 binding（Gate C 成功）**：第三套 WorkflowModule
  （uses_seed=true / input_kind=image / input_required=true / output_kind=processed /
  parent_policy=input_image），参数仅 `denoise`（0.05–1.0）；provider binding
  `workflows/providers/comfyui/img2img/v1/`（LoadImage → VAEEncode → KSampler denoise →
  VAEDecode → SaveImage，复用现有 Qwen-Image 2.1 三件套）。输出 = `kind=processed` +
  `parent_image_id=输入图` + StageItem 真实 Seed；**QueueWorker / PipelineScheduler /
  ImageService 核心零改动**。
- **工作台模式 ↔ Primary Module 绑定（Task6）**：文生图自动确保 `basic_generate`；
  图片生成自动切换到**可用**的图片条件模块（img2img）；禁止"图片生成 + basic_generate +
  输入图"自相矛盾状态；历史矛盾数据（Phase 5 旧配方）在模块可用时自动校正；
  图片生成 UI 新增"变化强度"滑杆（0.05–1.0）。
- **`/modules` 真实可用性（Task7）**：响应新增 `registered / available / provider /
  binding_version / unavailable_reason`；comfyui 下必须能加载 provider binding 才
  `available=true`（`binding_not_configured` / `binding_invalid`）；前端 Gate 只依据
  `available=true`（不因"代码里注册了模块"就显示可用）。
- **Face Asset 参考图清除（Task8）**：`POST /assets/{id}/versions` 新增
  `reference_action: inherit | set | clear`（缺省兼容旧语义）；UI [更换] / [移除]；
  clear = 新版本 reference=none，旧版本保留原参考图。
- **导入去重 DB 兜底（Task9）**：迁移 `0011_image_import_dedup_unique`——
  `images(sha256)` 部分唯一索引（source='import'）；并发 IntegrityError → 重新查询并返回
  已存在图片（duplicate），不是 500；迁移前防御性去重历史重复行（保留最早，不删数据）。
- **图库"以此图进行图生图"**：图片详情新增入口 → 打开图片生成工作台
  （mode=image、input_image=当前图、Primary Module=可用图生图模块）；
  有生成上下文恢复原 Prompt，外部导入 Prompt 为空（不伪造）。

### 实验（零下载 Qwen Img2Img，Gate C 成功）

- `docs/evidence/phase51-img2img/`：实验 Workflow（**不进入正式 providers 目录**）+
  spike 脚本 + 输入/输出/元数据。**未下载模型、未安装节点、未升级 ComfyUI、
  未修改用户工作流**。
- 实测（ComfyUI 0.37.0 / RTX 3060 Laptop 6GB / 768×768 / steps 25 / seed 20261008）：
  denoise 0.55 → 输出结构 ≈ 输入（像素 MAE 2.25/255，粗结构相关 0.9993）；
  denoise 1.0（同 seed/同 Prompt 对照）→ 完全由 Prompt 驱动的新图（结构相关 0.16）；
  无缺节点 / 无缺模型 / 无 OOM；输出尺寸正确、Seed 与 denoise 确实进入 KSampler。
  **结论：输入图对输出有决定性影响，未退化为文生图。**
- 详见 `docs/PHASE51_REPORT.md`。

### Changed

- **架构验收**：新增第三种 Module 仅需 `Img2ImgModule` + `img2img/v1` binding + 参数/UI——
  QueueWorker / PipelineScheduler / ImageService / Job 状态机零改动（与 Phase 5 §二十五 结论一致）。
- 迁移 `0011_image_import_dedup_unique`；版本 0.6.0 → 0.7.0（后端 / 前端 / configs/app.yaml 同步）。
- 文档：新增 PHASE51_REPORT；同步 README / AGENTS / CHANGELOG / TASKS / DEV_LOG /
  TEST_REPORT / WORKBENCH_STATE / MODULE_IO_CONTRACT / IMAGE_MODEL / API_PLAN /
  DATABASE_PLAN / DATA_MODEL_V1 / IMAGE_CONDITIONING_INVENTORY。

### Tests

- 新增 `tests/backend/test_phase51_contract.py`（15 用例：身份/配置单链/输入校验/
  /modules 可用性/参考图 clear/唯一索引与并发兜底）与
  `tests/backend/test_phase51_img2img.py`（7 用例：能力/config/processed 输出/
  parent/Seed/链式/Resume//modules）；
- Phase 5 专项测试更新：`basic_generate + 输入图 → UNUSED_INPUT_IMAGE`（原"允许"行为纠正）、
  `/modules` Gate C 断言（img2img registered + available）；
- 前端：`npm run build`（tsc + vite）通过；工作台 store 逻辑经
  临时 esbuild 断言脚本验证 9/9 PASS（Phase 6 起该脚本由 `tests/frontend/workbench_store.phase6.mjs`
  + CI `npm run test:store` 取代，临时目录已删除）。

## [0.6.0] — 2026-10-08

### Added（Phase 5：Image Input Foundation + Reference / Img2Img Capability Gate）

- **外部图片导入正式产品化（§三/§四/§五）**：`POST /api/v1/images/import`（PNG / JPG / JPEG / WEBP，
  单张 / 多张）；流程 = 选择本地文件 → 校验（扩展名 + MIME + magic bytes + 尺寸 + ≤10MB）→ Studio temp
  → 原子导入 → `DataRoot/images/originals/` → Image 数据库 → Gallery。**绝不引用用户原始文件路径**；
  来源统一 `kind=original / source=import / job_id=null`；外部导入的 Provenance 如实标记
  "外部导入"，无生成 Job 时返回 `IMAGE_NO_GENERATION_CONTEXT`（不伪造生成历史）。
- **sha256 去重（§六）**：新增 `images.sha256`（+索引）与 `images.imported_filename`；
  重复文件不创建第二份（返回已存在 image_id）；批量导入单张失败不影响整批
  （成功 / 已存在 / 失败 三类明细）；WEBP 尺寸解析（VP8 / VP8L / VP8X，无第三方依赖）。
- **图库批量导入 UI（§二十三）**：Gallery"导入"（多选 + 进度 n / N + 结果摘要"成功 N · 已存在 N · 失败 N"）。
- **工作台"输入图片"（§七/§八）**：生成页顶部模式切换 [文生图] / [图片生成]（不增加一级导航）；
  图片生成模式显示独立"输入图片"区（[+ 从图库选择] / [上传新图片 → 先行导入 Gallery 再引用]）；
  `WorkbenchSnapshot.input_images`（max=1，role=source，统一 `image_id`，禁止临时外部路径）。
- **Gallery Picker（§二十一）**：筛选（最近 / 未审核 / 保留 / 收藏）+ 搜索导入文件名；
  卡片 = 缩略图 / 尺寸 / 收藏；工作台与 Face Asset 参考图共用同一 Picker。
- **Gallery 快捷入口（§二十二）**：图片详情 Drawer"用作输入图片"→ 打开生成工作台并设置 input_image
  （当前工作台其它配置保留）。
- **Recipe 输入图快照（§九）**：recipe_versions 新增 `input_images_json`
  （image_id + file hash + role）；恢复配方原样恢复输入图关系；图片不存在 → 响应显式
  `missing=true`（界面显示"输入图片已丢失"，**绝不静默清空**）；input_images 参与
  "内容无变化不建新版本"的 signature 比较。
- **Job 创建冻结图片输入（§十）**：创建 Job 时从 WorkbenchSnapshot 冻结输入图片 →
  `JobStageItem.input_image_id`（Stage0 全部槽位）；**Job 创建后切换工作台图片不影响等待中的 Job**；
  输入图片不存在 → 创建期 404 `IMAGE_NOT_FOUND`；处理型 Job 快照与 input_image_ids 不一致 → 拒绝。
- **Face Asset Reference Image（§十二/§十三）**：新增正式关系表 `asset_reference_images`
  （asset_version_id / image_id / role / sort_order）；Face Asset 可绑定 1 张图库参考图
  （来源 = Gallery，不复制外部文件；绑定 / 更换 = 新版本，旧版本保留自己的参考图）。
- **ModuleCapabilities 输入声明（§十四）**：新增 `input_required / input_role`；
  `GET /api/v1/modules` 能力列表 → 前端图片生成 Gate 判定（无可用工作流时明确显示
  "图片生成：尚未配置可用工作流"并禁用提交，不猜测、不硬编码）。
- **ImageReferenceService（§十一）**：`GET /api/v1/images/{id}/references` 返回
  Recipe / StageItem（含活跃 Job）/ Asset 参考图 / Asset 溯源 / 派生图 的引用计数与明细
  （图片生命周期的删除前检查，Phase 5 不实现删除 UI）。
- **审图快捷键（§二十四）**：← / → 上一张 / 下一张，K 保留，R 淘汰，F 收藏；
  Ctrl+Z 或页面内"撤销"按钮撤销最近一次审核 / 收藏操作（栈深 20），不做复杂快捷键设置页。

### 能力 Gate（§二：本机调查结论 = Gate B，真实 Module 接入暂停）

- **Task 0 只读调查**（docs/IMAGE_CONDITIONING_INVENTORY.md；**未**下载模型 / 安装节点 /
  升级 ComfyUI / 更新 Manager / 移动模型 / 修改用户工作流）：本机**不存在**"现成、稳定、
  无需新增关键依赖"的参考图 / 图生图工作流 —— 唯一现成 Img2Img 工作流（`sdxl-图生图.json`，
  LoadImage→VAEEncode→KSampler denoise 0.55→VAEDecode）依赖的 `RealVisXL_V5.0_fp16` 与
  `add-detail-xl` 均不在磁盘；Reference / Face Reference / ControlNet / Qwen-Edit 均缺节点或模型
  （IPAdapter / PuLID / InstantID 节点不存在；controlnet / clip_vision / photomaker 目录为空）。
- **结论：需要新增模型/节点，已停止**；候选方案（方案 0 零下载 Qwen-2.1 latent Img2Img /
  方案 1 恢复 SDXL 链 / 方案 2 Qwen-Edit / 方案 3 IPAdapter）含模型、体积、显存、节点与
  ComfyUI 影响评估，见文档 §6，**等待用户选择**，未执行任何下载或安装。
- **本阶段零真实生图**（Gate B，§二十九）；"输入图片 → 新 Module → 现有 Pipeline → ComfyUI →
  Processed Image"链路待用户选定方案后接入（Phase 5.1）。

### Changed

- **架构验收（§二十五）**：未修改 QueueWorker / PipelineScheduler / ImageService 核心 /
  Job 状态机；输入图片冻结复用既有通用机制（快照 → StageItem.input_image_id + `_materialize_stages`），
  新增内容仅 = Module 能力字段（input_required/input_role）+ 通用图片输入层（导入/快照/引用检查）+ UI。
- 迁移 **`0010_image_inputs`**：`images.sha256/imported_filename`（+idx_images_sha256）、
  `recipe_versions.input_images_json`、`asset_reference_images` 关系表（+2 索引）。
- 版本：0.5.0 → 0.6.0（后端 / 前端 / configs/app.yaml 同步）。
- 文档：新增 IMAGE_CONDITIONING_INVENTORY（Task 0）与 PHASE5_REPORT；
  同步 API_PLAN / DATABASE_PLAN / DATA_MODEL_V1 / WORKBENCH_STATE / IMAGE_MODEL /
  MODULE_IO_CONTRACT / README / AGENTS / TASKS / DEV_LOG / TEST_REPORT。

### Tests

- 新增 `tests/backend/test_phase5_image_input.py` 18 例：导入（单张 / WEBP 尺寸 / 超限 / 非法类型）、
  sha256 去重（按内容不按文件名）、批量部分失败、Job 输入冻结（多槽位 / 缺失 404 / 多图 422 /
  处理型快照不一致）、Recipe 输入图快照（hash / 无变化不建版 / 恢复 / 丢失标记 / 未知图 404）、
  Face Asset 参考图（绑定 / 更换 / 沿用 / 非 face 拒绝 / 缺失 404）、引用保护（5 类来源计数与 0 引用）、
  Modules 能力（Gate B 判定）、迁移 0010 结构与幂等。
- 快速套件 168 → **186 passed**（Phase 4 全部回归继续通过）；前端 `npm run build`（tsc + vite）通过。

## [0.5.0] — 2026-10-08

### Added（Phase 4：History + Provenance + Generic Module I/O Contract）

- **历史正式可用**：`GET /api/v1/history`（来源 = jobs 表，不另建 History 表）+
  提示词页"历史"Tab：任务卡（时间/来源/Prompt 摘要/状态/数量/Pipeline/续跑标记）、
  基础筛选（全部/进行中/完成/失败/取消 + 来源）、右侧 Drawer（完整 Prompt / Negative /
  结构化字段 / 尺寸 / Seed / Workflow stages 与版本 / 错误 / 生成图片缩略图 +
  在生成工作台打开 / 在图库查看 / 继续剩余图片）。
- **续跑归组（Task6）**：沿 `resume_of_job_id` 归组为任务族（`root_job_id` 计算字段），
  A → B → C 续跑链在历史中显示为一个任务族（两级展示，不建复杂树）。
- **Image Provenance（Task10）**：`GET /api/v1/images/{id}/provenance` 返回
  parent/root/scale/job/stage/module/版本/双指纹/Seed；图库详情简洁展示 + 高级信息折叠。
- **派生图 → 工作台追溯根生成 Job（Task7）**：任何派生图（原图/高清/未来处理图）都恢复
  **根生成图所属 generate Job** 的配置；图库手动高清后的高清图不再恢复到 process Job 的空 Prompt；
  外部导入图明确返回 `IMAGE_NO_GENERATION_CONTEXT`（"没有可恢复的生成配置"）；
  "使用此图 Seed"改为"使用原图 Seed"（根图 Seed，高清图自身 seed 为 null）。
- **执行身份恢复（Task9）**：Image / History / 配方恢复出的 `workflow_modules` 携带完整身份
  （module/version/provider/binding_version/双指纹）；提交时按**原版本固定执行**，
  指纹不一致或 provider 不匹配直接拒绝（400），绝不静默升级到当前默认 Workflow。
- **前端 WorkflowModuleRef[] 列表化（Task8）**：工作台状态由 `upscaleEnabled` 布尔升级为
  `workflowModules: WorkflowModuleRef[]`（开关为派生值）；Phase 5 增加 Reference 只需列表加一项。
- **Module I/O 正式契约（Task2）**：ModuleCapabilities 新增
  `uses_seed / input_kind / output_kind / parent_policy / output_cardinality`；
  basic_generate `uses_seed=true, none→original, 无 parent`；upscale `uses_seed=false,
  image→upscaled, parent=input_image`；ImageService 按能力落库，**删除"有 input_image 就推断
  upscaled"的规则**（docs/MODULE_IO_CONTRACT.md）。
- **StageItem.seed（Task3）**：JobStageItem 新增真实 Seed（执行前落库；uses_seed=false 的 Stage
  为 NULL）；`JobItem.seed` 保留为基础生成快捷字段；图库手动高清不再产生"假 Seed"。
- **EngineAdapter 输入图片正式契约（Task4）**：`upload_input_image()` 进入基类契约
  （默认 `ENGINE_INPUT_UNSUPPORTED`，系统性）；ComfyUI / Mock 实现；UpscaleModule 删除 getattr
  duck typing；"构造引擎请求"阶段的系统性错误与提交阶段一致触发队列暂停。
- **binding_hash 执行指纹（Task1）**：`sha256(binding.yaml)[:16]` 与 workflow_hash 并列，
  进入 EngineBindingRef / Job / JobStage / workflow_snapshot / API / Image metadata；
  binding.yaml 改动（inputs/defaults/save_image_node/save_image_prefix 等）→
  `BINDING_HASH_MISMATCH` 拒绝执行；binding 自描述（module/provider/binding_version）一致性校验。
- **Studio Input Registry + TTL 清理（Task11）**：输入上传登记 `DataRoot/engine_inputs.json`；
  启动时只清理 NSFWStudio_inputs 下、已登记、无 RUNNING/INTERRUPTED 引用、超过 TTL（默认 24h）
  的文件；未配置 `comfyui.input_dir` 时安全跳过；绝不触碰其他 input 文件。

### Fixed

- **P0 历史 Job 无 Stage（Task0）**：v0.3.x 库执行 0007 后历史 Job 没有 Stage，
  Worker 领取后直接 FAILED（已复现）。新增 **`0008_pipeline_backfill`**：
  扫描 `jobs WHERE NOT EXISTS job_stages`，为每个旧 Job 回填 Stage0（basic_generate，身份继承
  Job 列）+ 对应 StageItem（状态/engine_job_id/图片关系从 JobItem 映射），**不改变历史 Job 本身状态**；
  并新增 **`0009_execution_fingerprint`**（jobs/job_stages.binding_hash + job_stage_items.seed +
  历史假 Seed 修正）。升级测试使用真实 v0.3.2 数据库（COMPLETED/QUEUED/PAUSED/INTERRUPTED），
  并验证 QUEUED Job 升级后仍可被同一 Worker 真实执行。
- **P1/P0 workflow_hash 覆盖不全（Task1）**：此前只校验 workflow.json，
  修改 binding.yaml（inputs/defaults/save_image_* 等）不会触发 hash 变化 → 已由 binding_hash 补齐。
- **P1 历史页面假空态（Task5）**："任务系统接入后自动记录"占位删除，历史正式接 Job 系统。
- **P1 派生图工作台恢复错误（Task7）**：高清处理 Job 的空 Prompt 不再被当作恢复源。

### Tests

- 新增 21 例：真实 v0.3.2 升级（含 QUEUED 可执行）、双指纹/自描述拒绝、能力驱动 kind/parent/seed、
  StageItem/manual Seed、EngineAdapter 输入契约（含不支持→系统性）、History 筛选与归组、
  派生图追溯、导入图无上下文、Provenance 全链路、Input Registry TTL 清理；
  快速套件 147 → **168 passed**；Phase 3 的 12 场景与 Phase 2.x 回归全部继续通过。
- 真实 ComfyUI 最短 smoke（Task13）：1 张基础图（768×1024，seed=1501957504）
  → 4x 高清（3072×4096，seed=null，parent 正确）→ History 任务族 → Gallery 父子 →
  从高清图打开工作台（恢复原 Prompt + 完整双指纹身份）；证据见 docs/PHASE4_REPORT.md。

### Changed

- 版本：0.4.0 → 0.5.0（后端 / 前端 / configs/app.yaml 同步）。
- 文档新增 PROVENANCE_SPEC / HISTORY_SPEC / MODULE_IO_CONTRACT / MIGRATION_0008_BACKFILL / PHASE4_REPORT；
  同步 PIPELINE_V2 / PIPELINE_STATE_MACHINE / UPSCALE_MODULE / COMFY_ADAPTER / IMAGE_MODEL /
  WORKBENCH_STATE / DATA_MODEL_V1 / DATABASE_PLAN / API_PLAN / JOB_STATE_MACHINE / RECOVERY_SPEC。

## [0.4.0] — 2026-10-08

### Added（Phase 3：Multi-stage Pipeline + Upscale）

- **多阶段管线**：新增 JobStage / JobStageItem（迁移 0007 + jobs.job_kind）；
  Job 创建时从 `workflow_snapshot.modules` 物化 Stage，**执行真源 = JobStage + workflow_snapshot**；
  Stage Gate 严格门控：`basic×N 全部 COMPLETED` 才启动 `upscale×N`，禁止交错与跨 Stage 抢跑。
- **UpscaleModule（第二套正式 WorkflowModule）**：标准输入只有 `input_image`；
  provider binding `upscale/v1`（4x-UltraSharp 链，复用本机已验证资源，见
  docs/UPSCALE_WORKFLOW_INVENTORY.md）；输入图片经 `POST /upload/image` 上传（Studio 唯一命名）。
- **图库已有图片单独高清**：`POST /api/v1/images/upscale` 创建 upscale-only `process` Job，
  与生成流水线共用同一 QueueWorker / UpscaleModule（禁止两套高清代码）。
- **Image 父子关系**：高清 `kind=upscaled` 存 `images/upscaled/`，`parent_image_id` 指向原图；
  `GET /images/{id}/versions` 支持原图 ↔ 高清切换；图库 HD 标记与多选"高清放大"。
- **前端**：工作台"② 高清放大"开关（配方保存/恢复 100% 一致）；分阶段实时进度
  （原图生成 x/y ✓、高清放大 m/n · 第 k 张 · p%）；缩略图 HD 标记。
- **Job API**：Job Detail 返回 `stages[]`（module/status/total/completed/current_item/progress）。

### Fixed（Task 0 执行漏洞修复）

- **§0.1 Worker 意外异常必须停队列**：代码级意外异常（非 EngineError）→ 当前 Job/Stage
  INTERRUPTED（保留 engine_job_id）+ `queue_paused=true` + WORKER_INTERNAL_ERROR，绝不继续领取
  下一个 Job；正常 shutdown 的 CancelledError 仍按原崩溃恢复逻辑（不写终态）。
- **§0.2 Binding 改为每次请求动态选择**：取消 Adapter 实例级绑定；新增 `EngineBindingRef`
  （module/module_version/provider/binding_version/workflow_hash），Adapter 按
  `(module_id, binding_version)` 缓存动态加载——一个 Adapter 服务全部模块。
- **§0.3 Workflow Hash 必须校验**：Job 固化的 workflow_hash 与磁盘不一致 →
  `WORKFLOW_HASH_MISMATCH`（系统性）拒绝执行；binding 目录视为 immutable，改 Workflow 必须新建 v2。
- **§0.4 修正固定 Seed**：恢复"每张独立随机 Seed"；`seed_mode=fixed` 仅用于单张精确复现
  （后端 fixed+count>1 → 400 FIXED_SEED_SINGLE_ONLY；前端"使用此图 Seed"自动 count=1，
  数量改 >1 自动切回随机）；删除 `base_seed + item_index`。
- **§十 执行总超时**：StageItem `execution_timeout`（默认 1800s，可由 Stage config 覆盖）→
  `ENGINE_TIMEOUT`，不无限 RUNNING。
- **§九 文件系统恢复**：ComfyUI SaveImage 输出前缀含 Studio 身份
  （`NSFWStudio/{job_short}/{stage}/{item_short}`）；history 丢失时按命名规则扫描自有输出兜底
  （绝不触碰用户普通图片）。

### Changed

- `WorkflowModule.execute()` / `build_engine_request()` 契约扩展：binding 来自 context（请求级）；
  `prepare_inputs()` 可选钩子（处理型模块的引擎侧输入准备）。
- `JobService.create_job`：workflow_modules / job_kind / input_image_ids / stage_configs；
  未知模块在创建期拒绝（400 WORKFLOW_ERROR）。
- 文档新增 PIPELINE_V2 / PIPELINE_STATE_MACHINE / UPSCALE_MODULE / UPSCALE_WORKFLOW_INVENTORY；
  同步 JOB_STATE_MACHINE / RECOVERY_SPEC / COMFY_ADAPTER / IMAGE_MODEL / WORKBENCH_STATE /
  DATA_MODEL_V1 / DATABASE_PLAN / API_PLAN / README / AGENTS。

## [0.3.2] — 2026-10-07

### Fixed（Phase 2.2：Data Consistency & Recovery Closure，无新功能）

- **P0 多输出导入整批原子化**：拆分为 `prepare_image_output()`（全部先校验）+
  `import_outputs_transaction()`（全部写 temp → 全部移动 → 单事务写入全部 Image）；
  任一步失败：回滚 DB + 删除本批次全部正式文件 + 清理 temp，不再出现"半成功图库资产"。
  `import_adapter_outputs()` 不再循环调用内部 commit 的单图函数。
- **P0 崩溃恢复后的 Job 终态归并**：恢复核对后重算 completed_count；全部 Item COMPLETED →
  Job COMPLETED + finished_at + `JOB_RECOVERED_COMPLETED` 事件；仍有未完成 Item → 保持
  INTERRUPTED。禁止"全部 Item COMPLETED 但 Job INTERRUPTED"。
- **附带修复（实测发现）**：Worker 任务被取消（进程退出/停机超时）或意外异常时不再经
  `finally` 写 Job 终态——此前会把仍有未完成 Item 的 Job 误标为 COMPLETED；现在保持
  RUNNING 现场，交由下次启动恢复。
- **P1 Resume 保持原 Workflow 身份**：`resume_remaining()` 完整继承 Parent 的
  workflow_snapshot + module/provider/binding/workflow_hash，不再读取当前 settings，
  禁止静默升级；原 binding 缺失时执行期报 BINDING_NOT_FOUND。升级 Workflow 属于创建新 Job。
- **P1 ComfyUI 取消不误伤其他任务**：先读 `/queue` 判断 target 位置——pending 只 delete、
  绝不 `/interrupt`；target 正是当前 running 才允许 interrupt；running 是别人的 prompt 时
  什么都不做（不再打断用户手工任务）。
- 文档同步：IMAGE_MODEL / RECOVERY_SPEC / COMFY_ADAPTER / JOB_STATE_MACHINE / QUEUE_SPEC /
  PHASE2_1_REPORT（原子化交叉引用）/ TEST_REPORT / DEV_LOG / TASKS / README。

### Tests

- 新增 9 例（批次原子 3 + 恢复归并/Resume 身份 3 + 取消边界 3）；快速套件 120 → **129 passed**；
  本阶段全部离线 Mock / stub 验证（合同不要求真实生成）；前端 build 通过。

## [0.3.1] — 2026-10-07

### Fixed（Phase 2.1：Stable Execution & Pipeline Contract Closure，无新功能）

- **P0 无图片却 COMPLETED**：Item COMPLETED 收紧为"engine succeeded ∧ 输出非空 ∧ 成功导入
  Studio Image（image_ids 非空）"；OUTPUT_MISSING / STORAGE_ERROR / 取输出异常一律
  Item FAILED + Job FAILED + `completed_count` 不增加 + `image_id=null`；崩溃恢复路径同步收紧。
- **ComfyUI 掉线后永久 RUNNING**：`/history` 请求失败不再伪装成"还在运行"——
  ConnectError → ENGINE_OFFLINE（Job FAILED + 队列暂停），其他网络错误 → ENGINE_NETWORK(transient)
  有限重试；history 可达但任务缺失时结合 `/queue` 与实时层新鲜度判定，超容忍才 unknown（任务丢失）。
- **Worker 硬编码模块参数**：新增 BasicGenerateModule + ModuleRegistry + PipelineExecutor，
  Worker 经 `PipelineExecutor.build_engine_request(job, item, seed)` 取请求，源码级守卫
  （测试）禁止 Worker 出现模块参数名。
- **Workflow Snapshot 与真实执行不一致**：Job 创建/续跑时由 module_identity 写入
  `modules:[{module_id,module_version,provider,binding_version,workflow_hash}]`。
- **Resume 复用 fixed seed**：resume-remaining 生成新快照（`count=remaining, seed_mode=random,
  seed=null`，workbench + generation_settings 同步）；父 Job 快照只读不变。
- **priority 越过拖拽顺序**：queue_position 成为唯一执行顺序事实源（Worker 领取 / GET /queue /
  reorder 统一排序）；`queue_mode=next` 仅通过插入位置实现；priority 保留但不参与排序。
- **Binding 版本硬编码**：Adapter 按 `module_id + binding_version` 解析
  `workflows/providers/comfyui/<module>/<version>/`；缺失 → 新错误类型 `BINDING_NOT_FOUND`
  （系统性；Job 创建时返回 4xx）。
- **Job API 输入过宽**：snapshot 直接复用严格 WorkbenchSnapshotModel（宽高 64–4096、
  count 1–64、seed 范围、prompt_mode/selected_assets/workflow_modules 结构 → 422）；
  Prompt 长度上限（结构化 ≤2000 / 正向 ≤10000 / 负向 ≤8000 → 400 PROMPT_TOO_LONG）。
- **Cancel 请求异常**：取消请求 try/except 隔离，失败时当前 Item 可完成、完成后 Job 安全落 CANCELLED。
- **Handoff ZIP 无 .git 可测**：gitignore 断言改为 .gitignore 文本规则（存在 .git 时才附加
  git check-ignore 核对），交接包解压后快速套件可独立运行。

### Tests

- 新增 `test_phase21_stability.py`（22 例）与 `test_comfyui_resilience.py`（7 例）；
  快速套件 91 → **120 passed**；真实 ComfyUI smoke（1 张）见 docs/PHASE2_1_REPORT.md。

## [0.3.0] — 2026-10-07

### Added（Phase 2：Job Execution Core + ComfyUIAdapter + Gallery）

- **数据模型**：jobs / job_items / job_events（migration 0005）、images（migration 0006）；
  `UNIQUE(source, client_request_id)` 外部幂等；Job 固化 WorkbenchSnapshot + Prompt + 素材/尺寸/数量 +
  Workflow 快照（后续修改 Prompt/Recipe/Asset 不影响已创建 Job）。
- **Job 执行核心（2A）**：JobService（创建 / 幂等 / 状态操作 / 续跑剩余）；单队列 SingleQueueWorker
  串行执行（唯一逻辑队列）；安全暂停（当前图完成后）、取消（终态、已完成图片保留）、
  继续（已完成 Item 绝不重跑）；每张图独立随机 Seed（执行时分配）；
  系统性失败（离线/OOM/工作流/模型/节点缺失）→ Job FAILED + 队列自动暂停；
  崩溃恢复（启动 RUNNING → INTERRUPTED，engine history 核对后导入或保持可恢复）；
  磁盘空间检查（严重不足拒绝新任务）。
- **Engine 层**：输出获取接口 + 错误分类（ENGINE_OFFLINE/NETWORK/WORKFLOW_ERROR/MODEL_MISSING/
  NODE_MISSING/OUT_OF_MEMORY/OUTPUT_MISSING/STORAGE_ERROR/UNKNOWN）+ 瞬态重试 ≤2 +
  MockEngineAdapter（success/delay/fail/offline/oom/workflow_error，仅测试用）+ 引擎工厂。
- **SSE 与 Job API**：`GET /api/v1/events/jobs`（只通知，DB 才是事实源）；
  POST/GET /jobs、pause/resume/cancel、resume-remaining、/queue、/queue/reorder、/queue/resume、
  /engine/status；`queue_mode: normal|next`。
- **真实 ComfyUI 接入（2B）**：本机环境调查（docs/COMFY_ENV_INVENTORY.md、WORKFLOW_INVENTORY.md，
  未破坏现有环境）；ComfyUIAdapter（POST /prompt + WebSocket 进度 + /history 核对 + /view 取回字节 +
  错误分类 + 安全取消）；provider binding（workflows/providers/comfyui/basic_generate/v1：
  Qwen-Image 2.1 UC 文生图链，支持 Negative，steps=25/cfg=1.0）；
  Job 记录 module/provider/binding_version/workflow_hash 溯源；机器地址只进 config.local.yaml。
- **Image / 图库（2C）**：引擎输出 → Studio temp → 校验（magic bytes + 尺寸）→ 原子移动
  DataRoot/images/originals → DB 登记；Gallery API（列表过滤/详情/content/review/favorite/
  workbench/by-job summary）；图库页（筛选 全部/未审核/保留/收藏/淘汰 + 图片 Grid + 详情 Drawer +
  按任务查看 + 保留/淘汰/收藏 + Image → 工作台 + 使用此图 Seed + 从图库创建素材 source_image_id）。
- **前端**：顶部双状态 Studio ● / Engine ●；右栏真实 Engine 状态 + 生成按钮（POST /jobs，
  normal/优先插队）+ 当前任务进度（第 N 张 / %）+ 队列（暂停/继续/取消/优先/拖拽排序）；
  中栏当前图 + 本 Job 已完成缩略图逐张显示（续跑父子合并）；SSE 实时刷新（断线回源 + 兜底轮询）；
  WorkbenchStore 支持固定 Seed。
- **测试**：新增 Job 队列与 Mock 故障套件（§五十八 全清单）、Image 服务/API 套件、
  binding 单测（无需 ComfyUI）、真实 ComfyUI 集成测试（1/3/8 张，离线自动跳过）。
- **文档**：JOB_STATE_MACHINE / QUEUE_SPEC / RECOVERY_SPEC / COMFY_ADAPTER / IMAGE_MODEL /
  COMFY_ENV_INVENTORY / WORKFLOW_INVENTORY 新增；DATA_MODEL_V1 / DATABASE_PLAN / API_PLAN /
  WORKBENCH_STATE / README / AGENTS 同步。

### Changed

- 公共默认引擎：`workflow.engine.provider = comfyui`（产品默认；测试/CI 用 mock；
  公共配置仍不得携带机器地址）。
- 版本：0.2.0 → 0.3.0（后端 / 前端 / configs/app.yaml 同步）。

## [0.2.0] — 2026-10-07

### Added（Phase 1：Prompt / Asset / Recipe Core）

- **数据模型**：prompts/prompt_versions、assets/asset_versions、recipes/recipe_versions/recipe_asset_snapshots
  （migration 0002/0003/0004；TEXT 主键 + `<前缀>_<uuid4>`；FK/UNIQUE/CHECK 全量约束；业务时间统一 UTC ISO 8601）。
- **Prompt**：结构化（固定八栏）/完整双模式；Negative Prompt 独立字段；内容变化建版本、元数据不建；
  版本 immutable；恢复旧版本 = 复制为新最新版；归档/恢复（软删除）；PromptComposer 后端权威合成
  + `/api/v1/prompts/compose` 前端同源预览。
- **Asset**：face/clothing/pose/scene 四分类；预览图上传（扩展名+MIME+magic bytes+大小≤10MB 校验）；
  temp → 校验 → 原子移动 → 提交 的安全文件流（提交失败清理文件）；DataRoot 相对路径入库；
  `StorageManager.resolve_under()` 防路径穿越；版本 immutable。
- **Recipe**：完整工作台快照（Prompt 快照+来源 FK、素材按 slot 锁定 asset_version 并复制内容快照、
  generation_settings（model_ref 占位槽位）、workflow_snapshot 预留 modules 结构、seed 固定 random）。
- **API**：/api/v1/prompts、/api/v1/assets、/api/v1/recipes 全套 CRUD+版本+归档+预览图+compose；
  统一错误格式 `{"error":{"code","message"}}`；列表统一 search/favorite/archived/limit/offset。
- **前端**：WorkbenchStore 统一工作台状态；生成工作台三栏（左 Prompt 编辑/中 预览占位/右 基础配置）；
  提示词页（我的 Prompt / 配方 / 历史 三 Tab + 编辑抽屉 + 版本历史）；素材页（分类 Tabs + 卡片网格 +
  上传 + 详情抽屉 + 用于生成）；"在生成工作台打开" 100% 恢复（Prompt / Recipe / Asset 三条注入路径复用
  WorkbenchSnapshot）；生成按钮明确显示"生成引擎尚未接入"。
- **测试**：33 → 68 例（Composer/服务/事务回滚/约束/迁移升级/文件安全/API 全链路）。
- **文档**：docs/DATA_MODEL_V1.md、docs/WORKBENCH_STATE.md 新增。

## [0.1.2] — 2026-10-07

### Changed（Phase 0.1.1：审查合同遗留契约修正）

- **统一异步契约**：`WorkflowModule.execute()` 改为 async（执行链路固定为
  Pipeline → WorkflowModule → EngineAdapter → 具体引擎，全部 await）；
  `validate_input()` / `capabilities()` 纯计算接口保持同步；异步原则写入模块 docstring 与开发指南。
- **DataRoot 配置分层**：公共 `configs/config.yaml` 不再携带任何机器路径（不设置 data_root）；
  新增本机私有层 `configs/config.local.yaml`（已 gitignore，不提交）。
  优先级固定：`NSFW_STUDIO_DATA_ROOT` > `config.local.yaml` > `config.yaml` > `%USERPROFILE%/NSFW-Studio-Data`。
  换电脑 clone 后零修改即可启动；本机 D 盘只存在于 local 文件。
- **Node 探测**：`dev_frontend.bat` 优先读取 `AIHOME_ROOT` 环境变量定位 AIHome Node，
  兼容探测规范默认根目录，最后回落系统 PATH。

### Added

- 新增 6 个测试（execute 为 async / EngineAdapter 全方法 async / 纯计算接口保持 sync /
  公共配置机器无关哨兵 / local 覆盖 / env 最高优先级 / config.local.yaml 被 gitignore），共 33 例。

## [0.1.1] — 2026-10-07

### Fixed（Phase 0.1：架构收口）

- **迁移失败恢复**：`applied_migration_ids()` 只把 `status='applied'` 视为已完成；failed 迁移下次启动仍按未完成重试；重试前清除同 ID failed 记录，避免主键冲突。
- **跨机器可移植**：代码默认 DataRoot 改为 `%USERPROFILE%/NSFW-Studio-Data`（本机盘符只在 configs/config.yaml 明确声明）；`dev_frontend.bat` 不再写死 AIHome 路径（AIHome 存在则用，否则回落系统 PATH，均无则清晰报错）。
- **状态语义**：前端顶部指示改为 "Studio 在线/离线"（只反映后端健康，不再显示虚假的 Engine 连接状态）。

### Added

- SQLite 工程化：`make_engine()` 统一 `journal_mode=WAL`、`busy_timeout=5000`、`foreign_keys=ON`。
- 数据库安全备份：`app/database/backup.py`（SQLite backup API）+ `scripts/backup_db.py`；DataRoot 新增 `backups/`。
- Workflow 标准契约：`WorkflowInput` / `WorkflowOutput` / `WorkflowValidation` / `ModuleCapabilities` / `ParameterSpec`；`WorkflowModule.execute()` 接收 EngineAdapter（引擎调用只发生在 EngineAdapter）。
- EngineAdapter 类型化：`EngineJobRequest` / `EngineJobStatus`（含进度字段）。
- GitHub CI（`.github/workflows/ci.yml`）：push/PR 自动跑 pytest 与 `npm ci && npm run build`。
- 新增 12 个测试（迁移失败恢复 / PRAGMA 生效 / 备份一致性 / 路径可移植 / 环境变量覆盖 / 契约存在性 / system_info 版本更新），共 27 例。

### Changed

- `QueueWorker` 移除 `submit(job)`：Job 的创建与持久化属于 API/JobService，Worker 只消费已存在的 Job（`process_job(job_id)`）。
- `system_info.version` 语义明确为**当前应用版本**：启动时与应用版本对齐，不一致自动更新。

## [0.1.0] — 2026-10-07

### Added（Phase 0：工程初始化与架构搭建）

- 后端骨架：FastAPI 应用工厂、lifespan 启动引导、health API（`GET /api/v1/health`）。
- 配置系统：`configs/{config,app,storage,workflow}.yaml`，支持 `NSFW_STUDIO_DATA_ROOT` / `NSFW_STUDIO_HOST` / `NSFW_STUDIO_PORT` 环境变量覆盖。
- DataRoot 系统：首次启动按 `storage.yaml` 清单自动创建 15 个目录（幂等）。
- 数据库基础：SQLAlchemy 2 + SQLite；`migration` 表、`system_info` 表、极简迁移框架。
- 日志系统：JSON Lines，app / jobs / errors 三路文件 + 控制台，5MB×5 轮转。
- 接口预留（仅规范，无实现、无引擎绑定）：`WorkflowModule`、`EngineAdapter`、`QueueWorker`。
- 存储管理：`StorageManager`（DataRoot 白名单路径解析）。
- 前端壳：React 18 + TypeScript + Vite 5；顶部导航（生成/图库/提示词/素材/设置）、
  Engine 健康指示、ThemeProvider 深浅主题（localStorage 持久化）、五页面空状态。
- 测试：pytest 15 例（后端启动 / API / 数据目录 / 数据库 / 接口存在性 / 幂等性）。
- 脚本：`dev_backend.bat`、`dev_frontend.bat`、`init_dataroot.py`、`build_handoff.py`。
- 文档：`docs/` 五份 + `DEV_LOG.md` / `TASKS.md` / `TEST_REPORT.md`。
