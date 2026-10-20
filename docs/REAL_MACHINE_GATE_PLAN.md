# 真实机器验收计划（Gate A–F）

> 状态：**待执行**（2026-10-20 编写）。代码基线 v0.25.0（main = develop = `2750fb2`），
> 部署实例 `projects/nsfw-studio-v2-app` 已同步。
>
> 目的：在真实 ComfyUI + 真实模型环境下验证生成主链路、进度、恢复与显示，
> 补上"本地/CI 只能验证到单元与构建"的最后一环。

## 1. 环境审计（2026-10-20 只读检查结果）

| 检查项 | 结果 |
|---|---|
| ComfyUI 项目目录 | 存在：`projects/comfyui/app` |
| 模型 | checkpoints 2 个；loras 10 个；custom_nodes 10 个 |
| DataRoot | 存在：`D:/NSFW-Studio-Data`（database/images/logs 等） |
| 磁盘 | D: 剩余约 117 GB / 1863 GB |
| 本机配置 | `configs/config.local.yaml` 已配置 comfyui url `127.0.0.1:8188`、output/input 目录 |
| ControlHub | 已安装：`D:\control-hub`（含 `lifecycle_cli`、`.venv`、安装版 exe） |
| ControlHub 运行态 | 未运行（无进程、未监听） |
| ComfyUI 8188 | 未运行 |
| Studio 8000 | 未运行 |
| AIHome binding | `controlhub/integration/bindings.json` 记录 nsfw-studio-v2 已 connected（2026-10-20 核对） |

> 结论：环境齐备，**只差启动服务**。启动属于长期运行对象生命周期操作，
> 必须由用户授权后通过 ControlHub 官方 lifecycle CLI 执行（AGENTS §5 / §8.1）。

## 2. 启动顺序（获得授权后执行）

```powershell
# 1) 启动 ControlHub 平台（若未运行；按 ControlHub 自身文档启动）
#    D:\control-hub\dist\AIHomeControlHub\AIHomeControlHub.exe

# 2) 启动 ComfyUI（ControlHub 生命周期，唯一合法入口）
D:\control-hub\.venv\Scripts\python.exe -m control_hub.lifecycle_cli start comfyui `
  --data-root C:\Users\30566\AppData\Local\AIHomeControlHub\data

# 3) 启动 Studio（ControlHub 生命周期）
D:\control-hub\.venv\Scripts\python.exe -m control_hub.lifecycle_cli start nsfw-studio-v2 `
  --data-root C:\Users\30566\AppData\Local\AIHomeControlHub\data

# 4) 健康检查
curl http://127.0.0.1:8000/api/v1/health      # {"status":"ok","version":"0.25.0"}
curl http://127.0.0.1:8188/system_stats       # ComfyUI 就绪
```

验收结束后按相反顺序 `stop`，**不得**用 `Stop-Process` 之类的旁路方式控制这两个对象。

## 3. Gate 用例与通过标准

### Gate A｜文生图基础链路
- 模块 `basic_generate`，1024×1024，数量 1，固定 Seed。
- 通过标准：Job 状态 RUNNING→COMPLETED；Stage/Step 进度在 TaskDock 与 SSE 中递增；
  图片入库 DataRoot、图库可见、缩略图可加载；图片详情字段（尺寸/Seed/模块/Job）正确。
- 证据：任务 ID、进度截图、图库截图、`images` API 响应片段。

### Gate B｜动漫生图（Anima）
- 模块 `anime_generate`，832×1216。
- 通过标准：与 A 相同 + 确认走的是 anime binding（图片详情"来源"显示 `anime_generate`）。

### Gate C｜图生图
- 模块 `img2img`，输入图取 Gate A 产物，denoise 0.8，seed 固定。
- 通过标准：Job 冻结输入图快照；输出图 `parent_image_id` 指向输入图；图库详情显示派生关系。

### Gate D｜高清放大
- 模块 `upscale`，输入 Gate A 产物，2x/4x 各一次。
- 通过标准：新图 `kind=upscaled`、尺寸按倍率；图库/详情显示 HD 徽标；父子关系正确；
  放大链路在 Stage 进度中可见。

### Gate E｜参考图生成
- 模块 `reference_generate`，参考图取 Gate A 产物（或已上传素材）。
- 通过标准：`input_role=reference` 校验通过；输出图正常入库；不接受错误角色输入（Gate 提示）。

### Gate F｜恢复与大图显示
- 阶段 F1：构建 A→B→C 三阶段 Pipeline，执行中途停止 Studio，再启动并 Resume。
  通过标准：原 Stage/Binding 完整继承（不静默升级），从断点继续并最终 COMPLETED。
- 阶段 F2：生成 >1536 长边图片（如 2048×1152），Canvas 在 Fit / 100% 模式下显示正确，
  不拉伸、不溢出；记录渲染耗时。
- 证据：Resume 前后 job 快照、Stage 状态截图、Canvas 显示截图。

## 4. 验收记录模板

每条 Gate 记录：

```
Gate: A
时间: 2026-10-20 HH:MM
Job / Stage ID:
输入参数:
预期:
实际:
结论: PASS / FAIL
证据: 截图路径 / API 片段 / 日志路径
```

验收结果写入 `docs/evidence/`（图片不入库，按现有 .gitignore 规则）或交接材料。

## 5. 风险与回滚

- 启动/停止只走 ControlHub lifecycle CLI；异常时优先 `stop`，不改 DataRoot 数据。
- DataRoot 不做清理；如需重跑，用新 Job 而非删除历史。
- 若 ComfyUI 启动超时（清单含 420s 启动等待），先看
  `projects/comfyui/runtime/logs/comfyui.log` 与 `carrier.log`。
- Studio 启动后若 8188 离线，前端顶部会显示引擎离线；以 `/api/v1/engine/status` 为准。
