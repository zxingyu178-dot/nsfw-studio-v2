"""Phase 5.1 真实 smoke：产品路径 img2img（1 张，真实本机 ComfyUI）。

与 production 完全同路径：
    load_settings（config.local.yaml → 真实 DataRoot + 真实 ComfyUI）
    → 输入图导入（真实 DataRoot / sha256 去重）→ resolve_workflow_modules（真实 comfyui 双指纹）
    → job_service.create_job（PipelineValidator 校验 + config 单链）
    → SingleQueueWorker（真实 ComfyUIAdapter + 生产同款 importer/loader）
    → 断言：COMPLETED / kind=processed / parent=输入图 / StageItem.seed / denoise config /
           输出文件存在（images/processed/）

用法（项目根目录）：
    .venv/Scripts/python temp/smoke_phase51.py [输入图路径]
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_settings  # noqa: E402
from app.database.base import make_engine, make_session_factory  # noqa: E402
from app.engine.factory import create_engine_adapter, resolve_workflow_modules  # noqa: E402
from app.main import _make_input_loader, _make_output_importer  # noqa: E402
from app.models import Image, Job, JobStage, JobStageItem  # noqa: E402
from app.services import image_service, job_service  # noqa: E402
from app.services.system_service import bootstrap  # noqa: E402
from app.storage.manager import StorageManager  # noqa: E402
from app.workers.queue_worker import SingleQueueWorker  # noqa: E402
from app.workflows.pipeline import PipelineExecutor  # noqa: E402

DEFAULT_INPUT = PROJECT_ROOT / "temp" / "experimental" / "qwen_img2img" / "inputs" / "structure_test_768.png"
REPORT_PATH = PROJECT_ROOT / "temp" / "smoke_phase51_report.json"


def main() -> int:
    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_INPUT
    input_bytes = input_path.read_bytes()

    settings = load_settings()
    report = bootstrap(settings)
    engine = make_engine(report.database_path)
    session_factory = make_session_factory(engine)
    storage = StorageManager(settings)
    record: dict = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "data_root": str(settings.storage.data_root),
        "input_path": str(input_path),
    }

    # 1) 输入图导入真实 DataRoot（sha256 去重：已存在则复用）
    with session_factory() as session:
        batch = image_service.import_images_batch(
            session, storage, [(input_path.name, "image/png", input_bytes)]
        )
        if batch.imported:
            image_id = batch.imported[0].id
        elif batch.duplicates:
            image_id = batch.duplicates[0]["image_id"]
        else:
            print(f"[FAIL] 输入图导入失败: {batch.failed}")
            return 2
    record["input_image_id"] = image_id
    print(f"[..] 输入图: {image_id}")

    # 2) 解析真实执行身份（comfyui 双指纹）+ 创建 Job（产品同路径）
    with session_factory() as session:
        identities = resolve_workflow_modules(
            settings, [{"module_id": "img2img", "config": {"denoise": 0.55}}]
        )
        record["identity"] = identities[0]
        snapshot = {
            "prompt_mode": "structured",
            "structured_prompt": {
                "style": "watercolor", "scene": "zen garden",
                "extra": "soft morning light, stones",
            },
            "full_prompt": "",
            "negative_prompt": "blurry, low quality, text, watermark",
            "selected_assets": {},
            "width": 768,
            "height": 768,
            "count": 1,
            "seed_mode": "random",
            "workflow_modules": [{"module_id": "img2img", "config": {"denoise": 0.55}}],
            "input_images": [{"role": "source", "image_id": image_id}],
        }
        job, created = job_service.create_job(
            session, source="web", snapshot=snapshot, workflow_modules=identities,
            # 内部直调路径：放宽 Stage 超时（真实队列等待 + 采样），不与模块 config 冲突
            stage_configs=[{"execution_timeout": 7200}],
        )
        job_id = job.id
    record["job_id"] = job_id
    record["job_created"] = created
    print(f"[..] Job: {job_id}（identity={identities[0]['module_id']}@{identities[0]['binding_version']} "
          f"wf={identities[0]['workflow_hash']} bh={identities[0]['binding_hash']}）")

    # 3) 生产同款 Worker 执行（真实 ComfyUI）
    adapter = create_engine_adapter(settings)
    worker = SingleQueueWorker(
        session_factory,
        adapter,
        pipeline=PipelineExecutor(),
        output_importer=_make_output_importer(session_factory, storage),
        input_loader=_make_input_loader(session_factory, storage),
    )
    asyncio.run(worker.process_job(job_id))

    # 4) 断言（真实数据）
    with session_factory() as session:
        final = session.get(Job, job_id)
        stages = list(session.query(JobStage).filter(JobStage.job_id == job_id)
                      .order_by(JobStage.stage_index))
        stage = stages[0]
        stage_items = list(session.query(JobStageItem)
                           .filter(JobStageItem.job_stage_id == stage.id)
                           .order_by(JobStageItem.item_index))
        item = stage_items[0]
        output = session.get(Image, item.output_image_id) if item.output_image_id else None
        output_path = storage.absolutize(output.file_path) if output is not None else None

        checks = {
            "job_completed": final.status == "COMPLETED",
            "stage_module_img2img": stage.module_id == "img2img",
            "stage_completed": stage.status == "COMPLETED",
            "stage_config_denoise": json.loads(stage.config_json).get("denoise") == 0.55,
            "input_frozen": item.input_image_id == image_id,
            "output_exists": bool(output and output_path and output_path.is_file()),
            "output_kind_processed": bool(output and output.kind == "processed"),
            "parent_is_input": bool(output and output.parent_image_id == image_id),
            "stage_item_seed_recorded": item.seed is not None,
            "output_seed_matches": bool(output and output.seed == item.seed),
        }
        record.update({
            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "job_status": final.status,
            "error_type": final.error_type,
            "error_message": final.error_message,
            "stage": {
                "module_id": stage.module_id, "provider": stage.provider,
                "binding_version": stage.binding_version,
                "workflow_hash": stage.workflow_hash, "binding_hash": stage.binding_hash,
                "config": json.loads(stage.config_json),
            },
            "stage_item": {
                "input_image_id": item.input_image_id, "output_image_id": item.output_image_id,
                "seed": item.seed,
            },
            "output_image": {
                "id": output.id if output else None,
                "kind": output.kind if output else None,
                "parent_image_id": output.parent_image_id if output else None,
                "file_path": output.file_path if output else None,
                "exists": bool(output_path and output_path.is_file()),
                "dimensions": [output.width, output.height] if output else None,
                "seed": output.seed if output else None,
            },
            "checks": checks,
        })

    REPORT_PATH.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    ok = all(record["checks"].values())
    print(f"[{'OK' if ok else 'FAIL'}] status={record['job_status']} checks={json.dumps(record['checks'], ensure_ascii=False)}")
    print(f"[..] 报告: {REPORT_PATH}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())