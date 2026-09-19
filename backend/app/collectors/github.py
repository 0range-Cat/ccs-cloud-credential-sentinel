"""GitHub 仓库采集器：REST API 树遍历 + blob 下载。

限制（如实记录）：
- 仅当前分支文件树；Git 历史扫描在阶段2 实现。
- api.github.com 限流：未认证 60 次/小时，认证 5000 次/小时；树接口单次最多 10 万条目，
  超出返回 truncated=true（本采集器如实记录该标记）。
- 不假定 Code Search 实时完整；持续监控靠轮询树 HEAD（阶段2 接入游标）。
"""
from __future__ import annotations

import asyncio
import base64
import time

import httpx

from .base import BaseCollector, ContentItem, CollectorError, register

DEFAULT_API_BASE = "https://api.github.com"


def parse_repo(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if value.startswith(("http://", "https://")):
        parts = value.rstrip("/").split("/")
        return "/".join(parts[-2:])
    if value.count("/") == 1:
        return value
    raise CollectorError(f"无法解析仓库标识: {value}")


@register
class GitHubCollector(BaseCollector):
    key = "github"
    category = "code_hosting"
    platform = "github"
    title = "GitHub 仓库扫描"

    def __init__(self, config: dict, client_factory=None, token: str = ""):
        super().__init__(config)
        self._client_factory = client_factory
        self._token = token or ""
        self.rate_limited = False
        self.auth_error: str | None = None

    def _make_client(self) -> httpx.AsyncClient:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "ccs-collector",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if self._client_factory is not None:
            return self._client_factory(headers)
        return httpx.AsyncClient(
            base_url=(self.config.get("api_base") or DEFAULT_API_BASE).rstrip("/"),
            headers=headers, timeout=20, follow_redirects=False,
        )

    def _repo(self) -> str:
        return parse_repo(self.config.get("repo") or "")

    def _handle_status(self, status: int, headers, what: str) -> None:
        if status in (403, 429):
            remaining = headers.get("x-ratelimit-remaining")
            if remaining == "0" or status == 429 or headers.get("retry-after"):
                self.rate_limited = True
                return
            raise CollectorError(f"GitHub 拒绝访问（{status}）于 {what}")
        if status == 401:
            self.auth_error = "认证失败：Token 无效或过期"
            return
        if status == 404:
            raise CollectorError(f"GitHub 资源不存在（404）: {what}")

    async def _get(self, client: httpx.AsyncClient, url: str):
        resp = await client.get(url)
        self._handle_status(resp.status_code, resp.headers, url)
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
            branch = self.config.get("branch") or info.get("default_branch") or "main"
            tree = await self._get(client, f"/repos/{repo}/git/trees/{branch}?recursive=1")
            if tree is None:
                return
            entries = [e for e in tree.get("tree", []) if e.get("type") == "blob"]
            truncated = bool(tree.get("truncated"))
            last = 0.0
            for entry in entries:
                path = entry.get("path", "")
                size = int(entry.get("size") or 0)
                if not self._path_allowed(path):
                    continue
                if size > max_bytes:
                    continue
                now = time.monotonic()
                if now - last < min_interval:
                    await asyncio.sleep(min_interval - (now - last))
                last = time.monotonic()
                blob = await self._get(client, f"/repos/{repo}/git/blobs/{entry.get('sha')}")
                if blob is None:
                    if self.auth_error:
                        raise CollectorError(self.auth_error)
                    if self.rate_limited:
                        return
                    continue
                if blob.get("encoding") != "base64":
                    continue
                try:
                    data = base64.b64decode(blob.get("content") or "")
                except Exception:
                    continue
                text = self.decode_text(data)
                if text is None:
                    continue
                origin = f"https://github.com/{repo}/blob/{branch}/{path}"
                yield ContentItem(
                    kind="blob", platform=self.platform, origin_url=origin,
                    repo=info.get("full_name", repo), path=path,
                    version_id=str(entry.get("sha")), version_kind="blob",
                    text=text, size=size,
                    published_at=None, published_source="github_api",
                    published_confidence="none",
                    extra={
                        "branch": branch,
                        "head_tree_sha": tree.get("sha"),
                        "tree_truncated": truncated,
                        "repo_pushed_at": info.get("pushed_at"),
                    },
                )
                if self.rate_limited:
                    return

    def test_connection(self) -> dict:
        import httpx as _h

        repo = self._repo()
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "ccs-collector"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        try:
            resp = _h.get(f"{(self.config.get('api_base') or DEFAULT_API_BASE).rstrip('/')}/repos/{repo}",
                          headers=headers, timeout=15, follow_redirects=False)
        except _h.HTTPError as exc:
            return {"ok": False, "message": f"网络错误: {exc}"}
        if resp.status_code == 200:
            token_state = "已配置 Token" if self._token else "未配置 Token（匿名低频）"
            return {"ok": True, "message": f"仓库可访问（{token_state}）: {repo}"}
        if resp.status_code == 401:
            return {"ok": False, "message": "Token 无效或过期（401）"}
        if resp.status_code in (403, 429):
            return {"ok": False, "message": f"触发限流或权限不足（{resp.status_code}）"}
        if resp.status_code == 404:
            return {"ok": False, "message": f"仓库不存在（404）: {repo}"}
        return {"ok": False, "message": f"意外状态码 {resp.status_code}"}
