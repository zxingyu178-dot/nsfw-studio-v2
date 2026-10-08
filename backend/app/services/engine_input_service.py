"""引擎输入缓存治理（Phase 4 Task11）。

背景：处理型 Stage（高清放大等）会把待处理图片上传到引擎 input 目录的
``NSFWStudio_inputs/`` 子目录；ComfyUI 没有"安全删除 input 文件"的公开 API，
上传文件会随使用逐步积累。

规则（固定）：
- 只操作 ``NSFWStudio_inputs/``（Studio 专属子目录），**绝不触碰其他 input 文件**；
- 只清理 Studio Input Registry 登记过、且无 RUNNING / INTERRUPTED Stage 引用的文件；
- TTL 未到不清理；未配置 ``comfyui.input_dir`` 时安全跳过（无法确认路径就不动文件）；
- 禁止 ``rm -rf input`` 之类的目录级操作——只删除单个确认属于 Studio 的文件。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.engine.input_registry import REGISTRY_FILENAME, EngineInputRegistry
from app.models import JobStage, JobStageItem

logger = logging.getLogger(__name__)

DEFAULT_INPUT_TTL_SECONDS = 24 * 3600
STUDIO_INPUT_SUBDIR = "NSFWStudio_inputs"


def _parse_uploaded_at(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def cleanup_engine_inputs(settings: Settings, session_factory: sessionmaker) -> dict:
    """TTL 清理引擎输入文件（best-effort；返回统计，不抛异常给调用方）。"""
    input_dir_raw = settings.comfyui.get("input_dir")
    if not input_dir_raw:
        return {"skipped": True, "reason": "未配置 comfyui.input_dir，无法安全清理引擎输入"}

    input_dir = Path(str(input_dir_raw)).resolve()
    ttl_seconds = int(settings.comfyui.get("input_ttl_seconds", DEFAULT_INPUT_TTL_SECONDS))
    registry = EngineInputRegistry(settings.storage.data_root / REGISTRY_FILENAME)
    entries = registry.entries()
    if not entries:
        return {"skipped": False, "deleted": 0, "kept": 0}

    # 活动引用保护：RUNNING / INTERRUPTED Stage 正在使用（或可能仍在使用）的输入图片
    with session_factory() as session:
        rows = session.execute(
            select(JobStageItem.input_image_id)
            .join(JobStage, JobStage.id == JobStageItem.job_stage_id)
            .where(
                JobStageItem.status.in_(("RUNNING", "INTERRUPTED")),
                JobStageItem.input_image_id.is_not(None),
            )
        ).scalars()
        active_inputs = {image_id for image_id in rows if image_id}

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl_seconds)
    deleted = 0
    kept_files: set[str] = set()
    for entry in entries:
        engine_file = str(entry.get("file") or "")
        image_id = str(entry.get("image_id") or "")
        uploaded_at = _parse_uploaded_at(entry.get("uploaded_at"))

        # 只处理 NSFWStudio_inputs 子目录内的相对路径（其余一律不动）
        if not engine_file.startswith(f"{STUDIO_INPUT_SUBDIR}/"):
            kept_files.add(engine_file)
            continue
        target = (input_dir / engine_file).resolve()
        if not target.is_relative_to(input_dir) or not target.is_file():
            continue  # 越界或已不存在 → 回收登记项
        if uploaded_at is None or uploaded_at > cutoff:
            kept_files.add(engine_file)
            continue
        if image_id and image_id in active_inputs:
            kept_files.add(engine_file)
            continue
        try:
            target.unlink()
            deleted += 1
        except OSError:
            logger.warning("引擎输入文件删除失败（保留登记）: %s", target, exc_info=True)
            kept_files.add(engine_file)

    registry.retain(kept_files)
    return {"skipped": False, "deleted": deleted, "kept": len(kept_files)}