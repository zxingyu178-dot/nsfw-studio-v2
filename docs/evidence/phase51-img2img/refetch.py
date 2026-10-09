"""补取实验输出（提交客户端因排队超时退出后，ComfyUI 仍在执行该 prompt）。

用法：
    .venv/Scripts/python docs/evidence/phase51-img2img/refetch.py \
        --prompt-id <id> --label d080 --input docs/evidence/phase51-img2img/inputs/structure_test_768.png
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE_URL = "http://127.0.0.1:8188"
HERE = Path(__file__).parent
OUT_DIR = HERE / "outputs"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return tuple(struct.unpack(">II", data[16:24]))  # type: ignore[return-value]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-id", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--input", default="inputs/structure_test_768.png")
    parser.add_argument("--timeout", type=float, default=3600.0)
    args = parser.parse_args()

    client = httpx.Client(timeout=60.0, trust_env=False)
    started = time.monotonic()
    history: dict = {}
    while time.monotonic() - started < args.timeout:
        hist = client.get(f"{BASE_URL}/history/{args.prompt_id}").json()
        if args.prompt_id in hist:
            history = hist[args.prompt_id]
            break
        time.sleep(5.0)
    if not history:
        print("[FAIL] 超时仍未完成")
        return 3

    status = history.get("status", {})
    if status.get("status_str") != "success":
        print(f"[FAIL] 执行失败: {json.dumps(status, ensure_ascii=False)[:600]}")
        return 4

    images = history.get("outputs", {}).get("9", {}).get("images", [])
    if not images:
        print("[FAIL] 无输出")
        return 5
    view = client.get(f"{BASE_URL}/view", params={
        "filename": images[0]["filename"],
        "subfolder": images[0].get("subfolder", ""),
        "type": images[0].get("type", "output"),
    })
    view.raise_for_status()
    output_bytes = view.content
    output_path = OUT_DIR / f"{args.label}_output.png"
    output_path.write_bytes(output_bytes)

    input_bytes = (HERE / args.input).read_bytes()
    output_info = {
        "path": str(output_path),
        "sha256": _sha256(output_bytes),
        "bytes": len(output_bytes),
        "dimensions": _png_dimensions(output_bytes),
        "comfyui_file": images[0],
    }
    meta_path = OUT_DIR / f"{args.label}_metadata.json"
    record = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    record.update({
        "refetched_at": datetime.now(timezone.utc).isoformat(),
        "outcome": "OK",
        "history_status": status,
        "history_outputs": history.get("outputs", {}),
        "output": output_info,
        "checks": {
            **(record.get("checks") or {}),
            "refetched_after_queue_timeout": True,
            "execution_success": True,
            "output_valid_png": output_info["dimensions"] is not None,
            "output_dimensions_match_input": output_info["dimensions"] == _png_dimensions(input_bytes),
            "no_oom": "out of memory" not in json.dumps(status).lower(),
        },
    })
    meta_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] 补取完成: {output_path} 尺寸={output_info['dimensions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())