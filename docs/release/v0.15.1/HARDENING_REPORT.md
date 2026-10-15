# NSFW Studio v0.15.1 Workbench Live Hardening 报告

- 版本：v0.15.0 → **v0.15.1**（patch）
- 基线：`main` v0.15.0（2fb7f8d，annotated tag v0.15.0）
- 分支：`feature/v0.15.1-workbench-hardening`
- 需求来源：`temp/NSFW_Studio_v0.15_Code_Audit_and_v0.15.1_Hardening.md`
- 原则：不改业务模型 / 单队列语义，不新增模型 / 节点 / AI 能力，无数据库迁移。

## 1. 修复项总览

| 级别 | 编号 | 主题 | 状态 |
|---|---|---|---|
| P0 | — | CI Node 22.22.2 工具链固定 | ✅ 已修复（单独 commit） |
| P1 | #17 | Canvas 逻辑尺寸 / 真实 100% | ✅ |
| P1 | #18 | liveProgress 多阶段按 stage_item_id | ✅ |
| P1 | #19 | sampler-only Step 语义 | ✅ |
| P1 | #20 | transient SSE 签名去重 + stage_item_id | ✅ |
| P1 | #21 | Canvas 完整 resume family 图片 | ✅ |
| P1 | #22 | Canvas review mutation 串行化 | ✅ |
| P1 | #23 | TaskDock busyJobId 绑定 | ✅ |
| P1 | #24 | Prompt preview 失败统一占位 | ✅ |
| P1 | #25 | QUEUED / RUNNING Canvas 语义分离 | ✅ |
| P2 | #26 | sampling stall 看门狗重写 | ✅ |
| P2 | #26 | Canvas 增量刷新去重 | ✅ |
| P2 | #26 | 0.14 legacy 组件清理 + guard | ✅ |
| P2 | #26 | active slot localStorage 守卫 | ✅ |

## 2. P0：CI 工具链

- `.github/workflows/ci.yml` 固定 Node `22.22.2`；
- `frontend/package.json` `engines.node` 改为 `>=22.22.2 <23`；
- 新增 `.nvmrc` / `.node-version`（均 `22.22.2`）；
- README 注明 Node 版本要求。
- 本机工具链 Node v22.23.2 / npm 10.9.8 满足 engines。

## 3. P1 明细

### #17 Canvas 逻辑尺寸
- `CanvasViewport` 不再用 preview 图的 `naturalWidth` 覆盖几何，避免 1536 preview 与
  真实像素不一致导致 Fit/100% 错误伸缩；
- 新增逻辑尺寸兜底 `FALLBACK_IMAGE{1024,1024}`，100% 反映真实逻辑像素。

### #18 多阶段 liveProgress（前端）
- store 进度 map 由按 item 改为 `liveProgressByStageItem`，key = `stage_item_id`；
- `LiveProgress` 增加 `stageItemId`；`pruneLiveProgress` 按终态 StageItem.id 精确清理；
- 导出 `liveProgressForStageItem`。

### #19 sampler-only Step（后端）
- `comfyui.py` 模块级 `SAMPLER_CLASS_TYPES`
  （`KSampler`/`KSamplerAdvanced`/`SamplerCustom`/`SamplerCustomAdvanced`）；
- submit 记录 `node_classes` / `current_node`；WS 新增 `executing` 分支跟踪当前节点；
- progress 分支仅当 current_node 命中采样白名单才输出 step/max_step，否则
  `stage="execution"`、`step=None`。

### #20 SSE 去重（后端）
- `queue_worker` 构造 `progress_broadcast_heartbeat_ms=2000`；
- 每个 stage_item 维护 **db 与 sse 两套签名**：
  - SSE 广播签名 `(progress,step,max_step,stage,stage_index)` 变化即发，否则 2s heartbeat；
  - DB 持久化签名 `(progress,step,stage)` 330ms 节流，stage 切换立即写；
- 生命周期事件 payload 补 `stage_item_id`。

### #21 完整 resume family
- 新增 `resumeFamily.ts`：`fetchResumeFamilyJobIds(getJob,jobId)`，visited set +
  `MAX_RESUME_FAMILY_DEPTH=16`，返回 root→current 链；
- CanvasStage 用 `jobApi.get` 取完整链后 `fetchAllJobImages` 合并全部图片，
  多层 resume（A→B→C）图片全可见。

### #22 review mutation 串行化
- 新增 `imageMutationQueue.ts`：per-image 串行、`drainPromise` Map 保证 enqueue 始终返回
  Promise、latest Map 合并最后意图；
- CanvasStage `applyMutation`：favorite/setStatus 成功用响应 DTO 校正，失败
  `imageApi.get` 重取权威 + `ds-notice--error`（不静默）；
- 三个动作按钮在 `actionPendingId===shown.id` 时禁用。

### #23 TaskDock busyJobId
- store 增加 `busyJobAction:'pause'|'resume'|'cancel'|null`，`runJobAction(jobId,kind,action)`；
- TaskDock 仅当 `busyJobId===running.id` 时禁用三按钮并显示“正在暂停/继续/取消…”+ `aria-busy`；
- busyJobId 指向别的任务时不误禁用当前任务。

### #24 Prompt preview 失败占位
- PromptCard：onError 置 `previewFailed` 渲染统一“暂未生成”占位（不再隐藏 img / 裂图）；
- Editor 小封面由 content 改为 1536 preview，失败回退“无封面”；preview_image_id 变化重置。

### #25 QUEUED / RUNNING 分离
- CanvasStage 拆 `isRunning` / `isQueued`；ProgressHUD 仅 RUNNING 渲染；
- QUEUED 显示排队横幅（“已加入队列 · 前方 N 个任务 · 等待开始” + 查看当前运行任务）；
- 空结果占位区分运行 / 排队 / 完成三态。

## 4. P2 明细（#26）

### ① sampling stall 看门狗
- 删除旧的 progress/stage 看门狗，改为 `last_step` / `last_step_time`；
- 仅采样阶段（state=running 且 step/max_step 为 int 且 max_step>0）step 冻结超过
  `_stall_timeout` 才判 `ENGINE_STALLED`（消息含“采样 Step 停在 x/y”）；
- 非采样阶段（model load / VAE / upscale / save）不套短 stall，重置 last_step，
  交执行总超时 `ENGINE_TIMEOUT`。

### ② Canvas 增量刷新
- CanvasStage 增加 `imagesKeyRef`，拉取后按 id 去重（Map），`nextKey=排序id join('|')`，
  与上一次相同则跳过 setImages，避免每完成一张全量重排抖动；jobId 切换重置。

### ③ legacy 清理
- 删除 `ResultPane.tsx`（含 lightbox 测试）、`components/GenerationControls.tsx`
  （含 count 测试），确认仅测试引用、无生产 import；
- 迁移生产测试：`InspectorPanel.count`（数量 1–64 / chips / 越界钳制）、
  `CanvasStage.lightbox`（主 preview、filmstrip thumbnail+lazy、全屏 Lightbox、ESC）；
- 新增 `workbench/legacy.guard.test.ts`：遍历 src 非测试源文件，断言旧文件已删除且无
  legacy import/re-export。

### ④ active slot 守卫
- 新增 `resolveActiveSlot.ts`：合法记忆值（命中 STRUCTURED_FIELDS 白名单）优先，
  否则回退第一个有内容 slot，再否则 `style`；
- PromptConsole 改用该函数，杜绝 localStorage 非法值（如 `foo`）导致 8 个槽位全不 active。

## 5. 影响面与兼容性

- 无数据库迁移；SSE 信封结构保持 `{type,job_id,item_id,payload,time}`，仅在 payload
  中补充/细化 `stage_item_id`，后向兼容；
- 前端 liveProgress 结构为内存瞬态，不持久化，结构调整不影响历史数据；
- 删除的组件为 0.14 旧实现，生产路径（Workbench 4.0）已完全覆盖，无路由/导出引用。
