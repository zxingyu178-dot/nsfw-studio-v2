import time
import httpx

BASE = "http://127.0.0.1:8001"
c = httpx.Client(base_url=BASE, timeout=15, trust_env=False)

# 先暂停队列，避免取消期间继续起任务
c.post("/api/v1/queue/pause")
time.sleep(1)

for _ in range(120):
    q = c.get("/api/v1/queue").json()
    jobs = c.get("/api/v1/jobs").json()["items"]
    # 取消所有 QUEUED / PAUSED
    acted = False
    for j in jobs:
        if j["status"] in ("QUEUED", "PAUSED"):
            r = c.post(f"/api/v1/jobs/{j['id']}/cancel")
            print("cancel", j["id"], j["status"], r.status_code)
            acted = True
    running = q.get("running")
    if not running and not acted:
        break
    print("running:", running["id"] if running else None,
          "queued:", len(q.get("queued", [])), "paused:", len(q.get("paused", [])))
    time.sleep(2)

# 恢复队列
c.post("/api/v1/queue/resume")
q = c.get("/api/v1/queue").json()
print("FINAL running:", q.get("running"), "queued:", len(q["queued"]),
      "paused:", len(q["paused"]), "paused_flag:", q["worker"]["queue_paused"])
print("images:", c.get("/api/v1/images").json()["total"])
