"""Studio Input Registry（Phase 4 Task11）——引擎输入文件登记表。

只登记 **Studio 自己** 上传到引擎 input 目录的文件（NSFWStudio_inputs/），
供 TTL 清理使用；绝不用于枚举/接管用户其他 ComfyUI input 文件。

存储：DataRoot/engine_inputs.json（纯 JSON，进程内单 Worker + 启动清理，无并发写压力）。
写入失败不抛异常（登记失败不应影响真实生成），只记日志。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from app.core.timeutil import utc_now_iso

logger = logging.getLogger(__name__)

REGISTRY_FILENAME = "engine_inputs.json"


class EngineInputRegistry:
    """Studio 引擎输入文件登记（append-only + 显式移除）。"""

    def __init__(self, path: Path) -> None:
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def record(self, *, engine_file: str, image_id: str) -> None:
        """登记一个已上传到引擎侧的文件（best-effort，绝不影响生成链路）。"""
        try:
            entries = self.entries()
            entries.append({
                "file": engine_file,
                "image_id": image_id,
                "uploaded_at": utc_now_iso(),
            })
            self._write(entries)
        except Exception:
            logger.warning("引擎输入登记失败（忽略）: %s", engine_file, exc_info=True)

    def entries(self) -> list[dict]:
        if not self._path.is_file():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            logger.warning("引擎输入登记表损坏，按空表处理: %s", self._path)
            return []
        if not isinstance(data, list):
            return []
        return [entry for entry in data if isinstance(entry, dict) and entry.get("file")]

    def retain(self, kept_files: set[str]) -> None:
        """只保留仍存在的登记项（清理后回收无用条目）。"""
        try:
            entries = [entry for entry in self.entries() if entry.get("file") in kept_files]
            self._write(entries)
        except Exception:
            logger.warning("引擎输入登记表回写失败（忽略）", exc_info=True)

    def _write(self, entries: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        temp_path.replace(self._path)