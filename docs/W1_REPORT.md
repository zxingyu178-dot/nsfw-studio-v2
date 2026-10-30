# W1 完成报告：工作流治理与自动验收

> 日期：2026-10-30。基线 `0c581c8`。本阶段不新增模型、不下载模型、不安装节点、不执行 GPU 工作流。

## 1. 完成内容

| 任务 | 状态 | 结果 |
| --- | --- | --- |
| W1-0 img2img 版本完整性 | 完成 | 只读审计 13 个历史 Stage；恢复 v1；新建 v2（0.8）；新任务默认 v2；历史身份不变 |
| W1-1 正式放行机制 | 完成 | `workflows/release_manifest.yaml` + `release_status`；前端按 `ready_to_run` 选择，anime 隐藏 |
| W1-2 G0 静态校验器 | 完成 | `scripts/validate_workflows.py`；CI 接入；6 个 binding / 0 errors / 13 legacy warnings |
| W1-3 文档与归档核实 | 完成 | Pose 分支仅本地；Anima 双路径记录；Turbo8 性能状态；Inventory/技术债更新 |

## 2. 放行状态设计

- 状态按 `module_id + binding_version` 计算，不固化到模块全局；
- `available` 保留兼容语义（binding 可加载）；
- 新增 `release_status`：
  `registered` / `binding_valid` / `dependencies_ready` / `real_gate_passed` /
  `hardware_status` / `default_profile_verified` / `ready_to_run` / `notes`；
- 未登记的 binding fail-closed（`ready_to_run=false`）；
- 前端正式选择使用 `ready_to_run`，不再只看 `available`；慢速/未验证配置显示提示但不隐藏。

当前状态：

| Module | Binding | ready_to_run | hardware | 说明 |
| --- | --- | --- | --- | --- |
| basic_generate | v1 | true | normal | 主力；G4 峰值待补 |
| img2img | v1 | true | slow | 冻结，历史 Job |
| img2img | v2 | true | slow | 新任务默认；0.8 |
| reference_generate | v1 | true | slow | 低频；1024/25 默认未验证 |
| anime_generate | v1 | **false** | experimental | G3 未通过，正常列表隐藏 |
| upscale | v1 | true | normal | G4 待补 |

## 3. G0 检查器

- 遍历 `workflows/providers/**`；
- 检查身份、节点引用、binding 注入点、defaults、SaveImage、Seed、绝对路径、禁止文件；
- 新 binding 必须声明 `requirements` / `performance`；legacy v1 缺声明只警告；
- 当前结果：`checked=6 errors=0 warnings=13`（警告均为 legacy 缺声明与 `UnetLoaderGGUF` 未声明）；
- CI 后端 job 增加 `python scripts/validate_workflows.py`，失败阻断。

## 4. 测试与构建

- 后端定向（W1 相关）：52 passed。
- 前端：typecheck 通过；96 test files / 462 tests passed。
- 前端构建：通过（`vite build`）。
- G0：0 errors。
- 未运行全量后端 pytest（本阶段按指令只跑定向，最终以 GitHub CI 为准）；未启动 GPU。

## 5. 文档修正

- `docs/W1_IMG2IMG_VERSION_AUDIT.md`（新增）
- `workflows/release_manifest.yaml`（新增）
- `docs/COMFY_ENV_INVENTORY.md`（Anima 双路径、LoRA、节点）
- `docs/WORKFLOW_INVENTORY.md`（5 模块 + img2img v1/v2 + 放行状态）
- `docs/WORKFLOW_TECH_DEBT.md`（W1 已解决项、pose 分支仅本地）
- `docs/WORKFLOW_SUBMISSION_STANDARD.md`（legacy 兼容政策）
- `docs/AI_IMAGE_GENERATION_GUIDE.md`（anime 不再宣传轻量/快速）
- `CHANGELOG.md` / `DEV_LOG.md` / `TASKS.md`

## 6. 归档与路径核实

- `experiment/pose-generate-20261030` **只存在本地**，未推送远端；按指令不擅自推送。
- Anima 主模型在 `C:/ComfyUI_models/diffusion_models` 与 `app/models/diffusion_models` 各有一份；
  binding 注释为历史记录，实际加载以 ComfyUI folder_paths 顺序为准，环境清单已记录两处。
- basic_generate Turbo8 双 LoRA 已有真实日用运行，但本轮未补 G4 峰值；manifest 标记
  `default_profile_verified=false`，不得宣称已验证性能。

## 7. Git

- 基线：`0c581c8`
- 本轮提交：见 `git log -1`（W1 工作流治理）
- 工作区：提交后 clean（用户既有未跟踪文档除外）
- 推送：`origin/main`

## 8. 未完成 / 下一阶段

- W2：依赖实际探测、硬件 Preflight、图片总像素限制、4096 宽高预算；
- W3：五个模块真实 G3/G4 重测；
- ComfyUI 冷启动超过载体 420 秒属 ControlHub 生命周期维护，不混入 W1。
