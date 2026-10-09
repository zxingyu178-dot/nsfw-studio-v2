# PHASE6_REPORT — Pipeline 可靠性收口（v0.8.0）

> 日期：2026-10-09 ｜ 版本：0.8.0 ｜ 基线：v0.7.0 (4cc8012) ｜ 分支：feature/phase6-pipeline-reliability
> 目标：不扩模型，解决"能生成之后如何可靠继续编辑、可靠复现、可靠扩第四个 Module"——
> Image→Workbench 生成上下文、前端身份保留、Recipe 固定 Seed、Pipeline 顺序/重复模块、
> Module Availability、Img2Img execute 契约、generation_mode、参数元数据驱动、size_mode、
> 真实照片验收、浏览器人工验收、交接包清理。
>
> **结论：Task1-9 + Task12 完成；Task10/11 结果见 §2/§3。**

## 0. 结论先行

1. **Task1-9 全部落地**（含 4 个真实缺陷修复）：
   - Image → Workbench 取"距离最近的 generate 上下文"（import→img2img→upscale 恢复 Img2Img，
     不再回到导入图 / 树根；Seed 用该上下文图片的真实 Seed）；
   - 前端 `normalizeModules()` 不再重建裸 `{module_id:'upscale'}`——历史/配方/图片恢复的
     7 字段身份（含双 hash）与 config 原样保留；
   - Recipe 固定 Seed 归一化（"使用此图 Seed"的工作台保存配方不再 400）；
   - 移除 `MODULE_ORDER` 执行重排（严格保持 Pipeline 顺序）+ 重复模块拒绝
     （`PIPELINE_DUPLICATE_MODULE`）+ 未注册 module_version 创建期拒绝；
   - `module_availability()` 版本域修正（不再拿 module_version 当 binding_version 兜底）；
   - `Img2ImgModule.execute()` 补齐 Prompt/Negative 契约（独立执行不再空 Prompt）；
   - `generation_mode`（text|image）进入 WorkbenchSnapshot / Recipe / Job / History / Image 恢复；
   - `/modules` 返回 ParameterSpec（含 min/max/step/configurable/title）+ size_mode，
     前端按 schema 渲染控件（denoise 滑杆不再按 module_id 硬编码）；
   - size_mode=input 的模块 UI/详情不显示"假宽高"，History 显示"跟随输入图 W×H"。
2. **测试与构建**：后端 227 passed（208 基线 + 19 新增，含 11 个新回归文件覆盖全部要求场景）；
   前端 store 回归 11 passed（`tests/frontend/workbench_store.phase6.mjs`，已接入 CI `npm run test:store`）；
   `npm run build`（tsc + vite）通过。
3. **Task12 交接包清理**：Qwen 实验证据从 `temp/experimental/qwen_img2img/` 迁至
   `docs/evidence/phase51-img2img/`（引用同步更新，binding.yaml 因 fingerprint 不可变未动）；
   Source 包由 git tracked 维护（`.pytest_cache / __pycache__ / *.pyc` 确认未跟踪，`git archive` 天然排除）。

## 1. Task1-9 实现明细

### Task1 Image → Workbench 最近的生成上下文

- `image_service.resolve_generation_context()`：从当前图沿 parent_image_id 向上，找**距离最近、
  由 generate Job 产出、且真实使用 Seed** 的图及其 Job（同 Job 内嵌 upscale Stage 的产出图
  Seed 为 NULL → 继续向上到真实生成图）；
- `GET /images/{id}/workbench` 的 `seed` 改为该上下文图片的真实 Seed（不再无条件树根 Seed）；
- 回归（`test_phase6_pipeline_reliability.py`）：
  `import→img2img`（200 / 恢复 img2img）、`import→img2img→upscale`（仍 img2img，Seed 取 img2img 真实值）、
  `basic→upscale`（basic）、`basic→img2img→upscale`（img2img，非树根 Seed）、纯导入（404）。

### Task2 前端身份保留（normalizeModules）

- `[primary, ...rest]` 结构：rest（高清等非 Primary 模块）**保持原顺序与完整身份**；
  仅 mode 与 primary 不一致时替换 primary（新 primary 为裸引用，由后端解析身份）；
- `setPrimaryModule()` 新增（Task8 选择器入口）；`setUpscaleEnabled(false→true)` 仍是唯一
  "用户手动开启高清 → 裸 {module_id:'upscale'}"路径；
- 回归（前端 harness）：pinned upscale / img2img 经 hydrate → setModuleCatalog → snapshot，
  双 hash 与 config 完全不丢；目录未就绪时绝不静默降级（Gate 关闭）。

### Task3 Recipe 不保存固定 Seed

- `_validate_generation_settings()`：接受 fixed，落库时归一化 `seed_mode=random`（不强制改工作台）；
  仍拒绝非法值（`SEED_MODE_INVALID`）；
- 回归：API 级 fixed → 201 → reopen random；service 级 fixed 归一化 + 非法值拒绝。

### Task4 Pipeline 顺序 + 重复模块

- `resolve_workflow_modules()`：删除 `MODULE_ORDER`；严格按请求顺序产出身份
  （回归：`[upscale, basic_generate]` 输入 → 输出顺序不变）；
- 重复 module_id → `PIPELINE_DUPLICATE_MODULE`（resolver + PipelineValidator + Recipe 保存三处拦截）；
- **未注册 module_version 创建期拒绝**（PipelineValidator 不再回退 id 级能力）：
  回归覆盖 pinned `basic_generate@v99` → 400；`test_phase22_consistency` 的"升级到 v2 后新 Job"
  断言同步改为"创建期 400"。

### Task5 Module Availability 收紧

- `module_availability()`：`module_version` 只从 module 域解析、`binding_version` 只从 binding 域解析
  （默认模块回落 engine 级配置，其余模块 v1）；新 Job 将使用的 module 版本必须真实注册，
  否则 `available=false / module_version_not_registered`；
- `/modules` 返回 `registered / available / module_version / provider / binding_version / unavailable_reason`；
  只检查磁盘 binding，不探测引擎在线（ComfyUI 临时离线 ≠ 模块不存在）；
- 回归：`module_version=v2 未注册 → 不可用 + binding_version 仍为 v1`；mock 下全部 available。

### Task6 Img2ImgModule.execute 契约

- `execute()` 把 `positive_prompt / negative_prompt` 完整放入 JobRequestContext；
- 回归：直接 `execute(payload, MockEngineAdapter)` → 断言 `EngineJobRequest.parameters`
  的 positive/negative/seed/denoise/input_image 与 payload 一致。

### Task7 generation_mode（text | image）

- `WorkbenchSnapshotModel.generation_mode`（向后兼容 None=推断）+ `GenerationSettingsModel.generation_mode`；
- Job 快照与 generation_settings 双写；Recipe 版本经 generation_settings 往返；
  前端：snapshotFromState 显式写、hydrate 显式优先（旧快照回落 input_images 推断）、
  Recipe/Prompt/Asset/图库"用作输入图 / 以此图进行图生图"入口显式设置模式；
- 回归：API 往返（Job/History/Image/Recipe）、"image 模式即使暂无图片也保持 image"（前端 harness）。

### Task8 参数元数据驱动

- `ParameterSpec` 扩展：`title / min / max / step / configurable`；img2img.denoise →
  `min=0.05 / max=1 / step=0.05 / configurable=true / title=变化强度`；
- `/modules` 序列化 parameters；前端 `ModuleParameterDTO` + `ModuleParameterField`
  按 float/int/bool/enum 渲染（range/number/checkbox/select），值写 `WorkflowModuleRef.config`；
- Primary Module 轻量选择器：候选来自 catalog（available=true；文生图=不消费输入图，
  图片生成=可用图片条件模块），>1 时渲染 select；
- 回归：`/modules` schema 断言；denoise 默认来自 schema（config 为空 → 执行按 0.55）、
  显式配置精确物化到 `JobStage.config_json`；前端 harness 切换 primary 后非 primary 身份保留。

### Task9 size_mode 与有效尺寸

- `ModuleCapabilities.size_mode`：basic_generate=explicit、img2img=input、upscale=input；
- SettingsPane：size_mode=input 时隐藏宽高输入，显示"跟随输入图（无需设置宽高）"；
- History 任务详情：explicit 显示 generation_settings 宽高；input 显示
  "跟随输入图 W×H"（读取 Stage0 输入图真实尺寸，而不是 Workbench 遗留的 1024×1024）；
- 回归：`/modules` size_mode 断言 + 前端 harness。

### Task12 交接包清理

- `git mv temp/experimental/qwen_img2img docs/evidence/phase51-img2img`（历史保留）；
  引用更新：CHANGELOG / DEV_LOG / TASKS / TEST_REPORT / PHASE51_REPORT / img2img.py /
  binding README / spike.py / refetch.py / smoke_phase51.py；
  **binding.yaml 未改**（fingerprint 不可变，改注释会破坏历史 Job 的 binding_hash 校验）；
- 删除被新 harness 取代的临时脚本目录 `temp/experimental/frontend_store_check/`
  （其覆盖场景已并入 `tests/frontend/workbench_store.phase6.mjs`）；
- Source 包：仓库无 tracked 缓存文件；发布用 `git archive <tag>`（天然只含 tracked，排除缓存）。

## 2. Task10 真实照片 Img2Img 验收

> 输入：`docs/evidence/phase6-img2img/inputs/real_photo_768x1024.png`
> （为避免使用任何私人照片，输入为一张文生图产生的写实人像照片 1680×2240，缩放至 768×1024 测试尺寸）
> 路径：真实后端服务（JobService + PipelineValidator + QueueWorker + 真实 ComfyUIAdapter）→ 真实 DataRoot
> 全部 4 次运行 **11/11 检查通过**（COMPLETED / kind=processed / parent=输入图 / StageItem.seed 真实 /
> 输出尺寸=输入尺寸 / denoise 进入 config_json）

| 运行 | denoise | Prompt | 耗时 | 人物/主体保留 | Prompt 效果（人眼评估） |
| --- | --- | --- | --- | --- | --- |
| d055 | 0.55 | 与源图同语义（咖啡馆/窗边/暖光） | 773s（含 ~10min 冷加载） | 完整保留 | 近乎不可见（细节重绘级：去水印、发丝/皮肤轻微重渲染） |
| d055_winter | 0.55 | **不同**（冬日雪夜/蓝调/落雪） | 578s | 完整保留 | **几乎无变化**（仅轻微冷色与玻璃纹理） |
| d070_winter | 0.7 | 同 d055_winter | 162s | 完整保留 | 轻度变化（少量雪意/冷凝，整体仍接近原图） |
| d080_winter | 0.8 | 同 d055_winter | 172s | **保留良好**（姿态/五官/发型/毛衣一致） | **明显生效**：雪街、秃树、落雪、蓝调窗外 + 室内暖光 |

产出（`docs/evidence/phase6-img2img/outputs/`）：`d055_photo_output.png` / `d055_winter_output.png` /
`d080_winter_output.png`；报告 `report_d055.json` / `report_d055_winter.json` / `report_d070_winter.json` /
`report_d080_winter.json`（含 job/stage/identity/seed/尺寸/耗时/11 项检查）。

### 默认值结论（依据真实照片实测，而非几何图相关系数）

1. **0.55 在真实照片上"几乎没变化"成立**：即使给出完全不同的场景 Prompt（冬日雪夜），
   0.55 输出仍与原图近乎一致 → 它是"精修档"，不适合作为面向改变画面的默认值。
2. **0.8 同时满足"人物保留 + Prompt 生效"**：真实人像在 0.8 下主体完好，雪景/蓝调等场景语义明确落地。
3. 因此把 `Img2ImgModule` 默认 `denoise` 由 **0.55 → 0.8**（config 为空时生效；
   滑杆仍可 0.05–1.0 自由调整）；参数说明更新为
   "0.55 以下≈精修（近乎不变）；0.8（默认）可做场景级变化"。
   同步更新：前端 schema 默认值（自动）、`test_phase6` / 前端 harness 断言、binding README 说明
   （**未改 binding.yaml / workflow.json**——指纹不可变，历史 Job 的 hash 校验不受影响）。

## 3. Task11 浏览器人工验收

> 工具：Playwright + 系统 Edge（复用 art-museum 已装依赖，零下载；headless + 全页截图）
> 环境：真实后端 8000（真实 DataRoot）+ 真实 ComfyUI + 前端 dev 5173
> 结果：**ALL PASS（10/10 断言）**，证据 `docs/evidence/phase6-img2img/acceptance_browser.json` +
> `screenshots/01..15`（`99_error.png` 为首次运行失败残留，已删除）

| 步骤 | 断言 | 结果 |
| --- | --- | --- |
| ① 文生图初始 | 文生图 tab 选中 + 显式宽高可见 | ✅ |
| ① 文生图提交/完成 | Job 创建 + COMPLETED（真实 ComfyUI） | ✅ |
| ② 图库导入外部照片 | 导入成功 | ✅（screenshot 04） |
| ② 图片生成模式 | 图片 tab 选中 + 输入图缩略图 + **"跟随输入图（无需设置宽高）"** + denoise 滑杆=0.8 + 无假宽高 | ✅ |
| ② Img2Img(+高清) | 提交并 COMPLETED（img2img→upscale 两 Stage 全绿） | ✅ |
| ③ Gallery | processed + HD 徽标 | ✅ |
| ④ History → 工作台 | 图片模式 + denoise=0.8 + Prompt 恢复（cafe） | ✅ |
| ④ 高清图 → 工作台（Task1） | **恢复 Img2Img（非导入图）+ denoise + 输入图缩略图** | ✅ |
| ⑤ Recipe 保存/重开 | 配方落库：generation_mode=image、seed_mode=random、img2img+upscale 双指纹完整、输入图绑定 | ✅（DB 核验） |
| ⑤ 切回文生图 | 文生图 tab + 宽高回归 | ✅ |

> 说明：浏览器脚本中"图片生成模式"断言改用 `getByText('跟随输入图（无需设置宽高）')`
> 精确匹配（避免 `跟随输入图` 前缀歧义）；"从高清图恢复"改为按 image_id 定位卡片
> （修复抽屉 backdrop 遮挡点击）。这些是**测试脚本**迭代，未改任何产品代码。

## 4. 环境记录（如实声明）

- 2026-10-09 09:49-10:17：托管计划任务启动 ComfyUI 三次均 420s 超时（`FATAL startup timeout`）；
  决定性诊断：`import torch` 停滞在内核等待 → 机器环境层面阻塞；
- 用户处理环境后 10:55 引擎就绪；首次照片任务（11:25）在模型加载阶段停滞，
  Studio 侧有限重试 3 次后 `ENGINE_NETWORK` 失败（retry_count=3，事件时间线见
  `report_d055.json` 与 job_events）；
- 13:10 我按授权重启服务（Signal-Stop 事件 → 任务 Ready/Last Result=0 → Start-ScheduledTask，
  3.2 分钟就绪）；
- 13:14 轻量探测（64×64 高清链，仅 64MB 小模型）22 秒通过 → 引擎本身可用；
- 13:15 重跑照片 img2img：加载阶段空闲内存一度降至 ~240MB（提交 22GB/40GB，大量换页），
  模型加载+采样共 12:44（Model load 约 10 分钟 + 采样 2:45）→ **任务 COMPLETED，11/11 检查通过**。
  结论：16GB 物理内存在常驻应用并存时对"T5 6GB + GGUF 5.4GB"链路过紧，
  启动/加载阶段表现为分钟级卡顿（Studio 的瞬时重试窗口正好覆盖）。