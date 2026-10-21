"""V1 导入图片按 metadata 中的提示词归属参与提示词图片查询。"""
import json

from sqlalchemy import event

from app.core.ids import IMAGE, JOB, new_id
from app.models import Image, Job


def _prompt(client, name: str) -> dict:
    response = client.post(
        "/api/v1/prompts",
        json={"name": name, "mode": "full", "positive_prompt": name},
    )
    assert response.status_code == 201
    return response.json()


def _import_image(
    client,
    *,
    prompts: list[dict[str, str]] | None,
    created_at: str,
    image_id: str | None = None,
    include_v1_output: bool = True,
) -> str:
    image_id = image_id or new_id(IMAGE)
    metadata = {"v1_output": {"prompts": prompts}} if include_v1_output else {}
    with client.app.state.session_factory() as session:
        session.add(Image(
            id=image_id,
            file_path=f"images/imports/{image_id}.png",
            width=640,
            height=480,
            source="import",
            metadata_json=json.dumps(metadata),
            created_at=created_at,
        ))
        session.commit()
    return image_id


def _job_image(
    client,
    *,
    prompt_id: str,
    version_id: str,
    created_at: str,
    image_id: str,
) -> str:
    with client.app.state.session_factory() as session:
        job = Job(
            id=new_id(JOB),
            source="web",
            status="COMPLETED",
            prompt_mode="full",
            workbench_snapshot_json=json.dumps({
                "source_prompt_id": prompt_id,
                "source_prompt_version_id": version_id,
            }),
            generation_settings_json="{}",
            requested_count=1,
            module_id="basic_generate",
        )
        session.add(job)
        session.flush()
        session.add(Image(
            id=image_id,
            job_id=job.id,
            file_path=f"images/{image_id}.png",
            width=640,
            height=480,
            source="mock",
            created_at=created_at,
        ))
        session.commit()
    return image_id


def test_list_prompt_images_includes_import_and_filters_by_version(client):
    prompt = _prompt(client, "导入版本过滤")
    matched_version_id = prompt["current_version"]["id"]
    other_version = client.post(
        f"/api/v1/prompts/{prompt['id']}/versions",
        json={"mode": "full", "positive_prompt": "另一个版本"},
    ).json()
    image_id = _import_image(
        client,
        prompts=[{"prompt_id": prompt["id"], "version_id": matched_version_id}],
        created_at="2026-10-21T01:00:00Z",
    )
    url = f"/api/v1/prompts/{prompt['id']}/images"

    body = client.get(url).json()
    assert body["total"] == 1
    assert [item["id"] for item in body["items"]] == [image_id]
    assert body["items"][0]["job_status"] == "IMPORTED"
    assert body["items"][0]["module_id"] is None
    assert body["items"][0]["thumbnail_url"] == f"/api/v1/images/{image_id}/thumbnail"
    assert body["items"][0]["preview_url"] == f"/api/v1/images/{image_id}/preview"

    matched = client.get(url, params={"version_id": matched_version_id}).json()
    assert matched["total"] == 1
    assert [item["id"] for item in matched["items"]] == [image_id]
    unmatched = client.get(url, params={"version_id": other_version["id"]}).json()
    assert unmatched["total"] == 0
    assert unmatched["items"] == []


def test_list_prompt_images_merges_job_and_import_with_shared_order(client):
    prompt = _prompt(client, "统一排序")
    version_id = prompt["current_version"]["id"]
    job_image_id = _job_image(
        client,
        prompt_id=prompt["id"],
        version_id=version_id,
        created_at="2026-10-21T02:00:00Z",
        image_id="img_order_a",
    )
    imported_image_id = _import_image(
        client,
        prompts=[{"prompt_id": prompt["id"], "version_id": version_id}],
        created_at="2026-10-21T02:00:00Z",
        image_id="img_order_z",
    )

    body = client.get(f"/api/v1/prompts/{prompt['id']}/images").json()
    assert body["total"] == 2
    assert [item["id"] for item in body["items"]] == [imported_image_id, job_image_id]
    assert [item["job_status"] for item in body["items"]] == ["IMPORTED", "COMPLETED"]


def test_prompt_list_batch_images_groups_imports_in_one_query(client):
    first = _prompt(client, "批量甲")
    second = _prompt(client, "批量乙")
    first_image_id = _import_image(
        client,
        prompts=[{
            "prompt_id": first["id"],
            "version_id": first["current_version"]["id"],
        }],
        created_at="2026-10-21T01:00:00Z",
    )
    second_image_id = _import_image(
        client,
        prompts=[{
            "prompt_id": second["id"],
            "version_id": second["current_version"]["id"],
        }],
        created_at="2026-10-21T02:00:00Z",
    )
    engine = client.app.state.session_factory.kw["bind"]
    image_selects: list[str] = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT") and "images" in statement:
            image_selects.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get(
            "/api/v1/prompts",
            params={"include_images": True, "images_limit": 3, "limit": 50},
        )
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert response.status_code == 200
    assert len(image_selects) == 1
    items = {item["id"]: item for item in response.json()["items"]}
    assert items[first["id"]]["images_total"] == 1
    assert [image["id"] for image in items[first["id"]]["images"]] == [first_image_id]
    assert items[second["id"]]["images_total"] == 1
    assert [image["id"] for image in items[second["id"]]["images"]] == [second_image_id]


def test_import_without_prompt_metadata_is_not_attributed(client):
    prompt = _prompt(client, "空关联")
    _import_image(
        client,
        prompts=None,
        created_at="2026-10-21T01:00:00Z",
        include_v1_output=False,
    )
    _import_image(
        client,
        prompts=[],
        created_at="2026-10-21T02:00:00Z",
    )

    body = client.get(f"/api/v1/prompts/{prompt['id']}/images").json()
    assert body["total"] == 0
    assert body["items"] == []
