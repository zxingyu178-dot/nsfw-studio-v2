"""ComfyUIAdapter（Phase 2B）——真实对接本机 ComfyUI。

执行流程（规范 §三十三）::

    EngineJobRequest → 载入 provider binding → 注入 Prompt/Seed/尺寸
    → POST /prompt → 记录 prompt_id → WebSocket 进度 → history 确认
    → /view 取回输出 → 由 Worker 导入 DataRoot

设计要点：
- 节点 ID / Workflow JSON 全部来自 provider binding（规范 §二十九），核心层零绑定；
- WebSocket 只用于**进度**：掉线不判定 FAILED，自动重连 + HTTP history 重新确认（§三十四）；
- 错误分类（§三十五）：/prompt 的 node_errors → NODE_MISSING/WORKFLOW_ERROR，
  执行异常消息 → classify_engine_message；连接失败 → ENGINE_OFFLINE/ENGINE_NETWORK；
- 真实模型信息只来自调查（见 docs/WORKFLOW_INVENTORY.md），不硬编码新模型（§五十六）。
"""
from __future__ import annotations

import asyncio
import contextlib
import datetime as _dt
import hashlib
import json
import logging
import time
import uuid
from pathlib import Path

import httpx
import yaml

from app.engine.base import (
    EngineAdapter,
    EngineError,
    EngineJobRequest,
    EngineJobStatus,
    EngineOutputFile,
    EngineStatus,
)
from app.engine.errors import classify_engine_message  # noqa: F401（submit/ws 分类）

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROVIDERS_DIR = PROJECT_ROOT / "workflows" / "providers" / "comfyui"

# 实时层新鲜度：超过该秒数未收到任何 WS 更新时，才允许“引擎丢失任务”判定（§二）
LIVE_STALE_SECONDS = 30.0
# 既不在 /queue 也不在 /history 的连续轮询次数容忍（避免提交竞态误判）
MISSING_TOLERANCE = 10


class ComfyUIAdapter(EngineAdapter):
    name = "comfyui"
    version = "0.1.0"

    def __init__(
        self,
        options: dict | None = None,
        comfyui_config: dict | None = None,
        *,
        module_id: str = "basic_generate",
        binding_version: str = "v1",
    ) -> None:
        options = options or {}
        comfyui_config = comfyui_config or {}
        self.base_url = str(comfyui_config.get("url", "http://127.0.0.1:8188")).rstrip("/")
        self.client_id = uuid.uuid4().hex
        self.request_timeout = float(options.get("timeout_seconds", 600))
        self.ws_enabled = bool(options.get("websocket_progress", True))
        # provider binding 目录由 module_id + binding_version 解析（§七，禁止硬编码 v1）
        self.module_id = module_id
        self.configured_binding_version = binding_version
        self._workflow: dict | None = None
        self._binding: dict | None = None
        self._workflow_hash: str | None = None
        # prompt_id → {"stage","progress","state","error","updated"}（WebSocket 实时层）
        self._live: dict[str, dict] = {}
        self._missing_polls: dict[str, int] = {}
        self._ws_task: asyncio.Task | None = None

    # ===== Binding =====
    def binding_dir(self) -> Path:
        """实际 provider binding 目录：workflows/providers/comfyui/<module_id>/<binding_version>/"""
        return PROVIDERS_DIR / self.module_id / self.configured_binding_version

    def _load_binding(self) -> tuple[dict, dict]:
        if self._workflow is None or self._binding is None:
            directory = self.binding_dir()
            workflow_path = directory / "workflow.json"
            binding_path = directory / "binding.yaml"
            if not workflow_path.is_file() or not binding_path.is_file():
                raise EngineError("BINDING_NOT_FOUND", f"provider binding 不存在: {directory}")
            self._workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
            self._binding = yaml.safe_load(binding_path.read_text(encoding="utf-8"))
            self._workflow_hash = hashlib.sha256(workflow_path.read_bytes()).hexdigest()[:16]
        return self._workflow, self._binding

    @property
    def workflow_hash(self) -> str | None:
        self._load_binding()
        return self._workflow_hash

    @property
    def binding_version(self) -> str:
        self._load_binding()
        return str(self._binding.get("binding_version", "v1"))

    def _build_prompt(self, request: EngineJobRequest) -> dict:
        workflow, binding = self._load_binding()
        prompt = json.loads(json.dumps(workflow))  # deep copy
        params = request.parameters
        for name, target in (binding.get("inputs") or {}).items():
            value = params.get(name)
            if value is None:
                continue
            if name == "seed":
                seed_range = binding.get("seed_range") or {}
                value = max(int(seed_range.get("min", 0)), min(int(value), int(seed_range.get("max", 2**31 - 1))))
            prompt[str(target["node"])]["inputs"][target["field"]] = value
        for node_id, fields in (binding.get("defaults") or {}).items():
            prompt[str(node_id)]["inputs"].update(fields)
        save_node = str(binding["save_image_node"])
        date = _dt.date.today().strftime("%Y%m%d")
        prompt[save_node]["inputs"]["filename_prefix"] = str(binding.get("save_image_prefix", "NSFWStudio")).replace(
            "{date}", date
        )
        return prompt

    # ===== 健康探测 =====
    async def health(self) -> EngineStatus:
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
                response = await client.get(f"{self.base_url}/system_stats")
                response.raise_for_status()
                data = response.json()
            version = str(data.get("system", {}).get("comfyui_version", ""))
            return EngineStatus(online=True, detail=f"comfyui {version} @ {self.base_url}",
                                engine_name=self.name, engine_version=version or self.version)
        except Exception as error:
            return EngineStatus(online=False, detail=f"ComfyUI 不可达: {error}", engine_name=self.name)

    # ===== 提交 =====
    async def submit_job(self, request: EngineJobRequest) -> str:
        prompt = self._build_prompt(request)
        payload = {"prompt": prompt, "client_id": self.client_id}
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=30) as client:
                response = await client.post(f"{self.base_url}/prompt", json=payload)
        except httpx.ConnectError as error:
            raise EngineError("ENGINE_OFFLINE", f"ComfyUI 连接失败: {error}") from error
        except httpx.HTTPError as error:
            raise EngineError("ENGINE_NETWORK", f"ComfyUI 请求失败: {error}", transient=True) from error

        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        if response.status_code != 200 or data.get("error") or data.get("node_errors"):
            message = json.dumps(data, ensure_ascii=False)[:500]
            if data.get("node_errors"):
                node_text = json.dumps(data["node_errors"], ensure_ascii=False)
                raise EngineError(classify_engine_message(node_text), message)
            raise EngineError("WORKFLOW_ERROR", message)
        prompt_id = data.get("prompt_id")
        if not prompt_id:
            raise EngineError("UNKNOWN_ENGINE_ERROR", f"/prompt 未返回 prompt_id: {message}")
        self._live[prompt_id] = {"stage": "queued", "progress": 0.0, "state": "queued",
                                 "error_type": "", "error_message": "",
                                 "updated": time.monotonic()}
        self._ensure_ws()
        return prompt_id

    # ===== 进度（WebSocket 优先，HTTP history 兜底确认） =====
    async def get_job_status(self, engine_job_id: str) -> EngineJobStatus:
        """查询引擎任务状态（规范 §二）。

        语义边界（修复"掉线后永久 RUNNING"）：
        - history 请求本身失败 → EngineError（ENGINE_OFFLINE / ENGINE_NETWORK transient），
          由 Worker 按策略有限重试或系统性失败，**不得伪装成“还在运行”**；
        - history 可达但尚无该任务 → 结合 /queue 与实时层判断：
          在队列中 / WS 显示仍在执行 → running；两者都没有且超过容忍 → unknown（任务丢失）。
        """
        live = self._live.get(engine_job_id)
        if live and live.get("state") == "failed":
            return EngineJobStatus(state="failed", progress=live.get("progress"),
                                   message=live.get("error_message") or "execution error",
                                   stage=live.get("stage", ""), error_type=live.get("error_type", ""))
        history_state = await self._history_state(engine_job_id)
        if history_state is not None:
            self._missing_polls.pop(engine_job_id, None)
            if history_state.state == "succeeded" and live is not None:
                self._mark_live(engine_job_id, state="succeeded", stage="save_image", progress=1.0)
            return history_state

        if await self._in_engine_queue(engine_job_id):
            self._missing_polls.pop(engine_job_id, None)
            return self._running_status(live)

        fresh = live is not None and (time.monotonic() - live.get("updated", 0.0)) < LIVE_STALE_SECONDS
        if fresh and live.get("state") in ("queued", "running", "succeeded"):
            return self._running_status(live)

        missing = self._missing_polls.get(engine_job_id, 0) + 1
        self._missing_polls[engine_job_id] = missing
        if missing >= MISSING_TOLERANCE:
            self._missing_polls.pop(engine_job_id, None)
            return EngineJobStatus(state="unknown", progress=None, stage="unknown",
                                   message="引擎队列与 history 均无该任务（任务丢失）")
        return self._running_status(live)

    @staticmethod
    def _running_status(live: dict | None) -> EngineJobStatus:
        if live is not None and live.get("state") in ("queued", "running"):
            return EngineJobStatus(state="running", progress=live.get("progress"),
                                   stage=live.get("stage", ""))
        return EngineJobStatus(state="running", progress=None, stage="unknown")

    async def _history_state(self, engine_job_id: str) -> EngineJobStatus | None:
        """history 权威结果；None 仅表示“请求成功但任务尚未出现在 history”。"""
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=15) as client:
                response = await client.get(f"{self.base_url}/history/{engine_job_id}")
                response.raise_for_status()
                history = response.json()
        except httpx.ConnectError as error:
            raise EngineError("ENGINE_OFFLINE", f"ComfyUI 连接失败: {error}") from error
        except httpx.HTTPError as error:
            # 瞬时网络错误：标记 transient，交给 Worker 有限重试（§三十六），不直接判 FAILED
            raise EngineError("ENGINE_NETWORK", f"ComfyUI /history 请求失败: {error}",
                              transient=True) from error
        entry = history.get(engine_job_id)
        if not entry:
            return None  # 尚未完成（history 只存已结束任务）
        status_info = entry.get("status") or {}
        if status_info.get("status_str") == "error":
            messages = json.dumps(status_info.get("messages", []), ensure_ascii=False)
            return EngineJobStatus(state="failed", progress=None,
                                   message=messages[:500], stage="error")
        return EngineJobStatus(state="succeeded", progress=1.0, stage="save_image")

    async def _in_engine_queue(self, engine_job_id: str) -> bool:
        """该任务是否仍在 ComfyUI 队列（running/pending）中。"""
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                response = await client.get(f"{self.base_url}/queue")
                response.raise_for_status()
                data = response.json()
        except httpx.ConnectError as error:
            raise EngineError("ENGINE_OFFLINE", f"ComfyUI 连接失败: {error}") from error
        except httpx.HTTPError as error:
            raise EngineError("ENGINE_NETWORK", f"ComfyUI /queue 请求失败: {error}",
                              transient=True) from error
        ids = self._queue_ids(data, "queue_running") | self._queue_ids(data, "queue_pending")
        return engine_job_id in ids

    # ===== 输出取回（规范 §三十九/§四十：字节级取回，Worker 导入 DataRoot） =====
    async def get_job_outputs(self, engine_job_id: str) -> list[EngineOutputFile]:
        async with httpx.AsyncClient(trust_env=False, timeout=30) as client:
            response = await client.get(f"{self.base_url}/history/{engine_job_id}")
            response.raise_for_status()
            entry = response.json().get(engine_job_id) or {}
            outputs = entry.get("outputs") or {}
            files: list[EngineOutputFile] = []
            for _node_id, node_output in outputs.items():
                for image in node_output.get("images", []):
                    if image.get("type") not in (None, "output"):
                        continue
                    params = {
                        "filename": image["filename"],
                        "subfolder": image.get("subfolder", ""),
                        "type": image.get("type", "output"),
                    }
                    view = await client.get(f"{self.base_url}/view", params=params)
                    view.raise_for_status()
                    files.append(EngineOutputFile(filename=image["filename"], data=view.content))
            if not files:
                raise EngineError("OUTPUT_MISSING", f"history 中没有输出文件: {engine_job_id}")
            return files

    # ===== 取消（规范 §十九：Adapter 安全支持时请求取消） =====
    async def cancel_job(self, engine_job_id: str) -> bool:
        """安全取消（Phase 2.2 §4）：只处理自己的 target，绝不打断其他任务。

        /interrupt 是 ComfyUI 的全局行为，必须先读 /queue 判断 target 位置：
        - target 在 pending  → 只 POST /queue delete，**不调用 /interrupt**；
        - target 正是当前 running → 才允许 /interrupt；
        - target 不在队列（已完成/被删除），或当前 running 是别人的 prompt
          → 什么都不做（Studio 不得代替用户打断手工运行的其他任务）。
        """
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                response = await client.get(f"{self.base_url}/queue")
                response.raise_for_status()
                data = response.json()
                running_ids = self._queue_ids(data, "queue_running")
                pending_ids = self._queue_ids(data, "queue_pending")
                if engine_job_id in pending_ids:
                    await client.post(f"{self.base_url}/queue", json={"delete": [engine_job_id]})
                    return True
                if engine_job_id in running_ids:
                    await client.post(f"{self.base_url}/queue", json={"delete": [engine_job_id]})
                    await client.post(f"{self.base_url}/interrupt")
                    return True
                logger.info("取消目标不在 ComfyUI 队列中（不打断其他任务）: %s", engine_job_id)
                return False
        except httpx.HTTPError as error:
            logger.warning("ComfyUI 取消请求失败: %s", error)
            return False

    @staticmethod
    def _queue_ids(data: dict, bucket: str) -> set[str]:
        """解析 /queue 响应中的一个队列桶（running/pending）里的 prompt_id 集合。"""
        ids: set[str] = set()
        for entry in data.get(bucket) or []:
            if isinstance(entry, (list, tuple)) and len(entry) > 1 and isinstance(entry[1], str):
                ids.add(entry[1])
            elif isinstance(entry, dict) and entry.get("prompt_id"):
                ids.add(str(entry["prompt_id"]))
        return ids

    # ===== WebSocket 进度监听（§三十四） =====
    def _ensure_ws(self) -> None:
        if not self.ws_enabled or (self._ws_task is not None and not self._ws_task.done()):
            return
        self._ws_task = asyncio.create_task(self._ws_loop(), name="comfyui-ws")

    async def _ws_loop(self) -> None:
        import websockets

        ws_url = self.base_url.replace("http", "ws", 1) + f"/ws?clientId={self.client_id}"
        while True:
            try:
                async with websockets.connect(ws_url, max_size=2**23, open_timeout=10) as ws:
                    logger.info("ComfyUI WebSocket 已连接")
                    async for raw in ws:
                        self._handle_ws_message(raw)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.debug("ComfyUI WebSocket 断开（自动重连，不判 FAILED）: %s", error)
            await asyncio.sleep(3)  # 掉线 → 重连；进度由 HTTP history 兜底（规范 §三十四）

    def _mark_live(self, prompt_id: str, **fields) -> None:
        """更新实时层并刷新新鲜度时间戳（§二：stale 实时层不得掩盖掉线）。"""
        live = self._live.get(prompt_id)
        if live is None:
            live = {"stage": "", "progress": None, "state": "running",
                    "error_type": "", "error_message": ""}
            self._live[prompt_id] = live
        live.update(fields)
        live["updated"] = time.monotonic()

    def _handle_ws_message(self, raw) -> None:
        try:
            message = json.loads(raw)
        except (TypeError, ValueError):
            return
        kind = message.get("type")
        data = message.get("data") or {}
        prompt_id = data.get("prompt_id")
        if prompt_id and prompt_id in self._live:
            live = self._live[prompt_id]
            if kind == "execution_start":
                self._mark_live(prompt_id, state="running", stage="execution",
                                progress=live.get("progress") or 0.0)
            elif kind == "progress":
                value, maximum = data.get("value", 0), data.get("max", 1) or 1
                self._mark_live(prompt_id, state="running", stage="sampling",
                                progress=round(min(0.99, value / maximum), 3))
            elif kind == "execution_success":
                self._mark_live(prompt_id, state="succeeded", stage="save_image", progress=1.0)
            elif kind == "execution_error":
                node_type = data.get("node_type") or ""
                error_message = f"{node_type}: {data.get('exception_message', '')}".strip(": ")
                self._mark_live(prompt_id, state="failed", stage="error",
                                error_type=classify_engine_message(error_message),
                                error_message=error_message[:400])


