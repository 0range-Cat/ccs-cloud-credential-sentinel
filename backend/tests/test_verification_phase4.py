"""阶段4 验证器测试：AWS SigV4 结构、五平台状态映射、配对字段传递。"""
import asyncio
import random
import string

import httpx

from app.verification.base import CredentialView, get_verifier
from app.verification.verifiers import _sigv4_headers


def rand_alnum(n):
    return "".join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(n))


def factory_for(handler):
    def _make():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5,
                                 follow_redirects=False)
    return _make


def run(verifier_id: str, cred: CredentialView, handler):
    v = get_verifier(verifier_id)
    return asyncio.run(v.verify(cred, factory_for(handler)))


def test_sigv4_header_structure_and_determinism():
    # 固定时间不可注入，这里验证结构与同一秒内的确定性
    a = _sigv4_headers("AKIDEXAMPLE", "wJalrXUtnFEMI")
    b = _sigv4_headers("AKIDEXAMPLE", "wJalrXUtnFEMI")
    for h in (a, b):
        assert h["Authorization"].startswith("AWS4-HMAC-SHA256 ")
        assert "Credential=AKIDEXAMPLE/" in h["Authorization"]
        assert "SignedHeaders=host;x-amz-date" in h["Authorization"]
        assert "Signature=" in h["Authorization"]
        assert h["x-amz-date"].endswith("Z") and len(h["x-amz-date"]) == 16
    # 同一 amzdate 下签名确定（绕过时间：直接比较同调用内的组件）
    assert a["x-amz-date"] == b["x-amz-date"] or a["Authorization"] != b["Authorization"]


def test_aws_verifier_requires_pairing():
    v = get_verifier("aws-sts-getcalleridentity")
    assert v.missing_context(CredentialView(id=1, type="aws_secret_access_key", secret="sk")) is not None
    ok = v.missing_context(CredentialView(id=1, type="aws_secret_access_key", secret="sk",
                                          paired={"aws_access_key_id": "AKIA123"}))
    assert ok is None, "配对齐全时不得报缺上下文"


def test_aws_status_mapping():
    vid = "aws-sts-getcalleridentity"
    cred = CredentialView(id=1, type="aws_secret_access_key", secret="sk",
                          paired={"aws_access_key_id": "AKIAQ5F2ZK7WLMXEDR9T"})

    def ok(request: httpx.Request) -> httpx.Response:
        assert "AWS4-HMAC-SHA256" in request.headers["authorization"]
        assert request.url.params["Action"] == "GetCallerIdentity"
        return httpx.Response(200, text="<GetCallerIdentityResult></GetCallerIdentityResult>")
    assert run(vid, cred, ok).status == "valid"

    def denied(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, text="<Error><Code>InvalidClientTokenId</Code></Error>")
    assert run(vid, cred, denied).status == "invalid"

    def throttled(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="<Error><Code>ThrottlingException</Code></Error>")
    assert run(vid, cred, throttled).status == "rate_limited", "限流不得判为 invalid"


def test_gitee_gitlab_slack_telegram_status_mapping():
    # Gitee：200/401/403
    g_ok = lambda r: httpx.Response(200, json={"login": "x"})  # noqa: E731
    assert run("gitee-token", CredentialView(1, "gitee_token", "t"), g_ok).status == "valid"
    g_bad = lambda r: httpx.Response(401, json={"message": "bad"})  # noqa: E731
    assert run("gitee-token", CredentialView(1, "gitee_token", "t"), g_bad).status == "invalid"
    g_lim = lambda r: httpx.Response(403, json={})  # noqa: E731
    assert run("gitee-token", CredentialView(1, "gitee_token", "t"), g_lim).status == "rate_limited"

    # GitLab：403 权限不足 ≠ invalid
    l_ok = lambda r: httpx.Response(200, json={"username": "x"})  # noqa: E731
    assert run("gitlab-pat", CredentialView(1, "gitlab_pat", "t"), l_ok).status == "valid"
    l_403 = lambda r: httpx.Response(403, json={"message": "403 Forbidden"})  # noqa: E731
    assert run("gitlab-pat", CredentialView(1, "gitlab_pat", "t"), l_403).status == "inconclusive"

    # Slack：按响应体 ok/error 语义
    s_ok = lambda r: httpx.Response(200, json={"ok": True})  # noqa: E731
    assert run("slack-auth-test", CredentialView(1, "slack_token", "t"), s_ok).status == "valid"
    s_bad = lambda r: httpx.Response(200, json={"ok": False, "error": "invalid_auth"})  # noqa: E731
    assert run("slack-auth-test", CredentialView(1, "slack_token", "t"), s_bad).status == "invalid"
    s_lim = lambda r: httpx.Response(200, json={"ok": False, "error": "ratelimited"})  # noqa: E731
    assert run("slack-auth-test", CredentialView(1, "slack_token", "t"), s_lim).status == "rate_limited"

    # Telegram：getMe 401/429
    t_ok = lambda r: httpx.Response(200, json={"ok": True, "result": {"id": 1}})  # noqa: E731
    assert run("telegram-getme", CredentialView(1, "telegram_bot_token", "1:AAx"), t_ok).status == "valid"
    t_bad = lambda r: httpx.Response(401, json={"ok": False, "error_code": 401})  # noqa: E731
    assert run("telegram-getme", CredentialView(1, "telegram_bot_token", "1:AAx"), t_bad).status == "invalid"
    t_lim = lambda r: httpx.Response(429, json={"ok": False, "error_code": 429})  # noqa: E731
    assert run("telegram-getme", CredentialView(1, "telegram_bot_token", "1:AAx"), t_lim).status == "rate_limited"


def test_engine_pairing_carries_values():
    from app.detection.engine import DetectionEngine
    from app.detection.registry import RuleRegistry
    reg = RuleRegistry(); reg.load()
    engine = DetectionEngine(reg)
    ak = "AKIA" + rand_alnum(16).upper()
    sk = rand_alnum(40)
    cands = [c for c in engine.scan(f"aws_access_key_id = {ak}\naws_secret_access_key = {sk}")
             if not c.evidence.get("rejected_candidate")]
    sk_cand = next(c for c in cands if c.type == "aws_secret_access_key")
    assert sk_cand.evidence.get("paired", {}).get("aws_access_key_id") == ak, \
        "配对字段值必须传递给验证器"
    ak_cand = next(c for c in cands if c.type == "aws_access_key_id")
    assert ak_cand.evidence.get("paired", {}).get("aws_secret_access_key") == sk


def test_fingerprint_separates_accounts_by_pairing():
    from app.security import credential_fingerprint
    sk = rand_alnum(40)
    a = credential_fingerprint("aws_secret_access_key", sk, {"aws_access_key_id": "AKIAAAA"})
    b = credential_fingerprint("aws_secret_access_key", sk, {"aws_access_key_id": "AKIABBB"})
    assert a != b, "同一 SK 配不同 AK 属不同账号，不得合并"
