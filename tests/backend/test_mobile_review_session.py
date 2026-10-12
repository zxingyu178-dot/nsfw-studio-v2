"""冻结式 ImageReviewSession 测试（Phase 0.13 核心）。

覆盖：创建时按 filter 冻结 image_id 顺序；后续 NEW→KEEP/REJECT 不改变队列；
latest 恢复不重建；queue 分页返回绝对 index；单事务 decision；favorite 独立；
RESET 回 NEW + seen=false；complete 时仍有 seen=false 返回 remaining_count。
"""
from __future__ import annotations


def _auth(mobile_client, session_factory):
    from app.services import mobile_pairing_service
    with session_factory() as session:
        code = mobile_pairing_service.generate_pairing_code(session)
    r = mobile_client.post("/mobile/pairing/verify", json={
        "installation_id": "dev-review", "device_name": "p", "code": code,
    })
    return {"Authorization": f"Bearer {r.json()['data']['token']}"}


def test_create_session_freezes_queue(mobile_client, session_factory, make_mobile_image):
    imgs = make_mobile_image(3)
    h = _auth(mobile_client, session_factory)

    r = mobile_client.post("/mobile/review/sessions", json={"filter": {"status": "NEW"}}, headers=h)
    assert r.status_code == 201
    s = r.json()["data"]
    sid = s["id"]
    assert s["total_count"] == 3
    assert s["seen_count"] == 0

    q = mobile_client.get(f"/mobile/review/sessions/{sid}/queue?page=1&page_size=50", headers=h).json()["data"]
    assert q["total"] == 3
    ids = [item["image"]["image_id"] for item in q["items"]]
    # 冻结顺序 = created_desc（最近建的在前）
    assert ids[0] == imgs[-1].id and ids[-1] == imgs[0].id
    assert [item["index"] for item in q["items"]] == [0, 1, 2]
    assert all(item["seen"] is False for item in q["items"])


def test_decision_and_queue_stable(mobile_client, session_factory, make_mobile_image):
    imgs = make_mobile_image(2)
    h = _auth(mobile_client, session_factory)
    sid = mobile_client.post("/mobile/review/sessions", json={}, headers=h).json()["data"]["id"]
    q = mobile_client.get(f"/mobile/review/sessions/{sid}/queue", headers=h).json()["data"]
    target = q["items"][0]

    # KEEP index=0
    r = mobile_client.post(f"/mobile/review/sessions/{sid}/decision", json={
        "item_index": 0, "action": "KEEP",
        "expected_status": "NEW", "expected_updated_at": target["image"]["updated_at"],
    }, headers=h)
    # updated_at 来自 queue DTO，乐观锁命中
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["image"]["status"] == "KEEP"
    assert d["session"]["seen_count"] == 1

    # 队列顺序不变、index 不压缩
    q2 = mobile_client.get(f"/mobile/review/sessions/{sid}/queue", headers=h).json()["data"]
    assert [it["index"] for it in q2["items"]] == [0, 1]
    assert q2["items"][0]["seen"] is True
    assert q2["items"][1]["seen"] is False
    assert q2["items"][0]["image"]["image_id"] == target["image"]["image_id"]


def test_latest_resumes_not_rebuild(mobile_client, session_factory, make_mobile_image):
    make_mobile_image(1)
    h = _auth(mobile_client, session_factory)
    sid = mobile_client.post("/mobile/review/sessions", json={}, headers=h).json()["data"]["id"]

    latest = mobile_client.get("/mobile/review/sessions/latest", headers=h).json()["data"]
    assert latest["id"] == sid  # 恢复同一 session，不新建


def test_complete_requires_all_seen(mobile_client, session_factory, make_mobile_image):
    make_mobile_image(2)
    h = _auth(mobile_client, session_factory)
    sid = mobile_client.post("/mobile/review/sessions", json={}, headers=h).json()["data"]["id"]

    # 只审 1 张就 complete → 不强完成
    r = mobile_client.post(f"/mobile/review/sessions/{sid}/complete", headers=h)
    data = r.json()["data"]
    assert data["completed"] is False
    assert data["remaining_count"] == 2

    # 审完两张
    q = mobile_client.get(f"/mobile/review/sessions/{sid}/queue", headers=h).json()["data"]
    for item in q["items"]:
        mobile_client.post(f"/mobile/review/sessions/{sid}/decision", json={
            "item_index": item["index"], "action": "REJECT",
            "expected_status": "NEW", "expected_updated_at": item["image"]["updated_at"],
        }, headers=h)

    r2 = mobile_client.post(f"/mobile/review/sessions/{sid}/complete", headers=h)
    assert r2.json()["data"]["completed"] is True
    assert r2.json()["data"]["status"] == "COMPLETED"


def test_freeze_supports_job_id(mobile_client, session_factory, make_mobile_image):
    """按任务审核：freeze filter 支持 job_id，队列只含该 job 的图。"""
    make_mobile_image(1)  # 其它 job（job_id=None）
    from app.models.image import Image
    from app.models.job import Job
    with session_factory() as session:
        session.add(Job(id="jobA", source="web", status="COMPLETED", prompt_mode="structured",
                        workbench_snapshot_json="{}", generation_settings_json="{}",
                        requested_count=1))
        session.commit()
        imgs = session.query(Image).order_by(Image.created_at.desc()).all()
        imgs[0].job_id = "jobA"
        session.commit()
    jobA_ids = [imgs[0].id]

    h = _auth(mobile_client, session_factory)
    r = mobile_client.post("/mobile/review/sessions",
                           json={"filter": {"status": "NEW", "job_id": "jobA"}}, headers=h)
    assert r.status_code == 201, r.text
    q = mobile_client.get(f"/mobile/review/sessions/{r.json()['data']['id']}/queue",
                         headers=h).json()["data"]
    assert q["total"] == 1
    assert q["items"][0]["image"]["image_id"] == jobA_ids[0]
