"""阶段2 采集器测试：Gitee / MediaWiki / 通用RSS·Sitemap / StackOverflow / GitHub历史。

平台响应均为样例注入；GitHub 历史验证游标增量（第二次运行不重复扫描）。
"""
import asyncio
import base64
from datetime import datetime

import httpx

from app.collectors.gitee import GiteeCollector, parse_gitee_repo
from app.collectors.mediawiki import MediaWikiCollector
from app.collectors.generic_web import GenericWebCollector, html_to_text
from app.collectors.stackoverflow import StackOverflowCollector
from app.collectors.github import GitHubCollector
from app.collectors.base import CollectorError
from app import pipeline
from app.models import Cursor, Source, Task


def collect(collector):
    async def _run():
        return [item async for item in collector.items()]
    return asyncio.run(_run())


# ---------------- Gitee ----------------

def _gitee(responder, token=""):
    def factory(headers):
        return httpx.AsyncClient(base_url="https://gitee.com/api/v5", headers=headers,
                                 transport=httpx.MockTransport(responder), timeout=5,
                                 follow_redirects=False)
    return GiteeCollector({"repo": "demo/demo"}, client_factory=factory, token=token)


def test_gitee_happy_path():
    token = "ghp_" + "a" * 36

    def responder(request: httpx.Request) -> httpx.Response:
        path = request.url.path  # base_url 含 /api/v5，路径带前缀
        if path == "/api/v5/repos/demo/demo":
            return httpx.Response(200, json={"default_branch": "master", "full_name": "demo/demo"})
        if path == "/api/v5/repos/demo/demo/git/trees/master":
            return httpx.Response(200, json={"tree": [
                {"type": "blob", "path": "conf/app.ini", "sha": "blob1", "size": 40}]})
        if path == "/api/v5/repos/demo/demo/git/blobs/blob1":
            return httpx.Response(200, json={"encoding": "base64",
                                             "content": base64.b64encode(f"token = {token}".encode()).decode()})
        return httpx.Response(404)

    items = collect(_gitee(responder))
    assert len(items) == 1
    assert items[0].origin_url == "https://gitee.com/demo/demo/blob/master/conf/app.ini"
    assert items[0].version_kind == "blob"
    assert items[0].published_confidence == "none"


def test_gitee_rate_limit_and_auth():
    def limited(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/repos/demo/demo"):
            return httpx.Response(200, json={"default_branch": "master", "full_name": "demo/demo"})
        if request.url.path.endswith("trees/master"):
            return httpx.Response(200, json={"tree": [
                {"type": "blob", "path": f"f{i}.txt", "sha": f"s{i}", "size": 10} for i in range(3)]})
        return httpx.Response(403, json={})

    c = _gitee(limited)
    assert collect(c) == [] and c.rate_limited is True

    def unauthorized(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={})

    try:
        collect(_gitee(unauthorized, token="bad"))
        raise AssertionError("401 应触发 CollectorError")
    except CollectorError:
        pass


def test_gitee_repo_parse():
    assert parse_gitee_repo("https://gitee.com/o/r") == "o/r"
    assert parse_gitee_repo("o/r") == "o/r"


# ---------------- MediaWiki ----------------

def _mediawiki(responder):
    def factory(headers):
        return httpx.AsyncClient(headers=headers,
                                 transport=httpx.MockTransport(responder), timeout=5,
                                 follow_redirects=False)
    return MediaWikiCollector({"api_url": "https://wiki.example.org/w/api.php", "max_items": 10},
                              client_factory=factory)


def test_mediawiki_recentchanges_with_trusted_publish_time():
    calls = {"rc": 0}

    def responder(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if params.get("list") == "recentchanges":
            calls["rc"] += 1
            if calls["rc"] == 1:
                return httpx.Response(200, json={
                    "query": {"recentchanges": [
                        {"type": "edit", "pageid": 7, "revid": 100, "title": "Page A",
                         "timestamp": "2026-09-19T01:00:00Z"},
                        {"type": "log", "pageid": 8, "revid": 101, "title": "Log E",
                         "timestamp": "2026-09-19T01:01:00Z"},
                    ]},
                    "continue": {"rccontinue": "20260919010000|100"}})
            return httpx.Response(200, json={"query": {"recentchanges": []}})
        if params.get("prop") == "revisions":
            revids = params["revids"].split("|")
            assert revids == ["100"], "log 类型变更不应取内容"
            return httpx.Response(200, json={"query": {"pages": [
                {"pageid": 7, "title": "Page A", "revisions": [
                    {"revid": 100, "timestamp": "2026-09-19T01:00:00Z",
                     "content": "api_key = J8kQ2wL5vB8nM4cR6tZ0aS3dF7yG1x"}]}]}})
        return httpx.Response(400)

    c = _mediawiki(responder)
    items = collect(c)
    assert len(items) == 1
    item = items[0]
    assert item.version_id == "rev-100" and item.version_kind == "revision"
    assert item.published_at == datetime(2026, 9, 19, 1, 0)
    assert item.published_confidence == "medium", "修订时间戳=可信公开时间"
    assert item.published_source == "mediawiki_revision_timestamp"
    assert "api_key" in item.text
    assert c.cursors.get("rccontinue") == "20260919010000|100", "游标必须写回供增量续扫"


def test_mediawiki_bad_api_url():
    try:
        collect(MediaWikiCollector({"api_url": "not-a-url"}))
        raise AssertionError
    except CollectorError:
        pass


# ---------------- 通用 RSS / Sitemap / URL ----------------

def _web(responder):
    def factory(headers):
        return httpx.AsyncClient(headers=headers,
                                 transport=httpx.MockTransport(responder), timeout=5,
                                 follow_redirects=True)
    return GenericWebCollector


RSS_XML = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>demo feed</title>
<item><title>Post A</title><link>https://blog.example.org/a</link>
<pubDate>Tue, 01 Sep 2026 00:00:00 GMT</pubDate>
<description>&lt;p&gt;SECRET_KEY=J8kQ2wL5vB8nM4cR6tZ0aS3dF7yG1x&lt;/p&gt;</description></item>
</channel></rss>"""

SITEMAP_XML = """<?xml version="1.0"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://site.example.org/page1</loc><lastmod>2026-09-01</lastmod></url>
<url><loc>https://site.example.org/page2</loc></url>
</urlset>"""


def test_rss_items_with_published_time():
    def responder(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "blog.example.org"
        return httpx.Response(200, text=RSS_XML, headers={"etag": '"v1"'})

    c = GenericWebCollector({"feed_url": "https://blog.example.org/feed.xml"}, client_factory=responder_factory(responder))
    items = collect(c)
    assert len(items) == 1
    item = items[0]
    assert item.platform == "blog.example.org"
    assert item.published_at == datetime(2026, 9, 1)
    assert item.published_source == "rss_published" and item.published_confidence == "medium"
    assert "SECRET_KEY" in item.text and "<p>" not in item.text, "HTML 必须被剥离"
    assert c.cursors.get("etag:" + __import__("hashlib").sha256(b"https://blog.example.org/feed.xml").hexdigest()[:16]) == '"v1"'


def responder_factory(responder):
    def factory(headers):
        return httpx.AsyncClient(headers=headers,
                                 transport=httpx.MockTransport(responder), timeout=5,
                                 follow_redirects=True)
    return factory


def test_sitemap_pages_and_low_confidence_time():
    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sitemap.xml":
            return httpx.Response(200, text=SITEMAP_XML)
        page = "token: ghp_" + "b" * 36
        return httpx.Response(200, text=f"<html><body>{page}</body></html>")

    c = GenericWebCollector({"sitemap_url": "https://site.example.org/sitemap.xml", "max_items": 5},
                            client_factory=responder_factory(responder))
    items = collect(c)
    assert [i.origin_url for i in items] == [
        "https://site.example.org/page1", "https://site.example.org/page2"]
    assert items[0].published_source == "sitemap_lastmod"
    assert items[0].published_confidence == "low", "sitemap lastmod 为站点自述，低可信"
    assert items[1].published_confidence == "none"


def test_rss_304_not_modified_skips():
    import hashlib
    calls = {"n": 0}
    feed_url = "https://x.example.org/f.xml"
    cursor_key = hashlib.sha256(feed_url.encode()).hexdigest()[:16]

    def responder(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if request.headers.get("if-none-match") == '"v1"':
            return httpx.Response(304)
        return httpx.Response(200, text=RSS_XML, headers={"etag": '"v1"'})

    cursors = {f"etag:{cursor_key}": '"v1"'}
    c = GenericWebCollector({"feed_url": feed_url}, client_factory=responder_factory(responder), cursor_store=cursors)
    items = collect(c)
    assert items == []
    assert calls["n"] == 1


def test_html_to_text():
    assert html_to_text("<script>evil()</script><p>a &amp; b</p>") == "a & b"


# ---------------- Stack Overflow ----------------

def test_stackoverflow_two_step():
    def responder(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/2.3/search/advanced":
            assert request.url.params["q"] == "api key"
            return httpx.Response(200, json={
                "quota_remaining": 290, "backoff": 0,
                "items": [
                    {"question_id": 11, "link": "https://stackoverflow.com/q/11",
                     "title": "How to store keys", "creation_date": 1787000000,
                     "last_activity_date": 1787000100, "score": 3, "tags": ["api"]},
                    {"question_id": 12, "link": "https://stackoverflow.com/q/12",
                     "title": "Token leak", "creation_date": 1787000001,
                     "last_activity_date": 1787000101, "score": 0, "tags": []},
                ]})
        if request.url.path == "/2.3/questions/11;12":
            return httpx.Response(200, json={
                "quota_remaining": 289,
                "items": [
                    {"question_id": 11, "body": "<p>use env vars</p>"},
                    {"question_id": 12, "body": "<p>token=Ab12Cd34Ef56Gh78Ij90Kl12Mn34</p>"},
                ]})
        return httpx.Response(400)

    c = StackOverflowCollector({"q": "api key", "max_items": 10}, client_factory=responder_factory(responder))
    items = collect(c)
    assert len(items) == 2
    assert items[0].version_id == "q-11-1787000100"
    assert items[0].published_confidence == "medium"
    assert "<p>" not in items[1].text and "token=Ab12Cd34Ef56Gh78Ij90Kl12Mn34" in items[1].text


def test_stackoverflow_quota_exhausted_stops():
    def responder(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"quota_remaining": 0, "items": []})

    c = StackOverflowCollector({"q": "x"}, client_factory=responder_factory(responder))
    assert collect(c) == [] and c.rate_limited is True


# ---------------- GitHub 历史扫描 + 游标增量 ----------------

def _github_history(responder, cursors=None, config=None):
    def factory(headers):
        return httpx.AsyncClient(base_url="https://api.github.com", headers=headers,
                                 transport=httpx.MockTransport(responder), timeout=5,
                                 follow_redirects=False)
    cfg = {"repo": "demo/demo", "fetch_history": True, "history_max_commits": 10}
    cfg.update(config or {})
    return GitHubCollector(cfg, client_factory=factory, cursor_store=cursors)


def test_github_history_scan_and_cursor_increment():
    blob = base64.b64encode(b"GH_TOKEN=ghp_" + b"c" * 36).decode()
    requests_log = []

    def responder(request: httpx.Request) -> httpx.Response:
        requests_log.append(request.url.path)
        path = request.url.path
        if path == "/repos/demo/demo":
            return httpx.Response(200, json={"default_branch": "main", "full_name": "demo/demo"})
        if path == "/repos/demo/demo/git/trees/main":
            return httpx.Response(200, json={"sha": "t", "tree": [], "truncated": False})
        if path == "/repos/demo/demo/commits":
            assert request.url.params["page"] == "1"
            return httpx.Response(200, json=[
                {"sha": "c2"}, {"sha": "c1"}])
        if path == "/repos/demo/demo/commits/c2":
            return httpx.Response(200, json={
                "commit": {"committer": {"date": "2026-09-01T00:00:00Z"}, "message": "add env"},
                "files": [{"filename": ".env", "status": "added", "sha": "blobC2"}]})
        if path == "/repos/demo/demo/commits/c1":
            return httpx.Response(200, json={
                "commit": {"committer": {"date": "2026-08-01T00:00:00Z"}, "message": "init"},
                "files": [{"filename": "README.md", "status": "added", "sha": "blobC1"}]})
        if path == "/repos/demo/demo/git/blobs/blobC2":
            return httpx.Response(200, json={"encoding": "base64", "content": blob})
        return httpx.Response(404)

    cursors: dict = {}
    c = _github_history(responder, cursors=cursors)
    items = collect(c)
    assert len(items) == 1, "只扫描了 c2 的 .env（c1 只有 README，未在本 mock 提供内容）"
    item = items[0]
    assert item.version_kind == "commit"
    assert item.published_at == datetime(2026, 9, 1)
    assert item.published_source == "git_commit_date"
    assert item.published_confidence == "low", "提交时间只能作低可信公开时间"
    assert item.extra["commit_sha"] == "c2"
    assert cursors.get("last_commit_scanned") == "c2"

    # 第二次运行：游标生效，不再重复扫描
    c2 = _github_history(responder, cursors=dict(cursors))
    assert collect(c2) == []


# ---------------- 游标持久化 ----------------

def test_pipeline_persists_cursors(db):
    source = Source(name="cursor-test", category="code_hosting", platform="mediawiki",
                    collector_key="mediawiki", config_json={"api_url": "https://x/w/api.php"}, enabled=True)
    db.add(source)
    db.flush()
    task = Task(source_id=source.id, mode="manual", interval_sec=300, status="pending")
    db.add(task)
    db.commit()
    pipeline._persist_cursors(db, task.id, {"rccontinue": "2026|1"})
    row = db.query(Cursor).filter_by(task_id=task.id, cursor_key="rccontinue").one()
    assert row.cursor_value == "2026|1"
    pipeline._persist_cursors(db, task.id, {"rccontinue": "2026|2"})
    db.expire_all()
    row = db.query(Cursor).filter_by(task_id=task.id, cursor_key="rccontinue").one()
    assert row.cursor_value == "2026|2"
