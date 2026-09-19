"""通用网页采集器：RSS/Atom 订阅、Sitemap、单 URL。

- RSS/Atom：feedparser 解析；条目发布时间为来源声明（confidence=medium，source=rss_published；
  只有 updated 时用 rss_updated）。ETag/Last-Modified 作增量游标。
- Sitemap：loc+lastmod 为低可信公开时间（site-claimed）；逐页抓取受 max_items 预算限制。
- 单 URL：内容哈希作版本（重扫不变即跳过）。
- 平台标识取 URL 主机名，便于按站点统计。
"""
from __future__ import annotations

import hashlib
import html as html_lib
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

from .base import BaseCollector, ContentItem, CollectorError, register

_SCRIPT_RE = re.compile(r"<(script|style)[\s\S]*?</\1>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\n{3,}")


def html_to_text(raw: str) -> str:
    text = _SCRIPT_RE.sub(" ", raw)
    text = _TAG_RE.sub("\n", text)
    text = html_lib.unescape(text)
    return _WS_RE.sub("\n\n", text).strip()


def _parse_dt(value) -> datetime | None:
    if isinstance(value, tuple):
        try:
            return datetime.fromtimestamp(__import__("calendar").timegm(value), tz=timezone.utc).replace(tzinfo=None)
        except Exception:
            return None
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    return None


@register
class GenericWebCollector(BaseCollector):
    key = "generic_web"
    category = "knowledge"
    platform = "web"  # 实际 platform 在产出 item 时取主机名
    title = "通用 RSS/Sitemap/URL 采集"

    def __init__(self, config: dict, client_factory=None, cursor_store: dict | None = None):
        super().__init__(config, cursor_store)
        self._client_factory = client_factory

    def _client(self) -> httpx.AsyncClient:
        headers = {"User-Agent": "ccs-collector (feed/sitemap monitor)"}
        if self._client_factory is not None:
            return self._client_factory(headers)
        return httpx.AsyncClient(headers=headers, timeout=25, follow_redirects=True)

    def _platform(self, url: str) -> str:
        host = urlparse(url).netloc
        return host or "web"

    @staticmethod
    def _fetch_headers(cursor_key: str | None, cursors: dict) -> dict:
        h = {}
        if cursor_key and cursors.get(f"etag:{cursor_key}"):
            h["If-None-Match"] = cursors[f"etag:{cursor_key}"]
        if cursor_key and cursors.get(f"lm:{cursor_key}"):
            h["If-Modified-Since"] = cursors[f"lm:{cursor_key}"]
        return h

    def _store_conditional(self, cursor_key: str | None, resp: httpx.Response) -> None:
        if not cursor_key:
            return
        if resp.headers.get("etag"):
            self.save_cursor(f"etag:{cursor_key}", resp.headers["etag"])
        if resp.headers.get("last-modified"):
            self.save_cursor(f"lm:{cursor_key}", resp.headers["last-modified"])

    async def items(self):
        feed_url = (self.config.get("feed_url") or "").strip()
        sitemap_url = (self.config.get("sitemap_url") or "").strip()
        single_url = (self.config.get("url") or "").strip()
        if not (feed_url or sitemap_url or single_url):
            raise CollectorError("需要配置 feed_url / sitemap_url / url 之一")
        max_items = int(self.config.get("max_items") or 50)
        async with self._client() as client:
            if feed_url:
                async for item in self._iter_feed(client, feed_url, max_items):
                    yield item
            if sitemap_url:
                async for item in self._iter_sitemap(client, sitemap_url, max_items):
                    yield item
            if single_url:
                item = await self._fetch_page(client, single_url, published_confidence="none",
                                              published_source="", published_at=None,
                                              version_extra="")
                if item:
                    yield item

    async def _get(self, client, url: str, cursor_key: str | None = None):
        resp = await client.get(url, headers=self._fetch_headers(cursor_key, self.cursors))
        if resp.status_code == 304:
            self.save_cursor(f"not_modified:{cursor_key}", "1") if cursor_key else None
            return None
        if resp.status_code in (403, 429):
            self.rate_limited = True
            return None
        if resp.status_code != 200:
            return None
        self._store_conditional(cursor_key, resp)
        return resp

    async def _iter_feed(self, client, feed_url: str, max_items: int):
        import feedparser

        cursor_key = hashlib.sha256(feed_url.encode()).hexdigest()[:16]
        resp = await self._get(client, feed_url, cursor_key)
        if resp is None:
            return
        parsed = feedparser.parse(resp.content)
        count = 0
        for entry in parsed.entries:
            if count >= max_items or self.rate_limited:
                break
            link = entry.get("link") or entry.get("id") or ""
            title = entry.get("title") or ""
            content = ""
            if entry.get("content"):
                content = entry.content[0].get("value", "")
            content = content or entry.get("summary") or entry.get("description") or ""
            if not content and not title:
                continue
            published = _parse_dt(entry.get("published_parsed")) or _parse_dt(entry.get("updated_parsed"))
            source = "rss_published" if entry.get("published_parsed") else (
                "rss_updated" if entry.get("updated_parsed") else "")
            confidence = "medium" if published else "none"
            text = (html_to_text(content) or title)
            version_meta = f"{link}|{entry.get('updated') or entry.get('published') or ''}"
            yield ContentItem(
                kind="page", platform=self._platform(feed_url),
                origin_url=link or feed_url, repo=self._platform(feed_url),
                path=title[:200] or (link or feed_url),
                version_id=hashlib.sha256(version_meta.encode()).hexdigest()[:32],
                version_kind="none", text=text, size=len(text),
                published_at=published, published_source=source, published_confidence=confidence,
                extra={"feed": feed_url},
            )
            count += 1

    async def _iter_sitemap(self, client, sitemap_url: str, max_items: int):
        import xml.etree.ElementTree as ET

        resp = await self._get(client, sitemap_url)
        if resp is None:
            return
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            raise CollectorError(f"Sitemap 解析失败（非 XML）: {sitemap_url}")
        urls = []
        for elem in root.iter():
            if elem.tag.endswith("}url") or elem.tag == "url":
                loc = lastmod = None
                for child in elem:
                    if child.tag.endswith("}loc") or child.tag == "loc":
                        loc = (child.text or "").strip()
                    if child.tag.endswith("}lastmod") or child.tag == "lastmod":
                        lastmod = (child.text or "").strip()
                if loc:
                    urls.append((loc, lastmod))
        for loc, lastmod in urls[:max_items]:
            if self.rate_limited:
                break
            published = _parse_dt(lastmod)
            page = await self._fetch_page(
                client, loc,
                published_at=published, published_source="sitemap_lastmod",
                published_confidence="low" if published else "none",
                version_extra=lastmod or "")
            if page:
                yield page

    async def _fetch_page(self, client, url: str, published_at, published_source: str,
                          published_confidence: str, version_extra: str):
        resp = await self._get(client, url)
        if resp is None:
            return None
        try:
            resp.raise_for_status()
        except httpx.HTTPError:
            return None
        text = html_to_text(resp.text)
        if not text:
            return None
        return ContentItem(
            kind="page", platform=self._platform(url),
            origin_url=url, repo=self._platform(url),
            path=url[:200], version_id=hashlib.sha256(f"{url}|{version_extra}".encode()).hexdigest()[:32],
            version_kind="none", text=text, size=len(text),
            published_at=published_at, published_source=published_source,
            published_confidence=published_confidence,
            extra={"http_content_type": resp.headers.get("content-type", "")},
        )

    def test_connection(self) -> dict:
        import httpx as _h

        url = (self.config.get("feed_url") or self.config.get("sitemap_url") or self.config.get("url") or "").strip()
        if not url:
            return {"ok": False, "message": "未配置 feed_url / sitemap_url / url"}
        try:
            resp = _h.get(url, timeout=15, follow_redirects=True,
                          headers={"User-Agent": "ccs-collector"})
        except _h.HTTPError as exc:
            return {"ok": False, "message": f"网络错误: {exc}"}
        if resp.status_code == 200:
            return {"ok": True, "message": f"可访问: {url}"}
        if resp.status_code in (403, 429):
            return {"ok": False, "message": f"触发限流或访问控制（{resp.status_code}）"}
        return {"ok": False, "message": f"意外状态码 {resp.status_code}"}
