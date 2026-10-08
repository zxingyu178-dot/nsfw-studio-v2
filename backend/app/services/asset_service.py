"""AssetService（Phase 1 规范 §十二-§二十、§三十二、§五十六、§五十七）。

文件写入顺序（规范 §十九）::

    上传 → images/temp（校验）→ 原子移动到正式位置 → 数据库提交
    - 数据库提交失败：删除已移动的正式文件，不留无法追踪的素材；
    - 文件移动失败：回滚数据库，绝不先提交数据库。

数据库只保存 DataRoot 相对路径（规范 §十七）；版本 immutable（§五十六）。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.filetypes import validate_image_upload
from app.core.ids import ASSET, ASSET_REFERENCE_IMAGE, ASSET_VERSION, new_id
from app.models import ASSET_TYPES, Asset, AssetReferenceImage, AssetVersion, Image
from app.storage.manager import StorageManager


@dataclass(frozen=True)
class PreviewUpload:
    filename: str | None
    content_type: str | None
    data: bytes


def _version_dir_name(version_no: int) -> str:
    return f"v{version_no:04d}"


def get_asset(session: Session, asset_id: str) -> Asset:
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise NotFoundError("素材不存在", code="ASSET_NOT_FOUND")
    return asset


def get_current_version(session: Session, asset: Asset) -> AssetVersion | None:
    if asset.current_version_id is None:
        return None
    return session.get(AssetVersion, asset.current_version_id)


def get_reference_image_ids(session: Session, asset_version_id: str) -> list[str]:
    """素材版本的参考图 image_id 列表（Phase 5 §十二/§十三：来自 asset_reference_images）。"""
    return list(session.execute(
        select(AssetReferenceImage.image_id)
        .where(AssetReferenceImage.asset_version_id == asset_version_id)
        .order_by(AssetReferenceImage.sort_order)
    ).scalars())


def _validate_reference_image(session: Session, asset_type: str, image_id: str) -> None:
    """参考图绑定校验（§十二：Phase 5 仅 Face Asset 支持 1 张，来源必须是图库图片）。"""
    if asset_type != "face":
        raise ValidationError("Phase 5 仅人脸素材支持绑定参考图", code="ASSET_REFERENCE_TYPE_INVALID")
    if session.get(Image, image_id) is None:
        raise NotFoundError("参考图片不存在", code="IMAGE_NOT_FOUND")


def _store_reference_images(
    session: Session, asset_version_id: str, image_id: str | None
) -> None:
    """写入参考图关系行（role=face_reference, sort_order=0；Phase 5 单张）。"""
    if image_id is None:
        return
    session.add(AssetReferenceImage(
        id=new_id(ASSET_REFERENCE_IMAGE),
        asset_version_id=asset_version_id,
        image_id=image_id,
        role="face_reference",
        sort_order=0,
    ))


def _validate_type(asset_type: str) -> str:
    if asset_type not in ASSET_TYPES:
        raise ValidationError(
            f"非法素材类型: {asset_type}（仅允许 {'/'.join(ASSET_TYPES)}）", code="ASSET_TYPE_INVALID"
        )
    return asset_type


def _normalize_tags(tags: list[str] | None) -> list[str]:
    if not tags:
        return []
    cleaned: list[str] = []
    for tag in tags:
        tag = tag.strip()
        if tag and tag not in cleaned:
            cleaned.append(tag)
    return cleaned[:32]


def _store_preview(
    session: Session,
    storage: StorageManager,
    *,
    asset_type: str,
    asset_id: str,
    version_no: int,
    upload: PreviewUpload | None,
    previous_version: AssetVersion | None,
) -> str | None:
    """返回该版本 preview 的 DataRoot 相对路径（无图返回 None）。

    流程：temp 写入 → 校验 → 原子移动到 assets/<type>/<id>/vXXXX/preview.ext。
    由调用方保证：本函数在数据库 commit 之前调用；commit 失败时调用方清理版本目录。
    """
    version_dir = storage.resolve_under("assets", asset_type, asset_id, _version_dir_name(version_no))

    if upload is not None and upload.data:
        suffix = validate_image_upload(upload.filename, upload.content_type, upload.data)
        temp_path = storage.temp_dir / f"upload_{uuid.uuid4().hex}{suffix}"
        storage.temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path.write_bytes(upload.data)
        try:
            final_path = storage.atomic_move_into(temp_path, version_dir, f"preview{suffix}")
        except Exception:
            storage.safe_delete(temp_path)
            raise
        return storage.relative_to_root(final_path)

    if previous_version is not None and previous_version.preview_path:
        # 沿用旧版本预览图：复制到新版本目录（旧版本文件保持不动，历史不可变）
        src = storage.absolutize(previous_version.preview_path)
        if src.is_file():
            dest = version_dir / src.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            import shutil

            shutil.copyfile(src, dest)
            return storage.relative_to_root(dest)
    return None


def create_asset(
    session: Session,
    storage: StorageManager,
    *,
    asset_type: str,
    name: str,
    prompt_text: str = "",
    notes: str = "",
    tags: list[str] | None = None,
    favorite: bool = False,
    preview: PreviewUpload | None = None,
    source_image_id: str | None = None,
    reference_image_id: str | None = None,
) -> Asset:
    """创建素材 + v1（单事务；文件先落位，提交失败则清理文件）。

    source_image_id：图库图片创建素材时记录溯源（规范 §四十八）；
    素材使用独立资产文件，来源图片被清理不影响素材。
    reference_image_id：Face Asset 参考图（Phase 5 §十二：仅 face，来源=图库 image_id）。
    """
    _validate_type(asset_type)
    if not name or not name.strip():
        raise ValidationError("素材名称不能为空")
    if source_image_id is not None and session.get(Image, source_image_id) is None:
        raise NotFoundError("来源图片不存在", code="IMAGE_NOT_FOUND")
    if reference_image_id is not None:
        _validate_reference_image(session, asset_type, reference_image_id)

    asset = Asset(
        id=new_id(ASSET), type=asset_type, name=name.strip(), favorite=favorite,
        archived=False, source_image_id=source_image_id,
    )
    version = AssetVersion(
        id=new_id(ASSET_VERSION),
        asset_id=asset.id,
        version_no=1,
        prompt_text=prompt_text or "",
        notes=notes or "",
        tags_json=json.dumps(_normalize_tags(tags), ensure_ascii=False),
    )
    version.preview_path = _store_preview(
        session, storage, asset_type=asset_type, asset_id=asset.id, version_no=1,
        upload=preview, previous_version=None,
    )
    asset.current_version_id = version.id
    try:
        session.add(asset)
        session.add(version)
        session.flush()  # 先落 asset_version（参考图行的 FK 依赖它，与 recipe_snapshot 同模式）
        _store_reference_images(session, version.id, reference_image_id)
        session.commit()
    except IntegrityError:
        session.rollback()
        storage.safe_delete(storage.resolve_under("assets", asset_type, asset.id))
        raise ConflictError("版本号冲突，请重试", code="VERSION_CONFLICT")
    except Exception:
        session.rollback()
        # 数据库失败：清理已落位的正式文件，不留无法追踪的素材（规范 §十九）
        storage.safe_delete(storage.resolve_under("assets", asset_type, asset.id))
        raise
    return asset


def add_asset_version(
    session: Session,
    storage: StorageManager,
    asset_id: str,
    *,
    prompt_text: str | None = None,
    notes: str | None = None,
    tags: list[str] | None = None,
    preview: PreviewUpload | None = None,
    reference_image_id: str | None = None,
) -> tuple[AssetVersion, bool]:
    """内容变化（Prompt/预览图/参考图/tags/notes 任一）→ 新 AssetVersion（旧版本永远保留）。

    reference_image_id：传入即设置参考图（§十二）；不传则沿用当前版本参考图
    （与 preview 的沿用语义一致）。
    """
    asset = get_asset(session, asset_id)
    current = get_current_version(session, asset)
    current_reference_ids = get_reference_image_ids(session, current.id) if current else []
    current_reference_id = current_reference_ids[0] if current_reference_ids else None

    new_prompt = prompt_text if prompt_text is not None else (current.prompt_text if current else "")
    new_notes = notes if notes is not None else (current.notes if current else "")
    new_tags = _normalize_tags(tags) if tags is not None else (
        json.loads(current.tags_json) if current else []
    )
    if reference_image_id is not None:
        _validate_reference_image(session, asset.type, reference_image_id)
    new_reference_id = reference_image_id if reference_image_id is not None else current_reference_id

    if current is not None and (
        new_prompt == current.prompt_text
        and new_notes == current.notes
        and json.dumps(new_tags, ensure_ascii=False) == current.tags_json
        and (preview is None or not preview.data)
        and new_reference_id == current_reference_id
    ):
        return current, False  # 内容无变化

    version_no = _next_version_no(session, asset.id)
    version = AssetVersion(
        id=new_id(ASSET_VERSION),
        asset_id=asset.id,
        version_no=version_no,
        prompt_text=new_prompt,
        notes=new_notes,
        tags_json=json.dumps(new_tags, ensure_ascii=False),
    )
    version.preview_path = _store_preview(
        session, storage, asset_type=asset.type, asset_id=asset.id, version_no=version_no,
        upload=preview, previous_version=current,
    )
    asset.current_version_id = version.id
    try:
        session.add(version)
        session.flush()  # 先落 asset_version（参考图行的 FK 依赖它）
        _store_reference_images(session, version.id, new_reference_id)
        session.commit()
    except IntegrityError:
        session.rollback()
        storage.safe_delete(storage.resolve_under("assets", asset.type, asset.id, _version_dir_name(version_no)))
        raise ConflictError("版本号冲突，请重试", code="VERSION_CONFLICT")
    except Exception:
        session.rollback()
        storage.safe_delete(storage.resolve_under("assets", asset.type, asset.id, _version_dir_name(version_no)))
        raise
    return version, True


def update_asset_meta(
    session: Session,
    asset_id: str,
    *,
    name: str | None = None,
    favorite: bool | None = None,
) -> Asset:
    """元数据修改：不创建内容版本。"""
    asset = get_asset(session, asset_id)
    if name is not None:
        if not name.strip():
            raise ValidationError("素材名称不能为空")
        asset.name = name.strip()
    if favorite is not None:
        asset.favorite = favorite
    session.commit()
    return asset


def _next_version_no(session: Session, asset_id: str) -> int:
    current_max = session.execute(
        select(func.max(AssetVersion.version_no)).where(AssetVersion.asset_id == asset_id)
    ).scalar_one()
    return (current_max or 0) + 1


def get_version(session: Session, asset_id: str, version_id: str) -> AssetVersion:
    version = session.get(AssetVersion, version_id)
    if version is None or version.asset_id != asset_id:
        raise NotFoundError("素材版本不存在", code="ASSET_VERSION_NOT_FOUND")
    return version


def list_versions(session: Session, asset_id: str) -> list[AssetVersion]:
    asset = get_asset(session, asset_id)
    return list(
        session.execute(
            select(AssetVersion)
            .where(AssetVersion.asset_id == asset.id)
            .order_by(AssetVersion.version_no.desc())
        ).scalars()
    )


def list_assets(
    session: Session,
    *,
    asset_type: str | None = None,
    search: str | None = None,
    favorite: bool | None = None,
    archived: bool | None = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Asset], int]:
    if asset_type is not None:
        _validate_type(asset_type)
    if limit < 1 or limit > 200:
        raise ValidationError("limit 取值范围为 1-200")
    if offset < 0:
        raise ValidationError("offset 不能为负")

    query = select(Asset)
    if archived is not None:
        query = query.where(Asset.archived == archived)
    if asset_type is not None:
        query = query.where(Asset.type == asset_type)
    if favorite is not None:
        query = query.where(Asset.favorite == favorite)
    if search:
        like = f"%{search.strip()}%"
        matching_versions = select(AssetVersion.asset_id).where(AssetVersion.prompt_text.like(like))
        query = query.where(or_(Asset.name.like(like), Asset.id.in_(matching_versions)))

    total = session.execute(select(func.count()).select_from(query.subquery())).scalar_one()
    items = list(
        session.execute(query.order_by(Asset.updated_at.desc()).limit(limit).offset(offset)).scalars()
    )
    return items, int(total)


def set_archived(session: Session, asset_id: str, archived: bool) -> Asset:
    asset = get_asset(session, asset_id)
    asset.archived = archived
    session.commit()
    return asset
