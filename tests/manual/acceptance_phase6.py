"""Phase 6 Task11 验收：真实应用（后端 8000 + 真实 DataRoot + 真实 ComfyUI）全链路。

严格对齐浏览器操作路径（同一套 API 与真实队列 Worker）：
    文生图 → 图片生成（选外部图）→ Img2Img（+ 高清）→ Gallery → History
    → 从 processed / upscaled 图恢复工作台（Task1 最近生成上下文 + 完整身份）
    → Recipe 保存重开 → 切回文生图

输出：docs/evidence/phase6-img2img/acceptance_task11.json（逐步骤证据）

用法（项目根目录；需后端已在 127.0.0.1:8000 运行）：
    .venv/Scripts/python tests/manual/acceptance_phase6.py [--run-generations]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8000/api/v1"
EVIDENCE = PROJECT_ROOT / "docs" / "evidence" / "phase6-img2img"
PHOTO = EVIDENCE / "inputs" / "real_photo_768x1024.png"

results: list[dict] = []


def record(step: str, ok: bool, detail: dict | None = None) -> None:
    results.append({"step": step, "ok": ok, "detail": detail or {}})
    print(f"[{'OK' if ok else 'FAIL'}] {step}")


def wait_job(client: httpx.Client, job_id: str, timeout: float = 3600.0) -> dict:
    deadline = time.monotonic() + timeout
    last: dict = {}
    while time.monotonic() < deadline:
        last = client.get(f"{BASE}/jobs/{job_id}").json()
        if last.get("status") in ("COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"):
            return last
        time.sleep(2.0)
    return last


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-generations", action="store_true",
                        help="真实执行文生图与 img2img+upscale（GPU 时间；不加则复用已完成证据）")
    args = parser.parse_args()

    client = httpx.Client(timeout=60.0, trust_env=False)
    health = client.get(f"{BASE}/health").json()
    record("Health", health.get("status") == "ok", health)

    modules = {item["module_id"]: item for item in client.get(f"{BASE}/modules").json()}
    record("Modules 可用性", all(modules[mid]["available"] for mid in ("basic_generate", "img2img", "upscale")), {
        mid: {"available": modules[mid]["available"], "module_version": modules[mid]["module_version"],
              "size_mode": modules[mid]["size_mode"]}
        for mid in ("basic_generate", "img2img", "upscale")
    })

    # ===== 1) 文生图（真实执行）=====
    text_snapshot = {
        "prompt_mode": "structured",
        "structured_prompt": {"style": "photorealistic", "scene": "quiet library interior",
                              "extra": "warm lamp light"},
        "full_prompt": "",
        "negative_prompt": "blurry, low quality, text, watermark",
        "selected_assets": {},
        "width": 768, "height": 768, "count": 1,
        "seed_mode": "random", "seed": None,
        "generation_mode": "text",
        "workflow_modules": [{"module_id": "basic_generate"}],
        "input_images": [],
    }
    created = client.post(f"{BASE}/jobs", json={"snapshot": text_snapshot})
    job_text = created.json() if created.status_code == 201 else {}
    record("文生图 Job 创建", created.status_code == 201, {
        "status": created.status_code, "job_id": job_text.get("id"),
        "generation_mode": job_text.get("workbench_snapshot", {}).get("generation_mode"),
        "modules": [m["module_id"] for m in job_text.get("workflow_snapshot", {}).get("modules", [])],
    })
    if args.run_generations and job_text:
        final_text = wait_job(client, job_text["id"])
        record("文生图 Job 完成", final_text.get("status") == "COMPLETED",
               {"status": final_text.get("status"), "error": final_text.get("error_message")})
        images = client.get(f"{BASE}/images", params={"job_id": job_text["id"]}).json()["items"]
        text_images = [img for img in images if img["kind"] == "original"]
        record("文生图 Gallery 产出", len(text_images) == 1,
               {"count": len(text_images), "seed": text_images[0]["seed"] if text_images else None})

    # ===== 2) 图片生成：外部导入图 → Img2Img（+ 高清）=====
    with PHOTO.open("rb") as handle:
        imported = client.post(f"{BASE}/images/import",
                               files=[("files", (PHOTO.name, handle, "image/png"))]).json()
    source = imported["imported"][0]["image"] if imported["imported_count"] else None
    if source is None and imported["duplicate_count"]:
        source = {"id": imported["duplicates"][0]["image_id"], "width": 768, "height": 1024}
    record("外部照片导入", source is not None, {"image_id": source and source["id"],
                                          "duplicates": imported["duplicate_count"]})

    image_snapshot = {
        **{k: text_snapshot[k] for k in (
            "prompt_mode", "full_prompt", "negative_prompt", "selected_assets", "count")},
        "structured_prompt": {"style": "photorealistic", "scene": "sunlit cafe by the window",
                              "extra": "warm afternoon light"},
        "width": 768, "height": 1024,
        "seed_mode": "random", "seed": None,
        "generation_mode": "image",
        "workflow_modules": [
            {"module_id": "img2img", "config": {"denoise": 0.55}},
            {"module_id": "upscale"},
        ],
        "input_images": [{"role": "source", "image_id": source["id"]}],
    }
    created_img = client.post(f"{BASE}/jobs", json={"snapshot": image_snapshot})
    job_img = created_img.json() if created_img.status_code == 201 else {}
    record("Img2Img(+高清) Job 创建", created_img.status_code == 201, {
        "status": created_img.status_code, "job_id": job_img.get("id"),
        "generation_mode": job_img.get("workbench_snapshot", {}).get("generation_mode"),
        "modules": [dict(module_id=m["module_id"], config=m.get("config"))
                    for m in job_img.get("workflow_snapshot", {}).get("modules", [])],
    })
    if args.run_generations and job_img:
        final_img = wait_job(client, job_img["id"])
        record("Img2Img(+高清) Job 完成", final_img.get("status") == "COMPLETED",
               {"status": final_img.get("status"), "error": final_img.get("error_message")})

    # ===== 3) Gallery / History =====
    gallery = client.get(f"{BASE}/images", params={"source": "import", "limit": 5}).json()
    record("Gallery 列表", gallery["total"] >= 1, {"total": gallery["total"]})
    history = client.get(f"{BASE}/history", params={"bucket": "all", "limit": 5}).json()
    roots = [entry["root"]["id"] for entry in history["items"]]
    record("History 归组", job_img.get("id") in roots or job_text.get("id") in roots,
           {"roots": roots[:3], "total": history["total"]})

    # ===== 4) 从 processed / upscaled 图恢复工作台（Task1）=====
    if job_img.get("id"):
        job_detail = client.get(f"{BASE}/jobs/{job_img['id']}").json()
        stages = job_detail.get("stages", [])
        processed_id = upscaled_id = None
        for stage in stages:
            for item in stage.get("items", []):
                if stage["module_id"] == "img2img":
                    processed_id = item.get("output_image_id")
                if stage["module_id"] == "upscale":
                    upscaled_id = item.get("output_image_id")
        for label, image_id, expect_module in (
            ("processed → 工作台", processed_id, "img2img"),
            ("upscaled → 工作台", upscaled_id, "img2img"),
        ):
            if not image_id:
                record(label, False, {"reason": "尚无该 Stage 输出（未真实执行）"})
                continue
            restored = client.get(f"{BASE}/images/{image_id}/workbench")
            body = restored.json() if restored.status_code == 200 else {}
            snapshot = body.get("snapshot", {})
            modules = snapshot.get("workflow_modules", [])
            record(label, restored.status_code == 200 and bool(modules)
                   and modules[0]["module_id"] == expect_module
                   and snapshot.get("generation_mode") == "image"
                   and snapshot.get("input_images", [{}])[0].get("image_id") == source["id"],
                   {"status": restored.status_code,
                    "primary": modules[0]["module_id"] if modules else None,
                    "generation_mode": snapshot.get("generation_mode"),
                    "denoise": modules[0].get("config", {}).get("denoise") if modules else None,
                    "binding_hash": modules[0].get("binding_hash") if modules else None,
                    "dynamic_seed": body.get("seed")})

    # ===== 5) Recipe 保存 / 重开（含生成模式与完整身份）=====
    if job_img.get("id"):
        job_detail = client.get(f"{BASE}/jobs/{job_img['id']}").json()
        recipe_snapshot = dict(job_detail.get("workbench_snapshot") or {})
        recipe_snapshot["workflow_modules"] = job_detail["workflow_snapshot"]["modules"]
        saved = client.post(f"{BASE}/recipes",
                            json={"name": "Phase6 验收配方", "snapshot": recipe_snapshot})
        recipe = saved.json() if saved.status_code == 201 else {}
        version = recipe.get("current_version", {})
        ok_recipe = (
            saved.status_code == 201
            and version.get("generation_settings", {}).get("generation_mode") == "image"
            and version.get("generation_settings", {}).get("seed_mode") == "random"
            and version.get("workflow_snapshot", {}).get("modules", [{}])[0].get("binding_hash")
                == job_detail["workflow_snapshot"]["modules"][0].get("binding_hash")
            and version.get("input_images", [{}])[0].get("image_id") == source["id"]
        )
        record("Recipe 保存（固定 Seed 归一化 + 身份 + 模式）", ok_recipe, {
            "status": saved.status_code,
            "generation_mode": version.get("generation_settings", {}).get("generation_mode"),
            "seed_mode": version.get("generation_settings", {}).get("seed_mode"),
            "modules": [dict(module_id=m["module_id"], config=m.get("config"),
                             binding_hash=m.get("binding_hash"))
                        for m in version.get("workflow_snapshot", {}).get("modules", [])],
        })
        if recipe.get("id"):
            reopened = client.get(f"{BASE}/recipes/{recipe['id']}").json()
            record("Recipe 重开一致", reopened["current_version"] == version)

    # ===== 6) 切回文生图（模式与 Primary Module 校正；创建后立即取消，不占用 GPU）=====
    text_again = client.post(f"{BASE}/jobs", json={"snapshot": {
        **text_snapshot, "width": 512, "height": 512, "seed_mode": "fixed", "seed": 1,
    }})
    body = text_again.json() if text_again.status_code == 201 else {}
    ok_text_again = (
        text_again.status_code == 201
        and body.get("workbench_snapshot", {}).get("generation_mode") == "text"
        and body.get("workflow_snapshot", {}).get("modules", [{}])[0].get("module_id") == "basic_generate"
    )
    if body.get("id"):
        client.post(f"{BASE}/jobs/{body['id']}/cancel")
    record("切回文生图（basic_generate + generation_mode=text）", ok_text_again,
           {"status": text_again.status_code, "job_id": body.get("id")})

    EVIDENCE.mkdir(parents=True, exist_ok=True)
    out = EVIDENCE / "acceptance_task11.json"
    out.write_text(json.dumps({"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                               "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    failed = [item["step"] for item in results if not item["ok"]]
    print(f"\n{'ALL PASS' if not failed else 'FAILED: ' + ', '.join(failed)}")
    print(f"[..] 证据: {out}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())