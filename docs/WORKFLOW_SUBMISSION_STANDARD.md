# NSFW Studio V2 — 工作流提交标准（W0）

> 状态：正式标准（2026-10-30，W0 工作流治理收口）
> 适用范围：`workflows/providers/**` 下所有 ComfyUI（及未来其他引擎）工作流绑定。
> 本文件是工作流提交、版本、依赖、硬件验收与 Git 纪律的唯一标准；与 `AGENTS.md` 冲突时，
> 以 `AGENTS.md` 的全局/项目规则为准，并应尽快修正本文件或 `AGENTS.md`，不得两套口径并行。

## 1. 三层模型：Module / Binding / Hardware Profile

工作流必须拆成三个独立层次，不得混在一起：

| 层 | 位置 | 回答的问题 | 不允许做的事 |
| --- | --- | --- | --- |
| WorkflowModule | `backend/app/workflows/<module>.py` | 这是什么功能、输入/输出语义、用户可配置参数、Job/Stage 契约 | 不写 ComfyUI 节点 ID、模型文件名、采样参数 |
| Provider Binding | `workflows/providers/<provider>/<module>/<version>/` | 实际节点图、模型、注入位置、固定默认参数、依赖声明 | 不改 Python 模块契约；不承担硬件结论 |
| Hardware Profile | `binding.yaml` 的 `requirements` / `performance` 与 `docs/COMFY_ENV_INVENTORY.md` | 本机是否具备节点/模型、适合的分辨率、耗时与显存记录、是否通过真实 Gate | 不用磁盘文件大小冒充显存峰值；不把估算写成实测 |

`available=true` 只代表“模块已注册且 binding 文件自描述/指纹合法”，**不代表依赖齐全，
更不代表当前电脑能跑**。工作流管理必须能区分“可加载”“可执行”“已通过性能验收”。

## 2. 工作流来源与导出格式

ComfyUI 有两种 JSON：

| 格式 | 用途 | 能否直接作为 Studio 执行文件 |
| --- | --- | --- |
| 普通 Save JSON | 保存节点位置、布局、连线等编辑信息 | 否 |
| API Format JSON | 以节点 ID 为键，含 `class_type` 与 `inputs`；连接用 `[上游ID, 输出序号]` | 是 |

正式提交必须使用 **File → Export Workflow (API)** 导出的 API 格式，不能直接按 Ctrl+S。
`source.workflow.json` 可保留 UI 可编辑格式作为来源备份，但不参与 Studio 执行。

提交前必须先在真实 ComfyUI 中用真实模型与节点跑通至少一张图片；只交一份 JSON 不算完成。

## 3. 统一目录结构

```text
workflows/
└── providers/
    └── comfyui/
        └── <module_id>/
            └── <binding_version>/
                ├── workflow.json          # 必须：ComfyUI API 工作流
                ├── binding.yaml           # 必须：节点映射、参数、依赖、性能声明
                ├── README.md              # 必须：来源、图结构、注入契约、限制
                └── source.workflow.json   # 建议：UI 格式来源备份，不参与运行
```

- 目录名中的 `<binding_version>` 与 `binding.yaml` 的 `binding_version` 必须一致；
- 禁止机器绝对路径、私人提示词、模型权重、图片、日志、缓存进入该目录；
- SaveImage 前缀必须使用 Studio 身份模板：
  `NSFWStudio/{job_short}/{stage}/{item_short}`。

## 4. binding.yaml 标准

除现有字段（`binding_version` / `module` / `provider` / `workflow_file` /
`save_image_node` / `save_image_prefix` / `inputs` / `defaults` / `seed_range` /
`capabilities`）外，新提交必须增加以下两段：

```yaml
requirements:
  comfyui_min_version: "0.37.0"
  nodes:
    - class_type: KSampler
      source: comfyui_core
    - class_type: SomeCustomNode
      source: custom
      package: some-custom-node
      version: "exact-version-or-unverified"
  models:
    - type: diffusion_models
      filename: model.safetensors
      size_bytes: 0            # 官方/磁盘实际值；未知写 0 并在 performance 标注
      sha256: "unverified"     # 不得伪造
      precision: fp16

performance:
  status: unverified           # unverified / measured / failed
  batch_size: 1
  tested_hardware:
    gpu: null
    vram_gb: null
    ram_gb: null
  tested_profiles: []          # 例：{width: 768, height: 768, steps: 12, cfg: 2.5, sampler: er_sde, scheduler: beta, seconds: 0}
  known_limitations: []
```

数据来源必须明确区分：

- **实测值**：本机真实运行记录，必须写清日期、命令/任务 ID、硬件与配置；
- **官方/磁盘信息**：模型文件大小、发布说明，可作为参考但不能当显存峰值；
- **估算值**：必须标注 `estimated`，不得与实测混写；
- **未验证**：必须写 `unverified` 或 `null`，禁止填猜测数字。

`requirements` 与 `performance` 必须被现有 `binding_hash` 覆盖；未来还需增加实际依赖校验
（节点是否存在、模型是否可加载），不能只记录不检查。

## 5. Module 与 Binding 的提交边界

| 修改内容 | 正确提交方式 |
| --- | --- |
| 只改现有工作流节点结构 | 新 binding 版本（`v2/`） |
| 更换模型但输入输出语义不变 | 新 binding 版本 |
| 新增用户可配置参数 | 更新 Module 契约 + binding |
| 输入图片角色变化 | 新 Module 或正式修改 Module 契约 |
| 输出类型/父子关系变化 | 新 Module 或正式修改 Module 契约 |
| 全新功能 | 新 WorkflowModule + 新 binding |

示例：换 LoRA、换采样器不需要新模块；图生图改为参考条件生成则需要独立模块。
禁止为同一功能创建多个名称不同、语义重复的模块。

## 6. 版本与 Git 纪律

- `module_version`：Python 模块接口版本；
- `binding_version`：ComfyUI 工作流绑定版本；
- `workflow_hash = sha256(workflow.json)[:16]`；
- `binding_hash = sha256(binding.yaml)[:16]`。

一般规则：**已投入使用的 binding 目录视为 immutable**，修改 `workflow.json` 或
`binding.yaml` 必须新建 `v2/`，旧目录保留；指纹不一致时旧 Job 不可续跑。

唯一例外（2026-10-27 用户确认，方案 A 单目录）：

- `basic_generate/v1/` 是唯一目录，不新建 `v2/`；版本演进靠 Git 历史；
- 代价：旧 Job 的 `workflow_hash` / `binding_hash` 可能失效，旧任务不可续跑；
- 该例外只适用于 `basic_generate`，不得推广到其它模块；必须在本文件与 `AGENTS.md` 中同时可见。

**Legacy 兼容政策（W1）**：已冻结的 v1 binding（`basic_generate` / `img2img` /
`reference_generate` / `anime_generate` / `upscale`）允许暂时缺少 `requirements` /
`performance`，G0 只给警告；新 binding（如 `img2img/v2`）必须完整声明。
禁止为了通过 G0 而批量修改旧 binding；需要变更时新建 v2。

Git 提交建议：

```text
feat(workflow): add <module> <binding>
fix(workflow): align <module> defaults
test(workflow): validate binding dependencies
docs(workflow): update hardware inventory
```

一个提交只处理一个明确的工作流功能或修复。禁止提交：模型权重、本机 ComfyUI 配置、
私人图片/提示词、DataRoot、ComfyUI output、临时缓存、其他机器绝对路径。

## 7. 五级验收 Gate

| Gate | 检查内容 | 需要 GPU |
| --- | --- | --- |
| G0 静态检查 | API JSON 格式、节点 ID/class_type 存在、binding 映射、默认字段、SaveImage、无绝对路径/私人提示词、依赖声明完整 | 否 |
| G1 Mock 测试 | Module 输入输出、Pipeline、Job/Stage 状态，不启动 ComfyUI | 否 |
| G2 环境检查 | `GET /object_info`、`/system_stats`；ComfyUI 版本、节点、模型文件是否齐全 | 否 |
| G3 真实运行 | 单张真实出图、结果入库、Gallery 可看、Job/Stage/Seed/溯源正确 | 是 |
| G4 性能验收 | 冷启动、热启动、GPU 峰值、RAM 峰值、采样耗时、输出尺寸、OOM/崩溃/超时 | 是 |

要求：

- G0、G1 必须进入 CI 自动执行；
- G3、G4 必须本机人工执行并记录证据，不得云端模拟、不得用 Mock 冒充；
- 未通过 G3 的模块不得进入正式 UI；未通过 G4 的模块不得宣称“可日常使用/批量首选”；
- G4 记录必须与硬件档案绑定，至少包含显卡、显存、内存、实际分辨率/步数/采样器。

## 8. 运行提交纪律

工作流定义提交（开发流程）：
`ComfyUI 创作 → API JSON → binding → GitHub → 独立审查 → 合并`。

生图任务提交（运行流程）：
`工作台 / scripts/agent_generate.py → POST /api/v1/jobs → 单队列 → WorkflowModule → ComfyUI`。

正式任务只能通过 Studio 队列提交；**禁止开发 Agent 绕过队列直接调用 ComfyUI `/prompt`**
来制作正式图片（一次性诊断/烟测必须在 `temp` 中执行并明确标注，不进入正式资产）。

## 9. 状态语义（建议在下一阶段实现）

`GET /api/v1/modules` 的 `available` 不得继续被理解为“可运行”。建议增加：

| 状态 | 含义 |
| --- | --- |
| `registered` | Python 模块已注册 |
| `binding_valid` | 工作流文件、映射、指纹合法 |
| `dependencies_ready` | 节点、模型依赖齐全 |
| `hardware_status` | 当前硬件适配：ok / slow / experimental / unsupported |
| `real_gate_passed` | 已通过 G3 真实运行 |
| `ready_to_run` | 综合以上检查后可执行 |

工作流管理必须在执行前拒绝明显超出资源限制的任务（分辨率/像素数/步数），
而不是等 ComfyUI OOM 后再报错。

## 10. 现有正式模块与实验模块

正式模块（5 个）：

| 模块 | 状态 | 说明 |
| --- | --- | --- |
| `basic_generate` | 日用主力 | Turbo8 + f23gg 双 LoRA，8 步，单目录特例 |
| `img2img` | 慢速可用 | 输入尺寸需限制在已验证范围；默认 denoise 以 Python 模块 0.8 为准 |
| `reference_generate` | 低频使用 | 已验证 640/20 步单张 60+ 分钟；当前 1024/25 默认未通过对应 G4 |
| `anime_generate` | 待真实验收 | 模型文件 4.22 GB，实际显存/耗时未验证；不得宣传轻量/快速/批量首选 |
| `upscale` | 轻量优先 | 4x-UltraSharp 现役，暂不接入 SeedVR2 |

实验/下线模块：

- `pose_generate`（2026-10-29 实验）：双 LoRA + 双参考图在 6GB/16GB 机器上 OOM，
  代码保留在 `experiment/pose-generate-20261030` 分支；未通过 G3/G4 前不得注册、不得出现在正式 UI。

## 11. 禁止事项

- 禁止只提交 JSON 就宣布工作流完成；
- 禁止用 Mock/离线测试代替 G3/G4；
- 禁止把磁盘文件大小写成显存峰值；
- 禁止在正式 binding 中写机器绝对路径、私人提示词、模型权重；
- 禁止修改已投入使用的 binding 而不升版本（`basic_generate` 单目录例外除外）；
- 禁止绕过 Studio 队列直接 `/prompt` 制作正式任务；
- 禁止在未通过硬件验收时把模块标记为“日常/批量/轻量/快速”。
