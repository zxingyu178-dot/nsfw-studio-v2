"""ImageService（Phase 2C，规范 §三十九、§四十、§四十一-§四十三；Phase 3 §十四 泛化）。

引擎输出导入流程（规范 §四十）::

    Engine 输出字节 → Studio temp → 校验（magic bytes + 尺寸解析）
    → 原子移动到 DataRoot/images/<kind 目录>/<img_id>/ → Image DB 登记

kind 决定存储目录（original→images/originals / upscaled→images/upscaled /
processed→images/processed）；高清图必须记录 parent_image_id（§十四）。

ComfyUI output 目录不作为 Studio 永久图库；数据库只存 DataRoot 相对路径。
"""
from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.core.filetypes import (
    image_dimensions,
    mime_for_suffix,
    sha256_hex,
    sniff_image_format,
    validate_image_upload,
)
from app.core.ids import IMAGE, new_id
from app.core.timeutil import utc_now_iso
from app.engine.base import EngineError, EngineOutputFile
from app.models import IMAGE_STATUSES, Image, Job, JobItem, JobStage, JobStageItem
from app.storage.manager import StorageManager
from app.workflows.base import InputImageRef

IMAGE_SOURCES = ("comfyui", "mock", "import", "engine")
IMAGE_KIND_DIRS = {
    "original": "images/originals",
    "upscaled": "images/upscaled",
    "processed": "images/processed",
}

logger = logging.getLogger(__name__)

# Phase 0.11.1 统一审核状态语义：
# - 审核 status 只有 NEW/KEEP/REJECT/ARCHIVED；favorite 是独立 bool，可与任意状态共存。
# - FAVORITE 不再作为应用层写入的 status（DB CHECK 保留 FAVORITE 兼容历史，不重写 0016）；
#   收藏一律走 favorite 列。新旧列必须同源双写，杜绝"旧接口只改旧字段"的分裂。
# 新 status → 旧 review_status（ARCHIVED 在旧体系按"保留"计）
_STATUS_TO_LEGACY_REVIEW = {
    "NEW": "UNREVIEWED",
    "KEEP": "KEPT",
    "REJECT": "REJECTED",
    "ARCHIVED": "KEPT",
}
# 旧 review_status → 新 status（旧 PATCH /review 接口仍需与新 status 同源）
_LEGACY_REVIEW_TO_STATUS = {
    "UNREVIEWED": "NEW",
    "KEPT": "KEEP",
    "REJECTED": "REJECT",
}


def _kind_dir(kind: str) -> str:
    directory = IMAGE_KIND_DIRS.get(kind)
    if directory is None:
        raise ValidationError(f"非法图片 kind: {kind}", code="IMAGE_KIND_INVALID")
    return directory


def get_image(session: Session, image_id: str) -> Image:
    image = session.get(Image, image_id)
    if image is None:
        raise NotFoundError("图片不存在", code="IMAGE_NOT_FOUND")
    return image


def get_versions(session: Session, image_id: str) -> dict[str, Any]:
    """父子关系（§十九）：返回 {image, parent, children}，支持原图/高清之间切换。"""
    image = get_image(session, image_id)
    parent = session.get(Image, image.parent_image_id) if image.parent_image_id else None
    children = list(session.execute(
        select(Image).where(Image.parent_image_id == image_id).order_by(Image.created_at)
    ).scalars())
    return {"image": image, "parent": parent, "children": children}


def root_image_of(session: Session, image: Image) -> Image:
    """沿 parent_image_id 向上找到根图（original / 外部导入），带环保护。"""
    root = image
    visited: set[str] = {image.id}
    while root.parent_image_id:
        if root.parent_image_id in visited:
            break  # 环保护（防御性；正常数据不可能）
        parent = session.get(Image, root.parent_image_id)
        if parent is None:
            break
        visited.add(parent.id)
        root = parent
    return root


def get_provenance(session: Session, image_id: str) -> dict[str, Any]:
    """Image Provenance（Task10）：返回图片的完整溯源信息（含 module/binding/双指纹/seed）。

    直接执行来源（job/stage）优先于 metadata 快照；老图片（无 StageItem）回落 metadata。
    """
    image = get_image(session, image_id)
    root = root_image_of(session, image)
    parent = session.get(Image, image.parent_image_id) if image.parent_image_id else None
    metadata = json.loads(image.metadata_json or "{}")

    stage_item = None
    if image.job_item_id:
        stage_item = session.execute(
            select(JobStageItem).where(JobStageItem.output_image_id == image.id)
        ).scalars().first()
        if stage_item is None:
            # 兜底：取该 JobItem 最后一个 StageItem（历史上唯一的产出 Stage）
            stage_item = session.execute(
                select(JobStageItem)
                .join(JobStage, JobStage.id == JobStageItem.job_stage_id)
                .where(JobStageItem.job_item_id == image.job_item_id)
                .order_by(JobStage.stage_index.desc())
            ).scalars().first()
    stage = session.get(JobStage, stage_item.job_stage_id) if stage_item is not None else None

    # Phase 0.12 Task12：轻量 Image Provenance —— 工作台最初从哪个 Recipe 打开。
    # 经 Image → Job.workbench_snapshot_json 读出；旧 Job / 非 Recipe 来源 → None（前端据此隐藏该行）。
    source_recipe_id = None
    source_recipe_version_id = None
    if image.job_id:
        job = session.get(Job, image.job_id)
        if job is not None:
            try:
                snapshot = json.loads(job.workbench_snapshot_json or "{}")
            except ValueError:
                snapshot = {}
            if isinstance(snapshot, dict):
                source_recipe_id = snapshot.get("source_recipe_id")
                source_recipe_version_id = snapshot.get("source_recipe_version_id")

    scale = None
    if parent is not None and parent.width > 0 and image.width > 0 and parent.width != image.width:
        scale = max(1, round(image.width / parent.width))
    return {
        "image_id": image.id,
        "kind": image.kind,
        "parent_image_id": image.parent_image_id,
        "root_image_id": root.id,
        "scale": scale,
        "job_id": image.job_id,
        "job_item_id": image.job_item_id,
        "stage_id": stage.id if stage is not None else metadata.get("stage_id"),
        "stage_index": stage.stage_index if stage is not None else metadata.get("stage_index"),
        "stage_item_id": stage_item.id if stage_item is not None else metadata.get("stage_item_id"),
        "module_id": stage.module_id if stage is not None else metadata.get("module_id"),
        "module_version": stage.module_version if stage is not None else metadata.get("module_version"),
        "provider": stage.provider if stage is not None else metadata.get("provider"),
        "binding_version": stage.binding_version if stage is not None else metadata.get("binding_version"),
        "workflow_hash": stage.workflow_hash if stage is not None else metadata.get("workflow_hash"),
        "binding_hash": stage.binding_hash if stage is not None else metadata.get("binding_hash"),
        "seed": image.seed,
        "source_recipe_id": source_recipe_id,
        "source_recipe_version_id": source_recipe_version_id,
    }


@dataclass(frozen=True)
class PreparedImageOutput:
    """已校验、已分配身份的待导入输出（尚未落盘/入库）。"""

    image_id: str
    data: bytes
    suffix: str
    relative_path: str
    width: int
    height: int
    # Phase 5：外部导入来源哈希与原始文件名（引擎输出为 None）
    sha256: str | None = None
    imported_filename: str | None = None


def prepare_image_output(data: bytes, *, kind: str = "original") -> PreparedImageOutput:
    """校验输出字节并生成 Image 身份与元数据（不落盘、不入库）。

    Phase 2.2 §1：整批导入必须先对全部输出做本步骤，任一不合法即整批失败，
    绝不允许"先落了一张、后一张校验失败"的半成功状态。
    Phase 3 §十四：kind 决定正式目录（original/upscaled/processed）。
    """
    if not data:
        raise ValidationError("输出文件为空", code="OUTPUT_MISSING")
    fmt = sniff_image_format(data)
    if fmt is None:
        raise ValidationError("引擎输出不是可识别的图片", code="OUTPUT_MISSING")
    dimensions = image_dimensions(data)
    if dimensions is None:
        raise ValidationError("无法解析图片尺寸", code="OUTPUT_MISSING")
    width, height = dimensions
    suffix = ".png" if fmt == "png" else (".jpg" if fmt == "jpeg" else ".webp")
    image_id = new_id(IMAGE)
    directory = _kind_dir(kind)
    return PreparedImageOutput(
        image_id=image_id,
        data=data,
        suffix=suffix,
        relative_path=f"{directory}/{image_id}/{kind}{suffix}",
        width=width,
        height=height,
    )


def prepare_import_image(data: bytes, *, filename: str | None, content_type: str | None) -> PreparedImageOutput:
    """外部导入图片校验并生成 Image 身份（Phase 5 §三/§五）。

    - 扩展名 + MIME + magic bytes + 大小（validate_image_upload）；
    - 像素尺寸必须可解析（PNG/JPEG/WEBP），否则拒绝——避免图库出现 0x0 图片；
    - 统一复制进 DataRoot/images/originals/，**绝不引用用户原始路径**；
    - sha256 随 PreparedImageOutput 携带（§六：去重不以文件名为依据）。
    """
    suffix = validate_image_upload(filename, content_type, data)
    dimensions = image_dimensions(data)
    if dimensions is None:
        raise ValidationError("无法解析图片尺寸", code="IMAGE_INVALID")
    width, height = dimensions
    image_id = new_id(IMAGE)
    return PreparedImageOutput(
        image_id=image_id,
        data=data,
        suffix=suffix,
        relative_path=f"{IMAGE_KIND_DIRS['original']}/{image_id}/original{suffix}",
        width=width,
        height=height,
        sha256=sha256_hex(data),
        imported_filename=(filename or "").strip() or None,
    )


@dataclass
class ImageImportBatchResult:
    """外部导入批次结果（§二十三：单张失败不影响整批，返回可报告的明细）。"""

    imported: list[Image]
    duplicates: list[dict[str, str]]
    failed: list[dict[str, str]]


def find_image_by_sha256(session: Session, digest: str) -> Image | None:
    return session.execute(select(Image).where(Image.sha256 == digest)).scalars().first()


def import_images_batch(
    session: Session,
    storage: StorageManager,
    uploads: list[tuple[str | None, str | None, bytes]],
) -> ImageImportBatchResult:
    """外部图片批量导入（Phase 5 §三/§六/§二十三）：逐张校验、hash 去重、部分失败继续。

    - 重复文件（sha256 已存在）：不创建第二份，返回 duplicate + 已存在的 image_id；
    - 单张失败（非法/超限/损坏）：记入 failed 继续处理下一张，绝不整批失败；
    - 每张成功图片独立事务落库（单张校验失败不会留下半张图片）；
    - Phase 5.1 Task9：DB 部分唯一索引兜底并发竞态——IntegrityError 时重新查询
      并返回已存在图片（duplicate），而不是 500。
    """
    imported: list[Image] = []
    duplicates: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []

    for filename, content_type, data in uploads:
        display_name = (filename or "").strip() or "(未命名)"
        prepared: PreparedImageOutput | None = None
        try:
            prepared = prepare_import_image(data, filename=filename, content_type=content_type)
            existing = find_image_by_sha256(session, prepared.sha256 or "")
            if existing is not None:
                duplicates.append({
                    "filename": display_name,
                    "image_id": existing.id,
                    "sha256": prepared.sha256 or "",
                })
                continue
            images = import_outputs_transaction(
                session, storage, [prepared], source="import", kind="original",
                metadata={"sha256": prepared.sha256, "imported_filename": prepared.imported_filename},
            )
            imported.append(images[0])
        except IntegrityError:
            # Task9：并发导入竞态——另一请求先落库，唯一索引拒绝本行；
            # 回滚后返回已存在图片，绝不把并发当 500 处理
            session.rollback()
            existing = (
                find_image_by_sha256(session, prepared.sha256 or "")
                if prepared is not None else None
            )
            if existing is not None:
                duplicates.append({
                    "filename": display_name,
                    "image_id": existing.id,
                    "sha256": prepared.sha256 or "",
                })
            else:
                failed.append({
                    "filename": display_name,
                    "error_code": "IMPORT_CONFLICT",
                    "message": "并发导入冲突，请重试",
                })
        except Exception as error:  # noqa: BLE001 —— 单张失败必须继续处理其余文件
            session.rollback()
            failed.append({
                "filename": display_name,
                "error_code": getattr(error, "code", "IMPORT_FAILED"),
                "message": getattr(error, "message", str(error)),
            })
    return ImageImportBatchResult(imported=imported, duplicates=duplicates, failed=failed)


def file_sha256(session: Session, storage: StorageManager, image: Image) -> str | None:
    """图片文件 hash（§九：Recipe 输入图快照必须带 file hash）。

    优先使用导入时记录的 images.sha256；否则现算（引擎生成图）；文件缺失返回 None。
    """
    if image.sha256:
        return image.sha256
    path = storage.absolutize(image.file_path)
    if not path.is_file():
        return None
    return sha256_hex(path.read_bytes())


def import_outputs_transaction(
    session: Session,
    storage: StorageManager,
    prepared: list[PreparedImageOutput],
    *,
    job: Job | None = None,
    item: JobItem | None = None,
    seed: int | None = None,
    source: str = "comfyui",
    kind: str = "original",
    parent_image_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[Image]:
    """一个输出批次"整体成功或整体失败"导入（Phase 2.2 §1，P0）。

    顺序：全部写 temp → 全部移动到正式目录 → 单事务写入全部 Image → commit。
    任一步失败：回滚 DB + 删除本批次已创建的全部正式文件 + 清理 temp。
    禁止在批次循环里调用任何内部 commit 的单图函数。
    """
    if source not in IMAGE_SOURCES:
        raise ValidationError(f"非法图片来源: {source}", code="IMAGE_SOURCE_INVALID")
    directory = _kind_dir(kind)
    if not prepared:
        return []

    temp_paths: list[Path] = []
    created_dirs: list[Path] = []
    try:
        storage.temp_dir.mkdir(parents=True, exist_ok=True)
        # 1. 全部写 temp（尚未接触正式目录）
        for entry in prepared:
            temp_path = storage.temp_dir / f"import_{uuid.uuid4().hex}{entry.suffix}"
            temp_path.write_bytes(entry.data)
            temp_paths.append(temp_path)
        # 2. 全部移动到正式目录（kind → images/originals|upscaled|processed）
        for entry, temp_path in zip(prepared, temp_paths):
            final_dir = storage.resolve_under(directory, entry.image_id)
            final_dir.mkdir(parents=True, exist_ok=True)
            created_dirs.append(final_dir)
            storage.atomic_move_into(temp_path, final_dir, f"{kind}{entry.suffix}")
        # 3. 单事务写入全部 Image
        images = [
            Image(
                id=entry.image_id,
                job_id=job.id if job is not None else None,
                job_item_id=item.id if item is not None else None,
                parent_image_id=parent_image_id,
                kind=kind,
                file_path=entry.relative_path,
                width=entry.width,
                height=entry.height,
                seed=seed,
                review_status="UNREVIEWED",
                favorite=False,
                source=source,
                sha256=entry.sha256,
                imported_filename=entry.imported_filename,
                metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            )
            for entry in prepared
        ]
        for image in images:
            session.add(image)
        session.commit()
        _best_effort_thumbnail(session, storage, images, prepared)
        return images
    except Exception:
        session.rollback()
        for path in temp_paths:
            storage.safe_delete(path)
        for directory in created_dirs:
            storage.safe_delete(directory)
        raise


def _best_effort_thumbnail(
    session: Session, storage: StorageManager,
    images: list[Image], prepared: list[PreparedImageOutput],
) -> None:
    """Phase 0.11.1 P1-3：新图入库后 best-effort 主动生成 thumbnail。

    - 用**已在内存的输出字节**渲染（绝不重新读盘）；
    - 同步且轻量；失败仅 log warning，**绝不向调用方抛错、绝不回滚/拖慢 Job 或 import**；
    - preview 不在入库时同步生成（留给按需/回填，避免每张大图额外开销）。
    """
    for image, entry in zip(images, prepared):
        try:
            from app.services.thumbnail_service import produce_thumbnail_from_bytes

            produce_thumbnail_from_bytes(session, storage, image, entry.data)
        except Exception:  # noqa: BLE001 —— 缩略图失败绝不影响落库
            session.rollback()
            logger.warning("入库后主动生成缩略图失败 image_id=%s（忽略，留待回填）",
                           image.id)


def import_engine_output(
    session: Session,
    storage: StorageManager,
    *,
    data: bytes,
    original_filename: str,
    job: Job | None = None,
    item: JobItem | None = None,
    seed: int | None = None,
    source: str = "comfyui",
    kind: str = "original",
    metadata: dict[str, Any] | None = None,
) -> Image:
    """单图便捷入口（prepare + 单元素批次事务）。

    仅供单张场景；多图必须走 prepare_image_output() + import_outputs_transaction()
    的整批路径（Phase 2.2 §1）。original_filename 仅作调用签名兼容，不参与落盘命名。
    """
    prepared = prepare_image_output(data, kind=kind)
    images = import_outputs_transaction(
        session, storage, [prepared],
        job=job, item=item, seed=seed, source=source, kind=kind, metadata=metadata,
    )
    return images[0]


def _stage_capabilities(stage: JobStage):
    """取 Stage 模块的 ModuleCapabilities（Task2：kind/parent/seed 的唯一判定依据）。"""
    from app.workflows.registry import default_registry

    return default_registry().get(stage.module_id, stage.module_version).capabilities()


def import_adapter_outputs(session: Session, storage: StorageManager, job: Job,
                           stage_item: JobStageItem, outputs: list[EngineOutputFile]) -> list[str]:
    """Worker 的 output_importer 回调：把 Adapter 取回的输出登记为 Image（Phase 3 §十四）。

    Phase 4 Task2/3：kind / parent_image_id / seed **全部来自 Stage 模块的 ModuleCapabilities**，
    禁止再用"有 input_image_id 就推断为 upscaled"（未来 Img2Img / Reference 会立刻出错）：
    - output_kind → Image.kind（含存储目录）；
    - parent_policy=input_image → parent_image_id = StageItem.input_image_id；
    - seed → StageItem.seed（uses_seed=false 的 Stage 导入的图为 NULL，绝不带假 Seed）。
    Phase 2.2 §1：先全部校验（prepare）→ 整批事务导入。
    """
    stage = session.get(JobStage, stage_item.job_stage_id) if stage_item is not None else None
    job_item = session.get(JobItem, stage_item.job_item_id) if stage_item is not None else None
    capabilities = _stage_capabilities(stage) if stage is not None else None
    kind = capabilities.output_kind if capabilities is not None else "original"
    parent_image_id = None
    if capabilities is not None and capabilities.parent_policy == "input_image":
        parent_image_id = stage_item.input_image_id if stage_item is not None else None
    seed = stage_item.seed if stage_item is not None else None
    # Phase 7 Task8：图片来源必须反映真实产出引擎——"import" 只属于外部导入，
    # 非 comfyui/mock 的未来引擎输出绝不能错标成 import（统一记 engine，provenance 保留 actual_provider）。
    if job.provider == "comfyui":
        source = "comfyui"
    elif job.provider == "mock":
        source = "mock"
    else:
        source = "engine"
    metadata = {
        "module_id": stage.module_id if stage is not None else job.module_id,
        "module_version": stage.module_version if stage is not None else job.module_version,
        "provider": stage.provider if stage is not None else job.provider,
        "binding_version": stage.binding_version if stage is not None else job.binding_version,
        "workflow_hash": stage.workflow_hash if stage is not None else job.workflow_hash,
        "binding_hash": stage.binding_hash if stage is not None else job.binding_hash,
        "stage_id": stage.id if stage is not None else None,
        "stage_index": stage.stage_index if stage is not None else None,
        "stage_item_id": stage_item.id if stage_item is not None else None,
        "parent_image_id": parent_image_id,
        "actual_provider": job.provider,
    }
    prepared = [prepare_image_output(output.data, kind=kind) for output in outputs]
    images = import_outputs_transaction(
        session, storage, prepared,
        job=job, item=job_item, seed=seed,
        source=source, kind=kind, parent_image_id=parent_image_id, metadata=metadata,
    )
    return [image.id for image in images]


def _is_generative_output(session: Session, image: Image) -> bool:
    """Phase 7 Task8：本图产出是否来自"生成型"模块（生成上下文锚点判定）。

    依据产出 Stage 的 ModuleCapabilities.is_generative（模块语义声明），
    **不再依赖 Image.seed 数据是否非空**——未来非 ComfyUI Engine / 未记录 Seed 的生成路径
    同样能恢复工作台。旧数据（找不到产出 StageItem / 模块版本已不存在）回退兼容判定。
    """
    stage = session.execute(
        select(JobStage)
        .join(JobStageItem, JobStageItem.job_stage_id == JobStage.id)
        .where(JobStageItem.output_image_id == image.id)
    ).scalars().first()
    if stage is None:
        return image.seed is not None  # 兼容：Phase 3 之前无 Stage 结构的旧数据
    try:
        return _stage_capabilities(stage).is_generative
    except EngineError:
        return image.seed is not None  # 模块版本已不存在：兼容回落


def resolve_generation_context(session: Session, image: Image) -> tuple[Image, Job]:
    """派生图 → **最近的生成上下文**（Phase 6 Task1 修复"永远取树根"；Phase 7 Task8 语义化）。

    旧逻辑沿 parent_image_id 找到树根再要求它是生成图；img2img 以外部导入图（或上一代
    生成图）为输入时树根没有 generate Job，导致 processed / upscaled 图无法恢复配置。

    语义：从当前图开始沿父链向上，找**距离最近、由 generate Job 产出、且产出模块声明为
    生成型（ModuleCapabilities.is_generative）**的图及其 Job（Seed 用该图真实 Seed，
    不再无条件用树根 Seed，也不再依赖 seed 数据是否非空）：

    - import → img2img → 恢复 Img2Img（上下文 = img2img 输出）；
    - import → img2img → upscale → 仍恢复 Img2Img：同一 generate Job 内嵌的后处理
      Stage（is_generative=false）产出不构成锚点，继续向上到真实生成图；
    - basic → upscale → 恢复 basic；纯外部导入图（全链无生成图）→ NotFoundError
      IMAGE_NO_GENERATION_CONTEXT（"没有可恢复的生成配置"，绝不伪造 Prompt）。
    """
    current: Image | None = image
    visited: set[str] = {image.id}
    while current is not None:
        if current.job_id is not None:
            job = session.get(Job, current.job_id)
            if (
                job is not None
                and job.job_kind == "generate"
                and _is_generative_output(session, current)
            ):
                return current, job
        if not current.parent_image_id or current.parent_image_id in visited:
            break  # 到顶 / 环保护（防御性；正常数据不可能）
        visited.add(current.parent_image_id)
        current = session.get(Image, current.parent_image_id)
    raise NotFoundError("没有可恢复的生成配置", code="IMAGE_NO_GENERATION_CONTEXT")


def load_input_image_ref(session: Session, storage: StorageManager, image_id: str) -> InputImageRef:
    """加载处理型 Stage 的输入图片（§十三/§二十一）→ InputImageRef（字节已在内存）。"""
    image = get_image(session, image_id)
    path = storage.absolutize(image.file_path)
    if not path.is_file():
        raise NotFoundError("输入图片文件不存在", code="IMAGE_FILE_MISSING")
    return InputImageRef(
        image_id=image.id,
        file_name=path.name,
        data=path.read_bytes(),
        width=image.width,
        height=image.height,
    )


def _validate_filter_values(*, review_status: str | None, status: str | None) -> None:
    """图库列表 / 统计共用的过滤参数校验（两处口径必须完全一致）。"""
    if review_status is not None and review_status not in ("UNREVIEWED", "KEPT", "REJECTED"):
        raise ValidationError(f"非法审核状态: {review_status}", code="REVIEW_STATUS_INVALID")
    if status is not None and status not in IMAGE_STATUSES:
        raise ValidationError(f"非法图片状态: {status}", code="IMAGE_STATUS_INVALID")


def _apply_image_filters(
    query,
    *,
    job_id: str | None = None,
    review_status: str | None = None,
    favorite: bool | None = None,
    source: str | None = None,
    kind: str | None = None,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
):
    """把图库过滤条件统一叠加到 select(Image) 查询上（list_images 与 image_stats 共用，
    保证列表与统计的过滤口径完全一致——禁止为统计另写一套不一致的过滤）。"""
    if job_id is not None:
        query = query.where(Image.job_id == job_id)
    if review_status is not None:
        query = query.where(Image.review_status == review_status)
    if favorite is not None:
        query = query.where(Image.favorite == favorite)
    if status is not None:
        query = query.where(Image.status == status)
    if source is not None:
        query = query.where(Image.source == source)
    if kind is not None:
        query = query.where(Image.kind == kind)
    if search:
        # Phase 5：按导入文件名搜索（生成图没有文件名，自然不命中）
        query = query.where(Image.imported_filename.like(f"%{search.strip()}%"))
    if date_from is not None:
        query = query.where(Image.created_at >= date_from)
    if date_to is not None:
        query = query.where(Image.created_at <= date_to)
    return query


def list_images(
    session: Session,
    *,
    job_id: str | None = None,
    review_status: str | None = None,
    favorite: bool | None = None,
    source: str | None = None,
    kind: str | None = None,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
    sort: str = "created_desc",
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Image], int]:
    if limit < 1 or limit > 200:
        raise ValidationError("limit 取值范围为 1-200")
    if offset < 0:
        raise ValidationError("offset 不能为负")
    _validate_filter_values(review_status=review_status, status=status)
    if sort not in ("created_desc", "created_asc", "favorite", "size"):
        raise ValidationError(f"非法排序: {sort}", code="IMAGE_SORT_INVALID")

    query = _apply_image_filters(
        select(Image),
        job_id=job_id, review_status=review_status, favorite=favorite, source=source,
        kind=kind, search=search, date_from=date_from, date_to=date_to, status=status,
    )

    total = session.execute(select(func.count()).select_from(query.subquery())).scalar_one()

    # Phase 0.11 排序：
    # - created_desc/created_asc：按生成时间；
    # - favorite：精品优先，再按时间倒序；
    # - size：按像素数（width*height）倒序，大尺寸优先（图片无文件字节列，
    #   像素数由列直接可得、确定性可排序，避免为排序而全库读文件）。
    # Phase 0.11.1：所有排序补稳定 tie-breaker（created_at, id），
    # 保证连续页无重复/遗漏（同 created_at 时按 id 确定性排序）。
    if sort == "created_asc":
        order_by = (Image.created_at.asc(), Image.id.asc())
    elif sort == "favorite":
        order_by = (Image.favorite.desc(), Image.created_at.desc(), Image.id.desc())
    elif sort == "size":
        order_by = ((Image.width * Image.height).desc(), Image.created_at.desc(), Image.id.desc())
    else:
        order_by = (Image.created_at.desc(), Image.id.desc())

    items = list(session.execute(
        query.order_by(*order_by).limit(limit).offset(offset)
    ).scalars())
    return items, int(total)


def image_stats(
    session: Session,
    *,
    job_id: str | None = None,
    review_status: str | None = None,
    favorite: bool | None = None,
    source: str | None = None,
    kind: str | None = None,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    status: str | None = None,
) -> dict[str, int]:
    """全局图库统计（Phase 0.12 Task5/ReviewMode）：与 list_images 完全相同的过滤口径。

    用一次 SQL 条件聚合（COUNT/GROUP BY 单行），绝不把全部行 load 进内存。
    口径（Phase 0.11.1 冻结）：
    - new/keep/reject/archived = images.status 各状态计数；
    - favorites = favorite=true 的独立交叉计数（不并入任一审核状态，可与任意状态共存）；
    - total = 命中过滤条件的全部图片数（前端 ReviewMode 的"分母"必须来自这里，
      而非本地已加载 list，避免把局部统计误认为全局统计）。
    """
    _validate_filter_values(review_status=review_status, status=status)
    agg = (
        select(
            func.count().label("total"),
            func.coalesce(func.sum(case((Image.status == "NEW", 1), else_=0)), 0).label("new"),
            func.coalesce(func.sum(case((Image.status == "KEEP", 1), else_=0)), 0).label("keep"),
            func.coalesce(func.sum(case((Image.status == "REJECT", 1), else_=0)), 0).label("reject"),
            func.coalesce(func.sum(case((Image.status == "ARCHIVED", 1), else_=0)), 0).label("archived"),
            func.coalesce(func.sum(case((Image.favorite.is_(True), 1), else_=0)), 0).label("favorites"),
        )
        .select_from(Image)
    )
    agg = _apply_image_filters(
        agg,
        job_id=job_id, review_status=review_status, favorite=favorite, source=source,
        kind=kind, search=search, date_from=date_from, date_to=date_to, status=status,
    )
    row = session.execute(agg).one()
    return {
        "total": int(row.total),
        "new": int(row.new),
        "keep": int(row.keep),
        "reject": int(row.reject),
        "archived": int(row.archived),
        "favorites": int(row.favorites),
    }


def set_review(session: Session, image_id: str, review_status: str) -> Image:
    """旧审核接口（PATCH /images/{id}/review）——与新 status 同源，绝不第二套逻辑。

    旧值 → 新 status：UNREVIEWED→NEW（清 reviewed_at）、KEPT→KEEP、REJECTED→REJECT；
    同步写 status / review_status / reviewed_at；**绝不改 favorite**。
    """
    if review_status not in ("UNREVIEWED", "KEPT", "REJECTED"):
        raise ValidationError(f"非法审核状态: {review_status}", code="REVIEW_STATUS_INVALID")
    image = get_image(session, image_id)
    new_status = _LEGACY_REVIEW_TO_STATUS[review_status]
    image.review_status = review_status
    image.status = new_status
    image.reviewed_at = None if new_status == "NEW" else utc_now_iso()
    session.commit()
    return image


def set_favorite(session: Session, image_id: str, favorite: bool) -> Image:
    """收藏切换（PATCH /images/{id}/favorite）——只写 favorite，**绝不改 status/review_status/reviewed_at**。

    收藏与审核状态相互独立：KEEP+favorite、ARCHIVED+favorite、NEW+favorite 都合法。
    """
    image = get_image(session, image_id)
    image.favorite = favorite
    session.commit()
    return image


def set_image_status(session: Session, image_id: str, status: str,
                     note: str | None = None) -> Image:
    """新审核状态流转（NEW/KEEP/REJECT/ARCHIVED）。

    语义（Phase 0.11.1 合同冻结）：
    - 置 status、review_note；除 NEW 外置 reviewed_at=now，回到 NEW 则清空；
    - **FAVORITE 不再作为可写入状态**：传入即 IMAGE_STATUS_DEPRECATED(400)，提示收藏请用
      favorite（PATCH /images/{id}/favorite）；DB CHECK 仍保留 FAVORITE 兼容历史；
    - 同步双写旧 review_status（NEW→UNREVIEWED、KEEP/ARCHIVED→KEPT、REJECT→REJECTED），
      保证按旧列聚合的统计随新状态实时变化（旧列保留兼容，不做删除）；
    - **绝不改 favorite**：切审核状态不得偷偷覆盖用户收藏。
    """
    if status not in IMAGE_STATUSES:
        raise ValidationError(f"非法图片状态: {status}", code="IMAGE_STATUS_INVALID")
    if status == "FAVORITE":
        raise ValidationError(
            "FAVORITE 不再作为审核状态写入；收藏请使用 favorite（PATCH /images/{id}/favorite）",
            code="IMAGE_STATUS_DEPRECATED",
        )
    image = get_image(session, image_id)
    image.status = status
    image.review_note = note or ""
    image.reviewed_at = None if status == "NEW" else utc_now_iso()
    image.review_status = _STATUS_TO_LEGACY_REVIEW[status]
    session.commit()
    return image


def batch_set_status(session: Session, image_ids: list[str], status: str,
                    note: str | None = None) -> list[Image]:
    """Phase 0.11 批量审核（POST /images/batch-status）。

    逐个调用 set_image_status（单图事务）；任一 id 不存在即 404 中止，不静默跳过。
    FAVORITE 与单图接口同样被拒绝（IMAGE_STATUS_DEPRECATED）。
    """
    if status not in IMAGE_STATUSES:
        raise ValidationError(f"非法图片状态: {status}", code="IMAGE_STATUS_INVALID")
    if status == "FAVORITE":
        raise ValidationError(
            "FAVORITE 不再作为审核状态写入；收藏请使用 favorite",
            code="IMAGE_STATUS_DEPRECATED",
        )
    return [set_image_status(session, image_id, status, note) for image_id in image_ids]


def job_gallery_summary(session: Session, job_id: str) -> dict:
    """按 Job 统计（规范 §四十九：未审核 / 保留 / 收藏 / 淘汰）。

    Phase 0.11.1 口径（以新 status + favorite 为准，旧 review_status 仅兼容）：
    - unreviewed = count(status='NEW')；
    - rejected   = count(status='REJECT')；
    - kept       = count(status IN ('KEEP','ARCHIVED'))（ARCHIVED 视为已保留，保证
      unreviewed+kept+rejected == total）；
    - favorites  = count(favorite=true)（独立交叉计数，**不可**并入 kept/rejected）；
    - total      = 该 job 全部图。
    """
    def _count(*clauses) -> int:
        query = select(func.count()).select_from(Image).where(Image.job_id == job_id)
        for clause in clauses:
            query = query.where(clause)
        return int(session.execute(query).scalar_one())

    total = _count()
    unreviewed = _count(Image.status == "NEW")
    rejected = _count(Image.status == "REJECT")
    kept = _count(Image.status.in_(("KEEP", "ARCHIVED")))
    favorites = _count(Image.favorite.is_(True))
    return {
        "job_id": job_id,
        "total": total,
        "unreviewed": unreviewed,
        "kept": kept,
        "rejected": rejected,
        "favorites": favorites,
    }


def list_job_groups(
    session: Session, *, page: int = 1, page_size: int = 20,
) -> tuple[list[dict], int]:
    """Phase 0.11.1 P1-2：按 Job 聚合图库统计（单次 GROUP BY，避免 N+1）。

    口径与 ``job_gallery_summary`` 完全一致：
    - unreviewed = count(status='NEW')；rejected = count(status='REJECT')；
    - kept = count(status IN ('KEEP','ARCHIVED'))；favorites = count(favorite=true)。
    只含 status='COMPLETED' 且有产出图的 Job；按 Job created_at 倒序（id 兜底）。
    返回 (groups, total_groups)。
    """
    agg = (
        select(
            Image.job_id.label("job_id"),
            func.count().label("total"),
            func.coalesce(func.sum(case((Image.status == "NEW", 1), else_=0)), 0).label("unreviewed"),
            func.coalesce(func.sum(case((Image.status == "REJECT", 1), else_=0)), 0).label("rejected"),
            func.coalesce(func.sum(case((Image.status.in_(("KEEP", "ARCHIVED")), 1), else_=0)), 0).label("kept"),
            func.coalesce(func.sum(case((Image.favorite.is_(True), 1), else_=0)), 0).label("favorites"),
        )
        .where(Image.job_id.isnot(None))
        .group_by(Image.job_id)
        .subquery()
    )
    query = (
        select(
            agg.c.job_id,
            Job.module_id.label("module_id"),
            Job.created_at.label("created_at"),
            agg.c.total,
            agg.c.unreviewed,
            agg.c.kept,
            agg.c.rejected,
            agg.c.favorites,
        )
        .join(Job, Job.id == agg.c.job_id)
        .where(Job.status == "COMPLETED")
    )
    total = int(session.execute(select(func.count()).select_from(query.subquery())).scalar_one())
    rows = session.execute(
        query.order_by(Job.created_at.desc(), Job.id.desc())
        .limit(page_size).offset((page - 1) * page_size)
    ).all()
    groups = [
        {
            "job_id": row.job_id,
            "module_id": row.module_id,
            "created_at": row.created_at,
            "total": int(row.total),
            "unreviewed": int(row.unreviewed),
            "kept": int(row.kept),
            "rejected": int(row.rejected),
            "favorites": int(row.favorites),
        }
        for row in rows
    ]
    return groups, total
