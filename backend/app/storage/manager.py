"""文件系统访问入口：路径一律从 DataRoot 推导，禁止在业务代码中拼路径。"""
from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.core.paths import ensure_data_root


class StorageManager:
    """基于 DataRoot 的存储管理器。

    Phase 0 提供：目录清单访问、白名单路径解析、布局确保。
    Phase 1 将增加：文件落盘、缩略图、缓存清理等能力。
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.data_root = settings.storage.data_root

    def ensure(self) -> set[str]:
        """确保全部登记目录存在（幂等），返回本次新建的相对路径集合。"""
        return ensure_data_root(self._settings)

    def path(self, relative: str) -> Path:
        """解析 DataRoot 下的登记路径（白名单校验，防止越界）。"""
        if relative not in self._settings.storage.layout:
            raise KeyError(f"未登记的存储路径: {relative}（请在 configs/storage.yaml 登记）")
        return self.data_root / relative

    @property
    def database_dir(self) -> Path:
        return self.data_root / "database"

    @property
    def backups_dir(self) -> Path:
        return self.data_root / "backups"

    @property
    def images_dir(self) -> Path:
        return self.data_root / "images"

    @property
    def assets_dir(self) -> Path:
        return self.data_root / "assets"

    @property
    def logs_dir(self) -> Path:
        return self.data_root / "logs"
