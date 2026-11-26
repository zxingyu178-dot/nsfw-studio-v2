"""Mobile Bridge 版本与构建身份的唯一事实源。

Bridge 是独立进程，不能依赖主 Studio 的版本号；health 必须同时暴露
版本、构建提交和能力集哈希，避免“同版本不同物”。
"""
from __future__ import annotations

import hashlib
import os
import subprocess
from functools import lru_cache
from pathlib import Path

MOBILE_BRIDGE_VERSION = "0.14.0"
MOBILE_API_CONTRACT = 2

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


@lru_cache(maxsize=1)
def _build_commit() -> str:
    return os.environ.get("NSFW_BUILD_COMMIT") or _git("rev-parse", "--short", "HEAD") or "unknown"


@lru_cache(maxsize=1)
def _built_at() -> str:
    return os.environ.get("NSFW_BUILD_TIME") or _git("show", "-s", "--format=%cI", "HEAD") or "unknown"


def capability_set_hash(capabilities: tuple[str, ...] | list[str]) -> str:
    raw = "\n".join(sorted(capabilities)).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:12]


def build_identity(capabilities: tuple[str, ...] | list[str]) -> dict[str, str]:
    return {
        "build_commit": _build_commit(),
        "built_at": _built_at(),
        "capability_set_hash": capability_set_hash(capabilities),
    }
