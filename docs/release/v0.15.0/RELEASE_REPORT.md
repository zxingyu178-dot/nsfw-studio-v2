# RELEASE_REPORT — NSFW Studio v0.15.0

- 版本：**0.15.0**
- 发布日期：2026-10-14
- 分支：`feature/v0.15-workbench-layout4`
- 基线：`main` @ `b974ffa`（tag `v0.14.1`）
- 主题：**Workbench Layout 4.0（Canvas First）/ 真实进度（Job·Stage·Step）/ 可视化 Prompt 库 / Glass 设计体系**

---

## 1. 本版本交付了什么

v0.15 是一次**工作台布局与信息架构重构**，不是换肤：

1. Generate 重排为 **Canvas First 三栏 + 底部任务坞**：
   - 左：Prompt Console（8 槽位单槽聚焦）；
   - 中：深色哑光 Canvas（最大视觉区，图片直接滚轮缩放/拖拽，无需 Lightbox）；
   - 右：参数 Inspector（只负责“怎么生成”）；
   - 底：TaskDock（当前 Job / 队列迁出右栏）。
2. 左右栏可拖拽（`ResizablePane`），三档断点，**整页零纵向滚动**。
3. 生成中显示**真实 Job / Stage / Step**：后端透传 ComfyUI 真实 `step/max_step`，
   前端跨 stage 加权总进度；**高清放大（upscale）不伪造 Step**。
4. 进度事件分流为**瞬态 SSE**（不刷库）与**持久 job_events**（只记关键变化）。
5. Prompt 库卡片可视化：预览图在文本下方，无图固定 16:9 显示“暂未生成”。
6. Glass 毛玻璃 token 体系 + 性能守卫（玻璃层 ≤8、Canvas 绝不 blur）。
7. PR 闸门加入前端 Vitest（`test:ci` + GitHub Actions）。

## 2. 明确不做（沿用指导 §26）

不新增模型 / 节点 / Anime / FaceID / IPAdapter / ControlNet；不做 Prompt 自动 AI 生成、
自动换封面、手机生图、Tauri/Electron、Runtime Lease R5；MediaReview Android 移交下一阶段。
**单队列语义不变**，Job 创建只在 JobService，Worker 串行；无数据库迁移（沿用 0018）。

## 3. 验证结果（均实测，非声明）

| 验证项 | 命令 | 结果 |
|---|---|---|
| 前端类型检查 | `npm run typecheck` | **EXIT=0** |
| 前端全量测试 | `npm run test:ci`（vitest singleFork） | **311 passed（62 文件），0 失败** |
| 前端构建 | `npm run build` | **EXIT=0**（多次） |
| 后端全量测试 | `.venv\Scripts\python.exe -m pytest` | **475 tests，0 failures / 0 errors，3 skipped** |
| 浏览器视觉验收 | Aha Browser（本机 127.0.0.1:8000） | 见 `UI_VISUAL_ACCEPTANCE.md`（静态布局全绿；真实 Running/Completed 受环境限制） |

## 4. 环境受限项（如实标注，未伪造）

- **Task 19 真实 ComfyUI 出图未执行**：ComfyUI（8188）STOPPED、ControlHub offline；
  未擅自启动长生命周期 GPU 服务。Step 合同由后端 5 个契约测试 + 前端 workbenchProgress
  测试确定性覆盖。
- **Task 25 三次冷/热启动计时未执行**：同上，移交下一阶段按 ControlHub 现有合同处理
  per-service timeout，**禁止在 NSFW 写第二套 launcher**。
- Prompt 库“有预览”的真机截图需要真实出图，当前只有“暂未生成”卡；预览渲染路径由
  `PromptTab.cover.test.tsx` 6 个用例覆盖。

## 5. 版本号位置

- `configs/app.yaml` → `0.15.0`
- `frontend/package.json` → `0.15.0`
- `frontend/package-lock.json`（根 + `packages[""]`）→ `0.15.0`
- 后端 `backend/app/core/config.py` 从 `app_cfg` 读取 version（非硬编码）。

## 6. 发布动作

- 提交：`chore(release): v0.15.0`；
- 标签：`v0.15.0`；
- 合并：`feature → develop → main`；
- 推送：`git push origin`（含分支与 tag）；
- 交付包：`NSFW_Studio_v0.15.0_Handoff.zip`（12 份报告 + 验收截图）。
