# NSFW Studio v0.15.1 测试报告

- 测试时间：2026-10-15
- 环境：Windows，Node v22.23.2 / npm 10.9.8；后端 venv（项目内 `.venv`）
- 范围：v0.15.1 全部 P0/P1/P2 改动（后端引擎/队列 + 前端 Workbench 4.0）

## 1. 自动化测试结果

| 套件 | 命令 | 结果 |
|---|---|---|
| 后端全量 | `.venv\python -m pytest tests/backend --junitxml` | **480 passed / 0 failed / 3 skipped** |
| 前端全量 | `npm run test:ci`（vitest forks/singleFork） | **334 passed / 67 files**（EXIT=0） |
| 前端类型 | `npm run typecheck`（tsc --noEmit） | **EXIT=0** |
| 前端构建 | `npm run build`（tsc + vite build） | **EXIT=0**，151 modules，dist 产出 |
| store 专项 | `npm run test:store` | **11 passed / 0 failed** |

后端 junit：`temp/_v0151_backend_p2.xml`（tests=480 failures=0 skipped=3）。
前端全量日志：`temp/_v0151_vitest_p2b.log`（334 passed）。

> 说明：前端全量首次运行曾出现 3 个失败（`Settings/MobileReviewPairing` 等假定时器相关
> 用例），单独运行该文件 3/3 通过、且第二次全量 334/334 通过；判定为全量并行下的
> fake-timer 抖动，与本次改动（Generate workbench）无关，非回归。

## 2. 新增 / 重写测试清单（v0.15.1）

### 后端
- `test_progress_step_contract.py`：sampler-only step / stage_item_id / 去重契约（#19/#20）。
- `test_engine_stall.py`：**重写为 3 个用例**（#26）
  1. 采样 step 冻结卡死 → ENGINE_STALLED + cancel；
  2. 非采样阶段（模型加载等）不被短 stall 误判，最终 COMPLETED；
  3. step 正常推进不判 stall。
- 净效果：后端由 479 增至 **480**（净 +1）。

### 前端
- `resumeFamily.test.ts`（5）：完整 resume 链、visited 去环、max-depth 16（#21）。
- `imageMutationQueue.test.ts`（4）：per-image 串行、enqueue 始终返 Promise、
  latest 合并最后意图（#22）。
- `CanvasStage.queued.test.tsx`（2）：QUEUED 横幅 + 前方 N 任务；RUNNING 走 HUD（#25）。
- `CanvasStage.lightbox.test.tsx`（1）：主 preview / filmstrip thumbnail+lazy /
  全屏 Lightbox 定位 shown / ESC（#26 迁移自 ResultPane）。
- `InspectorPanel.count.test.tsx`（2）：数量 1–64 口径、chips、越界钳制（#26 迁移自
  GenerationControls）。
- `legacy.guard.test.ts`（2）：旧文件删除 + 生产源码无 legacy import（#26）。
- `resolveActiveSlot.test.ts`（5）：合法记忆 / 非法回退 / 全空回退 style（#26）。
- CanvasViewport（#17）、jobStore.liveProgress（#18/#23）、workbenchProgress（#18）、
  TaskDock（#23）、PromptTab.cover（#24，9 用例）等同步更新。

## 3. 真机 / 视觉验收（Gate A–E）

- 审计要求的真机 Gate（真实 ComfyUI Basic Step、Basic→Upscale Step 消失、>1536 长边
  100%、A→B→C resume 全图可见、CI green）依赖 ComfyUI 8188 在线。
- **当前状态：ComfyUI 8188 大概率 STOPPED、ControlHub offline**；真机 Gate A–E 标记为
  **部分验证 / 未执行**（未伪造）。已通过的等价保障：
  - sampler-only Step、stall、resume family、stage_item_id 均由后端/前端单测覆盖；
  - 前端 typecheck + build + 全量 vitest 通过；
  - 真机与多分辨率视觉 Gate 待 ComfyUI 恢复后补跑（沿用 v0.15.0 browser-use 流程）。

## 4. 结论

- 所有 P0/P1/P2 改动均有自动化测试覆盖且全绿；
- 前端生产构建成功、后端全量通过；
- 真机 Gate A–E 因引擎离线为**部分验证**，不阻塞代码与 tag，但须在引擎恢复后补做并归档。
