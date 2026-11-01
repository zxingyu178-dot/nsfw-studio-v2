"""W3.0 Mobile Review Bridge V2：事件流 / 快照 / 详情 / 单图审核 / 幂等 / 评分 / 安全。"""
from __future__ import annotations

import io
import uuid

from PIL import Image as PILImage
from sqlalchemy import select

from app.core.timeutil import utc_now_iso
from app.models import Job
from app.models.mobile_review import MobileImageEvent
from app.services import cleanup_service, image_event_service, image_service, prompt_service
from app.storage.manager import StorageManager


def auth(mobile_client, session_factory, *, installation_id: str | None = None) -> tuple[dict, str]:
    from app.services import mobile_pairing_service

    with session_factory() as session:
        code = mobile_pairing_service.generate_pairing_code(session)
    response = mobile_client.post("/mobile/pairing/verify", json={
        "installation_id": installation_id or f"dev_{uuid.uuid4().hex[:8]}",
        "device_name": "pytest",
        "code": code,
    })
    data = response.json()["data"]
    return {"Authorization": f"Bearer {data['token']}"}, data["device_id"]


def events(mobile_client, headers, *, cursor=None, limit=None) -> dict:
    params = {}
    if cursor is not None:
        params["cursor"] = cursor
    if limit is not None:
        params["limit"] = limit
    return mobile_client.get("/mobile/events", params=params, headers=headers).json()["data"]


def detail(mobile_client, headers, image_id: str) -> dict:
    return mobile_client.get(f"/mobile/images/{image_id}", headers=headers).json()["data"]


def review(mobile_client, headers, image_id: str, body: dict, key: str):
    return mobile_client.post(
        f"/mobile/images/{image_id}/review", json=body, headers={**headers, "Idempotency-Key": key},
    )


def image_events(session, event_type: str | None = None) -> list[MobileImageEvent]:
    query = select(MobileImageEvent).order_by(MobileImageEvent.seq.asc())
    if event_type:
        query = query.where(MobileImageEvent.event_type == event_type)
    return list(session.scalars(query))


def test_generated_image_emits_created_event(mobile_client, session_factory, make_mobile_image):
    image = make_mobile_image(1)[0]
    headers, _ = auth(mobile_client, session_factory)
    data = events(mobile_client, headers)
    created = [e for e in data["events"] if e["event_type"] == "IMAGE_CREATED"]
    assert len(created) == 1
    assert created[0]["image_id"] == image.id
    assert created[0]["payload"]["width"] == image.width
    assert "file_path" not in created[0]["payload"]


def test_external_import_emits_imported_event(mobile_client, session_factory, settings, png_bytes):
    storage = StorageManager(settings)
    with session_factory() as session:
        result = image_service.import_images_batch(
            session, storage, [("import.png", "image/png", png_bytes)],
        )
        image_id = result.imported[0].id
    headers, _ = auth(mobile_client, session_factory)
    data = events(mobile_client, headers)
    imported = [e for e in data["events"] if e["event_type"] == "IMAGE_IMPORTED"]
    assert [e["image_id"] for e in imported] == [image_id]


def test_desktop_review_and_favorite_events_are_independent(
    mobile_client, session_factory, make_mobile_image,
):
    image = make_mobile_image(1)[0]
    headers, _ = auth(mobile_client, session_factory)
    with session_factory() as session:
        image_service.set_image_status(session, image.id, "KEEP", note="保留备注")
    with session_factory() as session:
        image_service.set_favorite(session, image.id, True)
    data = events(mobile_client, headers)
    review = [e for e in data["events"] if e["event_type"] == "IMAGE_REVIEW_UPDATED"]
    favorite = [e for e in data["events"] if e["event_type"] == "IMAGE_FAVORITE_UPDATED"]
    metadata = [e for e in data["events"] if e["event_type"] == "IMAGE_METADATA_UPDATED"]
    assert len(review) == 1 and len(favorite) == 1 and len(metadata) == 1
    assert review[0]["payload"]["status"] == "KEEP"
    assert metadata[0]["payload"]["review_note"] == "保留备注"
    assert favorite[0]["payload"]["is_favorite"] is True


def test_mobile_review_event_and_favorite_independence(mobile_client, session_factory, make_mobile_image):
    image = make_mobile_image(1)[0]
    headers, _ = auth(mobile_client, session_factory)
    current = detail(mobile_client, headers, image.id)

    keep = review(mobile_client, headers, image.id, {
        "action": "KEEP", "expected_revision": current["revision"],
    }, "keep-1")
    assert keep.status_code == 200, keep.text
    after_keep = keep.json()["data"]
    assert after_keep["image"]["status"] == "KEEP"
    assert after_keep["image"]["is_favorite"] is False

    fav = review(mobile_client, headers, image.id, {
        "favorite": True, "expected_revision": after_keep["revision"],
    }, "fav-1")
    assert fav.status_code == 200, fav.text
    assert fav.json()["data"]["image"]["status"] == "KEEP"
    assert fav.json()["data"]["image"]["is_favorite"] is True

    data = events(mobile_client, headers)
    review_events = [e for e in data["events"] if e["event_type"] == "IMAGE_REVIEW_UPDATED"]
    favorite_events = [e for e in data["events"] if e["event_type"] == "IMAGE_FAVORITE_UPDATED"]
    assert len(review_events) == 1 and len(favorite_events) == 1


def test_removed_event_survives_image_delete(mobile_client, session_factory, settings, make_mobile_image):
    image = make_mobile_image(1)[0]
    headers, _ = auth(mobile_client, session_factory)
    with session_factory() as session:
        image_service.set_image_status(session, image.id, "REJECT")
        cleanup_service.execute(session, StorageManager(settings), [image.id])
        assert session.get(image_service.Image, image.id) is None
    data = events(mobile_client, headers)
    removed = [e for e in data["events"] if e["event_type"] == "IMAGE_REMOVED"]
    assert len(removed) == 1
    assert removed[0]["image_id"] == image.id


def test_event_cursor_pagination_no_gap_or_duplicate(
    mobile_client, session_factory, make_mobile_image, session,
):
    make_mobile_image(4)
    headers, _ = auth(mobile_client, session_factory)
    collected: list[str] = []
    cursor = None
    pages = 0
    while True:
        page = events(mobile_client, headers, cursor=cursor, limit=2)
        collected.extend(event["event_id"] for event in page["events"])
        pages += 1
        cursor = page["next_cursor"]
        if not page["has_more"]:
            break
        assert pages < 10
    expected = [row.event_id for row in image_events(session)]
    assert collected == expected, "分页不得漏事件或重复"
    assert len(collected) == len(set(collected))


def test_invalid_and_future_cursor_expired(mobile_client, session_factory, make_mobile_image):
    make_mobile_image(1)
    headers, _ = auth(mobile_client, session_factory)
    bad = mobile_client.get("/mobile/events", params={"cursor": "mr2_bad"}, headers=headers)
    assert bad.status_code == 410
    assert bad.json()["error"]["code"] == "CURSOR_EXPIRED"
    assert bad.json()["error"]["details"]["snapshot_required"] is True

    future = mobile_client.get(
        "/mobile/events", params={"cursor": image_event_service.encode_cursor(9999)}, headers=headers,
    )
    assert future.status_code == 410


def test_snapshot_watermark_has_no_gap_with_incremental_events(
    mobile_client, session_factory, make_mobile_image,
):
    make_mobile_image(1)
    headers, _ = auth(mobile_client, session_factory)
    snap = mobile_client.get("/mobile/sync/snapshot", headers=headers).json()["data"]
    assert snap["image_count"] == 1
    assert snap["cursor"]
    new_image = make_mobile_image(1)[0]
    page = events(mobile_client, headers, cursor=snap["cursor"])
    assert [e["image_id"] for e in page["events"]] == [new_image.id]
    assert len(snap["images"]) == 1


def test_image_detail_links_prompt_and_version(
    mobile_client, session_factory, settings, png_bytes, session,
):
    prompt = prompt_service.create_prompt(
        session, name="detail prompt", mode="full",
        positive_prompt="silver hair, kimono", negative_prompt="low quality",
    )
    version = prompt_service.get_current_version(session, prompt)
    now = utc_now_iso()
    job = Job(
        id="job_detail", source="web", status="COMPLETED", prompt_mode="full",
        positive_prompt_snapshot="silver hair, kimono", negative_prompt_snapshot="low quality",
        workbench_snapshot_json=(
            '{"source_prompt_id":"%s","source_prompt_version_id":"%s"}' % (prompt.id, version.id)
        ),
        generation_settings_json="{}", workflow_snapshot_json='{"modules":[]}',
        requested_count=1, completed_count=1, created_at=now, updated_at=now,
    )
    session.add(job)
    session.commit()
    storage = StorageManager(settings)
    with session_factory() as db:
        image = image_service.import_engine_output(
            db, storage, data=png_bytes, original_filename="detail.png",
            job=db.get(Job, "job_detail"), seed=42,
            metadata={"module_id": "basic_generate", "module_version": "v1"},
        )
        image_id = image.id
    headers, _ = auth(mobile_client, session_factory)
    data = detail(mobile_client, headers, image_id)
    assert data["job_id"] == "job_detail"
    assert data["seed"] == 42
    assert data["prompt_snapshot"] == "silver hair, kimono"
    assert data["negative_prompt"] == "low quality"
    assert data["source_prompt_id"] == prompt.id
    assert data["prompt_name"] == "detail prompt"
    assert data["prompt_version_no"] == 1
    assert data["generation_module"] == "basic_generate"
    assert "file_path" not in data


def test_imported_image_has_no_fake_prompt(mobile_client, session_factory, settings, png_bytes):
    with session_factory() as session:
        imported = image_service.import_images_batch(
            session, StorageManager(settings), [("raw.png", "image/png", png_bytes)],
        ).imported[0]
        image_id = imported.id
    headers, _ = auth(mobile_client, session_factory)
    data = detail(mobile_client, headers, image_id)
    assert data["job_id"] is None
    assert data["prompt_snapshot"] is None
    assert data["source_prompt_id"] is None
    assert data["prompt_name"] is None


def test_review_conflict_returns_authoritative_image(
    mobile_client, session_factory, make_mobile_image,
):
    image = make_mobile_image(1)[0]
    headers, _ = auth(mobile_client, session_factory)
    current = detail(mobile_client, headers, image.id)
    with session_factory() as session:
        image_service.set_image_status(session, image.id, "KEEP")
    stale = review(mobile_client, headers, image.id, {
        "action": "REJECT", "expected_revision": current["revision"],
    }, "conflict-1")
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "REVIEW_CONFLICT"
    authoritative = stale.json()["error"]["details"]["image"]
    assert authoritative["status"] == "KEEP"
    assert authoritative["revision"] != current["revision"]


def test_idempotent_review_replay_and_payload_conflict(
    mobile_client, session_factory, make_mobile_image, session,
):
    image = make_mobile_image(1)[0]
    headers, _ = auth(mobile_client, session_factory)
    current = detail(mobile_client, headers, image.id)
    body = {"action": "KEEP", "expected_revision": current["revision"]}
    first = review(mobile_client, headers, image.id, body, "idem-1")
    assert first.status_code == 200, first.text
    event_count = len(image_events(session, "IMAGE_REVIEW_UPDATED"))

    replay = review(mobile_client, headers, image.id, body, "idem-1")
    assert replay.status_code == 200
    assert replay.json()["data"]["idempotent_replay"] is True
    assert replay.json()["data"]["image"]["image_id"] == image.id
    assert len(image_events(session, "IMAGE_REVIEW_UPDATED")) == event_count

    conflict = review(
        mobile_client, headers, image.id,
        {"favorite": True, "expected_revision": current["revision"]}, "idem-1",
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_prompt_evaluation_version_link_and_atomic_receipt(
    mobile_client, session_factory, session,
):
    prompt = prompt_service.create_prompt(
        session, name="rate prompt", mode="full", positive_prompt="first version",
    )
    v1 = prompt_service.get_current_version(session, prompt)
    v2, _ = prompt_service.add_prompt_version(
        session, prompt.id, mode="full", positive_prompt="second version",
    )
    headers, device_id = auth(mobile_client, session_factory)
    body = {"overall_score": 4, "dimension_scores": {"style": 4}, "notes": "手机评分"}
    response = mobile_client.post(
        f"/mobile/prompts/{prompt.id}/versions/{v1.id}/evaluation",
        json=body, headers={**headers, "Idempotency-Key": "eval-1"},
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["evaluation"]["prompt_version_id"] == v1.id
    assert data["evaluation"]["source"] == "mobile"

    listed = mobile_client.get(
        f"/mobile/prompts/{prompt.id}/versions/{v1.id}/evaluations", headers=headers,
    ).json()["data"]["evaluations"]
    assert [item["id"] for item in listed] == [data["evaluation"]["id"]]
    other = mobile_client.get(
        f"/mobile/prompts/{prompt.id}/versions/{v2.id}/evaluations", headers=headers,
    ).json()["data"]["evaluations"]
    assert other == []

    # 评分 + 事件 + 回执原子提交；重放不重复
    from app.models import PromptEvaluation
    from app.models.mobile_review import MobileMutationReceipt
    assert session.query(PromptEvaluation).count() == 1
    assert session.query(MobileMutationReceipt).count() == 1
    assert len(image_events(session, "PROMPT_EVALUATED")) == 1
    replay = mobile_client.post(
        f"/mobile/prompts/{prompt.id}/versions/{v1.id}/evaluation",
        json=body, headers={**headers, "Idempotency-Key": "eval-1"},
    )
    assert replay.json()["data"]["idempotent_replay"] is True

    wrong = mobile_client.post(
        f"/mobile/prompts/{prompt.id}/versions/{v2.id}/evaluation",
        json={**body, "notes": "wrong version"}, headers={**headers, "Idempotency-Key": "eval-2"},
    )
    assert wrong.status_code == 201
    assert wrong.json()["data"]["evaluation"]["prompt_version_id"] == v2.id


def test_new_endpoints_require_bearer_and_revoked_device_rejected(
    mobile_client, session_factory, make_mobile_image,
):
    make_mobile_image(1)
    assert mobile_client.get("/mobile/events").status_code == 401
    assert mobile_client.get("/mobile/sync/snapshot").status_code == 401
    headers, device_id = auth(mobile_client, session_factory)
    with session_factory() as session:
        from app.services import mobile_pairing_service
        mobile_pairing_service.revoke_device(session, device_id)
    for path in ("/mobile/events", "/mobile/sync/snapshot"):
        assert mobile_client.get(path, headers=headers).status_code == 401
