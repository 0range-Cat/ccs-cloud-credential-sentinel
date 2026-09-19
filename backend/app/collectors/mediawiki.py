"""MediaWiki 兼容采集器：Action API recentchanges 增量 + 修订内容抓取。

- 游标 rccontinue 持久化，实现真正的增量监控。
- 修订时间戳 = 该版本公开发布时间（来源可信，confidence=medium）——
  使"发现时延"统计首次具备可靠样本。
- 内容为抓取时刻该页面的最新修订（同页多次变更按页去重），如实记录。
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import quote, urlparse

import httpx

from .base import USER_AGENT, BaseCollector, ContentItem, CollectorError, register


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)


@register
class MediaWikiCollector(BaseCollector):
    key = "mediawiki"
    category = "wiki"
    platform = "mediawiki"
    title = "MediaWiki 站点监控"

    def __init__(self, config: dict, client_factory=None, cursor_store: dict | None = None):
        super().__init__(config, cursor_store)
        self._client_factory = client_factory
        self.auth_error: str | None = None

    def _api_url(self) -> str:
        url = (self.config.get("api_url") or "").strip()
        if not url.startswith("http"):
            raise CollectorError("api_url 必须是完整的 MediaWiki api.php 地址")
        return url.rstrip("/")

    def _page_url(self, api_url: str, pageid: int) -> str:
        return f"{api_url.split('/api.php')[0]}/index.php?curid={pageid}"

    def _host(self, api_url: str) -> str:
        return urlparse(api_url).netloc

    async def items(self):
        api_url = self._api_url()
        max_items = int(self.config.get("max_items") or 50)
        namespaces = str(self.config.get("namespaces") or "0")
        async with self._client() as client:
            seen_pageids: set[int] = set()
            pending_revids: list[dict] = []
            while len(seen_pageids) < max_items:
                params = {
                    "action": "query", "list": "recentchanges",
                    "rcprop": "title|ids|timestamp", "rcnamespace": namespaces,
                    "rclimit": min(50, max_items - len(seen_pageids)) or 1,
                    "format": "json", "formatversion": "2",
                }
                cursor = self.cursors.get("rccontinue")
                if cursor:
                    params["rccontinue"] = cursor
                data = await self._get(client, api_url, params)
                if data is None or self.rate_limited:
                    break
                changes = data.get("query", {}).get("recentchanges", [])
                for ch in changes:
                    if ch.get("type") not in ("edit", "new"):
                        continue
                    pageid = ch.get("pageid")
                    revid = ch.get("revid")
                    if pageid in seen_pageids or not revid:
                        continue
                    seen_pageids.add(pageid)
                    pending_revids.append(ch)
                    if len(seen_pageids) >= max_items:
                        break
                new_cursor = (data.get("continue") or {}).get("rccontinue")
                if new_cursor:
                    self.save_cursor("rccontinue", new_cursor)
                    if not new_cursor or self._exhausted(changes, new_cursor):
                        pass
                if not changes or not new_cursor:
                    break
            # 批量抓取修订内容（每批 ≤10 个 revid）
            for i in range(0, len(pending_revids), 10):
                if self.rate_limited:
                    break
                batch = pending_revids[i:i + 10]
                params = {
                    "action": "query", "prop": "revisions",
                    "revids": "|".join(str(c["revid"]) for c in batch),
                    "rvprop": "content|timestamp", "format": "json", "formatversion": "2",
                }
                data = await self._get(client, api_url, params)
                if data is None:
                    if self.auth_error:
                        raise CollectorError(self.auth_error)
                    continue
                by_pageid: dict[int, dict] = {}
                for page in data.get("query", {}).get("pages", []):
                    rev = (page.get("revisions") or [{}])[0]
                    # formatversion=2 下修订对象不含 revid 字段，改按 pageid 映射
                    by_pageid[page.get("pageid")] = {
                        "content": rev.get("content") or "",
                        "timestamp": rev.get("timestamp"),
                        "title": page.get("title"),
                    }
                for ch in batch:
                    rev = by_pageid.get(ch["pageid"])
                    if not rev or not rev["content"]:
                        continue
                    ts = _parse_ts(rev.get("timestamp") or ch.get("timestamp"))
                    yield ContentItem(
                        kind="page", platform=self.platform,
                        origin_url=self._page_url(api_url, ch["pageid"]),
                        repo=self._host(api_url), path=str(rev.get("title") or ch.get("title") or ""),
                        version_id=f"rev-{ch['revid']}", version_kind="revision",
                        text=rev["content"], size=len(rev["content"]),
                        published_at=ts, published_source="mediawiki_revision_timestamp",
                        published_confidence="medium",
                        source_updated_at=ts,
                        extra={"pageid": ch.get("pageid"), "change_type": ch.get("type"),
                               "site_api": api_url},
                    )

    @staticmethod
    def _exhausted(_changes, _cursor) -> bool:
        return False

    def _client(self) -> httpx.AsyncClient:
        headers = {"User-Agent": USER_AGENT}
        if self._client_factory is not None:
            return self._client_factory(headers)
        return httpx.AsyncClient(headers=headers, timeout=25, follow_redirects=False)

    async def _get(self, client, url: str, params: dict):
        resp = await client.get(url, params=params)
        if resp.status_code in (403, 429):
            self.rate_limited = True
            return None
        if resp.status_code == 401:
            self.auth_error = "认证失败：该站点需要登录态"
            return None
        if resp.status_code != 200:
            return None
        data = resp.json()
        err = (data.get("error") or {}).get("info")
        if err:
            raise CollectorError(f"MediaWiki API 错误: {err}")
        return data

    def test_connection(self) -> dict:
        import httpx as _h

        try:
            resp = _h.get(self._api_url(), params={
                "action": "query", "meta": "siteinfo", "format": "json"}, timeout=15)
        except _h.HTTPError as exc:
            return {"ok": False, "message": f"网络错误: {exc}"}
        if resp.status_code == 200 and "query" in resp.json():
            name = resp.json()["query"].get("general", {}).get("sitename", "MediaWiki")
            return {"ok": True, "message": f"站点可访问: {name}"}
        if resp.status_code in (403, 429):
            return {"ok": False, "message": f"触发限流或访问控制（{resp.status_code}）"}
        return {"ok": False, "message": f"意外状态码 {resp.status_code}"}
