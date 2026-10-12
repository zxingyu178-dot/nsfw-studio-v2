"""Phase 0.11.1 统一审核状态语义回归（P0-1 / P1-1）。

显式复现并关闭"新旧审核状态双系统分裂"：
- 旧 PATCH /review 设 KEPT 后：review_status=KEPT 且 status=KEEP（不再停留在 NEW）；
- 旧 PATCH /favorite=true 后：favorite=true 且审核状态保持不变（NEW 仍是 NEW）；
- 收藏与审核状态独立共存：KEEP+favorite 合法，重复 set status KEEP 不清收藏；
- set_image_status('FAVORITE') / batch_set_status('FAVORITE') → IMAGE_STATUS_DEPRECATED(400)；
- migration 0017 归一：FAVORITE 行 / favorite=1&NEW 行升级后为 KEEP+favorite；
- job_gallery_summary 以新 status + favorite 口径统计（favorite 独立、ARCHIVED 计入 kept）。
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from app.core.errors import ValidationError
from app.database import migrations as migrations_module
from app.database.base import init_database, make_engine
from app.services import image_service


def _import_one(client, png_bytes):
    from app.storage.manager import StorageManager

    storage = StorageManager(client.app.state.settings)
    with client.app.state.session_factory() as session:
        image = image_service.import_engine_output(
            session, storage, data=png_bytes, original_filename="a.png", source="comfyui",
        )
        return image.id


# ===== 旧接口分裂关闭（API 层） =====

def test_legacy_review_keeps_status_synchronized(client, png_bytes):
    """旧 /review 设 KEPT → status 必须同步为 KEEP（不再是 NEW），reviewed_at 置位。"""
    image_id = _import_one(client, png_bytes)
    resp = client.patch(f"/api/v1/images/{image_id}/review",
                        json={"review_status": "KEPT"}).json()
    assert resp["review_status"] == "KEPT"
    assert resp["status"] == "KEEP"
    assert resp["reviewed_at"] is not None


def test_legacy_review_back_to_unreviewed_clears_status(client, png_bytes):
    """旧 /review 设 UNREVIEWED → status 回到 NEW，reviewed_at 清空。"""
    image_id = _import_one(client, png_bytes)
    client.patch(f"/api/v1/images/{image_id}/status", json={"status": "KEEP"})
    resp = client.patch(f"/api/v1/images/{image_id}/review",
                        json={"review_status": "UNREVIEWED"}).json()
    assert resp["review_status"] == "UNREVIEWED"
    assert resp["status"] == "NEW"
    assert resp["reviewed_at"] is None


def test_legacy_favorite_does_not_touch_status(client, png_bytes):
    """旧 /favorite=true → favorite=true，但审核状态保持 NEW（收藏与审核独立）。"""
    image_id = _import_one(client, png_bytes)
    resp = client.patch(f"/api/v1/images/{image_id}/favorite",
                        json={"favorite": True}).json()
    assert resp["favorite"] is True
    assert resp["status"] == "NEW"
    assert resp["review_status"] == "UNREVIEWED"


def test_favorite_independent_through_status(client, png_bytes):
    """KEEP →（收藏 favorite=true）→ status 仍 KEEP 且 favorite=true；再 set status KEEP 不清收藏。"""
    image_id = _import_one(client, png_bytes)
    fav = client.patch(f"/api/v1/images/{image_id}/favorite", json={"favorite": True}).json()
    assert fav["favorite"] is True and fav["status"] == "NEW"

    keep = client.patch(f"/api/v1/images/{image_id}/status", json={"status": "KEEP"}).json()
    assert keep["status"] == "KEEP" and keep["favorite"] is True

    keep_again = client.patch(f"/api/v1/images/{image_id}/status",
                             json={"status": "KEEP"}).json()
    assert keep_again["status"] == "KEEP" and keep_again["favorite"] is True


# ===== 应用层拒绝写入 FAVORITE 状态 =====

def test_set_image_status_favorite_rejected(session, settings, png_bytes):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    image = image_service.import_engine_output(
        session, storage, data=png_bytes, original_filename="a.png", source="comfyui",
    )
    with pytest.raises(ValidationError) as exc:
        image_service.set_image_status(session, image.id, "FAVORITE")
    assert exc.value.code == "IMAGE_STATUS_DEPRECATED"

    with pytest.raises(ValidationError) as exc2:
        image_service.batch_set_status(session, [image.id], "FAVORITE")
    assert exc2.value.code == "IMAGE_STATUS_DEPRECATED"


# ===== Job summary 新口径 =====

def test_job_gallery_summary_new_semantics(session, settings, png_bytes):
    from app.storage.manager import StorageManager

    storage = StorageManager(settings)
    job_id = "sem_job"
    # 插入最小 jobs 行（images.job_id 有外键约束，必须先有真实 job）
    session.execute(text(
        "INSERT INTO jobs (id, source, status, prompt_mode, positive_prompt_snapshot, "
        "negative_prompt_snapshot, structured_prompt_snapshot, workbench_snapshot_json, "
        "generation_settings_json, requested_count, completed_count, priority, pause_requested, "
        "cancel_requested, created_at, updated_at) "
        "VALUES (:id, 'web', 'COMPLETED', 'structured', '', '', '{}', '{}', '{}', 4, 4, 0, 0, 0, :now, :now)"
    ), {"id": job_id, "now": "2026-01-01T00:00:00.000Z"})
    session.commit()

    images = []
    for _ in range(4):
        img = image_service.import_engine_output(
            session, storage, data=png_bytes, original_filename="a.png", source="comfyui",
        )
        img.job_id = job_id
        session.commit()
        images.append(img)

    image_service.set_image_status(session, images[0].id, "NEW")
    image_service.set_image_status(session, images[1].id, "KEEP")
    image_service.set_image_status(session, images[2].id, "REJECT")
    image_service.set_image_status(session, images[3].id, "ARCHIVED")
    image_service.set_favorite(session, images[1].id, True)  # 独立交叉计数

    summary = image_service.job_gallery_summary(session, job_id)
    assert summary["total"] == 4
    assert summary["unreviewed"] == 1
    assert summary["kept"] == 2      # KEEP + ARCHIVED
    assert summary["rejected"] == 1
    assert summary["favorites"] == 1  # 仅 images[1]，独立于 kept
    assert summary["unreviewed"] + summary["kept"] + summary["rejected"] == summary["total"]


# ===== migration 0017 数据归一 =====

def test_migration_0017_normalizes_favorite_and_status(settings, monkeypatch):
    """构造 0016 时代的分裂数据（FAVORITE 行 / favorite=1&NEW 行），升级 0017 后断言归一。"""
    engine = make_engine(settings.storage.database_path)
    original_migrations = migrations_module.MIGRATIONS

    # 只应用到 0016（不含 0017）
    v016 = tuple(m for m in original_migrations if m.migration_id <= "0016_image_review_status")
    monkeypatch.setattr(migrations_module, "MIGRATIONS", v016)
    init_database(engine)

    now = "2026-01-01T00:00:00.000Z"

    def insert(img_id, status, favorite, review_status, reviewed_at):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO images (id, kind, file_path, width, height, review_status, favorite, "
                "source, metadata_json, status, reviewed_at, review_note, created_at, updated_at) "
                "VALUES (:id, 'original', :path, 8, 8, :review_status, :favorite, 'comfyui', '{}', "
                ":status, :reviewed_at, '', :now, :now)"
            ), {
                "id": img_id, "path": f"images/originals/{img_id}/original.png",
                "review_status": review_status, "favorite": favorite, "status": status,
                "reviewed_at": reviewed_at, "now": now,
            })

    insert("img_fav", "FAVORITE", 1, "KEPT", now)        # FAVORITE → KEEP, favorite 保持 1
    insert("img_fav_nofav", "FAVORITE", 0, "KEPT", now)  # FAVORITE → KEEP, favorite 补 1
    insert("img_new_fav", "NEW", 1, "UNREVIEWED", None)  # favorite=1 & NEW → KEEP
    insert("img_keep", "KEEP", 0, "KEPT", None)          # KEEP & reviewed_at NULL → 补 reviewed_at
    insert("img_reject", "REJECT", 0, "REJECTED", now)
    insert("img_archived", "ARCHIVED", 0, "KEPT", now)
    insert("img_new", "NEW", 0, "UNREVIEWED", None)      # NEW 不动

    # 升级：应用 0017
    monkeypatch.setattr(migrations_module, "MIGRATIONS", original_migrations)
    applied = init_database(engine)
    assert applied[-1].migration_id == "0017_image_review_semantics"

    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, status, favorite, review_status, (reviewed_at IS NOT NULL) AS has_reviewed "
            "FROM images ORDER BY id"
        )).all()
        by_id = {row[0]: row for row in rows}
        fav_left = conn.execute(
            text("SELECT COUNT(*) FROM images WHERE status = 'FAVORITE'")
        ).scalar_one()

    assert by_id["img_fav"][1] == "KEEP" and by_id["img_fav"][2] == 1
    assert by_id["img_fav_nofav"][1] == "KEEP" and by_id["img_fav_nofav"][2] == 1
    assert by_id["img_new_fav"][1] == "KEEP" and by_id["img_new_fav"][2] == 1
    assert by_id["img_new_fav"][3] == "KEPT" and bool(by_id["img_new_fav"][4])
    assert by_id["img_keep"][1] == "KEEP" and bool(by_id["img_keep"][4])
    assert by_id["img_reject"][1] == "REJECT" and by_id["img_reject"][3] == "REJECTED"
    assert by_id["img_archived"][1] == "ARCHIVED" and by_id["img_archived"][3] == "KEPT"
    assert by_id["img_new"][1] == "NEW" and by_id["img_new"][3] == "UNREVIEWED"
    assert not bool(by_id["img_new"][4])
    assert fav_left == 0, "0017 后不应再有 FAVORITE 行"
    engine.dispose()
