"""PoseGenerateModule — Qwen-Image 2.1 姿势生成模块（v1）。

角色参考图 + VNCCS 姿势预览图 → ``TextEncodeQwenImage21`` 两张参考图条件 →
``KSampler(er_sde + beta)`` 生成。姿势库直接读取
``ComfyUI_VNCCS_Utils/PoseLibrary``，不使用 ``VNCCS_PoseStudio`` 节点的前端实时捕获
（该节点在无浏览器时无法 headless 执行）。

binding 目录：``workflows/providers/comfyui/pose_generate/v1/``。
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from PIL import Image

from app.core.config import load_settings
from app.engine.base import EngineAdapter, EngineBindingRef, EngineError, EngineJobRequest
from app.workflows.base import (
    InputImageRef,
    InputSlotSpec,
    JobRequestContext,
    ModuleCapabilities,
    ParameterSpec,
    WorkflowInput,
    WorkflowModule,
    WorkflowOutput,
    WorkflowValidation,
)

SIZE_MIN = 64
SIZE_MAX = 4096
SEED_MAX = 2147483647
RESOLUTION_MIN = 512
RESOLUTION_MAX = 2048
RESOLUTION_DEFAULT = 1024

POSE_LIBRARY_ENV = "NSFW_STUDIO_POSE_LIBRARY_DIR"
PREVIEW_SUFFIXES = (".webp", ".png", ".jpg", ".jpeg")
LOCAL_REPOSITORY = "local_user_poses"
RESERVED_LIBRARY_JSON = {"repositories.user.json", "pose_library.json"}


@dataclass(frozen=True)
class PoseEntry:
    """PoseLibrary 中一个可用姿势（必须有预览图）。"""

    key: str  # "<repo-slug>/<category-slug>/<pose-slug>"，唯一
    alias: str | None  # 同名姿势全局唯一时的 "<pose-slug>"
    name: str
    category: str
    repo: str
    json_path: Path
    preview_path: Path


def _slug(value: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in str(value).lower()).split())


def _coerce_int(raw: Any) -> int | None:
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if isinstance(raw, float) and raw != value:
        return None
    return value


def _default_binding(module: "PoseGenerateModule") -> EngineBindingRef:
    return EngineBindingRef(
        module_id=module.module_id,
        module_version=module.module_version,
        provider="unbound",
        binding_version="v1",
    )


class PoseGenerateModule(WorkflowModule):
    """姿势生成：参考图 + VNCCS 姿势预览 → 保持角色的指定姿势。"""

    module_id = "pose_generate"
    module_version = "v1"

    def __init__(self, pose_library_dir: Path | None = None,
                 poll_interval_seconds: float = 0.2) -> None:
        self._pose_library_dir = Path(pose_library_dir) if pose_library_dir else None
        self._poll_interval = poll_interval_seconds

    # ===== 姿势库 =====
    def _resolve_pose_library_dir(self) -> Path | None:
        if self._pose_library_dir is not None:
            return self._pose_library_dir
        env_dir = os.environ.get(POSE_LIBRARY_ENV)
        if env_dir:
            return Path(env_dir)
        try:
            raw = load_settings().comfyui.get("pose_library_dir")
        except (OSError, ValueError):
            return None
        return Path(str(raw)) if raw else None

    def _scan_poses(self) -> list[PoseEntry]:
        library = self._resolve_pose_library_dir()
        if library is None or not library.is_dir():
            return []
        raw_entries: list[tuple[str, str, str, Path, Path]] = []

        local_root = library / LOCAL_REPOSITORY
        if local_root.is_dir():
            for json_path in local_root.rglob("*.json"):
                if json_path.parent == local_root and json_path.name in RESERVED_LIBRARY_JSON:
                    continue
                category = json_path.parent.name if json_path.parent != local_root else "Uncategorized"
                preview = self._find_preview(json_path)
                if preview is not None:
                    raw_entries.append((LOCAL_REPOSITORY, category, json_path.stem, json_path, preview))

        for repo_dir in sorted(library.iterdir()):
            if not repo_dir.is_dir() or repo_dir.name in {LOCAL_REPOSITORY, ".downloads"}:
                continue
            poses_dir = repo_dir / "poses"
            if not poses_dir.is_dir():
                continue
            for json_path in poses_dir.rglob("*.json"):
                preview = self._find_preview(json_path)
                if preview is not None:
                    raw_entries.append((repo_dir.name, json_path.parent.name, json_path.stem,
                                        json_path, preview))

        counts: dict[str, int] = {}
        for _repo, _category, name, _json, _preview in raw_entries:
            slug = _slug(name)
            counts[slug] = counts.get(slug, 0) + 1

        used_keys: set[str] = set()
        entries: list[PoseEntry] = []
        for repo, category, name, json_path, preview in raw_entries:
            base_key = f"{_slug(repo)}/{_slug(category)}/{_slug(name)}"
            key = base_key
            suffix = 2
            while key in used_keys:
                key = f"{base_key}-{suffix}"
                suffix += 1
            used_keys.add(key)
            alias = _slug(name) if counts.get(_slug(name), 0) == 1 else None
            entries.append(PoseEntry(
                key=key, alias=alias, name=name, category=category,
                repo=repo, json_path=json_path, preview_path=preview,
            ))
        return sorted(entries, key=lambda item: item.key)

    @staticmethod
    def _find_preview(json_path: Path) -> Path | None:
        try:
            siblings = list(json_path.parent.iterdir())
        except OSError:
            return None
        candidates = [
            path for path in siblings
            if path.is_file() and path.stem.casefold() == json_path.stem.casefold()
            and path.suffix.lower() in PREVIEW_SUFFIXES
        ]
        if not candidates:
            return None
        return sorted(candidates, key=lambda path: PREVIEW_SUFFIXES.index(path.suffix.lower()))[0]

    def _resolve_pose(self, value: str) -> PoseEntry:
        entries = self._scan_poses()
        wanted = str(value or "").strip()
        if not wanted:
            raise EngineError("WORKFLOW_ERROR", "pose_generate 需要 pose（姿势库键名）")
        wanted_slug = _slug(wanted)
        for entry in entries:
            if entry.key == wanted or entry.key == wanted_slug:
                return entry
        name_hits = [entry for entry in entries if _slug(entry.name) == wanted_slug]
        if len(name_hits) == 1:
            return name_hits[0]
        if len(name_hits) > 1:
            keys = ", ".join(entry.key for entry in name_hits[:6])
            raise EngineError("WORKFLOW_ERROR", f"姿势名不唯一，请使用完整键名: {keys}")
        library = self._resolve_pose_library_dir()
        if library is None or not library.is_dir():
            raise EngineError(
                "WORKFLOW_ERROR",
                f"姿势库不可用：请配置 comfyui.pose_library_dir 或 {POSE_LIBRARY_ENV}",
            )
        raise EngineError("WORKFLOW_ERROR", f"姿势不存在: {wanted}")

    # ===== 能力声明 =====
    def capabilities(self) -> ModuleCapabilities:
        poses = self._scan_poses()
        return ModuleCapabilities(
            module_id=self.module_id,
            module_version=self.module_version,
            title="姿势生成",
            description="角色参考图 + VNCCS 姿势 + Qwen-Image 2.1 NSFW LoRA → 保持角色的指定姿势",
            parameters=(
                ParameterSpec("input_image", "image", required=True,
                              description="角色参考图（来自 Studio 图库）"),
                ParameterSpec(
                    "pose", "string", required=True, configurable=True, title="姿势",
                    enum_values=tuple(entry.key for entry in poses),
                    description="VNCCS 姿势库键名（repo/category/name；同名唯一时可用短名）",
                ),
                ParameterSpec("positive_prompt", "string", required=True),
                ParameterSpec("negative_prompt", "string", default=""),
                ParameterSpec(
                    "resolution", "int", default=RESOLUTION_DEFAULT,
                    min=RESOLUTION_MIN, max=RESOLUTION_MAX, step=64, configurable=True,
                    title="参考分辨率",
                    description=f"参考图重采样基准（{RESOLUTION_MIN}~{RESOLUTION_MAX}）",
                ),
                ParameterSpec("seed", "int", required=True, description=f"0~{SEED_MAX}（每张独立）"),
            ),
            uses_seed=True,
            input_kind="image",
            input_required=True,
            input_role="reference",
            output_kind="original",
            parent_policy="input_image",
            output_cardinality=1,
            size_mode="explicit",
            allowed_job_kinds=("generate",),
            can_start_from_image=True,
            is_generative=True,
            input_slots=(
                InputSlotSpec("reference", required=True, max_count=1,
                              description="角色参考图（人物/主体）"),
            ),
            recommended_timeout_seconds=7200.0,
        )

    # ===== config =====
    def validate_config(self, config: Mapping[str, Any]) -> WorkflowValidation:
        errors: list[str] = []
        unknown = set(config.keys()) - {"pose", "resolution"}
        if unknown:
            errors.append(f"未知配置项: {', '.join(sorted(unknown))}")
        try:
            self._resolve_pose(str(config.get("pose") or ""))
        except EngineError as error:
            errors.append(error.message)
        resolution = _coerce_int(config.get("resolution", RESOLUTION_DEFAULT))
        if resolution is None:
            errors.append("resolution 必须为整数")
        elif not RESOLUTION_MIN <= resolution <= RESOLUTION_MAX:
            errors.append(f"resolution 取值范围为 {RESOLUTION_MIN}~{RESOLUTION_MAX}")
        return WorkflowValidation(ok=not errors, errors=tuple(errors))

    # ===== 标准输入 =====
    def build_input(self, context: JobRequestContext) -> WorkflowInput:
        image = context.input_image
        if not isinstance(image, InputImageRef):
            raise EngineError("WORKFLOW_ERROR", "pose_generate 需要角色参考图（input_image）")
        if context.seed is None:
            raise EngineError("WORKFLOW_ERROR", "pose_generate 需要 Seed（uses_seed=true）")
        settings: dict[str, Any] = dict(context.generation_settings or {})
        return WorkflowInput(values={
            "input_image": image,
            "pose": str(context.module_config.get("pose") or ""),
            "positive_prompt": context.positive_prompt,
            "negative_prompt": context.negative_prompt,
            "width": int(settings.get("width", 1024)),
            "height": int(settings.get("height", 1024)),
            "resolution": _coerce_int(context.module_config.get("resolution")) or RESOLUTION_DEFAULT,
            "seed": int(context.seed),
        })

    def validate_input(self, payload: WorkflowInput) -> WorkflowValidation:
        errors: list[str] = []
        values = payload.values
        if not isinstance(values.get("input_image"), InputImageRef):
            errors.append("input_image 必须为 InputImageRef（已有参考图）")
        if not str(values.get("pose") or "").strip():
            errors.append("pose 不能为空")
        for key in ("width", "height"):
            size = _coerce_int(values.get(key, 1024))
            if size is None or not SIZE_MIN <= size <= SIZE_MAX:
                errors.append(f"{key} 取值范围为 {SIZE_MIN}~{SIZE_MAX}")
        resolution = _coerce_int(values.get("resolution", RESOLUTION_DEFAULT))
        if resolution is None or not RESOLUTION_MIN <= resolution <= RESOLUTION_MAX:
            errors.append(f"resolution 取值范围为 {RESOLUTION_MIN}~{RESOLUTION_MAX}")
        seed = _coerce_int(values.get("seed", -1))
        if seed is None or not 0 <= seed <= SEED_MAX:
            errors.append(f"seed 取值范围为 0~{SEED_MAX}")
        return WorkflowValidation(ok=not errors, errors=tuple(errors))

    # ===== 引擎侧输入准备 =====
    async def prepare_inputs(self, context: JobRequestContext,
                             engine: EngineAdapter) -> Mapping[str, Any]:
        image = context.input_image
        if not isinstance(image, InputImageRef):
            raise EngineError("WORKFLOW_ERROR", "pose_generate 需要角色参考图（input_image）")
        entry = self._resolve_pose(str(context.module_config.get("pose") or ""))
        character_name = await engine.upload_input_image(
            image_id=image.image_id, file_name=image.file_name, data=image.data,
        )
        try:
            with Image.open(io.BytesIO(entry.preview_path.read_bytes())) as source:
                buffer = io.BytesIO()
                source.convert("RGB").save(buffer, format="PNG")
        except (OSError, ValueError) as error:
            raise EngineError("WORKFLOW_ERROR",
                              f"姿势预览图不可用: {entry.preview_path}: {error}") from error
        pose_id = f"poseasset_{hashlib.sha1(entry.key.encode('utf-8')).hexdigest()[:16]}"
        pose_name = await engine.upload_input_image(
            image_id=pose_id, file_name=f"{_slug(entry.name) or 'pose'}.png",
            data=buffer.getvalue(),
        )
        return {"input_image_name": character_name, "pose_image_name": pose_name}

    # ===== 引擎请求 =====
    def build_engine_request(self, context: JobRequestContext,
                             prepared: Mapping[str, Any] | None = None) -> EngineJobRequest:
        payload = self.build_input(context)
        validation = self.validate_input(payload)
        if not validation.ok:
            raise EngineError("WORKFLOW_ERROR", f"模块输入校验失败: {'; '.join(validation.errors)}")
        prepared = prepared or {}
        input_image_name = prepared.get("input_image_name")
        pose_image_name = prepared.get("pose_image_name")
        if not input_image_name or not pose_image_name:
            raise EngineError(
                "WORKFLOW_ERROR",
                "pose_generate 图片未准备（prepared.input_image_name / pose_image_name）",
            )
        values = payload.values
        return EngineJobRequest(
            binding=context.binding or _default_binding(self),
            parameters={
                "input_image": input_image_name,
                "pose_image": pose_image_name,
                "positive_prompt": values["positive_prompt"],
                "negative_prompt": values["negative_prompt"],
                "width": values["width"],
                "height": values["height"],
                "resolution": values["resolution"],
                "seed": values["seed"],
            },
            metadata=dict(context.metadata or {}),
        )

    # ===== 完整执行 =====
    async def execute(self, payload: WorkflowInput, engine: EngineAdapter,
                      *, binding: EngineBindingRef | None = None) -> WorkflowOutput:
        validation = self.validate_input(payload)
        if not validation.ok:
            raise EngineError("WORKFLOW_ERROR", f"模块输入校验失败: {'; '.join(validation.errors)}")
        context = JobRequestContext(
            input_image=payload.values.get("input_image"),
            positive_prompt=str(payload.values.get("positive_prompt") or ""),
            negative_prompt=str(payload.values.get("negative_prompt") or ""),
            seed=int(payload.values["seed"]),
            generation_settings={"width": payload.values.get("width"),
                                 "height": payload.values.get("height")},
            module_config={"pose": payload.values.get("pose"),
                           "resolution": payload.values.get("resolution")},
            binding=binding or _default_binding(self),
        )
        prepared = await self.prepare_inputs(context, engine)
        engine_job_id = await engine.submit_job(self.build_engine_request(context, prepared))
        while True:
            status = await engine.get_job_status(engine_job_id)
            if status.state == "succeeded":
                files = await engine.get_job_outputs(engine_job_id)
                if not files:
                    raise EngineError("OUTPUT_MISSING", "引擎报告成功但没有输出文件")
                return WorkflowOutput(artifacts={"image": files[0].filename},
                                      metadata={"engine_job_id": engine_job_id})
            if status.state in ("failed", "canceled"):
                raise EngineError(status.error_type or "UNKNOWN_ENGINE_ERROR",
                                  status.message or f"引擎任务未成功: {status.state}")
            if status.state == "unknown":
                raise EngineError("UNKNOWN_ENGINE_ERROR", "engine lost track of job")
            await asyncio.sleep(self._poll_interval)
