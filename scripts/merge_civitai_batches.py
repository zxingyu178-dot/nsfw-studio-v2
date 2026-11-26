# -*- coding: utf-8 -*-
"""合并多批 Civitai 采集结果，按图片 ID / 提示词归一化去重，输出累计清单。

扫描 runtime/civitai_prompts 下各子目录（batch1/batch2/...）与根目录的
civitai_clean_latest.json、civitai_review_latest.json，去重后回写根目录累计产物。
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = PROJECT_ROOT / "runtime" / "civitai_prompts"


def norm_prompt(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s*,\s*", ",", t)
    return t


def image_id(rec: dict) -> str | None:
    url = rec.get("source_url") or ""
    m = re.search(r"/images/(\d+)", url)
    return m.group(1) if m else None


def load_clean(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    return data if isinstance(data, list) else []


def load_review(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []
    return data if isinstance(data, list) else []


def main() -> int:
    clean_files = sorted(OUT_DIR.glob("**/civitai_clean_latest.json"))
    review_files = sorted(OUT_DIR.glob("**/civitai_review_latest.json"))

    merged: list[dict] = []
    seen_id: set[str] = set()
    seen_prompt: set[str] = set()
    per_source: dict[str, int] = {}

    for f in clean_files:
        recs = load_clean(f)
        added = 0
        for r in recs:
            iid = image_id(r)
            key_p = norm_prompt(r.get("prompt", ""))
            if iid and iid in seen_id:
                continue
            if key_p and key_p in seen_prompt:
                continue
            if iid:
                seen_id.add(iid)
            if key_p:
                seen_prompt.add(key_p)
            merged.append(r)
            added += 1
        per_source[str(f.relative_to(OUT_DIR))] = added

    reviews: list[dict] = []
    seen_rev: set[str] = set()
    for f in review_files:
        for r in load_review(f):
            k = image_id(r) or norm_prompt(r.get("prompt", ""))
            if k and k not in seen_rev:
                seen_rev.add(k)
                reviews.append(r)

    # 底模分布统计
    by_model: dict[str, int] = {}
    for r in merged:
        m = r.get("baseModel") or "unknown"
        by_model[m] = by_model.get(m, 0) + 1

    pending = {"to_resubmit": [r["submit"] for r in merged]}

    (OUT_DIR / "civitai_clean_latest.json").write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "pending_civitai.json").write_text(
        json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "civitai_review_latest.json").write_text(
        json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")

    fields = ["source_url", "baseModel", "width", "height", "nsfwLevel", "prompt",
              "negativePrompt", "steps", "cfgScale", "sampler", "scheduler", "seed",
              "username", "createdAt"]
    with (OUT_DIR / "civitai_clean_latest.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(merged)

    summary = {
        "total_clean": len(merged),
        "total_review": len(reviews),
        "by_base_model": by_model,
        "sources": per_source,
    }
    (OUT_DIR / "civitai_merge_report.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
