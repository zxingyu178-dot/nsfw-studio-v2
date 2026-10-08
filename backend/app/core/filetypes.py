"""上传文件类型校验（Phase 1 规范 §二十）。

第一版仅允许 jpg / jpeg / png / webp；通过扩展名 + magic bytes 双重校验，
不依赖第三方图像库。
"""
from __future__ import annotations

from pathlib import Path

from app.core.errors import FileValidationError

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

_FORMAT_BY_EXTENSION = {".jpg": "jpeg", ".jpeg": "jpeg", ".png": "png", ".webp": "webp"}
_MIME_BY_FORMAT = {"jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp"}


def sniff_image_format(data: bytes) -> str | None:
    """按 magic bytes 识别图片格式；无法识别返回 None。"""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
        return "webp"
    return None


def validate_image_upload(filename: str | None, content_type: str | None, data: bytes) -> str:
    """校验上传图片（扩展名 / MIME / magic bytes / 大小），返回规范化扩展名（如 ".png"）。

    任何不合法情况抛出 FileValidationError（统一错误格式）。
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise FileValidationError(f"文件超过大小上限（{MAX_UPLOAD_BYTES // (1024 * 1024)} MB）", code="FILE_TOO_LARGE")
    if not data:
        raise FileValidationError("文件内容为空")

    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise FileValidationError(f"不支持的文件扩展名: {suffix or '(无)'}，仅允许 jpg/jpeg/png/webp", code="UNSUPPORTED_FILE_TYPE")

    if content_type is not None and content_type != "application/octet-stream":
        if content_type not in ALLOWED_MIME_TYPES:
            raise FileValidationError(f"不支持的 MIME 类型: {content_type}", code="UNSUPPORTED_FILE_TYPE")

    fmt = sniff_image_format(data)
    expected = _FORMAT_BY_EXTENSION[suffix]
    if fmt != expected:
        raise FileValidationError("文件内容与扩展名不符（magic bytes 校验失败）", code="INVALID_FILE")

    return suffix


def mime_for_suffix(suffix: str) -> str:
    return _MIME_BY_FORMAT.get(suffix.lstrip(".").lower(), "application/octet-stream")


def image_dimensions(data: bytes) -> tuple[int, int] | None:
    """解析 PNG / JPEG / WEBP 像素尺寸（不依赖第三方图像库）；无法解析返回 None。"""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24:
        import struct

        width, height = struct.unpack(">II", data[16:24])
        return int(width), int(height)
    if data[:3] == b"\xff\xd8\xff":
        return _jpeg_dimensions(data)
    if data[:4] == b"RIFF" and len(data) >= 12 and data[8:12] == b"WEBP":
        return _webp_dimensions(data)
    return None


def _webp_dimensions(data: bytes) -> tuple[int, int] | None:
    """WebP 三种容器格式（VP8 有损 / VP8L 无损 / VP8X 扩展）的尺寸解析。"""
    if len(data) < 30:
        return None
    tag = data[12:16]
    if tag == b"VP8 ":  # 有损：帧头内 14-bit 宽高
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return (width, height) if width > 0 and height > 0 else None
    if tag == b"VP8L":  # 无损：签名 0x2F + 14-bit 宽高（各减 1 存储）
        if data[20] != 0x2F:
            return None
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if tag == b"VP8X":  # 扩展：24-bit canvas 宽高（各减 1 存储）
        width = int.from_bytes(data[24:27], "little") + 1
        height = int.from_bytes(data[27:30], "little") + 1
        return width, height
    return None


def sha256_hex(data: bytes) -> str:
    """文件内容 sha256（导入去重与 Recipe 输入图快照使用）。"""
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    import struct

    index = 2
    size = len(data)
    while index + 9 < size:
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:  # 无长度段
            index += 2
            continue
        if index + 4 > size:
            return None
        segment_length = struct.unpack(">H", data[index + 2:index + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):  # SOF0-15
            if index + 9 <= size:
                height, width = struct.unpack(">HH", data[index + 5:index + 9])
                return int(width), int(height)
            return None
        index += 2 + segment_length
    return None
