"""W3.1 两套历史 0021 数据库的兼容升级（SQLite 隔离，不触碰真实 DataRoot）。"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import migrations as migrations_module
from app.database.base import init_database, make_engine

BRANCH_0021_SQL = (
    "CREATE TABLE IF NOT EXISTS mobile_feed_identity (id INTEGER PRIMARY KEY CHECK(id=1), epoch TEXT NOT NULL)",
    "INSERT OR IGNORE INTO mobile_feed_identity VALUES (1, lower(hex(randomblob(32))))",
    "CREATE TABLE IF NOT EXISTS mobile_image_events (seq INTEGER PRIMARY KEY AUTOINCREMENT, image_id TEXT NOT NULL, event TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_mobile_events_image ON mobile_image_events(image_id, seq)",
    "CREATE TRIGGER IF NOT EXISTS mobile_image_insert AFTER INSERT ON images BEGIN INSERT INTO mobile_image_events(image_id,event) VALUES (NEW.id,'UPSERT'); END",
    "CREATE TRIGGER IF NOT EXISTS mobile_image_update AFTER UPDATE ON images BEGIN INSERT INTO mobile_image_events(image_id,event) VALUES (NEW.id,'UPSERT'); END",
    "CREATE TRIGGER IF NOT EXISTS mobile_image_delete AFTER DELETE ON images BEGIN INSERT INTO mobile_image_events(image_id,event) VALUES (OLD.id,'REMOVE'); END",
    "CREATE TABLE IF NOT EXISTS mobile_write_receipts (device_id TEXT NOT NULL REFERENCES mobile_review_devices(id), request_id TEXT NOT NULL, operation TEXT NOT NULL, fingerprint TEXT NOT NULL, result_json TEXT NOT NULL, PRIMARY KEY(device_id,request_id))",
    "CREATE TABLE IF NOT EXISTS mobile_image_seen (device_id TEXT NOT NULL REFERENCES mobile_review_devices(id), image_id TEXT NOT NULL REFERENCES images(id) ON DELETE CASCADE, seen INTEGER NOT NULL, PRIMARY KEY(device_id,image_id))",
)


def _insert_image(conn, image_id: str, source: str = "comfyui") -> None:
    conn.execute(text(
        "INSERT INTO images (id, kind, file_path, width, height, review_status, favorite, source, "
        "status, review_note, metadata_json, created_at, updated_at) "
        "VALUES (:id, 'original', :path, 10, 10, 'UNREVIEWED', 0, :source, 'NEW', '', '{}', "
        "'2026-01-01T00:00:00.000Z', '2026-01-01T00:00:00.000Z')"
    ), {"id": image_id, "path": f"images/originals/{image_id}/original.png", "source": source})


def _insert_device(conn, device_id: str) -> None:
    conn.execute(text(
        "INSERT INTO mobile_review_devices (id, installation_id, name, token_hash, paired_at, revoked) "
        "VALUES (:id, :install, 'pytest', :hash, '2026-01-01T00:00:00.000Z', 0)"
    ), {"id": device_id, "install": device_id, "hash": hashlib.sha256(device_id.encode()).hexdigest()})


def test_branch_0021_database_upgrades_without_data_loss(tmp_path, monkeypatch):
    engine = make_engine(tmp_path / "branch.sqlite")
    all_migrations = migrations_module.MIGRATIONS
    with monkeypatch.context() as patch:
        patch.setattr(migrations_module, "MIGRATIONS", tuple(
            item for item in all_migrations if item.migration_id <= "0020_review_session_end_reason"
        ))
        init_database(engine)

    with engine.begin() as conn:
        _insert_image(conn, "img_legacy")
        _insert_device(conn, "mdev_legacy")
        for statement in BRANCH_0021_SQL:
            conn.execute(text(statement))
        conn.execute(text("UPDATE images SET favorite=1 WHERE id='img_legacy'"))
        conn.execute(text("UPDATE images SET status='KEEP' WHERE id='img_legacy'"))
        conn.execute(text(
            "INSERT INTO mobile_write_receipts(device_id,request_id,operation,fingerprint,result_json) "
            "VALUES ('mdev_legacy','req-1','decision:img_legacy',:fp,:result)"
        ), {
            "fp": hashlib.sha256(json.dumps({"favorite": True}).encode()).hexdigest(),
            "result": json.dumps({"image_id": "img_legacy", "status": "NEW", "is_favorite": True,
                                  "updated_at": "2026-01-01T00:00:00.000Z", "revision": "2"}),
        })
        conn.execute(text(
            "INSERT INTO mobile_image_seen(device_id,image_id,seen) VALUES ('mdev_legacy','img_legacy',1)"
        ))
        conn.execute(text(
            "INSERT INTO migration (migration_id,version,time,status) "
            "VALUES ('0021_mobile_v2_events','0.38.0','t','applied')"
        ))

    applied = init_database(engine)
    assert [item.migration_id for item in applied] == [
        "0021_mobile_event_log_mutations", "0022_mobile_v2_compat",
    ]
    with engine.begin() as conn:
        triggers = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name='images'"
        )).all()
        assert triggers == [], "重复记录用的 images 触发器必须移除"
        events = conn.execute(text(
            "SELECT count(*), max(seq), count(event_id), count(revision) FROM mobile_image_events"
        )).one()
        assert events[0] >= 2 and events[1] >= 2
        assert events[2] == events[0] and events[3] == events[0]
        assert conn.execute(text("SELECT count(*) FROM mobile_write_receipts")).scalar_one() == 1
        receipt = conn.execute(text(
            "SELECT operation,idempotency_key,payload_hash FROM mobile_mutation_receipts"
        )).one()
        assert receipt[0] == "image_decision" and receipt[1] == "req-1"
        assert receipt[2].startswith("legacy_fp:")
        assert conn.execute(text("SELECT seen FROM mobile_image_seen")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM images")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM mobile_review_devices")).scalar_one() == 1

    assert init_database(engine) == []
    engine.dispose()


def test_main_0021_database_backfills_historical_images(tmp_path, monkeypatch):
    engine = make_engine(tmp_path / "main.sqlite")
    all_migrations = migrations_module.MIGRATIONS
    with monkeypatch.context() as patch:
        patch.setattr(migrations_module, "MIGRATIONS", tuple(
            item for item in all_migrations if item.migration_id <= "0021_mobile_event_log_mutations"
        ))
        init_database(engine)

    with engine.begin() as conn:
        _insert_image(conn, "img_old_1", source="comfyui")
        _insert_image(conn, "img_old_2", source="import")
        assert conn.execute(text("SELECT count(*) FROM mobile_image_events")).scalar_one() == 0

    applied = init_database(engine)
    assert [item.migration_id for item in applied] == ["0022_mobile_v2_compat"]
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT image_id,event_type,revision FROM mobile_image_events ORDER BY seq"
        )).all()
        assert [row[0] for row in rows] == ["img_old_1", "img_old_2"]
        assert rows[0][1] == "IMAGE_CREATED" and rows[1][1] == "IMAGE_IMPORTED"
        assert all(row[2] is not None and str(row[2]).isdecimal() for row in rows)
        assert conn.execute(text("SELECT count(*) FROM mobile_image_seen")).scalar_one() == 0
    assert init_database(engine) == []
    engine.dispose()


def test_legacy_receipt_replay_uses_old_fingerprint(tmp_path):
    import pytest

    from app.core.errors import ConflictError
    from app.services import mobile_mutation_service

    engine = make_engine(tmp_path / "receipt.sqlite")
    init_database(engine)
    with Session(engine) as session:
        _insert_device(session, "mdev_legacy")
        session.commit()
    payload = {"prompt_version_id": "prmv_1", "overall_score": 4, "dimensions": {"style": 4}, "notes": ""}
    legacy_payload = dict(payload)
    fingerprint = hashlib.sha256(
        json.dumps(legacy_payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    with Session(engine) as session:
        session.execute(text(
            "INSERT INTO mobile_mutation_receipts "
            "(id,device_id,operation,idempotency_key,payload_hash,response_json,created_at) "
            "VALUES ('mmr_legacy','mdev_legacy','prompt_evaluation','old-req',:hash,:response,'t')"
        ), {"hash": "legacy_fp:" + fingerprint,
            "response": json.dumps({"evaluation_id": "prev_old", "overall_score": 4})})
        session.commit()
        replay = mobile_mutation_service.find_receipt(
            session, device_id="mdev_legacy", operation="prompt_evaluation",
            idempotency_key="old-req",
            payload={"prompt_id": "prm_1", **payload}, legacy_payload=legacy_payload,
        )
        assert replay == {"evaluation_id": "prev_old", "overall_score": 4}
        with pytest.raises(ConflictError) as error:
            mobile_mutation_service.find_receipt(
                session, device_id="mdev_legacy", operation="prompt_evaluation",
                idempotency_key="old-req",
                payload={"prompt_id": "prm_1", **payload},
                legacy_payload={**legacy_payload, "overall_score": 3},
            )
        assert error.value.code == "IDEMPOTENCY_CONFLICT"
    engine.dispose()
