# Daily Use 验收报告（NSFW Studio V2 日用化）

> 分支：`feature/daily-use-ux-runtime`（worktree `projects/nsfw-studio-v2-dailyuse`）
> 基线：`d4f1821`。本报告对应计划第二十三节（A–I 顺序）、第二十四节（异常）、第二十七节（视觉尺寸）。
> 图例：✅ 真实浏览器/真实进程验证　🧪 确定性自动化测试覆盖（未真机）　⛔ 本轮未验证（环境受限）

---

## 0. 走查环境与方法（事实）

- 计划指定的云浏览器（云端 Linux 沙箱经 HTTP 代理出公网）**没有到本机回环 / 局域网的路由**
  （`127.0.0.1 → ERR_CONNECTION_REFUSED`），无法驱动本机服务。改用**本地 Playwright（1.63.0，
  `channel="chrome"` 直接驱动本机已装 Chrome，不另下浏览器）**，截图后由执行者逐张目检。
- 为不触碰受保护进程，dailyuse 后端起在 **8001**，使用**独立临时 DataRoot**
  `temp/dailyuse_e2e_data`（零污染用户 `D:/NSFW-Studio-Data`），生成适配器连接本机既有外部
  ComfyUI **8188**。
- 机器事实：GPU 为 RTX 3060 6GB，桌面同时运行大量用户程序；模型空闲后会卸载、每张图重新加载，
  单张 1024² 实测约 12–17 分钟（连续提交保持模型热时较快）。
- 受保护、本轮禁动：外部 ComfyUI 8188（pid 172356，`projects/comfyui/app`）、主仓库 uvicorn 8000
  （pid 144256）。

---

## 1. 计划第二十三节 A–I 验收总表

| 项 | 验收点 | 结果 | 证据 / 说明 |
|---|---|---|---|
| A | 桌面冷启动、浏览器自开、**8000 直出、不需 4173** | ✅（直出）/ ⛔（桌面双击 8000） | 全程 E2E 跑在 **FastAPI 直出的前端（8001）**，未使用 Vite 4173，证明“后端直出、不依赖预览服务器”。桌面双击 `.lnk` + 8000 冷启动因 8000 被主仓库 uvicorn 占用未真机；启动脚本通过语法解析与只读逻辑自检。 |
| B | 启动引擎 STARTING→RUNNING_MANAGED、8188 绿、重复点击不重复起 | 🧪 | 8188 为外部 ComfyUI（禁杀），无法真机受管启动。`test_engine_runtime_service.py / test_engine_runtime_api.py` 覆盖 managed start、STARTING→RUNNING_MANAGED、start 幂等（二次点击不二次 spawn）。 |
| C | 1:1 / 1024² / count1 正常生成、计时每秒更新、入 Gallery | ✅ | 真实出图 `img_ba62542d`；计时器捕获读数 `00:01 → 00:02`（每秒走表），无 ETA；图片入库并出现在 Gallery。 |
| D | 9:16 / 1080×1920 尺寸正确、能生成、提示“较慢”、无校验错误 | ✅ | UI 显示“当前 1080 × 1920”，有“该尺寸生成较慢”提示，生成按钮可用（无校验错误），真实出图 `img_d726ad31`。**注**：ComfyUI 工作流在图内把宽 1080 舍入为 **1088**（输出 1088×1920，疑似 VAE 64 倍数）；前端正确提交 1080、后端不转换；红线禁止改工作流，故如实记录不改。 |
| E | ≥3 任务，运行中暂停：当前图完成、后续不开始、Job 安全边界 PAUSED、Queue paused；继续后原暂停 Job 优先 | ✅ | count=2 Job A + B + C；暂停后 item0 跑完，A 在边界 **PAUSED 1/2**（实测等待 164s），worker `queue_paused`，无 RUNNING，B/C 保持排队；resume 后 **A 最先恢复 running=A**。 |
| F | 20+ 队列页面不增高、内部滚动、拖拽正常 | ✅ | 队列容器 `clientHeight=300`、`scrollHeight=1344 > 300`、`overflowY=auto`、内部 `scrollTop=200`、20 行 `draggable=true`，压入 20 任务（经 API 预暂停，未真实生成）。 |
| G | 双击放大/缩小/拖动/Fit/100%/ESC/左右切图 | ✅（Gallery）/ 🧪（Generate 触发） | Gallery 真机全功能：滚轮缩放 `scale(2.488)`、Fit 复位、100% `scale(1)`、拖动 `translate(130px,90px)`、方向键 `1/4→2/4`、ESC 关闭、Lightbox 内仅 1 张当前图。Generate 的 ResultPane 仅跟踪本会话 Job（历史图在 Gallery），其双击触发由 `ResultPane.lightbox.test.tsx` 覆盖；共用同一 Lightbox 组件，真机行为以 Gallery 为准。 |
| H | Prompt card 显示封面、摘要在图下、复制按钮复制正向 Prompt | ✅ | 真实创建 Prompt 并经 ImagePickerDrawer 设封面：卡片封面 lazy（`src=/api/v1/images/<id>/content`）、摘要在图下、设/换封面**不建版本（1→1）**、一键复制内容与后端合成 `positive_prompt` 完全一致、复制按钮不打开 Drawer。 |
| I | 停止引擎：进程树退出、8188 不健康、网页与 Gallery/Prompt 仍可用、再启动可恢复 | 🧪（进程树/再启动）/ ✅（离线可用） | 外部 ComfyUI 禁杀，受管 stop 的“PID + 递归子进程树、先 terminate 再 kill、只停自己启动的”由 `test_engine_runtime_service.py` 覆盖；“引擎离线时网页与 Gallery/Prompt 仍可用”见第 3 节离线真机；再启动恢复由测试覆盖。 |

---

## 2. 计划第二十四节 异常验收

| 异常项 | 结果 | 证据 / 说明 |
|---|---|---|
| **端口冲突，不跳 8189** | 🧪 | 真机 8188 是健康外部 ComfyUI（非冲突态）；模拟“8188 被普通（非 ComfyUI）服务占用”需占用 8188，会破坏外部 ComfyUI，未真机。服务测试覆盖：探测在线但非 ComfyUI → **PORT_CONFLICT**；UI 明示端口冲突、**无 8189 / 自动换口**；此态 start → 409 `ENGINE_PORT_CONFLICT`。 |
| **External：可生成、不可杀** | ✅ | 8001 `/engine/runtime` 返回 **RUNNING_EXTERNAL**（owned=false、health online、v0.37.0）；经其真实生成 4 张图；Popover 对 external **不渲染停止/重启按钮**并说明“不是由 Studio 启动，不能停止或重启”；API 对 external stop/restart → 409 `ENGINE_NOT_OWNED`。 |
| **引擎启动失败，Studio 不崩** | 🧪（spawn 失败）/ ✅（不崩） | 服务测试覆盖 spawn 失败 → state **ERROR**、API 仍 200 返回 ERROR、清理自己刚起的进程树、Studio 进程存活。另见第 3 节：引擎不可达时 Studio 健康检查始终 `ok`、导航不崩。 |
| **Engine Offline：Gallery/Prompt/Assets/Settings 正常，仅生成受限** | ✅ | 见第 3 节专项真机。 |

---

## 3. Engine Offline 专项真机（独立第二后端，非破坏性）

为在不动 8188/8000 的前提下真机验证离线行为，临时启动**第二后端 8002**（独立临时 DataRoot
`temp/dailyuse_offline_data`），把**生成适配器 URL 指向无服务的 8199**（受管 Runtime 仍按固定
8188 探测，符合“端口固定 8188”）。验证后已停止 8002、还原配置：

- ✅ Generate 配置面板引擎显示“**● 离线**”；**生成按钮禁用**，`title="Engine 离线，无法提交"`。
- ✅ 引擎离线时依次打开 **图库 / 提示词 / 素材 / 设置，全部 `OK`**（页面正常渲染，仅数据为空）。
- ✅ 全程 `/api/v1/health` 返回 `{"status":"ok"}`，**Studio 自身未崩**。
- 证据截图：`temp/e2e_shots/offline_gen_disabled.png`、`offline_gallery_ok.png`。

---

## 4. 计划第二十七节 视觉尺寸 / 主题

| 视口 | Dark | Light | 重点观察 |
|---|---|---|---|
| 1280×720 | ✅ | — | 生成配置/Queue/Lightbox/Prompt 卡片/Engine Popover；三列不横向溢出，配置与生成按钮在 720 高度内可见 |
| 1440×900 | ✅ | ✅ | Light 主题：浅底深字、紫色强调，对比清晰、无发白/对比度问题 |
| 1920×1080 | ✅ | — | Lightbox 大图 Fit、底部工具条；Popover；卡片栅格 |

- 截图：`temp/e2e_shots/vis_<w>x<h>_<theme>_<gen|engine|prompt|lightbox>.png`（共 16 张）。
- 目检结论：三种尺寸 Dark 下生成配置、Queue、Lightbox、Prompt 卡片、Engine Popover 均无错位/遮挡/
  横向溢出；Light（1440×900）配色与可读性正常。

---

## 5. 确定性自动化测试最终结果

| 套件 | 基线 | 收口 | 说明 |
|---|---|---|---|
| Backend pytest（`--ignore=test_comfyui_integration.py`） | 254 | **280 passed** | 新增 engine runtime / queue pause / prompt preview / SPA hosting 等；真实生图集成测试按约定 ignore；全量 120s |
| Frontend vitest | 44 | **121 passed / 18 files** | 原有 44 个 UI/store 测试无删除，新增画幅/分辨率/尺寸/timer/lightbox/queue/prompt/engine 等 |
| `npm run typecheck` | ✅ | ✅ | `tsc --noEmit` 零错误 |
| `npm run build` | ✅ | ✅ | tsc + vite build 通过，dist 已含最终修复 |

> 后端最终通过数以收口提交前的实际运行日志为准（`temp/e2e_logs/final_backend_pytest.log`：280 passed）。

---

## 6. 本轮未真机验证项与所需条件（如实标注）

以下项受“受保护端口/进程禁动 + 真机出图耗时长”限制，**未做真机验证**，已由确定性测试覆盖：

1. **受管 ComfyUI 真机启停 / 进程树退出 / 8188 离线后再启动恢复**（B、I）：需 8188 空闲（用户停止
   外部 ComfyUI pid 172356）。当前由 monkeypatch 测试覆盖 managed start、owned stop、idempotent、
   cannot-kill-external。
2. **桌面双击冷启动 + 8000 直出**（A）：需 8000 空闲（主仓库 uvicorn pid 144256 停止）。启动脚本
   已通过语法/只读逻辑自检；“FastAPI 直出不依赖 4173”已在 8001 真机证明。
3. **端口冲突真机（不跳 8189）**：需在 8188 放一个非 ComfyUI 服务且不破坏外部 ComfyUI，难以在本机
   并行实现；由测试覆盖。
4. **Generate 页 ResultPane 双击 Lightbox 真机**：ResultPane 仅跟踪本会话 Job，需在同会话再真实出
   图（每张 12–17 分钟）；其双击为一行 `onDoubleClick` 接线，已由集成测试覆盖，共用 Lightbox 组件已
   在 Gallery 真机全功能验证。

**建议**：用户在方便时停止外部 ComfyUI(8188) 与主仓库 uvicorn(8000)，按 A→B→I 顺序补做受管启停与
冷启动真机；本轮相关代码与确定性测试均已就绪。
