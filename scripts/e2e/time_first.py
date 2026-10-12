import time
import httpx

c = httpx.Client(base_url="http://127.0.0.1:8001", timeout=15, trust_env=False)
t0 = time.time()
last_prog = None
while time.time() - t0 < 600:
    q = c.get("/api/v1/queue").json()
    imgs = c.get("/api/v1/images").json()["total"]
    run = q.get("running")
    prog = None
    if run:
        for it in run.get("items", []):
            if it["status"] == "RUNNING":
                prog = it.get("progress")
    elapsed = int(time.time() - t0)
    if prog != last_prog or imgs:
        print(f"t={elapsed}s images={imgs} running={run['id'][:12] if run else None} prog={prog}")
        last_prog = prog
    if imgs >= 1:
        print("FIRST IMAGE DONE at", elapsed, "s")
        break
    time.sleep(3)
