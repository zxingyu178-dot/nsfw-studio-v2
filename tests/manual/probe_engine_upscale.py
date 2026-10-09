"""引擎健康探测：高清链（仅 64MB UltraSharp 小模型，不加载 T5/GGUF 大模型）。

用途：在真实照片 img2img 重试前，低成本判定引擎是否可用、以及问题是否只出在大模型加载。
走产品同路径（真实 DataRoot + 真实 ComfyUIAdapter + 生产同款 Worker）。

用法（项目根目录）：
    .venv/Scripts/python tests/manual/probe_engine_upscale.py <小图路径>
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
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


def main() -> int:
    input_path = Path(sys.argv[1]).resolve()
    input_bytes = input_path.read_bytes()

    settings = load_settings()
    report = bootstrap(settings)
    engine = make_engine(report.database_path)
    session_factory = make_session_factory(engine)
    storage = StorageManager(settings)
    started = time.monotonic()

    with session_factory() as session:
        batch = image_service.import_images_batch(
            session, storage, [(input_path.name, "image/png", input_bytes)]
        )
        image_id = (batch.imported[0].id if batch.imported else batch.duplicates[0]["image_id"])
    with session_factory() as session:
        identities = resolve_workflow_modules(settings, [{"module_id": "upscale"}])
        job, _ = job_service.create_job(
            session, source="web",
            snapshot={
                "prompt_mode": "structured", "structured_prompt": {}, "full_prompt": "",
                "negative_prompt": "", "selected_assets": {},
                "width": 64, "height": 64, "count": 1, "seed_mode": "random", "seed": None,
                "workflow_modules": [{"module_id": "upscale"}],
            },
            workflow_modules=identities, job_kind="process", input_image_ids=[image_id],
            stage_configs=[{"execution_timeout": 3600}],
        )
        job_id = job.id

    adapter = create_engine_adapter(settings)
    worker = SingleQueueWorker(
        session_factory, adapter, pipeline=PipelineExecutor(),
        output_importer=_make_output_importer(session_factory, storage),
        input_loader=_make_input_loader(session_factory, storage),
    )
    asyncio.run(worker.process_job(job_id))

    with session_factory() as session:
        final = session.get(Job, job_id)
        stage = session.query(JobStage).filter(JobStage.job_id == job_id).first()
        item = (session.query(JobStageItem)
                .filter(JobStageItem.job_stage_id == stage.id).first()) if stage else None
        output = session.get(Image, item.output_image_id) if item and item.output_image_id else None
        ok = final.status == "COMPLETED" and output is not None and output.kind == "upscaled"
        print(json.dumps({
            "probe": "upscale-small-model", "job_id": job_id,
            "status": final.status, "error_type": final.error_type, "error_message": final.error_message,
            "elapsed_s": round(time.monotonic() - started, 1),
            "output_kind": output.kind if output else None,
            "output_dims": [output.width, output.height] if output else None,
            "ok": ok,
        }, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())