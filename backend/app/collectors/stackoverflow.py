"""Stack Overflow 采集器：公开 API（免 key 匿名配额 300/天，>30 req/s 丢包）。

两步：search/advanced 找问题 → questions/{ids}?filter=withbody 取正文。
尊重响应中的 backoff 字段；quota_remaining=0 或 403/429 → 优雅停止。
创建时间 = 问题公开发布时间（confidence=medium）。
"""
from __future__ import annotations

import asyncio
from datetime import datetime

import httpx

from .base import USER_AGENT, BaseCollector, ContentItem, CollectorError, register
from .generic_web import html_to_text

DEFAULT_SITE = "stackoverflow"


def _ts(value) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=__import__("datetime").timezone.utc).replace(tzinfo=None)
    except (ValueError, OSError):
        return None


@register
class StackOverflowCollector(BaseCollector):
    key = "stackoverflow"
    category = "knowledge"
    platform = "stackoverflow"
    title = "Stack Overflow 关键词监控"

    def __init__(self, config: dict, client_factory=None, cursor_store: dict | None = None):
        super().__init__(config, cursor_store)
        self._client_factory = client_factory

    def _client(self) -> httpx.AsyncClient:
        headers = {"User-Agent": USER_AGENT}
        if self._client_factory is not None:
            return self._client_factory(headers)
        return httpx.AsyncClient(headers=headers, timeout=25, follow_redirects=False)

    async def _get(self, client, url: str, params: dict):
        resp = await client.get(url, params=params)
        if resp.status_code in (403, 429, 503):
            self.rate_limited = True
            return None
        if resp.status_code != 200:
            return None
        data = resp.json()
        backoff = int(data.get("backoff") or 0)
        if backoff > 0:
            await asyncio.sleep(min(backoff, 30))
        quota = data.get("quota_remaining")
        if quota is not None and int(quota) <= 0:
            self.rate_limited = True
            return None
        return data

    async def items(self):
        keyword = (self.config.get("q") or self.config.get("keyword") or "").strip()
        if not keyword:
            raise CollectorError("需要配置关键词 q")
        site = self.config.get("site") or DEFAULT_SITE
        max_items = int(self.config.get("max_items") or 30)
        tagged = self.config.get("tagged")
        async with self._client() as client:
            params = {
                "order": "desc", "sort": "activity", "site": site,
                "pagesize": min(50, max_items),
            }
            if tagged:
                params["tagged"] = tagged
            # URL 编码交给 httpx
            data = await self._get(client, "https://api.stackexchange.com/2.3/search/advanced",
                                   {**params, "q": keyword})
            if data is None:
                return
            questions = data.get("items", [])
            if not questions:
                return
            ids = ";".join(str(q["question_id"]) for q in questions[:max_items])
            detail = await self._get(client, f"https://api.stackexchange.com/2.3/questions/{ids}",
                                     {**params, "filter": "withbody"})
            if detail is None:
                return
            by_id = {q["question_id"]: q for q in detail.get("items", [])}
            for q in questions[:max_items]:
                full = by_id.get(q["question_id"], q)
                body = full.get("body") or full.get("body_markdown") or ""
                title = full.get("title") or ""
                text = f"{title}\n\n{html_to_text(body)}".strip()
                if not text:
                    continue
                yield ContentItem(
                    kind="page", platform=self.platform,
                    origin_url=full.get("link"), repo=site,
                    path=f"q/{q['question_id']}", version_id=f"q-{q['question_id']}-{q.get('last_activity_date')}",
                    version_kind="none", text=text, size=len(text),
                    published_at=_ts(q.get("creation_date")),
                    published_source="so_creation_date", published_confidence="medium",
                    source_updated_at=_ts(q.get("last_activity_date")),
                    extra={"score": q.get("score"), "tags": q.get("tags", [])},
                )

    def test_connection(self) -> dict:
        import httpx as _h

        try:
            resp = _h.get("https://api.stackexchange.com/2.3/info",
                          params={"site": self.config.get("site") or DEFAULT_SITE}, timeout=15)
        except _h.HTTPError as exc:
            return {"ok": False, "message": f"网络错误: {exc}"}
        if resp.status_code == 200:
            quota = resp.json().get("quota_remaining")
            return {"ok": True, "message": f"API 可访问，今日剩余配额 {quota}"}
        if resp.status_code in (403, 429, 503):
            return {"ok": False, "message": f"触发限流（{resp.status_code}）"}
        return {"ok": False, "message": f"意外状态码 {resp.status_code}"}
