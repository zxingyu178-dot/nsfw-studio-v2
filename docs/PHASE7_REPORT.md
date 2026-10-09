# PHASE7_REPORT — 可靠性收口 + Reference 能力 Gate（v0.9.0）

> 阶段：Phase 7（Task 0~9）。基线：main = develop = `1b8286b`（v0.8.0）。
> 分支：`feature/phase7-reference-slots`。最终交付：main = develop = tag `v0.9.0`。

## 0. 目标与结论

本阶段不扩展新模型，先解决"底层可靠性收口 + Reference 能力 Gate"：

- 让"继续剩余"变成真正的 **Stage-aware Resume**（不重跑已完成上游 Stage）；
- 让 Pipeline 校验 / 模块能力 / 输入契约 / 幂等语义全面转为**能力驱动与前向兼容**；
- **重新只读调查**本机真实 ComfyUI 环境，用 Gate 决策 Reference 能力；
- 清理 Git Evidence 与长期脚本位置。

**结论**：Gate **通过**——本机现役 Qwen-Image 2.1（GGUF 三件套）配合原生
`TextEncodeQwenImage21` reference latents 已具备"零安装、真实可运行"的参考图/人物一致性能力
（实测：同一人物身份保持 + 换衣 + 换场景全部生效）。已将其落地为第四个正式模块
`reference_generate` v1（QueueWorker 核心零修改）。

## 1. Task 0：真正 Stage-aware Resume

### 实现

- `job_service.resume_remaining()` 重写：对每个剩余（非 COMPLETED 的）槽位，逐 Stage 检查
  父 Job 同槽位 StageItem：
  - 已 COMPLETED 且 `output_image_id` 非空 → **直接复用**（物化为子 Job 的 COMPLETED
    StageItem，继承 input/output/seed/engine_job_id，并写 `reused_from_stage_item_id` 溯源）；
  - 整段全部复用 → Stage 直接 COMPLETED（Worker 既有"绝不重跑已完成 Stage"语义跳过）；
  - 从第一个真正未完成的 Stage 才开始执行；
- **Seed 语义**：复用槽位保留原 Seed（JobItem.seed 同步复制），只有真正重新执行的 Stage
  才由 Worker 分配新 Seed；
- 新增迁移 `0012_stage_item_reuse_trace`（`job_stage_items.reused_from_stage_item_id`）
  并暴露在 Job 详情 API。

### 四种场景（全离线 Mock，`tests/backend/test_phase7_stage_resume.py` 4 用例全绿）

| 场景 | 断言要点 |
| --- | --- |
| basic → upscale，Stage2 全失败 | 子 Job Stage0 整段复用（COMPLETED + 溯源 + Seed 原样）；只提交 upscale×2 |
| img2img → upscale，Stage2 取消 | 绝不重跑 img2img（无新提交、无输入图二次上传）；upscale 输入 = 复用的 processed 输出 |
| Stage2 部分失败 | 已 COMPLETED 槽位不再续跑；剩余槽位复用其 Stage0 输出后只重跑 upscale |
| Stage0 取消 | 已完成槽位复用原 Seed；取消槽位重执行并分配新 Seed（断言新旧不同） |

## 2. Task 1：Git Evidence 清理

- 移出 Git 跟踪（磁盘保留，完整图片只进 Handoff ZIP）：`docs/evidence/phase51-img2img/outputs/*.png`、
  `docs/evidence/phase6-img2img/{inputs/real_photo*, outputs/*.png, screenshots/*.png}`；
- `.gitignore` 新增：`docs/evidence/**/*.{png,jpg,jpeg,webp,gif}`、`temp/`；
- 长期脚本迁移：`scripts/acceptance/`（check_ci、send_handoff_mail 参数化、inspect_jobs、
  inspect_recipes）与 `tests/manual/`（smoke_phase51、smoke_phase6_photo、acceptance_phase6、
  acceptance_phase6_browser、probe_engine_upscale）；迁移后统一修正 PROJECT_ROOT
  （`parents[2]`，并实测跑通 Phase 7 smoke）；
- 阶段邮件工具升级为 `scripts/acceptance/send_handoff_mail.py`（--phase/--source/--handoff/
  --subject(-file)/--body-file + IMAP SHA-256 复核），本阶段交付即用它发送。

## 3. Task 2：process Job 校验能力驱动

- `ModuleCapabilities` 新增 `allowed_job_kinds`（默认 `("generate",)`）与
  `can_start_from_image`（默认 false）；
- PipelineValidator 删除"process 必须且只能是 upscale"硬编码：改为
  "模块必须声明允许当前 job_kind + 处理型 Job 首模块必须 can_start_from_image"；
- 声明：`upscale = generate + process, can_start_from_image=true`；
  `img2img/reference_generate = generate`（可从图片起步）；`basic_generate = generate`；
- 测试用"Face Repair 形状"的假模块验证：声明能力后 process Pipeline 立即合法、Validator 零改动。

## 4. Task 3：ComfyUI 环境重盘（只读）

产出 **[REFERENCE_CAPABILITY_INVENTORY.md](REFERENCE_CAPABILITY_INVENTORY.md)**，要点：

- ComfyUI 0.37.0 / RTX 3060 Laptop 6GB / `--lowvram`；1169 节点；自定义节点 7 个（GGUF /
  Impact / Subpack / OpenPose / SeedVR2 / cg-image-picker / Manager）；
- 可加载模型（object_info 权威 + 磁盘核查）：Qwen-Image 2.1 三件套（GGUF 4.15GB +
  text encoder 6.31GB + VAE 675MB，C:/ComfyUI_models）、SeedVR2、4x-UltraSharp、
  ultralytics 检测器、SD 世代 LoRA（无配套底模）；
- **缺失**：Qwen-Image-Edit 权重、IPAdapter 节点+模型+clip_vision、PuLID / InstantID、
  PhotoMaker 模型、ControlNet 模型、SD 底模——全部需要新增下载/安装；
- 用户历史 SD 工作流（ControlNet + FaceDetailer 等）引用的底模/SAM/ControlNet 均已不在磁盘，
  不可运行。

## 5. Task 4：Reference Gate（通过）

- Gate 实测（直接 ComfyUI API，零下载）：参考图（真实照片）→ `TextEncodeQwenImage21`
  （reference latents）→ KSampler（denoise 1.0）→ 输出与参考图对比：
  **同一人物面部/发型/构图保持；米色针织衫 → 红色连衣裙；白天咖啡馆 → 夜晚城市街景**；
- 耗时事实：6GB + 16GB RAM 下冷加载 ~35 分钟 + 采样，属"低频高质量能力"；
- 结论：选定该链作为唯一 Reference 方案（见下方 Task 6），未选择需下载的方案。

## 6. Task 5：通用图片输入 Slot 契约

- `ModuleCapabilities.input_slots`（role / required / max_count / description）；
- Workbench 快照 `input_images` 支持 source / reference / face_reference（总上限 4，
  schema 不再硬编码 max=1）；Job 创建期由 PipelineValidator 按模块声明校验
  （`UNUSED_INPUT_IMAGE` / `INPUT_IMAGE_REQUIRED` / `INPUT_SLOT_LIMIT_EXCEEDED`）；
- 链式主输入 = 模块声明顺序中第一个有图的槽位（img2img/upscale 行为不变）；
- Recipe 输入图快照保留多角色；Face Asset 参考图数据直接可用（同一条图库，不另造图库）。

## 7. Task 6：Reference Module（Gate 通过后落地）

- 新模块 `reference_generate` v1（`backend/app/workflows/reference_generate.py`）：
  - 能力：slot=reference（必填×1）、uses_seed、kind=original、parent=参考图、
    size_mode=input、is_generative、allowed_job_kinds=generate、can_start_from_image；
  - configurable 参数：`resolution`（512~2048，默认 1024；参考图重采样基准）；
- provider binding `workflows/providers/comfyui/reference_generate/v1/`
  （workflow.json + binding.yaml + README，双指纹固化；`images.image_1` Autogrow 静态链接；
  KSampler latent = TextEncodeQwenImage21 的参考尺寸 latent，denoise=1.0）；
- 沿用 WorkflowModule → EngineAdapter → ComfyUI binding 架构，**QueueWorker 核心零修改**；
- 离线 Mock 回归 6 用例全绿；真实产品路径 smoke 见 §9。

## 8. Task 7 + Task 8：幂等指纹与三个前向兼容点

- **Task 7**：`jobs.client_request_fingerprint`（迁移 0013）——相同 key + 相同 payload 重放原
  Job；不同 payload → 409 `IDEMPOTENCY_KEY_CONFLICT`；queue_mode 不进入指纹；
  历史 NULL 指纹 Job 保持兼容；
- **Task 8-①**：`/modules` capabilities 按**实际选中的 module_version** 获取
  （测试：配置选中 v2 时返回 v2 的能力声明与标题）；
- **Task 8-②**：Image → Workbench"最近生成上下文"改为按产出 Stage 的模块语义
  （`is_generative`）判定；测试：清空 img2img 输出图的 Seed 后仍能恢复 Img2Img 上下文；
- **Task 8-③**：非 comfyui/mock 引擎输出 `Image.source = "engine"`（不再错标 import；
  provenance 保留 actual_provider）。

## 9. Task 9：验收

### 离线回归（CI 同口径）

- 快速套件 **254 passed**（227 基线 + 27 新增，Phase 4~7 全绿）；
- 前端 `npm run build` 通过 + `npm run test:store` 11 断言全绿；
- 真实 DataRoot 迁移 0012/0013 在 smoke 中实测应用成功（0.8.0 → 0.9.0）。

### 真实 smoke（产品路径，1 张真实参考图）

`tests/manual/smoke_phase7_reference.py`：参考图导入真实 DataRoot → `reference_generate`
（resolution 768，→ 可选 upscale）→ 真实 ComfyUIAdapter + 生产同款 Worker。

**结果：COMPLETED，13/13 检查全部通过**（elapsed 1151.7s / 热缓存）：

```text
job_completed / stage0_module_reference_generate / stage0_completed /
stage0_config_resolution / reference_frozen / reference_output_exists /
reference_output_kind_original / reference_parent_is_input / stage_item_seed_recorded /
reference_output_seed_matches / final_output_exists / upscale_stage_completed /
upscale_parent_is_reference_output
```

- Job：`job_25c14f4d-…`；身份 `reference_generate@v1`（wf=b9413c99c1f4ddeb /
  bh=1022da22e48721e6）+ `upscale@v1`（wf=8232a833dc049803 / bh=6a7a21944d428ef6）；
- 产物：`img_2c732d9b…`（kind=original，672×896，parent=参考图，seed=504415952——
  输出尺寸跟随重采样后的参考图）→ `img_3f81fdbf…`（kind=upscaled，parent=reference 输出）；
- 人工比对（参考图 → 产品路径输出）：**同一人物面部/发型保持；红色连衣裙；夜晚霓虹街景**；
- 证据：`docs/evidence/phase7-reference/report_ref_upscale.json`（输出图本体在真实 DataRoot，
  按 Task 1 规范不入库，完整图片随 Handoff ZIP 交付）。

## 10. 已知边界与未验证项（如实声明）

- 6GB 显存 + 16GB RAM 下参考链运行**很慢**（冷启动约 35 分钟加载 + 采样，单次 > 1 小时；
  热缓存产品路径 smoke 约 19 分钟），适合低频高质量能力；批量场景不适用；
- Reference 模块 v1 只支持 **1 张** reference（多参考图受当前 Worker 单输入链限制，
  后续版本再扩 max_count）；
- 前端本阶段仅类型镜像扩展（InputImageRole / input_slots 等），**Reference 的 UI 入口
  未在本阶段实现**（走 API / 手工脚本；Gate 产品化 UI 建议列入下一阶段）；
- 未做浏览器人工验收（本阶段任务书未要求；UI 无行为变化）；
- ComfyUI 生命周期未改动；未下载模型、未安装节点、未升级 ComfyUI。