import time
import httpx

RAW = httpx.Client(base_url="http://127.0.0.1:8001", trust_env=False, timeout=20)


def call(fn, *a, **k):
    last = None
    for _ in range(6):
        try:
            return fn(*a, **k)
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            last = e
            time.sleep(1.5)
    raise last


def get(path):
    return call(RAW.get, path).json()


def post(path):
    return call(RAW.post, path)


def qstate():
    return get("/api/v1/queue")


def job_status(jid):
    for j in get("/api/v1/jobs")["items"]:
        if j["id"] == jid:
            return j
    return None


q = qstate()
run = q.get("running")
job_a = run["id"]
print("job A:", job_a[:14], "pause_req:", run["pause_requested"],
      "queue_paused:", q["worker"]["queue_paused"])

# 若暂停未生效则补一次（幂等）
if not q["worker"]["queue_paused"]:
    print("→ (re)pause")
    post("/api/v1/queue/pause")

# 等 item0 完成、A 在边界 PAUSED
t0 = time.time()
ok = False
while time.time() - t0 < 1200:
    q = qstate()
    ja = job_status(job_a)
    if q.get("running") is None and ja and ja["status"] == "PAUSED":
        ok = True
        break
    time.sleep(5)
q = qstate(); ja = job_status(job_a)
print(f"[{'PASS' if ok else 'FAIL'}] item0 完成后 A 边界 PAUSED "
      f"{ja['completed_count']}/{ja['requested_count']}  耗时{int(time.time()-t0)}s")
print(f"[{'PASS' if q['worker']['queue_paused'] else 'FAIL'}] worker queue_paused")
held = [j['id'][:12] for j in q['queued']]
print(f"[{'PASS' if not q.get('running') else 'FAIL'}] 无 RUNNING；B/C 排队 {held}")

# 继续 → A 最先
print("→ resume")
post("/api/v1/queue/resume")
t0 = time.time(); first = False
while time.time() - t0 < 60:
    q = qstate()
    if q.get("running") and q["running"]["id"] == job_a:
        first = True
        break
    time.sleep(2)
print(f"[{'PASS' if first else 'FAIL'}] 继续后原暂停 Job A 最先恢复")

# 节省时间：取消 A（中断 item1）与 B/C
time.sleep(2)
for j in get("/api/v1/jobs")["items"]:
    if j["status"] in ("QUEUED", "PAUSED", "RUNNING"):
        print("cancel", j["id"][:12], j["status"], call(RAW.post, f"/api/v1/jobs/{j['id']}/cancel").status_code)
time.sleep(3)
post("/api/v1/queue/resume")
q = qstate()
print("FINAL running:", q.get("running"), "queued:", len(q["queued"]),
      "paused:", len(q["paused"]), "flag:", q["worker"]["queue_paused"],
      "images:", get("/api/v1/images")["total"])
