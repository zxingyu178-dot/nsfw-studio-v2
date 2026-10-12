# Engine Runtime Contract（生图引擎运行时契约）

> 适用：NSFW Studio V2「日用化」阶段。本文档冻结 **Studio 后端对 ComfyUI 进程的运行时管理契约**，
> 后端实现见 `backend/app/services/engine_runtime_service.py`、`backend/app/api/v1/engine_runtime.py`，
> 前端实现见 `frontend/src/components/EngineControlPopover.tsx`。
>
> 本文档描述的是 **Engine Runtime State（引擎运行时状态）**，它与 **Job State（任务状态）完全独立**，
> 二者不得混用。

---

## 1. 目标与边界

- Studio 在界面内**按需启动 / 停止 / 重启自己的 ComfyUI 进程**，让用户在不生图时（如打游戏）释放 GPU。
- Studio **只拥有并控制自己启动的 ComfyUI**；对用户在 Studio 之外手动启动的 ComfyUI，只能连接使用，
  **不拥有进程、禁止停止 / 重启 / 杀进程**。
- 本轮**不做**：升级 ComfyUI、安装 custom node、下载模型、自动切换端口、ControlHub 接管。

---

## 2. 固定端口（红线）

- ComfyUI 端口**固定为 `8188`**（`FIXED_PORT`），Host 默认 `127.0.0.1`（`DEFAULT_HOST`）。
- **禁止自动换口**：任何情况下都不得因为 8188 被占就改用 8189 等其他端口。
  - 8188 上是健康 ComfyUI 但非 Studio 启动 → `RUNNING_EXTERNAL`（可连接使用）。
  - 8188 被非 ComfyUI 程序占用 → `PORT_CONFLICT`，UI 明示，不跳转端口。

---

## 3. Engine Runtime State（7 态，独立于 Job State）

| State | 含义 | `owned` |
|---|---|---|
| `STOPPED` | 8188 关闭，无受管进程 | false |
| `STARTING` | Studio 已 spawn 受管进程，正在等待健康探测通过 | true（PID 已记录） |
| `RUNNING_MANAGED` | 8188 健康，且该进程由 Studio 启动 | true |
| `RUNNING_EXTERNAL` | 8188 健康，但**不是** Studio 启动（受管进程不存在 / 已消失） | false |
| `STOPPING` | Studio 正在终止自己的受管进程树 | true（清理中） |
| `PORT_CONFLICT` | 8188 有 HTTP 响应但不是健康 ComfyUI（被其他程序占用） | false |
| `ERROR` | 受管进程已启动但健康探测超时 / 进程僵死；启动失败 | false |

**状态机：**

```text
STOPPED ──start──▶ STARTING ──健康探测成功──▶ RUNNING_MANAGED
                       │
                       └──60s 内未健康──▶ ERROR（清理自己刚启动的进程树，不留孤儿）

RUNNING_MANAGED ──stop/restart──▶ STOPPING ──▶ STOPPED
8188 健康但非 Studio 启动 ──▶ RUNNING_EXTERNAL（owned=false，不可杀）
8188 被非 ComfyUI 占用 ──▶ PORT_CONFLICT
```

状态推导（`_recompute_state`）同时依据：
1. Studio 记录的受管 PID 是否仍存活（psutil）；
2. 对 `http://host:port/system_stats` 的探测结果（`online` / `responded` / 无响应）。

> Engine Runtime State **绝不混入** `QUEUED / RUNNING / PAUSED / COMPLETED` 等 Job State；
> Job State 也不引用 Runtime State。

---

## 4. 健康探测

- 探测端点：`GET http://{host}:{port}/system_stats`，超时 `PROBE_TIMEOUT_S = 3s`，`trust_env=False`（不走代理）。
- 判定：
  - 返回 JSON 且含 `system` 字段 → `online=True`，版本取 `system.comfyui_version`；
  - 有 HTTP 响应但不是 ComfyUI → `online=False, responded=True`（→ `PORT_CONFLICT`）；
  - 连接拒绝 / 超时 → `online=False, responded=False`（端口关闭）。

---

## 5. HTTP API

所有路由挂在 `/api/v1` 下：

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/engine/runtime` | 查询当前运行时状态（内部先 recompute） |
| POST | `/api/v1/engine/runtime/start` | 启动受管 ComfyUI（幂等） |
| POST | `/api/v1/engine/runtime/stop` | 停止 Studio 自己的受管 ComfyUI |
| POST | `/api/v1/engine/runtime/restart` | 重启受管 ComfyUI（stop owned → start） |

阻塞操作（spawn / probe / psutil）在 API 层用 **`asyncio.to_thread`** 包装，不阻塞事件循环。

### 5.1 响应体（`RuntimeSnapshot`）

```json
{
  "state": "RUNNING_EXTERNAL",
  "host": "127.0.0.1",
  "port": 8188,
  "owned": false,
  "pid": null,
  "started_at": null,
  "detail": "检测到外部 ComfyUI @ 127.0.0.1:8188",
  "log_location": "<DataRoot>/logs/engine/comfyui-managed.log",
  "health": { "online": true, "engine_name": "comfyui", "engine_version": "0.37.0" }
}
```

- `owned`：当前是否存在 Studio 记录的受管 PID。
- `pid` / `started_at`：仅受管时非空。
- **start 失败也返回 HTTP 200**，且 `state="ERROR"`（启动失败是业务结果，不是 5xx）。

### 5.2 错误（统一信封 `{"error":{"code","message"}}`）

| HTTP | code | 触发条件 |
|---|---|---|
| 409 | `ENGINE_NOT_OWNED` | 对 `RUNNING_EXTERNAL` 调用 stop / restart |
| 409 | `ENGINE_PORT_CONFLICT` | `PORT_CONFLICT` 状态下调用 start |

---

## 6. 进程归属（硬安全）

- 使用 **psutil**（依赖理由：按 PID + 递归子进程树精确归属，避免 `taskkill /IM python.exe` 误杀）。
- 受管启动时记录：**PID + 命令（argv）+ 工作目录 + 启动时间（UTC ISO）**。
- 启动方式：`subprocess.Popen`，Windows 下 `creationflags=0x08000000`（`CREATE_NO_WINDOW`），
  stdout / stderr 重定向到 `<DataRoot>/logs/engine/comfyui-managed.log`。
  - Popen 会把日志句柄继承给子进程；父进程（Studio）在 Popen 后**立即关闭自己持有的句柄副本**，
    避免每次受管 start 在父进程泄漏一个 OS 文件句柄；子进程保留继承副本继续写日志。
- 停止（`_terminate_tree`）：
  1. `psutil.Process(pid).children(recursive=True)` 取**该 PID 及其全部递归子进程**；
  2. 对每个进程 `terminate()`，`psutil.wait_procs(..., timeout=10s)`（`TERMINATE_GRACE_S`）；
  3. 宽限期后仍存活的，再 `kill()`。
- **严禁** `taskkill /IM python.exe`、杀所有 Python、杀 external 进程。

### 启动失败 / 健康超时的清理

- start 后 60s（`START_HEALTH_TIMEOUT_S`，每 1s 探测一次）内未健康：
  调用 `_terminate_tree` 清理**自己刚启动**的进程树，清空受管记录，置 `ERROR`，不留孤儿。

---

## 7. 幂等性

- `start`：当前为 `RUNNING_MANAGED / STARTING / RUNNING_EXTERNAL` 时**直接返回当前快照，不再 spawn 第二个进程**。
- `stop`：已是 `STOPPED / PORT_CONFLICT / ERROR` 且无受管 PID 时直接返回。
- `restart`：对 external 抛 `ENGINE_NOT_OWNED`；否则先终止 owned 进程再 start。

---

## 8. UI 契约（EngineControlPopover）

- 顶部 **Engine 指示可点击**，弹出锚定的 Popover；打开即查询并每 3s 轮询 `/engine/runtime`；
  ESC / 点击外部关闭，含焦点管理。
- 各状态展示与按钮：
  - `RUNNING_MANAGED`：`● 已运行 / ComfyUI · 8188`，按钮 **[停止引擎] [重启]**。
  - `STOPPED`：`○ 已停止`，按钮 **[启动生图引擎]**。
  - `STARTING / STOPPING`：显示“正在启动 / 正在停止…”，禁用按钮。
  - `RUNNING_EXTERNAL`：`● 外部 ComfyUI · 8188`，**不渲染停止 / 重启按钮**，显示
    “当前 ComfyUI 不是由 Studio 启动，不能从这里停止或重启。”
  - `PORT_CONFLICT`：`! 端口冲突 / 8188 已被其他程序占用`，不出现 8189。
  - `ERROR`：显示“启动失败”+ detail，提供重试启动。

### 8.1 停止 / 重启前的确认与“先暂停队列再停引擎”

- 点击停止 / 重启时先查队列：
  - **无 RUNNING Job** → 直接执行。
  - **有 RUNNING Job** → 弹确认：
    > 当前图片仍在生成。停止引擎会中断当前图片，并暂停后续队列。
    > 按钮：[取消] [仍然停止]
  - 用户确认后**严格按顺序**：① `POST /api/v1/queue/pause`（暂停队列）→ ② 停止 / 重启受管引擎；
    当前 Worker 按现有异常 / interrupted 逻辑收口，禁止下一任务继续启动。
  - 取消则不发生任何动作。
- 这里**不伪装“安全完成当前图片”**——用户目标是立即释放 GPU。

---

## 9. 引擎离线时的可用性

- 引擎（ComfyUI）离线时，**Gallery / Prompt / Assets / Settings 必须照常可用**，仅“生成”受限。
- Studio 后端自身不随引擎启停而崩溃；受管引擎启动失败仅在 Popover 内体现为 `ERROR`。

---

## 10. 测试覆盖

- 服务层 `tests/backend/test_engine_runtime_service.py`、API 层 `tests/backend/test_engine_runtime_api.py`：
  覆盖 managed start / external detect / port conflict / owned stop / cannot kill external / 幂等 start。
  测试全部 monkeypatch spawn / probe / pid_alive / terminate 四个 seam，**不起真实进程**。
- 前端 `components/__tests__/EngineControlPopover.test.tsx`：覆盖各状态渲染、停止确认、
  “先 pause 再 stop”调用顺序、external 无停止 / 重启。
- 真实进程启停（managed）在 8188 空闲时由真实浏览器 E2E 验证；external 占用期间该项以确定性测试覆盖，
  并在验收报告中如实标注。
