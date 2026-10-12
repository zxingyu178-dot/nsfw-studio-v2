"""Phase 0.11 — 探索 Gallery 真实 DOM（用 dailyuse venv 的 playwright，连 8002）。"""
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8002"
SHOTS = Path(r"D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-phase011\temp\e2e_shots")
SHOTS.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1440, "height": 900})
    pg.goto(f"{BASE}/gallery", wait_until="networkidle")
    pg.wait_for_timeout(1500)
    pg.screenshot(path=str(SHOTS / "explore_gallery.png"))

    # tabs / filters
    tabs = [t.inner_text() for t in pg.query_selector_all("[role=tab], .ds-tabs button, button")]
    print("buttons/tabs (first 30):", tabs[:30])
    print("card count:", len(pg.query_selector_all(".gal-card")))
    print("count text:", pg.query_selector(".gal-count").inner_text() if pg.query_selector(".gal-count") else None)
    print("placeholder count:", len(pg.query_selector_all(".gal-card__ph")))
    print("img count:", len(pg.query_selector_all(".gal-card__img")))
    print("sentinel:", pg.query_selector("[data-sentinel], .gal-sentinel").get_attribute("class")
          if pg.query_selector("[data-sentinel], .gal-sentinel") else None)
    # any toolbar buttons (review/cleanup)
    for sel in ["button"]:
        pass
    labels = [b2.inner_text() for b2 in pg.query_selector_all("button")]
    print("all buttons:", [x for x in labels if x.strip()][:40])
    b.close()
