# Agent / AI 提交端点（安全加固说明）

> 适用：豆包 / Codex / Claude 等 AI 助手把**优化后的提示词**提交给本机 Studio 生成。
> 版本：v0.34.0 起。

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
    "prompt": "1girl, silver hair, kimono, shrine, masterpiece, best quality",
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
| 不传 `module_id` 或传 `null` | 使用**服务端当前配置的默认工作流**（来自 settings `engine.module_id`，没有第二套默认逻辑） |
| 显式传 `module_id` | 使用指定工作流；服务端校验能力与放行状态 |
| `upscale=true` | 在**实际选定的 Primary** 之后追加 `upscale`（不能把它当 Primary） |
| 未指定的默认工作流未放行 | **拒绝**（`WORKFLOW_NOT_RELEASED`），不会自动降级到其他模块 |
| 未知模块 | `400 AGENT_MODULE_UNKNOWN` |
| 模块存在但 binding 不可用 | `400 AGENT_MODULE_UNAVAILABLE` |
| 模块不是“无输入图片的文生图” | `400 AGENT_MODULE_NOT_TEXT_GENERATE`（如 img2img / reference_generate / upscale） |
| 未通过正式放行 | `400 WORKFLOW_NOT_RELEASED` |

Agent 第一版只开放**单个无输入图片的生成型模块 + 可选 upscale**，不开放任意 Pipeline，
也不提供 img2img / reference_generate 的输入图片上传链路。

检查顺序：解析实际工作流 → 正式放行门禁 → 模块能力校验 → 写提示词库 → 创建 Job。
任一检查失败都不会产生 Prompt / Job / Stage 数据。

## 5. CLI（更推荐给豆包用）

豆包只需给你一行命令，你在本机跑（脚本自动读取 `configs/config.local.yaml` 的 `agent.token`，环境变量 `NSFW_STUDIO_AGENT_TOKEN` 可覆盖）：

```powershell
$env:NSFW_STUDIO_AGENT_TOKEN = "你的 token"
.venv\Scripts\python scripts\agent_generate.py --prompt "1girl, red dress, night city, neon lights" --out D:\ai_out
```

- 不传 `--module` → 使用服务端默认工作流（CLI 不再默认 anime_generate）；
- 显式 `--module basic_generate` / `--module anime_generate` → 使用指定模块；
- `--list-workflows` → 读取 `/modules`，只列出 Agent 允许使用的文生图模块；
- 命令结束会打印**实际执行**的 `module_id`，不是仅回显 CLI 参数。

未设置 token 时脚本走本机 `/jobs`（向后兼容，仍只在本机 loopback 生效）；
加 `--legacy` 可显式强制旧路径（仅调试）。

## 5.1 AI 提交规范

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
