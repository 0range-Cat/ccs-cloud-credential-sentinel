"""Gitee 仓库采集器：API v5（gitee.com/api/v5），结构与 GitHub 相似。

限制（如实记录）：匿名限速官方数字未核实（待核实）；搜索接口匿名不可用，
仓库内容/树接口匿名可用（2026-09-19 实测 200）。
"""
from __future__ import annotations

import asyncio
import base64
import time

import httpx

from .base import BaseCollector, ContentItem, CollectorError, register

DEFAULT_API_BASE = "https://gitee.com/api/v5"


def parse_gitee_repo(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if value.startswith(("http://", "https://")):
        parts = value.rstrip("/").split("/")
        return "/".join(parts[-2:])
    if value.count("/") == 1:
        return value
    raise CollectorError(f"无法解析 Gitee 仓库标识: {value}")


@register
class GiteeCollector(BaseCollector):
    key = "gitee"
    category = "code_hosting"
    platform = "gitee"
    title = "Gitee 仓库扫描"

    def __init__(self, config: dict, client_factory=None, token: str = "", cursor_store: dict | None = None):
        super().__init__(config, cursor_store)
        self._client_factory = client_factory
        self._token = token or ""
        self.auth_error: str | None = None

    def _make_client(self) -> httpx.AsyncClient:
        headers = {"User-Agent": "ccs-collector"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if self._client_factory is not None:
            return self._client_factory(headers)
        return httpx.AsyncClient(
            base_url=(self.config.get("api_base") or DEFAULT_API_BASE).rstrip("/"),
            headers=headers, timeout=20, follow_redirects=False,
        )

    def _repo(self) -> str:
        return parse_gitee_repo(self.config.get("repo") or "")

    def _handle(self, status: int, headers, what: str) -> None:
        if status in (403, 429):
            self.rate_limited = True
            return
        if status == 401:
            self.auth_error = "认证失败：Token 无效或过期"
            return
        if status == 404:
            raise CollectorError(f"Gitee 资源不存在（404）: {what}")

    async def _get(self, client, url: str, not_found_ok: bool = False):
        resp = await client.get(url)
        if resp.status_code == 404 and not_found_ok:
            return None
        self._handle(resp.status_code, resp.headers, url)
        if self.rate_limited or self.auth_error:
            return None
        if resp.status_code != 200:
            return None
        return resp.json()

    async def items(self):
        repo = self._repo()
        max_bytes = self._max_file_bytes()
        min_interval = 1.0 / float(self.config.get("rate_per_sec") or 2.0)
        async with self._make_client() as client:
            info = await self._get(client, f"/repos/{repo}")
            if info is None:
                if self.auth_error:
                    raise CollectorError(self.auth_error)
                return
            branch = self.config.get("branch") or info.get("default_branch") or "master"
            tree = await self._get(client, f"/repos/{repo}/git/trees/{branch}?recursive=1")
            if tree is None:
                return
            last = 0.0
            for entry in tree.get("tree", []):
                if entry.get("type") != "blob":
                    continue
                path = entry.get("path", "")
                size = int(entry.get("size") or 0)
                if not self._path_allowed(path) or size > max_bytes:
                    continue
                now = time.monotonic()
                if now - last < min_interval:
                    await asyncio.sleep(min_interval - (now - last))
                last = time.monotonic()
                blob = await self._get(client, f"/repos/{repo}/git/blobs/{entry.get('sha')}", not_found_ok=True)
                if blob is None:
                    if self.auth_error:
                        raise CollectorError(self.auth_error)
                    if self.rate_limited:
                        return
                    continue
                content = blob.get("content") or ""
                encoding = blob.get("encoding", "base64")
                try:
                    data = base64.b64decode(content) if encoding == "base64" else content.encode()
                except Exception:
                    continue
                text = self.decode_text(data)
                if text is None:
                    continue
                yield ContentItem(
                    kind="blob", platform=self.platform,
                    origin_url=f"https://gitee.com/{repo}/blob/{branch}/{path}",
                    repo=info.get("full_name", repo), path=path,
                    version_id=str(entry.get("sha")), version_kind="blob",
                    text=text, size=size,
                    published_at=None, published_source="gitee_api",
                    published_confidence="none",
                    extra={"branch": branch, "repo_html_url": info.get("html_url")},
                )
                if self.rate_limited:
                    return

    def test_connection(self) -> dict:
        import httpx as _h

        repo = self._repo()
        headers = {"User-Agent": "ccs-collector"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            resp = _h.get(f"{(self.config.get('api_base') or DEFAULT_API_BASE).rstrip('/')}/repos/{repo}",
                          headers=headers, timeout=15, follow_redirects=False)
        except _h.HTTPError as exc:
            return {"ok": False, "message": f"网络错误: {exc}"}
        if resp.status_code == 200:
            return {"ok": True, "message": f"仓库可访问: {repo}"}
        if resp.status_code == 401:
            return {"ok": False, "message": "Token 无效或过期（401）"}
        if resp.status_code in (403, 429):
            return {"ok": False, "message": f"触发限流或权限不足（{resp.status_code}）"}
        if resp.status_code == 404:
            return {"ok": False, "message": f"仓库不存在（404）: {repo}"}
        return {"ok": False, "message": f"意外状态码 {resp.status_code}"}
