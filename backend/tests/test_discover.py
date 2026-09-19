"""种子发现 API 测试。"""
from app.models import Source


def test_seed_creates_multi_channel_tasks(client):
    resp = client.post("/api/discover/seed", json={
        "name_prefix": "验收",
        "github_repos": ["octocat/Hello-World"],
        "gitee_repos": ["demo/demo"],
        "wiki_api_urls": ["https://zh.wikipedia.org/w/api.php"],
        "feeds": ["https://feed.cnblogs.com/blog/sitehome/rss"],
        "sitemaps": ["https://site.example.org/sitemap.xml"],
        "urls": ["https://site.example.org/about"],
        "stackoverflow_keywords": ["api key"],
        "mode": "manual",
        "interval_sec": 300,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 7
    collectors = {c["collector"] for c in data["created"]}
    assert collectors == {"github", "gitee", "mediawiki", "generic_web(RSS)",
                          "generic_web(Sitemap)", "generic_web(URL)", "stackoverflow"}
    names = {s["name"] for s in client.get("/api/sources").json()}
    assert any(n.startswith("验收-GitHub-") for n in names)
    assert any(n.startswith("验收-Gitee-") for n in names)


def test_seed_keyword_note_is_honest(client):
    resp = client.post("/api/discover/seed", json={
        "stackoverflow_keywords": ["token"], "mode": "manual"})
    data = resp.json()
    assert data["count"] == 1
    assert data["notes"], "纯关键词必须返回代码搜索认证限制的如实说明"


def test_seed_rejects_bad_mode(client):
    resp = client.post("/api/discover/seed", json={"feeds": ["x"], "mode": "hourly"})
    assert resp.status_code == 400
