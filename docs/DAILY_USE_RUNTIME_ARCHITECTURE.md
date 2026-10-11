# Daily Use Runtime Architecture（日用化运行时架构）

> 适用：NSFW Studio V2「日用化（Daily Use）」阶段。本文档描述本轮的整体运行时架构、模块边界与数据流。
> 细节契约见 `ENGINE_RUNTIME_CONTRACT.md`（引擎运行时）与 `PROMPT_PREVIEW_CONTRACT.md`（Prompt 封面）。

---

## 1. 背景与目标

NSFW Studio 是**本地生图工作台**：FastAPI 后端 + React 前端 + 本机 ComfyUI。
本轮“日用化”要解决用户日常使用的真实摩擦：

1. 不再需要分别启动后端、前端 dev server——**FastAPI 直接托管前端构建产物**，桌面图标一键打开。
2. 能在**界面内按需启停 ComfyUI**，不生图时（如打游戏）立即释放 GPU。
3. **一键安全暂停 / 继续整个队列**；队列很长时面板**固定高度、内部滚动**。
4. 生成配置提供**画幅 / 分辨率预设**；只显示**已运行计时**（不做 ETA）。
5. Generate 与 Gallery 共用**图片 Lightbox**；Prompt 提供**封面预览、卡片、一键复制**。

本轮**不改变**核心生成链路：不升级 ComfyUI、不装 custom node、不下模型、不改 Anime 工作流、
不重写 QueueWorker / Job 状态机、不改 Seed / Stage-aware Resume。

---

## 2. 两种运行模式

| | 开发模式 | 日用模式（本轮强化） |
|---|---|---|
| 前端 | Vite dev server（5173）+ proxy | React 构建产物 `frontend/dist`，由 FastAPI 托管 |
| 后端 | uvicorn（自动重载） | uvicorn，单端口同时提供页面与 API |
| ComfyUI | 手动 / 外部 | 界面内按需启停（managed），或连接外部实例（external） |
| 入口 | 命令行 | 桌面「NSFW Studio」图标 → `launch_studio` |

开发模式行为保持不变：当 `frontend/dist/index.html` 不存在时，不注册静态托管，根路由仍返回 JSON。

---

## 3. 运行时组件与数据流

```text
┌──────────────┐   HTTP（单端口，默认 8000；E2E 用 8001）
│   Browser    │ ◀──────────────────────────────┐
│ React (dist) │                                │
└──────────────┘                                │
     │ fetch /api/v1/*                          │
     ▼                                          │
┌──────────────────────── FastAPI / uvicorn ───────────────────────┐
│  API Router (/api/v1)                                            │
│   jobs / queue / prompts / images / assets / engine/runtime ...  │
│  Static Hosting（include router 之后注册）                        │
│   /assets → dist/assets；SPA catch-all → dist/index.html         │
│  Lifespan：创建 EngineRuntimeService 单例（application.state）   │
└───────────────┬───────────────────────────────┬─────────────────┘
                │ SQLAlchemy                     │ HTTP 8188 / spawn+psutil
                ▼                                ▼
        ┌──────────────┐                 ┌─────────────────────────┐
        │ studio.db    │                 │ ComfyUI（managed 或 external）
        │ DataRoot     │                 │  固定端口 8188           │
        └──────────────┘                 └─────────────────────────┘
```

---

## 4. FastAPI 直接托管前端（static_hosting）

实现：`backend/app/core/static_hosting.py`，在 `create_app` 中 **include API router 之后**调用。

- `/assets` → 挂载 `dist/assets`（`StaticFiles(html=True)`）。
- `GET /` 与 SPA catch-all `GET /{full_path:path}`：非 API 客户端路由（`/generate`、`/gallery`、
  `/prompt`、`/settings` 及深层路径）返回 `dist/index.html`（200），支持前端路由与刷新。
- **API 不被吞**：catch-all 中 `full_path` 以 `api/` 开头时返回 **404 JSON**，绝不把 index.html 返回给 `/api`。
- `dist/index.html` 缺失 → 不注册任何路由（返回 False），保留开发 / 测试环境的 JSON 根路由。
- 测试：`tests/backend/test_spa_static_hosting.py`；`test_health_api.py` 兼容 dist 存在 / 缺失两种环境。

---

## 5. Engine Runtime（受管 ComfyUI 生命周期）

实现：`backend/app/services/engine_runtime_service.py`、`backend/app/api/v1/engine_runtime.py`；
前端 `components/EngineControlPopover.tsx`。**完整契约见 `ENGINE_RUNTIME_CONTRACT.md`。**

- **固定端口 8188，禁止自动换口**；Host 默认 127.0.0.1。
- **7 个 Engine Runtime State**（独立于 Job State）：
  `STOPPED / STARTING / RUNNING_MANAGED / RUNNING_EXTERNAL / STOPPING / PORT_CONFLICT / ERROR`。
- **进程归属是硬安全**：用 psutil 记录受管 PID + 命令 + 工作目录 + 启动时间；
  停止只终止该 PID 及其递归子进程树（先 terminate 等 10s，再 kill）；
  严禁 `taskkill /IM python.exe`、严禁杀 external。
- start 幂等；启动失败 / 健康超时清理自己刚起的进程树并置 ERROR（start 失败也返回 200）。
- 阻塞操作经 API 层 `asyncio.to_thread` 包装。
- 前端：Engine 指示点击弹出 Popover；停止 / 重启前若有 RUNNING Job 须弹确认，
  确认后**先暂停队列再停引擎**；external 不提供停止 / 重启。

---

## 6. Queue 手动暂停 / 继续

实现：`backend/app/workers/queue_worker.py`、`backend/app/services/job_service.py`、
`backend/app/api/v1/jobs.py`；前端 `pages/Generate/SettingsPane.tsx`。

- Worker 复用现有 Pause / Queue 语义与 `pause_requested`，**不新增 Job 状态**：
  - 公共 `pause_queue(reason="USER_REQUEST")`；记录 `_user_paused_job_id`；
  - 两个安全边界（Stage 进入前 / StageItem 执行前）在 USER_REQUEST 时把当前 Job 停在边界；
  - `resume_queue()` 返回并清空被暂停 Job id。
- `job_service.resume_job_front`：恢复时把被暂停 Job 放回**队首**（现有 QUEUED 顺延），实现“原暂停 Job 优先”。
- API：`POST /queue/pause`（设 flag + 暂停 current）、增强 `POST /queue/resume`（恢复 front Job）。
- 前端：队列标题旁“暂停队列 / 继续队列”切换（有活动时可用）。
- 测试：`tests/backend/test_queue_manual_pause.py`；`SettingsPane.queue.test.tsx`。

---

## 7. 生成配置：画幅 / 分辨率（纯前端）

实现：`frontend/src/utils/aspectRatio.ts`、`pages/Generate/AspectRatioPicker.tsx`，接入 `SettingsPane.tsx`。

- 画幅（1:1 / 3:4 / 4:5 / 9:16 / 16:9 / 5:4 / 4:3 / custom）+ 分辨率档位（标准长边 1024 / 高清长边 1920），
  结果均为 8 的倍数；高清档含 **9:16=1080×1920、16:9=1920×1080**。
- 自定义尺寸保留 **64~4096** 校验；总像素较大仅提示“生成较慢”，**不禁止**。
- `size_mode=input` 时不显示画幅 / 分辨率（跟随输入图）。
- **Job 仍只提交 width / height**；后端 schema / Recipe 不迁移、无快照。
- **模块能力判断（计划 §二十一）**：移除用 `output_kind==='processed'` 判断图片条件 Primary Module 的错误逻辑，
  新增纯函数 `isImageStartModule`，按 `available / input_required / input_slots / can_start_from_image /
  allowed_job_kinds` 判断；不把 `role=source` 写死到更多组件，优先读 `ModuleCapabilities.input_slots`。
  本轮不做完整 Reference UI。

---

## 8. 已运行计时（ElapsedTimer）

实现：`frontend/src/components/ui/ElapsedTimer.tsx`、`utils/elapsed.ts`。

- 只显示**“已运行 mm:ss”**（超 1h 为 hh:mm:ss），完成后定格；**禁止 ETA / 预计完成**。
- 计时器**每秒在组件内部自更新**，不导致整个 GeneratePage / store 每秒重渲染。
- 嵌入 CurrentJobCard（RUNNING 走表）与 ResultPane jobline。

---

## 9. 共用图片 Lightbox

实现：`frontend/src/components/ImageLightbox.tsx`（+ css），Generate 与 Gallery **共用单一组件**。

- 交互：ESC / 方向键切图 / 滚轮缩放（约 25%~400%，以中心为锚）/ 拖动平移 / Fit / 100%；切图复位。
- Gallery **单击 = Detail Drawer（220ms 延迟）、双击 = Lightbox（取消单击定时器）**，二者不冲突；
  Lightbox 打开时抑制 Gallery 自有按键。
- **打开只载当前大图、不预载全库原图**（DOM 中仅当前一张 content URL）。
- 测试：`components/__tests__/ImageLightbox.test.tsx`、`Gallery.lightbox.test.tsx`、`ResultPane.lightbox.test.tsx`。

---

## 10. 队列面板固定高度收缩

- `.wb-queue-list--scroll`：`max-height:300px; overflow-y:auto`（+ 内联双保险）；
  标题 / 暂停按钮 / 自动暂停提示固定在滚动区外。
- 拖拽（DnD）、优先、单任务暂停 / 继续 / 取消、队列暂停 / 继续全部保留。
- 测试：`SettingsPane.compact.test.tsx`。

---

## 11. Prompt 封面 / 卡片 / 复制

- 后端迁移 `0014_prompt_preview_image`（`prompts.preview_image_id`）；设置 / 清除封面**不建 PromptVersion**；
  封面引用纳入图片引用检查。**完整契约见 `PROMPT_PREVIEW_CONTRACT.md`。**
- 前端：卡片封面 lazy + 占位 + 摘要；一键复制后端合成的完整 `positive_prompt`（按钮 stopPropagation）；
  编辑 Drawer 复用 `ImagePickerDrawer` 选封面。

---

## 12. 桌面启动器

实现：`scripts/install_desktop_shortcut.ps1`（一次性安装 / 更新）、`scripts/launch_studio.ps1`、
`scripts/launch_studio.bat`。

- 安装：准备 `.venv`（装 requirements）、`npm ci`、`npm run build`，写入构建戳 `dist/.build_commit`，
  在桌面创建「NSFW Studio」快捷方式（不复制项目到桌面）。
- 启动：dist 缺失 / 构建戳 ≠ HEAD → 重新构建；探测健康，已在运行则只开浏览器，
  否则以隐藏窗口起 uvicorn 并轮询健康后打开页面。

---

## 13. 配置、数据与安全边界

- `configs/config.local.yaml`（gitignored）提供本机 DataRoot、ComfyUI 连接与（可选）受管启动信息；
  仓库仅提交 `configs/config.local.yaml.template`（`<LOCAL_ONLY ...>` 占位，无真实路径 / 密钥）。
- **禁止提交**：db、图片、模型、`config.local.yaml`、DataRoot、ComfyUI outputs、用户 Prompt 内容。
- 受管 ComfyUI 日志写 `<DataRoot>/logs/engine/comfyui-managed.log`。
- 引擎离线时 Gallery / Prompt / Assets / Settings 照常可用，仅生成受限。
- 本轮不接入 ControlHub（受管 ComfyUI 是已存在组件改为界面内按需启停；用户当前指令优先级最高），
  不新建平行控制系统。

---

## 14. 关键文件索引

| 关注点 | 位置 |
|---|---|
| 静态托管 | `backend/app/core/static_hosting.py`、`backend/app/main.py` |
| 引擎运行时 | `backend/app/services/engine_runtime_service.py`、`backend/app/api/v1/engine_runtime.py` |
| 队列暂停 | `backend/app/workers/queue_worker.py`、`backend/app/services/job_service.py`、`backend/app/api/v1/jobs.py` |
| 画幅 / 计时 | `frontend/src/utils/aspectRatio.ts`、`frontend/src/utils/elapsed.ts`、`frontend/src/components/ui/ElapsedTimer.tsx` |
| Lightbox | `frontend/src/components/ImageLightbox.tsx` |
| Prompt | `backend/app/models/prompt.py`、`backend/app/services/prompt_service.py`、`frontend/src/pages/Prompt/PromptTab.tsx` |
| 启动器 | `scripts/launch_studio.ps1`、`scripts/install_desktop_shortcut.ps1` |
| 迁移 | `backend/app/database/migrations.py`（0014） |
