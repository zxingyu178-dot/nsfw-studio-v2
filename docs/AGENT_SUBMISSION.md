# Agent / AI 提交端点（安全加固说明）

> 适用：豆包 / Codex / Claude 等 AI 助手把**优化后的提示词**提交给本机 Studio 生成。
> 版本：v0.34.0 起。

## 1. 结论先说

- Studio 的 8000 端口**固定只绑 127.0.0.1（loopback）**，公网/局域网默认**无法直连**；
- 云端豆包**不能**直接访问 `http://127.0.0.1:8000`，推荐路径是：**豆包写好参数/命令 → 你在本机执行**
  `scripts/agent_generate.py`（脚本自动处理 UTF-8、幂等、轮询、保存图片）；
- 给 AI 的专用提交端点 `POST /api/v1/agent/jobs` **默认关闭**，必须显式配置 token 才启用；
- 启用后也有：Bearer token 鉴权、每分钟限速（默认 30 次）、`client_request_id` 幂等、Prompt 长度上限、
  磁盘空间 Gate、模块白名单（仅 `basic_generate` / `anime_generate` + 可选 `upscale`）。

## 2. 安全模型

| 层 | 保护 |
| --- | --- |
| 网络 | `app.host=127.0.0.1`（默认）；不提供任何"打开 0.0.0.0"的开关 |
| 开关 | 未配置 `agent.token` → `/agent/jobs` 返回 **403 AGENT_API_DISABLED** |
| 鉴权 | `Authorization: Bearer <token>`；`secrets.compare_digest` 常量时间比较；错误码 401 |
| 限速 | 默认 30 次/分钟（按 token 摘要计数，内存中不留明文）；超出 → **429 AGENT_RATE_LIMITED** |
| 幂等 | `client_request_id` 重复提交返回原 Job（`idempotent_replay=true`），不重复生成 |
| 输入 | Prompt ≤10000 字符、Negative ≤8000；尺寸 64–4096；数量 1–64；模块白名单 |
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
    "module_id": "anime_generate",
    "width": 768, "height": 1024, "count": 1,
    "client_request_id": "doubao-20261022-001"
  }'
```

响应即 `JobResponse`：`id`、`status=QUEUED`、`queue_position`、`idempotent_replay`。
随后轮询 `GET /api/v1/jobs/{id}`，完成后用 `image_id` 取图：
`GET /api/v1/images/{image_id}/content`。

**模型选择**：`module_id=basic_generate`（Qwen-Image 写实）或 `anime_generate`（Anima 动漫）。
`upscale=true` 追加高清放大；`queue_mode=next` 插队到当前任务之后。

## 5. CLI（更推荐给豆包用）

豆包只需给你一行命令，你在本机跑（自动读环境变量 `NSFW_STUDIO_AGENT_TOKEN`）：

```powershell
$env:NSFW_STUDIO_AGENT_TOKEN = "你的 token"
.venv\Scripts\python scripts\agent_generate.py --module anime_generate `
  --prompt "1girl, red dress, night city, neon lights, anime style, masterpiece" `
  --out D:\ai_out
```

未设置 token 时脚本走本机 `/jobs`（向后兼容，仍只在本机 loopback 生效）；
加 `--legacy` 可显式强制旧路径（仅调试）。

## 6. 测试覆盖

`tests/backend/test_agent_submission.py`：

- 未配置 token → 403 `AGENT_API_DISABLED`
- 缺 token → 401 `AGENT_TOKEN_MISSING`；错误 token → 401 `AGENT_TOKEN_INVALID`
- 正确 token → 201，`source=agent`、模块/Seed 正确、Prompt 快照落库
- 同一 `client_request_id` 第二次 → 同 Job + `idempotent_replay=true`
- 限速：每分钟 1 次时第二次 → 429 `AGENT_RATE_LIMITED`
- 超长 Prompt / 非法模块 → 422
