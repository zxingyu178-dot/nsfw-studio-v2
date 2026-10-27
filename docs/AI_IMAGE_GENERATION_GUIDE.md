# AI 生图指南 —— 让 AI 助手（豆包等）正确调用 NSFW Studio 2.0 生图

> 适用版本：v0.36.1 · 生产（后端直出前端）`http://127.0.0.1:8000` · 开发前端 `http://localhost:5173`
> 写于 2026-10-10，基于一次真实事故（"图全是乱码"）的定位结果，先读 §0 再看你要走的路线。
>
> **启动前置（Studio / ComfyUI 启动、队列恢复、可生图验证）统一见 `AGENTS.md` §0「AI 快速操作卡」，
> 本文只讲提示词提交与编码避坑。**

---

## 0. 先看结论：为什么"生成的图是乱码"

**这张"乱码"不是 Studio 或模型的故障，而是提示词在"发送前"就被破坏了。**

事故回放（真实数据）：

| 时间 | 任务 | 收到的 prompt | 结果 |
| --- | --- | --- | --- |
| 10-10 11:24 | `test_20261010_112449`（source=agent） | `????,??????????,????,????,3:4` | COMPLETED，产出了一页"鬼画符文字"图 |
| 10-10 11:39 | `quick_test_20261010_113938`（source=agent） | `??????????????,???????,…` | COMPLETED，产出了一页"??? 涂鸦"图 |

- 任务本身全部**正常完成**（合法 PNG、正常入库）——链路没坏；
- 之前的网页端任务（中文 prompt）完全正常——**后端/数据库/模型对中文没有问题**；
- 唯一异常：这两次请求的 prompt 里，**所有中文都变成了 `?`**。Qwen 模型收到一串 `????`，于是"忠实地"把问号画成了纸上的乱码文字。

### 根因（已复现实证）

**Windows PowerShell 5.1 的 `Invoke-RestMethod -Body <字符串>` 会按非 UTF-8 编码发送请求体，每个中文字符在发出前变成 `?`。**

实测（向本机回显服务发送 `{"full_prompt":"编码测试"}`）：

| 写法 | 服务端实际收到的字节 | 结果 |
| --- | --- | --- |
| ❌ `-Body $json`（字符串，最常见的写法） | `{"full_prompt":"????"}` | **中文全灭** |
| ✅ `-Body ([Text.Encoding]::UTF8.GetBytes($json))` | `{"full_prompt":"编码测试"}`（UTF-8） | 正确 |
| ✅ `-InFile body.json`（UTF-8 无 BOM 文件） | `{"full_prompt":"编码测试"}`（UTF-8） | 正确 |

> 一句话：**中文提示词必须以 UTF-8 字节发送**。用 Python 脚本最省心；用 PowerShell 必须按上表"✅"的写法；cmd/curl 有额外的控制台编码坑（见 §3）。

---

## 1. 三条可行路线（按推荐度）

### 路线 A：直接用网页 UI（最省事，适合人）

生产：浏览器打开 **http://127.0.0.1:8000**（后端直出 `frontend/dist`）；
开发：`http://localhost:5173`（Vite dev server，代理到 8000）。
→ 工作台写提示词 → 生成 → 图库查看。不用碰任何编码问题（浏览器天然 UTF-8）。

### 路线 B：本机 Python + Studio API（★ 推荐给"AI 代跑"场景）

**重要前提**：豆包在云端，**无法直接访问你电脑上的 127.0.0.1**。
正确分工 = **豆包帮你写/改脚本，脚本在你电脑上执行**。

**最省事的方式（已内置 CLI，2026-10-10）**：本仓库自带全流程脚本
`scripts/agent_generate.py`（UTF-8 / 幂等键 / 轮询 / 取图全部处理好）——豆包只需要给一行命令：

```text
.venv/Scripts/python scripts/agent_generate.py --module anime_generate \
    --prompt "1girl, red dress, night city, neon lights, anime style, masterpiece" --out D:\ai_out
```

（可加 `--upscale` 高清、`--next` 插队、`--width/--height/--count/--seed` 等；`--module`
可选 `anime_generate`（动漫）或 `basic_generate`（写实）。）

> **安全加固（v0.34.0 起）**：Studio 8000 固定只绑 `127.0.0.1`（云端 AI 无法直连）；
> 新增 `POST /api/v1/agent/jobs` **默认关闭**，需在 `configs/config.local.yaml` 配置 `agent.token`
> 才启用，并带 Bearer token + 每分钟限速（默认 30）+ `client_request_id` 幂等。
> 豆包仍推荐"写命令 → 本机执行 CLI"；脚本会自动读取 `NSFW_STUDIO_AGENT_TOKEN` 走加固端点。
> 完整安全模型与示例见 **`docs/AGENT_SUBMISSION.md`**。

如果希望豆包生成独立脚本而不是用 CLI：

1. 把 §2 的 `gen.py` 模板保存到你电脑（例如 `D:\gen.py`），只需改开头的 `PROMPT` 等参数；
2. 以后想让豆包"帮我生图"，直接让豆包**按模板改提示词/参数**（或让豆包生成新脚本，并附上 §5 的约束说明）；
3. 在本机运行：`python gen.py`，图片会保存为 `img_xxx.png`。

> Python 的 `json.dumps(..., ensure_ascii=False).encode("utf-8")` 从根上杜绝了中文乱码。

### 路线 C：PowerShell / curl（能用，但必须按正确写法）

| 场景 | ✅ 正确写法 | ❌ 禁止写法 |
| --- | --- | --- |
| PowerShell 5.1 | 把 JSON 存成 **UTF-8 无 BOM** 文件，`-InFile body.json -ContentType "application/json; charset=utf-8"`；或 `-Body ([Text.Encoding]::UTF8.GetBytes($json))` | `-Body $json`（字符串直发，中文→`?`） |
| PowerShell 7+ | `-Body $json` 默认 UTF-8，可用；仍建议 `-InFile` | — |
| cmd + curl.exe | 先 `chcp 65001`；把 JSON 存成 UTF-8 文件，`curl -X POST --data-binary "@body.json" -H "Content-Type: application/json" ...` | 把中文直接内联在命令行里 |
| 查看中文响应 | `chcp 65001` 后再打印；或把响应写入文件再打开 | 在 GBK 控制台直接看 UTF-8 JSON（会显示乱码） |

---

## 2. Python 模板（复制即用）

```python
# gen.py —— 在本机运行；确保后端已在 127.0.0.1:8000 启动
import json, time, uuid, urllib.request

API = "http://127.0.0.1:8000/api/v1"

def post(path: str, payload: dict) -> dict:
    # 中文安全的关键：UTF-8 字节 + charset 头
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        API + path, data=data, method="POST",
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get(path: str) -> dict:
    with urllib.request.urlopen(API + path, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

# ===== 改这里 =====
PROMPT = "一位年轻东亚女性，黄昏海边，白色连衣裙，写实摄影，电影感光线"
NEGATIVE = "低质量, 模糊, 变形, 文字, 水印"
WIDTH, HEIGHT, COUNT = 768, 1024, 1

job = post("/jobs", {
    "source": "doubao",                            # doubao / agent / web 均可
    "client_request_id": f"doubao_{uuid.uuid4().hex[:12]}",  # 每次新任务都要唯一
    "snapshot": {
        "prompt_mode": "full",                     # full=纯文本提示词（最简单）
        "full_prompt": PROMPT,
        "negative_prompt": NEGATIVE,
        "count": COUNT,
        "width": WIDTH, "height": HEIGHT,
        "seed_mode": "random",
        "workflow_modules": [{"module_id": "basic_generate"}],   # 文生图
        "input_images": [],
    },
})
print("job:", job["id"], job["status"])
job_id = job["id"]

# 6GB 显存 + 16GB 内存：首次加载模型可能 10~35 分钟，整体给足超时
detail = job
deadline = time.time() + 2 * 3600
while time.time() < deadline:
    detail = get(f"/jobs/{job_id}")
    if detail["status"] in ("COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"):
        break
    print("...", detail["status"], flush=True)
    time.sleep(5)

if detail["status"] != "COMPLETED":
    raise SystemExit(f"任务未成功: {detail['status']} {detail.get('error_message')}")

for item in detail["items"]:
    image_id = item.get("image_id")
    if not image_id:
        continue
    with urllib.request.urlopen(f"{API}/images/{image_id}/content", timeout=120) as resp:
        data = resp.read()                          # 图片是二进制字节：只保存成文件，不要当文本打印
    file_name = f"{image_id}.png"
    with open(file_name, "wb") as fh:
        fh.write(data)
    print("saved:", file_name, len(data), "bytes")
```

> 完成后也可以直接在网页 http://localhost:5173 → 图库 里看到这张图。

---

## 3. API 速查（v0.9.0）

### 3.1 创建任务：`POST /api/v1/jobs`

```json
{
  "source": "doubao",
  "client_request_id": "唯一字符串（可选但强烈建议）",
  "queue_mode": "normal",
  "snapshot": {
    "prompt_mode": "full",
    "full_prompt": "中文提示词（UTF-8）",
    "negative_prompt": "低质量, 模糊",
    "width": 768, "height": 1024,
    "count": 1,
    "seed_mode": "random",
    "workflow_modules": [{"module_id": "basic_generate"}],
    "input_images": []
  }
}
```

| 字段 | 说明 |
| --- | --- |
| `source` | `web` / `resume` / `agent` / `doubao`（AI 调用请用 `doubao` 或 `agent`） |
| `client_request_id` | **幂等键**：相同 key + 相同内容 → 返回原任务；相同 key + **不同内容 → 409 `IDEMPOTENCY_KEY_CONFLICT`**。每次新需求都换新值 |
| `prompt_mode` | `full`（纯文本）或 `structured`（结构化字段）；AI 场景推荐 `full` |
| `width` / `height` | 64~4096（文生图有效；img2img/reference 的输出尺寸跟随输入图，写什么都不影响结果） |
| `count` | 1~64（建议先 1） |
| `seed_mode` / `seed` | `random` 或 `fixed`（`fixed` 时 `seed` 0~2147483647，且 `count` 建议为 1） |
| `workflow_modules` | 见 §4；`config` 只放模块声明为可配置的参数 |

### 3.2 查询 / 取图

| 操作 | 接口 |
| --- | --- |
| 任务详情（进度 / 状态 / 每张图的 `image_id`） | `GET /api/v1/jobs/{job_id}` |
| 图片列表 | `GET /api/v1/images?limit=20` |
| **下载图片本体** | `GET /api/v1/images/{image_id}/content`（**二进制，保存成文件**） |
| 导入外部图片（img2img 用） | `POST /api/v1/images/import`（multipart 上传，返回 `image_id`） |
| 引擎是否在线 | `GET /api/v1/engine/status` |

### 3.3 失败与异常对照表

| 现象 | 原因与处理 |
| --- | --- |
| 图是"乱码文字 / 鬼画符" | **提示词在发送端被编码破坏**（§0）；先 `GET /jobs/{id}` 检查 `full_prompt` 是否已变成 `?` |
| 控制台/结果里中文变 `?` | Windows 控制台编码；`chcp 65001`，或改用 Python / 文件方式 |
| `409 IDEMPOTENCY_KEY_CONFLICT` | `client_request_id` 复用了，但内容变了；换新 key |
| `400 UNUSED_INPUT_IMAGE` | 给了输入图但模块不消费（如文生图 + 输入图；img2img 请用 `role:"source"`，reference 请用 `role:"reference"`） |
| `400 INPUT_IMAGE_REQUIRED` | 模块需要输入图但没给（img2img/reference/upscale） |
| `422` | 字段类型/范围不符（如 `count=0`、`height=5000`） |
| 任务长时间 `QUEUED`/`RUNNING` | 6GB 显存机器首次加载模型 10~35 分钟属正常；看 `GET /api/v1/engine/status` |
| 任务 `INTERRUPTED` | 后端在任务执行中被重启；用 `POST /api/v1/jobs/{id}/resume-remaining` 续跑（已完成的上游 Stage 不会重跑） |

---

## 4. 四种生成模式（`workflow_modules` 与输入图怎么配）

| 模式 | workflow_modules | input_images | 备注 |
| --- | --- | --- | --- |
| **写实文生图** | `[{"module_id": "basic_generate"}]` | 不传 / `[]` | Qwen-Image 2.1；写实/通用；用 `width/height` |
| **动漫文生图**（2026-10-10 接入） | `[{"module_id": "anime_generate"}]` | 不传 / `[]` | **Anima-2.9B**（动漫/插画）；模型小、加载快（本机 3+1.1+0.24 GB），**批量首选**；官方说明写实表现差，写实请用 basic_generate |
| **图生图** | `[{"module_id": "img2img"}, {"module_id": "upscale"}]`（高清可选） | `[{"role": "source", "image_id": "<先 import 拿到的 id>"}]` | `config` 可调 `denoise`（0~1，默认 0.8；越低越像原图） |
| **参考图生成**（人物/主体一致性） | `[{"module_id": "reference_generate"}]`（高清可选） | `[{"role": "reference", "image_id": "..."}]` | `config` 可调 `resolution`（512~2048，默认 1024）。**很慢**，且目前只能通过 API/脚本使用（UI 尚未接入） |

> **怎么选**：动漫/插画 → `anime_generate`（轻、快）；写实照片感 → `basic_generate`；
> 基于已有图改图 → `img2img`；保持人物身份跨场景 → `reference_generate`。

示例：img2img + 高清 + denoise 0.7：

```json
"workflow_modules": [
  {"module_id": "img2img", "config": {"denoise": 0.7}},
  {"module_id": "upscale"}
]
```

示例：动漫文生图（推荐给批量 / 快速试用）：

```json
"workflow_modules": [{"module_id": "anime_generate"}]
```

---

## 5. 给豆包的"系统提示词"（直接复制给豆包）

```text
你在帮我调用本机的 NSFW Studio 2.0 生图（后端 http://127.0.0.1:8000）。
遵守以下约束：
1) 你无法直接访问 127.0.0.1 —— 请生成/修改我本机运行的 Python 脚本，由我执行；
2) 脚本必须用 UTF-8 发送 JSON（json.dumps(ensure_ascii=False).encode("utf-8")），
   严禁用 PowerShell 5.1 的 -Body 字符串发中文；
3) 每个新任务的 client_request_id 必须唯一（如 doubao_ + uuid）；
4) 创建任务用 POST /api/v1/jobs（source=doubao，prompt_mode=full），
   轮询 GET /api/v1/jobs/{id} 直到 COMPLETED/FAILED/CANCELLED；
5) 取图用 GET /api/v1/images/{image_id}/content，按二进制保存为 .png 文件，
   绝不把图片字节当文本打印；
6) 单次任务超时按 2 小时设置（本机 6GB 显存加载模型很慢）；
7) 生图模式用 workflow_modules 选择：动漫/插画用 [{"module_id":"anime_generate"}]（轻量快速）；
   写实照片感用 [{"module_id":"basic_generate"}]；改图用 img2img；人物一致性用 reference_generate；
8) 只输出可直接运行的完整脚本，参数（提示词/尺寸/张数/模式）放在脚本最上方。
```

---

## 6. 排错三步法

1. **先查任务**：`GET /api/v1/jobs/{最新任务id}` —— 看 `status` 与 `full_prompt`/`structured_prompt`。
   - prompt 已是 `?` → 发送端编码问题（回 §0/§1 修脚本）；
   - prompt 是正常中文但图不对 → 把 prompt 写得更具体，或换模式（§4）；
2. **再查引擎**：`GET /api/v1/engine/status` 是否在线；任务 `INTERRUPTED` 用 `resume-remaining`；
3. **最后查图库**：`GET /api/v1/images?limit=20`，确认 `kind`（original/upscaled/processed）与 `parent_image_id` 是否符合预期。
