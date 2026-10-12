import httpx

c = httpx.Client(trust_env=False, timeout=8)
q = c.get("http://127.0.0.1:8188/queue").json()
print("comfy running", len(q["queue_running"]), "pending", len(q["queue_pending"]))
for r in q["queue_running"]:
    print("  prompt", r[1][:8], "number", r[3].get("number"))
for r in q["queue_pending"]:
    print("  pending prompt", r[1][:8])

j = httpx.Client(base_url="http://127.0.0.1:8001", trust_env=False, timeout=8)
jobs = j.get("/api/v1/jobs").json()["items"]
cur = [x for x in jobs if x["status"] == "RUNNING"]
for job in cur:
    for it in job["items"]:
        eng = it["engine_job_id"][:8] if it["engine_job_id"] else None
        print("item", it["item_index"], it["status"], "eng", eng, "prog", it["progress"])

# 最近 history（看是否有刚完成/失败）
h = c.get("http://127.0.0.1:8188/history").json()
keys = sorted(h.keys())
print("history total", len(keys), "last3", [k[:8] for k in keys[-3:]])
