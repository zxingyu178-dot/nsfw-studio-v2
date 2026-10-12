import time
import httpx

c = httpx.Client(base_url="http://127.0.0.1:8001", trust_env=False, timeout=15)


def qstate():
    return c.get("/api/v1/queue").json()


def job_status(jid):
    for j in c.get("/api/v1/jobs").json()["items"]:
        if j["id"] == jid:
            return j
    return None


# 1) 找到当前 RUNNING 的 count2 Job（job A）
q = qstate()
run = q.get("running")
assert run, "当前无 RUNNING job"
job_a = run["id"]
print("job A:", job_a[:14], "requested", run["requested_count"])

# 2) 暂停队列（item0 会跑完，然后 A 在边界 PAUSED）
print("→ pause")
c.post("/api/v1/queue/pause")
t0 = time.time()
paused_ok = False
while time.time() - t0 < 1200:
    q = qstate()
    ja = job_status(job_a)
    if q.get("running") is None and ja and ja["status"] == "PAUSED":
        paused_ok = True
        break
    time.sleep(5)
q = qstate()
ja = job_status(job_a)
print(f"[{'PASS' if paused_ok else 'FAIL'}] item0 完成后 A 安全边界 PAUSED，comp="
      f"{ja['completed_count']}/{ja['requested_count']}  耗时 {int(time.time()-t0)}s")
print(f"[{'PASS' if q['worker']['queue_paused'] else 'FAIL'}] worker queue_paused")
held = [x[:12] for x in (q.get("queued", []) and [j["id"] for j in q["queued"]])]
print(f"[{'PASS' if not q.get('running') else 'FAIL'}] 暂停后无 RUNNING；B/C 仍排队 {held}")

# 3) 继续 → A 必须最先恢复
print("→ resume")
c.post("/api/v1/queue/resume")
t0 = time.time()
a_first = False
while time.time() - t0 < 60:
    q = qstate()
    if q.get("running") and q["running"]["id"] == job_a:
        a_first = True
        break
    time.sleep(2)
print(f"[{'PASS' if a_first else 'FAIL'}] 继续后原暂停 Job A 最先恢复（running=A）")

# 4) 为节省时间：取消 A（中断 item1）与其余排队 B/C
time.sleep(2)
for j in c.get("/api/v1/jobs").json()["items"]:
    if j["status"] in ("QUEUED", "PAUSED", "RUNNING"):
        r = c.post(f"/api/v1/jobs/{j['id']}/cancel")
        print("cancel", j["id"][:12], j["status"], r.status_code)
time.sleep(3)
# 确保队列恢复、无残留
c.post("/api/v1/queue/resume")
q = qstate()
print("FINAL running:", q.get("running"), "queued:", len(q["queued"]),
      "paused:", len(q["paused"]), "flag:", q["worker"]["queue_paused"])
print("images:", c.get("/api/v1/images").json()["total"])
