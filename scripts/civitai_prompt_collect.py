# -*- coding: utf-8 -*-
"""Civitai 提示词采集器（仅文本元数据，不下载图片本体）。

通道说明：
  1) 列表：GET https://civitai.com/api/v1/images
     - 底模过滤用复数参数 baseModels（单数 baseModel 无效）
     - 分级过滤用 browsingLevel 位掩码（1=None 2=Soft 4=Mature 8=X，12=Mature+X）
     - 分页用 cursor（metadata.nextCursor）
  2) 生成参数：图片详情页 SSR 中的 __NEXT_DATA__.trpcState（devalue 压缩），
     匿名或 API Key 均可拿到 /api/v1/images 已不再返回的 meta.prompt。

凭据：仅从环境变量 / 本地 .env 读取，不写入代码与输出。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_PROXY = "http://127.0.0.1:33210"
DEFAULT_BASE_MODELS = ["Pony", "Illustrious", "SDXL 1.0"]
PAGE_URL = "https://civitai.com/images/{id}"
LIST_URL = "https://civitai.com/api/v1/images"

SCORE_PREFIX = (
    "score_9, score_8_up, score_7_up, score_6_up, score_5_up, score_4_up, "
    "source_anime, rating_explicit, mature female, 18 years old"
)
LOCAL_NEGATIVE = (
    "worst quality, low quality, score_1, score_2, score_3, blurry, jpeg artifacts, "
    "bad anatomy, bad hands, missing fingers, extra digits, deformed, text, watermark, "
    "loli, child, young"
)

SUBMIT_WIDTH = 832
SUBMIT_HEIGHT = 1216

# 未成年相关硬拦截词（词边界匹配）
MINOR_TERMS = [
    "loli", "lolicon", "child", "children", "kid", "kids", "toddler", "infant",
    "baby", "underage", "minor", "shota", "shotacon", "teen", "teens", "teenager",
    "schoolgirl", "school boy", "little girl", "little boy", "young girl", "young boy",
    "preteen", "pubescent", "age regression",
]
# 需要人工复核但不直接丢弃的模糊词
REVIEW_TERMS = ["young", "small breasts", "petite"]

MINOR_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in MINOR_TERMS) + r")\b", re.I)
REVIEW_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in REVIEW_TERMS) + r")\b", re.I)
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)


# ---------------------------------------------------------------- 基础工具

def load_env_file(path: Path) -> None:
    """极简 .env 读取：KEY=VALUE，仅在环境变量缺省时生效。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def make_session(token: str, proxy: str | None) -> requests.Session:
    s = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=8, pool_maxsize=16, max_retries=0)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    })
    if token:
        s.headers["Authorization"] = f"Bearer {token}"
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    return s


def request_with_retry(session: requests.Session, url: str, *, params=None,
                       retries: int = 4, timeout: int = 45) -> requests.Response:
    last = None
    for attempt in range(retries):
        try:
            r = session.get(url, params=params, timeout=timeout)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                time.sleep(2.0 * (attempt + 1) + random.random())
                last = r
                continue
            return r
        except requests.RequestException as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1) + random.random())
    if isinstance(last, requests.Response):
        return last
    raise RuntimeError(f"请求失败（已重试 {retries} 次）：{url} -> {last}")


def check_proxy(session: requests.Session, proxy: str | None) -> None:
    """代理不可用时给出明确报错，而不是让后续请求逐个超时。"""
    if not proxy:
        return
    host, _, port = proxy.replace("http://", "").partition(":")
    import socket
    try:
        with socket.create_connection((host, int(port or 80)), timeout=5):
            pass
    except OSError as exc:
        raise SystemExit(
            f"[代理不可用] 无法连接 {proxy}（{exc}）。\n"
            f"请确认代理软件已启动，或用 --proxy 指定其他地址，或 --no-proxy 关闭代理。"
        )
    try:
        r = request_with_retry(session, "https://civitai.com/api/v1/images",
                               params={"limit": 1}, retries=2, timeout=30)
        if r.status_code != 200:
            raise SystemExit(f"[代理异常] 经代理访问 Civitai 返回 HTTP {r.status_code}，请检查代理规则。")
    except RuntimeError as exc:
        raise SystemExit(f"[代理异常] {exc}")


def devalue_decode(arr):
    """还原 devalue 压缩数组（trpcState 使用）。"""
    cache: dict[int, object] = {}
    specials = {-1: None, -2: float("nan"), -3: float("inf"), -4: float("-inf")}

    def resolve(n):
        if isinstance(n, bool) or not isinstance(n, int):
            return n
        if n < 0:
            return specials.get(n)
        if n in cache:
            return cache[n]
        v = arr[n]
        if isinstance(v, dict):
            out = {}
            cache[n] = out
            for k, val in v.items():
                out[k] = resolve(val)
            return out
        if isinstance(v, list):
            out = []
            cache[n] = out
            for val in v:
                out.append(resolve(val))
            return out
        cache[n] = v
        return v

    return resolve(0)


def extract_page_data(html: str) -> dict | None:
    """从图片详情页 SSR 中提取 image 数据对象（含 meta）。"""
    m = NEXT_DATA_RE.search(html)
    if not m:
        return None
    try:
        payload = json.loads(m.group(1))
        ts = payload.get("props", {}).get("pageProps", {}).get("trpcState")
        if ts is None:
            return None
        obj = devalue_decode(json.loads(ts)) if isinstance(ts, str) else ts
        queries = obj.get("queries", []) if isinstance(obj, dict) else []
        for q in queries:
            data = (q.get("state") or {}).get("data")
            if isinstance(data, dict) and "meta" in data and "resources" in data:
                return data
    except (ValueError, KeyError, TypeError):
        return None
    return None


# ---------------------------------------------------------------- 采集

def list_images(session: requests.Session, *, base_models: list[str], browsing_level: int,
                sort: str, period: str, target: int, max_pages: int,
                log) -> list[dict]:
    """游标分页拉列表，服务端已按底模/分级过滤，本地再按顶层 baseModel 复核。"""
    items: list[dict] = []
    seen: set[int] = set()
    cursor = None
    for page in range(1, max_pages + 1):
        params = [("limit", "200"), ("sort", sort), ("period", period),
                  ("browsingLevel", str(browsing_level))]
        params += [("baseModels", bm) for bm in base_models]
        if cursor:
            params.append(("cursor", cursor))
        r = request_with_retry(session, LIST_URL, params=params)
        if r.status_code != 200:
            log(f"[列表] 第 {page} 页 HTTP {r.status_code}: {r.text[:160]}")
            break
        body = r.json()
        batch = body.get("items") or []
        for it in batch:
            if it.get("baseModel") not in base_models:
                continue
            if it.get("id") in seen:
                continue
            seen.add(it["id"])
            items.append(it)
        log(f"[列表] 第 {page} 页 +{len(batch)}，累计候选 {len(items)}")
        cursor = (body.get("metadata") or {}).get("nextCursor")
        if not cursor or len(items) >= target * 2:
            break
        time.sleep(0.6)
    return items


def fetch_page_meta(session: requests.Session, item: dict, log) -> dict:
    """抓取详情页并解析 meta。"""
    iid = item["id"]
    rec = {
        "id": iid,
        "source_url": PAGE_URL.format(id=iid),
        "baseModel": item.get("baseModel"),
        "width": item.get("width"),
        "height": item.get("height"),
        "nsfwLevel": item.get("nsfwLevel"),
        "username": item.get("username"),
        "createdAt": item.get("createdAt"),
        "hash": item.get("hash"),
        "postId": item.get("postId"),
        "status": "ok",
    }
    try:
        r = request_with_retry(session, PAGE_URL.format(id=iid))
    except RuntimeError as exc:
        rec["status"] = "network_error"
        rec["error"] = str(exc)[:200]
        return rec

    if r.status_code == 403:
        rec["status"] = "blocked"
        rec["error"] = "cloudflare_403"
        return rec
    if r.status_code != 200:
        rec["status"] = "http_error"
        rec["error"] = f"http_{r.status_code}"
        return rec

    data = extract_page_data(r.text)
    if not data:
        rec["status"] = "parse_error"
        rec["error"] = "trpcstate_not_found"
        return rec

    meta = data.get("meta")
    rec["hideMeta"] = bool(data.get("hideMeta"))
    if not meta:
        rec["status"] = "meta_hidden" if data.get("hideMeta") else "meta_empty"
        return rec

    rec.update({
        "prompt": meta.get("prompt") or "",
        "negativePrompt": meta.get("negativePrompt") or "",
        "steps": meta.get("steps"),
        "cfgScale": meta.get("cfgScale"),
        "sampler": meta.get("sampler"),
        "scheduler": meta.get("scheduler"),
        "seed": meta.get("seed"),
        "metaModel": meta.get("Model"),
        "clipSkip": meta.get("clipSkip"),
    })
    if not rec["prompt"].strip():
        rec["status"] = "prompt_empty"
    return rec


# ---------------------------------------------------------------- 清洗

def dedupe(records: list[dict]) -> list[dict]:
    seen_id, seen_hash, seen_prompt = set(), set(), set()
    out = []
    for r in records:
        if r["id"] in seen_id:
            continue
        h = r.get("hash")
        if h and h in seen_hash:
            continue
        p = re.sub(r"\s+", " ", (r.get("prompt") or "").strip().lower())
        if p and p in seen_prompt:
            continue
        seen_id.add(r["id"])
        if h:
            seen_hash.add(h)
        if p:
            seen_prompt.add(p)
        out.append(r)
    return out


def safety_check(prompt: str) -> str:
    """ok / review / reject"""
    if MINOR_RE.search(prompt):
        return "reject"
    if REVIEW_RE.search(prompt):
        return "review"
    return "ok"


def normalize_tags(text: str) -> str:
    """去 <lora:...>/<lyco:...> 标签（本地无对应模型会报错），压缩空白与多余逗号。"""
    text = re.sub(r"<(?:lora|lyco):[^>]*>", "", text, flags=re.I)
    text = re.sub(r"\s*[\r\n]+\s*", " ", text)
    text = re.sub(r"\s*,\s*", ", ", text)
    parts = [p.strip() for p in text.split(",")]
    out, seen = [], set()
    for p in parts:
        if not p:
            continue
        key = p.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return ", ".join(out)


def clean_record(rec: dict) -> dict:
    prompt = normalize_tags(rec.get("prompt") or "")
    if not prompt.lower().startswith("score_9"):
        prompt = f"{SCORE_PREFIX}, {prompt}"
    else:
        rest = re.sub(r"^score_9[^,]*,\s*", "", prompt, flags=re.I)
        prompt = f"{SCORE_PREFIX}, {rest}"
    negative = normalize_tags(", ".join(
        p for p in [(rec.get("negativePrompt") or "").strip(), LOCAL_NEGATIVE] if p
    ))
    return {
        "source_url": rec["source_url"],
        "baseModel": rec["baseModel"],
        "width": rec.get("width"),
        "height": rec.get("height"),
        "nsfwLevel": rec.get("nsfwLevel"),
        "prompt": prompt,
        "negativePrompt": negative,
        "steps": rec.get("steps"),
        "cfgScale": rec.get("cfgScale"),
        "sampler": rec.get("sampler"),
        "scheduler": rec.get("scheduler"),
        "seed": rec.get("seed"),
        "username": rec.get("username"),
        "createdAt": rec.get("createdAt"),
        "submit": {
            "prompt": prompt,
            "negative": negative,
            "width": SUBMIT_WIDTH,
            "height": SUBMIT_HEIGHT,
            "requested_count": 9,
            "prompt_mode": "full",
            "seed_mode": "random",
            "seed": None,
        },
    }


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser(description="Civitai 提示词采集（仅文本元数据）")
    ap.add_argument("--target", type=int, default=20, help="目标条数（带提示词的有效条目）")
    ap.add_argument("--base-models", default=",".join(DEFAULT_BASE_MODELS))
    ap.add_argument("--browsing-level", type=int, default=12, help="4=Mature 8=X 12=Mature+X")
    ap.add_argument("--sort", default="Most Reactions")
    ap.add_argument("--period", default="Month", choices=["Day", "Week", "Month", "Year", "AllTime"])
    ap.add_argument("--max-pages", type=int, default=20)
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--proxy", default=None, help=f"默认 {DEFAULT_PROXY}，传 none 关闭")
    ap.add_argument("--out", default=None)
    ap.add_argument("--env-file", default=None)
    args = ap.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    load_env_file(Path(args.env_file) if args.env_file else project_root / ".env")
    token = os.environ.get("CIVITAI_API_KEY", "").strip()
    proxy = args.proxy if args.proxy is not None else os.environ.get("CIVITAI_PROXY", DEFAULT_PROXY)
    if proxy and proxy.lower() == "none":
        proxy = None

    out_dir = Path(args.out) if args.out else project_root / "runtime" / "civitai_prompts"
    out_dir.mkdir(parents=True, exist_ok=True)
    base_models = [b.strip() for b in args.base_models.split(",") if b.strip()]

    lock = threading.Lock()

    def log(msg: str) -> None:
        with lock:
            print(msg, flush=True)

    if not token:
        print("[提示] 未检测到 CIVITAI_API_KEY，匿名模式下 /api/v1/images 的 meta 恒为 null；"
              "本脚本改走详情页通道，仍可工作，但建议在 .env 中配置 Key。", flush=True)

    session = make_session(token, proxy)
    check_proxy(session, proxy)
    log(f"[配置] 底模={base_models} 分级={args.browsing_level} 排序={args.sort}/{args.period} "
        f"代理={proxy or 'off'} token={'已配置' if token else '无'}")

    candidates = list_images(session, base_models=base_models, browsing_level=args.browsing_level,
                             sort=args.sort, period=args.period, target=args.target,
                             max_pages=args.max_pages, log=log)

    records: list[dict] = []
    start = time.time()
    usable = 0
    chunk = max(20, args.target)
    pool = ThreadPoolExecutor(max_workers=max(1, args.workers))
    try:
        for offset in range(0, len(candidates), chunk):
            batch = candidates[offset:offset + chunk]
            log(f"[详情] 批次 {offset // chunk + 1}（{len(batch)} 条），开始抓详情页")
            futures = {pool.submit(fetch_page_meta, session, it, log): it for it in batch}
            for fut in as_completed(futures):
                rec = fut.result()
                records.append(rec)
                if rec.get("prompt") and safety_check(rec["prompt"]) == "ok":
                    usable += 1
                time.sleep(random.uniform(0.1, 0.3))
            log(f"[详情] 已完成 {len(records)} 条，可用 {usable}/{args.target}，"
                f"用时 {int(time.time() - start)}s")
            if usable >= args.target:
                break
            if args.target <= 0:
                break
    finally:
        pool.shutdown(wait=True)

    records.sort(key=lambda r: r["id"])
    raw = [r for r in records if r.get("prompt")]

    # 分桶
    rejected, reviewed, clean_src, empty = [], [], [], []
    for r in raw:
        verdict = safety_check(r["prompt"])
        if verdict == "reject":
            rejected.append(r)
        elif verdict == "review":
            reviewed.append(r)
        else:
            clean_src.append(r)
    clean_src = dedupe(clean_src)
    clean = [clean_record(r) for r in clean_src]

    # 不足目标条数时提示
    if len(clean) < args.target:
        log(f"[警告] 有效条目 {len(clean)} < 目标 {args.target}，可增大 --max-pages 或调整排序/周期")

    ts = time.strftime("%Y%m%d_%H%M%S")
    raw_path = out_dir / f"civitai_raw_{ts}.jsonl"
    with raw_path.open("w", encoding="utf-8") as f:
        for r in raw:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    csv_path = out_dir / f"civitai_clean_{ts}.csv"
    fields = ["source_url", "baseModel", "width", "height", "nsfwLevel", "prompt",
              "negativePrompt", "steps", "cfgScale", "sampler", "scheduler", "seed",
              "username", "createdAt"]
    with csv_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(clean)

    clean_json = out_dir / "civitai_clean_latest.json"
    clean_json.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")

    pending = out_dir / "pending_civitai.json"
    pending.write_text(json.dumps(
        {"to_resubmit": [c["submit"] for c in clean]}, ensure_ascii=False, indent=2
    ), encoding="utf-8")

    empty_json = out_dir / "civitai_empty_latest.json"
    empty_json.write_text(json.dumps(
        [{"id": r["id"], "source_url": r["source_url"], "status": r["status"],
          "hideMeta": r.get("hideMeta")} for r in records if not r.get("prompt")],
        ensure_ascii=False, indent=2), encoding="utf-8")

    review_json = out_dir / "civitai_review_latest.json"
    review_json.write_text(json.dumps(
        [{"source_url": r["source_url"], "prompt": r["prompt"]} for r in reviewed + rejected],
        ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "generated_at": ts,
        "params": {"base_models": base_models, "browsing_level": args.browsing_level,
                   "sort": args.sort, "period": args.period, "target": args.target},
        "listing_items": len(candidates),
        "detail_fetched": len(records),
        "with_prompt": len(raw),
        "clean": len(clean),
        "empty_or_hidden": sum(1 for r in records if not r.get("prompt")),
        "status_breakdown": {s: sum(1 for r in records if r["status"] == s)
                             for s in sorted({r["status"] for r in records})},
        "rejected_unsafe": len(rejected),
        "needs_review": len(reviewed),
        "outputs": {"raw_jsonl": str(raw_path), "clean_csv": str(csv_path),
                    "clean_json": str(clean_json), "pending_payload": str(pending),
                    "empty": str(empty_json), "review": str(review_json)},
    }
    (out_dir / "civitai_report_latest.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== 采集完成 ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
