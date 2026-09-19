"""种子驱动发现：一次性为目标生成多渠道监控任务。

诚实口径：仅根据用户提供的具体目标（仓库地址/站点 API/订阅源/关键词）生成任务；
GitHub/Gitee 的代码搜索接口需要认证且有结果上限，纯关键词不会自动生成代码搜索任务。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..collectors.base import get_collector_class
from ..db import get_session, utcnow
from ..models import Source, Task

router = APIRouter()


class SeedIn(BaseModel):
    name_prefix: str = "种子"
    github_repos: list[str] = []
    gitee_repos: list[str] = []
    wiki_api_urls: list[str] = []
    feeds: list[str] = []          # RSS/Atom 订阅源
    sitemaps: list[str] = []
    urls: list[str] = []
    stackoverflow_keywords: list[str] = []
    mode: str = "continuous"
    interval_sec: int = 300


def _create(session: Session, name: str, collector_key: str, config: dict,
            mode: str, interval_sec: int) -> int:
    cls = get_collector_class(collector_key)
    if cls is None:
        raise HTTPException(400, f"未注册的采集器: {collector_key}")
    source = Source(name=name[:190], category=cls.category, platform=cls.platform,
                    collector_key=collector_key, config_json=config, enabled=True)
    session.add(source)
    session.flush()
    task = Task(source_id=source.id, mode=mode, interval_sec=max(30, interval_sec),
                status="pending",
                next_run_at=utcnow() if mode == "continuous" else None)
    session.add(task)
    return source.id


@router.post("/discover/seed")
def discover_seed(body: SeedIn, session: Session = Depends(get_session)):
    if body.mode not in ("manual", "continuous"):
        raise HTTPException(400, "mode 必须是 manual 或 continuous")
    created: list[dict] = []
    notes: list[str] = []

    for repo in body.github_repos:
        sid = _create(session, f"{body.name_prefix}-GitHub-{repo}", "github", {"repo": repo},
                      body.mode, body.interval_sec)
        created.append({"source_id": sid, "collector": "github", "target": repo})
    for repo in body.gitee_repos:
        sid = _create(session, f"{body.name_prefix}-Gitee-{repo}", "gitee", {"repo": repo},
                      body.mode, body.interval_sec)
        created.append({"source_id": sid, "collector": "gitee", "target": repo})
    for api_url in body.wiki_api_urls:
        sid = _create(session, f"{body.name_prefix}-Wiki-{api_url[:60]}", "mediawiki",
                      {"api_url": api_url}, body.mode, body.interval_sec)
        created.append({"source_id": sid, "collector": "mediawiki", "target": api_url})
    for feed in body.feeds:
        sid = _create(session, f"{body.name_prefix}-RSS-{feed[:60]}", "generic_web",
                      {"feed_url": feed}, body.mode, body.interval_sec)
        created.append({"source_id": sid, "collector": "generic_web(RSS)", "target": feed})
    for sm in body.sitemaps:
        sid = _create(session, f"{body.name_prefix}-Sitemap-{sm[:60]}", "generic_web",
                      {"sitemap_url": sm}, body.mode, body.interval_sec)
        created.append({"source_id": sid, "collector": "generic_web(Sitemap)", "target": sm})
    for url in body.urls:
        sid = _create(session, f"{body.name_prefix}-URL-{url[:60]}", "generic_web",
                      {"url": url}, body.mode, body.interval_sec)
        created.append({"source_id": sid, "collector": "generic_web(URL)", "target": url})
    for kw in body.stackoverflow_keywords:
        sid = _create(session, f"{body.name_prefix}-SO-{kw[:40]}", "stackoverflow",
                      {"q": kw}, body.mode, body.interval_sec)
        created.append({"source_id": sid, "collector": "stackoverflow", "target": kw})

    if body.stackoverflow_keywords and not (body.github_repos or body.gitee_repos):
        notes.append("纯关键词已生成 Stack Overflow 监控；GitHub/Gitee 代码搜索需认证 Token 且有"
                     "结果上限（GitHub 10次/分、单查询1000条），如需代码搜索请在设置页配置 Token 后"
                     "单独创建仓库/组织任务，系统不做无认证的批量搜索。")

    session.commit()
    return {"created": created, "notes": notes, "count": len(created)}
