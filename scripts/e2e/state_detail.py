import httpx

c = httpx.Client(base_url="http://127.0.0.1:8001", trust_env=False, timeout=10)
jobs = c.get("/api/v1/jobs").json()["items"]
q = c.get("/api/v1/queue").json()
print("running:", q["running"]["id"][:14] if q["running"] else None,
      "queued:", len(q["queued"]), "paused:", len(q["paused"]))
for j in jobs[:8]:
    print(j["id"][:14], j["status"], "req", j["requested_count"], "comp", j["completed_count"],
          "start", j["started_at"][11:19] if j["started_at"] else None,
          "fin", j["finished_at"][11:19] if j["finished_at"] else None,
          "pause_req", j["pause_requested"])
imgs = c.get("/api/v1/images").json()["items"]
print("images total", len(imgs))
for i in imgs[:8]:
    print("  img", i["id"][:10], i["width"], "x", i["height"], i["kind"], i["created_at"][11:19])
