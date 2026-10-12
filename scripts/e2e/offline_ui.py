import time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8002"
SHOTS = r"D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-dailyuse\temp\e2e_shots"

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=False)
    pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()

    # ---- 生成：适配器指向 8199（死），应优雅失败、Studio 不崩 ----
    pg.goto(f"{BASE}/generate", wait_until="networkidle")
    pg.locator(".wb-structured-field").first.locator("textarea").fill(
        "a cute cat, best quality, highly detailed")
    pg.wait_for_timeout(300)
    gen = pg.get_by_role("button", name="生成", exact=True)
    disabled = gen.is_disabled()
    title = gen.get_attribute("title") or ""
    print(f"[{'PASS' if disabled and '离线' in title else 'FAIL'}] Engine 离线 → 生成禁用：{title}")
    pg.wait_for_timeout(500)
    pg.screenshot(path=f"{SHOTS}\\offline_gen_disabled.png")

    # Studio 仍存活：导航可用
    nav_ok = []
    for path, label in [("/gallery", "图库"), ("/prompts", "提示词"),
                        ("/assets", "素材"), ("/settings", "设置")]:
        try:
            pg.goto(f"{BASE}{path}", wait_until="networkidle", timeout=15000)
            pg.wait_for_timeout(500)
            nav_ok.append(f"{label}:OK")
        except Exception as e:
            nav_ok.append(f"{label}:FAIL {e}")
    print("[offline rest usable]", nav_ok)
    pg.goto(f"{BASE}/gallery", wait_until="networkidle")
    pg.screenshot(path=f"{SHOTS}\\offline_gallery_ok.png")

    # 健康仍 ok
    print("health:", pg.evaluate(
        "async () => (await fetch('/api/v1/health')).json()"))
    b.close()
