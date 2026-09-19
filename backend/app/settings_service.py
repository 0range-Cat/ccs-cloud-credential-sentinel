"""运行时设置：平台 Token 等敏感项加密存储；提供带默认值的读取。"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from .db import utcnow
from .models import AppSetting
from .security import decrypt_text, encrypt_text

# 默认设置（key: (默认值, 是否敏感)）
DEFAULTS: dict[str, tuple[object, bool]] = {
    "platform.github.token": ("", True),
    "platform.gitee.token": ("", True),
    "network.proxy": ("", False),
    "network.timeout_seconds": (20, False),
    "network.rate_per_host_per_sec": (2.0, False),
    "scan.max_items": (2000, False),
    "scan.max_bytes": (512 * 1024 * 1024, False),
    "scan.max_seconds": (1800, False),
    "scan.max_file_bytes": (1024 * 1024, False),
    "display.timezone": ("Asia/Shanghai", False),
    "masking.enabled": (True, False),
    "export.default_masked": (True, False),
    "verification.auto_enabled": (False, False),
    "verification.concurrency": (2, False),
    "verification.reverify_days": (30, False),
    "verification.max_per_minute": (10, False),
    "retention.cache_days": (30, False),
}


def get_setting(session: Session, key: str):
    if key in DEFAULTS:
        default, sensitive = DEFAULTS[key]
    else:
        default, sensitive = None, False
    row = session.get(AppSetting, key)
    if row is None:
        return default
    value = row.value_json.get("v", default)
    if row.sensitive:
        value = decrypt_text(value) if isinstance(value, str) else None
    return value


def set_setting(session: Session, key: str, value, sensitive: bool | None = None) -> None:
    if sensitive is None:
        sensitive = DEFAULTS.get(key, (None, False))[1]
    stored = value
    if sensitive and isinstance(value, str):
        stored = encrypt_text(value) if value else ""
    row = session.get(AppSetting, key)
    if row is None:
        row = AppSetting(key=key, value_json={"v": stored}, sensitive=sensitive)
        session.add(row)
    else:
        row.value_json = {"v": stored}
        if sensitive is not None:
            row.sensitive = sensitive
        row.updated_at = utcnow()


def all_settings(session: Session, include_secrets: bool = False) -> dict:
    """返回全部设置；sensitive 项默认以 fixed 遮盖显示是否已配置。"""
    out: dict[str, object] = {}
    keys = set(DEFAULTS) | {r.key for r in session.query(AppSetting).all()}
    for key in sorted(keys):
        default, sensitive = DEFAULTS.get(key, (None, False))
        raw = get_setting(session, key)
        if sensitive and not include_secrets:
            out[key] = {"configured": bool(raw), "value": None, "sensitive": True}
        else:
            out[key] = {"configured": bool(raw), "value": raw, "sensitive": sensitive}
    return out


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)
