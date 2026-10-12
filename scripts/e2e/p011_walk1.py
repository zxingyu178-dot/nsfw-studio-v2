"""Phase 0.11 E2E (1/2)：性能无限滚动 + 废片清理 + Review Mode。

用 dailyuse venv 的 playwright（channel=chrome）连 http://127.0.0.1:8002。
"""
from __future__ import annotations

import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = "http://127.0.0.1:8002"
SHOTS = Path(r"D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-phase011\temp\e2e_shots")
SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, info: str = "") -> None:
    results.append((name, bool(cond), info))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}")


def api(pg: Page, path: str, method: str = "GET", body: dict | None = None):
    init: dict = {"method": method}
    if body is not None:
        init["data"] = __import__("json").dumps(body)
        init["headers"] = {"Content-Type": "application/json"}
    r = pg.request.fetch(f"{BASE}{path}", **init)
    try:
        return r.status, r.json()
    except Exception:
        return r.status, None


def status_total(pg: Page, status: str) -> int:
    _, d = api(pg, f"/api/v1/images?status={status}&page_size=1")
    return int(d["total"])


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    pg = b.new_page(viewport={"width": 1440, "height": 900})

    cnt = {"thumb": 0, "content": 0, "page": 0}

    def on_req(r):
        if "/thumbnail" in r.url:
            cnt["thumb"] += 1
        if "/content" in r.url:
            cnt["content"] += 1
        if "/api/v1/images?" in r.url:
            cnt["page"] += 1

    pg.on("request", on_req)

    # ============ A. 首屏 + 懒加载 ============
    t0 = time.time()
    pg.goto(f"{BASE}/gallery", wait_until="domcontentloaded")
    pg.wait_for_selector(".gal-card", timeout=15000)
    pg.wait_for_timeout(800)
    first_paint = time.time() - t0
    cards0 = len(pg.query_selector_all(".gal-card"))
    check("首屏仅40张(非一次全载)", cards0 == 40, f"cards={cards0}, firstPaint={first_paint:.2f}s")
    ph = len(pg.query_selector_all(".gal-card__ph"))
    imgs = len(pg.query_selector_all(".gal-card__img"))
    check("懒加载: 占位与已载并存", ph > 0 and imgs > 0, f"placeholder={ph}, loaded={imgs}")
    pg.screenshot(path=str(SHOTS / "a_first.png"))

    # ============ B. 无限滚动到末页（性能） ============
    # 逐页：滚到底→哨兵进入→加载下一页→新内容把哨兵推出视口（形成干净的 out→in 转换）
    tscroll = time.time()
    total_cards = cards0
    while total_cards < 1000:
        before = total_cards
        pg.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        try:
            pg.wait_for_function(
                f"document.querySelectorAll('.gal-card').length > {before}", timeout=5000)
        except Exception:
            pg.evaluate("window.scrollBy(0,-1200)")
            pg.wait_for_timeout(150)
            pg.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            pg.wait_for_function(
                f"document.querySelectorAll('.gal-card').length > {before}", timeout=8000)
        total_cards = len(pg.query_selector_all(".gal-card"))
    scroll_dur = time.time() - tscroll
    check("无限滚动加载全部1000张", total_cards == 1000,
          f"cards={total_cards}, duration={scroll_dur:.1f}s, pageRequests={cnt['page']}, thumbRequests={cnt['thumb']}")
    pg.screenshot(path=str(SHOTS / "b_bottom.png"))
    # 滚动阶段不应请求 original content（只用 thumbnail）
    check("图库浏览不加载 original", cnt["content"] == 0, f"contentRequests={cnt['content']}")

    # 重载回干净首屏（避免重 DOM 影响后续弹窗）
    pg.goto(f"{BASE}/gallery", wait_until="domcontentloaded")
    pg.wait_for_selector(".gal-card")
    pg.wait_for_timeout(700)

    # ============ C. 废片清理（两阶段 UI + 引用保护） ============
    reject_before = status_total(pg, "REJECT")
    check("清理前 REJECT=100", reject_before == 100, f"reject={reject_before}")
    # 预览（API 层，确认受保护数量）
    _, preview = api(pg, "/api/v1/images/cleanup-rejected", "POST", {"confirm": False})
    check("清理预览: 候选100/保护2",
          preview.get("candidate_count") == 100 and preview.get("protected_count") == 2, str(preview))
    # UI：打开清理弹窗
    pg.get_by_role("button", name="清理废片").click()
    pg.wait_for_selector(".ds-modal", timeout=8000)
    pg.wait_for_function(
        "() => (document.querySelector('.ds-modal')?.innerText||'').includes('候选数量')", timeout=8000)
    pg.wait_for_timeout(300)
    pg.screenshot(path=str(SHOTS / "c_cleanup_modal.png"))
    modal_txt = pg.query_selector(".ds-modal").inner_text()
    check("清理弹窗: 候选100/保护2/显示空间",
          ("100" in modal_txt and "2 张" in modal_txt and ("KB" in modal_txt or "MB" in modal_txt)),
          modal_txt.replace("\n", " ")[:150])
    # 点击确认并等待 confirm:true 的 POST 完整返回（避免读到删除中途状态）
    import re as _re

    def is_confirm_resp(r):
        if "/cleanup-rejected" not in r.url or r.request.method != "POST":
            return False
        pd = r.request.post_data or ""
        return ('"confirm":true' in pd) or ('"confirm": true' in pd)

    with pg.expect_response(is_confirm_resp, timeout=30000) as ri:
        pg.get_by_role("button", name=_re.compile("确认删除")).click()
    cbody = ri.value.json()
    check("清理结果: 删除98/保护2/无失败",
          cbody.get("deleted_count") == 98 and cbody.get("protected_count") == 2
          and len(cbody.get("failed", [])) == 0, str(cbody))
    pg.wait_for_timeout(400)
    reject_after = status_total(pg, "REJECT")
    _, total_d = api(pg, "/api/v1/images?page_size=1")
    check("清理后 REJECT 仅剩2(受保护)", reject_after == 2, f"reject={reject_after}")
    check("清理后总数=902", total_d["total"] == 902, f"total={total_d['total']}")
    # 受保护图仍存在且引用对象完好
    s_pimg, _ = api(pg, "/api/v1/images/img_seed_00007")
    s_aimg, _ = api(pg, "/api/v1/images/img_seed_00017")
    check("受保护图仍存在", s_pimg == 200 and s_aimg == 200, f"{s_pimg}/{s_aimg}")
    orig_root = Path(r"D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-phase011\temp\phase011_e2e_data\images\originals")
    check("被删图 original 文件已移除", not (orig_root / "img_seed_00027").exists())
    check("受保护图 original 保留", (orig_root / "img_seed_00007").exists())
    thumb_root = Path(r"D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-phase011\temp\phase011_e2e_data\images\thumbnails")
    check("被删图 thumbnail 文件已移除",
          list(thumb_root.rglob("*00027*")) == [])

    # ============ D. Review Mode（Job module5 先做 pristine；全局 module4 后做） ============
    new_before = status_total(pg, "NEW")
    check("Review 前 NEW=670", new_before == 670, f"new={new_before}")

    # D1 Job 审核（在任何全局打标之前，初始为 16 全新）
    pg.get_by_role("button", name="按任务查看").click()
    pg.wait_for_selector(".gal-group", timeout=10000)
    pg.wait_for_timeout(500)
    pg.screenshot(path=str(SHOTS / "d_groups.png"))
    _, js_before = api(pg, "/api/v1/images/by-job/job_demo/summary")
    check("Job 初始统计: 16/未审核16",
          js_before.get("total") == 16 and js_before.get("unreviewed") == 16, str(js_before))
    pg.locator(".gal-group").get_by_role("button", name="开始审核").click()
    pg.wait_for_timeout(1000)
    pg.screenshot(path=str(SHOTS / "d_job_review.png"))
    # 打标：5 张保留(A) + 11 张淘汰(D)，打标自动前进
    for _ in range(5):
        pg.keyboard.press("a")
        pg.wait_for_timeout(300)
    for _ in range(11):
        pg.keyboard.press("d")
        pg.wait_for_timeout(300)
    pg.wait_for_timeout(500)
    pg.screenshot(path=str(SHOTS / "d_job_review_done.png"))
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(500)
    _, js_after = api(pg, "/api/v1/images/by-job/job_demo/summary")
    check("Job 结束统计: 保留5/淘汰11/未审0",
          js_after.get("kept") == 5 and js_after.get("rejected") == 11
          and js_after.get("unreviewed") == 0, str(js_after))
    # 返回平铺视图
    pg.get_by_role("button", name="按任务查看").click()
    pg.wait_for_selector(".gal-card", timeout=10000)
    pg.wait_for_timeout(500)

    # D2 全局 Review：方向键往返，F 收藏一张，截图，退出
    pg.get_by_role("button", name="开始审核").click()
    pg.wait_for_timeout(1000)
    pg.screenshot(path=str(SHOTS / "d_review_mode.png"))
    pg.keyboard.press("ArrowRight")
    pg.wait_for_timeout(250)
    pg.keyboard.press("ArrowLeft")
    pg.wait_for_timeout(250)
    pg.keyboard.press("f")
    pg.wait_for_timeout(400)
    pg.screenshot(path=str(SHOTS / "d_global_fav.png"))
    pg.keyboard.press("Escape")
    pg.wait_for_timeout(600)
    fav_global = status_total(pg, "FAVORITE")
    check("全局 Review F 收藏生效(10→11)", fav_global == 11, f"favorite={fav_global}")

    print("\n==== SUMMARY ====")
    for n, ok, info in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {n} {info}")
    b.close()
