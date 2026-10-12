"""NSFW Studio V2 — Daily Use 真实浏览器走查（Playwright 驱动本机已安装的 Chrome）。

用法（在 worktree 根，用 venv python）：
  .venv\\Scripts\\python.exe scripts/e2e/daily_use_walkthrough.py ext
      → 外部引擎流程：C 1024 / D 竖图 / E 队列暂停 / F 队列收缩 / G Lightbox / H Prompt / EP 外部 Popover
  .venv\\Scripts\\python.exe scripts/e2e/daily_use_walkthrough.py managed
      → 受管引擎启停（需 8188 空闲；外部 ComfyUI 已由用户停止）
  .venv\\Scripts\\python.exe scripts/e2e/daily_use_walkthrough.py <section ...>

截图：temp/e2e_shots；结果在结尾打印 PASS/FAIL 汇总。真实生成走外部/受管 ComfyUI。
"""
from __future__ import annotations

import json
import re
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

BASE = "http://127.0.0.1:8001"
SHOTS = Path(r"D:\AIHome_2.0_L1_L2\projects\nsfw-studio-v2-dailyuse\temp\e2e_shots")
SHOTS.mkdir(parents=True, exist_ok=True)

results: list[tuple[str, bool, str]] = []


def check(name: str, cond: bool, info: str = "") -> None:
    results.append((name, bool(cond), info))
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {info}")


def shot(page: Page, name: str) -> None:
    try:
        page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)
    except Exception as e:
        print("shot err", name, e)


# ---------- API helpers (via same-origin request context) ----------

def api(page: Page, path: str, method: str = "GET", body: dict | None = None):
    init: dict = {"method": method}
    if body is not None:
        init["data"] = json.dumps(body)
        init["headers"] = {"Content-Type": "application/json"}
    r = page.request.fetch(f"{BASE}{path}", **init)
    try:
        data = r.json()
    except Exception:
        data = None
    return r.status, data


def jobs(page: Page) -> list[dict]:
    _, d = api(page, "/api/v1/jobs")
    return (d or {}).get("items", [])


def images(page: Page) -> list[dict]:
    _, d = api(page, "/api/v1/images")
    return (d or {}).get("items", [])


def queue(page: Page) -> dict:
    _, d = api(page, "/api/v1/queue")
    return d or {}


def wait_settle(page: Page, want_images: int = 0, timeout: int = 600) -> None:
    """等到无 RUNNING（且图片数 >= want_images）。"""
    start = time.time()
    while time.time() - start < timeout:
        js = jobs(page)
        running = [j for j in js if j.get("status") == "RUNNING"]
        if not running and len(images(page)) >= want_images:
            return
        page.wait_for_timeout(1000)
    raise TimeoutError("wait_settle 超时")


def wait_running(page: Page, timeout: int = 60) -> dict:
    start = time.time()
    while time.time() - start < timeout:
        q = queue(page)
        if q.get("running"):
            return q["running"]
        page.wait_for_timeout(500)
    raise TimeoutError("等待 RUNNING 超时")


# ---------- UI helpers ----------

def set_aspect(page: Page, value: str) -> None:
    page.get_by_label("画幅").select_option(value)


def set_quality(page: Page, value: str) -> None:
    page.get_by_label("分辨率档位").select_option(value)


def set_count(page: Page, value: str) -> None:
    page.get_by_role("combobox").nth(2).select_option(value)


def fill_style(page: Page, text: str) -> None:
    page.locator(".wb-structured-field").nth(0).locator("textarea").fill(text)


def click_generate(page: Page) -> None:
    page.get_by_role("button", name="生成", exact=True).click()


def queue_toggle(page):
    head = page.locator(".wb-queue__head")
    return head.get_by_role("button")


def pause_queue_ui(page: Page) -> None:
    btn = page.get_by_role("button", name=re.compile("暂停队列"))
    btn.click()
    page.wait_for_timeout(400)


def resume_queue_ui(page: Page) -> None:
    btn = page.get_by_role("button", name=re.compile("继续队列"))
    btn.click()
    page.wait_for_timeout(400)


def goto_generate(page: Page) -> None:
    page.goto(f"{BASE}/generate", wait_until="networkidle", timeout=30000)


# ---------- Section C: 1024 文生图 + 计时 ----------

def sec_c(page: Page) -> None:
    goto_generate(page)
    fill_style(page, "a cute orange cat sitting, soft studio lighting, highly detailed, best quality")
    set_aspect(page, "1:1")
    set_quality(page, "standard")
    set_count(page, "1")
    page.wait_for_timeout(300)
    before = len(images(page))
    click_generate(page)

    # Elapsed timer：捕获两次不同读数（证明在走表）
    readings: list[str] = []
    t0 = time.time()
    while time.time() - t0 < 90:
        texts = page.get_by_text(re.compile("已运行")).all_inner_texts()
        for t in texts:
            m = re.search(r"已运行\s*(\d\d:\d\d|\d:\d\d:\d\d)", t)
            if m and m.group(1) not in readings:
                readings.append(m.group(1))
        if len(readings) >= 2:
            break
        page.wait_for_timeout(1100)
    check("C-计时器每秒走表", len(readings) >= 2, f"readings={readings}")
    check("C-无 ETA", "ETA" not in page.inner_text("body") and "预计" not in page.inner_text("body"))

    wait_settle(page, want_images=before + 1)
    shot(page, "c_1024_done")
    imgs = images(page)
    check("C-生成 1024 图并入图库", len(imgs) >= before + 1,
          f"latest={imgs[0].get('width')}x{imgs[0].get('height')}" if imgs else "no img")


# ---------- Section D: 9:16 1080x1920 ----------

def sec_d(page: Page) -> None:
    goto_generate(page)
    fill_style(page, "a cute cat, vertical portrait, soft light, highly detailed, best quality")
    set_aspect(page, "9:16")
    set_quality(page, "hd")
    set_count(page, "1")
    page.wait_for_timeout(400)
    body = page.inner_text("body")
    cur = re.search(r"当前\s*(\d+)\s*[×x]\s*(\d+)", body)
    check("D-当前尺寸 1080×1920", bool(cur) and cur.group(1) == "1080" and cur.group(2) == "1920",
          cur.group(0) if cur else "未找到当前尺寸")
    check("D-提示较慢", "较慢" in body)
    gen = page.get_by_role("button", name="生成", exact=True)
    check("D-生成按钮可用(无校验错误)", gen.is_enabled())
    before = len(images(page))
    gen.click()
    wait_settle(page, want_images=before + 1, timeout=900)
    shot(page, "d_portrait_done")
    latest = images(page)[0]
    check("D-竖图实际 1080×1920", latest.get("width") == 1080 and latest.get("height") == 1920,
          f"{latest.get('width')}x{latest.get('height')}")


# ---------- Section E: 队列暂停/继续 ----------

def sec_e(page: Page) -> None:
    goto_generate(page)
    fill_style(page, "a cute cat, best quality, highly detailed")
    set_aspect(page, "1:1")
    set_quality(page, "standard")
    set_count(page, "2")
    page.wait_for_timeout(200)
    click_generate(page)           # Job A: count=2
    page.wait_for_timeout(800)
    set_count(page, "1")
    click_generate(page)           # Job B
    page.wait_for_timeout(800)
    click_generate(page)           # Job C

    running = wait_running(page)
    job_a = running["id"]
    pause_queue_ui(page)

    # 等当前 item0 跑完、Job 在安全边界暂停（running 变 None），最多 ~300s
    t0 = time.time()
    while time.time() - t0 < 300:
        if queue(page).get("running") is None:
            break
        page.wait_for_timeout(1000)
    # 再稳定观察 5s：确认无 RUNNING
    page.wait_for_timeout(5000)
    q = queue(page)
    check("E-队列已暂停", q["worker"]["queue_paused"] is True)
    check("E-暂停后无 RUNNING", q.get("running") is None)
    paused_ids = [j["id"] for j in q.get("paused", [])]
    queued_ids = [j["id"] for j in q.get("queued", [])]
    a_state = next((j["status"] for j in jobs(page) if j["id"] == job_a), None)
    check("E-JobA 安全边界暂停", a_state in ("PAUSED", "COMPLETED"), f"state={a_state}")
    check("E-后续 B/C 未开始", set([b for b in [*paused_ids, *queued_ids]]).__len__() >= 1,
          f"paused={paused_ids} queued={queued_ids}")
    shot(page, "e_paused")

    resume_queue_ui(page)
    page.wait_for_timeout(1500)
    q = queue(page)
    check("E-继续后原暂停 Job 优先", q.get("running", {}).get("id") == job_a,
          f"running={q.get('running',{}).get('id')} expect={job_a}")
    wait_settle(page, want_images=len(images(page)) + (1 if a_state == "PAUSED" else 0) + 2, timeout=900)
    shot(page, "e_resumed_done")


# ---------- Section F: 队列固定高度收缩 ----------

def sec_f(page: Page) -> None:
    goto_generate(page)
    fill_style(page, "a cute cat, best quality")
    set_aspect(page, "1:1"); set_quality(page, "standard"); set_count(page, "1")
    # 先经 API 暂停队列（空队列时 UI 不显示暂停按钮；API 可直接置 flag），再压 20 个任务（不真实生成）
    api(page, "/api/v1/queue/pause", method="POST")
    page.wait_for_timeout(400)
    for _ in range(20):
        click_generate(page)
        page.wait_for_timeout(250)
    # 等到 queued≈20
    t0 = time.time()
    while time.time() - t0 < 60:
        q = queue(page)
        if len(q.get("queued", [])) >= 20:
            break
        page.wait_for_timeout(1000)
    q = queue(page)
    n_queued = len(q.get("queued", []))

    lst = page.locator(".wb-queue-list--scroll")
    metrics = lst.evaluate(
        "el => ({ch:el.clientHeight, sh:el.scrollHeight, "
        "mh:getComputedStyle(el).maxHeight, ov:getComputedStyle(el).overflowY})")
    check("F-队列容器固定高度", metrics["ch"] <= 320, f"clientHeight={metrics['ch']}")
    check("F-内容超出可内部滚动", metrics["sh"] > metrics["ch"], f"sh={metrics['sh']} ch={metrics['ch']}")
    check("F-overflowY auto", metrics["ov"] in ("auto", "scroll"), metrics["ov"])
    scrolled = lst.evaluate("el => { el.scrollTop=200; return el.scrollTop }")
    check("F-内部可滚动", scrolled > 0, f"scrollTop={scrolled}")
    drag = page.locator(".wb-queue-list li[draggable='true']").count()
    check("F-行仍可拖拽", drag > 0, f"draggable rows={drag}")
    shot(page, "f_compact")

    # 清理：API 取消全部未完成，再恢复队列
    for j in jobs(page):
        if j.get("status") in ("QUEUED", "PAUSED"):
            api(page, f"/api/v1/jobs/{j['id']}/cancel", method="POST")
    page.wait_for_timeout(1500)
    api(page, "/api/v1/queue/resume", method="POST")
    check("F-压入 20 任务", n_queued >= 20, f"queued={n_queued}")


# ---------- Section G: Lightbox ----------

def lightbox_checks(page: Page, tag: str) -> None:
    ov = page.locator(".lb-overlay")
    ov.wait_for(state="visible", timeout=8000)
    img = ov.locator("img.lb-img")
    img.wait_for(state="visible", timeout=8000)

    box = img.bounding_box()
    cx = box["x"] + box["width"] / 2
    cy = box["y"] + box["height"] / 2
    page.mouse.move(cx, cy)
    for _ in range(5):
        page.mouse.wheel(0, -160)
        page.wait_for_timeout(120)
    tr = img.get_attribute("style") or ""
    zoomed = "scale(" in tr
    check(f"{tag}-滚轮缩放", zoomed, f"style={tr[:80]}")
    if zoomed:
        shot(page, f"{tag}_zoomed")

    ov.get_by_role("button", name="适应窗口").click()
    page.wait_for_timeout(200)
    check(f"{tag}-Fit 复位", "scale(" not in (img.get_attribute('style') or ''))
    ov.get_by_role("button", name="100%").click()
    page.wait_for_timeout(200)
    check(f"{tag}-100%", "scale(1)" in (img.get_attribute('style') or ''),
          (img.get_attribute('style') or '')[:80])

    # 拖动平移
    b = img.bounding_box()
    page.mouse.move(b["x"] + b["width"]/2, b["y"] + b["height"]/2)
    page.mouse.down()
    page.mouse.move(b["x"] + b["width"]/2 + 130, b["y"] + b["height"]/2 + 90, steps=6)
    page.mouse.up()
    page.wait_for_timeout(200)
    check(f"{tag}-拖动平移", "translate(" in (img.get_attribute('style') or ''),
          (img.get_attribute('style') or '')[:100])

    # 方向键切图
    cnt0 = ov.locator(".lb-count").inner_text()
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(400)
    cnt1 = ov.locator(".lb-count").inner_text()
    check(f"{tag}-方向键切图", cnt0 != cnt1, f"{cnt0} -> {cnt1}")

    # 只载当前：仅检查 Lightbox 内部（Gallery 网格缩略图是页面上另有的、预期存在，不计入）
    n_img = ov.locator("img.lb-img").count()
    ov_src = ov.evaluate(
        "el => Array.from(el.querySelectorAll('img')).map(i=>i.getAttribute('src'))")
    ov_content = [s for s in ov_src if s and "/api/v1/images/" in s]
    check(f"{tag}-Lightbox 只载当前(不预载全库)", n_img == 1 and len(ov_content) == 1,
          f"lb-img={n_img} overlay_content={ov_content}")

    page.keyboard.press("Escape")
    ov.wait_for(state="hidden", timeout=5000)
    check(f"{tag}-ESC 关闭", True)


def sec_g_gen(page: Page) -> None:
    # 紧跟在 sec_e 之后：不整页跳转，trackedJob 仍是刚完成、带图的 Job，result-stage 有图。
    if "/generate" not in page.url:
        goto_generate(page)
    main = page.locator(".result-stage img").first
    main.wait_for(state="visible", timeout=20000)
    main.dblclick()
    lightbox_checks(page, "G-Generate")


def sec_g_gal(page: Page) -> None:
    # Gallery：单击=Drawer；双击=Lightbox
    page.goto(f"{BASE}/gallery", wait_until="networkidle", timeout=30000)
    card = page.locator(".gal-card").first
    card.wait_for(state="visible", timeout=15000)
    card.click()
    page.wait_for_timeout(400)
    drawer_open = page.locator(".ds-drawer, .gal-detail").first.is_visible()
    check("G-Gallery 单击打开 Detail Drawer", drawer_open)
    check("G-Gallery 单击未开 Lightbox", page.locator(".lb-overlay").count() == 0)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    card.dblclick()
    page.wait_for_timeout(500)
    check("G-Gallery 双击打开 Lightbox", page.locator(".lb-overlay").is_visible())
    check("G-Gallery 双击未开 Drawer",
          not page.locator(".ds-drawer, .gal-detail").first.is_visible())
    lightbox_checks(page, "G-Gallery")


# ---------- Section H: Prompt 封面/摘要/复制 ----------

def sec_h(page: Page) -> None:
    page.goto(f"{BASE}/prompts", wait_until="networkidle", timeout=30000)
    page.get_by_role("button", name="新建 Prompt").click()
    drawer = page.locator(".ds-drawer").last
    drawer.wait_for(state="visible", timeout=8000)
    pname = f"E2E猫_{int(time.time())%100000}"
    drawer.locator("input").first.fill(pname)
    # 编辑器用 ui Textarea（ds-input--textarea）；第 0 个 textarea = 结构化“风格”
    drawer.locator("textarea").nth(0).fill(
        "masterpiece, best quality, a cute orange cat, soft lighting, highly detailed")
    drawer.get_by_role("button", name=re.compile("创建")).click()
    # 创建后抽屉默认保持打开；等“已创建”，关闭抽屉，再确认卡片
    try:
        page.get_by_text("已创建").wait_for(state="visible", timeout=8000)
    except Exception:
        pass
    page.keyboard.press("Escape")
    page.wait_for_timeout(700)
    card = page.locator(".pp-card", has_text=pname).first
    card.wait_for(state="visible", timeout=10000)
    check("H-创建 Prompt 卡片", card.is_visible())

    # 取后端 Prompt（合成 positive + 版本数）
    _, plist = api(page, "/api/v1/prompts")
    prompt = next((p for p in plist["items"] if p["name"] == pname), None)
    pid = prompt["id"]
    _, vers = api(page, f"/api/v1/prompts/{pid}/versions")
    versions_before = len(vers)

    # 设置封面：打开卡片 → 设置封面 → ImagePickerDrawer 选图
    card.click()
    drawer = page.locator(".ds-drawer").last
    drawer.wait_for(state="visible", timeout=8000)
    drawer.get_by_role("button", name=re.compile("设置封面|更换封面")).click()
    picker = page.locator(".ds-drawer", has_text="选择封面图片").last
    picker.wait_for(state="visible", timeout=8000)
    picker.locator(".wb-image-grid button, .wb-image-grid img").first.wait_for(
        state="visible", timeout=15000)
    picker.locator(".wb-image-grid button, .wb-image-grid img").first.click()
    page.wait_for_timeout(1500)
    page.keyboard.press("Escape")
    page.wait_for_timeout(800)

    card = page.locator(".pp-card", has_text=pname).first
    cover = card.locator("img.pp-card__cover")
    cover.wait_for(state="visible", timeout=10000)
    check("H-卡片封面 lazy", cover.get_attribute("loading") == "lazy",
          f"src={cover.get_attribute('src')}")
    check("H-摘要在图下", card.locator(".pp-card__excerpt").is_visible())

    _, vers = api(page, f"/api/v1/prompts/{pid}/versions")
    check("H-设封面不建版本", len(vers) == versions_before,
          f"{versions_before} -> {len(vers)}")

    # 一键复制：复制后端合成 positive，且不打开 Drawer
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    copy = card.get_by_role("button", name=re.compile("复制"))
    copy.click()
    page.wait_for_timeout(500)
    clip = page.evaluate("navigator.clipboard.readText()")
    full = prompt["current_version"]["positive_prompt"]
    check("H-复制为后端合成 positive", clip.strip() == full.strip(),
          f"clip[:60]={clip[:60]!r} full[:60]={full[:60]!r}")
    check("H-复制不打开 Drawer", not page.locator(".ds-drawer").is_visible())
    shot(page, "h_prompt_card")


# ---------- Section EP: 外部引擎 Popover ----------

def open_engine_popover(page: Page):
    # Engine 指示（UI 改造后为 button；兼容 span）
    candidates = [
        page.get_by_role("button", name=re.compile("Engine")).first,
        page.locator(".engine-indicators").get_by_text("Engine").first,
    ]
    for c in candidates:
        try:
            c.click(timeout=4000)
            pop = page.locator(".ep, [role='dialog']").last
            pop.wait_for(state="visible", timeout=6000)
            # 等首次 runtime 加载完成（离开“检测引擎状态…”）
            for _ in range(10):
                if "检测引擎状态" not in pop.inner_text():
                    break
                page.wait_for_timeout(700)
            return pop
        except Exception:
            continue
    raise RuntimeError("无法打开 Engine Popover")


def sec_ep(page: Page) -> None:
    goto_generate(page)
    pop = open_engine_popover(page)
    txt = pop.inner_text()
    check("EP-外部状态展示", "外部" in txt or "EXTERNAL" in txt or "ComfyUI" in txt, txt[:120])
    stop = pop.get_by_role("button", name=re.compile("停止")).count()
    restart = pop.get_by_role("button", name=re.compile("重启")).count()
    check("EP-外部不可停止/重启", stop == 0 and restart == 0,
          f"stop={stop} restart={restart}")
    check("EP-显示 not-owned 说明", "不是由 Studio 启动" in txt, txt[:160])
    shot(page, "ep_external_popover")
    page.keyboard.press("Escape")


# ---------- Section managed: 受管引擎启停（8188 空闲时） ----------

def sec_managed(page: Page) -> None:
    goto_generate(page)
    pop = open_engine_popover(page)
    # 启动
    start = pop.get_by_role("button", name=re.compile("启动"))
    check("B-STOPPED 显示启动", start.count() >= 1)
    start.first.click()
    # 轮询 runtime 直到 RUNNING_MANAGED
    t0 = time.time(); rt = {}
    while time.time() - t0 < 180:
        _, rt = api(page, "/api/v1/engine/runtime")
        if rt["state"] in ("RUNNING_MANAGED", "PORT_CONFLICT", "ERROR"):
            break
        page.wait_for_timeout(1000)
    check("B-STARTING→RUNNING_MANAGED", rt.get("state") == "RUNNING_MANAGED",
          f"state={rt.get('state')} owned={rt.get('owned')} pid={rt.get('pid')}")
    pid1 = rt.get("pid")
    # 幂等：再点启动不应换 PID
    pop = open_engine_popover(page)
    pop.get_by_role("button", name=re.compile("启动|运行中")).first.click()
    page.wait_for_timeout(2000)
    _, rt2 = api(page, "/api/v1/engine/runtime")
    check("B-重复启动幂等(同 PID)", rt2.get("pid") == pid1, f"{pid1} -> {rt2.get('pid')}")
    shot(page, "b_managed_running")

    # 停止（无 RUNNING Job）→ 进程树退出
    pop = open_engine_popover(page)
    pop.get_by_role("button", name=re.compile("停止引擎")).click()
    t0 = time.time()
    while time.time() - t0 < 120:
        _, rt = api(page, "/api/v1/engine/runtime")
        if rt["state"] in ("STOPPED", "ERROR"):
            break
        page.wait_for_timeout(1000)
    check("I-停止后 STOPPED", rt.get("state") == "STOPPED", f"state={rt.get('state')}")
    _, health = api(page, "/api/v1/engine/runtime")
    check("I-8188 不再健康", health.get("health", {}).get("online") is False)
    # 网页与图库/Prompt 仍可用
    check("I-停止后图库可浏览", len(images(page)) >= 0 and page.goto(f"{BASE}/gallery", wait_until="networkidle") is None)
    shot(page, "i_stopped")

    # 再启动可恢复
    goto_generate(page)
    pop = open_engine_popover(page)
    pop.get_by_role("button", name=re.compile("启动")).first.click()
    t0 = time.time()
    while time.time() - t0 < 180:
        _, rt = api(page, "/api/v1/engine/runtime")
        if rt.get("state") == "RUNNING_MANAGED":
            break
        page.wait_for_timeout(1000)
    check("I-再启动恢复 RUNNING_MANAGED", rt.get("state") == "RUNNING_MANAGED", f"state={rt.get('state')}")
    shot(page, "i_restarted")


SECTIONS = {
    "c": sec_c, "d": sec_d, "e": sec_e, "g_gen": sec_g_gen, "f": sec_f,
    "g_gal": sec_g_gal, "h": sec_h, "ep": sec_ep, "managed": sec_managed,
}
EXT_FLOW = ["c", "d", "e", "g_gen", "f", "g_gal", "h", "ep"]


def main() -> int:
    args = sys.argv[1:] or ["ext"]
    if args[0] == "ext":
        names = EXT_FLOW
    elif args[0] == "all":
        names = EXT_FLOW + ["managed"]
    else:
        names = args

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.grant_permissions(["clipboard-read", "clipboard-write"])
        page = context.new_page()
        for n in names:
            print(f"\n===== SECTION {n} =====")
            try:
                SECTIONS[n](page)
            except Exception as e:
                check(n + "-EXCEPTION", False, repr(e)[:200])
                shot(page, f"{n}_error")
        browser.close()

    print("\n========== SUMMARY ==========")
    npass = sum(1 for _, ok, _ in results if ok)
    nfail = sum(1 for _, ok, _ in results if not ok)
    for name, ok, info in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {info}")
    print(f"TOTAL {npass} passed / {nfail} failed")
    return 1 if nfail else 0


if __name__ == "__main__":
    sys.exit(main())
