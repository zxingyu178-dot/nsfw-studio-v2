"""W3.1 MediaReview V2 客户端合同：feed / details / decision / prompt 审核 / 幂等。"""
from __future__ import annotations

import json
import uuid
import pytest
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.timeutil import utc_now_iso
from app.models import Image, Job, PromptEvaluation
from app.models.mobile_review import MobileImageEvent, MobileMutationReceipt
from app.services import (
    image_event_service,
    image_service,
    mobile_pairing_service,
    mobile_v2_service,
    prompt_service,
)


def auth(mobile_client, session_factory, *, installation_id: str | None = None) -> tuple[dict, str]:
    with session_factory() as session:
        code = mobile_pairing_service.generate_pairing_code(session)
    response = mobile_client.post("/mobile/pairing/verify", json={
        "installation_id": installation_id or f"dev_{uuid.uuid4().hex[:8]}",
        "device_name": "pytest",
        "code": code,
    })
    data = response.json()["data"]
    return {"Authorization": f"Bearer {data['token']}"}, data["device_id"]


def feed(mobile_client, headers, **params) -> dict:
    return mobile_client.get("/mobile/images/feed", params=params, headers=headers).json()["data"]


def details(mobile_client, headers, image_id: str) -> dict:
    return mobile_client.get(f"/mobile/images/{image_id}/details", headers=headers).json()["data"]


def decide(mobile_client, headers, image_id: str, body: dict):
    return mobile_client.post(f"/mobile/review/images/{image_id}/decision", json=body, headers=headers)


def test_health_declares_v2_capabilities(mobile_client):
    data = mobile_client.get("/mobile/system/health").json()["data"]
    assert data["api_contract"] == 2
    for capability in (
        "mobile_feed_v2", "mobile_image_details_v2", "mobile_image_decision_v2",
        "mobile_prompt_review_v2", "mobile_prompt_evaluation_v2",
    ):
        assert capability in data["capabilities"]
    assert "permanent_delete" not in data["capabilities"]


def _batch_items(client, headers, images):
    return [{"image_id": image.id, "action": "KEEP" if index == 0 else "REJECT",
             "expected_revision": details(client, headers, image.id)["revision"]}
            for index, image in enumerate(images)]


def test_batch_review_mixed_atomic_receipt_and_device_scope(mobile_client, session_factory, make_mobile_image):
    images = make_mobile_image(2)
    headers, _ = auth(mobile_client, session_factory)
    other, _ = auth(mobile_client, session_factory)
    with session_factory() as session:
        session.get(Image, images[0].id).favorite = True
        session.commit()
    items = _batch_items(mobile_client, headers, images)
    key = "batch-mixed"
    route = "/mobile/images/batch-review"
    request_headers = {**headers, "Idempotency-Key": key}
    before = feed(mobile_client, headers)["next_cursor"]
    response = mobile_client.post(route, headers=request_headers, json={"items": items})
    assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["kept_count"] == result["rejected_count"] == 1
    assert [row["status"] for row in result["items"]] == ["KEEP", "REJECT"]
    with session_factory() as session:
        assert session.get(Image, images[0].id).favorite is True
    changes = feed(mobile_client, headers, cursor=before)["items"]
    assert len(changes) == 2 and {row["image_id"] for row in changes} == {image.id for image in images}
    repeated = mobile_client.post(route, headers=request_headers, json={"items": items})
    assert repeated.status_code == 200 and repeated.json()["data"] == result
    assert feed(mobile_client, headers, cursor=before)["items"] == changes
    receipt = f"{route}/{key}/result"
    assert mobile_client.get(receipt, headers=headers).json()["data"] == result
    assert mobile_client.get(receipt, headers=other).status_code == 404
    assert mobile_client.get(receipt).status_code == 401
    changed = {"items": [{**items[0], "action": "REJECT"}, items[1]]}
    conflict = mobile_client.post(route, headers=request_headers, json=changed)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    assert "mobile_image_batch_review_v1" in mobile_client.get("/mobile/system/health").json()["data"]["capabilities"]


@pytest.mark.parametrize("problem", ["revision", "reviewed", "missing", "duplicate", "empty", "oversize"])
def test_batch_review_rejects_entire_invalid_page(mobile_client, session_factory, make_mobile_image, problem):
    images = make_mobile_image(2)
    headers, _ = auth(mobile_client, session_factory)
    items = _batch_items(mobile_client, headers, images)
    if problem == "revision":
        items[1]["expected_revision"] = "stale"
    elif problem == "reviewed":
        with session_factory() as session:
            session.get(Image, images[1].id).status = "KEEP"
            session.commit()
    elif problem == "missing":
        items[1]["image_id"] = "unknown-image"
    elif problem == "duplicate":
        items[1] = dict(items[0])
    elif problem == "empty":
        items = []
    else:
        items = items * 6
    with session_factory() as session:
        events_before = session.scalar(select(func.count()).select_from(MobileImageEvent))
    response = mobile_client.post("/mobile/images/batch-review", headers={**headers, "Idempotency-Key": "invalid-page"}, json={"items": items})
    assert response.status_code in (404, 409, 422), response.text
    with session_factory() as session:
        assert session.get(Image, images[0].id).status == "NEW"
        assert session.scalar(select(func.count()).select_from(MobileImageEvent)) == events_before
        assert session.scalar(select(func.count()).select_from(MobileMutationReceipt)) == 0


def test_batch_review_event_failure_rolls_back_all(mobile_client, session_factory, make_mobile_image, monkeypatch):
    images = make_mobile_image(2)
    headers, _ = auth(mobile_client, session_factory)
    items = _batch_items(mobile_client, headers, images)
    original = image_event_service.record_review_change
    calls = 0
    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("controlled event failure")
        return original(*args, **kwargs)
    monkeypatch.setattr(image_event_service, "record_review_change", fail_second)
    with session_factory() as session:
        before = session.scalar(select(func.count()).select_from(MobileImageEvent))
    try:
        response = mobile_client.post("/mobile/images/batch-review", headers={**headers, "Idempotency-Key": "rollback"}, json={"items": items})
        assert response.status_code == 500
    except RuntimeError as error:
        assert str(error) == "controlled event failure"
    with session_factory() as session:
        assert all(session.get(Image, image.id).status == "NEW" for image in images)
        assert session.scalar(select(func.count()).select_from(MobileImageEvent)) == before
        assert session.scalar(select(func.count()).select_from(MobileMutationReceipt)) == 0


def test_feed_requires_pairing(mobile_client):
    assert mobile_client.get("/mobile/images/feed").status_code == 401


@pytest.mark.parametrize("size,mime,expected_size,expected_mime", [
    (1234, "image/png", 1234, "image/png"),
    (0, "image/webp", 0, "image/webp"),
    (None, None, None, None),
    (-1, "", None, None),
    (True, 12, None, None),
])
def test_details_projects_w41_asset_metadata(
    mobile_client, session_factory, make_mobile_image, size, mime, expected_size, expected_mime,
):
    image = make_mobile_image(1)[0]
    with session_factory() as session:
        row = session.get(Image, image.id)
        row.metadata_json = json.dumps({"file_size": size, "mime_type": mime})
        session.commit()
    headers, _ = auth(mobile_client, session_factory)
    response = mobile_client.get(f"/mobile/images/{image.id}/details", headers=headers)
    assert response.status_code == 200
    result = response.json()["data"]
    assert result["size_bytes"] == expected_size
    assert result["mime"] == expected_mime
    assert "storage_key" not in result and "file_path" not in result


def test_feed_first_sync_paginates_without_gap_or_duplicate(
    mobile_client, session_factory, make_mobile_image,
):
    images = make_mobile_image(3)
    headers, _ = auth(mobile_client, session_factory)
    first = feed(mobile_client, headers, limit=2)
    assert len(first["items"]) == 2 and first["has_more"] is True
    assert first["resumed"] is False
    second = feed(mobile_client, headers, cursor=first["next_cursor"], limit=2)
    assert len(second["items"]) == 1 and second["has_more"] is False
    assert second["resumed"] is True
    collected = first["items"] + second["items"]
    assert {row["image_id"] for row in collected} == {image.id for image in images}
    assert all(row["revision"].isdecimal() for row in collected)
    empty = feed(mobile_client, headers, cursor=second["next_cursor"])
    assert empty["items"] == [] and empty["has_more"] is False


def test_feed_desktop_update_and_delete_are_events(
    mobile_client, session_factory, make_mobile_image, settings,
):
    from app.services import cleanup_service
    from app.storage.manager import StorageManager

    image = make_mobile_image(1)[0]
    headers, _ = auth(mobile_client, session_factory)
    first = feed(mobile_client, headers)
    item = first["items"][0]
    original_revision = int(item["revision"])

    with session_factory() as session:
        image_service.set_favorite(session, image.id, True)
    changed = feed(mobile_client, headers, cursor=first["next_cursor"])
    assert changed["items"][0]["is_favorite"] is True
    assert int(changed["items"][0]["revision"]) > original_revision

    with session_factory() as session:
        image_service.set_image_status(session, image.id, "REJECT")
    from app.database.base import make_engine
    engine = make_engine(settings.storage.database_path)

    storage = StorageManager(settings)
    with Session(engine) as session:
        cleanup_service.execute(session, storage, [image.id])
        assert session.get(Image, image.id) is None
    engine.dispose()
    removed = feed(mobile_client, headers, cursor=changed["next_cursor"])
    assert removed["items"][0]["event"] == "REMOVE"
    assert removed["items"][0]["image_id"] == image.id
    assert int(removed["items"][0]["revision"]) > int(changed["items"][0]["revision"])


def test_details_link_states_and_no_fake_prompt(
    mobile_client, session_factory, settings, png_bytes, session,
):
    prompt = prompt_service.create_prompt(
        session, name="v2 detail", mode="full",
        positive_prompt="silver hair", negative_prompt="low quality",
    )
    version = prompt_service.get_current_version(session, prompt)
    now = utc_now_iso()
    job = Job(
        id="job_v2_detail", source="web", status="COMPLETED", prompt_mode="full",
        positive_prompt_snapshot="silver hair", negative_prompt_snapshot="low quality",
        workbench_snapshot_json=json.dumps({
            "source_prompt_id": prompt.id, "source_prompt_version_id": version.id,
        }),
        generation_settings_json="{}", requested_count=1, completed_count=1,
        created_at=now, updated_at=now,
    )
    session.add(job)
    session.commit()
    from app.storage.manager import StorageManager

    with session_factory() as db:
        image = image_service.import_engine_output(
            db, StorageManager(settings), data=png_bytes, original_filename="v2.png",
            job=db.get(Job, "job_v2_detail"), seed=7,
        )
        image_id = image.id
    headers, _ = auth(mobile_client, session_factory)
    data = details(mobile_client, headers, image_id)
    assert data["positive_prompt"] == "silver hair"
    assert data["negative_prompt"] == "low quality"
    assert data["link_state"] == "EXACT"
    assert data["prompt_id"] == prompt.id and data["prompt_version_id"] == version.id
    assert "file_path" not in data and "file_path" not in data["positive_prompt"]
    assert data["revision"].isdecimal()

    with session_factory() as db:
        imported = image_service.import_images_batch(
            db, StorageManager(settings), [("raw.png", "image/png", png_bytes)],
        ).imported[0]
        imported_id = imported.id
    imported = details(mobile_client, headers, imported_id)
    assert imported["link_state"] == "UNLINKED"
    assert imported["prompt_id"] is None and imported["positive_prompt"] is None


def test_decision_favorite_only_preserves_status_and_conflict(
    mobile_client, session_factory, make_mobile_image,
):
    image = make_mobile_image(1)[0]
    headers, _ = auth(mobile_client, session_factory)
    data = details(mobile_client, headers, image.id)
    keep = decide(mobile_client, headers, image.id, {
        "action": "KEEP", "expected_updated_at": data["updated_at"],
        "client_request_id": "decision-1",
    })
    assert keep.status_code == 200
    result = keep.json()["data"]
    assert result["status"] == "KEEP" and result["revision"].isdecimal()

    favorite = decide(mobile_client, headers, image.id, {
        "favorite": True, "expected_updated_at": result["updated_at"],
        "client_request_id": "decision-2",
    })
    assert favorite.status_code == 200
    assert favorite.json()["data"]["status"] == "KEEP"
    assert favorite.json()["data"]["is_favorite"] is True

    stale = decide(mobile_client, headers, image.id, {
        "action": "REJECT", "expected_updated_at": result["updated_at"],
        "client_request_id": "decision-3",
    })
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "REVIEW_CONFLICT"
    authoritative = stale.json()["error"]["details"]["image"]
    assert authoritative["status"] == "KEEP" and authoritative["is_favorite"] is True

    replay = decide(mobile_client, headers, image.id, {
        "action": "KEEP", "expected_updated_at": data["updated_at"],
        "client_request_id": "decision-1",
    })
    assert replay.status_code == 200
    assert replay.json()["data"] == result
    altered = decide(mobile_client, headers, image.id, {
        "action": "REJECT", "expected_updated_at": data["updated_at"],
        "client_request_id": "decision-1",
    })
    assert altered.status_code == 409
    assert altered.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_concurrent_decision_writes_single_event_and_receipt(
    mobile_client, session_factory, make_mobile_image,
):
    image = make_mobile_image(1)[0]
    headers, device_id = auth(mobile_client, session_factory)
    data = details(mobile_client, headers, image.id)

    def submit() -> dict:
        with session_factory() as session:
            return mobile_v2_service.decide(
                session, device_id=device_id, image_id=image.id,
                action="KEEP", favorite=None,
                expected_updated_at=data["updated_at"],
                client_request_id="concurrent-decision",
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert results[0] == results[1]
    with session_factory() as session:
        events = list(session.scalars(
            select(MobileImageEvent).where(
                MobileImageEvent.image_id == image.id,
                MobileImageEvent.event_type == "IMAGE_REVIEW_UPDATED",
            )
        ))
        receipts = list(session.scalars(select(MobileMutationReceipt).where(
            MobileMutationReceipt.device_id == device_id,
            MobileMutationReceipt.idempotency_key == "concurrent-decision",
        )))
        assert len(events) == 1 and len(receipts) == 1


def test_concurrent_evaluation_writes_single_history(
    mobile_client, session_factory, session,
):
    prompt = prompt_service.create_prompt(session, name="concurrent score", mode="full", positive_prompt="c")
    version = prompt_service.get_current_version(session, prompt)
    headers, device_id = auth(mobile_client, session_factory)
    body = {
        "prompt_version_id": version.id, "overall_score": 5,
        "client_request_id": "concurrent-score",
    }

    def submit() -> tuple[int, dict]:
        response = mobile_client.post(
            f"/mobile/prompts/{prompt.id}/evaluations", json=body, headers=headers,
        )
        return response.status_code, response.json()["data"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert all(status == 200 for status, _ in results)
    assert results[0][1] == results[1][1]
    with session_factory() as db:
        assert db.scalar(select(func.count()).select_from(PromptEvaluation)) == 1
        events = list(db.scalars(select(MobileImageEvent).where(
            MobileImageEvent.event_type == "PROMPT_EVALUATED",
        )))
        receipts = list(db.scalars(select(MobileMutationReceipt).where(
            MobileMutationReceipt.device_id == device_id,
            MobileMutationReceipt.idempotency_key == "concurrent-score",
        )))
        assert len(events) == 1 and len(receipts) == 1


def test_prompt_evaluation_version_and_overall_receipts_are_device_scoped(
    mobile_client, session_factory, session,
):
    prompt = prompt_service.create_prompt(session, name="v2 score", mode="full", positive_prompt="p")
    version = prompt_service.get_current_version(session, prompt)
    headers, _ = auth(mobile_client, session_factory)
    url = f"/mobile/prompts/{prompt.id}/evaluations"

    version_body = {
        "prompt_version_id": version.id, "overall_score": 4,
        "dimensions": {"style": 5}, "notes": "version", "client_request_id": "score-version",
    }
    first = mobile_client.post(url, json=version_body, headers=headers)
    assert first.status_code == 200
    result = first.json()["data"]
    assert result["prompt_version_id"] == version.id
    assert result["overall_score"] == 4 and result["client_request_id"] == "score-version"
    replay = mobile_client.post(url, json=version_body, headers=headers)
    assert replay.json()["data"] == result
    conflict = mobile_client.post(url, json={**version_body, "overall_score": 2}, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    overall = mobile_client.post(url, json={
        "overall_score": 3, "client_request_id": "score-overall",
    }, headers=headers)
    assert overall.status_code == 200
    summary = mobile_client.get(
        f"/mobile/prompts/{prompt.id}/review-summary",
        params={"version_id": version.id}, headers=headers,
    ).json()["data"]
    assert summary["evaluation_count"] == 1
    assert summary["version_latest"]["overall_score"] == 4
    assert summary["prompt_latest"]["overall_score"] == 3
    assert summary["prompt_latest"]["prompt_version_id"] is None
    assert summary["link_state"] == "EXACT"

    receipt = mobile_client.get("/mobile/prompts/evaluations/score-version", headers=headers).json()["data"]
    assert receipt == {"found": True, "evaluation": result}

    other_headers, _ = auth(mobile_client, session_factory, installation_id="other-device")
    hidden = mobile_client.get(
        "/mobile/prompts/evaluations/score-version", headers=other_headers,
    ).json()["data"]
    assert hidden == {"found": False, "evaluation": None}

    with session_factory() as db:
        rows = list(db.scalars(select(PromptEvaluation)))
        assert len(rows) == 2
        assert all(row.source == "mobile" for row in rows)
        events = list(db.scalars(select(MobileImageEvent).where(
            MobileImageEvent.event_type == "PROMPT_EVALUATED",
        )))
        receipts = list(db.scalars(select(MobileMutationReceipt).where(
            MobileMutationReceipt.operation == "prompt_evaluation",
        )))
        assert len(events) == 2 and len(receipts) == 2, "评分/事件/回执必须原子且不重复"


def test_prompt_evaluation_wrong_version_rejected_without_writes(
    mobile_client, session_factory, session,
):
    prompt = prompt_service.create_prompt(session, name="p1", mode="full", positive_prompt="a")
    other = prompt_service.create_prompt(session, name="p2", mode="full", positive_prompt="b")
    other_version = prompt_service.get_current_version(session, other)
    headers, _ = auth(mobile_client, session_factory)
    response = mobile_client.post(
        f"/mobile/prompts/{prompt.id}/evaluations",
        json={"prompt_version_id": other_version.id, "overall_score": 4,
              "client_request_id": "wrong-version"},
        headers=headers,
    )
    assert response.status_code == 404
    with session_factory() as db:
        assert db.scalar(select(PromptEvaluation).where(
            PromptEvaluation.prompt_id == prompt.id,
        )) is None


def test_prompt_images_use_mobile_thumbnail_path(
    mobile_client, session_factory, session, settings, png_bytes,
):
    prompt = prompt_service.create_prompt(session, name="group", mode="full", positive_prompt="g")
    version = prompt_service.get_current_version(session, prompt)
    now = utc_now_iso()
    job = Job(
        id="job_v2_group", source="web", status="COMPLETED", prompt_mode="full",
        positive_prompt_snapshot="g", negative_prompt_snapshot="",
        workbench_snapshot_json=json.dumps({
            "source_prompt_id": prompt.id, "source_prompt_version_id": version.id,
        }),
        generation_settings_json="{}", requested_count=1, completed_count=1,
        created_at=now, updated_at=now,
    )
    session.add(job)
    session.commit()
    from app.storage.manager import StorageManager

    with session_factory() as db:
        image = image_service.import_engine_output(
            db, StorageManager(settings), data=png_bytes, original_filename="group.png",
            job=db.get(Job, "job_v2_group"),
        )
        image_id = image.id
    headers, _ = auth(mobile_client, session_factory)
    page = mobile_client.get(
        f"/mobile/prompts/{prompt.id}/images",
        params={"version_id": version.id}, headers=headers,
    ).json()["data"]
    assert page["total"] == 1 and page["items"][0]["image_id"] == image_id
    assert page["items"][0]["thumbnail_url"] == f"/mobile/images/{image_id}/thumbnail"
    assert page["has_more"] is False
    summary = mobile_client.get(
        f"/mobile/prompts/{prompt.id}/review-summary",
        params={"version_id": version.id}, headers=headers,
    ).json()["data"]
    assert summary["images_total"] == 1 and summary["seen_count"] == 0
    detail = details(mobile_client, headers, image_id)
    seen = decide(mobile_client, headers, image_id, {
        "favorite": True, "expected_updated_at": detail["updated_at"],
        "client_request_id": "seen-mark",
    })
    assert seen.status_code == 200
    summary = mobile_client.get(
        f"/mobile/prompts/{prompt.id}/review-summary",
        params={"version_id": version.id}, headers=headers,
    ).json()["data"]
    assert summary["seen_count"] == 1 and summary["keep_count"] == 0


def test_new_v2_endpoints_require_bearer_and_revoked_rejected(
    mobile_client, session_factory, make_mobile_image,
):
    make_mobile_image(1)
    paths = (
        "/mobile/images/feed",
        "/mobile/prompts/missing/review-summary",
        "/mobile/prompts/evaluations/x",
    )
    for path in paths:
        assert mobile_client.get(path).status_code == 401
    headers, device_id = auth(mobile_client, session_factory)
    with session_factory() as session:
        mobile_pairing_service.revoke_device(session, device_id)
    for path in paths:
        assert mobile_client.get(path, headers=headers).status_code == 401
    assert mobile_client.post(
        "/mobile/review/images/missing/decision",
        json={"favorite": True, "expected_updated_at": "x", "client_request_id": "k"},
        headers=headers,
    ).status_code == 401


def test_feed_cursor_contract_expiry(mobile_client, session_factory, make_mobile_image):
    make_mobile_image(1)
    headers, _ = auth(mobile_client, session_factory)
    bad = mobile_client.get("/mobile/images/feed", params={"cursor": "garbage"}, headers=headers)
    assert bad.status_code == 410
    assert bad.json()["error"]["code"] == "CURSOR_EXPIRED"
    assert bad.json()["error"]["details"]["snapshot_required"] is True
    future = mobile_client.get(
        "/mobile/images/feed",
        params={"cursor": image_event_service.encode_cursor(10_000)}, headers=headers,
    )
    assert future.status_code == 410
