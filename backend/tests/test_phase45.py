"""阶段4/收尾测试：wxapkg 容器解析、npm/HF 验证器、自动验证策略（T4.1）。"""
import asyncio
import random
import string
import struct

import httpx

from app.collectors.wxapkg import WxapkgCollector
from app.collectors.base import CollectorError
from app.verification.base import CredentialView, get_verifier
from app.verification import worker
from app.models import Credential, VerificationJob


def rand_alnum(n):
    return "".join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(n))


def collect(collector):
    async def _run():
        return [item async for item in collector.items()]
    return asyncio.run(_run())


def build_wxapkg(entries: dict[str, bytes]) -> bytes:
    """按公开容器格式构造未加密 wxapkg（0xBE + 索引 + 正文）。"""
    index = b""
    body = b""
    offset = 0
    for name, data in entries.items():
        nb = name.encode()
        index += struct.pack(">I", len(nb)) + nb + struct.pack(">II", offset, len(data))
        body += data
        offset += len(data)
    header = b"\xBE" + struct.pack(">II", len(index), len(body)) + b"\xED" + struct.pack(">I", len(entries))
    return header + index + body


def _scan_bytes(collector, data: bytes):
    import tempfile
    from pathlib import Path
    with tempfile.NamedTemporaryFile(suffix=".wxapkg", delete=False) as f:
        f.write(data)
        p = f.name
    try:
        collector.config["path"] = p
        return collect(collector)
    finally:
        Path(p).unlink(missing_ok=True)


def test_wxapkg_entries_scanned():
    token = "ghp_" + rand_alnum(36)
    pkg = build_wxapkg({
        "app-config.json": b'{"pages":["pages/index"]}',
        "pages/index.js": f'var t = "{token}";'.encode(),
        "images/logo.png": b"\x89PNG\r\n\x1a\n\x00\x01",
    })
    c = WxapkgCollector({})
    items = _scan_bytes(c, pkg)
    paths = {i.path for i in items}
    assert "app-config.json" in paths and "pages/index.js" in paths
    assert "images/logo.png" not in paths, "二进制条目应跳过"
    js = next(i for i in items if i.path == "pages/index.js")
    assert token in js.text and js.version_kind == "app_version"
    assert js.extra.get("entry_count") == 3


def test_wxapkg_encrypted_refused():
    pkg = b"V1MMWX" + b"\x00" * 100
    c = WxapkgCollector({})
    try:
        _scan_bytes(c, pkg)
        raise AssertionError("加密包必须拒绝且不做解密")
    except CollectorError as exc:
        assert "解密" in str(exc) or "加密" in str(exc)


def test_wxapkg_truncated_index_refused():
    pkg = build_wxapkg({"a.js": b"var x=1;"})[:-3]
    c = WxapkgCollector({})
    try:
        _scan_bytes(c, pkg)
        raise AssertionError
    except CollectorError:
        pass


# ---------------- npm / HuggingFace 验证器 ----------------

def factory_for(handler):
    def _make():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5,
                                 follow_redirects=False)
    return _make


def run(vid, cred, handler):
    return asyncio.run(get_verifier(vid).verify(cred, factory_for(handler)))


def test_npm_whoami_mapping():
    ok = lambda r: httpx.Response(200, text="someuser")  # noqa: E731
    assert run("npm-whoami", CredentialView(1, "npm_token", "npm_" + rand_alnum(36)), ok).status == "valid"
    bad = lambda r: httpx.Response(401, json={"error": "unauthorized"})  # noqa: E731
    assert run("npm-whoami", CredentialView(1, "npm_token", "npm_x"), bad).status == "invalid"
    lim = lambda r: httpx.Response(429, text="")  # noqa: E731
    assert run("npm-whoami", CredentialView(1, "npm_token", "npm_x"), lim).status == "rate_limited"


def test_huggingface_whoami_mapping():
    ok = lambda r: httpx.Response(200, json={"name": "u", "type": "user"})  # noqa: E731
    assert run("huggingface-whoami", CredentialView(1, "huggingface_token", "hf_" + rand_alnum(34)), ok).status == "valid"
    bad = lambda r: httpx.Response(401, json={"error": "Invalid credentials"})  # noqa: E731
    assert run("huggingface-whoami", CredentialView(1, "huggingface_token", "hf_x"), bad).status == "invalid"


# ---------------- 自动验证策略（T4.1） ----------------

def _mk(db, ctype, secret, status="not_requested", verified_at=None):
    cred = Credential(fingerprint=f"t-{rand_alnum(12)}", type=ctype, vendor="t", rule_id="t",
                      secret_encrypted=__import__("app.security", fromlist=["encrypt_text"]).encrypt_text(secret),
                      preview="****", verification_status=status, verified_at=verified_at)
    db.add(cred)
    db.commit()
    return cred


def test_auto_verify_off_by_default(db):
    _mk(db, "github_pat", "ghp_" + rand_alnum(36))
    assert worker.auto_enqueue_due(db) == 0
    assert db.query(VerificationJob).filter(VerificationJob.requested_by == "auto").count() == 0


def test_auto_verify_enqueue_and_reverify(db):
    from datetime import timedelta
    from app.db import utcnow
    from app import settings_service
    settings_service.set_setting(db, "verification.auto_enabled", True)
    db.commit()

    fresh = _mk(db, "github_pat", "ghp_" + rand_alnum(36))
    unsupported = _mk(db, "db_connection_url", "mysql://u:SecretX99@h/db")
    stale_valid = _mk(db, "slack_token", "xoxb-" + rand_alnum(20), status="valid",
                      verified_at=utcnow() - timedelta(days=60))
    fresh_valid = _mk(db, "slack_token", "xoxb-" + rand_alnum(20), status="valid",
                      verified_at=utcnow())
    transient = _mk(db, "telegram_bot_token", "1:AA" + rand_alnum(33), status="rate_limited",
                    verified_at=utcnow() - timedelta(hours=2))

    n = worker.auto_enqueue_due(db, limit=10)
    assert n >= 3, "应入队：未验证1 + 过期valid1 + 过期瞬态1"
    statuses = {c.id: c.verification_status for c in (fresh, unsupported, stale_valid, fresh_valid, transient)}
    assert statuses[fresh.id] == "queued"
    assert statuses[unsupported.id] == "not_requested", "无验证器类型不自动入队"
    assert statuses[stale_valid.id] == "queued", "超过重验间隔应重新验证"
    assert statuses[fresh_valid.id] == "valid", "未到重验间隔不动"
    assert statuses[transient.id] == "queued", "瞬态失败1小时后重试"

    # 每次限量
    n2 = worker.auto_enqueue_due(db, limit=1)
    assert n2 <= 1
    # 关闭开关后不再入队
    settings_service.set_setting(db, "verification.auto_enabled", False)
    db.commit()
    assert worker.auto_enqueue_due(db) == 0
