"""W4.1 GenerationProvenanceService：Job → 工作流 / 模型 / Prompt / Seed / 输出资产。

只读投影，不修改历史 Job。历史 Job 若缺少 model_snapshot，标记 ``derived`` 或
``unavailable``，绝不伪造。
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Image, Job, JobItem, JobStage, JobStageItem
from app.services import job_service


def _snapshot(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except ValueError:
        return {}


def job_provenance(session: Session, job_id: str) -> dict[str, Any]:
    job = job_service.get_job(session, job_id)
    workflow = _snapshot(job.workflow_snapshot_json)
    workbench = _snapshot(job.workbench_snapshot_json)
    modules: list[dict[str, Any]] = []
    missing: list[str] = []
    for module in workflow.get("modules") or []:
        if not isinstance(module, dict):
            continue
        model_snapshot = module.get("model_snapshot")
        if not isinstance(model_snapshot, list) or not model_snapshot:
            model_snapshot = []
            missing.append(f"{module.get('module_id')}: model_snapshot 缺失（历史 Job）")
        modules.append({
            "module_id": module.get("module_id"),
            "module_version": module.get("module_version"),
            "provider": module.get("provider"),
            "binding_version": module.get("binding_version"),
            "workflow_hash": module.get("workflow_hash"),
            "binding_hash": module.get("binding_hash"),
            "hash_algorithm": module.get("hash_algorithm") or "raw-bytes-v1",
            "model_snapshot": model_snapshot,
        })

    prompt = {
        "prompt_id": workbench.get("source_prompt_id"),
        "prompt_version_id": workbench.get("source_prompt_version_id"),
        "positive_prompt": job.positive_prompt_snapshot,
        "negative_prompt": job.negative_prompt_snapshot,
        "structured_prompt": _snapshot(job.structured_prompt_snapshot),
        "source": "job_snapshot",
    }
    if not prompt["prompt_id"]:
        missing.append("prompt: 无 source_prompt_id（历史 Job/导入路径）")

    items = []
    for item in session.execute(
        select(JobItem).where(JobItem.job_id == job.id).order_by(JobItem.item_index)
    ).scalars():
        items.append({
            "generation_item_id": item.id,
            "item_index": item.item_index,
            "seed": item.seed,
            "status": item.status,
            "image_id": item.image_id,
        })

    stages = []
    for stage in session.execute(
        select(JobStage).where(JobStage.job_id == job.id).order_by(JobStage.stage_index)
    ).scalars():
        stage_items = []
        for stage_item in session.execute(
            select(JobStageItem).where(JobStageItem.job_stage_id == stage.id).order_by(JobStageItem.item_index)
        ).scalars():
            stage_items.append({
                "stage_item_id": stage_item.id,
                "generation_item_id": stage_item.job_item_id,
                "input_asset_id": stage_item.input_image_id,
                "output_asset_id": stage_item.output_image_id,
                "seed": stage_item.seed,
                "status": stage_item.status,
            })
        stages.append({
            "stage_id": stage.id,
            "stage_index": stage.stage_index,
            "module_id": stage.module_id,
            "binding_version": stage.binding_version,
            "workflow_hash": stage.workflow_hash,
            "binding_hash": stage.binding_hash,
            "status": stage.status,
            "items": stage_items,
        })

    output_assets = [
        {
            "asset_id": image.id,
            "storage_key": image.file_path,
            "kind": image.kind,
            "sha256": image.sha256,
            "seed": image.seed,
            "parent_asset_id": image.parent_image_id,
        }
        for image in session.execute(select(Image).where(Image.job_id == job.id)).scalars()
    ]

    return {
        "job_id": job.id,
        "status": job.status,
        "job_kind": job.job_kind,
        "module_id": job.module_id,
        "module_version": job.module_version,
        "provider": job.provider,
        "binding_version": job.binding_version,
        "workflow_hash": job.workflow_hash,
        "binding_hash": job.binding_hash,
        "hash_algorithm": (modules[0]["hash_algorithm"] if modules else None),
        "engine_version": workflow.get("engine_version"),
        "modules": modules,
        "prompt": prompt,
        "generation_parameters": _snapshot(job.generation_settings_json),
        "items": items,
        "stages": stages,
        "output_assets": output_assets,
        "output_asset_ids": [asset["asset_id"] for asset in output_assets],
        "missing_fields": missing,
        "created_at": job.created_at,
        "finished_at": job.finished_at,
    }
