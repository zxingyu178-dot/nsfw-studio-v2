"""Capture genuine Light theme at 1440x900 (app uses explicit toggle, not prefers-color-scheme)."""
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8002"
SHOTS = Path(r"D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-phase011\temp\e2e_shots")

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
    pg = ctx.new_page()
    pg.goto(f"{BASE}/gallery", wait_until="domcontentloaded")
    pg.wait_for_selector(".gal-card")
    pg.wait_for_timeout(600)
    # 点击应用内主题切换（当前显示"深色"）→ 切到浅色
    toggle = pg.get_by_role("button", name="深色")
    if toggle.count() > 0:
        toggle.first.click()
        pg.wait_for_timeout(700)
    # 确认已切（按钮变为"浅色"）
    is_light = pg.get_by_role("button", name="浅色").count() > 0
    print("light mode active:", is_light)
    pg.screenshot(path=str(SHOTS / "matrix_1440_light_gallery.png"))
    pg.locator(".gal-card").first.dblclick()
    pg.wait_for_selector(".lb-side")
    pg.wait_for_timeout(1100)
    pg.screenshot(path=str(SHOTS / "matrix_1440_light_lightbox.png"))
    b.close()
print("done")
