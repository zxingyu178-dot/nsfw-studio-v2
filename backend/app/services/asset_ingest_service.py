"""W4.1 AssetIngestService：所有新图片写入的唯一正式入口。

现有 ``image_service`` 的批次事务仍是底层实现；本模块是新代码/新工具的正式边界，
禁止其他模块自行 INSERT ``images`` 或直接写 DataRoot 资产目录。

规则：
- 引擎输出 / 手动导入 / 图片处理结果统一走这里；
- 每张图必须有 sha256、mime_type、file_size、asset_type、created_at；
- 同批整体成功或整体失败；
- 不覆盖原图，派生图必须带 parent_asset_id。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.engine.base import EngineOutputFile
from app.models import Image, Job, JobItem, JobStageItem
from app.services import image_service
from app.storage.manager import StorageManager


@dataclass
class AssetIngestResult:
    imported: list[Image]
    duplicates: list[dict[str, str]]
    failed: list[dict[str, str]]


def ingest_engine_outputs(
    session: Session,
    storage: StorageManager,
    outputs: list[EngineOutputFile],
    *,
    job: Job,
    stage_item: JobStageItem,
) -> list[str]:
    """Worker 输出导入（唯一入口；内部走 image_service 的批次事务）。"""
    return image_service.import_adapter_outputs(session, storage, job, stage_item, outputs)


def ingest_uploads(
    session: Session,
    storage: StorageManager,
    uploads: list[tuple[str | None, str | None, bytes]],
) -> AssetIngestResult:
    """手动/批量图片导入（sha256 去重、部分失败继续）。"""
    result = image_service.import_images_batch(session, storage, uploads)
    return AssetIngestResult(
        imported=list(result.imported), duplicates=result.duplicates, failed=result.failed,
    )


def ingest_single(
    session: Session,
    storage: StorageManager,
    *,
    data: bytes,
    kind: str = "original",
    source: str = "engine",
    job: Job | None = None,
    item: JobItem | None = None,
    seed: int | None = None,
    parent_asset_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Image:
    """单张图片处理结果统一入库（未来图片处理工具的正式入口）。"""
    prepared = image_service.prepare_image_output(data, kind=kind)
    images = image_service.import_outputs_transaction(
        session, storage, [prepared], job=job, item=item, seed=seed, source=source,
        kind=kind, parent_image_id=parent_asset_id, metadata={
            **(metadata or {}), "parent_asset_id": parent_asset_id,
        },
    )
    return images[0]
