# NSFW Studio v0.15.1 发布报告（Workbench Live Hardening）

- 发布日期：2026-10-15
- 版本：v0.15.0 → **v0.15.1**（SemVer patch）
- 类型：缺陷修复 / 稳定性加固（无新业务模型、无数据库迁移、无新增模型/节点/AI 能力）
- 基线：v0.15.0（main `2fb7f8d`，tag `v0.15.0`）
- 需求来源：`temp/NSFW_Studio_v0.15_Code_Audit_and_v0.15.1_Hardening.md`

## 1. 发布主题

针对 v0.15 代码审计发现的 1 个 P0、8 个 P1、4 个 P2 问题做 Workbench Live Hardening，
覆盖 CI 工具链、Canvas 几何与进度语义、真实采样 Step、SSE 去重、resume 链、
review 串行化、任务坞忙碌态、预览失败占位、队列语义、stall 看门狗、增量刷新、
legacy 清理与 active slot 守卫。

## 2. 交付内容

| 项 | 内容 |
|---|---|
| P0 | CI Node 22.22.2 固定（ci.yml / engines / .nvmrc / .node-version / README） |
| P1 | #17–#25 共 8 项（详见 HARDENING_REPORT.md） |
| P2 | #26 共 4 项（stall / 增量刷新 / legacy 清理 / slot guard） |
| 文档 | HARDENING_REPORT.md、TEST_REPORT.md、CHANGELOG.md |
| 版本 | configs/app.yaml、frontend/package.json、package-lock.json 均 0.15.1 |

## 3. 提交记录（feature/v0.15.1-workbench-hardening）

- `4ade0af` fix(ci): pin Node 22.22.2 toolchain（修 main 前端 CI 红）
- `cac4441` feat(engine): sampler-only Step 语义 + SSE stage_item_id/去重 + 采样 stall 看门狗
- `764bc27` feat(workbench): Canvas 逻辑尺寸/多阶段进度/resume 链/串行 review/队列语义/TaskDock busy
- `9857369` fix(prompt): PromptCard 预览失败统一“暂未生成”占位，Editor 小封面回退“无封面”
- `b78710f` refactor(workbench): 清理 0.14 legacy 组件 + active slot localStorage 守卫

发布顺序：feature → develop → main，等待 main CI green 后**最后**打 annotated tag
`v0.15.1`；旧 `v0.15.0` tag 不动。

## 4. 测试与验证

- 后端：**480 passed / 0 failed / 3 skipped**（junit `temp/_v0151_backend_p2.xml`）
- 前端：**334 passed / 67 files**；typecheck EXIT=0；production build EXIT=0；
  store 专项 11 passed / 0 failed
- 详见 TEST_REPORT.md。

## 5. 已知限制 / 待办

- **真机 Gate A–E 为部分验证 / 未执行**：ComfyUI 8188 离线、ControlHub offline，
  真实引擎 Basic/Upscale Step、>1536 长边 100%、A→B→C resume 全图可见待引擎恢复后补跑
  并归档；未伪造真机结果。
- 首次全量前端出现的 3 个 fake-timer 用例失败已确认为并行抖动（单跑与复跑均通过）。

## 6. 升级说明

- 拉取 `v0.15.1`，前端需 Node `>=22.22.2 <23`（`npm ci && npm run build`）；
- 后端无需数据库迁移；
- 无新增环境变量或配置项。
