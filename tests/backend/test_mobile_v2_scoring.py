from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import func, select

from app.models import PromptEvaluation
from app.services import prompt_service
from test_mobile_image_api import _auth
import json


def _prompt(session_factory):
    with session_factory() as session:
        prompt = prompt_service.create_prompt(session, name="disposable", mode="full", positive_prompt="snapshot")
        return prompt.id, prompt.current_version_id


def test_evaluation_receipt_and_version_summary(mobile_client, session_factory):
    prompt, version = _prompt(session_factory)
    headers = _auth(mobile_client, session_factory)
    body = {"prompt_version_id": version, "overall_score": 4, "dimensions": {"quality": 5}, "client_request_id": "score-1"}
    url = f"/mobile/prompts/{prompt}/evaluations"
    response = mobile_client.post(url, json=body, headers=headers)
    assert response.status_code == 200
    result = response.json()["data"]
    assert result["prompt_id"] == prompt and result["prompt_version_id"] == version
    assert mobile_client.post(url, json=body, headers=headers).json()["data"] == result
    receipt = mobile_client.get("/mobile/prompts/evaluations/score-1", headers=headers).json()["data"]
    assert receipt == {"found": True, "evaluation": result}
    conflict = mobile_client.post(url, json={**body, "overall_score": 2}, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    summary = mobile_client.get(f"/mobile/prompts/{prompt}/review-summary", params={"version_id": version}, headers=headers).json()["data"]
    assert summary["evaluation_count"] == 1
    assert summary["version_latest"]["overall_score"] == 4
    assert summary["images_total"] == 0
    # 整体评分与版本评分不能互相冒充。
    mobile_client.post(url, json={"overall_score": 2, "client_request_id": "overall"}, headers=headers)
    summary = mobile_client.get(f"/mobile/prompts/{prompt}/review-summary", params={"version_id": version}, headers=headers).json()["data"]
    assert summary["version_latest"]["overall_score"] == 4
    assert summary["prompt_latest"]["prompt_version_id"] is None


def test_concurrent_evaluation_writes_only_one_history(mobile_client, session_factory):
    prompt, version = _prompt(session_factory)
    headers = _auth(mobile_client, session_factory)
    body = {"prompt_version_id": version, "overall_score": 5, "client_request_id": "concurrent"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: mobile_client.post(f"/mobile/prompts/{prompt}/evaluations", json=body, headers=headers), range(2)))
    assert all(response.status_code == 200 for response in results)
    assert results[0].json()["data"] == results[1].json()["data"]
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PromptEvaluation)) == 1


def test_score_validation_and_cross_prompt_version_rejected(mobile_client, session_factory):
    prompt, _ = _prompt(session_factory)
    _, other_version = _prompt(session_factory)
    headers = _auth(mobile_client, session_factory)
    url = f"/mobile/prompts/{prompt}/evaluations"
    for extra in ({"overall_score": 0}, {"overall_score": True}, {"dimensions": {"quality": 6}}, {"dimensions": {"unknown": 3}}):
        response = mobile_client.post(url, json={"overall_score": 4, "client_request_id": "bad", **extra}, headers=headers)
        assert response.status_code in (400, 422)
    response = mobile_client.post(url, json={"overall_score": 4, "client_request_id": "wrong-version", "prompt_version_id": other_version}, headers=headers)
    assert response.status_code in (400, 404)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(PromptEvaluation)) == 0


def test_receipts_require_auth_and_are_device_scoped(mobile_client, session_factory):
    prompt, _ = _prompt(session_factory)
    headers = _auth(mobile_client, session_factory)
    assert mobile_client.get("/mobile/prompts/evaluations/private").status_code == 401
    mobile_client.post(f"/mobile/prompts/{prompt}/evaluations", json={"overall_score": 4, "client_request_id": "private"}, headers=headers)
    from app.services import mobile_pairing_service
    with session_factory() as session:
        code = mobile_pairing_service.generate_pairing_code(session)
    device = mobile_client.post("/mobile/pairing/verify", json={"installation_id": "other-device", "device_name": "test", "code": code}).json()["data"]
    result = mobile_client.get("/mobile/prompts/evaluations/private", headers={"Authorization": f"Bearer {device['token']}"})
    assert result.json()["data"] == {"found": False, "evaluation": None}


def test_linked_details_and_group_use_generated_version(mobile_client, session_factory, make_mobile_image):
    from app.models import Image, Job
    prompt, version = _prompt(session_factory)
    image = make_mobile_image(1)[0]
    with session_factory() as session:
        session.add(Job(id="job-mobile-test", source="web", status="COMPLETED", prompt_mode="full",
            positive_prompt_snapshot="historical generation", negative_prompt_snapshot="",
            workbench_snapshot_json=json.dumps({"source_prompt_id": prompt, "source_prompt_version_id": version}),
            generation_settings_json="{}", requested_count=1, completed_count=1))
        session.flush()
        session.get(Image, image.id).job_id = "job-mobile-test"
        session.commit()
    headers = _auth(mobile_client, session_factory)
    details = mobile_client.get(f"/mobile/images/{image.id}/details", headers=headers).json()["data"]
    assert details["positive_prompt"] == "historical generation"
    assert details["negative_prompt"] == ""
    assert details["link_state"] == "EXACT" and details["prompt_version_id"] == version
    group = mobile_client.get(f"/mobile/prompts/{prompt}/images", params={"version_id": version}, headers=headers).json()["data"]
    assert group["total"] == 1 and group["items"][0]["image_id"] == image.id
    summary = mobile_client.get(f"/mobile/prompts/{prompt}/review-summary", params={"version_id": version}, headers=headers).json()["data"]
    assert summary["images_total"] == 1 and summary["seen_count"] == 0
    decision = mobile_client.post(f"/mobile/review/images/{image.id}/decision", headers=headers,
        json={"favorite": True, "expected_updated_at": details["updated_at"], "client_request_id": "seen"})
    assert decision.status_code == 200
    summary = mobile_client.get(f"/mobile/prompts/{prompt}/review-summary", params={"version_id": version}, headers=headers).json()["data"]
    assert summary["seen_count"] == 1
