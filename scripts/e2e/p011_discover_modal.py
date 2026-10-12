"""Discover cleanup modal markup + verify state intact."""
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8002"
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.goto(f"{BASE}/gallery", wait_until="domcontentloaded")
    pg.wait_for_selector(".gal-card")
    pg.wait_for_timeout(800)

    # state
    total = pg.request.fetch(f"{BASE}/api/v1/images?page_size=1").json()["total"]
    rej = pg.request.fetch(f"{BASE}/api/v1/images?status=REJECT&page_size=1").json()["total"]
    print("total:", total, "reject:", rej)

    pg.get_by_role("button", name="清理废片").click()
    pg.wait_for_timeout(1000)
    pg.screenshot(path=r"D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-phase011\temp\e2e_shots\discover_cleanup.png")

    # dump candidate overlay containers
    handles = pg.query_selector_all("[class*=odal],[class*=verlay],[class*=leanup],[role=dialog],[role=alertdialog]")
    print("overlay-ish nodes:")
    for h in handles:
        print("  class=", h.get_attribute("class"), "role=", h.get_attribute("role"),
              "visible=", h.is_visible())
    # all visible buttons with text + class
    print("visible buttons:")
    for bt in pg.query_selector_all("button"):
        if bt.is_visible() and bt.inner_text().strip():
            print("  ", repr(bt.inner_text().strip()), "class=", bt.get_attribute("class"))
    b.close()
