"""图库查询必须直接读最新图片，不能把事件回放当日期分页。"""
import pytest
from sqlalchemy import delete, func, select

from app.models import Image
from app.models.mobile_review import MobileImageEvent
from app.services import image_service
from test_mobile_v2_contract import auth


def gallery(client, headers, **params):
    response = client.get('/mobile/images/gallery', headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()['data']


@pytest.mark.parametrize('sort', ['created_desc', 'created_asc'])
def test_latest_keyset_does_not_pull_in_new_backdated_image(
    mobile_client, session_factory, make_mobile_image, sort,
):
    images = make_mobile_image(5)
    dates = {image.id: f'2026-11-09T0{index // 2 + 1}:00:00.000Z' for index, image in enumerate(images)}
    with session_factory() as session:
        for image in images:
            session.get(Image, image.id).created_at = dates[image.id]
        session.commit()
    headers, _ = auth(mobile_client, session_factory)
    first = gallery(mobile_client, headers, sort=sort, limit=2)
    expected = sorted(dates, key=lambda image_id: (dates[image_id], image_id), reverse=sort == 'created_desc')
    assert [row['image_id'] for row in first['items']] == expected[:2]
    assert first['has_more'] and first['total'] == 5
    assert first['sync_cursor']

    new_image = make_mobile_image(1)[0]
    new_date = '2026-11-09T01:30:00.000Z' if sort == 'created_desc' else '2026-11-09T02:30:00.000Z'
    with session_factory() as session:
        session.get(Image, new_image.id).created_at = new_date
        image_service.set_favorite(session, expected[-1], True)
        session.commit()
    collected = list(first['items'])
    page = first
    while page['has_more']:
        page = gallery(mobile_client, headers, sort=sort, limit=2, page_cursor=page['next_page_cursor'])
        collected.extend(page['items'])
    assert [row['image_id'] for row in collected] == expected
    assert collected[-1]['is_favorite'] is True
    restored = gallery(mobile_client, headers, sort=sort, anchor_id=expected[-2],
        scope_cursor=first['scope_cursor'], limit=100)
    assert [row['image_id'] for row in restored['items']] == expected[-2:]
    assert restored['sync_cursor'] == first['sync_cursor']
    refreshed = gallery(mobile_client, headers, sort='created_asc', limit=100)
    dates[new_image.id] = new_date
    assert [row['image_id'] for row in refreshed['items']] == sorted(dates, key=lambda image_id: (dates[image_id], image_id))


def test_local_day_boundaries_and_query_bound_cursor(
    mobile_client, session_factory, make_mobile_image,
):
    images = make_mobile_image(4)
    times = ['2026-11-08T15:59:59.999Z', '2026-11-08T16:00:00.000Z',
             '2026-11-09T15:59:59.999Z', '2026-11-09T16:00:00.000Z']
    with session_factory() as session:
        for image, timestamp in zip(images, times):
            session.get(Image, image.id).created_at = timestamp
        session.commit()
    headers, _ = auth(mobile_client, session_factory)
    params = {'sort': 'created_asc', 'from_utc': '2026-11-09T00:00:00+08:00',
              'before_utc': '2026-11-10T00:00:00+08:00', 'limit': 1}
    first = gallery(mobile_client, headers, **params)
    assert [row['image_id'] for row in first['items']] == [images[1].id]
    assert first['total'] == 2
    second = gallery(mobile_client, headers, **params, page_cursor=first['next_page_cursor'])
    assert [row['image_id'] for row in second['items']] == [images[2].id]
    assert mobile_client.get('/mobile/images/gallery', headers=headers, params={
        **params, 'page_cursor': first['scope_cursor'],
    }).status_code == 422
    for changed in ({'sort': 'created_desc'}, {'before_utc': '2026-11-11T00:00:00+08:00'}):
        response = mobile_client.get('/mobile/images/gallery', headers=headers,
            params={**params, **changed, 'page_cursor': first['next_page_cursor']})
        assert response.status_code == 422
    for invalid in ({'from_utc': '2026-11-09'}, {'sort': 'unknown'},
                    {'page_cursor': 'mr2_invalid'}, {'limit': 0}):
        assert mobile_client.get('/mobile/images/gallery', headers=headers, params=invalid).status_code == 422
    assert gallery(mobile_client, headers, from_utc='2027-01-01T00:00:00Z')['items'] == []


def test_legacy_without_events_is_visible_without_backfill_and_anchor_is_scoped(
    mobile_client, session_factory, make_mobile_image,
):
    images = make_mobile_image(2)
    with session_factory() as session:
        session.execute(delete(MobileImageEvent))
        for index, image in enumerate(images):
            session.get(Image, image.id).created_at = f'2026-11-0{index + 1}T00:00:00.000Z'
        session.commit()
    headers, _ = auth(mobile_client, session_factory)
    page = gallery(mobile_client, headers, anchor_id=images[0].id, limit=1)
    assert page['items'][0]['image_id'] == images[0].id
    assert page['items'][0]['revision'] == '0'
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(MobileImageEvent)) == 0
    assert mobile_client.get('/mobile/images/gallery', headers=headers, params={
        'anchor_id': images[0].id, 'from_utc': '2026-11-02T00:00:00Z',
    }).status_code == 404
    assert mobile_client.get('/mobile/images/gallery').status_code == 401


def test_first_page_and_watermark_share_a_real_read_snapshot(
    mobile_client, session_factory, make_mobile_image, monkeypatch,
):
    from app.services import image_event_service
    old = make_mobile_image(1)[0]
    headers, _ = auth(mobile_client, session_factory)
    original = image_event_service.newest_seq
    inserted = []

    def concurrent_change(session):
        watermark = original(session)
        if not inserted:
            inserted.extend(make_mobile_image(1))
            with session_factory() as writer:
                image_service.set_favorite(writer, old.id, True)
        return watermark

    monkeypatch.setattr(image_event_service, 'newest_seq', concurrent_change)
    page = gallery(mobile_client, headers)
    assert [row['image_id'] for row in page['items']] == [old.id]
    assert page['items'][0]['is_favorite'] is False
    changes = mobile_client.get('/mobile/images/feed', headers=headers,
        params={'cursor': page['sync_cursor']}).json()['data']['items']
    assert {row['image_id'] for row in changes} == {old.id, inserted[0].id}
    assert {row['event_type'] for row in changes} == {'IMAGE_CREATED', 'IMAGE_FAVORITE_UPDATED'}
