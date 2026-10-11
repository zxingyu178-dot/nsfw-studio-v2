"""NSFW Studio V2 Phase 0.11 - 构建交接包（含禁含扫描）。

用法（worktree 根）：
    .venv\\Scripts\\python.exe scripts\\build_handoff_p011.py

输出（temp 下，避免污染源码树）：
    temp\\NSFW_Studio_Phase0.11_Handoff.zip

只含：阶段报告/测试结果/Git 信息/核心源码/migration/启动脚本/config template。
严禁含：图片/模型/数据库/config.local.yaml/DataRoot/.venv/node_modules/dist/日志。
打包后做二次禁含扫描，发现违禁条目即非零退出。
"""
from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "temp" / "NSFW_Studio_Phase0.11_Handoff.zip"

# 以目录整体纳入（仍会逐文件过排除规则）
INCLUDE_DIRS = [
    "backend/app",
    "tests",
    "frontend/src",
    "scripts",
    "configs",
]
# 单独文件
INCLUDE_FILES = [
    "backend/requirements.txt",
    "backend/requirements-dev.txt",
    "pytest.ini",
    "frontend/package.json",
    "frontend/package-lock.json",
    "frontend/tsconfig.json",
    "frontend/vite.config.ts",
    "docs/PHASE011_BASELINE.md",
]
# 阶段报告目录整体
REPORT_DIR = ROOT / "docs" / "phase011"

EXCLUDE_PARTS = {
    ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".git", "dist", "coverage", ".idea", ".vscode", "temp", "evidence",
}
EXCLUDE_SUFFIXES = {
    # 数据 / 日志 / 字节码
    ".db", ".sqlite", ".sqlite3", ".log", ".pyc",
    # 图片（真实/合成图片一律不入；测试在运行时用 Pillow 生成）
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif", ".ico",
    # 音视频
    ".mp4", ".webm", ".mov", ".mkv", ".avi", ".mp3", ".wav", ".flac", ".ogg",
    # 模型权重
    ".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".onnx",
}
# DataRoot / 私有配置路径关键字
FORBIDDEN_PATH_HINTS = (
    "dataroot", "data_root", "config.local", "originals/", "processed/",
    "thumbnails/", "upscaled/", "comfyui/outputs", "studio.db",
)
MAX_BYTES = 3_000_000  # 单条目上限（package-lock 等通常 < 3MB）


def is_private_config(path: Path) -> bool:
    return path.name.endswith((".local.yaml", ".local.yml", ".local.json"))


def excluded(path: Path) -> bool:
    if set(path.parts) & EXCLUDE_PARTS:
        return True
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    if is_private_config(path):
        return True
    return False


def git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True,
            encoding="utf-8", check=True,
        ).stdout
    except Exception as exc:  # noqa: BLE001
        return f"(git {args} 获取失败: {exc})"


def collect() -> list[tuple[Path, str]]:
    items: list[tuple[Path, str]] = []
    seen: set[str] = set()

    def add(path: Path, arc: str) -> None:
        if not path.is_file() or excluded(path) or arc in seen:
            return
        items.append((path, arc))
        seen.add(arc)

    # 报告（置于 reports/ 下）
    for f in sorted(REPORT_DIR.glob("*.md")):
        add(f, f"reports/{f.name}")
    add(ROOT / "docs/PHASE011_BASELINE.md", "reports/PHASE011_BASELINE.md")

    for name in INCLUDE_FILES:
        add(ROOT / name, name)

    for d in INCLUDE_DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for f in sorted(base.rglob("*")):
            if f.is_file():
                add(f, f.relative_to(ROOT).as_posix())

    return items


def main() -> int:
    OUT.parent.mkdir(exist_ok=True)
    items = collect()

    meta = (
        "NSFW Studio V2 - Phase 0.11 Handoff\n"
        f"Branch: feature/phase0.11-image-asset-management\n"
        f"Functional close: {git('rev-parse', 'HEAD~1').strip()}\n"
        f"Final HEAD: {git('rev-parse', 'HEAD').strip()}\n"
        f"Remote: {git('ls-remote', 'origin', 'feature/phase0.11-image-asset-management').strip()}\n"
    )
    gitlog = git("log", "--oneline", "f6fad0d..HEAD")
    status = git("status", "--porcelain") or "(clean)\n"

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("GIT_INFO.txt", meta)
        zf.writestr("GIT_LOG.txt", gitlog)
        zf.writestr("GIT_STATUS.txt", status)
        for path, arc in items:
            zf.write(path, arc)

    # ---- 二次禁含扫描（直接读 zip 条目）----
    violations: list[str] = []
    with zipfile.ZipFile(OUT) as zf:
        names = zf.namelist()
        for n in names:
            low = n.lower()
            if any(h in low for h in FORBIDDEN_PATH_HINTS):
                violations.append(f"path-hint: {n}")
            if Path(n).suffix.lower() in EXCLUDE_SUFFIXES:
                violations.append(f"forbidden-suffix: {n}")
            if zf.getinfo(n).file_size > MAX_BYTES:
                violations.append(f"oversize {zf.getinfo(n).file_size}: {n}")

    print(f"交接包: {OUT}")
    print(f"条目数: {len(names)}")
    if violations:
        print("禁含扫描发现违规：")
        for v in violations:
            print("  [VIOLATION]", v)
        return 1
    print("禁含扫描：PASS（无图片/模型/db/config.local/DataRoot，无超大条目）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
