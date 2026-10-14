# Generate 页信息重复 Inventory（§9 审计）

- 分支：`feature/v0.14.1-fix-hardening`　HEAD：`1e5893e`（v0.14.0）
- 范围：只**盘点**当前「ComfyUI 状态 / 当前 Job / Queue / Stage / elapsed（计时）」在前端各组件的出现位置，并给出**下一阶段唯一推荐位置**。**本轮不重排 UI。**
- 路径相对仓库根（`frontend/`）。

## 单一事实源（先认清数据从哪来）

所有这些展示都来自同一个 store：`frontend/src/stores/jobStore.ts`。

- `engine: EngineStatusDTO | null`（`jobStore.ts:9`）——ComfyUI 在线/离线/版本，来自 `GET /engine/status`（`refreshJobs` `:76`）。
- `queue: QueueDTO | null`（`jobStore.ts:11`）——`{running, queued, paused, worker}`，来自 `GET /queue`。
- `trackedJob: JobDTO | null`（`jobStore.ts:13`）——本页提交/关注的 Job（含 items/stages/progress）。
- `activeJob(store) = trackedJob ?? queue?.running ?? null`（`jobStore.ts:55-57`）——**「当前 Job」的唯一派生口径**，Canvas 与 TaskDock 都用它。
- 刷新机制：SSE 仅作唤醒（`subscribeJobEvents(() => scheduleJobRefresh(), ...)` `:238-241`）→ 0.3s 防抖回源（`scheduleJobRefresh` `:64-70`）；另有 10s 兜底轮询（`:242-244`）。
- 结论先行：**数据层没有重复**（都读同一 store）；**重复发生在「同一信息被多个 UI 区块各自渲染一遍」**。

## 五项信息逐处盘点

### ① ComfyUI 状态（engine online / name / version）

| 位置 | 文件:行 | 展示形式 |
|---|---|---|
| TopNav 状态胶囊 | `frontend/src/components/TopNav.tsx:18-28`（`ComfyStatusPill`，挂载 `:46`） | glance：`COMFY 在线/离线` 圆点胶囊 |
| TopNav 电源按钮 | `frontend/src/components/PowerMenu.tsx:113-127`（`PowerControl`，TopNav 挂载 `:49`） | 电源图标，点开统一 Runtime 面板（启停/详情） |
| 右栏 GenerationControls 引擎只读点 | `frontend/src/pages/Generate/components/GenerationControls.tsx:145-160`（`EngineState`，挂载于「工作流」段 `:53`） | 在线圆点 + `engine_name version`；离线显「离线」 |
| 生成按钮禁用文案 | `frontend/src/pages/Generate/components/GenerateAction.tsx:31-37` | 离线时禁用并显「Engine 离线，无法提交」 |
| 引擎面板（轮询详情） | `frontend/src/components/EngineControlPopover.tsx`（PowerMenu 复用其 body）、`EngineStatus.tsx`（15s 轮询） | 丰富启停状态/操作 |

- 实时性差异：TopNav 胶囊与右栏圆点读同一 `store.engine`，同一次刷新；`EngineControlPopover`/`EngineStatus` 是独立 15s/3s 轮询（`:81`/`EngineStatus.tsx:38`），用于面板内的运行时细节，属「操作面板」而非 glance，不构成展示冗余。

### ② 当前 Job（运行中任务的身份 + 总进度%）

| 位置 | 文件:行 | 展示形式 |
|---|---|---|
| 中栏 Canvas（ResultPane） | `frontend/src/pages/Generate/ResultPane.tsx:65-67,118-128` | `shortJobId` +「正在生成第 N/M 张 · progress%」 |
| 右栏 TaskDock（CurrentJobCard） | `frontend/src/pages/Generate/components/CurrentJobCard.tsx:16-22,35-41` | StatusBadge + shortJobId + ProgressBar +「第 N 张 · progress%」 |
| 队列 running 来源 | `frontend/src/pages/Generate/components/QueuePanel.tsx`（`store.queue.running`） | running 行也带当前任务摘要 |

- 二者同源 `activeJob(store)`（`jobStore.ts:55`），**进度百分比在 Canvas 与 TaskDock 各渲染一次 = 真重复**。

### ③ Queue（等待/暂停/队列操作）

| 位置 | 文件:行 | 展示形式 |
|---|---|---|
| 右栏 QueuePanel（唯一队列面板） | `frontend/src/pages/Generate/components/QueuePanel.tsx:22-...`（计数 `:54-58`、暂停/继续队列、拖拽排序、清理陈旧） | 等待/暂停列表 + 全局队列操作 |

- Queue **只在 TaskDock/QueuePanel 一处**完整呈现；Canvas 不渲染队列，仅经 `activeJob` 显示 running 那个。属合理分工，非重复。

### ④ Stage（粗粒度阶段 / 分阶段进度行）

| 位置 | 文件:行 | 展示形式 |
|---|---|---|
| 中栏 Canvas 分阶段行 | `ResultPane.tsx:67,137-145`（`stageProgressLines`）+ 行内 `current_stage` 文案 `:126` | 多阶段时「基础生成 N/M · 第 x 张 · %」逐行；单阶段时显 `current_stage` 中文 |
| 右栏 TaskDock 分阶段行 | `CurrentJobCard.tsx:18,42-49` + 行内 `current_stage` `:53` | 与 Canvas **同一套** `stageProgressLines(job)` |
| 标签映射 | `frontend/src/types/workbench.ts:713-721`（`STAGE_LABEL`：submit/queued/execution/sampling/save_image/done/error）、`:686-690`（`MODULE_LABEL`） | 把后端粗 stage/module id 翻中文 |
| 计算工具 | `frontend/src/utils/jobProgress.ts`（`stageLine`/`stageProgressLines`/`overallProgress`） | Canvas 与 TaskDock **共用同一函数** |

- **Stage 行在 Canvas 与 TaskDock 各渲染一次 = 真重复**（且因共用 `stageProgressLines`，文案完全一致）。
- 注：此处的 `current_stage` 是后端 adapter 硬编码的粗粒度阶段（sampling/execution/save_image），**不是真实 sampling step**（见 §11 审计）。

### ⑤ elapsed（计时）

| 位置 | 文件:行 | 展示形式 |
|---|---|---|
| 中栏 Canvas | `ResultPane.tsx:129-134`（`<ElapsedTimer startedAt={job.started_at} finishedAt={job.finished_at} />`） | 「· 已运行 xx」 |
| 右栏 TaskDock | `CurrentJobCard.tsx:57-61`（同一 `ElapsedTimer`） | 「已运行 xx」 |
| 计时器组件 | `frontend/src/components/ui/ElapsedTimer.tsx:25`（内部 `setInterval(...,1000)` 自走秒） | 唯一计时实现 |

- **elapsed 在 Canvas 与 TaskDock 各渲染一次 = 真重复**。实时性差异：只有 elapsed 需要「秒级自走」，`ElapsedTimer` 内部 1s tick 是合理的；progress/stage 仍走 store 回源（秒级以下不需要）。

## 重复 / 实时性差异判定

- **真重复（同一信息、同一实时口径、同屏两处）**：
  - 当前 Job 进度%：Canvas `ResultPane` ↔ TaskDock `CurrentJobCard`；
  - Stage 分阶段行：Canvas ↔ TaskDock（且共用 `stageProgressLines`）；
  - elapsed 计时：Canvas ↔ TaskDock。
- **有实时性需求差异、不算冗余**：
  - ComfyUI 状态：TopNav 胶囊/glance（随 store）vs Power 面板内 3s/15s 轮询（操作态）——一个只读概览、一个操作面板。
  - elapsed 自走 1s（必须）vs progress/stage 回源（秒级轮询足够）。
- **合理分工、非重复**：Queue 只在 TaskDock；Canvas 不重复队列。

## 下一阶段唯一推荐位置（本轮只给结论，不实施）

| 信息 | 当前出现位置 | 下一阶段唯一推荐位置 |
|---|---|---|
| ComfyUI 状态 | TopNav 胶囊 + Power 按钮（`TopNav.tsx`）；右栏 `GenerationControls.EngineState`（`GenerationControls.tsx:145`）；`GenerateAction` 禁用 | **TopNav Power 区**（`TopNav.tsx` 的 `ComfyStatusPill` + `PowerControl`）作为唯一 glance 与操作入口；右栏 `EngineState` 降级为「不可用时的就地提示」，不再与 TopNav 重复在线/版本 |
| 当前 Job | Canvas `ResultPane` + TaskDock `CurrentJobCard` | **Canvas（`ResultPane`）**：运行中的大图舞台旁显示当前任务身份/总进度；TaskDock `CurrentJobCard` 保留**操作（暂停/继续/取消/续跑）与错误/摘要**，不再重复渲染进度条与「第 N 张」文案 |
| Queue | TaskDock `QueuePanel` | **TaskDock（`QueuePanel`）保持唯一**；Canvas 不显示队列 |
| Stage | Canvas + TaskDock 两处 `stageProgressLines` | **Canvas（`ResultPane`）**作为阶段进度的唯一展示；TaskDock 不再重复分阶段行（操作卡只保留模块链摘要 `moduleLabel`） |
| elapsed | Canvas `ResultPane` + TaskDock `CurrentJobCard` | **Canvas / Dock 二选一：推荐 Canvas（`ResultPane`）** 随当前任务显示；TaskDock 操作卡不再重复计时（若保留操作卡可视性，可只在 Canvas 消失后于 Dock 兜底一次，避免空窗） |

> 总原则：**「看进度/阶段/计时」收敛到 Canvas，「管任务（操作/摘要/错误/队列）」收敛到 TaskDock，「看/管引擎」收敛到 TopNav Power。** 当前重复集中在 Canvas ↔ TaskDock 之间的「进度 + 阶段 + 计时」三件套。
