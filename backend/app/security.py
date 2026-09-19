"""安全基础设施：主密钥、Fernet 加密、凭据指纹、脱敏预览、占位符/熵判定。

约束：
- 主密钥来自环境变量 CCS_MASTER_KEY 或 data/master.key（自动生成），绝不入库入 Git。
- 凭据指纹 = HMAC(pepper, 类型+值)，稳定且无法由指纹反推原文。
- 本模块任何函数都不打印敏感原文。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import math
import secrets
from functools import lru_cache
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings

# 文档示例/占位符特征（小写匹配）。命中即视为非真实凭据。
PLACEHOLDER_TOKENS = (
    "example", "your_", "your-", "xxxx", "changeme", "placeholder", "dummy",
    "sample", "todo", "fixme", "fake", "<", ">", "{", "}", "«", "»",
    "insert_", "apikey_here", "token_here", "secret_here", "********",
    "postgres://user:password@", "not_a_real", "n/a",
)


@lru_cache
def _master_secret() -> str:
    s = get_settings()
    if s.master_key:
        return s.master_key
    key_file = s.data_dir / "master.key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    generated = secrets.token_urlsafe(32)
    key_file.write_text(generated, encoding="utf-8")
    return generated


@lru_cache
def _fernet() -> Fernet:
    digest = hashlib.sha256(_master_secret().encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_text(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_text(token: str | None) -> str | None:
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def _pepper() -> bytes:
    return hashlib.sha256(b"ccs-fingerprint-v1:" + _master_secret().encode("utf-8")).digest()


def credential_fingerprint(cred_type: str, secret: str, paired: dict | None = None) -> str:
    canonical = cred_type + "\x00" + secret
    if paired:
        for k in sorted(paired):
            canonical += f"\x00{k}={paired[k]}"
    return hmac.new(_pepper(), canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def location_hash(*parts: str | int | None) -> str:
    joined = "\x00".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def mask_preview(value: str) -> str:
    v = (value or "").strip()
    if len(v) <= 8:
        return "****"
    head = min(6, max(2, len(v) // 8))
    tail = 4 if len(v) >= 20 else 2
    return v[:head] + "****" + v[-tail:]


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    freq: dict[str, int] = {}
    for ch in value:
        freq[ch] = freq.get(ch, 0) + 1
    n = len(value)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def is_placeholder(value: str) -> bool:
    v = (value or "").strip()
    if not v:
        return True
    low = v.lower()
    if any(t in low for t in PLACEHOLDER_TOKENS):
        return True
    if len(v) >= 12 and len(set(v)) <= 4:  # 重复字符
        return True
    if low in {"password", "passwd", "pass", "pwd", "secret", "token", "key", "none", "null", "true", "false"}:
        return True
    return False
