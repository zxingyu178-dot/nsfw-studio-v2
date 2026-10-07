"""NSFW Studio V2 - 构建阶段交接包（Handoff ZIP）。

用法（项目根目录）：
    .venv/Scripts/python scripts/build_handoff.py --phase Phase0

输出：handoff/NSFW_Studio_<Phase>_Handoff.zip
包含：报告文档、DEV_LOG/TASKS/CHANGELOG/TEST_REPORT、Git commit 记录、核心源码
（排除 .venv / node_modules / dist / 数据 / 日志 / 交接包本身）。
"""
from __future__ import annotations

import argparse
import subprocess
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

INCLUDE_DIRS = ["backend", "frontend", "configs", "database", "workflows", "scripts", "tests", "docs"]
INCLUDE_FILES = [
    "README.md",
    "AGENTS.md",
    "pytest.ini",
    ".gitignore",
    "DEV_LOG.md",
    "TASKS.md",
    "CHANGELOG.md",
    "TEST_REPORT.md",
    "frontend/package-lock.json",
]

EXCLUDE_PARTS = {
    ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    ".git", "dist", "coverage", ".idea", ".vscode", "handoff",
}
EXCLUDE_SUFFIXES = {".db", ".sqlite3", ".log", ".pyc"}


def git_log() -> str:
    try:
        return subprocess.run(
            ["git", "log", "--oneline", "--decorate", "--all"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8", check=True,
        ).stdout
    except Exception as exc:  # noqa: BLE001 - 记录失败不阻断打包
        return f"(git log 获取失败: {exc})"


def is_excluded(path: Path) -> bool:
    parts = set(path.parts)
    if parts & EXCLUDE_PARTS:
        return True
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return True
    return False


def add_file(zf: zipfile.ZipFile, path: Path, arcname: str) -> None:
    zf.write(path, arcname)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", default="Phase0", help="阶段名（用于输出文件名）")
    args = parser.parse_args()

    out_dir = PROJECT_ROOT / "handoff"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"NSFW_Studio_{args.phase}_Handoff.zip"

    count = 0
    added: set[str] = set()
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("GIT_COMMITS.txt", git_log())

        for name in INCLUDE_FILES:
            file_path = PROJECT_ROOT / name
            if file_path.is_file():
                add_file(zf, file_path, name)
                added.add(name)
                count += 1

        for dir_name in INCLUDE_DIRS:
            base = PROJECT_ROOT / dir_name
            if not base.is_dir():
                continue
            for path in sorted(base.rglob("*")):
                if not path.is_file():
                    continue
                arcname = path.relative_to(PROJECT_ROOT).as_posix()
                if arcname in added or is_excluded(path):
                    continue
                add_file(zf, path, arcname)
                added.add(arcname)
                count += 1

    print(f"交接包已生成: {out_path}（{count} 个文件）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
