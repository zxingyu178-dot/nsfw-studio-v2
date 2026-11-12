"""图库查询必须直接读最新图片，不能把事件回放当日期分页。"""
import base64
import json

import pytest
from sqlalchemy import delete, func, select

from app.models import Image
from app.models.mobile_review import MobileImageEvent
from app.services import image_service
from app.services.cleanup_service import _purge_image_rows
from test_mobile_v2_contract import auth


@pytest.mark.parametrize('endpoint', ['gallery', 'feed'])
def test_mobile_image_categories_match_existing_library_filters(
    mobile_client, session_factory, make_mobile_image, endpoint,
):
    from app.models import Job
    images = make_mobile_image(5)
    with session_factory() as session:
        session.add(Job(id='category_anime', source='web', prompt_mode='full',
            workbench_snapshot_json='{}', generation_settings_json='{}',
            requested_count=1, module_id='anime_generate'))
        session.flush()
        session.get(Image, images[1].id).job_id = 'category_anime'
        for index in (2, 3, 4):
            session.get(Image, images[index].id).source = 'import'
        session.get(Image, images[2].id).imported_filename = 'photo.png'
        session.get(Image, images[3].id).imported_filename = 'AnImA_output.png'
        session.get(Image, images[4].id).metadata_json = json.dumps({'origin': 'ANIMA-v1'})
        session.commit()
        expected = {image.id: [] for image in images}
        for category in ('anime', 'imported'):
            query = image_service._apply_image_filters(select(Image), category=category)
            for image in session.scalars(query):
                expected[image.id].append(category)
    assert list(expected.values()) == [[], ['anime'], ['imported'], ['anime', 'imported'], ['anime', 'imported']]
    headers, _ = auth(mobile_client, session_factory)
    response = mobile_client.get(f'/mobile/images/{endpoint}', headers=headers)
    assert response.status_code == 200
    rows = response.json()['data']['items']
    assert {row['image_id']: row['categories'] for row in rows} == expected


def test_gallery_filters_prompt_versions_and_new_status(mobile_client, session_factory, make_mobile_image):
    from app.services import prompt_service
    images = make_mobile_image(4)
    with session_factory() as session:
        prompt = prompt_service.create_prompt(session, name='filter prompt', mode='full', positive_prompt='one')
        first = prompt_service.get_current_version(session, prompt)
        second, _ = prompt_service.add_prompt_version(session, prompt.id, mode='full', positive_prompt='two')
        for index, image in enumerate(images):
            row = session.get(Image, image.id)
            row.source = 'import'
            row.metadata_json = json.dumps({'v1_output': {'prompts': [{
                'prompt_id': prompt.id, 'version_id': first.id if index < 3 else second.id,
            }]}})
        session.commit()
        prompt_id, first_id, second_id = prompt.id, first.id, second.id
    headers, _ = auth(mobile_client, session_factory)
    params = dict(prompt_id=prompt_id, version_id=first_id, status='NEW', sort='created_asc', limit=1)
    page = gallery(mobile_client, headers, **params)
    assert page['total'] == 3
    assert page['filters'] == {'prompt_id': prompt_id, 'version_id': first_id, 'status': 'NEW'}
    assert [row['image_id'] for row in page['items']] == [images[0].id]
    other = gallery(mobile_client, headers, prompt_id=prompt_id, version_id=second_id)
    assert [row['image_id'] for row in other['items']] == [images[3].id]
    with session_factory() as session:
        image_service.set_image_status(session, images[0].id, 'KEEP')
    following = gallery(mobile_client, headers, **params, page_cursor=page['next_page_cursor'])
    assert following['total'] == 2 and following['start_index'] == 0
    assert following['items'][0]['image_id'] == images[1].id
    for altered in ({'version_id': second_id}, {'status': 'KEEP'}, {'prompt_id': None}):
        query = {**params, **altered, 'page_cursor': page['next_page_cursor']}
        query = {key: value for key, value in query.items() if value is not None}
        assert mobile_client.get('/mobile/images/gallery', headers=headers, params=query).status_code == 422
    assert mobile_client.get('/mobile/images/gallery', headers=headers, params={'version_id': first_id}).status_code == 422
    assert mobile_client.get('/mobile/images/gallery', headers=headers, params={'prompt_id': 'missing'}).status_code == 404
    assert mobile_client.get('/mobile/images/gallery', headers=headers, params={'prompt_id': prompt_id, 'version_id': 'missing'}).status_code == 404


def test_gallery_filters_category_favorite_and_legacy_scope(mobile_client, session_factory, make_mobile_image):
    images = make_mobile_image(3)
    with session_factory() as session:
        for index, image in enumerate(images):
            row = session.get(Image, image.id)
            row.source = 'import' if index < 2 else 'comfyui'
            row.imported_filename = 'anima_test.png' if index == 0 else 'photo.png'
            row.favorite = index == 0
        session.commit()
    headers, _ = auth(mobile_client, session_factory)
    anime = gallery(mobile_client, headers, category='anime', favorite=True)
    assert [row['image_id'] for row in anime['items']] == [images[0].id]
    imported = gallery(mobile_client, headers, category='imported', favorite=False)
    assert imported['filters'] == {'category': 'imported', 'favorite': False}
    assert [row['image_id'] for row in imported['items']] == [images[1].id]
    for changed in ({'category': 'imported', 'favorite': True}, {'category': 'anime', 'favorite': False}):
        response = mobile_client.get('/mobile/images/gallery', headers=headers,
            params={**changed, 'scope_cursor': anime['scope_cursor']})
        assert response.status_code == 422
    plain = gallery(mobile_client, headers)
    encoded = plain['scope_cursor'].removeprefix('mg1_')
    decoded = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
    assert decoded['q'] == ['created_desc', None, None]
    assert plain['filters'] == {}
    assert gallery(mobile_client, headers, scope_cursor=plain['scope_cursor'])['scope_cursor'] == plain['scope_cursor']
    assert 'mobile_gallery_filters_v1' in mobile_client.get('/mobile/system/health').json()['data']['capabilities']


def gallery(client, headers, **params):
    response = client.get('/mobile/images/gallery', headers=headers, params=params)
    assert response.status_code == 200, response.text
    return response.json()['data']


@pytest.mark.parametrize('sort', ['created_desc', 'created_asc'])
def test_bidirectional_gallery_anchor_and_boundaries(
    mobile_client, session_factory, make_mobile_image, sort,
):
    images = make_mobile_image(9)
    with session_factory() as session:
        for image in images:
            session.get(Image, image.id).created_at = '2026-11-09T01:00:00.000Z'
        session.commit()
    expected = sorted((image.id for image in images), reverse=sort == 'created_desc')
    headers, _ = auth(mobile_client, session_factory)
    first = gallery(mobile_client, headers, sort=sort, limit=2)
    scope = first['scope_cursor']
    assert first['start_index'] == 0
    assert first['previous_page_cursor'] is None
    assert 'mobile_gallery_bidirectional_v1' in mobile_client.get('/mobile/system/health').json()['data']['capabilities']
    middle = gallery(mobile_client, headers, sort=sort, scope_cursor=scope,
                     anchor_id=expected[4], limit=2)
    assert middle['start_index'] == 4 and middle['total'] == 9
    assert [row['image_id'] for row in middle['items']] == expected[4:6]
    newer = make_mobile_image(1)[0]
    with session_factory() as session:
        session.get(Image, newer.id).created_at = '2026-11-09T01:00:00.000Z'
        session.commit()
    # 从中间向前取最近两张，再向后返回原窗口；同时间戳也不漏重。
    previous = gallery(mobile_client, headers, sort=sort, limit=2,
                       page_cursor=middle['previous_page_cursor'])
    assert previous['start_index'] == 2 and previous['total'] == 9
    assert previous['scope_cursor'] == scope
    assert [row['image_id'] for row in previous['items']] == expected[2:4]
    returned = gallery(mobile_client, headers, sort=sort, limit=2,
                       page_cursor=previous['next_page_cursor'])
    assert [row['image_id'] for row in returned['items']] == expected[4:6]
    head = gallery(mobile_client, headers, sort=sort, limit=2,
                   page_cursor=previous['previous_page_cursor'])
    assert [row['image_id'] for row in head['items']] == expected[:2]
    assert head['previous_page_cursor'] is None and head['start_index'] == 0
    collected = []
    page = head
    while True:
        assert page['scope_cursor'] == scope and page['total'] == 9
        assert page['start_index'] == len(collected)
        collected.extend(row['image_id'] for row in page['items'])
        if not page['has_more']:
            break
        page = gallery(mobile_client, headers, sort=sort, limit=2,
                       page_cursor=page['next_page_cursor'])
    assert collected == expected
    assert page['next_page_cursor'] is None


@pytest.mark.parametrize('sort', ['created_desc', 'created_asc'])
def test_bidirectional_gallery_deletion_and_empty_pages(
    mobile_client, session_factory, make_mobile_image, sort,
):
    images = make_mobile_image(5)
    expected = sorted(images, key=lambda image: (image.created_at, image.id), reverse=sort == 'created_desc')
    headers, _ = auth(mobile_client, session_factory)
    first = gallery(mobile_client, headers, sort=sort, limit=1)
    middle = gallery(mobile_client, headers, sort=sort, scope_cursor=first['scope_cursor'],
                     anchor_id=expected[2].id, limit=1)
    tail = gallery(mobile_client, headers, sort=sort, scope_cursor=first['scope_cursor'],
                   anchor_id=expected[-1].id, limit=1)
    with session_factory() as session:
        for image_id in (expected[0].id, expected[2].id):
            _purge_image_rows(session, image_id)
        session.commit()
    previous = gallery(mobile_client, headers, sort=sort, limit=2,
                       page_cursor=middle['previous_page_cursor'])
    assert [row['image_id'] for row in previous['items']] == [expected[1].id]
    assert previous['start_index'] == 0 and previous['total'] == 3
    assert previous['previous_page_cursor'] is None and previous['has_more']
    next_page = gallery(mobile_client, headers, sort=sort, limit=2,
                        page_cursor=middle['next_page_cursor'])
    assert [row['image_id'] for row in next_page['items']] == [image.id for image in expected[3:]]
    assert next_page['start_index'] == 1 and next_page['total'] == 3
    assert next_page['next_page_cursor'] is None
    assert mobile_client.get('/mobile/images/gallery', headers=headers, params={
        'sort': sort, 'scope_cursor': first['scope_cursor'], 'anchor_id': expected[2].id,
    }).status_code == 404
    with session_factory() as session:
        for image_id in list(session.scalars(select(Image.id))):
            _purge_image_rows(session, image_id)
        session.commit()
    for cursor in (middle['previous_page_cursor'], middle['next_page_cursor']):
        empty = gallery(mobile_client, headers, sort=sort, page_cursor=cursor)
        assert empty['items'] == [] and empty['start_index'] == 0 and empty['total'] == 0
        assert not empty['has_more'] and empty['next_page_cursor'] is None
        assert empty['previous_page_cursor'] is None
    assert tail['start_index'] == 4


def test_bidirectional_gallery_rejects_invalid_direction_and_scope(
    mobile_client, session_factory, make_mobile_image,
):
    make_mobile_image(3)
    headers, _ = auth(mobile_client, session_factory)
    page = gallery(mobile_client, headers, limit=1)
    payload = json.loads(base64.urlsafe_b64decode(page['next_page_cursor'][4:] + '==='))
    for direction in ('sideways', 'next', None, 1, []):
        encoded = base64.urlsafe_b64encode(json.dumps({**payload, 'direction': direction}).encode()).decode().rstrip('=')
        response = mobile_client.get('/mobile/images/gallery', headers=headers,
                                    params={'page_cursor': 'mg1_' + encoded})
        assert response.status_code == 422
    second = gallery(mobile_client, headers, page_cursor=page['next_page_cursor'], limit=1)
    backward = second['previous_page_cursor']
    for params in ({'scope_cursor': backward},
                   {'page_cursor': backward, 'sort': 'created_asc'},
                   {'page_cursor': backward, 'from_utc': '2026-01-01T00:00:00Z'},
                   {'page_cursor': backward, 'limit': 101}):
        assert mobile_client.get('/mobile/images/gallery', headers=headers, params=params).status_code == 422
    state = json.loads(base64.urlsafe_b64decode(backward[4:] + '==='))
    state['after'] = None
    forged_scope = 'mg1_' + base64.urlsafe_b64encode(json.dumps(state).encode()).decode().rstrip('=')
    assert mobile_client.get('/mobile/images/gallery', headers=headers,
                             params={'scope_cursor': forged_scope}).status_code == 422


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
    assert page['start_index'] == 0 and page['total'] == 1
    assert page['items'][0]['is_favorite'] is False
    changes = mobile_client.get('/mobile/images/feed', headers=headers,
        params={'cursor': page['sync_cursor']}).json()['data']['items']
    assert {row['image_id'] for row in changes} == {old.id, inserted[0].id}
    assert {row['event_type'] for row in changes} == {'IMAGE_CREATED', 'IMAGE_FAVORITE_UPDATED'}


def test_gallery_search_and_current_prompt_tag_scope(mobile_client, session_factory, make_mobile_image):
    from app.services import prompt_service
    images = make_mobile_image(3)
    with session_factory() as session:
        prompt = prompt_service.create_prompt(session, name='night collection', mode='full', positive_prompt='silver hair', tags=['old'])
        first = prompt_service.get_current_version(session, prompt)
        prompt_service.add_prompt_version(session, prompt.id, mode='full', positive_prompt='new scene', tags=[' curated '])
        row = session.get(Image, images[0].id)
        row.source = 'import'
        row.metadata_json = json.dumps({'v1_output': {'prompts': [{'prompt_id': prompt.id, 'version_id': first.id}]}})
        session.get(Image, images[1].id).imported_filename = '100%_sample.png'
        session.get(Image, images[2].id).imported_filename = '100XXsample.png'
        session.commit()
    headers, _ = auth(mobile_client, session_factory)
    for term in ('night', 'silver hair'):
        page = gallery(mobile_client, headers, search=term, tag='curated', limit=1)
        assert [item['image_id'] for item in page['items']] == [images[0].id]
        assert page['filters'] == {'search': term, 'tag': 'curated'}
        assert mobile_client.get('/mobile/images/gallery', headers=headers, params={'search': 'other', 'tag': 'curated', 'scope_cursor': page['scope_cursor']}).status_code == 422
    assert gallery(mobile_client, headers, tag='old')['items'] == []
    assert [item['image_id'] for item in gallery(mobile_client, headers, search='%_')['items']] == [images[1].id]
    plain = gallery(mobile_client, headers)
    blank = gallery(mobile_client, headers, search='  ', tag=' ', scope_cursor=plain['scope_cursor'])
    assert blank['scope_cursor'] == plain['scope_cursor'] and blank['filters'] == {}
    for params in ({'search': 's' * 201}, {'tag': 't' * 101}):
        assert mobile_client.get('/mobile/images/gallery', headers=headers, params=params).status_code == 422
    assert 'mobile_gallery_search_v1' in mobile_client.get('/mobile/system/health').json()['data']['capabilities']


def test_gallery_tag_ignores_malformed_historical_structured_json(mobile_client, session_factory, make_mobile_image):
    from app.services import prompt_service
    images = make_mobile_image(1)
    with session_factory() as session:
        prompt = prompt_service.create_prompt(session, name='legacy', mode='full', positive_prompt='legacy')
        version = prompt_service.get_current_version(session, prompt)
        version.structured_json = '{broken'
        image = session.get(Image, images[0].id)
        image.source = 'import'
        image.metadata_json = json.dumps({'v1_output': {'prompts': [{'prompt_id': prompt.id}]}})
        session.commit()
    headers, _ = auth(mobile_client, session_factory)
    assert gallery(mobile_client, headers, tag='curated')['items'] == []


def test_gallery_not_rejected_pagination_and_review_change(mobile_client, session_factory, make_mobile_image):
    images = make_mobile_image(6)
    with session_factory() as session:
        for image, status in zip(images, ['NEW', 'KEEP', 'ARCHIVED', 'REJECT', 'NEW', 'KEEP']):
            session.get(Image, image.id).status = status
        session.commit()
    headers, _ = auth(mobile_client, session_factory)
    params = {'status': 'NOT_REJECTED', 'sort': 'created_asc', 'limit': 2}
    first = gallery(mobile_client, headers, **params)
    assert first['total'] == 5
    assert first['filters'] == {'status': 'NOT_REJECTED'}
    assert [item['image_id'] for item in first['items']] == [images[0].id, images[1].id]
    second = gallery(mobile_client, headers, **params, page_cursor=first['next_page_cursor'])
    assert second['total'] == 5
    assert [item['image_id'] for item in second['items']] == [images[2].id, images[4].id]
    for status in ('NEW', 'KEEP', 'REJECT', None):
        for cursor_name, cursor in [('page_cursor', first['next_page_cursor']), ('scope_cursor', first['scope_cursor'])]:
            altered = {**params, cursor_name: cursor}
            if status is None:
                altered.pop('status')
            else:
                altered['status'] = status
            assert mobile_client.get('/mobile/images/gallery', headers=headers, params=altered).status_code == 422
    with session_factory() as session:
        image_service.set_image_status(session, images[2].id, 'REJECT')
    changed = gallery(mobile_client, headers, **params, page_cursor=first['next_page_cursor'])
    assert changed['total'] == 4
    assert [item['image_id'] for item in changed['items']] == [images[4].id, images[5].id]
    assert changed['next_page_cursor'] is None
    assert 'mobile_gallery_review_filter_v1' in mobile_client.get('/mobile/system/health').json()['data']['capabilities']


@pytest.mark.parametrize('status, count', [('NEW', 2), ('KEEP', 1), ('REJECT', 1)])
def test_gallery_existing_single_review_status(mobile_client, session_factory, make_mobile_image, status, count):
    images = make_mobile_image(4)
    with session_factory() as session:
        for image, value in zip(images, ['NEW', 'KEEP', 'REJECT', 'NEW']):
            session.get(Image, image.id).status = value
        session.commit()
    headers, _ = auth(mobile_client, session_factory)
    page = gallery(mobile_client, headers, status=status)
    assert page['total'] == count
    assert page['filters'] == {'status': status}
    assert {item['image_id'] for item in page['items']} == {
        image.id for image, value in zip(images, ['NEW', 'KEEP', 'REJECT', 'NEW']) if value == status
    }
