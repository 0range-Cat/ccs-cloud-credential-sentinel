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


def test_seed_org_expansion(client, monkeypatch):
    """组织/用户种子 → 公开仓库列表自动扩展（mock 平台响应）。"""
    import app.api.discover as d

    monkeypatch.setattr(d, "fetch_repo_list",
                        lambda platform, org, token, limit: [f"{org}/repo{i}" for i in range(3)])
    resp = client.post("/api/discover/seed", json={
        "name_prefix": "组织验收", "github_orgs": ["octocat"],
        "max_repos_per_org": 3, "mode": "manual"})
    data = resp.json()
    assert data["count"] == 3
    assert any("扩展 3 个任务" in n for n in data["notes"])


def test_seed_org_failure_recorded_honestly(client, monkeypatch):
    import app.api.discover as d
    from fastapi import HTTPException

    def boom(platform, org, token, limit):
        raise HTTPException(404, "组织/用户不存在")
    monkeypatch.setattr(d, "fetch_repo_list", boom)
    resp = client.post("/api/discover/seed", json={
        "github_orgs": ["ghost-org"], "mode": "manual"})
    data = resp.json()
    assert data["count"] == 0
    assert any("扩展失败" in n and "不存在" in n for n in data["notes"]), "失败原因必须如实返回"
