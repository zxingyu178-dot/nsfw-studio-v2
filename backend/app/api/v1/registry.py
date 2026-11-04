"""W4.1 Registry API：Model Center / Workflow Center 只读投影。

不替代现有业务 API：工作台仍读取 /api/v1/modules；本组端点用于资源管理、
诊断、Agent 提交审核与验收。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_storage
from app.core.config import Settings
from app.models import Image, ImageVariant
from app.services import asset_query_service
from app.services.model_registry_service import ModelRegistryService
from app.services.workflow_registry_service import WorkflowRegistryService
from app.storage.manager import StorageManager

router = APIRouter(prefix="/registry", tags=["registry"])


def _services(request: Request) -> tuple[ModelRegistryService, WorkflowRegistryService]:
    settings: Settings = request.app.state.settings
    models = ModelRegistryService(settings)
    return models, WorkflowRegistryService(settings, model_registry=models)


@router.get("/summary", summary="资源注册中心摘要（模型/工作流/校验）")
def registry_summary(request: Request) -> dict:
    models, workflows = _services(request)
    report = workflows.validate_all()
    active = workflows.active_workflows()
    return {
        "models": {
            "active": len(models.list_models(include_archived=False)),
            "archived": len(models.list_models(include_archived=True)) - len(models.list_models(include_archived=False)),
        },
        "workflows": {
            "active": [] if report["errors"] else [item.get("workflow_id") for item in active],
            "defaults": {item.get("workflow_id"): item.get("version") for item in active},
        },
        "validation": {"checked": report["checked"], "errors": report["errors"], "warnings": report["warnings"]},
    }


@router.get("/models", summary="模型登记与安装状态")
def list_models(
    request: Request,
    include_archived: bool = Query(default=False),
    verify_hash: bool = Query(default=False, description="是否逐文件计算 SHA256（GB 级文件会较慢）"),
) -> dict:
    models, _workflows = _services(request)
    items = []
    for manifest in models.list_models(include_archived=include_archived):
        status = models.install_status(manifest["model_id"], verify_hash=verify_hash)
        items.append({
            **manifest,
            "install": {
                "status": status.status,
                "installed": status.installed,
                "missing_files": status.missing_files,
                "size_mismatch": status.size_mismatch,
                "sha256_mismatch": status.sha256_mismatch,
            },
        })
    return {"items": items, "verify_hash": verify_hash}


@router.get("/workflows", summary="工作流登记、Hash 与放行状态")
def list_workflows(
    request: Request,
    include_history: bool = Query(default=False),
) -> dict:
    _models, workflows = _services(request)
    items = workflows.list_workflows(include_history=include_history)
    result = []
    for item in items:
        status = workflows.runtime_status(item)
        result.append({
            **item,
            "validation": {
                "binding_valid": status["binding_valid"],
                "issues": status["issues"],
                "release": status["release"],
            },
        })
    return {"items": result, "include_history": include_history}


@router.get("/validate", summary="Registry 全量校验报告")
def validate_registry(request: Request) -> dict:
    _models, workflows = _services(request)
    return workflows.validate_all()


@router.get("/assets", summary="Image Asset Center 统计（W4.1）")
def asset_stats(
    session: Session = Depends(get_session),
    storage: StorageManager = Depends(get_storage),
    check_files: bool = Query(default=True, description="逐条检查图片/变体文件是否存在"),
) -> dict:
    return asset_query_service.stats(session, storage, check_files=check_files)


@router.get("/assets/orphans", summary="孤立图片文件（只报告，不删除）")
def asset_orphans(
    session: Session = Depends(get_session),
    storage: StorageManager = Depends(get_storage),
) -> dict:
    known = set(session.execute(select(Image.file_path)).scalars())
    known.update(session.execute(select(ImageVariant.path)).scalars())
    orphans = asset_query_service.orphan_files(storage, known)
    return {"total": len(orphans), "bytes": sum(item["size"] for item in orphans), "items": orphans[:200]}
