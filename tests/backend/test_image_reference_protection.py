"""Phase 0.11 删除引用保护：被 Prompt / 派生图引用的 REJECT 图禁止删除。"""
from __future__ import annotations

import io

from PIL import Image as PILImage

from app.services import cleanup_service, image_reference_service, image_service


def _real_png(width=800, height=600) -> bytes:
    buffer = io.BytesIO()
    PILImage.new("RGB", (width, height), (50, 150, 200)).save(buffer, format="PNG")
    return buffer.getvalue()


def _import_real(session, storage):
    return image_service.import_engine_output(
        session, storage, data=_real_png(), original_filename="a.png", source="comfyui",
    )


def test_referenced_as_prompt_cover_is_protected(client, settings):
    """设为 Prompt 封面的图被引用 → cleanup 跳过（protected），不得删除。"""
    from app.storage.manager import StorageManager

    storage = StorageManager(client.app.state.settings)
    with client.app.state.session_factory() as session:
        image = _import_real(session, storage)
        image_id = image.id
        image_service.set_image_status(session, image.id, "REJECT")
        # 引用检查在删除前 total>0
        refs = image_reference_service.count_references(session, image_id)
        assert refs["total"] == 0

    prompt = client.post("/api/v1/prompts", json={
        "name": "封面", "mode": "full", "positive_prompt": "x",
    }).json()
    client.put(f"/api/v1/prompts/{prompt['id']}/preview-image", json={"image_id": image_id})

    with client.app.state.session_factory() as session:
        refs = image_reference_service.count_references(session, image_id)
        assert refs["total"] > 0, "Prompt 封面引用必须被 count_references 识别"

        result = cleanup_service.execute(session, storage, [image_id])
    assert result["protected_count"] == 1
    assert result["deleted_count"] == 0

    with client.app.state.session_factory() as session:
        from app.services import image_service as svc
        image = svc.get_image(session, image_id)
        assert storage.absolutize(image.file_path).is_file(), "受保护图文件不得被删"


def test_derived_parent_is_protected(session, settings):
    """存在派生子图（parent_image_id 指向本图）→ 本图 protected。"""
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    parent = _import_real(session, storage)
    child = _import_real(session, storage)
    child.parent_image_id = parent.id
    session.commit()
    image_service.set_image_status(session, parent.id, "REJECT")

    refs = image_reference_service.count_references(session, parent.id)
    assert refs["total"] > 0

    result = cleanup_service.execute(session, storage, [parent.id])
    assert result["protected_count"] == 1
    assert result["deleted_count"] == 0
    assert storage.absolutize(parent.file_path).is_file()


def test_unreferenced_reject_can_be_deleted(session, settings):
    """未被任何对象引用的 REJECT 图可以正常删除（对照用例）。"""
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = _import_real(session, storage)
    image_service.set_image_status(session, image.id, "REJECT")

    refs = image_reference_service.count_references(session, image.id)
    assert refs["total"] == 0

    result = cleanup_service.execute(session, storage, [image.id])
    assert result["deleted_count"] == 1
    assert result["protected_count"] == 0
