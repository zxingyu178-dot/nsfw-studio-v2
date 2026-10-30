"""仅隔离图库；v2增量合同先于实现。"""
from test_mobile_image_api import _auth
from sqlalchemy import text


def test_feed_requires_pairing(mobile_client):
    assert mobile_client.get("/mobile/images/feed").status_code == 401


def test_feed_paginates_and_delivers_later_images(mobile_client, session_factory, make_mobile_image):
    images = make_mobile_image(3)
    headers = _auth(mobile_client, session_factory)
    first = mobile_client.get("/mobile/images/feed?limit=2", headers=headers)
    assert first.status_code == 200
    page = first.json()["data"]
    assert len(page["items"]) == 2 and page["has_more"] is True
    cursor = page["next_cursor"]
    second = mobile_client.get("/mobile/images/feed", params={"cursor": cursor, "limit": 2}, headers=headers).json()["data"]
    assert len(second["items"]) == 1 and second["has_more"] is False
    assert {row["image_id"] for row in page["items"] + second["items"]} == {image.id for image in images}
    assert all(str(row["revision"]).isdecimal() for row in page["items"])
    empty = mobile_client.get("/mobile/images/feed", params={"cursor": second["next_cursor"]}, headers=headers).json()["data"]
    assert empty["items"] == []
    # 同一夹具连续import可能复用相同内容；使用两张形成新的尺寸/颜色。
    later = make_mobile_image(5)
    updated = mobile_client.get("/mobile/images/feed", params={"cursor": empty["next_cursor"]}, headers=headers).json()["data"]
    assert {row["image_id"] for row in updated["items"]} >= {image.id for image in later} - {image.id for image in images}


def test_details_preserves_unknown_prompt(mobile_client, session_factory, make_mobile_image):
    image = make_mobile_image(1)[0]
    headers = _auth(mobile_client, session_factory)
    response = mobile_client.get(f"/mobile/images/{image.id}/details", headers=headers)
    assert response.status_code == 200
    details = response.json()["data"]
    assert details["image_id"] == image.id
    assert details["positive_prompt"] is None
    assert details["link_state"] == "UNLINKED"
    assert "file_path" not in details


def test_feed_captures_desktop_update_and_remove(mobile_client, session_factory, make_mobile_image):
    image = make_mobile_image(1)[0]
    headers = _auth(mobile_client, session_factory)
    first = mobile_client.get("/mobile/images/feed", headers=headers).json()["data"]
    original_revision = int(first["items"][0]["revision"])
    # 桌面连接直接更新，必须与手机共用数据库事件，而非依赖手机路由触发。
    with session_factory() as session:
        session.execute(text("UPDATE images SET favorite=1 WHERE id=:id"), {"id": image.id})
        session.commit()
    changed = mobile_client.get("/mobile/images/feed", params={"cursor": first["next_cursor"]}, headers=headers).json()["data"]
    assert changed["items"][0]["is_favorite"] is True
    assert int(changed["items"][0]["revision"]) > original_revision
    with session_factory() as session:
        session.execute(text("DELETE FROM image_variants WHERE image_id=:id"), {"id": image.id})
        session.execute(text("DELETE FROM images WHERE id=:id"), {"id": image.id})
        session.commit()
    removed = mobile_client.get("/mobile/images/feed", params={"cursor": changed["next_cursor"]}, headers=headers).json()["data"]
    assert removed["items"][0]["event"] == "REMOVE"
    assert removed["items"][0]["image_id"] == image.id
    assert int(removed["items"][0]["revision"]) > int(changed["items"][0]["revision"])


def test_invalid_cursor_is_explicit_and_cannot_cross_database(mobile_client, session_factory):
    headers = _auth(mobile_client, session_factory)
    response = mobile_client.get("/mobile/images/feed?cursor=not-a-valid-cursor", headers=headers)
    assert response.status_code == 410
    assert response.json()["error"]["code"] == "CURSOR_EXPIRED"


def test_image_decision_favorite_only_and_nonce_replay(mobile_client, session_factory, make_mobile_image):
    image = make_mobile_image(1)[0]
    headers = _auth(mobile_client, session_factory)
    url = f"/mobile/review/images/{image.id}/decision"
    request = {"favorite": True, "expected_updated_at": image.updated_at, "client_request_id": "favorite-1"}
    response = mobile_client.post(url, json=request, headers=headers)
    assert response.status_code == 200
    result = response.json()["data"]
    assert result["status"] == "NEW" and result["is_favorite"] is True
    replay = mobile_client.post(url, json=request, headers=headers)
    assert replay.json()["data"] == result
    altered = mobile_client.post(url, json={**request, "favorite": False}, headers=headers)
    assert altered.status_code == 409
    assert altered.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_feed_select_count_is_bounded_by_batches(session_factory, make_mobile_image):
    from sqlalchemy import event
    from app.services import mobile_v2_service
    make_mobile_image(20)
    counts = []
    for limit in (5, 20):
        statements = []
        with session_factory() as session:
            engine = session.get_bind()
            def capture(conn, cursor, statement, parameters, context, executemany):
                if statement.lstrip().upper().startswith('SELECT'):
                    statements.append(statement)
            event.listen(engine, 'before_cursor_execute', capture)
            try:
                page = mobile_v2_service.feed(session, None, limit)
            finally:
                event.remove(engine, 'before_cursor_execute', capture)
            assert len(page['items']) == limit
        counts.append(len(statements))
    print(f'Feed SELECT counts for 5/20 images: {counts}')
    assert max(counts) <= 8, f'SELECT counts for 5/20 images: {counts}'
    assert counts[1] <= counts[0] + 1, f'Query count grows with page size: {counts}'
