"""文件系统访问入口：路径一律从 DataRoot 推导，禁止在业务代码中拼路径。

Phase 1 新增 ``resolve_under()``：在已登记目录下安全解析动态子路径
（素材版本目录等），防御路径穿越 / 绝对路径 / ``..`` 逃逸。
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from app.core.config import Settings
from app.core.errors import ValidationError
from app.core.paths import ensure_data_root


class StorageManager:
    """基于 DataRoot 的存储管理器。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.data_root = settings.storage.data_root

    def ensure(self) -> set[str]:
        """确保全部登记目录存在（幂等），返回本次新建的相对路径集合。"""
        return ensure_data_root(self._settings)

    def path(self, relative: str) -> Path:
        """解析 DataRoot 下的登记路径。

        白名单：精确匹配 layout，或为某个登记目录的父目录（如 ``assets``、``images``）。
        """
        layout = self._settings.storage.layout
        if relative in layout or any(item.startswith(f"{relative}/") for item in layout):
            return self.data_root / relative
        raise ValidationError(f"未登记的存储路径: {relative}（请在 configs/storage.yaml 登记）")

    def resolve_under(self, base: str, *segments: str) -> Path:
        """在已登记目录 ``base`` 下安全解析动态子路径。

        规则：
        - 每一段不得为空、不得包含路径分隔符、不得是 ``.`` / ``..``、不得是绝对路径；
        - 解析后必须仍位于 ``base`` 之内（防符号链接/大小写逃逸的最终校验）；
        - 不要求路径已存在（由调用方负责创建）。
        """
        base_path = self.path(base)
        current = base_path
        for segment in segments:
            if (
                not segment
                or segment in (".", "..")
                or "/" in segment
                or "\\" in segment
                or Path(segment).is_absolute()
                or ":" in segment
            ):
                raise ValidationError(f"非法路径段: {segment!r}")
            current = current / segment

        resolved = current.resolve()
        if not resolved.is_relative_to(base_path.resolve()):
            raise ValidationError(f"路径越界: {segment!r}")
        return resolved

    def relative_to_root(self, path: Path) -> str:
        """把 DataRoot 内的绝对路径转为 POSIX 相对路径（入库格式）。"""
        resolved = path.resolve()
        if not resolved.is_relative_to(self.data_root.resolve()):
            raise ValidationError(f"路径不在 DataRoot 内: {path}")
        return resolved.relative_to(self.data_root.resolve()).as_posix()

    def absolutize(self, relative: str) -> Path:
        """把入库的 DataRoot 相对路径还原为绝对路径（拒绝穿越）。"""
        candidate = (self.data_root / relative).resolve()
        if not candidate.is_relative_to(self.data_root.resolve()):
            raise ValidationError(f"路径越界: {relative!r}")
        return candidate

    def atomic_move_into(self, source: Path, dest_dir: Path, filename: str) -> Path:
        """把校验后的临时文件原子移动到正式位置（同一 DataRoot 卷内）。

        数据库尚未提交前调用；若数据库随后失败，调用方负责删除返回的文件。
        """
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename
        os.replace(source, dest)  # 同卷原子
        return dest

    def safe_delete(self, path: Path) -> None:
        """删除文件或空目录树（用于回滚清理），不存在则忽略。"""
        try:
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
        except OSError:
            pass

    @property
    def database_dir(self) -> Path:
        return self.data_root / "database"

    @property
    def backups_dir(self) -> Path:
        return self.data_root / "backups"

    @property
    def temp_dir(self) -> Path:
        return self.data_root / "images" / "temp"

    @property
    def images_dir(self) -> Path:
        return self.data_root / "images"

    @property
    def assets_dir(self) -> Path:
        return self.data_root / "assets"

    @property
    def logs_dir(self) -> Path:
        return self.data_root / "logs"
