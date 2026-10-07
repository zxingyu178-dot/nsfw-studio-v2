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


class ComfyUIAdapter(EngineAdapter):
    name = "comfyui"
    version = "0.1.0"

    def __init__(self, options: dict | None = None, comfyui_config: dict | None = None) -> None:
        options = options or {}
        comfyui_config = comfyui_config or {}
        self.base_url = str(comfyui_config.get("url", "http://127.0.0.1:8188")).rstrip("/")
        self.client_id = uuid.uuid4().hex
        self.request_timeout = float(options.get("timeout_seconds", 600))
        self.ws_enabled = bool(options.get("websocket_progress", True))
        self._binding_dir = PROVIDERS_DIR / str(options.get("binding", "basic_generate")) / "v1"
        self._workflow: dict | None = None
        self._binding: dict | None = None
        self._workflow_hash: str | None = None
        # prompt_id → {"stage","progress","state","error"}（WebSocket 实时层）
        self._live: dict[str, dict] = {}
        self._ws_task: asyncio.Task | None = None

    # ===== Binding =====
    def _load_binding(self) -> tuple[dict, dict]:
        if self._workflow is None or self._binding is None:
            workflow_path = self._binding_dir / "workflow.json"
            binding_path = self._binding_dir / "binding.yaml"
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
                                 "error_type": "", "error_message": ""}
        self._ensure_ws()
        return prompt_id

    # ===== 进度（WebSocket 优先，HTTP history 兜底确认） =====
    async def get_job_status(self, engine_job_id: str) -> EngineJobStatus:
        live = self._live.get(engine_job_id)
        if live and live.get("state") == "failed":
            return EngineJobStatus(state="failed", progress=live.get("progress"),
                                   message=live.get("error_message") or "execution error",
                                   stage=live.get("stage", ""), error_type=live.get("error_type", ""))
        history_state = await self._history_state(engine_job_id)
        if history_state is not None:
            return history_state
        if live:
            return EngineJobStatus(state=live.get("state", "running"), progress=live.get("progress"),
                                   stage=live.get("stage", ""))
        return EngineJobStatus(state="running", progress=None, stage="unknown")

    async def _history_state(self, engine_job_id: str) -> EngineJobStatus | None:
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=15) as client:
                response = await client.get(f"{self.base_url}/history/{engine_job_id}")
                response.raise_for_status()
                history = response.json()
        except httpx.HTTPError:
            return None  # 网络抖动：交给上层瞬态重试逻辑，不直接判 FAILED（规范 §三十四）
        entry = history.get(engine_job_id)
        if not entry:
            return None  # 尚未完成（history 只存已结束任务）
        status_info = entry.get("status") or {}
        if status_info.get("status_str") == "error":
            messages = json.dumps(status_info.get("messages", []), ensure_ascii=False)
            return EngineJobStatus(state="failed", progress=None,
                                   message=messages[:500], stage="error")
        return EngineJobStatus(state="succeeded", progress=1.0, stage="save_image")

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
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=10) as client:
                await client.post(f"{self.base_url}/queue", json={"delete": [engine_job_id]})
                await client.post(f"{self.base_url}/interrupt")
            return True
        except httpx.HTTPError as error:
            logger.warning("ComfyUI 取消请求失败: %s", error)
            return False

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
                live.update(state="running", stage="execution", progress=live.get("progress") or 0.0)
            elif kind == "progress":
                value, maximum = data.get("value", 0), data.get("max", 1) or 1
                live.update(state="running", stage="sampling",
                            progress=round(min(0.99, value / maximum), 3))
            elif kind == "execution_success":
                live.update(state="succeeded", stage="save_image", progress=1.0)
            elif kind == "execution_error":
                node_type = data.get("node_type") or ""
                message = f"{node_type}: {data.get('exception_message', '')}".strip(": ")
                live.update(state="failed", stage="error",
                            error_type=classify_engine_message(message),
                            error_message=message[:400])


