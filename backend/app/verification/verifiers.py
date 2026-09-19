"""具体验证器。硬性约束（docs/INTERFACES.md §4.3）：
- 只发判断认证状态所需的最小请求（身份确认接口），不枚举资源、不读业务数据、无写操作。
- 禁止重定向；校验最终域名与固定端点一致。
- 401/403 区分认证失败与限流/权限；限流、网络故障、服务不可用一律不算 invalid。
- 证据只存状态码与端点，不保存响应体（可能含敏感信息）。
"""
from __future__ import annotations

import time

import httpx

from .base import BaseVerifier, CredentialView, Outcome, register


def _guard_redirect(resp: httpx.Response, allowed_host: str) -> Outcome | None:
    if resp.url.host != allowed_host:
        return Outcome(status="error", evidence={"reason": f"重定向到非预期域名: {resp.url.host}"})
    return None


@register
class GitHubPatVerifier(BaseVerifier):
    id = "github-pat"
    title = "GitHub PAT（GET /user 身份确认）"
    version = "1.0.0"
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
                           latency_ms=int((time.monotonic() - start) * 1000))
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
        return Outcome(status=result, evidence=evidence,
                       latency_ms=int((time.monotonic() - start) * 1000))
