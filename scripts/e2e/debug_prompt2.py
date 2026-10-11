import time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8001"
pname = f"E2E猫_{int(time.time())%100000}"
print("pname:", pname)
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=False)
    pg = b.new_context(viewport={"width": 1440, "height": 900}).new_page()
    posts = []
    pg.on("response", lambda r: posts.append((r.status, r.url, r.request.method))
          if "/api/v1/prompts" in r.url else None)
    pg.goto(f"{BASE}/prompts", wait_until="networkidle")
    print("cards before:", pg.locator(".pp-card").count())
    pg.get_by_role("button", name="新建 Prompt").click()
    dr = pg.locator(".ds-drawer").last
    dr.wait_for(state="visible")
    name_in = dr.locator("input").first
    name_in.fill(pname)
    print("name after fill:", name_in.input_value())
    dr.locator("textarea").nth(0).fill(
        "masterpiece, best quality, a cute orange cat, soft lighting, highly detailed")
    dr.get_by_role("button", name="创建").click()
    time.sleep(3)
    print("posts:", posts)
    print("notices:", pg.locator(".ds-notice").all_inner_texts())
    print("cards after:", pg.locator(".pp-card").count())
    titles = pg.locator(".pp-card__title").all_inner_texts()
    print("card titles:", titles)
    print("match count:", pg.locator(".pp-card", has_text=pname).count())
    pg.screenshot(path=r"D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-dailyuse\temp\e2e_shots\h_debug2.png")
    b.close()
