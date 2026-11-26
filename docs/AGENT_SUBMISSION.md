# Agent / AI 提交端点（安全加固说明）

> 适用：豆包 / Codex / Claude 等 AI 助手把**优化后的提示词、模型与采样参数**提交给本机 Studio 生成。
> 版本：v0.34.0 起；v0.39.0 增加多模型 / LoRA / 采样参数（binding v15）。

## 1. 结论先说

- Studio 的 8000 端口**固定只绑 127.0.0.1（loopback）**，公网/局域网默认**无法直连**；
- 云端豆包**不能**直接访问 `http://127.0.0.1:8000`，推荐路径是：**豆包写好参数/命令 → 你在本机执行**
  `scripts/agent_generate.py`（脚本自动处理 UTF-8、幂等、轮询、保存图片）；
- 给 AI 的专用提交端点 `POST /api/v1/agent/jobs` **默认关闭**，必须显式配置 token 才启用；
- 启用后也有：Bearer token 鉴权、每分钟限速（默认 30 次）、`client_request_id` 幂等、Prompt 长度上限、
  磁盘空间 Gate、**服务端工作流能力校验**（默认/指定的工作流必须是已注册、可用、已放行、
  生成型、无输入图片、允许 generate 的模块；不再使用静态模块白名单）。

## 2. 安全模型

| 层 | 保护 |
| --- | --- |
| 网络 | `app.host=127.0.0.1`（默认）；不提供任何"打开 0.0.0.0"的开关 |
| 开关 | 未配置 `agent.token` → `/agent/jobs` 返回 **403 AGENT_API_DISABLED** |
| 鉴权 | `Authorization: Bearer <token>`；`secrets.compare_digest` 常量时间比较；错误码 401 |
| 限速 | 默认 30 次/分钟（按 token 摘要计数，内存中不留明文）；超出 → **429 AGENT_RATE_LIMITED** |
| 幂等 | `client_request_id` 重复提交返回原 Job（`idempotent_replay=true`），不重复生成 |
| 输入 | Prompt ≤10000 字符、Negative ≤8000；尺寸 64–4096；数量 1–64；工作流由服务端校验 |
| 资源 | 复用 `check_disk_space`：磁盘严重不足拒绝新任务 |
| 日志 | token 不写入日志/响应；错误体只含固定 code + 中文说明 |

**边界**：本端点的安全前提仍是"本机可信进程"。如果未来需要从另一台机器/公网提交，必须额外：
TLS 反向代理 + 防火墙白名单 + 独立 token（并且只把反向代理暴露出去，绝不直接暴露 8000/0.0.0.0）。
目前项目**没有**也不需要这种远程暴露。

## 3. 启用步骤（一次性）

1. 在 `configs/config.local.yaml`（本机私有，gitignore）加入：

```yaml
agent:
  token: "换成一串你生成的随机字符串（32+ 字符）"
  # rate_limit_per_min: 30   # 可选，0 = 不限制（不推荐）
```

   生成随机 token（PowerShell）：

```powershell
[Convert]::ToHexString((1..32 | ForEach-Object { Get-Random -Max 256 }))
```

2. 重启 Studio（ControlHub lifecycle 或桌面快捷方式）。
3. 验证"未带 token 会被拒"：

```powershell
curl.exe -s -X POST http://127.0.0.1:8000/api/v1/agent/jobs -H "Content-Type: application/json" -d '{"prompt":"test"}'
# 期望：401 AGENT_TOKEN_MISSING（或未配置时 403 AGENT_API_DISABLED）
```

## 4. 调用示例

```powershell
$token = "你的 token"
curl.exe -s -X POST http://127.0.0.1:8000/api/v1/agent/jobs `
  -H "Content-Type: application/json" `
  -H "Authorization: Bearer $token" `
  -d '{
    "prompt": "a field botanist, examining a fern, glasshouse, medium shot, soft window light, natural documentary photography",
    "negative_prompt": "low quality, blurry, watermark",
    "width": 768, "height": 1024, "count": 1,
    "client_request_id": "agent-20261031-001"
  }'
```

响应即 `JobResponse`：`id`、`status=QUEUED`、`queue_position`、`module_id`（实际使用的工作流）、
`idempotent_replay`。随后轮询 `GET /api/v1/jobs/{id}`，完成后用 `image_id` 取图：
`GET /api/v1/images/{image_id}/content`。

### 4.1 工作流选择（W1.2）

| 请求 | 行为 |
| --- | --- |
| 不传 `module_id` 或传 `null` | 使用**服务端当前配置的默认工作流**（当前为 `anime_generate`，binding v15） |
| 显式传 `module_id` | 使用指定工作流；服务端校验能力与放行状态 |
| `module_id=""` / `"   "` | `422` 拒绝（空字符串不能绕过显式选择；只有 None 才走默认） |
| `module_version` / `binding_version` | 必须同时提供 `module_id`；按显式身份解析并校验指纹 |
| `workflow_modules=[]`（旧 `/jobs`） | 允许，按服务器默认工作流 |
| 未指定的默认工作流未放行 | **拒绝**（`WORKFLOW_NOT_RELEASED`），不会自动降级到其他模块 |
| 未知模块 | `400 AGENT_MODULE_UNKNOWN` |
| 模块存在但 binding 不可用 | `400 AGENT_MODULE_UNAVAILABLE` |
| 模块不是“无输入图片的文生图” | `400 AGENT_MODULE_NOT_TEXT_GENERATE` |
| 未通过正式放行 | `400 WORKFLOW_NOT_RELEASED` |
| 运行环境未就绪（W2.0） | `400 RUNTIME_PREFLIGHT_BLOCKED`（确认缺节点/模型/版本）或 `RUNTIME_PREFLIGHT_UNKNOWN`（引擎离线/无法验证）；不会降级 |

Agent 只开放**单个无输入图片的生成型模块**，不开放任意 Pipeline，也不提供输入图片上传链路。
当前产品只有 `anime_generate` 一条生成线。

检查顺序：解析实际工作流 → 正式放行门禁 → binding 参数声明 → 模型/LoRA 存在性 →
模块 config 校验 → 运行环境预检 → 写提示词库 → 创建 Job。
任一检查失败都不会产生 Prompt / Job / Stage 数据。

### 4.2 多模型 / LoRA / 采样参数（v15）

`anime_generate` 的 binding `v15` 支持任务级覆盖；不传的字段沿用默认
（miaomiaoHarem v14 / 30 步 / cfg4.0 / er_sde / simple / denoise1.0）。

```json
{
  "prompt": "1girl, solo, red kimono, night city, anime style, masterpiece",
  "negative_prompt": "low quality, blurry",
  "module_id": "anime_generate",
  "module_version": "v1",
  "binding_version": "v15",
  "model": "NoobAI-XL-v1.1.safetensors",
  "loras": [
    {"name": "cunnyfunky_noobai_v3.3_000080.safetensors", "strength_model": 0.6, "strength_clip": 0.6}
  ],
  "params": {"steps": 30, "cfg": 5.0, "sampler_name": "dpmpp_2m", "scheduler": "karras", "denoise": 1.0, "face_detailer": false},
  "width": 832, "height": 1216, "count": 1, "seed": 20261127,
  "client_request_id": "agent-v15-001"
}
```

- `model` 必须是 ComfyUI `/models/checkpoints` 中的文件名（不含路径）；
- `loras` 最多 2 条，强度 -2..2；
- `sampler_name` / `scheduler` 必须来自模块枚举；
- `params.face_detailer=false` 关闭人脸修复以显著提速（默认开启；仅 v15 等工作流含 FaceDetailer 节点时可用）；
- 能力发现：`GET /api/v1/agent/capabilities`（Bearer）返回模块、可用底模、可用 LoRA 与参数边界。

**事务（W1.2.1 / W1.2.2）**：Prompt 创建/复用与 Job / JobItem / JobStage 在同一数据库事务中，
`assign_ai_prompt(commit=False)` 只 flush；`attach_ai_prompt` 不单独提交；
JobService 创建成功时统一提交，失败（校验错误 / 幂等冲突 / 数据库错误）统一 rollback。
CLI 不再提前调用 `/prompts/ensure`。
幂等指纹只覆盖用户请求语义，服务端生成的 `source_prompt_id/version_id` 不参与指纹，
因此 Prompt 归档后同键同内容重放仍返回原 Job；W1.2.2 之前的历史指纹会按旧算法重建兼容。

## 5. CLI（更推荐给豆包用）

现有参数方式继续兼容。AI 可以给出一行命令，由用户在本机运行（脚本自动读取
`configs/config.local.yaml` 的 `agent.token`，环境变量 `NSFW_STUDIO_AGENT_TOKEN` 可覆盖）：

```powershell
$env:NSFW_STUDIO_AGENT_TOKEN = "你的 token"
.venv\Scripts\python scripts\agent_generate.py --prompt "a red fox resting beside a woodland stream" --out D:\ai_out
```

- 不传 `--module` → 使用服务端默认工作流（当前 `anime_generate`，binding v15）；
- 显式 `--module anime_generate` → 使用指定模块；
- `--binding v15 --model <文件名> --lora <文件名>:0.6 --steps 30 --cfg 5.0 --sampler dpmpp_2m --scheduler karras`
  → 多模型 / LoRA / 采样参数（仅 Agent 端点；未配置 token 时 CLI 直接拒绝）；
- `--no-face-detailer` → 关闭人脸修复以提速；`--face-detailer` 可显式强制开启；
- `--list-workflows` → 读取 `/modules`，只列出 Agent 允许使用的文生图模块；
- 命令结束会打印**实际执行**的 `module_id`，不是仅回显 CLI 参数；
- 提示词由服务端在 Job 事务内关联（原 `--no-prompt-library` 已删除，不再有无效选项）。

未设置 token 时脚本走本机 `/jobs`（向后兼容，仍只在本机 loopback 生效）；
加 `--legacy` 可显式强制旧路径（仅调试）。

### 5.1 标准 JSON 请求（推荐给 AI）

把请求保存为标准 UTF-8 JSON，例如 `request.json`：

```json
{
  "prompt": "a field botanist, examining a fern, glasshouse, medium shot, soft window light, natural documentary photography",
  "negative_prompt": "blur, watermark, distorted hands",
  "width": 768,
  "height": 1024,
  "count": 1,
  "seed": 42,
  "queue_mode": "normal",
  "client_request_id": "botanist-study-20261125-001"
}
```

先做完全离线的校验，再提交：

```powershell
.venv\Scripts\python scripts\agent_generate.py --request-file request.json --validate-only
.venv\Scripts\python scripts\agent_generate.py --request-file request.json --out D:\ai_out
```

`--validate-only` 在读取 token、访问网络或创建输出目录之前结束；成功/失败输出不会回显 Prompt 正文或
token。`--request-file` 可以和运行参数 `--out`、`--api`、`--timeout-min`、`--token`、`--legacy`
组合，但不能再混用 `--prompt`、`--negative`、`--module`、`--width`、`--height`、`--count`、
`--seed`、`--next`，避免出现两个请求事实源。

标准文件字段与 `POST /api/v1/agent/jobs` 对齐：

| 字段 | 规则 |
| --- | --- |
| `prompt` | 必填字符串，非空白，最多 10000 字符；脚本不裁剪或改写正文 |
| `negative_prompt` | 可选字符串，默认 `""`，最多 8000 字符；与正向 Prompt 分开 |
| `module_id` | 可选字符串，1–64 字符；省略或 `null` 表示服务端默认，不由 CLI 硬编码 |
| `width` / `height` | 可选整数，64–4096，文件默认均为 1024 |
| `count` | 可选整数，1–64，默认 1；固定 `seed` 时必须为 1 |
| `seed` | 可选整数，0–2147483647；省略或 `null` 表示随机 |
| `queue_mode` | 可选 `normal` / `next`，默认 `normal` |
| `client_request_id` | **必填**非空字符串，最多 128 字符；同一次请求的重试必须复用 |

文件不能超过 128 KiB。脚本拒绝非 UTF-8、JSON 重复字段、未知字段、错误类型、未配对 surrogate、
显式纯空白字符串和越界数值。

`client_request_id` 表示一次用户请求，不是 Prompt 内容的哈希：网络失败后重跑同一个请求文件时保留
原 ID，服务端会幂等返回原 Job；用户有意再次生成相同内容时必须换新 ID。标准请求在临时网络错误或
HTTP 5xx 时最多自动重试两次，所有尝试复用同一 ID。旧 `--prompt ...` 参数方式仍为每次执行生成随机 ID。

### 5.2 Prompt 编排建议

正向 Prompt 可按“主体 → 动作 → 环境 → 构图与光线 → 风格”组织，例如上面的植物学家示例；
负向要求只放在 `negative_prompt`。`count`、尺寸、Seed、队列位置是独立参数，不应塞入 Prompt 正文。
脚本只校验和原样传递正文，不会为了“标准化”而擅自增删、翻译或重排用户语义。

工作流同样不是 Prompt 的一部分：用户明确指定时才传 `module_id`；要求默认时省略它，由服务端当前配置
决定。不要在 AI 模板里硬编码某个工作流，也不要把当前可用模块误当作永久固定清单。

### 5.3 AI 提交规范

- 用户明确指定工作流 → 直接选择并传入 `module_id`；
- 用户要求“默认” → 不传 `module_id`；
- 用户未表达选择 → 先询问“用默认还是指定工作流”，不得自行猜测；
- 不得选择 `ready_to_run=false` 的模块；
- 不得自行声明 G3/G4 已通过；没有真实证据必须标未验证。

## 6. 测试覆盖

`tests/backend/test_agent_submission.py`：

- 未配置 token → 403 `AGENT_API_DISABLED`
- 缺 token → 401 `AGENT_TOKEN_MISSING`；错误 token → 401 `AGENT_TOKEN_INVALID`
- 正确 token → 201，`source=agent`、模块/Seed 正确、Prompt 快照落库
- W1.2：不传 `module_id` → 服务端默认；显式 basic / anime → 201
- W1.2：未知模块 → `AGENT_MODULE_UNKNOWN`；未放行默认 → `WORKFLOW_NOT_RELEASED` 且不降级
- W1.2：process 模块（upscale）→ `AGENT_MODULE_NOT_TEXT_GENERATE`
- W1.2：`upscale=true` 追加在选定 Primary 之后
- W1.2：拒绝请求不产生 Prompt / Job / Stage 数据
- 同一 `client_request_id` 第二次 → 同 Job + `idempotent_replay=true`
- 限速：每分钟 1 次时第二次 → 429 `AGENT_RATE_LIMITED`
- 超长 Prompt → 422
