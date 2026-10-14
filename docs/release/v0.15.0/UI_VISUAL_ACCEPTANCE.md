# UI_VISUAL_ACCEPTANCE — v0.15.0（Task 20）

> 验收方式：Aha Browser 对本机实时服务 **http://127.0.0.1:8000**（后端静态托管本次
> 新构建 `frontend/dist`）通过 CDP `Emulation.setDeviceMetricsOverride` 逐分辨率截图。
> 日期：2026-10-14。截图存于本目录 `screenshots/`（16 张）。

## 1. 总体结论

| 指导 §29 成功标准 | 结论 |
|---|---|
| Canvas 是最大视觉区域 | ✅ 中栏宽于左右栏，深色哑光突出图片 |
| 一眼看全整个工作台 | ✅ 三栏 + 顶部 WorkbenchBar + 底部 TaskDock 一屏呈现 |
| Prompt 8 栏结构一眼可见 | ✅ 左栏风格/人脸/服饰/动作/场景/镜头/光线/额外（结构化槽位） |
| 页面本体零纵向滚动 | ✅ 仅左/右栏内部滚动，document 无纵向滚动（见 `GenerateNoDocumentScroll` 测试） |
| 宽屏不显示 Workspace Tabs | ✅（特异性修复后，commit `c30d321`） |
| 窄屏 Tabs 切换一次一个 pane | ✅ 900 宽显示 Prompt/预览/配置 |
| Canvas 两主题恒定深色哑光 | ✅ 新增 `--canvas-stage-bg`，Light 下舞台仍深色、空态浅字 |
| Queue 不挤右栏 | ✅ 迁至底部 TaskDock |
| 毛玻璃统一但不滥用 | ✅ 仅顶栏/容器，Canvas 不 blur |
| Power 弹层 | ✅ 生图引擎状态 + Studio 后台 + 停止全部后台 |
| 图片生成（图生图）模式 | ✅ 输入图片槽位（0/1）+ 从图库选择/上传，尺寸跟随输入 |
| TaskDrawer 展开 | ✅ 当前任务 / 队列两列，空态“暂无等待任务” |
| Prompt 库每条有预览区 | ✅ 无图固定 16:9“暂未生成” |

## 2. 截图清单（Dark）

| 文件 | 分辨率 | 场景 |
|---|---|---|
| `screenshots/dark_1024x600.png` | 1024×600 | 三档断点·中（固定 280/270，手柄隐藏） |
| `screenshots/dark_1100x650.png` | 1100×651 | 中档边界 |
| `screenshots/dark_1280x720.png` | 1280×720 | Empty Generate（Canvas First，Tabs 已隐藏） |
| `screenshots/dark_1366x768.png` | 1366×768 | 常见笔记本 |
| `screenshots/dark_1440x900.png` | 1440×900 | 桌面 |
| `screenshots/dark_1920x1080.png` | 1920×1080* | 宽屏（CDP 截图实际渲染 1800×1013） |
| `screenshots/dark_900x700_narrow.png` | 900×700 | <1024 Workspace Tabs（Prompt pane） |
| `screenshots/dark_900x700_narrow_settings.png` | 900×700 | 窄屏“配置”Tab |
| `screenshots/dark_1280x720_image_mode.png` | 1280×720 | **Image mode（图生图）** |
| `screenshots/dark_1280x720_power_popover.png` | 1280×720 | **Power popover** |
| `screenshots/dark_1280x720_taskdrawer.png` | 1280×720 | **TaskDrawer open** |
| `screenshots/dark_1280x720_prompt_library.png` | 1280×720 | **Prompt library without preview**（暂未生成） |

## 3. 截图清单（Light）

| 文件 | 分辨率 | 场景 |
|---|---|---|
| `screenshots/light_1024x600.png` | 1024×600 | 浅色面板 + **深色 Canvas** |
| `screenshots/light_1280x720.png` | 1280×720 | 浅色面板 + **深色 Canvas**（空态浅字） |
| `screenshots/light_1440x900.png` | 1440×900 | 浅色面板 + 深色 Canvas |
| `screenshots/light_1280x720_prompt_library.png` | 1280×720 | Prompt 库浅色 |

## 4. 验收中发现并修复的真实视觉缺陷

1. **宽屏多出一行 Workspace Tabs**：Tabs 根类同时带 `ds-tabs`（`.ds-tabs{display:flex}`）
   与 `generate__tabs`（`.generate__tabs{display:none}`），同特异性下按打包顺序
   `.ds-tabs` 胜出。修复为 `.generate .generate__tabs`（特异性 0,2,0），媒体块同步，
   并更新 `GenerateCompactDesktop.test.ts` 断言。已 rebuild + 刷新确认。
2. **Light 主题 Canvas 变浅**：`--canvas-bg` 是主题相关变量，浅色主题下舞台为 `#e9edf4`，
   不符合“Canvas 本体保持深色哑光”。新增主题无关 `--canvas-stage-bg/fg/border`，
   `.wb4-stage` / `.canvas-viewport__stage` 恒定深色，空态透明底浅字。已 rebuild + 截图确认。

## 5. 部分验证（受环境限制，如实标注）

以下指导要求的场景依赖 ComfyUI 真实出图，当前 **ComfyUI(8188) STOPPED / ControlHub offline**，
未擅自启动 GPU 服务，因此**未取得真机截图**：

- **Running Generate**（进行中 HUD 真机）：HUD 渲染逻辑由 `workbenchProgress.test.ts`、
  `ProgressHUD` 组件与后端 5 个契约测试确定性覆盖。
- **Completed Generate**（完成图、filmstrip、Canvas 拖拽/缩放真机）：CanvasViewport
  交互由 `CanvasViewport.test.tsx`（ResizeObserver fit、滚轮锚点缩放、拖拽、钳制）覆盖。
- **Prompt library with preview**（有真实预览图的卡片）：预览渲染、点预览放大、
  错误图隐藏由 `PromptTab.cover.test.tsx` 6 用例覆盖；当前库内仅 1 条无图 Prompt。

> 结论：**静态布局/响应式/双主题/任务坞/电源弹层/图生图/Prompt 库空态已实测通过**；
> 出图相关动态态为“部分验证（单元/契约覆盖，真机未执行）”。
