"""Discover group view + verify original deletion layout."""
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8002"
orig = Path(r"D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-phase011\temp\phase011_e2e_data\images\originals")
for i in ["00007", "00017", "00027"]:
    d = orig / f"img_seed_{i}"
    print(f"dir img_seed_{i}: exists={d.exists()}, contents={list(d.glob('*')) if d.exists() else None}")

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.goto(f"{BASE}/gallery", wait_until="domcontentloaded")
    pg.wait_for_selector(".gal-card")
    pg.wait_for_timeout(600)
    pg.get_by_role("button", name="按任务查看").click()
    pg.wait_for_timeout(1800)
    pg.screenshot(path=r"D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-phase011\temp\e2e_shots\discover_groups.png")
    # dump group-related classes/text
    body = pg.query_selector("main") or pg.query_selector("body")
    txt = body.inner_text
    print("main text (first 600):", body.inner_text()[:600])
    print("group card nodes:", [h.get_attribute("class") for h in pg.query_selector_all("[class*=group i]")])
    print("开始审核 count:", len(pg.get_by_role("button", name="开始审核").all()))
    b.close()
