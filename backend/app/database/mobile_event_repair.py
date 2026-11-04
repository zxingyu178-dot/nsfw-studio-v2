"""W4.1 Migration 0023：``mobile_image_events`` 旧结构兼容修复。

背景：历史上存在两套 0021：
- 主干：``(seq, event_id, event_type, image_id, revision, payload_json, created_at)``
- 旧分支：``(seq, image_id, event)``，且 ``event TEXT NOT NULL``

0022 只做原位 ``ADD COLUMN``，会在旧库留下 legacy ``event NOT NULL`` 列；
新代码写 ``event_type`` 时会因 ``event`` 非空约束失败。本模块负责：

1. 识别旧结构（缺 event_id/event_type 或仍存在 event 列）；
2. 重建为唯一主干结构；
3. 保留全部历史事件与 ``seq`` 单调值；
4. 保留必要索引与唯一约束；
5. 已修复库安全跳过（幂等）；
6. 不删除任何事件行，不修改 0021/0022 文件。

不依赖 ORM，只用 SQLAlchemy Connection，便于迁移事务内执行。
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Connection

MAIN_COLUMNS = {
    "seq", "event_id", "event_type", "image_id", "revision", "payload_json", "created_at",
}
TEMP_TABLE = "mobile_image_events_w41_new"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _table_exists(conn: Connection) -> bool:
    return conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='mobile_image_events'")
    ).first() is not None


def _columns(conn: Connection, table: str = "mobile_image_events") -> set[str]:
    return {
        str(row["name"])
        for row in conn.execute(text(f"PRAGMA table_info({table})")).mappings().all()
    }


def _main_ddl(table: str) -> str:
    return f"""
    CREATE TABLE {table} (
        seq          INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id     TEXT    NOT NULL UNIQUE,
        event_type   TEXT    NOT NULL,
        image_id     TEXT,
        revision     TEXT,
        payload_json TEXT    NOT NULL DEFAULT '{{}}',
        created_at   TEXT    NOT NULL
    )
    """


def _ensure_indexes(conn: Connection) -> None:
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_mobile_image_events_type ON mobile_image_events(event_type)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_mobile_image_events_image ON mobile_image_events(image_id)"
    ))
    conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mobile_image_events_event_id ON mobile_image_events(event_id)"
    ))


def _legacy_event_type(conn: Connection, seq: int, image_id: str | None, event: str) -> str:
    raw = str(event or "").upper()
    if raw == "REMOVE":
        return "IMAGE_REMOVED"
    if raw == "UPSERT":
        earlier = conn.execute(
            text(
                "SELECT 1 FROM mobile_image_events earlier "
                "WHERE earlier.image_id = :image_id AND earlier.seq < :seq "
                "AND upper(earlier.event) = 'UPSERT'"
            ),
            {"image_id": image_id, "seq": seq},
        ).first()
        return "IMAGE_METADATA_UPDATED" if earlier is not None else "IMAGE_CREATED"
    return "IMAGE_METADATA_UPDATED"


def _rebuild(conn: Connection, columns: set[str]) -> int:
    """把旧结构重建为主干结构，返回保留的事件行数。"""
    now = _now()
    rows = conn.execute(text("SELECT * FROM mobile_image_events ORDER BY seq")).mappings().all()
    conn.execute(text(f"DROP TABLE IF EXISTS {TEMP_TABLE}"))
    conn.execute(text(_main_ddl(TEMP_TABLE)))

    inserted = 0
    for row in rows:
        seq = int(row["seq"]) if row.get("seq") is not None else None
        image_id = row.get("image_id") if "image_id" in columns else None
        event_id = row.get("event_id") if "event_id" in columns else None
        if not event_id:
            seed = f"{seq}|{image_id}|{row.get('event') or ''}"
            event_id = "mevt_w41_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()
        event_type = row.get("event_type") if "event_type" in columns else None
        if not event_type:
            event_type = _legacy_event_type(conn, seq or 0, image_id, str(row.get("event") or ""))
        revision = row.get("revision") if "revision" in columns else None
        if revision is None and seq is not None:
            revision = str(seq)
        payload = row.get("payload_json") if "payload_json" in columns else None
        if not payload:
            legacy = row.get("event")
            payload = (
                '{"legacy_event":"' + str(legacy).replace('"', '\\"') + '"}'
                if legacy else "{}"
            )
        created_at = row.get("created_at") if "created_at" in columns else None
        if not created_at:
            created_at = conn.execute(
                text("SELECT updated_at FROM images WHERE images.id = :id"), {"id": image_id}
            ).scalar() or now

        exists = conn.execute(
            text(f"SELECT 1 FROM {TEMP_TABLE} WHERE event_id = :event_id"), {"event_id": event_id}
        ).first()
        if exists is not None:
            event_id = event_id + "_" + str(seq)
        params = {
            "event_id": event_id, "event_type": event_type, "image_id": image_id,
            "revision": revision, "payload_json": payload, "created_at": created_at,
        }
        if seq is None:
            conn.execute(
                text(
                    f"INSERT INTO {TEMP_TABLE} (event_id, event_type, image_id, revision, payload_json, created_at) "
                    f"VALUES (:event_id, :event_type, :image_id, :revision, :payload_json, :created_at)"
                ), params,
            )
        else:
            conn.execute(
                text(
                    f"INSERT INTO {TEMP_TABLE} (seq, event_id, event_type, image_id, revision, payload_json, created_at) "
                    f"VALUES (:seq, :event_id, :event_type, :image_id, :revision, :payload_json, :created_at)"
                ), {**params, "seq": seq},
            )
        inserted += 1

    conn.execute(text("DROP TABLE mobile_image_events"))
    conn.execute(text(f"ALTER TABLE {TEMP_TABLE} RENAME TO mobile_image_events"))
    _ensure_indexes(conn)

    max_seq = conn.execute(text("SELECT max(seq) FROM mobile_image_events")).scalar()
    if max_seq is not None:
        # sqlite_sequence 没有 name 唯一约束，不能使用 ON CONFLICT；显式 UPDATE/INSERT。
        current = conn.execute(
            text("SELECT seq FROM sqlite_sequence WHERE name = 'mobile_image_events'")
        ).scalar()
        if current is None:
            conn.execute(
                text("INSERT INTO sqlite_sequence (name, seq) VALUES ('mobile_image_events', :seq)"),
                {"seq": int(max_seq)},
            )
        elif int(current) < int(max_seq):
            conn.execute(
                text("UPDATE sqlite_sequence SET seq = :seq WHERE name = 'mobile_image_events'"),
                {"seq": int(max_seq)},
            )
    return inserted


def ensure_mobile_events_w41(conn: Connection) -> None:
    """0023：识别旧结构并重建；已修复库安全跳过。"""
    conn.execute(text("PRAGMA temp_store=MEMORY"))
    if not _table_exists(conn):
        conn.execute(text(_main_ddl("mobile_image_events")))
        _ensure_indexes(conn)
        return
    columns = _columns(conn)
    needs_rebuild = ("event" in columns) or not (columns >= MAIN_COLUMNS)
    if not needs_rebuild:
        _ensure_indexes(conn)
        return

    before = conn.execute(text("SELECT count(*) FROM mobile_image_events")).scalar_one()
    kept = _rebuild(conn, columns)
    after = conn.execute(text("SELECT count(*) FROM mobile_image_events")).scalar_one()
    if before != after or kept != after:
        raise RuntimeError(
            f"0023 事件行数不一致：before={before} kept={kept} after={after}"
        )
    remaining = _columns(conn)
    if "event" in remaining or not (remaining >= MAIN_COLUMNS):
        raise RuntimeError(f"0023 重建后结构仍不符合主干标准: {sorted(remaining)}")
