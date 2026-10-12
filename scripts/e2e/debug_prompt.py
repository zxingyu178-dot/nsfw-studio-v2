import time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8001"
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=False)
    pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
    responses = []
    pg.on("response", lambda r: responses.append((r.status, r.url)) if "/api/v1/prompts" in r.url else None)
    pg.goto(f"{BASE}/prompts", wait_until="networkidle")
    pg.get_by_role("button", name="新建 Prompt").click()
    dr = pg.locator(".ds-drawer").last
    dr.wait_for(state="visible")
    print("drawer inputs:", dr.locator("input").count(), "textareas:", dr.locator("textarea").count())
    dr.locator("input").first.fill("调试猫_999")
    dr.locator("textarea").nth(0).fill("masterpiece, best quality, a cute cat")
    create = dr.get_by_role("button", name="创建")
    print("create disabled:", create.is_disabled())
    create.click()
    time.sleep(3)
    print("drawer still open:", dr.is_visible())
    notice = pg.locator(".ds-notice").all_inner_texts()
    print("notices:", notice)
    print("grid cards:", pg.locator(".pp-card").count())
    print("grid container exists:", pg.locator(".pp-grid").count())
    print("responses:", responses)
    pg.screenshot(path=r"D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-dailyuse\temp\e2e_shots\h_debug.png")
    print("body snippet:", pg.inner_text(".ds-drawer__body")[:300] if dr.is_visible() else "(closed)")
    b.close()
