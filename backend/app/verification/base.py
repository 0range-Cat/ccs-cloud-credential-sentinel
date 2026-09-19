"""验证器插件契约与注册表。验证器与采集/检测完全解耦。"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CredentialView:
    """传给验证器的最小凭据视图（已解密）。"""
    id: int
    type: str
    secret: str
    paired: dict = field(default_factory=dict)


@dataclass
class Outcome:
    status: str          # valid/invalid/inconclusive/missing_context/unsupported/rate_limited/network_error/error
    evidence: dict = field(default_factory=dict)
    latency_ms: int | None = None


class BaseVerifier:
    id: str = ""
    title: str = ""
    version: str = "1.0.0"
    supported_types: list[str] = []
    required_fields: list[str] = ["secret"]
    endpoint_hint: str = ""

    def missing_context(self, cred: CredentialView) -> str | None:
        """缺配对字段或目标信息时返回原因（不发请求）。"""
        for f in self.required_fields:
            if f == "secret" and not cred.secret:
                return "缺少凭据值"
            if f != "secret" and f not in cred.paired:
                return f"缺少配对字段: {f}"
        return None

    async def verify(self, cred: CredentialView, http_factory) -> Outcome:
        raise NotImplementedError

    def spec(self) -> dict:
        return {
            "id": self.id, "title": self.title, "version": self.version,
            "supported_types": self.supported_types,
            "endpoint": self.endpoint_hint,
        }


_VERIFIERS: dict[str, BaseVerifier] = {}


def register(obj) -> BaseVerifier:
    """注册验证器实例；传类则自动实例化（防止误注册类导致契约错误）。"""
    if isinstance(obj, type):
        obj = obj()
    _VERIFIERS[obj.id] = obj
    return obj


def get_verifier(verifier_id: str) -> BaseVerifier | None:
    return _VERIFIERS.get(verifier_id)


def verifier_for_type(cred_type: str) -> BaseVerifier | None:
    for v in _VERIFIERS.values():
        if cred_type in v.supported_types:
            return v
    return None


def all_verifiers() -> dict[str, BaseVerifier]:
    return dict(_VERIFIERS)


from . import verifiers  # noqa: E402,F401  # 触发注册
