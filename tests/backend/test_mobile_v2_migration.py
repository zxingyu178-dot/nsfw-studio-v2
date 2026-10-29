from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.database import migrations
from app.database.base import init_database, make_engine
from app.models import Image


def test_upgrade_backfills_images_and_retries_partial_ddl(tmp_path, monkeypatch):
    engine = make_engine(tmp_path / "upgrade.sqlite")
    all_migrations = migrations.MIGRATIONS
    with monkeypatch.context() as patch:
        patch.setattr(migrations, "MIGRATIONS", tuple(item for item in all_migrations if item.migration_id < "0021"))
        init_database(engine)
    with Session(engine) as session:
        session.add(Image(id="legacy", file_path="not-read.png", width=10, height=20, source="mock", status="KEEP"))
        session.commit()
    # SQLite某些DDL可先于事务保留；重试不应因已建identity表失败或更换游标身份。
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE mobile_feed_identity (id INTEGER PRIMARY KEY CHECK(id=1), epoch TEXT NOT NULL)"))
        connection.execute(text("INSERT INTO mobile_feed_identity VALUES (1, 'existing-epoch')"))
    assert [item.migration_id for item in init_database(engine)] == ["0021_mobile_v2_events"]
    assert init_database(engine) == []
    with Session(engine) as session:
        assert session.get(Image, "legacy").status == "KEEP"
        assert session.execute(text("SELECT image_id,event FROM mobile_image_events")).all() == [("legacy", "UPSERT")]
        assert session.execute(text("SELECT epoch FROM mobile_feed_identity")).scalar_one() == "existing-epoch"
    engine.dispose()
