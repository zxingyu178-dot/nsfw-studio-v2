import time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8001"
SHOTS = r"D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-dailyuse\temp\e2e_shots"
COMBOS = [
    (1280, 720, "dark"),
    (1440, 900, "dark"),
    (1920, 1080, "dark"),
    (1440, 900, "light"),
]


def api(page, path, method="GET"):
    js = f"""
    async () => {{
      const r = await fetch('{path}', {{method:'{method}'}});
      const t = await r.text();
      return [r.status, t ? JSON.parse(t) : null];
    }}"""
    return page.evaluate(js)


def set_theme(page, want):
    btn = page.get_by_role("button", name="切换深色/浅色主题")
    label = btn.inner_text()
    cur = "dark" if label == "深色" else "light"
    if cur != want:
        btn.click()
        page.wait_for_timeout(400)


def open_popover(page):
    trig = page.locator("[data-engine-trigger]").first
    if trig.count() == 0:
        trig = page.get_by_text("Engine").first
    trig.click()
    pop = page.locator(".ep, [role='dialog']").last
    pop.wait_for(state="visible", timeout=8000)
    for _ in range(10):
        if "检测引擎状态" not in pop.inner_text():
            break
        page.wait_for_timeout(600)
    return pop


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=False)
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()

    # 预暂停 + 压 8 个任务（队列视觉），全程不真实生成
    page.goto(f"{BASE}/generate", wait_until="networkidle")
    api(page, "/api/v1/queue/pause", "POST")
    page.wait_for_timeout(400)
    for i in range(8):
        api(page, "/api/v1/jobs", "POST") if False else None
    # 经 UI 压 8 个（保证 body 合法）：填一次风格后连点
    page.locator(".wb-structured-field").first.locator("textarea").fill(
        "a cute cat, best quality") if page.locator(".wb-structured-field").count() else None
    # 直接用最小合法 payload 经 fetch 提交
    payload = ('{"job_kind":"generate","prompt_mode":"structured",'
               '"structured_prompt":{"style":"a cute cat, best quality","face":"","clothing":"",'
               '"pose":"","scene":"","composition":"","lighting":"","extra":""},'
               '"generation_settings":{"width":1024,"height":1024,"seed_mode":"random"},'
               '"workflow_modules":[{"module_id":"basic_generate"}]}')
    for i in range(8):
        page.evaluate(
            "async (b) => { const r = await fetch('/api/v1/jobs',"
            "{method:'POST',headers:{'Content-Type':'application/json'},body:b}); return r.status; }",
            payload)
        page.wait_for_timeout(150)

    for (w, h, theme) in COMBOS:
        tag = f"{w}x{h}_{theme}"
        page.set_viewport_size({"width": w, "height": h})
        page.goto(f"{BASE}/generate", wait_until="networkidle")
        set_theme(page, theme)
        page.wait_for_timeout(500)
        page.screenshot(path=f"{SHOTS}\\vis_{tag}_gen.png")

        # Engine popover
        pop = open_popover(page)
        page.wait_for_timeout(800)
        page.screenshot(path=f"{SHOTS}\\vis_{tag}_engine.png")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # Prompt cards
        page.goto(f"{BASE}/prompts", wait_until="networkidle")
        page.wait_for_timeout(500)
        page.screenshot(path=f"{SHOTS}\\vis_{tag}_prompt.png")

        # Lightbox
        page.goto(f"{BASE}/gallery", wait_until="networkidle")
        page.wait_for_timeout(500)
        page.locator(".gal-card").first.dblclick()
        page.locator(".lb-overlay").wait_for(state="visible", timeout=8000)
        page.wait_for_timeout(700)
        page.screenshot(path=f"{SHOTS}\\vis_{tag}_lightbox.png")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        print("done", tag)

    # cleanup
    page.set_viewport_size({"width": 1440, "height": 900})
    page.goto(f"{BASE}/generate", wait_until="networkidle")
    jobs = api(page, "/api/v1/jobs")[1]["items"]
    for j in jobs:
        if j["status"] in ("QUEUED", "PAUSED", "RUNNING"):
            api(page, f"/api/v1/jobs/{j['id']}/cancel", "POST")
    page.wait_for_timeout(1500)
    api(page, "/api/v1/queue/resume", "POST")
    print("cleanup done")
    b.close()
