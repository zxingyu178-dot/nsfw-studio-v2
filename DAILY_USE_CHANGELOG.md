# Daily Use Changelog（NSFW Studio V2 日用化变更日志）

> 分支：`feature/daily-use-ux-runtime`（worktree `projects/nsfw-studio-v2-dailyuse`）
> 基线：`d4f1821`（feature/ui-v1-phase7）。本轮结束**停在该 feature 分支，不 merge main**。

---

## 提交历史（按时间顺序）

| # | SHA | 类型 / 主题 |
|---|---|---|
| 1 | `be146e8` | chore: daily-use worktree baseline docs（Task0 基线） |
| 2 | `368a821` | feat(runtime): serve production frontend from FastAPI |
| 3 | `021c89c` | feat(runtime): managed ComfyUI start stop status（后端） |
| 4 | `15d0080` | feat(deploy): desktop shortcut launcher |
| 5 | `fefff91` | feat(queue): global safe pause |
| 6 | `ff10bce` | feat(generate): aspect ratio and resolution presets |
| 7 | `d5a25f3` | feat(generate): elapsed timers |
| 8 | `a17ccf7` | feat(gallery): shared image lightbox with zoom pan |
| 9 | `3c7669f` | feat(queue): compact queue panel with fixed height |
| 10 | `d070e6f` | feat(prompt): preview image metadata with reference guard |
| 11 | `c57c9f8` | feat(prompt): card cover thumbnails and one click copy |
| 12 | `fc0b55f` | feat(engine): in app runtime control popover（补齐计划 Task4 UI） |
| 13 | （收口） | test/docs: daily-use acceptance and handoff（含句柄修复） |

> 说明：计划列出 12 个功能/收口提交节奏。实施中在独立验证阶段发现**计划 Task4「界面内置生图引擎
> 控制」的前端 UI 缺失**（commit 3 仅交付后端），为保证功能完整，新增 commit 12 `fc0b55f` 专门
> 交付该 Popover；原计划的“test/docs 收口”相应顺延为最后一个提交。该偏差为补全遗漏功能，
> 已在验收报告中如实说明。

---

## 新增功能

### Runtime / 部署
- **FastAPI 直接托管前端**：`/assets` 静态 + SPA catch-all 返回 `index.html`；`/api/*` 未匹配返回
  404 JSON 不被吞；dist 缺失时保留开发模式 JSON 根路由。
- **桌面启动器**：一键安装（venv / npm ci / build / 构建戳 / 桌面快捷方式）与日常启动
  （过期重建、健康探测、隐藏窗口起 uvicorn、自动开浏览器）。
- **受管 ComfyUI 运行时（后端）**：固定端口 8188、7 个独立 Runtime State、psutil 精确进程归属、
  start 幂等、失败清理进程树。
- **界面内引擎控制 Popover（前端）**：启停 / 重启、状态轮询；停止前有 RUNNING Job 须确认、
  确认后先暂停队列再停引擎；external 不提供停止 / 重启。

### Queue
- **一键暂停 / 继续整个队列**：复用 Pause 语义、不新增 Job 状态；当前图在安全边界停住、后续不开始；
  继续时原暂停 Job 回到队首优先。
- **队列面板固定高度收缩**：max-height 300、内部滚动；DnD 与全部任务操作保留。

### Generate
- **画幅 / 分辨率预设**：8 种画幅 + 标准 / 高清档位（含 1080×1920、1920×1080），自定义 64~4096，
  慢尺寸只提示不禁止，`size_mode=input` 跟随输入图；Job 仍只提交 width/height，后端不迁移。
- **模块能力判断（§21）**：移除 `output_kind==='processed'` 的错误 Primary 判断，
  改按 available / input_required / input_slots / can_start_from_image / allowed_job_kinds 能力判断。
- **已运行计时**：只显示已运行时长（无 ETA），计时器组件内部每秒自更新、不重渲染整页。

### Gallery / Prompt
- **共用图片 Lightbox**：Generate 与 Gallery 单一组件，ESC / 方向键 / 滚轮缩放（25%~400%）/
  拖动平移 / Fit / 100%；Gallery 单击 Drawer、双击 Lightbox；只载当前、不预载全库。
- **Prompt 封面预览**：`preview_image_id` 元数据（迁移 0014），换封面不建版本，纳入图片引用检查。
- **Prompt 卡片**：lazy 封面 + 摘要；一键复制后端合成完整 positive_prompt，按钮 stopPropagation。

---

## 缺陷修复

- **受管启动句柄泄漏**：`engine_runtime_service._spawn` 中 Popen 把日志句柄继承给子进程后，
  父进程（Studio）立即关闭自己持有的副本，避免每次受管 start 泄漏一个 OS 文件句柄。
- **新建 Prompt 后列表不刷新**：`PromptEditorDrawer.run()` 仅在编辑既有 Prompt 时经
  `refreshDetail → onChanged` 刷新外层列表；新建（`prompt=null`）路径漏调 `onChanged`，
  导致新卡片需手动刷新页面才出现。已在新建成功后补调 `onChanged()`，新卡片即时出现，
  并新增 1 条前端测试守护（vitest 共 121）。

---

## 依赖与配置

- 新增 Python 依赖 **psutil（>=5.9）**：按 PID + 递归子进程树精确归属与终止，避免
  `taskkill /IM python.exe` 误杀；理由已记录在服务模块 docstring。
- 新增 `configs/config.local.yaml.template`（`<LOCAL_ONLY ...>` 占位，无真实路径 / 密钥）；
  `config.local.yaml` 保持 gitignored。

---

## 测试

- 后端确定性套件：基线 254 → 收口 **280 passed**（真实生图 `test_comfyui_integration.py` 按约定 ignore）。
- 前端 vitest：基线 44 → 收口 **121 passed**；`typecheck` 与 `build` 全绿。
- 真实浏览器 E2E：见 `docs/DAILY_USE_ACCEPTANCE.md`（含未执行 / 部分验证项的如实标注）。

---

## 明确不做（本轮范围外）

升级 ComfyUI、装 custom node、下模型、改 Anime 工作流、新增 AI 模块、重写 QueueWorker /
Job 状态机、改 Seed / Stage-aware Resume、自动换端口、完整 Reference UI、ControlHub 接管、merge main。
