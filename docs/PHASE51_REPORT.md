# PHASE51_REPORT — Image Pipeline Contract Closure + Qwen Img2Img（v0.7.0）

> 日期：2026-10-08 ｜ 版本：0.7.0 ｜ 基线：v0.6.0 (f7d8ebd) ｜ 分支：feature/phase51-contract-img2img
> 目标：先把图片 Pipeline 契约漏洞收口（Task1-9），再用**现有 Qwen-Image 2.1 做零下载 latent
> Img2Img 实验**（Task10-12）；成功 → 正式落地 Img2ImgModule 并发布 v0.7.0；失败 → 只发布修复版。
>
> **Gate C 结论：成功。** Img2ImgModule 已正式接入（img2img/v1 binding），版本 v0.7.0。

## 0. 结论先行

1. **契约收口全部完成**（含两个 P0）：Recipe 完整 Workflow 身份、输入图片不可静默忽略、
   模式 ↔ Primary Module 绑定、`/modules` 真实可用性、config 单链、参考图清除、导入唯一索引兜底。
2. **零下载实验成功**：不复用任何新模型（现有 Qwen-Image 2.1 三件套），
   `LoadImage → VAEEncode → KSampler(denoise) → VAEDecode → SaveImage` 真实跑通；
   denoise 0.55 输出保留输入结构（粗结构相关 0.9993），同 seed/prompt 的 denoise=1.0 对照
   完全由 Prompt 驱动（结构相关 0.16）→ **输入图对输出有决定性影响，未退化成文生图**。
3. **架构验收通过（关键）**：新增第三种 Module 只做了三件事——
   新增 `Img2ImgModule` + 新增 `img2img/v1` provider binding + 新增参数/UI；
   **QueueWorker / PipelineScheduler / ImageService / Job 状态机核心零改动**。
   这证明「WorkflowModule 像积木一样可插拔」的架构成立。

## 1. Part A：图片 Pipeline 契约收口（Task1-9）

### Task1 WorkflowModuleRef 正式类型化

- 新增 `WorkflowModuleRefModel`（backend/app/schemas/workbench.py）：
  `module_id / module_version / provider / binding_version / workflow_hash / binding_hash / config`；
- `WorkbenchSnapshotModel.workflow_modules`、`WorkflowSnapshotModel.modules`、
  `JobResponse.workflow_snapshot` 全部使用正式类型；前端 `WorkflowModuleRef`（+ config）镜像；
- 核心工作流契约不再使用无约束 `list[dict[str, Any]]`。

### Task2 Recipe 完整 Workflow 身份（P0 修复）

- **修复前**：`RecipeService._validate_workflow_snapshot()` 只留下 module_id / module_version / config，
  provider / binding_version / workflow_hash / binding_hash 全部被丢弃 → 老配方可能偷偷换新 Workflow。
- **修复后**：7 字段全部保留；`RecipeVersion` immutable → 关闭再打开 100% 一致；
- 新增行为：保存配方时**尽可能固化当前真实身份**（与 Job 创建同一 `resolve_workflow_modules` 解析器；
  模块暂不可用时不阻塞保存、不做静默降级）；
- 测试：`test_recipe_preserves_full_workflow_identity`、`test_recipe_identity_never_silently_upgrades`
  （v1 保存 → 系统默认切 v2 → 重开仍 v1 + 原双 hash、提交 Job 固定 v1）、
  `test_recipe_unpinned_module_resolves_identity_at_save`。

### Task3 config 单链（唯一事实源）

```
Workbench.workflow_modules[].config
  → Recipe.workflow_snapshot（保存/恢复）
  → Job.workflow_snapshot（_merge_module_configs）
  → JobStage.config_json（_materialize_stages，逐 Stage 对应模块 config）
  → PipelineExecutor → JobRequestContext.module_config → 模块 build_engine_request
```

- `stage_configs` 仅保留为内部/测试直调路径（显式提供时优先），新 API 不再依赖；
- Resume 完整继承 config（原快照 → 新 Stage），另有测试；
- 测试：`test_recipe_config_roundtrip`（含"config 改变 → 新版本"）、
  `test_job_stage_config_json_materialized`。

### Task4/Task5 PipelineValidator（P0 修复 + 统一校验）

**修复前**：Workbench 携带输入图 + Pipeline=basic_generate → 照常创建 Job，
输入图被静默忽略（Phase 5 测试甚至把该行为当作允许）。

**修复后**：Job 创建前由 `PipelineValidator`（services/pipeline_validator.py）依据
ModuleCapabilities 统一校验，**判断不写进 QueueWorker**：

| 规则 | 错误码 |
| --- | --- |
| Stage0 `input_required=false` 却携带输入图 | `UNUSED_INPUT_IMAGE`（400） |
| Stage0 `input_required=true` 却没给输入图 | `INPUT_IMAGE_REQUIRED`（400） |
| Stage N 不消费 Stage N-1 输出 / 上游输出非图片产物 | `PIPELINE_INVALID`（400） |
| 处理型 Job 非 upscale-only | `PIPELINE_INVALID`（400） |
| 模块未注册 | `WORKFLOW_ERROR`（400） |
| 模块 config 非法（validate_config 钩子） | `MODULE_CONFIG_INVALID`（400） |

- `WorkflowModule.validate_config()` 为新钩子（默认无约束；Img2ImgModule 校验 denoise 0.05–1.0）；
- `resume_remaining` 同样复核 Pipeline，并把生成型 Job 的输入图从 Parent 快照**重新冻结**到剩余槽位
  （修复"续跑静默丢输入图"隐患）。

### Task6 工作台模式 ↔ Primary Module 绑定

- store（workbenchStore.ts）新增 `moduleCatalog` + `availableImageModuleIds` /
  `isImageCapablePrimary` / `normalizeModules`；
- 文生图 → primary 自动为 `basic_generate`；图片生成 → primary 自动为**可用**图片条件模块（img2img）；
- 禁止"图片生成 + basic_generate + 输入图"提交（Gate 提示区分"无可用工作流"与"当前工作流不接受输入图片"）；
- 历史矛盾数据（Phase 5 时期保存的 basic_generate + 输入图配方）在模块可用时自动校正为 img2img；
- 恢复路径的**完整执行身份**（含双指纹）在模块可用时原样保留，不因模式切换丢失。

### Task7 `/modules` 真实可用性

```json
{ "module_id": "img2img", "registered": true, "available": true,
  "provider": "comfyui", "binding_version": "v1", "unavailable_reason": null, ... 能力字段 }
```

- comfyui：必须能加载 provider binding（目录 / 自描述 / 指纹）→ `available=true`；
  否则 `binding_not_configured` / `binding_invalid` / `binding_unavailable`；
- mock：available=true；unbound：`engine_not_configured`；
- 前端 Gate（GeneratePage/SettingsPane）唯一依据 `available=true`。

### Task8 Face Asset 参考图清除

- `POST /api/v1/assets/{id}/versions` 新增 `reference_action: inherit | set | clear`（缺省兼容旧语义）；
- `clear` = 新版本 reference=none（旧版本保留原参考图，immutable）；UI：[更换] / [移除]；
- 测试：`test_face_asset_reference_can_be_cleared`（含"无变化不建新版本"与非法 action 400）。

### Task9 导入去重 DB 兜底

- 迁移 `0011_image_import_dedup_unique`：
  `CREATE UNIQUE INDEX uq_images_import_sha256 ON images(sha256) WHERE source='import' AND sha256 IS NOT NULL`；
  迁移前防御性去重（重复历史行保留最早一行，其余 sha256 置空——不删数据、不改文件）；
- `import_images_batch` 捕获 IntegrityError → 重新查询并返回 duplicate（已存在 image_id），绝非 500；
- 测试：`test_migration_0011_unique_index`、`test_import_duplicate_sha_guard`
  （直接 INSERT 重复 → IntegrityError；模拟并发窗口 → duplicate + 库中仅一行）。

## 2. Part B：Qwen Img2Img 零下载实验（Task10-12）

### 2.1 实验资产（temp/experimental/qwen_img2img/，**不进入正式 providers 目录**）

| 文件 | 内容 |
| --- | --- |
| `workflow.json` | 实验图：LoadImage(4) → VAEEncode(5) → TextEncodeQwenImage21(6) → KSampler(7, latent=5) → VAEDecode(8) → SaveImage(9)；模型 = 现有 qwen-image-2.1-UC-Q4 / qwen3vl_8b_w4a8 / qwen 2.1 VAE |
| `spike.py` | 上传（NSFWStudio_experiment subfolder）→ /prompt → 轮询 /history → /view 取回 → 元数据落盘 + 技术断言（trust_env=False，与产品 Adapter 一致） |
| `make_input.py` | 合成结构输入图（768×768：绿横带 / 红圆 / 蓝方 / 黄三角 / 白点） |
| `outputs/` | 输入与输出 PNG、sha256、尺寸、patched workflow、history、耗时、断言结果 |

**零下载确认**：未下载任何模型、未安装节点、未升级 ComfyUI、未改用户工作流；
只读使用 ComfyUI 0.37.0（ControlHub 计划任务托管，未启停服务）。

### 2.2 实测记录（ComfyUI 0.37.0 / RTX 3060 Laptop 6GB / 768×768 / steps 25 / cfg 1.0 / euler+simple / seed 20261008）

| 运行 | denoise | Prompt | 输出 | GPU 采样耗时 | 与输入差异（MAE/255） | 粗结构相关 |
| --- | --- | --- | --- | --- | --- | --- |
| d055（主实验） | 0.55 | 禅意水园（与输入内容无关） | 结构≈输入 | ≈310s（总 716s 含排队） | 2.25（0.42% 像素差>30） | **0.9993** |
| d080（中间点） | 0.8 | 同 d055 | 结构保留 + 局部形状向 Prompt 语义变形（三角→山岩、圆点→卵石） | ≈496s（总 1202s 含长时间排队） | 7.30（3.52%） | **0.9886** |
| d100（对照） | 1.0 | 同 d055 | 完全由 Prompt 驱动的新图（水彩园景） | ≈306s（总 919s 含排队） | 63.80（97.75%） | 0.1620 |

> 耗时口径：GPU 采样 = ComfyUI history `execution_start → execution_success`（metadata 的
> `gpu_sampling_seconds`）；总耗时含排队等待（共享 GPU 上同时有用户任务与其他实验在跑）。

核对（Task12 技术成功标准）：输入上传 ✅ / 执行成功 ✅ / 无缺节点缺模型 ✅ / 无 OOM ✅ /
输出有效 PNG 且尺寸=输入（768×768）✅ / Seed 与 denoise 确实进入 KSampler（patched workflow +
history success）✅。

### 2.3 结论（人工判读）

- denoise 0.55：输出在布局、色块位置与输入几乎一致（结构相关 0.999），**输入图完全主导结构**；
  提示词在该强度下只带来轻微纹理变化 → 满足"输入图对输出产生明显影响"的判定；
- denoise 1.0（同 seed/prompt）：输出与输入无任何结构关系（相关 0.16），完全由 Prompt 生成为
  一张新的水彩园景 → 证明采样器真实执行、denoise 参数确实生效，且 0.55 的近恒等不是"采样未跑"的假象；
- **未出现"技术上出图但退化为文生图"**；输入尺寸 / 输出尺寸 / Seed 全链可追溯。

### 2.4 denoise 曲线判读（默认值依据）

| 对比 | MAE/255 | 像素差>30 | 粗结构相关 |
| --- | --- | --- | --- |
| input vs d055 | 2.25 | 0.42% | 0.9993 |
| input vs d080 | 7.30 | 3.52% | 0.9886 |
| input vs d100 | 63.80 | 97.75% | 0.1620 |
| d080 vs d100 | 62.66 | 96.29% | 0.1914 |

- 曲线形态：0.55 ≈ 保守（近恒等，仅轻微纹理变化）；0.8 = **结构保留 + 可见语义变形**
  （三角→山岩、圆点→卵石，提示词开始起作用）；1.0 = 完全重绘（退化为文生图行为）。
- 默认值取舍：正式模块默认取 **0.55**（Gate C 实测值、最保守、不会让用户"什么都没发生又惊到"）；
  UI 滑杆 0.05–1.0 覆盖完整区间，需要强变化时由用户上调（0.8 已验证可用）。
- 说明：本实验输入为合成几何图；真实照片在 0.55 下的观感未做人工评估（见 §5 限制）。

## 3. Gate C 判定与正式 Img2Img 落地

### 3.1 判定

实验满足全部技术标准且输入影响确凿 → **Gate C 成功** → 按合同继续正式实现，版本 v0.7.0。

### 3.2 Img2ImgModule（backend/app/workflows/img2img.py）

| 能力 | 值 |
| --- | --- |
| module_id / module_version | `img2img` / `v1` |
| uses_seed | true（StageItem 记录真实 Seed） |
| input_kind / input_required / input_role | image / true / source |
| output_kind | processed |
| parent_policy | input_image（parent_image_id = 输入图） |
| output_cardinality | 1 |
| 参数 | 仅 `denoise`（0.05–1.0，默认 0.55；config 单链唯一来源） |

- 输入图片走 `EngineAdapter.upload_input_image()` 正式契约（与 upscale 相同，无 duck typing）；
- 输出尺寸 = 输入图尺寸（VAEEncode 决定；不接受 width/height 注入——binding README 已声明）。

### 3.3 Provider binding（workflows/providers/comfyui/img2img/v1/）

- `workflow.json`：LoadImage → VAEEncode → TextEncodeQwenImage21 → KSampler（latent=VAEEncode,
  denoise 注入）→ VAEDecode → SaveImage（前缀含 Studio 身份，支持文件级恢复核对）；
- `binding.yaml`：inputs = input_image / positive / negative / seed / denoise；
  defaults = resolution / steps / cfg / sampler / scheduler（**denoise 不在 defaults**，
  避免覆盖注入值——binding defaults 在 inputs 之后应用）；双指纹（workflow_hash + binding_hash）生效；
- 目录视为 immutable：修改必须新建 v2。

### 3.4 UI

- 工作台图片生成模式：输入图缩略图 + Prompt + **变化强度滑杆（0.05–1.0，步进 0.05）**；
  工作流区显示 ① 图生图（模块标题来自 `/modules`）② 高清放大 [可选]；
- 图库图片详情：**"以此图进行图生图"** → 打开工作台（mode=image、input_image=当前图、
  Primary Module=可用图生图模块）；有生成上下文恢复原 Prompt，外部导入 Prompt 为空；
- Stage Gate 不变：`img2img 1..N 全部完成 → 才进入 upscale`。

### 3.5 架构验收（关键结论）

新增第三种 Module 的完整改动清单 = `Img2ImgModule` + `img2img/v1` binding + 参数/UI（+ 注册表一行）。
**QueueWorker / PipelineScheduler / ImageService / Job 状态机 / 迁移框架零改动**——
第三种 Module 真正"像积木一样插进去"。

## 4. 测试与验证

| 项目 | 结果 |
| --- | --- |
| 新增 `test_phase51_contract.py` | 15 用例全过 |
| 新增 `test_phase51_img2img.py` | 7 用例全过（processed 输出 / parent / Seed / 链式 / Resume / Gate / 能力） |
| Phase 5 更新 | `basic_generate+输入图 → UNUSED_INPUT_IMAGE`（原允许行为按新契约反转）；`/modules` Gate C 断言 |
| 迁移测试更新 | 0011 进入升级路径断言（backfill / upgrade 两个测试） |
| 前端 | `npm run build`（tsc + vite）通过（60 modules） |
| 前端 store 逻辑 | `temp/experimental/frontend_store_check/`（esbuild + node 断言）**9/9 PASS** |
| 真实 ComfyUI 实验 | d055 / d100（+ d080）全部成功、无 OOM、无缺节点 |

## 5. 未执行 / 限制（如实声明）

- 未执行浏览器 GUI 人工验收（滑杆手感 / 图库入口跳转 / 模式切换动画），建议验收方按清单检查；
- 真实实验输入为**合成几何图**（结构判定专用）；真实写真照片在 0.55 下的观感未做人工评估；
- denoise 0.55 ≈ 保留结构（对合成图近恒等）；若未来需要"强变化"语义，考虑在 UI 标注推荐区间
  （本阶段不调参、不引入第二模型）；
- 本机全量 pytest 含 3 个真实 ComfyUI smoke（CI 环境自动跳过）；本机受共享 GPU 队列影响耗时较长。

## 6. 发布流程小修正（执行记录）

- 固定顺序：代码完成 → 文档最终回填 → CI GREEN → main/develop 同步 → **最后打 tag** →
  从 tag 对应 commit 生成 Source / Handoff ZIP；
- Source ZIP 排除 `.pytest_cache / __pycache__ / *.pyc`（Handoff 构建脚本本就排除）；
- 不再出现"ZIP 早于最后文档 commit"的发布链不一致（v0.6.0 tag 少一个纯文档 commit 的历史问题
  不再移动旧 tag，仅流程修正）。