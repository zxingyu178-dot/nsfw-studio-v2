#!/usr/bin/env python3
"""W4.1 Registry / Agent 提交包校验器（只读）。

用法：
    python scripts/validate_registry.py
    python scripts/validate_registry.py --strict
    python scripts/validate_registry.py --submission agent_submissions/sub_xxx
    python scripts/validate_registry.py --json

退出码：0=无 error；1=存在 error；2=参数/路径错误。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.core.config import load_settings  # noqa: E402
from app.services import registry_validator  # noqa: E402
from app.services.model_registry_service import ModelRegistryService  # noqa: E402
from app.services.workflow_registry_service import WorkflowRegistryService  # noqa: E402

SUBMISSION_KIND = {
    "model": "model",
    "workflow": "workflow",
    "prompt": "prompt",
    "asset_import": "asset",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_registry(registry_root: Path) -> dict:
    settings = load_settings()
    models = ModelRegistryService(settings, registry_root=registry_root)
    workflows = WorkflowRegistryService(settings, registry_root=registry_root, model_registry=models)
    return workflows.validate_all()


def validate_submission(path: Path) -> dict:
    settings = load_settings()
    registry_root = PROJECT_ROOT / "registry"
    models = ModelRegistryService(settings, registry_root=registry_root)
    workflows = WorkflowRegistryService(settings, registry_root=registry_root, model_registry=models)
    issues: list[dict[str, str]] = []
    submission_file = path / "submission.yaml"
    manifest_file = path / "manifest.yaml"
    if not submission_file.is_file():
        return {"checked": 0, "errors": 1, "warnings": 0, "issues": [
            {"level": "error", "code": "SUBMISSION_MISSING", "path": str(path), "message": "缺少 submission.yaml"}
        ]}
    try:
        submission = yaml.safe_load(submission_file.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        return {"checked": 0, "errors": 1, "warnings": 0, "issues": [
            {"level": "error", "code": "SUBMISSION_UNREADABLE", "path": str(submission_file), "message": str(error)}
        ]}
    issues.extend(registry_validator.validate_manifest(registry_root, "submission", submission))
    status = str(submission.get("status") or "")
    kind = SUBMISSION_KIND.get(str(submission.get("submission_type") or ""))
    if kind and manifest_file.is_file():
        try:
            manifest = yaml.safe_load(manifest_file.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError) as error:
            issues.append({"level": "error", "code": "MANIFEST_UNREADABLE", "path": str(manifest_file), "message": str(error)})
            manifest = {}
        if manifest:
            issues.extend(registry_validator.validate_manifest(registry_root, kind, manifest))
            if kind == "model":
                model_id = str(manifest.get("model_id") or "")
                version = str(manifest.get("version") or "")
                if any(
                    item.get("model_id") == model_id and str(item.get("version")) == version
                    for item in models.list_models(include_archived=True)
                ):
                    issues.append({"level": "error", "code": "ID_DUPLICATE", "path": str(manifest_file),
                                   "message": f"模型版本已登记: {model_id}/{version}"})
            if kind == "workflow":
                key = f"{manifest.get('workflow_id')}/{manifest.get('version')}"
                if any(f"{i.get('workflow_id')}/{i.get('version')}" == key for i in workflows.list_workflows(include_history=True)):
                    issues.append({"level": "error", "code": "ID_DUPLICATE", "path": str(manifest_file),
                                   "message": f"工作流版本已登记: {key}"})
    else:
        issues.append({"level": "error", "code": "MANIFEST_MISSING", "path": str(path), "message": "缺少 manifest.yaml 或类型未知"})

    for item in submission.get("files") or []:
        raw = str(item.get("path") or "")
        resolved, error = registry_validator.safe_relative_path(raw, PROJECT_ROOT)
        if error or resolved is None:
            issues.append({"level": "error", "code": "PATH_INVALID", "path": str(submission_file), "message": f"{raw}: {error}"})
            continue
        if not resolved.is_file():
            issues.append({"level": "error", "code": "FILE_MISSING", "path": str(submission_file), "message": f"文件不存在: {raw}"})
            continue
        declared = str(item.get("sha256") or "")
        if declared == "unverified":
            if status == "released":
                issues.append({"level": "error", "code": "SUBMISSION_HASH_UNVERIFIED",
                               "path": str(submission_file), "message": f"released 提交不得使用 unverified: {raw}"})
            else:
                issues.append({"level": "warning", "code": "SUBMISSION_HASH_UNVERIFIED",
                               "path": str(submission_file), "message": f"草稿 Hash 未验证: {raw}"})
        elif declared and _sha256(resolved) != declared:
            issues.append({"level": "error", "code": "SUBMISSION_HASH_MISMATCH",
                           "path": str(submission_file), "message": f"Hash 不一致: {raw}"})
    if status == "released" and "测试" not in str(submission.get("test_method") or "") and "test" not in str(submission.get("test_method") or "").lower():
        issues.append({"level": "warning", "code": "SUBMISSION_TEST_NOTE",
                       "path": str(submission_file), "message": "released 提交缺少明确测试说明"})
    return {
        "checked": 1,
        "errors": sum(1 for i in issues if i["level"] == "error"),
        "warnings": sum(1 for i in issues if i["level"] == "warning"),
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="W4.1 Registry / Agent 提交包校验")
    parser.add_argument("--registry", default=str(PROJECT_ROOT / "registry"), help="Registry 根目录")
    parser.add_argument("--submission", default=None, help="Agent 提交包目录")
    parser.add_argument("--strict", action="store_true", help="warning 也视为失败")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    registry_root = Path(args.registry)
    if not registry_root.is_dir():
        print(f"Registry 目录不存在: {registry_root}", file=sys.stderr)
        return 2
    if args.submission:
        report = validate_submission(Path(args.submission))
    else:
        report = validate_registry(registry_root)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"checked={report['checked']} errors={report['errors']} warnings={report['warnings']}")
        for issue in report["issues"]:
            print(f"[{issue['level'].upper()}] {issue['code']} {issue.get('path')}: {issue['message']}")
    failed = report["errors"] > 0 or (args.strict and report["warnings"] > 0)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
