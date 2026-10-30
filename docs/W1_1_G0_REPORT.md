# G0 完整检查报告（W1.1-4）

> 工具：`scripts/validate_workflows.py`；执行日期：2026-10-30。
> 方式：静态读取 `workflows/providers/<provider>/<module>/<binding>/`，不启动 ComfyUI、
> 不使用 GPU、不下载模型、不读取 DataRoot 图片。

## 1. 检查项与实现

| # | 检查 | 实现 | 阻断级别 |
| --- | --- | --- | --- |
| 1 | 精确核心节点类型 | `CORE_NODE_TYPES` 精确集合（不再用 `startswith` 白名单） | 新 binding 报错；legacy 未声明仅警告 |
| 2 | `requirements.nodes` 与实际节点对应 | 声明节点必须存在；出现但未声明的非核心节点报错 | 新 binding 报错 |
| 3 | `requirements.models` 与 Loader 文件名双向对应 | `MODEL_FIELDS` 提取实际模型文件名，缺失/多余都报错 | 新 binding 报错 |
| 4 | 必要标准输入映射 | `REQUIRED_INPUTS[module_id]` 检查 positive/negative/width/height/seed 等 | 报错 |
| 5 | SaveImage 图像输入连接 | `save_image_node` 必须是 `SaveImage`，`images` 必须是存在的节点连接 | 报错 |
| 6 | 节点输出索引合法 | 节点存在、索引非负、不超出 `NODE_OUTPUT_COUNTS` | 报错 |
| 7 | 内嵌私人 Prompt | 对 workflow 节点 `prompt/text/negative_prompt` 非空值检查 | 新 binding 报错；legacy 警告 |
| 8 | Git 跟踪权重文件 | `git ls-files` + 权重后缀，`ALLOWED_TRACKED_WEIGHTS` 为空例外 | 报错 |
| 9 | `performance.tested_profiles` 证据字段 | width/height/steps/cfg/sampler/scheduler/batch_size + sampling_seconds；batch_size 必须 1 | 报错 |
| 10 | 其他结构检查 | 目录层级、binding 身份、注入点、defaults、seed_range、绝对路径、禁止文件 | 报错 |

保留的 legacy 兼容政策：

- `LEGACY_BINDINGS`（5 个冻结 v1）：缺 `requirements` / `performance` 只警告；结构错误仍阻断；
- 不批量修改冻结 v1 的 `workflow.json` / `binding.yaml`，不为减少 warning 改旧指纹；
- 新 binding 执行为完整规范。

## 2. 当前全量结果

```text
[WARN] anime_generate/v1: legacy binding 未声明 requirements（允许，按兼容政策）
[WARN] anime_generate/v1: legacy binding 未声明 performance（允许，按兼容政策）
[WARN] anime_generate/v1: 节点 6.text 含内置 Prompt（可能泄漏私人内容）
[WARN] basic_generate/v1: legacy binding 未声明 requirements（允许，按兼容政策）
[WARN] basic_generate/v1: legacy binding 未声明 performance（允许，按兼容政策）
[WARN] basic_generate/v1: 节点 1 的 class_type UnetLoaderGGUF 未在 requirements.nodes 声明
[WARN] img2img/v1: legacy binding 未声明 requirements（允许，按兼容政策）
[WARN] img2img/v1: legacy binding 未声明 performance（允许，按兼容政策）
[WARN] img2img/v1: 节点 1 的 class_type UnetLoaderGGUF 未在 requirements.nodes 声明
[WARN] reference_generate/v1: legacy binding 未声明 requirements（允许，按兼容政策）
[WARN] reference_generate/v1: legacy binding 未声明 performance（允许，按兼容政策）
[WARN] reference_generate/v1: 节点 1 的 class_type UnetLoaderGGUF 未在 requirements.nodes 声明
[WARN] upscale/v1: legacy binding 未声明 requirements（允许，按兼容政策）
[WARN] upscale/v1: legacy binding 未声明 performance（允许，按兼容政策）
[G0] checked=6 errors=0 warnings=14
```

- `checked=6`：`basic_generate/v1`、`img2img/v1`、`img2img/v2`、`reference_generate/v1`、
  `anime_generate/v1`、`upscale/v1`。
- `img2img/v2` 是唯一新 binding，已完整声明 requirements/performance，无 error/warning
  涉及它本身（其节点类型与 v1 相同，核心节点在白名单内）。

## 3. 负向测试（每类错误都必须被发现）

`tests/backend/test_validate_workflows_w11.py`：

| 用例 | 期望 |
| --- | --- |
| 合法新 binding | `errors=0`，exit 0 |
| `KSamplerFake` | 不被 startswith 白名单误放行，报“未在 requirements.nodes 声明” |
| SaveImage 连接不存在节点 | 报“SaveImage.images 引用了不存在的节点” |
| 输出索引 5 超出 TextEncodeQwenImage21 的 3 个输出 | 报“输出索引 5 超出” |
| 缺少标准输入映射（seed） | 报“缺少标准输入映射” |
| requirements.models 缺少实际模型 | 报“未在 requirements.models 声明” |
| 新 binding 内嵌私人 Prompt | 报“含内置 Prompt” |
| tested_profile 缺 batch_size | 报“tested_profile 缺少 batch_size” |
| Git 跟踪 `.safetensors` | 报“Git 跟踪了模型权重文件” |

结果：9 个用例全部通过（本次运行 17 passed 含正向用例）。

## 4. CI 阻断

`.github/workflows/ci.yml` 的后端 job 已包含 G0 步骤：

```yaml
- name: G0 workflow static validation
  run: python scripts/validate_workflows.py
```

脚本在有 error 时 `exit 1`，任何 binding 错误或 Git 跟踪权重都会使 CI 失败，
从而阻止提交进入 main。

## 5. 已知边界

- 未知自定义节点的输出数量无法推断时跳过索引上限（仍校验节点存在与非负）；
- `UnetLoaderGGUF` 属于已安装自定义节点，legacy 未声明仅警告；
- 不检查模型文件是否实际存在（避免读取机器路径），该职责属于 W2 的运行时依赖探测；
- 不修改任何冻结 v1 文件。
