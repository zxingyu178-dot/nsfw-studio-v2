# COMFY_ADAPTER — ComfyUIAdapter 设计与契约（Phase 2B / 2.1，v0.3.1）

> 更新：2026-10-07。实现：`backend/app/engine/comfyui.py`。
> 环境事实见 docs/COMFY_ENV_INVENTORY.md；工作流选型见 docs/WORKFLOW_INVENTORY.md。

## 1. 分层边界（§二十九）

```text
WorkflowModule / EngineAdapter 核心 ── 零节点知识（不知道任何 node id）
        ↑ 只认标准输入：positive_prompt / negative_prompt / width / height / seed
provider binding（workflows/providers/comfyui/basic_generate/v1/）
        ├── workflow.json   参数化节点图模板（注入点留空）
        ├── binding.yaml    节点 ID / 字段注入位置 / 默认值 / seed 范围 / save 节点
        └── README.md       来源与升级约定
```

修改工作流 = 新增 `v2/` 目录 + 更新 `binding_version`，核心代码零改动。

## 2. 执行流程（§三十三；Phase 2.1 §三 起经 WorkflowModule）

```text
QueueWorker → PipelineExecutor.resolve_module(job)（workflow_snapshot.modules）
  → BasicGenerateModule.build_engine_request()（模块标准输入 → 参数映射）
  → EngineJobRequest
  ↓ ComfyUIAdapter
  → _load_binding()（缓存 workflow + binding，计算 workflow_hash）
  → _build_prompt()：标准输入按 binding.inputs 注入节点字段
                    + binding.defaults 覆盖固定参数
                    + SaveImage.filename_prefix = NSFWStudio/<YYYYMMDD>
  → POST /prompt  {prompt, client_id}         → prompt_id（engine_job_id）
  → 进度：WebSocket（ws://…/ws?clientId=）优先，HTTP /history 兜底
  → 完成：GET /history/{id} → outputs[].images[] → GET /view?filename=… 取字节
  → 返回 EngineOutputFile（字节级），由 Worker 注入的 output_importer 导入 DataRoot
```

Worker 轮询 `get_job_status()`（engine_poll_ms）；`_live` 内存态由 WebSocket 更新，
`/history` 是完成状态的权威（存储已结束任务）。

## 3. EngineAdapter 接口实现

| 方法 | 行为 |
| --- | --- |
| `health()` | `GET /system_stats`（5s 超时，trust_env=False）→ online/detail/version |
| `submit_job()` | binding 注入 → `POST /prompt`；node_errors → 分类错误 |
| `get_job_status()` | `_live`（WS）优先；`/history` 兜底；掉线返回 running 不判 FAILED |
| `cancel_job()` | `POST /queue {delete:[id]}` + `POST /interrupt`（安全取消） |
| `get_job_outputs()` | `/history` → `/view` 取回字节；无输出 → `OUTPUT_MISSING` |

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
| WORKFLOW_ERROR | /prompt 400 非节点错误 | 不自动重试，Item FAILED |
| BINDING_NOT_FOUND | provider binding 目录/文件缺失 | 不自动重试，系统性（Job 创建时 4xx） |
| MODEL_MISSING / NODE_MISSING | node_errors 消息分类 | 不自动重试，系统性 |
| OUT_OF_MEMORY | "out of memory"/"allocation" | 不自动重试，系统性 |
| OUTPUT_MISSING | history 无输出文件 | Item FAILED |
| STORAGE_ERROR | 导入 DataRoot 失败 | Item FAILED |
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

## 6. 版本溯源与 binding 解析（§五十五；Phase 2.1 §七）

binding 目录由配置解析，不再硬编码：

```text
workflows/providers/comfyui/<module_id>/<binding_version>/
  basic_generate/v1/  →  v2/ 仅新增目录 + 配置 binding_version=v2，核心 Adapter 零改动
```

目录/文件缺失 → `EngineError("BINDING_NOT_FOUND")`（系统性，不自动重试）；
Job 创建时该错误转为 4xx（`BINDING_NOT_FOUND`）而不是 500。

## 6.1 版本溯源（§五十五、§五十六）

Job 创建时 `module_identity()` 从 binding 读取：
`module_id=basic_generate / module_version=v1 / provider=comfyui /
binding_version=v1 / workflow_hash=sha256(workflow.json)[:16]`。
以后 binding 升级到 v2，老 Job 仍能通过 hash 追溯当时的工作流版本。
真实模型名（Qwen-Image 2.1 UC GGUF 三件套）来自环境调查，记录在
`docs/WORKFLOW_INVENTORY.md`，不硬编码进核心。

## 7. 本机配置（§三十二，禁止提交机器信息）

```yaml
# configs/config.local.yaml（gitignore）
comfyui:
  url: "http://127.0.0.1:8188"
```

公共配置只声明 `workflow.engine.provider: comfyui`（产品默认）与
`module_id / module_version / binding_version`；守卫测试
（tests/backend/test_interfaces.py::test_no_engine_binding_in_configs）
禁止公共配置出现 `127.0.0.1` / `localhost` 等机器地址。

## 8. 测试

- `tests/backend/test_comfyui_binding.py`：binding 注入 / seed 范围 / hash 溯源（CI 可跑，无需 ComfyUI）；
- `tests/backend/test_comfyui_integration.py`：真实 1/3/8 张生成（ComfyUI 不在线时自动 skip）。