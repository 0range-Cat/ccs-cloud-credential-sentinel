"""具体验证器。硬性约束（docs/INTERFACES.md §4.3）：
- 只发判断认证状态所需的最小请求（身份确认接口），不枚举资源、不读业务数据、无写操作。
- 禁止重定向；校验最终域名与固定端点一致。
- 401/403 区分认证失败与限流/权限；限流、网络故障、服务不可用一律不算 invalid。
- 证据只存状态码与端点，不保存响应体（可能含敏感信息）。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import datetime, timezone

import httpx

from .base import BaseVerifier, CredentialView, Outcome, register


def _guard_redirect(resp: httpx.Response, allowed_host: str) -> Outcome | None:
    if resp.url.host != allowed_host:
        return Outcome(status="error", evidence={"reason": f"重定向到非预期域名: {resp.url.host}"})
    return None


def _latency(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


@register
class GitHubPatVerifier(BaseVerifier):
    id = "github-pat"
    title = "GitHub PAT（GET /user 身份确认）"
    version = "1.1.0"
    supported_types = ["github_pat"]
    required_fields = ["secret"]
    endpoint_hint = "https://api.github.com/user"

    async def verify(self, cred: CredentialView, http_factory) -> Outcome:
        start = time.monotonic()
        try:
            async with http_factory() as client:
                resp = await client.get(
                    "https://api.github.com/user",
                    headers={"Authorization": f"Bearer {cred.secret}",
                             "User-Agent": "ccs-verifier",
                             "Accept": "application/vnd.github+json"},
                )
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
            return Outcome(status="network_error",
                           evidence={"endpoint": self.endpoint_hint},
                           latency_ms=_latency(start))
        redirected = _guard_redirect(resp, "api.github.com")
        if redirected:
            return redirected
        status = resp.status_code
        evidence = {"endpoint": self.endpoint_hint, "http_status": status}
        if status == 200:
            result = "valid"
        elif status == 401:
            result = "invalid"
        elif status in (403, 429):
            result = "rate_limited" if resp.headers.get("x-ratelimit-remaining") == "0" else "inconclusive"
        else:
            result = "inconclusive"
        return Outcome(status=result, evidence=evidence, latency_ms=_latency(start))


# ---------------- AWS（SigV4 + STS GetCallerIdentity，需要 AK/SK 配对） ----------------

def _sigv4_headers(access_key: str, secret_key: str, host: str = "sts.amazonaws.com",
                   region: str = "us-east-1", service: str = "sts",
                   query: str = "Action=GetCallerIdentity&Version=2011-06-15") -> dict:
    """最小 SigV4 签名（GET + 空载荷）。仅用于 STS GetCallerIdentity 身份确认。"""
    now = datetime.now(timezone.utc)
    amzdate = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    payload_hash = hashlib.sha256(b"").hexdigest()
    canonical_headers = f"host:{host}\nx-amz-date:{amzdate}\n"
    signed_headers = "host;x-amz-date"
    canonical_request = f"GET\n/\n{query}\n{canonical_headers}\n{signed_headers}\n{payload_hash}"
    scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = (f"AWS4-HMAC-SHA256\n{amzdate}\n{scope}\n"
                      f"{hashlib.sha256(canonical_request.encode()).hexdigest()}")

    def _hmac(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode(), hashlib.sha256).digest()

    k_date = _hmac(("AWS4" + secret_key).encode(), datestamp)
    k_region = _hmac(k_date, region)
    k_service = _hmac(k_region, service)
    k_signing = _hmac(k_service, "aws4_request")
    signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return {
        "Authorization": (f"AWS4-HMAC-SHA256 Credential={access_key}/{scope}, "
                          f"SignedHeaders={signed_headers}, Signature={signature}"),
        "x-amz-date": amzdate,
    }


@register
class AwsStsVerifier(BaseVerifier):
    id = "aws-sts-getcalleridentity"
    title = "AWS AK/SK（STS GetCallerIdentity 身份确认，需配对）"
    version = "1.0.0"
    supported_types = ["aws_access_key_id", "aws_secret_access_key"]
    required_fields = ["secret"]  # 配对字段单独校验
    endpoint_hint = "https://sts.amazonaws.com/?Action=GetCallerIdentity"

    def missing_context(self, cred: CredentialView) -> str | None:
        if cred.type == "aws_access_key_id":
            ak, sk = cred.secret, cred.paired.get("aws_secret_access_key")
        else:
            ak, sk = cred.paired.get("aws_access_key_id"), cred.secret
        if not ak or not sk:
            return "缺少配对的 Access Key ID / Secret Access Key（未配对则无法构造签名，也不允许猜测）"
        return None

    async def verify(self, cred: CredentialView, http_factory) -> Outcome:
        start = time.monotonic()
        if cred.type == "aws_access_key_id":
            ak, sk = cred.secret, cred.paired.get("aws_secret_access_key")
        else:
            ak, sk = cred.paired.get("aws_access_key_id"), cred.secret
        headers = _sigv4_headers(ak, sk)
        try:
            async with http_factory() as client:
                resp = await client.get("https://sts.amazonaws.com/",
                                        params={"Action": "GetCallerIdentity", "Version": "2011-06-15"},
                                        headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
            return Outcome(status="network_error",
                           evidence={"endpoint": self.endpoint_hint}, latency_ms=_latency(start))
        redirected = _guard_redirect(resp, "sts.amazonaws.com")
        if redirected:
            return redirected
        status = resp.status_code
        evidence = {"endpoint": self.endpoint_hint, "http_status": status}
        if status == 200:
            result = "valid"
        elif status == 403:
            # 签名被拒：InvalidClientTokenId / SignatureDoesNotMatch / 过期 —— 认证失败
            result = "invalid"
        elif "throttl" in resp.text.lower():
            result = "rate_limited"  # 读响应仅用于识别限流，不存入证据
        elif status == 400:
            result = "inconclusive"
        else:
            result = "inconclusive"
        return Outcome(status=result, evidence=evidence, latency_ms=_latency(start))


# ---------------- Gitee / GitLab / Slack / Telegram ----------------

@register
class GiteeTokenVerifier(BaseVerifier):
    id = "gitee-token"
    title = "Gitee 私人令牌（GET /api/v5/user 身份确认）"
    version = "1.0.0"
    supported_types = ["gitee_token"]
    required_fields = ["secret"]
    endpoint_hint = "https://gitee.com/api/v5/user"

    async def verify(self, cred: CredentialView, http_factory) -> Outcome:
        start = time.monotonic()
        try:
            async with http_factory() as client:
                resp = await client.get("https://gitee.com/api/v5/user",
                                        params={"access_token": cred.secret},
                                        headers={"User-Agent": "ccs-verifier"})
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
            return Outcome(status="network_error",
                           evidence={"endpoint": self.endpoint_hint}, latency_ms=_latency(start))
        redirected = _guard_redirect(resp, "gitee.com")
        if redirected:
            return redirected
        status = resp.status_code
        evidence = {"endpoint": self.endpoint_hint, "http_status": status}
        if status == 200:
            result = "valid"
        elif status == 401:
            result = "invalid"
        elif status in (403, 429):
            result = "rate_limited"
        else:
            result = "inconclusive"
        return Outcome(status=result, evidence=evidence, latency_ms=_latency(start))


@register
class GitLabPatVerifier(BaseVerifier):
    id = "gitlab-pat"
    title = "GitLab PAT（GET /api/v4/user 身份确认）"
    version = "1.0.0"
    supported_types = ["gitlab_pat"]
    required_fields = ["secret"]
    endpoint_hint = "https://gitlab.com/api/v4/user"

    async def verify(self, cred: CredentialView, http_factory) -> Outcome:
        start = time.monotonic()
        try:
            async with http_factory() as client:
                resp = await client.get("https://gitlab.com/api/v4/user",
                                        headers={"PRIVATE-TOKEN": cred.secret,
                                                 "User-Agent": "ccs-verifier"})
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
            return Outcome(status="network_error",
                           evidence={"endpoint": self.endpoint_hint}, latency_ms=_latency(start))
        redirected = _guard_redirect(resp, "gitlab.com")
        if redirected:
            return redirected
        status = resp.status_code
        evidence = {"endpoint": self.endpoint_hint, "http_status": status}
        if status == 200:
            result = "valid"
        elif status == 401:
            result = "invalid"
        elif status == 429 or resp.headers.get("retry-after"):
            result = "rate_limited"
        elif status == 403:
            result = "inconclusive"  # 权限不足 ≠ 无效
        else:
            result = "inconclusive"
        return Outcome(status=result, evidence=evidence, latency_ms=_latency(start))


@register
class SlackTokenVerifier(BaseVerifier):
    id = "slack-auth-test"
    title = "Slack Token（auth.test 身份确认）"
    version = "1.0.0"
    supported_types = ["slack_token"]
    required_fields = ["secret"]
    endpoint_hint = "https://slack.com/api/auth.test"

    async def verify(self, cred: CredentialView, http_factory) -> Outcome:
        start = time.monotonic()
        try:
            async with http_factory() as client:
                resp = await client.post("https://slack.com/api/auth.test",
                                         headers={"Authorization": f"Bearer {cred.secret}",
                                                  "User-Agent": "ccs-verifier"})
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
            return Outcome(status="network_error",
                           evidence={"endpoint": self.endpoint_hint}, latency_ms=_latency(start))
        redirected = _guard_redirect(resp, "slack.com")
        if redirected:
            return redirected
        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            data = {}
        error = data.get("error") or ""
        evidence = {"endpoint": self.endpoint_hint, "http_status": resp.status_code,
                    "ok": bool(data.get("ok"))}
        if data.get("ok") is True:
            return Outcome(status="valid", evidence=evidence, latency_ms=_latency(start))
        if error in ("invalid_auth", "account_inactive", "token_revoked", "token_expired"):
            return Outcome(status="invalid", evidence={**evidence, "error": error},
                           latency_ms=_latency(start))
        if error == "ratelimited" or resp.status_code == 429:
            return Outcome(status="rate_limited", evidence={**evidence, "error": error or None},
                           latency_ms=_latency(start))
        return Outcome(status="inconclusive", evidence=evidence, latency_ms=_latency(start))


@register
class TelegramBotVerifier(BaseVerifier):
    id = "telegram-getme"
    title = "Telegram Bot Token（getMe 身份确认）"
    version = "1.0.0"
    supported_types = ["telegram_bot_token"]
    required_fields = ["secret"]
    endpoint_hint = "https://api.telegram.org/bot<token>/getMe"

    async def verify(self, cred: CredentialView, http_factory) -> Outcome:
        start = time.monotonic()
        try:
            async with http_factory() as client:
                resp = await client.get(f"https://api.telegram.org/bot{cred.secret}/getMe",
                                        headers={"User-Agent": "ccs-verifier"})
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
            return Outcome(status="network_error",
                           evidence={"endpoint": "https://api.telegram.org/getMe"},
                           latency_ms=_latency(start))
        redirected = _guard_redirect(resp, "api.telegram.org")
        if redirected:
            return redirected
        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError):
            data = {}
        evidence = {"endpoint": "https://api.telegram.org/getMe", "http_status": resp.status_code,
                    "ok": bool(data.get("ok"))}
        if data.get("ok") is True:
            return Outcome(status="valid", evidence=evidence, latency_ms=_latency(start))
        if resp.status_code == 401:
            return Outcome(status="invalid", evidence=evidence, latency_ms=_latency(start))
        if resp.status_code == 429:
            return Outcome(status="rate_limited", evidence=evidence, latency_ms=_latency(start))
        return Outcome(status="inconclusive", evidence=evidence, latency_ms=_latency(start))


@register
class NpmTokenVerifier(BaseVerifier):
    id = "npm-whoami"
    title = "npm 令牌（registry whoami 身份确认）"
    version = "1.0.0"
    supported_types = ["npm_token"]
    required_fields = ["secret"]
    endpoint_hint = "https://registry.npmjs.org/-/user/npm.whoami"

    async def verify(self, cred: CredentialView, http_factory) -> Outcome:
        start = time.monotonic()
        try:
            async with http_factory() as client:
                resp = await client.get("https://registry.npmjs.org/-/user/npm.whoami",
                                        headers={"Authorization": f"Bearer {cred.secret}",
                                                 "User-Agent": "ccs-verifier",
                                                 "Accept": "application/json"})
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
            return Outcome(status="network_error",
                           evidence={"endpoint": self.endpoint_hint}, latency_ms=_latency(start))
        redirected = _guard_redirect(resp, "registry.npmjs.org")
        if redirected:
            return redirected
        status = resp.status_code
        evidence = {"endpoint": self.endpoint_hint, "http_status": status}
        if status == 200:
            result = "valid"
        elif status == 401:
            result = "invalid"
        elif status == 429:
            result = "rate_limited"
        else:
            result = "inconclusive"
        return Outcome(status=result, evidence=evidence, latency_ms=_latency(start))


@register
class HuggingFaceVerifier(BaseVerifier):
    id = "huggingface-whoami"
    title = "Hugging Face 令牌（whoami-v2 身份确认）"
    version = "1.0.0"
    supported_types = ["huggingface_token"]
    required_fields = ["secret"]
    endpoint_hint = "https://huggingface.co/api/whoami-v2"

    async def verify(self, cred: CredentialView, http_factory) -> Outcome:
        start = time.monotonic()
        try:
            async with http_factory() as client:
                resp = await client.get("https://huggingface.co/api/whoami-v2",
                                        headers={"Authorization": f"Bearer {cred.secret}",
                                                 "User-Agent": "ccs-verifier"})
        except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPError):
            return Outcome(status="network_error",
                           evidence={"endpoint": self.endpoint_hint}, latency_ms=_latency(start))
        redirected = _guard_redirect(resp, "huggingface.co")
        if redirected:
            return redirected
        status = resp.status_code
        evidence = {"endpoint": self.endpoint_hint, "http_status": status}
        if status == 200:
            result = "valid"
        elif status in (401, 403):
            result = "invalid"
        elif status == 429:
            result = "rate_limited"
        else:
            result = "inconclusive"
        return Outcome(status=result, evidence=evidence, latency_ms=_latency(start))
