"""v0.37 P0-A：审核会话批次语义测试（桌面 /api/v1/review/*）。

覆盖指导书要求：
- 0 张建会话立即 COMPLETED，不留下永不结束的空 ACTIVE；
- 旧 ACTIVE 会话 A 不混入新图；显式新建 B（only_new）只含新图；
- 放弃会话语义（保留 items，不删数据）；
- 完成后新图可进入新批次，不复活旧会话；
- new-count 按真实 DB 排除当前会话成员。
"""
from __future__ import annotations


def _create(client, *, mode: str = "all", exclude_session_id: str | None = None,
            close_active: bool = False, filter_obj: dict | None = None) -> dict:
    body: dict = {"mode": mode, "close_active": close_active}
    if filter_obj is not None:
        body["filter"] = filter_obj
    if exclude_session_id is not None:
        body["exclude_session_id"] = exclude_session_id
    r = client.post("/api/v1/review/sessions", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_empty_session_is_immediately_completed(client, make_mobile_image):
    empty = _create(client)
    assert empty["status"] == "COMPLETED"
    assert empty["ended_reason"] == "EMPTY"
    assert empty["total_count"] == 0

    # latest 不会把空会话当 ACTIVE 恢复
    latest = client.get("/api/v1/review/sessions/latest").json()
    assert latest["id"] == empty["id"]
    assert latest["status"] == "COMPLETED"

    # 之后有新图 → 新建会话能看到，不被空 ACTIVE 锁死
    make_mobile_image(5)
    full = _create(client)
    assert full["status"] == "ACTIVE"
    assert full["total_count"] == 5
    q = client.get(f"/api/v1/review/sessions/{full['id']}/queue").json()
    assert q["total"] == 5


def test_only_new_excludes_previous_session_members(client, make_mobile_image):
    first = make_mobile_image(3)
    a = _create(client)
    assert a["total_count"] == 3
    a_ids = {
        item["image"]["image_id"]
        for item in client.get(f"/api/v1/review/sessions/{a['id']}/queue").json()["items"]
    }
    assert a_ids == {img.id for img in first}

    added = make_mobile_image(2)
    # 冻结队列不因新增图片而改变
    q_a = client.get(f"/api/v1/review/sessions/{a['id']}/queue").json()
    assert q_a["total"] == 3

    new_count = client.get(f"/api/v1/review/sessions/{a['id']}/new-count").json()
    assert new_count["count"] == 2

    b = _create(client, mode="only_new", exclude_session_id=a["id"])
    assert b["status"] == "ACTIVE"
    assert b["total_count"] == 2
    b_ids = {
        item["image"]["image_id"]
        for item in client.get(f"/api/v1/review/sessions/{b['id']}/queue").json()["items"]
    }
    assert b_ids == {img.id for img in added}
    assert b_ids.isdisjoint(a_ids)


def test_abandon_keeps_items_and_stops_resume(client, make_mobile_image):
    make_mobile_image(2)
    a = _create(client)
    assert a["status"] == "ACTIVE"

    r = client.post(f"/api/v1/review/sessions/{a['id']}/abandon").json()
    assert r["abandoned"] is True
    assert r["status"] == "COMPLETED"
    assert r["ended_reason"] == "ABANDONED"
    assert r["remaining_count"] == 2
    # items 保留（不删数据）：队列仍可读
    assert client.get(f"/api/v1/review/sessions/{a['id']}/queue").json()["total"] == 2

    # 放弃后 latest 不再返回 ACTIVE，新批次 mode=all 能重新冻结全部未审
    b = _create(client)
    assert b["status"] == "ACTIVE"
    assert b["total_count"] == 2


def test_completed_session_is_not_revived_and_new_batch_works(client, make_mobile_image):
    make_mobile_image(2)
    a = _create(client)
    for item in client.get(f"/api/v1/review/sessions/{a['id']}/queue").json()["items"]:
        r = client.post(f"/api/v1/review/sessions/{a['id']}/decision", json={
            "item_index": item["index"], "action": "KEEP",
            "expected_status": "NEW", "expected_updated_at": item["image"]["updated_at"],
        })
        assert r.status_code == 200, r.text

    done = client.post(f"/api/v1/review/sessions/{a['id']}/complete").json()
    assert done["completed"] is True
    assert done["ended_reason"] == "COMPLETED"

    added = make_mobile_image(3)
    b = _create(client, mode="only_new", exclude_session_id=a["id"], close_active=True)
    assert b["status"] == "ACTIVE"
    assert b["total_count"] == 3
    b_ids = {
        item["image"]["image_id"]
        for item in client.get(f"/api/v1/review/sessions/{b['id']}/queue").json()["items"]
    }
    assert b_ids == {img.id for img in added}

    # 已完成的会话再 complete：不报错、不复活
    again = client.post(f"/api/v1/review/sessions/{a['id']}/complete").json()
    assert again["completed"] is True
    assert again["status"] == "COMPLETED"


def test_only_new_without_exclude_uses_latest_session(client, make_mobile_image):
    make_mobile_image(2)
    a = _create(client)
    make_mobile_image(1)
    # 不传 exclude_session_id → 排除最近会话（A）
    b = _create(client, mode="only_new")
    assert b["total_count"] == 1


def test_new_count_after_zero_new_batch(client, make_mobile_image):
    make_mobile_image(1)
    _create(client)
    b = _create(client, mode="only_new")  # 无新图 → 0 张 COMPLETED EMPTY
    assert b["status"] == "COMPLETED"
    assert b["total_count"] == 0
    # 空批次之外的待审图仍被如实计数（不把“当前会话成员”算进去，也不会漏掉旧图）
    assert client.get(f"/api/v1/review/sessions/{b['id']}/new-count").json()["count"] == 1

    make_mobile_image(1)
    assert client.get(f"/api/v1/review/sessions/{b['id']}/new-count").json()["count"] == 2
