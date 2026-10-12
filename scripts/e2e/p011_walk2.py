"""Phase 0.11 真机走查 2：详情抽屉动作 + Lightbox 信息栏/缩放 + 视觉矩阵。

前置：walk1 已在同一 DataRoot 跑过（清理 + 审核）。后端 8002。
"""
from __future__ import annotations
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8002"
WT = Path(r"D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-phase011")
SHOTS = WT / "temp" / "e2e_shots"
SHOTS.mkdir(parents=True, exist_ok=True)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, info: str = "") -> None:
    results.append((name, ok, info))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} {info}")


def api_json(pg, path: str):
    raw = pg.evaluate(
        "async (u) => { const r = await fetch(u); return { status: r.status, body: await r.text() }; }",
        path,
    )
    return raw["status"], json.loads(raw["body"])


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    ctx.grant_permissions(["clipboard-read", "clipboard-write"], origin=BASE)
    pg = ctx.new_page()
    content_seen = []
    pg.on("request", lambda r: (
        content_seen.append(r.url) if ("/content" in r.url and "thumbnail" not in r.url) else None))

    pg.goto(f"{BASE}/gallery", wait_until="domcontentloaded")
    pg.wait_for_selector(".gal-card")
    pg.wait_for_timeout(800)

    # 第一张图 id（job-linked，全字段）
    first_id = pg.evaluate(
        "() => document.querySelector('.gal-card img').src"
    ).split("/images/")[1].split("/thumbnail")[0]
    print("first image:", first_id)

    # ============ A. 详情抽屉（单击） ============
    pg.locator(".gal-card").first.click()
    pg.wait_for_selector(".gal-fields", timeout=8000)
    pg.wait_for_timeout(800)
    drawer = pg.get_by_role("dialog")
    dtext = drawer.inner_text()
    check("抽屉: 尺寸字段", "×" in dtext, "")
    check("抽屉: Prompt 内容", "masterpiece" in dtext, "")
    check("抽屉: Seed 字段", "Seed" in dtext, "")
    check("抽屉: 任务字段", "任务" in dtext, "")

    # A1 复制 Prompt → 剪贴板含 masterpiece
    drawer.get_by_role("button", name="复制 Prompt").click()
    pg.wait_for_timeout(500)
    clip = pg.evaluate("async () => await navigator.clipboard.readText()")
    check("复制 Prompt 到剪贴板", "masterpiece" in clip, clip[:40])

    # A2 创建素材
    name_input = drawer.locator(".gal-asset-edit").first.locator("input")
    name_input.fill("E2E测试素材")
    drawer.locator(".gal-asset-edit").first.get_by_role("button", name="创建素材").click()
    pg.wait_for_timeout(1500)
    _, assets = api_json(pg, "/api/v1/assets")
    asset_items = assets.get("items", assets if isinstance(assets, list) else [])
    linked = [a for a in asset_items if a.get("source_image_id") == first_id]
    check("创建素材并记录 source_image_id", len(linked) >= 1,
          f"assets={len(asset_items)} linked={len(linked)}")

    # A3 设为 Prompt 封面（prompt_demo）
    cover_section = drawer.locator(".gal-asset-edit").nth(1)
    if cover_section.get_by_role("button", name="选择 Prompt").count() > 0:
        cover_section.get_by_role("button", name="选择 Prompt").click()
    cover_sel = cover_section.locator("select").first
    cover_sel.wait_for(state="visible", timeout=8000)
    pg.wait_for_function(
        "() => Array.from(document.querySelectorAll('.gal-asset-edit select option'))"
        ".some((o) => o.value === 'prompt_demo')",
        timeout=8000,
    )
    cover_sel.select_option(value="prompt_demo")
    pg.wait_for_timeout(300)
    cover_section.get_by_role("button", name="设为封面").click()
    pg.wait_for_timeout(1200)
    _, prompts = api_json(pg, "/api/v1/prompts?limit=200")
    pitems = prompts.get("items", [])
    pd = next((x for x in pitems if x.get("id") == "prompt_demo"), None)
    check("设为 prompt_demo 封面", pd is not None and pd.get("preview_image_id") == first_id,
          f"preview={pd.get('preview_image_id') if pd else None}")

    pg.screenshot(path=str(SHOTS / "walk2_drawer.png"))
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(600)

    # ============ B. Lightbox（双击） ============
    content_seen.clear()
    pg.locator(".gal-card").first.dblclick()
    pg.wait_for_selector(".lb-side", timeout=8000)
    pg.wait_for_timeout(1200)
    pg.screenshot(path=str(SHOTS / "walk2_lightbox.png"))
    side = pg.locator(".lb-side").inner_text()
    check("Lightbox 信息栏: 尺寸", "×" in side, "")
    check("Lightbox 信息栏: Prompt", "masterpiece" in side, "")
    check("Lightbox 信息栏: 来源 Job", "Job" in side, "")
    check("Lightbox 加载 original(/content)",
          any(first_id in u and "/content" in u for u in content_seen), str(content_seen[:2]))

    # B1 滚轮缩放
    box = pg.locator(".lb-stage").bounding_box()
    pg.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    for _ in range(4):
        pg.mouse.wheel(0, -200)
        pg.wait_for_timeout(120)
    tf = pg.locator(".lb-img").get_attribute("style") or ""
    check("滚轮放大(scale>1)", "scale(" in tf and tf.split("scale(")[1].split(")")[0] > "1", tf)
    pg.get_by_role("button", name="适应窗口").click()
    pg.wait_for_timeout(300)
    pg.get_by_role("button", name="100%").click()
    pg.wait_for_timeout(300)
    tf2 = pg.locator(".lb-img").get_attribute("style") or ""
    check("100% 按钮", "scale(1" in tf2, tf2)

    # B2 方向键下一张 → 新 /content
    content_seen.clear()
    pg.get_by_role("button", name="下一张").click()
    pg.wait_for_timeout(900)
    check("下一张加载新 original", len(content_seen) >= 1, str(content_seen[:1]))
    pg.screenshot(path=str(SHOTS / "walk2_lightbox_next.png"))
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(500)

    # ============ C. 视觉矩阵 ============
    def matrix(width, height, theme, tag):
        ctx.close()
        c2 = b.new_context(viewport={"width": width, "height": height}, color_scheme=theme)
        p2 = c2.new_page()
        p2.goto(f"{BASE}/gallery", wait_until="domcontentloaded")
        p2.wait_for_selector(".gal-card")
        p2.wait_for_timeout(700)
        p2.screenshot(path=str(SHOTS / f"matrix_{tag}_gallery.png"))
        p2.locator(".gal-card").first.dblclick()
        p2.wait_for_selector(".lb-side")
        p2.wait_for_timeout(1000)
        p2.screenshot(path=str(SHOTS / f"matrix_{tag}_lightbox.png"))
        p2.keyboard.press("Escape")
        p2.wait_for_timeout(300)
        return c2, p2

    ctx, pg = matrix(1280, 720, "dark", "1280_dark")
    ctx, pg = matrix(1440, 900, "dark", "1440_dark")
    ctx, pg = matrix(1440, 900, "light", "1440_light")
    ctx, pg = matrix(1920, 1080, "dark", "1920_dark")

    print("\n==== SUMMARY ====")
    for n, ok, info in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {n} {info}")
    b.close()
