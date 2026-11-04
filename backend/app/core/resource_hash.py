"""W4.1 统一资源 Hash（跨平台换行规范化）。

两种算法必须明确区分，禁止互相替代：

- ``raw-bytes-v1``：历史 ``sha256(file_bytes)[:16]``。历史 Binding / 历史 Job
  的执行身份使用它；W4.1 之后仍然必须可验证，否则历史 Job 会全部失效。
- ``lf-normalized-v1``：把 CRLF/CR 统一为 LF 后再算 ``sha256[:16]``。Git 以 LF
  存储 JSON/YAML，因此该值在 dev/部署/CI/Windows/Linux 上稳定，作为 W4.1
  起新 Job 与 Manifest 的标准身份。

只做字节级换行归一，不做缩进/空白/编码改写，保证内容语义不变。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

RAW_ALGORITHM = "raw-bytes-v1"
LF_ALGORITHM = "lf-normalized-v1"
HASH_LENGTH = 16


def normalize_lf_bytes(data: bytes) -> bytes:
    """把 CRLF / 单独 CR 统一为 LF；其它字节保持不变。"""
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def sha256_prefix(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:HASH_LENGTH]


def raw_hash_bytes(data: bytes) -> str:
    """历史算法：原始字节 sha256 前 16 位。"""
    return sha256_prefix(data)


def lf_hash_bytes(data: bytes) -> str:
    """W4.1 标准算法：LF 规范化后 sha256 前 16 位。"""
    return sha256_prefix(normalize_lf_bytes(data))


def file_hash_pair(path: Path) -> dict[str, str]:
    """返回 ``{"raw": ..., "lf": ...}``；调用方负责处理 OSError。"""
    data = Path(path).read_bytes()
    return {"raw": raw_hash_bytes(data), "lf": lf_hash_bytes(data)}


def match_algorithm(ref_value: str | None, raw: str, lf: str) -> str | None:
    """判断引用 Hash 命中的算法；两者都为空/未命中返回 None。

    当 raw == lf（文件本身已是 LF）时优先返回 ``lf-normalized-v1``，
    因为这是 W4.1 的规范算法。
    """
    if not ref_value:
        return None
    if ref_value == lf:
        return LF_ALGORITHM
    if ref_value == raw:
        return RAW_ALGORITHM
    return None
