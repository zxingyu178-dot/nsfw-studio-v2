"""只读移动出图进度的配对与持久化队列合同。"""

import time

from fastapi.testclient import TestClient

from app.main import create_app
from app.models.job import Job, JobItem, JobStage, JobStageItem
from app.services import mobile_pairing_service
from test_job_queue import make_snapshot, mock_settings
from test_mobile_v2_contract import auth

PROGRESS_PATH = "/mobile/generation/progress"


def _job(name: str, status: str, kind: str = "generate") -> Job:
    return Job(
        id=f"job_{name}",
        source="web",
        status=status,
        job_kind=kind,
        prompt_mode="full",
        positive_prompt_snapshot="fixture prompt",
        workbench_snapshot_json="{}",
        generation_settings_json="{}",
        requested_count=6,
    )


def _start_slot(session, job: Job, index: int) -> JobStageItem:
    stage = session.get(JobStage, f"stage_{job.id}")
    if stage is None:
        stage = JobStage(
            id=f"stage_{job.id}",
            job=job,
            stage_index=0,
            module_id="basic_generate",
            module_version="v1",
            status="RUNNING",
            total_count=job.requested_count,
        )
    item = JobItem(
        id=f"item_{job.id}_{index}",
        job=job,
        item_index=index,
        status="RUNNING",
    )
    slot = JobStageItem(
        id=f"slot_{job.id}_{index}",
        stage=stage,
        job_item=item,
        item_index=index,
        status="RUNNING",
    )
    session.add(slot)
    return slot


def _assert_progress(mobile_client, headers, current, total, remaining):
    response = mobile_client.get(PROGRESS_PATH, headers=headers)
    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"].lower()
    payload = response.json()
    assert payload["success"] is True
    assert payload["data"] == {
        "current_image": current,
        "images_in_segment": total,
        "remaining_segments": remaining,
    }


def test_bridge_advertises_progress_and_keeps_desktop_queue_private(
    mobile_client, session_factory,
):
    response = mobile_client.get("/mobile/system/health")
    assert response.status_code == 200
    assert "mobile_generation_progress_v1" in response.json()["data"]["capabilities"]
    headers, _ = auth(mobile_client, session_factory)
    assert mobile_client.get("/api/v1/queue", headers=headers).status_code == 404


def test_progress_uses_committed_active_slot_and_remaining_generation_segments(
    mobile_client, session_factory,
):
    headers, _ = auth(mobile_client, session_factory)
    with session_factory() as session:
        current = _job("current", "RUNNING")
        queued = [_job(f"waiting_{index}", "QUEUED") for index in range(18)]
        paused = _job("paused", "PAUSED")
        excluded = [
            _job("completed", "COMPLETED"),
            _job("failed", "FAILED"),
            _job("cancelled", "CANCELLED"),
            _job("interrupted", "INTERRUPTED"),
            _job("processing", "QUEUED", kind="process"),
        ]
        session.add_all([current, *queued, paused, *excluded])
        third = _start_slot(session, current, 2)
        # The active image is authoritative even if the completed counter differs.
        assert current.completed_count == 0
        session.commit()

        _assert_progress(mobile_client, headers, 3, 6, 20)

        third.status = "COMPLETED"
        session.commit()
        # A persisted RUNNING job/item can outlive the actual stage slot.
        assert third.job_item.status == "RUNNING"
        _assert_progress(mobile_client, headers, None, None, 20)

        fourth = _start_slot(session, current, 3)
        session.commit()
        _assert_progress(mobile_client, headers, 4, 6, 20)

        fourth.status = "COMPLETED"
        current.status = "COMPLETED"
        queued[0].status = "RUNNING"
        first = _start_slot(session, queued[0], 0)
        session.commit()
        _assert_progress(mobile_client, headers, 1, 6, 19)

        first.status = "COMPLETED"
        for job in queued:
            job.status = "CANCELLED"
        processing = excluded[-1]
        processing.status = "RUNNING"
        _start_slot(session, processing, 4)
        session.commit()
        _assert_progress(mobile_client, headers, None, None, 1)

        paused.status = "CANCELLED"
        session.commit()
        _assert_progress(mobile_client, headers, None, None, 0)


def test_progress_rejects_unpaired_invalid_and_revoked_devices(
    mobile_client, session_factory,
):
    assert mobile_client.get(PROGRESS_PATH).status_code == 401
    invalid = {"Authorization": "Bearer synthetic-invalid-token"}
    assert mobile_client.get(PROGRESS_PATH, headers=invalid).status_code == 401

    headers, device_id = auth(mobile_client, session_factory)
    _assert_progress(mobile_client, headers, None, None, 0)
    with session_factory() as session:
        mobile_pairing_service.revoke_device(session, device_id)
    response = mobile_client.get(PROGRESS_PATH, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "DEVICE_REVOKED"

def test_bridge_reads_real_worker_transitions_with_mock_engine(
    mobile_client, session_factory, settings,
):
    headers, _ = auth(mobile_client, session_factory)
    worker_settings = mock_settings(settings, delay_per_item_ms=350)
    with TestClient(create_app(worker_settings)) as desktop:
        assert desktop.post("/api/v1/queue/pause").status_code == 200
        for count in (2, 1):
            assert desktop.post("/api/v1/jobs", json={"snapshot": make_snapshot(count=count)}).status_code == 201
        _assert_progress(mobile_client, headers, None, None, 2)
        assert desktop.post("/api/v1/queue/resume").status_code == 200

        observed = []
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            response = mobile_client.get(PROGRESS_PATH, headers=headers)
            assert response.status_code == 200
            progress = response.json()["data"]
            sample = (progress["current_image"], progress["images_in_segment"], progress["remaining_segments"])
            if not observed or sample != observed[-1]:
                observed.append(sample)
            if sample == (None, None, 0):
                break
            time.sleep(0.04)

        expected = [(1, 2, 2), (2, 2, 2), (1, 1, 1), (None, None, 0)]
        assert [sample for sample in observed if sample[0] is not None or sample[2] == 0] == expected, observed
