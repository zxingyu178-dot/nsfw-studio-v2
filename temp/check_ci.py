"""CI 状态查询（直连 api.github.com，绕系统代理；只读）。

用法：
    .venv/Scripts/python temp/check_ci.py <branch> [wait_seconds]
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request

REPO = "zxingyu178-dot/nsfw-studio-v2"


def fetch_runs(branch: str, per_page: int = 5) -> list[dict]:
    url = (
        f"https://api.github.com/repos/{REPO}/actions/runs"
        f"?branch={branch}&per_page={per_page}"
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, headers={"User-Agent": "nsfw-studio-ci-check"})
    with opener.open(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))["workflow_runs"]


def main() -> int:
    branch = sys.argv[1] if len(sys.argv) > 1 else "develop"
    wait_seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    deadline = time.monotonic() + wait_seconds
    last_error = None
    while True:
        try:
            runs = fetch_runs(branch)
        except Exception as error:  # noqa: BLE001 —— 直连 GitHub 间歇性超时：重试直到窗口结束
            last_error = error
            if time.monotonic() >= deadline:
                print(f"[{branch}] fetch failed: {last_error}")
                return 1
            time.sleep(15)
            continue
        if not runs:
            print(f"[{branch}] no runs yet")
            return 1
        latest = runs[0]
        print(json.dumps({
            "branch": branch,
            "head_sha": latest["head_sha"][:9],
            "run_id": latest["id"],
            "event": latest["event"],
            "status": latest["status"],
            "conclusion": latest["conclusion"],
            "created_at": latest["created_at"],
            "url": latest["html_url"],
        }, ensure_ascii=False))
        if latest["status"] == "completed" or time.monotonic() >= deadline:
            return 0 if latest.get("conclusion") == "success" else 1
        time.sleep(20)


if __name__ == "__main__":
    raise SystemExit(main())