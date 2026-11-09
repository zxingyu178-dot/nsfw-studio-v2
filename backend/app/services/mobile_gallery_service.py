"""只读日期图库：稳定分页与增量水位分开，不回放或补写全库事件。"""
from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone
import json
from typing import Any

from sqlalchemy import false, func, select, tuple_
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.models import Image
from app.models.mobile_review import MobileImageEvent
from app.services import image_event_service, image_service, mobile_v2_service

_PREFIX = 'mg1_'
_CREATION_EVENTS = (image_event_service.EVENT_IMAGE_CREATED, image_event_service.EVENT_IMAGE_IMPORTED)


class GalleryQueryInvalid(ValidationError):
    status_code = 422


def _invalid(message: str = '图库查询或游标无效，请重新选择范围') -> ValidationError:
    return GalleryQueryInvalid(message, code='GALLERY_QUERY_INVALID')


def _utc(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        instant = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if instant.tzinfo is None or instant.microsecond % 1000:
            raise ValueError()
        return instant.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise _invalid('日期必须包含时区，精度不能小于毫秒') from None


def _key(value: Any) -> tuple[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2:
        raise _invalid()
    timestamp, image_id = value
    if not isinstance(timestamp, str) or _utc(timestamp) != timestamp:
        raise _invalid()
    if not isinstance(image_id, str) or not 1 <= len(image_id) <= 64:
        raise _invalid()
    return timestamp, image_id


def _encode(payload: dict) -> str:
    raw = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    return _PREFIX + base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


def _decode(cursor: str, query: list, session: Session) -> dict:
    try:
        if len(cursor) > 4096 or not cursor.startswith(_PREFIX):
            raise ValueError()
        encoded = cursor[len(_PREFIX):]
        raw = base64.b64decode(encoded + '=' * (-len(encoded) % 4), altchars=b'-_', validate=True)
        value = json.loads(raw)
        if not isinstance(value, dict) or type(value.get('v')) is not int or value['v'] != 1 or value.get('q') != query:
            raise ValueError()
        if type(value.get('wm')) is not int or value['wm'] < 0:
            raise ValueError()
        _key(value['upper'])
        _key(value['after'])
    except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error):
        raise _invalid() from None
    # 同步日志恢复/裁剪后沿用既有410语义，不把旧水位当作新快照。
    image_event_service.resolve_cursor(session, image_event_service.encode_cursor(value['wm']))
    return value


def _read_snapshot(session: Session) -> None:
    connection = session.connection()
    if connection.dialect.name == 'sqlite' and not connection.connection.driver_connection.in_transaction:
        # sqlite3旧事务模式下SELECT不会真正BEGIN，单有Session不足以锁定读视图。
        connection.exec_driver_sql('BEGIN')


def gallery(
    session: Session, *, sort: str = 'created_desc', from_utc: str | None = None,
    before_utc: str | None = None, page_cursor: str | None = None,
    scope_cursor: str | None = None, anchor_id: str | None = None, limit: int = 50,
) -> dict:
    if sort not in ('created_desc', 'created_asc') or not 1 <= limit <= 100:
        raise _invalid()
    start, end = _utc(from_utc), _utc(before_utc)
    if start is not None and end is not None and start >= end:
        raise _invalid('开始日期必须早于结束日期')
    if page_cursor and (scope_cursor or anchor_id):
        raise _invalid()
    query = [sort, start, end]
    _read_snapshot(session)
    cursor = page_cursor or scope_cursor
    if cursor:
        state = _decode(cursor, query, session)
        if (scope_cursor and state['after'] is not None) or (page_cursor and state['after'] is None):
            raise _invalid()
    else:
        state = {'v': 1, 'q': query, 'wm': image_event_service.newest_seq(session),
                 'upper': None, 'after': None}

    # 正式新图/导入图按同事务creation事件排除。旧图无事件仍显示，不在读取时补写。
    created_later = select(MobileImageEvent.seq).where(
        MobileImageEvent.image_id == Image.id,
        MobileImageEvent.event_type.in_(_CREATION_EVENTS),
        MobileImageEvent.seq > state['wm'],
    ).exists()
    statement = select(Image).where(~created_later)
    if start is not None:
        statement = statement.where(Image.created_at >= start)
    if end is not None:
        statement = statement.where(Image.created_at < end)
    key = tuple_(Image.created_at, Image.id)
    if not cursor:
        newest = session.execute(statement.with_only_columns(Image.created_at, Image.id)
            .order_by(Image.created_at.desc(), Image.id.desc()).limit(1)).first()
        state['upper'] = list(newest) if newest else None
    upper = _key(state['upper'])
    statement = statement.where(key <= upper) if upper else statement.where(false())
    total = int(session.scalar(select(func.count()).select_from(statement.subquery())) or 0)
    if anchor_id is not None:
        anchor = session.scalar(statement.where(Image.id == anchor_id))
        if anchor is None:
            raise NotFoundError('图片不在当前日期范围，请返回图库', code='GALLERY_ANCHOR_NOT_FOUND')
        anchor_key = (anchor.created_at, anchor.id)
        statement = statement.where(key <= anchor_key if sort == 'created_desc' else key >= anchor_key)
    after = _key(state['after'])
    if after is not None:
        statement = statement.where(key < after if sort == 'created_desc' else key > after)
    rows = list(session.scalars(statement.order_by(*image_service._image_order_by(sort)).limit(limit + 1)))
    has_more = len(rows) > limit
    rows = rows[:limit]
    revisions = image_event_service.latest_event_seqs(session, [row.id for row in rows])
    scope = {**state, 'after': None}
    next_page = None
    if has_more:
        next_page = _encode({**scope, 'after': [rows[-1].created_at, rows[-1].id]})
    return {
        'items': [mobile_v2_service.image_summary(session, row, revision=revisions.get(row.id, 0)) for row in rows],
        'next_page_cursor': next_page, 'has_more': has_more, 'total': total,
        'sync_cursor': image_event_service.encode_cursor(state['wm']), 'scope_cursor': _encode(scope),
        'sort': sort, 'range': {'from_utc': start, 'before_utc': end},
    }
