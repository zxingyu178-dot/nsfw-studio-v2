# COMFY_ADAPTER — ComfyUIAdapter 设计与契约（Phase 2B / 2.1 / 2.2 / 3 / 4，v0.5.0）

> 更新：2026-10-08。实现：`backend/app/engine/comfyui.py`。
> 环境事实见 docs/COMFY_ENV_INVENTORY.md；工作流选型见 docs/WORKFLOW_INVENTORY.md
> 与 docs/UPSCALE_WORKFLOW_INVENTORY.md。

## 1. 分层边界（§二十九；Phase 3 §0.2/§二十二）

```text
WorkflowModule / EngineAdapter 核心 ── 零节点知识（不知道任何 node id）
        ↑ 只认标准输入：positive_prompt / negative_prompt / width / height / seed（生成）
          或 input_image（处理型）
provider binding（workflows/providers/comfyui/<module_id>/<binding_version>/）
        ├── basic_generate/v1/   workflow.json + binding.yaml + README.md
        └── upscale/v1/          LoadImage → UpscaleModelLoader → ImageUpscaleWithModel → SaveImage
```

**绑定属于每次请求，不属于 Adapter 实例（§0.2）**：一个 ComfyUIAdapter 交替执行
`basic_generate/v1 → upscale/v1 → basic_generate/v1`，按 `(module_id, binding_version)`
动态加载并缓存，无需多套 Adapter。

修改工作流 = 新增 `v2/` 目录 + 更新配置 `binding_version`，核心代码零改动；
**已投入使用的 binding 目录视为 immutable**（Phase 4 Task1：执行指纹 = 双文件）：

```text
workflow_hash = sha256(workflow.json)[:16]
binding_hash  = sha256(binding.yaml)[:16]   ← 覆盖 inputs/defaults/save_image_node/save_image_prefix/capabilities
```

任一指纹与 Job 固化值不一致 → `WORKFLOW_HASH_MISMATCH` / `BINDING_HASH_MISMATCH`
（系统性，拒绝执行）；首次加载同时校验 binding **自描述**
（`binding.module == 请求 module_id`、`binding.provider == 请求 provider`、
`binding.binding_version == 目录版本`），不一致 → `BINDING_IDENTITY_MISMATCH`。

## 2. 执行流程（§三十三；Phase 3：按 Stage 动态绑定）

```text
QueueWorker → PipelineExecutor.resolve_stage_module(stage)（JobStage 固化身份）
  → WorkflowModule.prepare_inputs()（处理型：upload_input_image 正式契约，Task4）
  → WorkflowModule.build_engine_request() → EngineJobRequest{binding, parameters, metadata}
  ↓ ComfyUIAdapter
  → load_binding(request.binding)（按 (module_id, binding_version) 缓存 + 双指纹校验 + 自描述校验）
  → _build_prompt()：标准输入按 binding.inputs 注入节点字段
                    + binding.defaults 覆盖固定参数
                    + SaveImage.filename_prefix = NSFWStudio/{job_short}/{stage}/{item_short}
  → POST /prompt  {prompt, client_id}         → prompt_id（engine_job_id）
  → 进度：WebSocket（ws://…/ws?clientId=）优先，HTTP /history 兜底
  → 完成：GET /history/{id} → outputs[].images[] → GET /view?filename=… 取字节
  → 返回 EngineOutputFile（字节级），由 Worker 注入的 output_importer 导入 DataRoot
```

- 输出命名含 Studio 身份（§九）：`NSFWStudio/<job-short>/<stage>/<item-short>/`；
- `scan_stage_outputs(ref, job_id, stage_index, stage_item_id)`（§九）：ComfyUI 重启后
  history 丢失时，按 binding 前缀模板扫描 Studio 自己的输出目录（仅 `output_dir` 内），
  用于崩溃恢复兜底；绝不扫描用户普通图片。

## 3. EngineAdapter 接口实现

| 方法 | 行为 |
| --- | --- |
| `health()` | `GET /system_stats`（5s 超时，trust_env=False）→ online/detail/version |
| `load_binding(ref)` | 按 `(module_id, binding_version)` 加载并缓存；文件缺失 → BINDING_NOT_FOUND；自描述不一致 → BINDING_IDENTITY_MISMATCH；双指纹不一致 → WORKFLOW_HASH_MISMATCH / BINDING_HASH_MISMATCH |
| `binding_identity(module, version)` | 返回 (实际 binding_version, workflow_hash, binding_hash)，供 Job 创建时固化身份 |
| `upload_input_image(*, image_id, file_name, data)` | Task4 正式契约：`POST /upload/image`（subfolder=NSFWStudio_inputs，命名 `{image_id}{suffix}`）→ 引擎侧引用名 + 登记 Studio Input Registry |
| `submit_job()` | binding 注入 → `POST /prompt`；node_errors → 分类错误 |
| `get_job_status()` | `/history` 权威 + `/queue` 与 WS 新鲜度判定；请求失败抛 OFFLINE/NETWORK（见 §5.1） |
| `cancel_job()` | 先读 `GET /queue` 判断 target 位置（Phase 2.2 §4，见 §3.1） |
| `get_job_outputs()` | `/history` → `/view` 取回字节；无输出 → `OUTPUT_MISSING` |
| `scan_stage_outputs()` | §九 文件级恢复兜底（仅 Studio 自己命名的输出目录） |

## 3.1 取消边界（Phase 2.2 §4，固定）

`/interrupt` 是 ComfyUI 的**全局行为**，会打断当前正在运行的任务——因此必须先读 `/queue`：

```text
target 在 queue_pending            → 只 POST /queue {delete:[target]}，禁止 /interrupt
target 正是 queue_running 的第一位 → 允许 POST /interrupt（同时 delete 清理）
target 不在队列（已完成/被删）
  或 running 是别人的 prompt       → 什么都不做，返回 False
```

原则：**Studio 不能为了取消自己的一个等待任务，打断用户手工在 ComfyUI 里运行的其他任务。**

## 4. 进度通道（§三十四）

- WebSocket 连接 `ws://<url>/ws?clientId=<client_id>`，只更新内存态：
  `execution_start / progress（value/max → 0..0.99）/ execution_success / execution_error`；
- **掉线不判 FAILED**：3 秒自动重连；进度事实由 Worker 的 HTTP 轮询兜底确认；
- `progress_state` 等新式消息忽略即可（不依赖其结构稳定性）。

## 5. 错误分类（§三十五）与重试（§三十六）

`backend/app/engine/errors.py`：`classify_engine_message()`（消息 → 错误类型）与
`is_systemic()`（是否系统性失败）：

| 类型 | 来源示例 | 处理 |
| --- | --- | --- |
| ENGINE_OFFLINE | ConnectError / 队列暂停 | 系统性：Job FAILED + 队列暂停 |
| ENGINE_NETWORK | 网络抖动、超时 | 瞬态：提交/轮询各自动重试 ≤2 |
| ENGINE_TIMEOUT | StageItem 执行总超时（§十，默认 1800s，可配） | 不自动重试，Item FAILED |
| WORKFLOW_ERROR | /prompt 400 非节点错误 | 不自动重试，系统性 |
| BINDING_NOT_FOUND | provider binding 目录/文件缺失 | 不自动重试，系统性（Job 创建时 4xx） |
| WORKFLOW_HASH_MISMATCH | workflow.json 被改动（immutable 违约，§0.3） | 不自动重试，系统性 |
| BINDING_HASH_MISMATCH | binding.yaml 被改动（inputs/defaults/save_image_* 等，Task1） | 不自动重试，系统性 |
| BINDING_IDENTITY_MISMATCH | binding 自描述与请求身份不符 / 恢复时 provider 不匹配 | 不自动重试，系统性 |
| ENGINE_INPUT_UNSUPPORTED | 引擎不支持输入图片契约（Task4） | 不自动重试，系统性 |
| MODEL_MISSING / NODE_MISSING | node_errors 消息分类 | 不自动重试，系统性 |
| OUT_OF_MEMORY | "out of memory"/"allocation" | 不自动重试，系统性 |
| OUTPUT_MISSING | history 无输出文件 | Item FAILED |
| STORAGE_ERROR | 导入 DataRoot 失败 | Item FAILED |
| WORKER_INTERNAL_ERROR | Worker/循环级代码异常（§0.1） | Job INTERRUPTED + 队列暂停 |
| UNKNOWN_ENGINE_ERROR | 其他 | 不自动重试 |

OOM / Workflow / 模型 / 节点缺失 → **不自动重试**。

## 5.1 掉线语义（Phase 2.1 §二，修复"永久 RUNNING"）

```text
get_job_status 的三种来源（优先级）：
  1. WS 实时层（_live，带 updated 新鲜度时间戳）
  2. GET /history/<id>（权威：只存已结束任务）
  3. GET /queue（任务是否仍在 running/pending）

语义边界：
  /history 请求 ConnectError        → 抛 ENGINE_OFFLINE（系统性：Job FAILED + 队列暂停）
  /history 请求其他网络错误          → 抛 ENGINE_NETWORK(transient=true)（Worker 有限重试 ≤2）
  /history 可达但无该任务            → 不是失败：
      · 在 /queue 或 WS 新鲜（<30s）→ running（继续等待）
      · 两者皆无且连续 10 次轮询      → unknown（引擎丢失任务）→ Item FAILED（不自动重试）
```

网络异常**禁止**降级为"还在运行"；"history 尚无该 prompt"**禁止**误判为失败。

## 6. 版本溯源与 binding 解析（§五十五；Phase 2.1 §七；Phase 3 §0.2 动态）

```text
workflows/providers/comfyui/<module_id>/<binding_version>/
  basic_generate/v1/  → v2/   仅新增目录 + 配置 binding_version=v2，核心 Adapter 零改动
  upscale/v1/                 按请求动态加载（一个 Adapter 服务全部模块）
```

目录/文件缺失 → `EngineError("BINDING_NOT_FOUND")`（系统性，不自动重试）；
Job 创建时该错误转为 4xx（`BINDING_NOT_FOUND`）而不是 500。
缓存 key 必须是 `(module_id, binding_version)`，不是一个 Adapter 只保存一个绑定。

## 6.1 版本溯源（§五十五、§五十六；Phase 3 §五）

Job 创建时 `resolve_workflow_modules()` / `binding_identity()` 从 binding 读取每个模块的真实身份：
`module_id / module_version / provider / binding_version / workflow_hash=sha256(workflow.json)[:16] / binding_hash=sha256(binding.yaml)[:16]`，
写入 `workflow_snapshot.modules` 并物化为 JobStage（执行真源）；
从历史 Job / Image 恢复时（Task9）携带完整身份，`resolve_workflow_modules` **固定原身份**执行
（指纹不一致 / provider 不匹配直接拒绝），绝不静默升级。
以后 binding 升级到 v2，老 Job 仍能通过双指纹追溯当时的工作流版本；不一致直接拒绝执行（§0.3）。
真实模型名（Qwen-Image 2.1 UC GGUF 三件套 / 4x-UltraSharp）来自环境调查，记录在
`docs/WORKFLOW_INVENTORY.md` 与 `docs/UPSCALE_WORKFLOW_INVENTORY.md`，不硬编码进核心。

## 7. 本机配置（§三十二，禁止提交机器信息）

```yaml
# configs/config.local.yaml（gitignore）
comfyui:
  url: "http://127.0.0.1:8188"
  # 可选：文件级恢复兜底（§九）需要扫描 ComfyUI output 目录时配置
  output_dir: "D:/AIHome_2.0_L1_L2/projects/comfyui/app/output"
  # 可选：Phase 4 Task11 输入缓存治理（只清理 NSFWStudio_inputs 下登记过、无活动引用的文件）
  input_dir: "D:/AIHome_2.0_L1_L2/projects/comfyui/app/input"
  input_ttl_seconds: 86400
```

公共配置只声明 `workflow.engine.provider: comfyui`（产品默认）与
`module_id / module_version / binding_version`；守卫测试
（tests/backend/test_interfaces.py::test_no_engine_binding_in_configs）
禁止公共配置出现 `127.0.0.1` / `localhost` 等机器地址。

## 8. 测试

- `tests/backend/test_comfyui_binding.py`：binding 注入 / seed 范围 / 双指纹溯源 /
  指纹不一致拒绝 / 自描述不一致拒绝 / binding.yaml 改动必变 binding_hash /
  一个 Adapter 多模块动态加载（CI 可跑，无需 ComfyUI）；
- `tests/backend/test_comfyui_resilience.py`：掉线语义 / binding 版本解析 / 安全取消（离线 stub）；
- `tests/backend/test_comfyui_integration.py`：真实 1 张基础生成 + 1 张真实高清 +
  图库单张高清（§二十六；ComfyUI 不在线时自动 skip）。