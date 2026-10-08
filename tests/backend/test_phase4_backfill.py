"""Phase 4 Task 0：v0.3.x → v0.4.x/0.5.x Job 迁移真实升级测试。

覆盖合同 Task 0 的强制场景（禁止只测试"表存在"）：
- 真实 v0.3.2 数据库（0001~0006）含 COMPLETED / QUEUED / PAUSED / INTERRUPTED 四种 Job；
- 升级（0007 + 0008 + 0009）后每个 Job 都有 Stage / StageItem，历史状态与图片关系不丢失；
- QUEUED Job 升级后仍可被同一 Worker **真实执行**（Mock 引擎，离线可跑）；
- StageItem.seed 回填（仅 basic_generate Stage）；历史 Job 本身状态不被改变。
"""
from __future__ import annotations

import dataclasses
import json
import time

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core.config import Settings, WorkflowConfig
from app.database import migrations as migrations_module
from app.database.base import init_database, make_engine
from app.main import create_app

NOW = "2026-01-01T00:00:00.000Z"


def mock_settings(settings: Settings) -> Settings:
    merged = {"worker_poll_interval_ms": 20, "engine_poll_ms": 20}
    return dataclasses.replace(
        settings,
        workflow=WorkflowConfig(raw={"engine": {"provider": "mock", "options": merged}}),
    )


def wait_for(client, job_id, predicate, timeout=30.0):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = client.get(f"/api/v1/jobs/{job_id}").json()
        if predicate(last):
            return last
        time.sleep(0.05)
    raise AssertionError(f"等待任务状态超时: {json.dumps(last, ensure_ascii=False)[:500]}")


def _insert_legacy_job(conn, job_id: str, status: str, *, completed_count: int = 0,
                       requested_count: int = 1, module_id: str | None = "basic_generate",
                       workflow_hash: str | None = "legacyhash0000000") -> None:
    conn.execute(text(
        "INSERT INTO jobs (id, source, status, prompt_mode, positive_prompt_snapshot, "
        "negative_prompt_snapshot, structured_prompt_snapshot, workbench_snapshot_json, "
        "generation_settings_json, workflow_snapshot_json, module_id, module_version, provider, "
        "binding_version, workflow_hash, requested_count, completed_count, queue_position, "
        "priority, pause_requested, cancel_requested, created_at, updated_at) "
        "VALUES (:id, 'web', :status, 'structured', 'legacy prompt', '', '{}', "
        "'{\"seed_mode\": \"random\"}', '{\"width\": 512, \"height\": 768}', "
        "'{\"modules\": []}', :module_id, 'v1', 'comfyui', 'v1', :workflow_hash, "
        ":requested_count, :completed_count, 1, 0, 0, 0, :now, :now)"
    ), {
        "id": job_id, "status": status, "module_id": module_id,
        "workflow_hash": workflow_hash, "requested_count": requested_count,
        "completed_count": completed_count, "now": NOW,
    })


def _insert_legacy_item(conn, item_id: str, job_id: str, index: int, status: str, *,
                        image_id: str | None = None, seed: int | None = None,
                        engine_job_id: str | None = None) -> None:
    conn.execute(text(
        "INSERT INTO job_items (id, job_id, item_index, status, seed, engine_job_id, image_id, "
        "created_at, updated_at) "
        "VALUES (:id, :job_id, :index, :status, :seed, :engine_job_id, :image_id, :now, :now)"
    ), {
        "id": item_id, "job_id": job_id, "index": index, "status": status,
        "seed": seed, "engine_job_id": engine_job_id, "image_id": image_id, "now": NOW,
    })


def _insert_legacy_image(conn, image_id: str, job_id: str, *, seed: int | None = None) -> None:
    conn.execute(text(
        "INSERT INTO images (id, job_id, job_item_id, kind, file_path, width, height, seed, "
        "review_status, favorite, source, metadata_json, created_at, updated_at) "
        "VALUES (:id, :job_id, NULL, 'original', :path, 512, 768, :seed, 'UNREVIEWED', 0, "
        "'comfyui', '{}', :now, :now)"
    ), {
        "id": image_id, "job_id": job_id, "path": f"images/originals/{image_id}/original.png",
        "seed": seed, "now": NOW,
    })


def test_v032_database_backfill_and_queued_job_still_runs(settings, monkeypatch):
    """真实 v0.3.2 库 → 0007+0008+0009 → Stage 回填正确，且 QUEUED Job 仍可执行。"""
    engine = make_engine(settings.storage.database_path)
    original_migrations = migrations_module.MIGRATIONS

    # ===== 1) 构造 v0.3.2 状态（只应用 0001~0006，无 job_kind / 无 Stage 表）=====
    v032 = tuple(m for m in original_migrations if m.migration_id <= "0006_image")
    monkeypatch.setattr(migrations_module, "MIGRATIONS", v032)
    init_database(engine)

    with engine.begin() as conn:
        # COMPLETED Job：1 个已完成 item（带 image 与真实 seed）
        _insert_legacy_job(conn, "job_done", "COMPLETED", completed_count=1)
        _insert_legacy_item(conn, "item_done_1", "job_done", 0, "COMPLETED",
                            image_id="img_done_1", seed=4242, engine_job_id="comfy_done_1")
        _insert_legacy_image(conn, "img_done_1", "job_done", seed=4242)

        # QUEUED Job：升级后必须仍能真实执行
        _insert_legacy_job(conn, "job_queued", "QUEUED")
        _insert_legacy_item(conn, "item_q_1", "job_queued", 0, "QUEUED")

        # PAUSED Job：1 张已完成、1 张排队（Stage 视为已开始）
        _insert_legacy_job(conn, "job_paused", "PAUSED", completed_count=1, requested_count=2)
        _insert_legacy_item(conn, "item_p_1", "job_paused", 0, "COMPLETED",
                            image_id="img_p_1", seed=777)
        _insert_legacy_item(conn, "item_p_2", "job_paused", 1, "QUEUED")
        _insert_legacy_image(conn, "img_p_1", "job_paused", seed=777)

        # INTERRUPTED Job：中断现场（engine_job_id 保留，供恢复核对）
        _insert_legacy_job(conn, "job_interrupted", "INTERRUPTED")
        _insert_legacy_item(conn, "item_i_1", "job_interrupted", 0, "INTERRUPTED",
                            engine_job_id="comfy_old_1")

    # ===== 2) 升级：0007 + 0008 + 0009 =====
    monkeypatch.setattr(migrations_module, "MIGRATIONS", original_migrations)
    applied = init_database(engine)
    assert [m.migration_id for m in applied] == [
        "0007_pipeline_stage", "0008_pipeline_backfill", "0009_execution_fingerprint",
    ]

    # ===== 3) Stage / StageItem 回填正确 =====
    with engine.begin() as conn:
        # 每个旧 Job 都有且只有 1 个 Stage（stage 0，身份继承 Job 列）
        rows = conn.execute(text(
            "SELECT j.id, s.stage_index, s.module_id, s.module_version, s.provider, "
            "s.binding_version, s.workflow_hash, s.status, s.total_count, s.completed_count "
            "FROM jobs j JOIN job_stages s ON s.job_id = j.id ORDER BY j.id"
        )).fetchall()
        assert len(rows) == 4, "每个旧 Job 必须回填恰好 1 个 Stage"
        by_job = {row[0]: row for row in rows}
        for row in rows:
            assert row[1] == 0 and row[2] == "basic_generate" and row[3] == "v1"
            assert row[4] == "comfyui" and row[5] == "v1"
            assert row[6] == "legacyhash0000000", "Stage 身份必须优先继承 Job 列"

        assert by_job["job_done"][7] == "COMPLETED" and by_job["job_done"][8:10] == (1, 1)
        assert by_job["job_queued"][7] == "QUEUED" and by_job["job_queued"][8:10] == (1, 0)
        # PAUSED 且已开始过 → Stage RUNNING（与在线暂停语义一致）
        assert by_job["job_paused"][7] == "RUNNING" and by_job["job_paused"][8:10] == (2, 1)
        assert by_job["job_interrupted"][7] == "INTERRUPTED"

        # StageItem：每个 JobItem 恰有一条；状态/engine_job_id/output_image_id 正确映射
        items = conn.execute(text(
            "SELECT si.job_item_id, si.status, si.output_image_id, si.engine_job_id, si.seed, "
            "st.module_id FROM job_stage_items si "
            "JOIN job_stages st ON st.id = si.job_stage_id ORDER BY si.job_item_id"
        )).fetchall()
        assert len(items) == 5
        by_item = {row[0]: row for row in items}
        assert by_item["item_done_1"][1] == "COMPLETED"
        assert by_item["item_done_1"][2] == "img_done_1", "output_image_id = JobItem.image_id"
        assert by_item["item_q_1"][1] == "QUEUED" and by_item["item_q_1"][2] is None
        assert by_item["item_p_2"][1] == "QUEUED"
        assert by_item["item_i_1"][1] == "INTERRUPTED"
        assert by_item["item_i_1"][3] == "comfy_old_1", "engine_job_id 必须保留（恢复核对用）"
        # 0009：basic_generate StageItem.seed 从 JobItem 回填（Task3 历史修正）
        assert by_item["item_done_1"][4] == 4242
        assert by_item["item_p_1"][4] == 777
        assert by_item["item_q_1"][4] is None

        # 历史 Job 本身状态不被 0008 改变
        statuses = dict(conn.execute(text("SELECT id, status FROM jobs")).fetchall())
        assert statuses == {
            "job_done": "COMPLETED", "job_queued": "QUEUED",
            "job_paused": "PAUSED", "job_interrupted": "INTERRUPTED",
        }
        # 历史图片 seed 不被误清理（basic_generate Stage 的产出与 seed 无关清理）
        assert conn.execute(text("SELECT seed FROM images WHERE id = 'img_done_1'")).scalar_one() == 4242
    engine.dispose()

    # ===== 4) 升级后的应用启动：QUEUED Job 被同一 Worker 真实执行 =====
    app = create_app(mock_settings(settings))
    with TestClient(app) as client:
        final = wait_for(client, "job_queued", lambda j: j["status"] == "COMPLETED")
        assert final["completed_count"] == 1
        assert final["stages"][0]["status"] == "COMPLETED"
        assert final["stages"][0]["items"][0]["output_image_id"], "执行完必须有真实输出图片"
        images = client.get("/api/v1/images", params={"job_id": "job_queued"}).json()["items"]
        assert len(images) == 1 and images[0]["kind"] == "original"

        # 其他历史 Job 状态不被升级/启动过程破坏
        assert client.get("/api/v1/jobs/job_done").json()["status"] == "COMPLETED"
        assert client.get("/api/v1/jobs/job_paused").json()["status"] == "PAUSED"
        assert client.get("/api/v1/jobs/job_interrupted").json()["status"] == "INTERRUPTED"