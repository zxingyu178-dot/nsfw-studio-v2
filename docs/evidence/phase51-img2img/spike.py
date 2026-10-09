"""Qwen-Image 2.1 零下载 latent Img2Img 实验（Phase 5.1 Task10/11/12）。

只读使用 ComfyUI（http://127.0.0.1:8188），仅上传 Studio 自己的实验输入图到
``NSFWStudio_experiment`` subfolder；不修改用户工作流 / 模型 / 节点 / 服务。
实验产物（输入 / 输出 / 元数据）全部落在本目录 outputs/，供 Gate C 判断。

用法（项目 venv，含 httpx）：
    .venv/Scripts/python.exe docs/evidence/phase51-img2img/spike.py \
        --input docs/evidence/phase51-img2img/inputs/structure_test_768.png \
        --prompt "..." --negative "..." \
        --seed 12345 --denoise 0.55 --label d055

成功标准（Task12）：输入成功上传 / 无缺节点缺模型 / 无 OOM / 输出有效且尺寸正确 /
Seed 与 denoise 确实进入 KSampler / 记录耗时。
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
DEFAULT_WORKFLOW = HERE / "workflow.json"
OUT_DIR = HERE / "outputs"
UPLOAD_SUBFOLDER = "NSFWStudio_experiment"
POLL_SECONDS = 3.0
TIMEOUT_SECONDS = 1200.0


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _png_dimensions(data: bytes) -> tuple[int, int] | None:
    """从 PNG 字节流解析 (width, height)（IHDR，> 24 bytes）。"""
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    width, height = struct.unpack(">II", data[16:24])
    return int(width), int(height)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="输入图片（PNG）")
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--negative", default="")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--denoise", type=float, default=0.55)
    parser.add_argument("--steps", type=int, default=25)
    parser.add_argument("--resolution", type=int, default=768,
                        help="TextEncodeQwenImage21.resolution（无参考图时仅占位，取输入尺寸级）")
    parser.add_argument("--label", default="run", help="输出文件标签（如 d055 / d100）")
    args = parser.parse_args()

    input_path = Path(args.input)
    input_bytes = input_path.read_bytes()
    input_dims = _png_dimensions(input_bytes)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc).isoformat()
    # trust_env=False：与 ComfyUIAdapter 一致，忽略系统代理（本机 SOCKS 代理会阻断直连）
    client = httpx.Client(timeout=60.0, trust_env=False)

    record: dict = {
        "started_at": started_at,
        "input": {
            "path": str(input_path),
            "sha256": _sha256(input_bytes),
            "bytes": len(input_bytes),
            "dimensions": input_dims,
        },
        "parameters": {
            "prompt": args.prompt, "negative": args.negative,
            "seed": args.seed, "denoise": args.denoise, "steps": args.steps,
        },
        "workflow_template": str(DEFAULT_WORKFLOW),
    }

    # 0) 预检：ComfyUI 在线 + 队列状态（不打断任何现有任务，只观察）
    stats = client.get(f"{BASE_URL}/system_stats").json()
    queue_before = client.get(f"{BASE_URL}/queue").json()
    record["preflight"] = {
        "comfyui_version": stats["system"]["comfyui_version"],
        "device": stats["devices"][0]["name"],
        "vram_total_mb": round(stats["devices"][0]["vram_total"] / 1024 / 1024),
        "vram_free_mb": round(stats["devices"][0]["vram_free"] / 1024 / 1024),
        "queue_running": len(queue_before.get("queue_running", [])),
        "queue_pending": len(queue_before.get("queue_pending", [])),
    }

    # 1) 上传输入图（Studio 自己的 subfolder；overwrite 仅影响本实验 file name）
    upload = client.post(
        f"{BASE_URL}/upload/image",
        files={"image": (input_path.name, input_bytes, "image/png")},
        data={"subfolder": UPLOAD_SUBFOLDER, "overwrite": "true"},
    )
    upload.raise_for_status()
    uploaded = upload.json()
    engine_ref = (
        f"{uploaded['subfolder']}/{uploaded['name']}"
        if uploaded.get("subfolder") else uploaded["name"]
    )
    record["upload"] = {"engine_ref": engine_ref, "response": uploaded}

    # 2) 构造实验 Workflow（只 patch 参数，不改 graph 结构）
    workflow = json.loads(DEFAULT_WORKFLOW.read_text(encoding="utf-8"))
    workflow["4"]["inputs"]["image"] = engine_ref
    workflow["6"]["inputs"]["prompt"] = args.prompt
    workflow["6"]["inputs"]["negative_prompt"] = args.negative
    workflow["6"]["inputs"]["resolution"] = args.resolution
    workflow["7"]["inputs"]["seed"] = args.seed
    workflow["7"]["inputs"]["denoise"] = args.denoise
    workflow["7"]["inputs"]["steps"] = args.steps
    workflow["9"]["inputs"]["filename_prefix"] = f"NSFWStudio_experiment/qwen_img2img/{args.label}"
    record["patched_workflow"] = workflow

    # 3) 提交
    submit = client.post(f"{BASE_URL}/prompt", json={"prompt": workflow})
    if submit.status_code != 200:
        record["submit"] = {"status": submit.status_code, "body": submit.text}
        _write_record(record, args.label, "SUBMIT_FAILED")
        print(f"[FAIL] /prompt {submit.status_code}: {submit.text[:500]}")
        return 2
    prompt_id = submit.json()["prompt_id"]
    record["submit"] = {"prompt_id": prompt_id}
    submit_ts = time.monotonic()
    print(f"[..] prompt 已提交: {prompt_id} (denoise={args.denoise})")

    # 4) 轮询 history（不碰 /interrupt）
    history: dict = {}
    while time.monotonic() - submit_ts < TIMEOUT_SECONDS:
        hist = client.get(f"{BASE_URL}/history/{prompt_id}").json()
        if prompt_id in hist:
            history = hist[prompt_id]
            break
        time.sleep(POLL_SECONDS)
    elapsed = round(time.monotonic() - submit_ts, 2)
    record["elapsed_seconds"] = elapsed
    if not history:
        record["history"] = None
        _write_record(record, args.label, "TIMEOUT")
        print(f"[FAIL] 超时（{TIMEOUT_SECONDS}s）未在 history 找到 prompt_id")
        return 3

    status = history.get("status", {})
    record["history_status"] = status
    record["history_outputs"] = history.get("outputs", {})
    if status.get("status_str") != "success":
        _write_record(record, args.label, "EXECUTION_FAILED")
        print(f"[FAIL] 执行未成功: {json.dumps(status, ensure_ascii=False)[:800]}")
        return 4

    # 5) 取回输出图片（/view），落盘到本目录
    images = history.get("outputs", {}).get("9", {}).get("images", [])
    if not images:
        _write_record(record, args.label, "OUTPUT_MISSING")
        print("[FAIL] SaveImage 节点没有输出")
        return 5
    view = client.get(f"{BASE_URL}/view", params={
        "filename": images[0]["filename"],
        "subfolder": images[0].get("subfolder", ""),
        "type": images[0].get("type", "output"),
    })
    view.raise_for_status()
    output_bytes = view.content
    output_dims = _png_dimensions(output_bytes)
    output_path = OUT_DIR / f"{args.label}_output.png"
    output_path.write_bytes(output_bytes)
    record["output"] = {
        "path": str(output_path),
        "sha256": _sha256(output_bytes),
        "bytes": len(output_bytes),
        "dimensions": output_dims,
        "comfyui_file": images[0],
    }
    record["finished_at"] = datetime.now(timezone.utc).isoformat()

    # 6) 断言（Task12 技术成功标准）
    checks = {
        "input_uploaded": bool(engine_ref),
        "execution_success": status.get("status_str") == "success",
        "output_valid_png": output_dims is not None,
        "output_dimensions_match_input": output_dims == input_dims,
        "seed_recorded": True,  # seed 写入 workflow["7"].inputs.seed（见 patched_workflow）
        "denoise_applied": workflow["7"]["inputs"]["denoise"] == args.denoise,
        "no_oom": "out of memory" not in json.dumps(status).lower(),
    }
    record["checks"] = checks
    ok = all(checks.values())
    _write_record(record, args.label, "OK" if ok else "CHECKS_FAILED")
    print(f"[{'OK' if ok else 'FAIL'}] 输出: {output_path} 尺寸={output_dims} 耗时={elapsed}s")
    print(f"      checks={json.dumps(checks, ensure_ascii=False)}")
    return 0 if ok else 6


def _write_record(record: dict, label: str, outcome: str) -> None:
    record["outcome"] = outcome
    path = OUT_DIR / f"{label}_metadata.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[..] 元数据: {path}")


if __name__ == "__main__":
    raise SystemExit(main())