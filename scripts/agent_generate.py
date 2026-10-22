"""agent_generate — AI 助手（豆包等）可直接调用的本机生图 CLI。

背景：豆包在云端，无法直接访问 http://127.0.0.1:8000；正确分工是"豆包给参数/写一行命令，
在本机执行本脚本"。脚本内已处理 UTF-8、幂等键、轮询、取图（二进制保存）全部细节。

前置：后端已启动（默认为 http://127.0.0.1:8000）。

用法（项目根目录）：
    .venv/Scripts/python scripts/agent_generate.py --prompt "1girl, silver hair, kimono, shrine" \
        [--module anime_generate|basic_generate] \
        [--negative "..."] [--width 768] [--height 1024] [--count 1] [--seed 42] \
        [--upscale] [--next] [--out D:\\ai_out] [--api http://127.0.0.1:8000/api/v1] [--timeout-min 120]

示例（豆包只需改提示词）：
    .venv/Scripts/python scripts/agent_generate.py --module anime_generate \
        --prompt "1girl, red dress, night city, neon lights, anime style, masterpiece" --out D:\\ai_out

安全（推荐）：在 configs/config.local.yaml 配置 agent.token 后，
设置环境变量 NSFW_STUDIO_AGENT_TOKEN=<同一个 token>，脚本会自动走受保护的
POST /api/v1/agent/jobs（Bearer token + 每分钟限速 + 幂等）。未配置 token 时
仍走本机 /jobs（向后兼容；8000 只绑 loopback，外部 AI 无法直连）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import uuid
from pathlib import Path


def post(api: str, path: str, payload: dict, token: str | None = None) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")  # 中文安全：UTF-8 字节
    headers = {"Content-Type": "application/json; charset=utf-8"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        api + path, data=data, method="POST", headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise SystemExit(f"[FAIL] HTTP {error.code}: {body[:600]}") from error


def get(api: str, path: str) -> dict:
    with urllib.request.urlopen(api + path, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="本机生图 CLI（AI 助手调用入口）")
    parser.add_argument("--prompt", required=True, help="正向提示词（中文/英文标签均可）")
    parser.add_argument("--module", default="anime_generate",
                        choices=["anime_generate", "basic_generate"],
                        help="anime_generate=动漫（轻快）；basic_generate=写实")
    parser.add_argument("--negative", default="worst quality, low quality, blurry, jpeg artifacts, watermark, text")
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--seed", type=int, default=None, help="固定 Seed（默认随机）")
    parser.add_argument("--upscale", action="store_true", help="生成后再接一次高清放大")
    parser.add_argument("--next", dest="queue_next", action="store_true",
                        help="插队到等待队列最前（默认排到队尾）")
    parser.add_argument("--out", default=".", help="输出目录（默认当前目录）")
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--timeout-min", type=int, default=120, help="单任务超时（分钟）")
    parser.add_argument("--token", default=os.environ.get("NSFW_STUDIO_AGENT_TOKEN", ""),
                        help="Agent token（默认读 NSFW_STUDIO_AGENT_TOKEN；配置后走受保护的 /agent/jobs）")
    parser.add_argument("--legacy", action="store_true",
                        help="强制走旧 /jobs 端点（仅本机调试；不推荐）")
    args = parser.parse_args()

    modules = [{"module_id": args.module}]
    if args.upscale:
        modules.append({"module_id": "upscale"})

    token = (args.token or "").strip()
    if token and not args.legacy:
        # 加固路径：专用 Agent 端点，Bearer token + 服务端限速 + 幂等键。
        job = post(args.api, "/agent/jobs", {
            "prompt": args.prompt,
            "negative_prompt": args.negative,
            "module_id": args.module,
            "upscale": args.upscale,
            "width": args.width,
            "height": args.height,
            "count": args.count,
            "seed": args.seed,
            "queue_mode": "next" if args.queue_next else "normal",
            "client_request_id": f"cli_{uuid.uuid4().hex[:12]}",
        }, token=token)
    else:
        # 旧路径：本机 loopback UI 同款 /jobs（未配置 token 时保持向后兼容）。
        job = post(args.api, "/jobs", {
            "source": "doubao",
            "client_request_id": f"cli_{uuid.uuid4().hex[:12]}",
            "queue_mode": "next" if args.queue_next else "normal",
            "snapshot": {
                "prompt_mode": "full",
                "full_prompt": args.prompt,
                "negative_prompt": args.negative,
                "count": args.count,
                "width": args.width,
                "height": args.height,
                "seed_mode": "fixed" if args.seed is not None else "random",
                "seed": args.seed,
                "workflow_modules": modules,
                "input_images": [],
            },
        })
    job_id = job["id"]
    print(f"[..] job={job_id}  状态={job['status']}  模块={[m['module_id'] for m in modules]}")

    deadline = time.time() + args.timeout_min * 60
    detail = job
    while time.time() < deadline:
        detail = get(args.api, f"/jobs/{job_id}")
        if detail["status"] in ("COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"):
            break
        time.sleep(5)

    if detail["status"] != "COMPLETED":
        print(f"[FAIL] 任务未成功: {detail['status']} {detail.get('error_type')} {detail.get('error_message')}")
        return 2

    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = []
    for index, item in enumerate(detail["items"]):
        image_id = item.get("image_id")
        if not image_id:
            continue
        with urllib.request.urlopen(f"{args.api}/images/{image_id}/content", timeout=300) as response:
            data = response.read()  # 图片是二进制：只写文件，不当文本打印
        file_path = out_dir / f"{args.module}_{job_id[-8:]}_{index}.png"
        file_path.write_bytes(data)
        saved.append(str(file_path))
        print(f"[OK] {file_path}  ({len(data)} bytes)")

    if not saved:
        print("[FAIL] 任务完成但未找到输出图片")
        return 3
    print(f"[OK] 完成：{len(saved)} 张。Seed={detail['items'][0].get('seed')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())