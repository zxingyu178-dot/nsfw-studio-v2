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


def _format_prefix(template: str, values: dict[str, str]) -> str:
    """渲染 save_image_prefix 模板；未知占位符原样保留（不抛异常）。"""

    class _Safe(dict):
        def __missing__(self, key: str) -> str:
            return "{" + key + "}"

    try:
        return template.format_map(_Safe(values))
    except (ValueError, IndexError):
        return template


class ComfyUIAdapter(EngineAdapter):
    name = "comfyui"
    version = "0.1.0"

    def __init__(
        self,
        options: dict | None = None,
        comfyui_config: dict | None = None,
        *,
        input_registry=None,
    ) -> None:
        options = options or {}
        comfyui_config = comfyui_config or {}
        self.base_url = str(comfyui_config.get("url", "http://127.0.0.1:8188")).rstrip("/")
        self.client_id = uuid.uuid4().hex
        self.request_timeout = float(options.get("timeout_seconds", 600))
        self.ws_enabled = bool(options.get("websocket_progress", True))
        # §九：可选的 ComfyUI output 目录（仅 config.local.yaml），用于文件级恢复兜底
        output_dir = comfyui_config.get("output_dir")
        self.output_dir = Path(output_dir) if output_dir else None
        # Task11：Studio Input Registry（只登记自己上传的输入文件，供 TTL 清理）
        self.input_registry = input_registry
        # Phase 3 §0.2：binding 属于每次请求；缓存 key = (module_id, binding_version)
        # 缓存值 = (workflow, binding, workflow_hash, binding_hash)
        self._bindings: dict[tuple[str, str], tuple[dict, dict, str, str]] = {}
        # prompt_id → {"stage","progress","state","error","updated"}（WebSocket 实时层）
        self._live: dict[str, dict] = {}
        self._missing_polls: dict[str, int] = {}
        self._ws_task: asyncio.Task | None = None

    # ===== Binding（按请求动态加载；Phase 3 §0.2/§0.3；Phase 4 Task1 完整指纹） =====
    @staticmethod
    def binding_dir(module_id: str, binding_version: str) -> Path:
        """provider binding 目录：workflows/providers/comfyui/<module_id>/<binding_version>/"""
        return PROVIDERS_DIR / module_id / binding_version

    @staticmethod
    def _validate_binding_self_description(ref, binding: dict, directory: Path) -> None:
        """Task1：provider binding 自描述必须与请求身份一致，否则直接拒绝。

        binding.module == request.module_id；binding.provider == request.provider；
        binding.binding_version == 目录版本（即 request.binding_version）。
        """
        problems: list[str] = []
        declared_module = binding.get("module")
        declared_provider = binding.get("provider")
        declared_version = binding.get("binding_version")
        if declared_module != ref.module_id:
            problems.append(f"module: 声明={declared_module!r} 请求={ref.module_id!r}")
        if declared_provider != ref.provider:
            problems.append(f"provider: 声明={declared_provider!r} 请求={ref.provider!r}")
        if declared_version != ref.binding_version:
            problems.append(f"binding_version: 声明={declared_version!r} 目录={ref.binding_version!r}")
        if problems:
            raise EngineError(
                "BINDING_IDENTITY_MISMATCH",
                f"provider binding 自描述与请求身份不一致（{directory}）: {'; '.join(problems)}",
            )

    def load_binding(self, ref) -> tuple[dict, dict, str, str]:
        """按请求身份加载 (workflow, binding, workflow_hash, binding_hash)。

        - 缓存 key = (module_id, binding_version)，一个 Adapter 服务所有模块；
        - 已投入使用的 binding 目录视为 **immutable**：请求携带的 workflow_hash /
          binding_hash 与磁盘不一致 → WORKFLOW_HASH_MISMATCH / BINDING_HASH_MISMATCH，
          禁止静默执行（§0.3 / Task1）；
        - 首次加载同时校验 binding 自描述（Task1）。
        """
        key = (ref.module_id, ref.binding_version)
        cached = self._bindings.get(key)
        if cached is None:
            directory = self.binding_dir(ref.module_id, ref.binding_version)
            workflow_path = directory / "workflow.json"
            binding_path = directory / "binding.yaml"
            if not workflow_path.is_file() or not binding_path.is_file():
                raise EngineError("BINDING_NOT_FOUND", f"provider binding 不存在: {directory}")
            workflow = json.loads(workflow_path.read_text(encoding="utf-8"))
            binding = yaml.safe_load(binding_path.read_text(encoding="utf-8"))
            self._validate_binding_self_description(ref, binding, directory)
            workflow_hash = hashlib.sha256(workflow_path.read_bytes()).hexdigest()[:16]
            binding_hash = hashlib.sha256(binding_path.read_bytes()).hexdigest()[:16]
            cached = (workflow, binding, workflow_hash, binding_hash)
            self._bindings[key] = cached
        workflow, binding, workflow_hash, binding_hash = cached
        if ref.workflow_hash and ref.workflow_hash != workflow_hash:
            raise EngineError(
                "WORKFLOW_HASH_MISMATCH",
                f"workflow_hash 不一致（binding 视为 immutable，修改请新建版本）: "
                f"job={ref.workflow_hash} 磁盘={workflow_hash} ({key[0]}/{key[1]})",
            )
        if ref.binding_hash and ref.binding_hash != binding_hash:
            raise EngineError(
                "BINDING_HASH_MISMATCH",
                f"binding_hash 不一致（binding.yaml 视为 immutable，修改请新建版本）: "
                f"job={ref.binding_hash} 磁盘={binding_hash} ({key[0]}/{key[1]})",
            )
        return cached

    def binding_identity(self, module_id: str, binding_version: str) -> tuple[str, str, str]:
        """返回 (实际 binding_version, workflow_hash, binding_hash)，供 Job 创建时记录真实身份。"""
        from app.engine.base import EngineBindingRef

        _workflow, binding, workflow_hash, binding_hash = self.load_binding(
            EngineBindingRef(module_id=module_id, provider="comfyui", binding_version=binding_version)
        )
        return str(binding.get("binding_version", binding_version)), workflow_hash, binding_hash

    def _build_prompt(self, request: EngineJobRequest, workflow: dict, binding: dict) -> dict:
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
        template = str(binding.get("save_image_prefix", "NSFWStudio"))
        metadata = dict(request.metadata or {})
        job_id = str(metadata.get("job_id", ""))
        item_id = str(metadata.get("stage_item_id") or metadata.get("item_id") or "")
        values = {
            "date": _dt.date.today().strftime("%Y%m%d"),
            "job_id": job_id,
            "job_short": job_id[-8:] if job_id else "unknown",
            "stage": str(metadata.get("stage_index", 0)),
            "item_short": item_id[-8:] if item_id else "unknown",
            "seed": str(params.get("seed", "")),
        }
        prompt[save_node]["inputs"]["filename_prefix"] = _format_prefix(template, values)
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

    # ===== 上传输入图片（Task4 正式契约；§十三：仅使用 Studio 唯一命名，便于只清理自己的文件） =====
    async def upload_input_image(self, *, image_id: str, file_name: str, data: bytes) -> str:
        """上传待处理图片到 ComfyUI input（/upload/image），返回引擎侧引用名。

        命名由 Studio 决定（{image_id}{suffix}，subfolder=NSFWStudio_inputs），
        同时登记到 Studio Input Registry（Task11：TTL 清理只处理登记过的文件）。
        """
        suffix = Path(file_name).suffix or ".png"
        filename = f"{image_id}{suffix}"
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=60) as client:
                response = await client.post(
                    f"{self.base_url}/upload/image",
                    files={"image": (filename, data, "application/octet-stream")},
                    data={"overwrite": "true", "type": "input", "subfolder": "NSFWStudio_inputs"},
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.ConnectError as error:
            raise EngineError("ENGINE_OFFLINE", f"ComfyUI 连接失败: {error}") from error
        except httpx.HTTPError as error:
            raise EngineError("ENGINE_NETWORK", f"ComfyUI 上传失败: {error}", transient=True) from error
        name = payload.get("name")
        if not name:
            raise EngineError("UNKNOWN_ENGINE_ERROR", f"上传图片未返回文件名: {payload}")
        subfolder = payload.get("subfolder") or ""
        engine_file = f"{subfolder}/{name}" if subfolder else str(name)
        if self.input_registry is not None:
            self.input_registry.record(engine_file=engine_file, image_id=image_id)
        return engine_file

    # ===== 文件级恢复兜底（§九：只扫描 Studio 自己命名的输出） =====
    def scan_stage_outputs(self, ref, *, job_id: str, stage_index: int,
                           stage_item_id: str) -> list[EngineOutputFile]:
        """在 ComfyUI output 目录中扫描某 StageItem 自己命名的输出（marker 由 binding 前缀模板渲染）。

        ComfyUI 重启后 /history 丢失时，只要输出文件已写完，Studio 仍可核对结果；
        绝不允许扫描/接管用户普通 ComfyUI 图片——目录必须由 provider binding 的
        save_image_prefix 模板推导，且必须位于 output_dir 之内。
        """
        if self.output_dir is None:
            return []
        _workflow, binding, _hash, _binding_hash = self.load_binding(ref)
        template = str(binding.get("save_image_prefix", "NSFWStudio"))
        marker = _format_prefix(template, {
            "date": _dt.date.today().strftime("%Y%m%d"),
            "job_id": job_id,
            "job_short": job_id[-8:] if job_id else "unknown",
            "stage": str(stage_index),
            "item_short": stage_item_id[-8:] if stage_item_id else "unknown",
            "seed": "",
        })
        output_root = self.output_dir.resolve()
        base = (self.output_dir / marker).resolve()
        if not base.is_relative_to(output_root):
            raise EngineError("STORAGE_ERROR", f"非法扫描路径: {marker}")
        if not base.is_dir():
            return []
        files = sorted(
            path for path in base.iterdir()
            if path.is_file() and path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
        )
        return [EngineOutputFile(filename=path.name, data=path.read_bytes()) for path in files]

    # ===== 提交 =====
    async def submit_job(self, request: EngineJobRequest) -> str:
        workflow, binding, _hash, _binding_hash = self.load_binding(request.binding)
        prompt = self._build_prompt(request, workflow, binding)
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


