"""业务逻辑层（Service）。

Phase 0 仅有系统引导；Phase 1 规划：JobService / PromptService / AssetService。
api 层只做 HTTP 编排，业务逻辑一律放这里。
"""
from app.services.system_service import BootstrapReport, bootstrap

__all__ = ["BootstrapReport", "bootstrap"]
