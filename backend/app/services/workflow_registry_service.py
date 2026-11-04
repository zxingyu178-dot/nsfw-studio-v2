"""W4.1 Workflow Center：工作流 Manifest 加载、Hash/依赖校验与放行状态投影。

唯一真源：
- 定义/版本/文件/模型依赖/Hash → ``registry/workflows/**/manifest.yaml``（Git）
- 执行文件 → ``workflows/providers/<provider>/<id>/<version>/``
- 放行/Gate 证据 → ``workflows/release_manifest.yaml``
- 默认 binding 选择 → ``configs/workflow.yaml``

本服务不重写现有执行链；``/api/v1/modules`` 与 Job 解析仍使用
``resolve_workflow_modules``，本服务只负责「注册中心」的读取与校验。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.core.config import Settings
from app.core.resource_hash import file_hash_pair
from app.engine.release import release_status
from app.services import registry_validator
from app.services.model_registry_service import ModelRegistryService

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_ROOT = PROJECT_ROOT / "registry"
WORKFLOWS_ROOT = REGISTRY_ROOT / "workflows"
HISTORY_DIR = "_history"


class WorkflowRegistryService:
    def __init__(
        self,
        settings: Settings,
        *,
        registry_root: Path | None = None,
        model_registry: ModelRegistryService | None = None,
    ) -> None:
        self.settings = settings
        self.registry_root = Path(registry_root) if registry_root else REGISTRY_ROOT
        self.workflows_root = self.registry_root / "workflows"
        self.project_root = self.workflows_root.parents[1] if registry_root else PROJECT_ROOT
        self.models = model_registry or ModelRegistryService(settings, registry_root=self.registry_root)

    # ===== 读取 =====
    def _manifest_paths(self) -> list[tuple[Path, bool]]:
        paths: list[tuple[Path, bool]] = []
        if not self.workflows_root.is_dir():
            return paths
        for path in sorted(self.workflows_root.glob("*/*/manifest.yaml")):
            if path.parent.parent.name == HISTORY_DIR:
                continue
            paths.append((path, False))
        history = self.workflows_root / HISTORY_DIR
        if history.is_dir():
            for path in sorted(history.glob("*/*/manifest.yaml")):
                paths.append((path, True))
        return paths

    def _load_one(self, path: Path, archived: bool) -> dict[str, Any]:
        manifest = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        workflow_id = str(manifest.get("workflow_id") or "")
        version = str(manifest.get("version") or "")
        try:
            manifest_path = path.relative_to(self.project_root).as_posix()
        except ValueError:
            manifest_path = str(path)
        return {
            **manifest,
            "archived": archived,
            "manifest_path": manifest_path,
            "registry_key": f"{workflow_id}/{version}",
        }

    def list_workflows(self, *, include_history: bool = False) -> list[dict[str, Any]]:
        result = []
        for path, archived in self._manifest_paths():
            if archived and not include_history:
                continue
            try:
                item = self._load_one(path, archived)
            except (OSError, yaml.YAMLError):
                continue
            result.append(item)
        return sorted(result, key=lambda item: (item.get("workflow_id") or "", item.get("version") or ""))

    def get_workflow(self, workflow_id: str, version: str) -> dict[str, Any]:
        for item in self.list_workflows(include_history=True):
            if item.get("workflow_id") == workflow_id and item.get("version") == version:
                return item
        raise KeyError(f"工作流未登记: {workflow_id}/{version}")

    def default_binding(self, workflow_id: str) -> str | None:
        engine = (self.settings.workflow.raw or {}).get("engine") or {}
        modules = engine.get("modules") or {}
        entry = modules.get(workflow_id) or {}
        return str(entry.get("binding_version") or "") or None

    # ===== 校验 =====
    def _check_files(self, item: dict[str, Any]) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        for field in ("workflow_file", "binding_file"):
            raw = str(item.get(field) or "")
            resolved, error = registry_validator.safe_relative_path(raw, PROJECT_ROOT)
            if error:
                issues.append({"level": "error", "code": "PATH_INVALID", "path": item["manifest_path"],
                               "message": f"{field}: {error}"})
                continue
            if resolved is None or not resolved.is_file():
                issues.append({"level": "error", "code": "FILE_MISSING", "path": item["manifest_path"],
                               "message": f"{field} 不存在: {raw}"})
        return issues

    def _check_hashes(self, item: dict[str, Any]) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        hashes = item.get("hashes") or {}
        checks = (
            ("workflow_file", "workflow_hash", "legacy_raw_workflow_hash"),
            ("binding_file", "binding_hash", "legacy_raw_binding_hash"),
        )
        for file_field, hash_field, legacy_field in checks:
            resolved, error = registry_validator.safe_relative_path(str(item.get(file_field) or ""), PROJECT_ROOT)
            if error or resolved is None or not resolved.is_file():
                continue
            actual = file_hash_pair(resolved)
            expected = str(hashes.get(hash_field) or "")
            if actual["lf"] != expected:
                issues.append({
                    "level": "error", "code": "HASH_MISMATCH", "path": item["manifest_path"],
                    "message": f"{hash_field}: manifest={expected} 实际LF={actual['lf']}",
                })
            legacy = [str(x) for x in (hashes.get(legacy_field) or [])]
            if actual["raw"] != actual["lf"] and actual["raw"] not in legacy:
                issues.append({
                    "level": "warning", "code": "LEGACY_HASH_NOT_RECORDED", "path": item["manifest_path"],
                    "message": f"{hash_field}: 当前树 raw={actual['raw']} 未出现在 {legacy_field}",
                })
        return issues

    def _check_models(self, item: dict[str, Any]) -> list[dict[str, str]]:
        issues: list[dict[str, str]] = []
        released = str(item.get("release_status") or "") == "released"
        for dependency in item.get("model_dependencies") or []:
            model_id = str(dependency.get("model_id") or "")
            try:
                model = self.models.get_model(model_id)
            except KeyError:
                issues.append({
                    "level": "error", "code": "MODEL_DEPENDENCY_UNKNOWN",
                    "path": item["manifest_path"], "message": f"未登记模型 {model_id}",
                })
                continue
            status = str(model.get("status") or "")
            if released and status != "released":
                issues.append({
                    "level": "error", "code": "MODEL_DEPENDENCY_NOT_RELEASED",
                    "path": item["manifest_path"], "message": f"{model_id} 状态={status}",
                })
            elif status == "archived":
                issues.append({
                    "level": "warning", "code": "MODEL_DEPENDENCY_ARCHIVED",
                    "path": item["manifest_path"], "message": f"{model_id} 已归档（仅历史兼容）",
                })
        return issues

    def validation_issues(self, item: dict[str, Any]) -> list[dict[str, str]]:
        manifest = {
            key: value for key, value in item.items()
            if key not in ("archived", "manifest_path", "registry_key")
        }
        issues = registry_validator.validate_manifest(self.registry_root, "workflow", manifest)
        issues = [{**i, "path": f"{item['manifest_path']}:{i['path']}"} for i in issues]
        # 已归档工作流的执行文件已移出项目目录，只校验定义与模型登记，不要求活动文件存在。
        if not item.get("archived"):
            issues.extend(self._check_files(item))
            issues.extend(self._check_hashes(item))
        issues.extend(self._check_models(item))
        return issues

    def runtime_status(self, item: dict[str, Any]) -> dict[str, Any]:
        issues = self.validation_issues(item)
        binding_valid = not any(i["level"] == "error" and i["code"].startswith(("HASH_", "FILE_", "PATH_")) for i in issues)
        registered = True
        release = release_status(
            str(item.get("workflow_id") or ""),
            str(item.get("version") or ""),
            binding_valid=binding_valid,
            registered=registered,
        )
        return {
            "binding_valid": binding_valid,
            "issues": issues,
            "release": release,
            "hash_algorithm": (item.get("hashes") or {}).get("algorithm"),
        }

    def active_workflows(self) -> list[dict[str, Any]]:
        result = []
        for item in self.list_workflows(include_history=False):
            status = self.runtime_status(item)
            result.append({**item, **status})
        return result

    def validate_all(self) -> dict[str, Any]:
        issues: list[dict[str, str]] = []
        checked = 0
        seen: set[str] = set()
        for path, archived in self._manifest_paths():
            checked += 1
            try:
                item = self._load_one(path, archived)
            except (OSError, yaml.YAMLError) as error:
                issues.append({"level": "error", "code": "MANIFEST_UNREADABLE", "path": str(path), "message": str(error)})
                continue
            key = item["registry_key"]
            if key in seen:
                issues.append({"level": "error", "code": "DUPLICATE_WORKFLOW_VERSION", "path": item["manifest_path"],
                               "message": f"重复注册 {key}"})
            seen.add(key)
            issues.extend(self.validation_issues(item))
        model_report = self.models.validate_all()
        issues.extend(model_report["issues"])
        return {"checked": checked + model_report["checked"], "errors": sum(1 for i in issues if i["level"] == "error"),
                "warnings": sum(1 for i in issues if i["level"] == "warning"), "issues": issues}
