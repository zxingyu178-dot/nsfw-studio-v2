import time
import httpx

c = httpx.Client(base_url="http://127.0.0.1:8002", trust_env=False, timeout=30)
payload = {
    "job_kind": "generate", "prompt_mode": "structured",
    "structured_prompt": {"style": "a cute cat, best quality", "face": "", "clothing": "",
                          "pose": "", "scene": "", "composition": "", "lighting": "", "extra": ""},
    "generation_settings": {"width": 1024, "height": 1024, "seed_mode": "random"},
    "workflow_modules": [{"module_id": "basic_generate"}],
}
r = c.post("/api/v1/jobs", json=payload)
print("submit status", r.status_code)
jid = r.json().get("id") if r.status_code < 300 else None
print("jid", jid)
time.sleep(8)
if jid:
    for x in c.get("/api/v1/jobs").json()["items"]:
        if x["id"] == jid:
            print("job", x["status"], "err_type", x["error_type"],
                  "err_msg", (x["error_message"] or "")[:140])
print("health after:", c.get("/api/v1/health").json().get("status"))
print("running:", c.get("/api/v1/queue").json()["running"])
