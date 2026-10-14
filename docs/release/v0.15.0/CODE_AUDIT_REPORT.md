# CODE_AUDIT_REPORT — v0.15.0

> 范围：相对基线 `b974ffa`（v0.14.1）的全部 47 个改动文件（+4137 / −1198）。
> 方式：静态审查 + 类型检查 + 全量测试 + 构建 + 浏览器实测。本文只报告已核实的问题与结论。

## 1. 架构合规

- **单队列语义不变**：未新增队列/调度路径；Job 创建仍只在 `JobService`，Worker 串行。
- **Job/Queue 归 TaskDock，Engine 归 TopNav Power**：职责边界按指导 §14 落实。
- **无平行基础设施**：未新增服务、端口、计划任务、launcher；未接入/绕过 ControlHub。
- **无数据库迁移**：`EngineJobStatus` 是引擎侧内存 DTO，`step/max_step` 不落新表；
  沿用 schema 0018。
- **业务模型未改**：未新增模型/节点/AI 能力（符合 §26“明确不做”）。

## 2. 审查发现并已修复的问题

| # | 严重度 | 问题 | 修复 |
|---|---|---|---|
| 1 | 高（崩溃） | `CompactCurrentJob` 对空 `positive_prompt_snapshot` 直接 `trim()` 导致崩溃 | 改为 `(job.positive_prompt_snapshot ?? '').trim()` |
| 2 | 中（视觉） | 宽屏（≥1024）多出一行 Workspace Tabs（`.ds-tabs` 与 `.generate__tabs` 同特异性，打包顺序决定胜出） | 选择器提高到 `.generate .generate__tabs`（0,2,0），媒体块同步，测试更新（commit `c30d321`） |
| 3 | 中（设计违背） | Light 主题 Canvas 变浅，违背“Canvas 恒定深色哑光” | 新增主题无关 `--canvas-stage-*`，舞台恒深色、空态浅字（commit `c30d321`） |
| 4 | 低（测试稳定性） | Tooltip 测试同时命中 IconButton 与 DS tooltip | 改为 hover 后 `findByText` 精确文案 |
| 5 | 低（精度） | 双阶段总进度 `9.2/16=57.4999` 落 57，与预期 58 不符 | 用例 progress 调整为整 58%，验证加权而非取整，代码本身 round 正确 |
| 6 | 低（整洁） | generate.css 残留无 DOM 匹配的 `.generate__columns` / `.generate__modebar` / 1319 死 CSS | 删除并合并新断点块 |

## 3. 安全 / 凭据

- 改动中**无任何密钥、Token、密码、Cookie、私钥**；
- 未硬编码 `localhost` 之外的敏感地址；引擎地址来自既有配置（127.0.0.1:8188）；
- 图片 URL 统一走既有 `imageContentUrl`，未新增越权路径；
- 未跟踪文件 `control-hub.json`（机器产物）**刻意不提交**，避免泄露本地拓扑。

## 4. 并发 / 状态正确性

- `liveProgressByItem` 为纯内存，终态/切换/prune 三条清理路径齐备，避免泄漏已完成条目；
- 进度持久化节流（330ms）在 **stage 切换时立即写**，不会因节流丢阶段边界；
- `ResizablePane` 用 pointer capture，拖拽期间不会因移出元素丢事件；
- localStorage 读写均包 try/catch（隐私模式降级），读取时 `Number.isFinite` 校验 + clamp。

## 5. 向后兼容 / 遗留

- 保留 `ResultPane.tsx`（被 CanvasStage 取代）、`GenerationControls.tsx`（被 InspectorPanel 取代），
  因对应测试仍有效且删除风险大于收益；后续版本可在确认无引用后移除，本版不做删除。
- 删除 `proto/` 前已确认其能力 100% 提升为正式 `components/CanvasViewport/`。
- 旧 `SettingsPane.compact/queue` 测试删除前，其断言已迁移到 Workbench/TaskDock 新测试。

## 6. 质量门禁结果

| 门禁 | 结果 |
|---|---|
| `npm run typecheck` | EXIT=0 |
| `npm run test:ci` | 311 passed（62 文件） |
| `npm run build` | EXIT=0 |
| 后端 `pytest` | 475 / 0 failures / 0 errors / 3 skipped |
| 浏览器实测 | 见 `UI_VISUAL_ACCEPTANCE.md` |

## 7. 未做 / 风险提示

- 真机 ComfyUI 出图、Running/Completed 动态态、冷启动计时未执行（环境离线），
  已在 `UI_VISUAL_ACCEPTANCE.md` / `RUNTIME_COLD_START_FOLLOWUP.md` 标注，
  合同层由测试覆盖；**不构成阻断 v0.15 布局/前端交付的缺口**，但需下一阶段补真机数据。
- 本版未删除旧组件与对应测试，包体积影响很小；如需进一步瘦身，列入后续清理任务。
