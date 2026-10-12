"""mobile_main route table 自动守卫（P0 安全）。

断言：mobile_main 只 include mobile/system、mobile/pairing、mobile/images、mobile/review；
**绝不** include jobs / engine_runtime / prompts / recipes / assets / cleanup / modules /
desktop SPA（8000 始终 loopback，Bridge 只暴露审核相关 API）。
"""
from __future__ import annotations

from app.mobile_main import create_mobile_app


def _all_paths(app) -> set[str]:
    """枚举 app 全部路由路径（兼容 FastAPI 懒加载 _IncludedRouter）。"""
    paths: set[str] = set()

    def walk(routes):
        for r in routes:
            path = getattr(r, "path", None)
            if path:
                paths.add(path)
            inner = getattr(r, "routes", None)
            if inner:
                walk(inner)
            included = getattr(r, "original_router", None)
            if included is not None:
                walk(getattr(included, "routes", []))

    walk(app.routes)
    return paths


def test_mobile_route_table_only_audit():
    # 直接构造 app（不进 lifespan，避免连库）；路由在 include_router 时已注册
    from app.core.config import load_settings
    import os, tempfile
    os.environ["NSFW_STUDIO_DATA_ROOT"] = tempfile.mkdtemp()
    application = create_mobile_app(load_settings())
    paths = _all_paths(application)

    # 必须存在的审核端点
    expected_present = {
        "/mobile/system/health",
        "/mobile/pairing/status",
        "/mobile/pairing/verify",
    }
    for p in expected_present:
        assert p in paths, f"缺少审核端点 {p}"

    # 禁止出现的高危/无关模块路径前缀
    forbidden_prefixes = (
        "/jobs", "/api/v1/jobs",
        "/engine", "/api/v1/engine",
        "/prompts", "/api/v1/prompts",
        "/recipes", "/api/v1/recipes",
        "/assets", "/api/v1/assets",
        "/cleanup",
        "/modules", "/api/v1/modules",
        "/api/v1/images",  # Desktop 图库内容（非 /mobile/images）
        "/api/v1/health",
    )
    for p in paths:
        for bad in forbidden_prefixes:
            assert not p.startswith(bad), f"Bridge 不得暴露 {p}（命中禁止前缀 {bad}）"

    # 所有业务路径必须以 /mobile/ 开头
    business = {p for p in paths if not p.startswith(("/docs", "/openapi.json", "/redoc"))}
    for p in business:
        assert p.startswith("/mobile/"), f"Bridge 业务路径必须在 /mobile/ 命名空间: {p}"


def test_mobile_docs_disabled():
    """安全硬化 O2：8767 在 LAN，关闭 /docs /redoc /openapi.json。"""
    from app.core.config import load_settings
    import os, tempfile
    os.environ["NSFW_STUDIO_DATA_ROOT"] = tempfile.mkdtemp()
    application = create_mobile_app(load_settings())
    assert application.docs_url is None
    assert application.redoc_url is None
    assert application.openapi_url is None
    paths = _all_paths(application)
    assert "/docs" not in paths
    assert "/redoc" not in paths
    assert "/openapi.json" not in paths
