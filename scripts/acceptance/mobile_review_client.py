#!/usr/bin/env python3
"""Mobile Review Bridge 独立验收客户端（不依赖 APK）。

模拟一台手机走完整审核流：
    health → pairing status → pairing verify(换 token) → create session →
    queue → preview → KEEP / favorite / REJECT → undo(RESET) → resume(latest) → complete。

用法（先由 Desktop loopback 起 Bridge 并生成配对码）：
    # 终端 A（Desktop 8000 loopback 生成配对码）：
    curl -X POST http://127.0.0.1:8000/api/v1/mobile-review/pairing/code
    # 终端 B（本客户端，指向 Bridge 8767）：
    python scripts/acceptance/mobile_review_client.py \
        --base-url http://127.0.0.1:8767 --code 123456 --installation-id accept-phone-1

已配对后可直接带 token 复跑：
    python scripts/acceptance/mobile_review_client.py --base-url ... --token <TOKEN>

退出码：0 全流程通过；非 0 任一步失败。
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
import urllib.error


def _request(method: str, url: str, token: str | None = None, body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return json.loads(raw)
        except Exception:
            return {"success": False, "error": {"code": "HTTP", "message": f"{e.code} {raw}"}}


def _unwrap(resp: dict) -> dict:
    """mobile envelope → data；失败抛异常。"""
    if not resp.get("success"):
        raise RuntimeError(f"API 失败: {resp.get('error')}")
    return resp.get("data") or {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8767")
    ap.add_argument("--code", default=None, help="6 位配对码（与 --token 二选一）")
    ap.add_argument("--token", default=None, help="已配对 Bearer token")
    ap.add_argument("--installation-id", default="accept-phone-1")
    ap.add_argument("--device-name", default="accept-client")
    args = ap.parse_args()
    base = args.base_url.rstrip("/")

    token = args.token

    print("[1] health")
    health = _unwrap(_request("GET", f"{base}/mobile/system/health"))
    assert health["product"] == "nsfw-studio", health
    print("    ok", health["version"], health["capabilities"])

    if not token:
        print("[2] pairing status")
        _unwrap(_request("GET", f"{base}/mobile/pairing/status"))

        print("[3] pairing verify")
        if not args.code:
            print("    缺少 --code 或 --token", file=sys.stderr)
            return 2
        paired = _unwrap(_request("POST", f"{base}/mobile/pairing/verify", body={
            "installation_id": args.installation_id,
            "device_name": args.device_name,
            "code": args.code,
        }))
        token = paired["token"]
        print("    paired device:", paired["device_id"])

    print("[4] create review session")
    session = _unwrap(_request("POST", f"{base}/mobile/review/sessions", token,
                              body={"filter": {"status": "NEW"}}))
    sid = session["id"]
    print("    session:", sid, "total:", session["total_count"])

    print("[5] queue page 1")
    queue = _unwrap(_request("GET", f"{base}/mobile/review/sessions/{sid}/queue?page=1&page_size=50", token))
    items = queue["items"]
    if not items:
        print("    队列为空（库中无 NEW 图）——跳过 decision，仍可 complete/exit")
    else:
        first = items[0]
        print("    first index:", first["index"], "image:", first["image"]["image_id"])

        print("[6] preview (HTTP HEAD-like GET, just verify 200 + headers)")
        img_id = first["image"]["image_id"]
        # 用原生请求看 headers
        req = urllib.request.Request(f"{base}/mobile/images/{img_id}/preview",
                                     headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                assert r.headers.get("X-Content-Type-Options") == "nosniff"
                assert "private" in r.headers.get("Cache-Control", "")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"preview 失败 {e.code}")
        print("    preview ok (nosniff + private)")

        print("[7] KEEP first")
        d = _unwrap(_request("POST", f"{base}/mobile/review/sessions/{sid}/decision", token, body={
            "item_index": first["index"], "action": "KEEP",
            "expected_status": "NEW", "expected_updated_at": first["image"]["updated_at"],
        }))
        assert d["image"]["status"] == "KEEP"
        print("    keep ok")

        print("[8] favorite same image")
        d = _unwrap(_request("POST", f"{base}/mobile/review/sessions/{sid}/decision", token, body={
            "item_index": first["index"], "favorite": True,
            "expected_status": "KEEP", "expected_updated_at": d["image"]["updated_at"],
        }))
        assert d["image"]["is_favorite"] is True
        print("    favorite ok")

        print("[9] REJECT second (if any)")
        if len(items) > 1:
            second = items[1]
            _unwrap(_request("POST", f"{base}/mobile/review/sessions/{sid}/decision", token, body={
                "item_index": second["index"], "action": "REJECT",
                "expected_status": "NEW", "expected_updated_at": second["image"]["updated_at"],
            }))
            print("    reject ok")

        print("[10] undo (RESET) first back to NEW")
        d = _unwrap(_request("POST", f"{base}/mobile/review/sessions/{sid}/decision", token, body={
            "item_index": first["index"], "action": "RESET", "expected_status": "KEEP",
        }))
        assert d["image"]["status"] == "NEW"
        print("    reset ok")

    print("[11] resume latest (不重建)")
    latest = _unwrap(_request("GET", f"{base}/mobile/review/sessions/latest", token))
    assert latest["id"] == sid
    print("    resumed:", latest["id"])

    print("[12] position")
    _unwrap(_request("POST", f"{base}/mobile/review/sessions/{sid}/position", token,
                     body={"item_index": 0}))
    print("    position ok")

    print("[13] complete（仍有未审则返回 remaining_count，不强完成）")
    done = _unwrap(_request("POST", f"{base}/mobile/review/sessions/{sid}/complete", token))
    print("    complete:", done)

    print("ALL OK")
    if token and not args.token:
        print(f"# 复跑可带 token：--token {token}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
