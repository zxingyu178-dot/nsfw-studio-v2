"""W4.1 Model Center：模型 Manifest 加载、校验、文件解析与安装状态。

唯一真源：
- 定义/版本/文件/SHA256 → ``registry/models/**/model.yaml``（Git）
- 实际安装状态 → 本机搜索根扫描（machine-local config）+ 可选 SHA256 校验
- 数据库不复制模型定义；Job 只保存模型快照（引用 model_id/version/sha256）
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from app.core.config import Settings
from app.services import registry_validator

PROJECT_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_ROOT = PROJECT_ROOT / "registry"
MODELS_ROOT = REGISTRY_ROOT / "models"
ARCHIVE_DIR = "_archive"

# binding requirements.models.type → 逻辑模型目录（registry 归一）
# 注意：ComfyUI 的 GGUF 探针目录是 unet_gguf，但物理文件在 diffusion_models；
# registry 只认 manifest 的 folder，探针目录映射在 runtime_preflight 内单独维护。
FOLDER_ALIASES = {
    "diffusion_models": "diffusion_models",
    "unet": "diffusion_models",
    "unet_gguf": "diffusion_models",
    "text_encoders": "text_encoders",
    "clip": "text_encoders",
    "vae": "vae",
    "loras": "loras",
    "checkpoints": "checkpoints",
    "upscale_models": "upscale_models",
}


@dataclass
class ModelRecord:
    manifest: dict[str, Any]
    path: Path
    archived: bool = False

    @property
    def model_id(self) -> str:
        return str(self.manifest.get("model_id") or "")

    @property
    def version(self) -> str:
        return str(self.manifest.get("version") or "")


@dataclass
class InstallStatus:
    status: str  # installed / missing / archived / unknown
    installed: bool | None
    missing_files: list[dict[str, str]] = field(default_factory=list)
    size_mismatch: list[dict[str, Any]] = field(default_factory=list)
    sha256_mismatch: list[dict[str, Any]] = field(default_factory=list)
    resolved_paths: list[str] = field(default_factory=list)


class ModelRegistryService:
    def __init__(self, settings: Settings, *, registry_root: Path | None = None) -> None:
        self.settings = settings
        self.registry_root = Path(registry_root) if registry_root else REGISTRY_ROOT
        self.models_root = self.registry_root / "models"
        self._cache: dict[str, ModelRecord] | None = None
        self._hash_cache_path = settings.storage.data_root / "cache" / "registry_model_hashes.json"

    # ===== Manifest =====
    def _iter_manifest_paths(self) -> list[tuple[Path, bool]]:
        paths: list[tuple[Path, bool]] = []
        if not self.models_root.is_dir():
            return paths
        for path in sorted(self.models_root.glob("*/model.yaml")):
            paths.append((path, False))
        archive = self.models_root / ARCHIVE_DIR
        if archive.is_dir():
            for path in sorted(archive.glob("*/model.yaml")):
                paths.append((path, True))
        return paths

    def _load_all(self) -> dict[str, ModelRecord]:
        if self._cache is not None:
            return self._cache
        records: dict[str, ModelRecord] = {}
        for path, archived in self._iter_manifest_paths():
            try:
                manifest = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError) as error:
                raise ValueError(f"模型 Manifest 无法读取: {path}: {error}") from error
            record = ModelRecord(manifest=manifest, path=path, archived=archived)
            if record.model_id in records:
                raise ValueError(f"模型 ID 重复: {record.model_id} ({path})")
            records[record.model_id] = record
        self._cache = records
        return records

    def refresh(self) -> None:
        self._cache = None

    def list_models(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        result = []
        for record in self._load_all().values():
            if record.archived and not include_archived:
                continue
            result.append({
                **record.manifest,
                "archived": record.archived,
                "manifest_path": str(record.path.relative_to(PROJECT_ROOT).as_posix()),
            })
        return sorted(result, key=lambda item: (item.get("status") != "released", item.get("model_id") or ""))

    def get_model(self, model_id: str) -> dict[str, Any]:
        record = self._load_all().get(model_id)
        if record is None:
            raise KeyError(f"模型未登记: {model_id}")
        return record.manifest

    def resolve_file(self, folder: str, filename: str) -> dict[str, Any] | None:
        """按物理目录 + 文件名反查模型 Manifest（用于 binding → model_id）。"""
        target_folder = FOLDER_ALIASES.get(folder, folder)
        for record in self._load_all().values():
            for item in record.manifest.get("files") or []:
                if (
                    FOLDER_ALIASES.get(str(item.get("folder")), str(item.get("folder"))) == target_folder
                    and item.get("filename") == filename
                ):
                    return record.manifest
        return None

    # ===== 本机安装状态 =====
    def _search_roots(self) -> list[Path]:
        roots = self.settings.model_registry.get("search_roots") if self.settings.model_registry else []
        return [Path(str(item)) for item in (roots or [])]

    def _load_hash_cache(self) -> dict[str, Any]:
        try:
            return json.loads(self._hash_cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_hash_cache(self, cache: dict[str, Any]) -> None:
        try:
            self._hash_cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._hash_cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    def install_status(self, model_id: str, *, verify_hash: bool = False) -> InstallStatus:
        manifest = self.get_model(model_id)
        if manifest.get("status") == "archived":
            return InstallStatus(status="archived", installed=None)
        roots = self._search_roots()
        if not roots:
            return InstallStatus(status="unknown", installed=None)
        hash_cache = self._load_hash_cache() if verify_hash else {}
        missing: list[dict[str, str]] = []
        size_mismatch: list[dict[str, Any]] = []
        sha_mismatch: list[dict[str, Any]] = []
        resolved: list[str] = []
        for item in manifest.get("files") or []:
            filename = str(item.get("filename") or "")
            folder = str(item.get("folder") or "")
            found: Path | None = None
            for root in roots:
                candidate = root / folder / filename
                if candidate.is_file():
                    found = candidate
                    break
            if found is None:
                if item.get("required", True):
                    missing.append({"folder": folder, "filename": filename})
                continue
            resolved.append(str(found))
            expected_size = item.get("size_bytes")
            if expected_size and found.stat().st_size != int(expected_size):
                size_mismatch.append({
                    "filename": filename, "expected": int(expected_size), "actual": found.stat().st_size,
                })
            expected_sha = str(item.get("sha256") or "")
            if verify_hash and expected_sha and expected_sha != "unverified":
                key = f"{found}|{found.stat().st_size}|{int(found.stat().st_mtime)}"
                digest = hash_cache.get(key)
                if not digest:
                    h = hashlib.sha256()
                    with found.open("rb") as fh:
                        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                            h.update(chunk)
                    digest = h.hexdigest()
                    hash_cache[key] = digest
                if digest != expected_sha:
                    sha_mismatch.append({"filename": filename, "expected": expected_sha, "actual": digest})
        if verify_hash:
            self._save_hash_cache(hash_cache)
        if missing or size_mismatch or sha_mismatch:
            status = "missing"
        else:
            status = "installed"
        return InstallStatus(
            status=status,
            installed=status == "installed",
            missing_files=missing,
            size_mismatch=size_mismatch,
            sha256_mismatch=sha_mismatch,
            resolved_paths=resolved,
        )

    # ===== binding → 模型快照 =====
    def model_snapshot(self, binding: dict[str, Any]) -> list[dict[str, Any]]:
        """把 binding.requirements.models 解析为稳定 model_id/version/sha256 快照。"""
        requirements = binding.get("requirements") if isinstance(binding.get("requirements"), dict) else {}
        snapshot: list[dict[str, Any]] = []
        for item in requirements.get("models") or []:
            if not isinstance(item, dict):
                continue
            folder = FOLDER_ALIASES.get(str(item.get("type") or item.get("folder") or ""), str(item.get("type") or ""))
            filename = Path(str(item.get("filename") or "")).name
            manifest = self.resolve_file(folder, filename)
            snapshot.append({
                "model_id": manifest.get("model_id") if manifest else None,
                "version": manifest.get("version") if manifest else None,
                "filename": filename,
                "folder": folder,
                "sha256": (
                    next(
                        (f.get("sha256") for f in manifest.get("files") or [] if f.get("filename") == filename),
                        None,
                    ) if manifest else None
                ),
                "registered": manifest is not None,
            })
        return snapshot

    # ===== 校验 =====
    def validate_all(self) -> dict[str, Any]:
        issues: list[dict[str, str]] = []
        checked = 0
        for path, _archived in self._iter_manifest_paths():
            checked += 1
            try:
                manifest = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError) as error:
                issues.append({"level": "error", "code": "MANIFEST_UNREADABLE", "path": str(path), "message": str(error)})
                continue
            for issue in registry_validator.validate_manifest(self.registry_root, "model", manifest):
                issues.append({**issue, "path": f"{path}:{issue['path']}"})
            if manifest.get("status") == "released":
                for item in manifest.get("files") or []:
                    if str(item.get("sha256") or "") == "unverified":
                        issues.append({
                            "level": "error", "code": "MODEL_SHA_UNVERIFIED",
                            "path": str(path), "message": "已发布模型不得使用 unverified SHA256",
                        })
        return {"checked": checked, "errors": sum(1 for i in issues if i["level"] == "error"),
                "warnings": sum(1 for i in issues if i["level"] == "warning"), "issues": issues}
