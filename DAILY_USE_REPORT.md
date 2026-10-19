# Daily Use 阶段完成报告

## 1. 基线
branch: `feature/daily-use-ux-runtime`（worktree `projects/nsfw-studio-v2-dailyuse`）
base commit: `d4f1821855064168d29300ad305e8a14ff20065b`（feature/ui-v1-phase7）
final commit: `f6fad0d36599e17e6d2dce4ae63845ebec3fbd97`（代码/测试/文档收口；报告本体由随后 docs 提交加入，无代码改动）

## 2. 完成功能
- 桌面启动：✅ 新增 `scripts/install_desktop_shortcut.ps1`（venv/npm ci/build/构建戳/桌面快捷方式）、`launch_studio.ps1`（过期重建、健康探测、隐藏窗口起 uvicorn、自开浏览器）、`launch_studio.bat` 薄封装。
- FastAPI 托管前端：✅ 新增 `backend/app/core/static_hosting.py`，include API router 后挂载 `frontend/dist`（`/assets` 静态 + SPA catch-all 返回 index.html）；`/api/*` 未匹配返回 404 JSON 不被吞；dist 缺失保留开发模式 JSON 根路由。
- ComfyUI 启停：✅ 后端受管 start/stop/restart/status（固定 8188、7 个独立 Runtime State、psutil 精确进程归属、start 幂等、失败清理进程树）；前端界面内 `EngineControlPopover`（停止/重启前有 RUNNING Job 须确认、确认后先 pause 队列再停引擎；external 不提供停止/重启）。
- Queue Pause：✅ 一键暂停/继续整个队列，复用 Pause 语义、不新增 Job 状态；当前图在安全边界停住、后续不开始；继续时原暂停 Job 回队首优先。
- 画幅：✅ 8 种画幅（1:1/3:4/4:5/9:16/16:9/5:4/4:3/custom），`size_mode=input` 跟随输入图不显示控件。
- 分辨率：✅ 标准/高清档位（高清含 1080×1920、1920×1080），自定义 64~4096，慢尺寸只提示不禁止；Job 仍只提交 width/height，后端 schema/Recipe 不迁移。
- 生成计时：✅ 只显示“已运行 mm:ss”（无 ETA），ElapsedTimer 组件内部每秒自更新、不重渲染整页。
- Lightbox：✅ Generate 与 Gallery 共用单一 `components/ImageLightbox`（ESC/方向键/滚轮缩放 25%~400%/拖动平移/Fit/100%），Gallery 单击 Drawer、双击 Lightbox，只载当前、不预载全库。
- Prompt 预览：✅ `preview_image_id` 元数据（迁移 0014），换封面不建版本，纳入图片引用检查；卡片 lazy 封面。
- Prompt 复制：✅ 一键复制后端合成完整 `positive_prompt`（非 UI 摘要），按钮 stopPropagation 不打开 Drawer。

## 3. Backend
新增 API：
- `GET /api/v1/engine/runtime`；`POST /api/v1/engine/runtime/start|stop|restart`。
- `POST /api/v1/queue/pause`；增强 `POST /api/v1/queue/resume`（原暂停 Job 回队首）。
Migration：自研极简框架追加 `0014_prompt_preview_image`（`prompts.preview_image_id`）——本轮唯一新增迁移。
服务：
- 新增 `services/engine_runtime_service.py`（受管进程生命周期 + psutil 进程树归属）。
- `services/prompt_service.py` 增 `set_preview_image/clear_preview_image`（不建 PromptVersion）。
- `services/image_reference_service.py` 增 `prompt_preview` 引用分类（计入 references/total）。
- `services/job_service.py` 增 `resume_job_front`（暂停 Job 恢复到队首、其余顺延）。
Queue 语义变化：
- `queue_worker.py` 新增公共 `pause_queue(reason="USER_REQUEST")`、`_user_paused_job_id`；两个安全边界（Stage 进入前 / StageItem 执行前）在 USER_REQUEST 时记录被暂停 Job；`resume_queue()` 返回并清空该 id。**未新增任何 Job 状态**，Engine Runtime State 与 Job State 严格分离。

## 4. Frontend
新增组件：
- `components/EngineControlPopover.tsx`（+css）、`components/ImageLightbox.tsx`（+css）、`components/ui/ElapsedTimer.tsx`、`pages/Generate/AspectRatioPicker.tsx`、`utils/aspectRatio.ts`、`utils/elapsed.ts`。
修改页面：
- `components/EngineStatus.tsx`（Engine 指示改 button 触发 Popover）。
- `pages/Generate/SettingsPane.tsx`（画幅/分辨率控件、队列暂停按钮）、`pages/Generate/ResultPane.tsx`（计时 + Lightbox）、`pages/Gallery/GalleryPage.tsx`（单击/双击区分 + Lightbox）、`pages/Prompt/PromptTab.tsx`（卡片封面/复制/抽屉封面 + 新建后列表刷新）。
- `api/client.ts`、`types/workbench.ts`、`stores/jobStore.ts`、`stores/workbenchStore.ts`（§21 能力判断）。

## 5. 测试
Backend: **280 passed**（`--ignore=test_comfyui_integration.py`，全量约 120s；基线 254）。新增 `test_engine_runtime_service.py / test_engine_runtime_api.py / test_queue_manual_pause.py / test_prompt_preview_image.py / test_spa_static_hosting.py`。
Frontend: **121 passed / 18 files**（基线 44，原有 UI/store 测试无删除）。
Typecheck: ✅ `tsc --noEmit` 零错误。
Build: ✅ tsc + vite build 通过，dist 已含最终修复。

## 6. 真实验收
1024×1024: ✅ 真实出图 `img_ba62542d`；计时器每秒走表（00:01→00:02、无 ETA）；入 Gallery。
1080×1920: ✅ UI 显示 1080×1920、有“较慢”提示、无校验错误、真实出图 `img_d726ad31`。注：ComfyUI 图内把宽 1080 舍入为 1088（输出 1088×1920），前端提交 1080、后端不转换、不改工作流。
Queue Pause: ✅ 暂停后当前 item 跑完、Job 边界 PAUSED 1/2（等待 164s）、无 RUNNING、B/C 保持排队；resume 后原暂停 Job A 最先恢复。队列 20+ 固定高度 300、内部滚动、20 行可拖拽。
Engine Stop/Start: 🧪 受管进程树 stop/再启动由确定性测试覆盖（external 8188 禁杀、8000 被占，未真机）；✅ 引擎离线时网页与图库/Prompt/素材/设置仍可用、仅生成受限（第二后端 8002 真机）。
Viewer: ✅ Gallery Lightbox 真机全功能（缩放 2.488/Fit/100%/拖动 translate(130,90)/方向键 1/4→2/4/ESC/只载当前）；Generate 双击触发由 `ResultPane.lightbox.test.tsx` 覆盖（共用组件已真机验证）。
Prompt: ✅ 卡片封面 lazy、摘要在图下、设封面不建版本（1→1）、一键复制内容等于后端合成 positive、复制不打开 Drawer。
视觉：✅ 1280×720 / 1440×900 / 1920×1080 Dark 全测，Light 1440×900 目检无错位/对比度问题。

## 7. 未完成
- 受管 ComfyUI 真机启停 / 进程树退出 / 8188 离线后再启动恢复：未真机（需用户停止外部 ComfyUI pid 172356 释放 8188），已由 monkeypatch 测试覆盖。
- 桌面双击冷启动 + 8000 直出：未真机（8000 被主仓库 uvicorn pid 144256 占用），启动脚本通过语法/只读逻辑自检；“FastAPI 直出不依赖 4173”已在 8001 真机证明。
- 端口冲突真机（不跳 8189）：未真机（需在 8188 放非 ComfyUI 服务且不破坏外部实例），由测试覆盖。
- Generate ResultPane 双击 Lightbox 真机：未真机（ResultPane 仅跟踪本会话 Job，需再真实出图，每张 12–17 分钟），由集成测试覆盖。
- 本轮未 merge main（计划要求停在 feature 分支等待审查）。

## 8. 风险
- 真机单张出图慢（RTX 3060 6GB + 桌面高负载，模型空闲卸载后每张 12–17 分钟）；这是环境吞吐问题，非功能缺陷；UI 已对大像素尺寸做“较慢”提示。
- ComfyUI 图内对非 64 倍数宽度做舍入（1080→1088），可能与用户预期的精确像素略有出入；本轮红线禁止改工作流，已如实记录，建议后续在前端提示或工作流层统一。
- 受管启停的真机安全边界（进程树精确终止）目前仅由测试验证，首次真机使用时建议用户目检任务管理器确认只终止 Studio 自己启动的进程。
- 未提交任何 db / 图片 / 模型 / config.local.yaml / DataRoot；交接包已剔除全部禁用内容。

## 9. Git
status: ✅ `git status` clean（受保护主工作树 feature/ui-v1-phase7 的 12 处未提交 Anime 实验改动全程未受影响）
commit: `f6fad0d36599e17e6d2dce4ae63845ebec3fbd97`（收口）；已 push 并经 `git ls-remote` 比对本地与远端一致
branch: `feature/daily-use-ux-runtime`（未 merge main，等待审查）
