# API_PLAN — API 现状与规划

> 更新：2026-10-09（Phase 6，v0.8.0）。错误格式统一为 `{"error": {"code", "message"}}`。

## 1. 约定

- 前缀：`/api/v1`（破坏性变更升级版本号，不做字段级兼容层）。
- 层次：api 只做 HTTP 编排（参数校验用 Pydantic schema），业务逻辑在 services。
- 交互格式：JSON；业务时间统一 UTC ISO 8601（`Z` 结尾）。
- 列表统一参数：`search / favorite / archived / limit / offset`（Asset 额外 `type`），响应含 `total`。
- 交互文档：FastAPI 自动 Swagger（`/docs`）。

## 2. 现有接口

### 健康与服务信息

- `GET /api/v1/health` → `{"status":"ok","version":"0.8.0"}`
- `GET /` → 服务基本信息

### Prompt（`app/api/v1/prompts.py`）

```
GET    /api/v1/prompts                       列表（search/favorite/archived/limit/offset）
POST   /api/v1/prompts                       创建（+v1；结构化模式正向由后端合成）
GET    /api/v1/prompts/{id}                  详情（含 current_version）
PATCH  /api/v1/prompts/{id}                  元数据（名称/收藏，不建版本）
POST   /api/v1/prompts/{id}/versions         新内容版本（内容不变则不建）
GET    /api/v1/prompts/{id}/versions         版本历史
POST   /api/v1/prompts/{id}/versions/{vid}/restore   恢复旧版本（复制为新最新版）
POST   /api/v1/prompts/{id}/archive | /restore       软删除/恢复
POST   /api/v1/prompts/compose               结构化合成预览（与保存同源）
```

### Asset（`app/api/v1/assets.py`）

```
GET    /api/v1/assets                        列表（额外支持 type 过滤）
POST   /api/v1/assets                        创建（multipart，支持预览图上传；v1）
GET    /api/v1/assets/{id}                   详情
PATCH  /api/v1/assets/{id}                   元数据
POST   /api/v1/assets/{id}/versions          新版本（multipart，可选新预览图）
GET    /api/v1/assets/{id}/versions          版本历史
GET    /api/v1/assets/{id}/preview[?version=]  预览图文件流
GET    /api/v1/assets/{id}/workbench         素材 → 工作台快照（prompt 填入对应 slot）
POST   /api/v1/assets/{id}/archive | /restore
```

创建素材额外支持可选表单字段 `source_image_id`（图库 → 素材溯源，§四十八）与
`reference_image_id`（Phase 5 §十二：Face Asset 参考图，仅 type=face，来源=图库 image_id；
绑定/更换 = 新版本；响应 `current_version.reference_images` 来自 asset_reference_images 关系表）。
**Phase 5.1 Task8**：`POST /assets/{id}/versions` 新增 `reference_action: inherit | set | clear`
（缺省兼容旧语义：传图 = set，不传 = inherit；clear = 新版本 reference=none，旧版本保留）；
`set` 缺 reference_image_id → 400 `ASSET_REFERENCE_INVALID`；非法 action → 400
`ASSET_REFERENCE_ACTION_INVALID`。

### Recipe（`app/api/v1/recipes.py`）

```
GET    /api/v1/recipes                       列表
POST   /api/v1/recipes                       保存配方（body: {name, favorite, snapshot: WorkbenchSnapshot}）
GET    /api/v1/recipes/{id}                  详情（含 current_version + asset_snapshots）
PATCH  /api/v1/recipes/{id}                  元数据
POST   /api/v1/recipes/{id}/versions         新版本（快照变化才创建；input_images 参与比较）
GET    /api/v1/recipes/{id}/versions         版本历史
POST   /api/v1/recipes/{id}/versions/{vid}/restore   恢复（快照原样复制，含输入图关系）
POST   /api/v1/recipes/{id}/archive | /restore
```

Phase 5 §九：snapshot.input_images（[{role:"source", image_id}]，max=1）→ RecipeVersion
`input_images_json`（[{role, image_id, sha256}]，file hash 由后端解析）；响应
`current_version.input_images[].missing` 标记图片已丢失（前端显示"输入图片已丢失"，不静默清空）。

### Job / Queue / SSE（`app/api/v1/jobs.py`）

```
POST   /api/v1/jobs                        创建生成任务（body: {snapshot, client_request_id?,
                                           queue_mode: normal|next, source}）
                                           幂等（Phase 7 Task7）：相同 (source, client_request_id) +
                                           相同 payload → 返回原 Job（idempotent_replay=true）；
                                           相同 key + 不同 payload → 409 IDEMPOTENCY_KEY_CONFLICT
GET    /api/v1/jobs                        列表（status/limit/offset）
GET    /api/v1/jobs/{id}                   详情（含 items 子项 + stages 多阶段进度，§二十四；
                                           StageItem 含 reused_from_stage_item_id 复用溯源）
POST   /api/v1/jobs/{id}/pause             安全暂停（当前图完成后暂停）
POST   /api/v1/jobs/{id}/resume            继续暂停任务（已完成 Item 不重跑）
POST   /api/v1/jobs/{id}/cancel            取消（终态；已完成图片保留）
POST   /api/v1/jobs/{id}/resume-remaining  继续剩余图片（创建子 Job，继承原 Workflow 身份；
                                           Phase 7 Task0：Stage-aware——已 COMPLETED 的上游 Stage
                                           直接复用，从第一个未完成 Stage 才开始执行）
GET    /api/v1/history                     历史任务（Phase 4 Task5/6：来源=jobs；
                                           bucket=all|active|completed|failed|cancelled + source 筛选；
                                           按 resume_of_job_id 归组为任务族 [{root_job_id, root, resumes}]）
GET    /api/v1/queue                       当前队列（worker/running/queued/paused）
POST   /api/v1/queue/reorder               拖拽排序（仅等待任务，全量一一对应）
POST   /api/v1/queue/resume                恢复队列（系统性失败自动暂停后）
GET    /api/v1/engine/status               引擎健康（Adapter.health()，独立于 Studio 状态）
GET    /api/v1/events/jobs                 SSE 任务事件（只通知；事实源永远是数据库）
```

### Image / Gallery（`app/api/v1/images.py`）

```
GET    /api/v1/images                      列表（job_id/review_status/favorite/source/kind/
                                           search=导入文件名/date_from/date_to/limit/offset）
GET    /api/v1/images/{id}                 详情
GET    /api/v1/images/{id}/content         图片文件流
GET    /api/v1/images/{id}/versions        父子关系 {image,parent,children}（§十九）
PATCH  /api/v1/images/{id}/review          审核：KEPT / REJECTED / UNREVIEWED
PATCH  /api/v1/images/{id}/favorite        收藏切换
GET    /api/v1/images/{id}/workbench       Image → 工作台（Task7：追溯根生成 Job 的快照 +
                                           完整执行身份；返回根图 Seed）｜导入图 → 404 IMAGE_NO_GENERATION_CONTEXT
GET    /api/v1/images/{id}/provenance      Provenance（Task10）：parent/root/job/stage/模块/双指纹/Seed（+scale）
GET    /api/v1/images/{id}/references      Phase 5 §十一：引用保护检查（Recipe/StageItem/Asset 参考/
                                           Asset 溯源/派生图 计数与明细 + active_job_ids）
POST   /api/v1/images/upscale              图库已有图片高清放大（body: {image_ids:[…]}，§二十四）
                                           → 创建 job_kind=process 的普通 Job（仅 upscale Stage）
POST   /api/v1/images/import               Phase 5 §三：外部图片导入（multipart files[] 多张，
                                           PNG/JPG/JPEG/WEBP，≤10MB）
                                           → {imported[], duplicates[], failed[], *_count}
                                           sha256 去重（同内容不建第二份）；单张失败不影响整批；
                                           source=import / kind=original / job_id=null；永久文件在 images/originals/
GET    /api/v1/images/by-job/{id}/summary  按 Job 统计（§四十九）
```

### Modules（`app/api/v1/modules.py`，Phase 5 §十四）

```
GET    /api/v1/modules                     WorkflowModule 能力列表（module_id/version/title/
                                           uses_seed/input_kind/input_required/input_role/
                                           output_kind/parent_policy/output_cardinality）
                                           + Phase 5.1 Task7 真实可用性：
                                             registered（恒 true）
                                             available（comfyui 下必须能加载 provider binding）
                                             provider / binding_version / unavailable_reason
                                           + Phase 6 Task8/9：parameters（ParameterSpec 元数据）/
                                             size_mode
                                           + Phase 7：allowed_job_kinds / can_start_from_image /
                                             is_generative / input_slots（role+required+max_count）
                                           + Phase 7 Task8：capabilities 按实际选中的
                                             module_version 获取（非注册表默认版本）
                                           → 前端"文生图/图片生成"Gate 判定（禁止硬编码模块列表；
                                             Gate 唯一依据 available=true，registered ≠ available）
```

Stage0 输入 Slot 校验（Phase 7 Task5，Job 创建前）：未声明角色 → `UNUSED_INPUT_IMAGE` /
必填缺失 → `INPUT_IMAGE_REQUIRED` / 超量 → `INPUT_SLOT_LIMIT_EXCEEDED`（模块声明为准）。

约定：状态机与暂停/取消/续跑语义见 docs/JOB_STATE_MACHINE.md；队列行为见 docs/QUEUE_SPEC.md；
崩溃恢复见 docs/RECOVERY_SPEC.md。

创建 Job 的输入校验（Phase 2.1 §八 + Phase 3 §0.4/§五 + Phase 5.1 Task1-5，固定）：

```
snapshot 直接复用严格 WorkbenchSnapshotModel：
  width / height  64..4096
  count           1..64
  seed            0..2147483647（seed_mode=fixed 时必须提供，且 count 必须 = 1，
                  §0.4 固定 Seed 仅用于单张精确复现：fixed + count>1 → 400 FIXED_SEED_SINGLE_ONLY）
  prompt_mode     structured | full（Literal）
  selected_assets 结构化类型
  workflow_modules Phase 5.1 正式类型 WorkflowModuleRef：
                  [basic_generate]（文生图）｜[img2img]（图生图，必须携带输入图）｜
                  [basic_generate|img2img, upscale]；process Job 必须 == [upscale]；
                  每项 = module_id + 可选 module_version/provider/binding_version/双指纹 + config{}
  input_images    Phase 5 §八/§十：[{role:"source", image_id}]，max=1（>1 → 422）；
                  创建期校验图片存在（404 IMAGE_NOT_FOUND）→ 冻结到 Stage0 全部
                  JobStageItem.input_image_id；process Job 若携带则必须与 input_image_ids 一致
                  （不一致 → 400 PIPELINE_INVALID）
Prompt 长度上限：结构化单字段 ≤2000 / 正向 ≤10000 / 负向 ≤8000（400 PROMPT_TOO_LONG）
workflow_snapshot.modules 由后端按实际模块身份写入（§四/§五），客户端无需传递
未知 WorkflowModule → 400 WORKFLOW_ERROR（创建期拒绝，不是执行期才炸）
Phase 5.1 PipelineValidator（Job 创建前，依据 ModuleCapabilities）：
  输入图没人消费（Stage0 input_required=false）→ 400 UNUSED_INPUT_IMAGE
  需要输入图却没给（Stage0 input_required=true）→ 400 INPUT_IMAGE_REQUIRED
  Stage N 不消费 Stage N-1 输出 / 上游输出非图片 → 400 PIPELINE_INVALID
  模块 config 非法（validate_config）→ 400 MODULE_CONFIG_INVALID
  config 单链：Workbench → Recipe → Job.workflow_snapshot → JobStage.config_json（唯一事实源）
```

Phase 4 Task9（创建期身份解析，固定）：

```
workflow_modules 请求项：
  只有 module_id（普通新建）            → 解析当前默认版本（含 workflow_hash/binding_hash）
  携带完整身份（module_version/provider/binding_version/双指纹，从历史/Image/配方恢复）
                                        → 固定原身份；指纹不一致 → 400 BINDING_HASH_MISMATCH /
                                          WORKFLOW_HASH_MISMATCH；provider 不匹配 → 400 BINDING_IDENTITY_MISMATCH
  老 Job 的 binding_hash=null           → 兼容；comfyui 下采纳磁盘当前指纹
```

## 3. 规划（Phase 5+，按需实现）

| 方法与方法路径 | 用途 |
| --- | --- |
| 参考图 / 人脸修复 / 局部重绘 | 新增 WorkflowModule（声明 I/O 能力，见 MODULE_IO_CONTRACT.md）+ provider binding 目录即可复用同一 Job API（img2img 已于 Phase 5.1 验证该路径；Reference 等待模型方案） |
| Agent / 豆包 / 手机端接入 | 复用同一 Job API（source=agent/doubao 已预留） |
