# PHASE5_REPORT — Image Input Foundation + Reference / Img2Img Capability Gate（v0.6.0）

> 日期：2026-10-08 ｜ 版本：0.6.0 ｜ 基线：v0.5.0 (40ac5e8) ｜ 分支：feature/phase5-image-input
> 目标：把"图片作为输入"从后台能力升级为产品能力（导入 → Gallery → 工作台输入 → Recipe → Job 冻结）；
> 真实图片条件工作流按环境能力 Gate 决定是否接入。
>
> **Image conditioning backend: pending environment decision**（Gate B，等待用户选择模型方案）。

## 0. 能力 Gate 结论（先行）

**Gate B —— 需要新增模型/节点，已停止**（详见 docs/IMAGE_CONDITIONING_INVENTORY.md）：

| 能力 | 是否可用 | 缺什么 |
| --- | --- | --- |
| Img2Img（SDXL 现成工作流） | ❌ | `sdxl-图生图.json` 依赖的 RealVisXL_V5.0 + add-detail-xl 不在磁盘 |
| Reference（IPAdapter 类） | ❌ | IPAdapter 节点不存在 + clip_vision 空 + 无模型 |
| Face Reference（PuLID/InstantID/PhotoMaker） | ❌ | PuLID/InstantID 节点不存在；PhotoMaker 节点在但模型空 |
| ControlNet | ❌ | controlnet 目录空（节点在） |
| Qwen-Edit 原生编辑链 | ❌ | 仅 Qwen-Image 2.1 base（无 Edit 模型） |

- 调查为**只读**：未下载模型 / 安装节点 / 升级 ComfyUI / 更新 Manager / 移动模型 / 修改用户工作流。
- **本阶段零真实生图**（合同 §29 Gate B）。
- 候选方案（方案 0 零下载 Qwen-2.1 latent Img2Img 最优先 / 方案 1 恢复 SDXL 链 /
  方案 2 Qwen-Edit / 方案 3 IPAdapter）含模型体积、显存、节点与影响评估，等待用户决定后再进 Phase 5.1。

## 1. 交付内容（全部完成，Gate B 不阻塞）

### 1.1 外部图片导入（§三-§六、§二十三）

- `POST /api/v1/images/import`：PNG / JPG / JPEG / WEBP，单张 / 多张；
  流程 = 选择本地文件 → 校验（扩展名 + MIME + magic bytes + 尺寸 + ≤10MB）→ Studio temp →
  原子导入（复用 `import_outputs_transaction` 单张批次）→ `DataRoot/images/originals/` →
  Image 数据库（`source=import / kind=original / job_id=null`）→ Gallery。
- **绝不引用用户原始路径**；`images.sha256` + `images.imported_filename`（迁移 0010）。
- **sha256 去重**：重复文件不创建第二份，返回已存在 image_id（实测：不同文件名、同内容 → duplicate）。
- **批量部分失败继续**（与生成输出"整批原子"语义明确区分：这是文件管理操作）：
  成功 / 已存在 / 失败三类明细；扩展名伪造（.gif）、magic bytes 不符、超限均为单张失败。
- WEBP 尺寸解析（VP8 / VP8L / VP8X 三种容器，无第三方依赖）。
- 图库 UI："导入"多选 + 进度 `n / N` + 结果摘要"成功 N · 已存在 N · 失败 N"。

### 1.2 工作台输入图片（§七、§八、§二十、§二十一、§二十二）

- 生成页顶部模式切换 [文生图] / [图片生成]（无一级导航变化）；图片生成模式显示独立"输入图片"区
  （[从图库选择] / [上传新图片] → 先正式导入 Gallery 再引用，统一 `image_id`）。
- `WorkbenchSnapshot.input_images`（max=1，role=source；后端 Pydantic `max_length=1` 与
  JobService 双重校验；>1 张 → 422）。
- Gallery Picker：筛选（最近 / 未审核 / 保留 / 收藏）+ 搜索导入文件名（新增
  `GET /api/v1/images?search=`）；卡片 = 缩略图 / 尺寸 / 收藏。
- Gallery 详情"用作输入图片"→ 打开工作台并设置 input_image（保留当前工作台其它配置）。
- Gate 判定：`GET /api/v1/modules` 返回能力列表，前端要求存在
  `input_required=true 且 output_kind=processed` 的模块才启用图片生成提交；
  Gate B 下明确显示"图片生成：尚未配置可用工作流"并禁用提交（可先选择输入图片并保存配方）。

### 1.3 Recipe 输入图快照（§九）

- `recipe_versions.input_images_json`：`[{role, image_id, sha256}]`（保存时解析 file hash，
  优先导入记录值，否则现算）；参与"内容无变化不建新版本"signature 比较；
  恢复旧版本（restore）= 原样复制输入图关系。
- 图片不存在 → 响应 `missing=true`（前端显示"输入图片已丢失"，**绝不静默清空**）；
  保存时图片必须存在（404 IMAGE_NOT_FOUND）。

### 1.4 Job 创建冻结输入图片（§十）

- `JobService.create_job` 从 WorkbenchSnapshot 提取 input_images → 校验存在 →
  写入 Stage0 **全部槽位** 的 `JobStageItem.input_image_id`（复用既有 `_materialize_stages`，
  未改 Worker / Pipeline 核心）。
- 处理型 Job（process）：快照输入图（若携带）必须与 `input_image_ids` 一致，否则拒绝
  （`PIPELINE_INVALID`），禁止两个事实源打架。
- 实测：count=2 的 Job 两个 StageItem 均冻结同一输入图；每个槽位各自产出（输入冻结不改变输出数量）；
  Job 创建后修改工作台/图库不影响其身份。

### 1.5 Face Asset Reference Image（§十二、§十三）

- 正式关系表 `asset_reference_images`（id / asset_version_id / image_id / role / sort_order / created_at，
  UNIQUE(asset_version_id, role, sort_order) + 2 索引）；**不再把复杂关系长期塞 JSON**。
- Face Asset 绑定 1 张图库参考图：创建 / 新增版本表单支持 `reference_image_id`；
  绑定 / 更换 = 新版本（旧版本保留自己的参考图）；不传 → 沿用当前版本参考图；
  非 face 类型 → 400 `ASSET_REFERENCE_TYPE_INVALID`；图片缺失 → 404。
- 前端：材质详情 Drawer"参考图（Face Reference）"区（缩略图 / 绑定 / 更换，Picker 复用）。

### 1.6 其他合同项

- **ImageReferenceService（§十一）**：`GET /api/v1/images/{id}/references` →
  Recipe / StageItem / Asset 参考图 / Asset 溯源（source_image_id）/ 派生图 的计数与明细 +
  `active_job_ids`；实测 5 类来源全计数、无引用图片 total=0。
- **ModuleCapabilities（§十四）**：新增 `input_required / input_role`；
  basic_generate=false / upscale=true(source)；`GET /api/v1/modules` 暴露。
- **快捷键（§二十四）**：← / → 上一张 / 下一张，K 保留，R 淘汰，F 收藏（Drawer 打开时作用于当前图）；
  Ctrl+Z / 页面"撤销"按钮撤销最近一次审核 / 收藏（栈深 20；按钮与快捷键同源）。
- **迁移 0010_image_inputs**（不修改 0001-0009）：`images.sha256/imported_filename`（+索引）、
  `recipe_versions.input_images_json`、`asset_reference_images`；升级幂等（重复启动 0 差异）。

## 2. 架构验收（§二十五）

**未修改**：QueueWorker / PipelineScheduler / ImageService 核心 / Job 状态机 / 迁移框架本身。
新增仅：WorkflowModule 能力字段（input_required/input_role）+ 通用图片输入层
（导入 / 快照 / 引用检查 / Modules API）+ UI。已验证：`basic_generate` Stage 携带冻结输入图时
Worker 正常执行（模块按能力忽略输入），无任何核心改动。

## 3. 测试证据

### 快速套件（CI 同口径）

```text
.venv\Scripts\python -m pytest tests/backend --ignore=tests/backend/test_comfyui_integration.py
结果：186 passed（v0.5.0 的 168 例 + Phase 5 新增 18 例）
```

新增 `tests/backend/test_phase5_image_input.py`（18 例）：

- 导入：单张 PNG 全链路（source/kind/job_id/file_path/DB sha256/文件存在/图库过滤/Provenance 外部导入/
  workbench 404 IMAGE_NO_GENERATION_CONTEXT）；WEBP 尺寸；超限拒绝；批量部分失败；
- 去重：API 级 + 服务级（不同文件名同内容）；
- Job 冻结：count=2 全槽位冻结 + 各槽位独立输出（Mock 引擎全流程）/ 缺失 404 / 多图 422 /
  处理型快照不一致 PIPELINE_INVALID；
- Recipe：快照 hash / 无变化不建版 / restore 复制 / 删除图片后 missing=true / 未知图 404；
- Face Asset：绑定 / 更换新版本 / 不传沿用 / 非 face 拒绝 / 缺失 404 / 版本历史各自参考图 / 关系行落库；
- 引用保护：5 类来源（Recipe/StageItem/Asset 参考/Asset 溯源/派生图）计数 + 未引用图片 0；
- Modules：input_required/input_role/capabilities 字段 + Gate B 判定断言；
- 迁移 0010：列 / 表 / 索引存在 + 幂等。

### 前端

- `npm run build`（tsc --noEmit + vite build）通过：60 modules，JS 259.7 KB（gzip 78.3 KB）。

## 4. 未执行 / 部分验证（如实声明）

- **真实图片条件生成：未执行**（Gate B，合同 §29 要求零真实生图）。
- **真实浏览器 GUI 验收：未执行**（本阶段交付为代码 + 快速套件 + 构建；建议用户/验收方按
  验收清单在真实浏览器与模拟数据上检查 UI 交互与快捷键）。
- 交付链：develop run 37747872243 success → main run 37749969875 success → tag v0.6.0；
  交接 ZIP（NSFW_Studio_Phase5_Handoff.zip）+ 源码 ZIP（NSFW_Studio_Phase5_Source.zip）
  已发送 3056668080@qq.com 并经 IMAP 复核（附件齐全）。

## 5. 状态

**READY_FOR_REVIEW** —— 基础图片输入 + 导入 + Recipe/Job 冻结 + Face 参考图 + 引用保护 + UI 完成；
真实 Img2Img/Reference 接入等待用户在 IMAGE_CONDITIONING_INVENTORY.md §6 选择方案。