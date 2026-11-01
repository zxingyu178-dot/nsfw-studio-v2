"""W3.1 Mobile Bridge V2 数据库兼容迁移（0021 守卫 + 0022 结构归一）。

背景：项目历史上有两套同名 ``0021`` 迁移：
- main W3.0 ``0021_mobile_event_log_mutations``：事件表为
  ``(seq, event_id, event_type, image_id, revision, payload_json, created_at)``，
  另建 ``mobile_mutation_receipts``；
- 参考分支 ``0021_mobile_v2_events``：事件表只有 ``(seq, image_id, event)``，
  并额外创建 images 触发器、``mobile_write_receipts``、``mobile_image_seen``、
  ``mobile_feed_identity``。

本模块只做 SQLite 结构检查与数据搬运，不依赖 ORM：
- 0021 迁移改为 callable 守卫：遇到旧分支结构时不重复建表，留给 0022 归一；
- 0022 把旧分支事件/回执无损转换为主干结构，为历史图片补首同步事件，
  移除重复记录用的 images 触发器（唯一事件机制 = 业务服务显式写入）。
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import text
from sqlalchemy.engine import Connection

LEGACY_TRIGGERS = ("mobile_image_insert", "mobile_image_update", "mobile_image_delete")

MOBILE_EVENT_DDL = """
CREATE TABLE IF NOT EXISTS mobile_image_events (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id     TEXT    NOT NULL UNIQUE,
    event_type   TEXT    NOT NULL,
    image_id     TEXT,
    revision     TEXT,
    payload_json TEXT    NOT NULL DEFAULT '{}',
    created_at   TEXT    NOT NULL
)
"""

MOBILE_RECEIPT_DDL = """
CREATE TABLE IF NOT EXISTS mobile_mutation_receipts (
    id              TEXT PRIMARY KEY,
    device_id       TEXT NOT NULL,
    operation       TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload_hash    TEXT NOT NULL,
    response_json   TEXT NOT NULL,
    created_at      TEXT    NOT NULL,
    UNIQUE (device_id, operation, idempotency_key)
)
"""

MOBILE_SEEN_DDL = """
CREATE TABLE IF NOT EXISTS mobile_image_seen (
    device_id TEXT NOT NULL REFERENCES mobile_review_devices(id),
    image_id  TEXT NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    seen      INTEGER NOT NULL CHECK (seen IN (0, 1)),
    PRIMARY KEY (device_id, image_id)
)
"""


def _table_exists(conn: Connection, table: str) -> bool:
    return conn.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table},
    ).first() is not None


def _columns(conn: Connection, table: str) -> set[str]:
    rows = conn.execute(text(f"PRAGMA table_info({table})")).mappings().all()
    return {str(row["name"]) for row in rows}


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _main_event_schema(columns: set[str]) -> bool:
    return columns >= {
        "seq", "event_id", "event_type", "image_id", "revision", "payload_json", "created_at",
    }


def _ensure_event_indexes(conn: Connection) -> None:
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mobile_image_events_type ON mobile_image_events(event_type)"))
    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_mobile_image_events_image ON mobile_image_events(image_id)"))


def ensure_mobile_event_log_tables(conn: Connection) -> None:
    """0021 主干迁移：旧分支 0021 已存在时只补回执表，事件表交给 0022 转换。"""
    columns = _columns(conn, "mobile_image_events") if _table_exists(conn, "mobile_image_events") else set()
    if not columns:
        conn.execute(text(MOBILE_EVENT_DDL))
        _ensure_event_indexes(conn)
    elif _main_event_schema(columns):
        _ensure_event_indexes(conn)
    # 旧分支结构（seq/image_id/event）：不重复建表、不改写，0022 负责归一。

    conn.execute(text(MOBILE_RECEIPT_DDL))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_mobile_mutation_device ON mobile_mutation_receipts(device_id)"
    ))


def _upgrade_legacy_event_table(conn: Connection, now: str) -> None:
    """旧分支 (seq, image_id, event) → 主干列原位扩展，保留 seq 与原 event 审计列。"""
    conn.execute(text("ALTER TABLE mobile_image_events ADD COLUMN event_id TEXT"))
    conn.execute(text("ALTER TABLE mobile_image_events ADD COLUMN event_type TEXT"))
    conn.execute(text("ALTER TABLE mobile_image_events ADD COLUMN revision TEXT"))
    conn.execute(text("ALTER TABLE mobile_image_events ADD COLUMN payload_json TEXT NOT NULL DEFAULT '{}'"))
    conn.execute(text("ALTER TABLE mobile_image_events ADD COLUMN created_at TEXT NOT NULL DEFAULT ''"))
    conn.execute(text(
        "UPDATE mobile_image_events SET "
        "event_id = 'mevt_legacy_' || seq, "
        "event_type = CASE "
        "  WHEN event = 'REMOVE' THEN 'IMAGE_REMOVED' "
        "  WHEN EXISTS (SELECT 1 FROM mobile_image_events earlier "
        "               WHERE earlier.image_id = mobile_image_events.image_id "
        "                 AND earlier.seq < mobile_image_events.seq "
        "                 AND earlier.event = 'UPSERT') "
        "       THEN 'IMAGE_METADATA_UPDATED' "
        "  ELSE 'IMAGE_CREATED' END, "
        "revision = CAST(seq AS TEXT), "
        "payload_json = '{\"legacy_event\":\"' || event || '\"}', "
        "created_at = coalesce((SELECT updated_at FROM images WHERE images.id = mobile_image_events.image_id), "
        "                      :now)"
    ), {"now": now})
    conn.execute(text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_mobile_image_events_event_id "
        "ON mobile_image_events(event_id)"
    ))
    _ensure_event_indexes(conn)


def _backfill_historical_images(conn: Connection, now: str) -> int:
    """为没有任何事件的历史图片补首同步事件，保证空游标首次同步包含历史图。"""
    images = conn.execute(
        text(
            "SELECT i.id, i.width, i.height, i.status, i.favorite, i.kind, i.source, i.job_id, "
            "i.seed, i.created_at, i.updated_at FROM images i "
            "WHERE NOT EXISTS (SELECT 1 FROM mobile_image_events e WHERE e.image_id = i.id) "
            "ORDER BY i.created_at, i.id"
        )
    ).mappings().all()
    for image in images:
        event_type = "IMAGE_IMPORTED" if str(image["source"]) == "import" else "IMAGE_CREATED"
        payload = json.dumps({
            "image_id": image["id"],
            "width": image["width"],
            "height": image["height"],
            "status": image["status"],
            "is_favorite": bool(image["favorite"]),
            "kind": image["kind"],
            "source": image["source"],
            "job_id": image["job_id"],
            "seed": image["seed"],
            "created_at": image["created_at"],
            "updated_at": image["updated_at"],
        }, ensure_ascii=False)
        event_id = "mevt_bk_" + hashlib.sha1(str(image["id"]).encode()).hexdigest()
        conn.execute(
            text(
                "INSERT INTO mobile_image_events "
                "(event_id, event_type, image_id, revision, payload_json, created_at) "
                "VALUES (:event_id, :event_type, :image_id, NULL, :payload, :created_at)"
            ),
            {
                "event_id": event_id,
                "event_type": event_type,
                "image_id": image["id"],
                "payload": payload,
                "created_at": now,
            },
        )
        seq = conn.execute(
            text("SELECT seq FROM mobile_image_events WHERE event_id=:id"), {"id": event_id},
        ).scalar_one()
        conn.execute(
            text("UPDATE mobile_image_events SET revision=:rev WHERE seq=:seq"),
            {"rev": str(seq), "seq": seq},
        )
    return len(images)


def _merge_legacy_receipts(conn: Connection, now: str) -> int:
    """旧分支 mobile_write_receipts → 主干回执；保留原 request_id 与结果。"""
    if not _table_exists(conn, "mobile_write_receipts"):
        return 0
    conn.execute(text(MOBILE_RECEIPT_DDL))
    rows = conn.execute(
        text("SELECT device_id, request_id, operation, fingerprint, result_json FROM mobile_write_receipts")
    ).mappings().all()
    merged = 0
    for row in rows:
        raw_op = str(row["operation"])
        if raw_op.startswith("decision:"):
            operation = "image_decision"
        elif raw_op.startswith("evaluation:"):
            operation = "prompt_evaluation"
        else:
            operation = "legacy_mutation"
        exists = conn.execute(
            text(
                "SELECT 1 FROM mobile_mutation_receipts "
                "WHERE device_id=:device AND operation=:operation AND idempotency_key=:key"
            ),
            {"device": row["device_id"], "operation": operation, "key": row["request_id"]},
        ).first()
        if exists is not None:
            continue
        receipt_id = "mmr_legacy_" + hashlib.sha1(
            f"{row['device_id']}|{row['request_id']}|{operation}".encode()
        ).hexdigest()
        conn.execute(
            text(
                "INSERT INTO mobile_mutation_receipts "
                "(id, device_id, operation, idempotency_key, payload_hash, response_json, created_at) "
                "VALUES (:id, :device, :operation, :key, :hash, :response, :created_at)"
            ),
            {
                "id": receipt_id,
                "device": row["device_id"],
                "operation": operation,
                "key": row["request_id"],
                # 旧分支只保存指纹、没有原始载荷：用标记保留，查找时按旧算法复核。
                "hash": "legacy_fp:" + str(row["fingerprint"]),
                "response": str(row["result_json"]),
                "created_at": now,
            },
        )
        merged += 1
    return merged


def migrate_mobile_v2_compat(conn: Connection) -> None:
    """0022：结构归一 + 历史事件回填 + 旧回执合并；所有步骤幂等可重试。"""
    # 排序索引/临时表一律走内存：避免受限环境下 SQLite 临时文件打不开。
    conn.execute(text("PRAGMA temp_store=MEMORY"))
    now = _now()
    for trigger in LEGACY_TRIGGERS:
        conn.execute(text(f"DROP TRIGGER IF EXISTS {trigger}"))

    if _table_exists(conn, "mobile_image_events"):
        columns = _columns(conn, "mobile_image_events")
        if not _main_event_schema(columns):
            _upgrade_legacy_event_table(conn, now)
    else:
        conn.execute(text(MOBILE_EVENT_DDL))
        _ensure_event_indexes(conn)

    _backfill_historical_images(conn, now)
    conn.execute(text(MOBILE_SEEN_DDL))
    _merge_legacy_receipts(conn, now)
