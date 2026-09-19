"""真实渠道 live 检查：对可直连的公开渠道执行完整流水线（采集→检测→入库→去重），
并做第二轮运行验证增量语义（版本缓存/游标/条件请求）。

用法：cd backend && .venv/Scripts/python ../scripts/live_check.py
独立 DB：data/live.db；全部预算收紧（防止对目标站点造成压力）。
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("CCS_DATA_DIR", str(ROOT / "data"))
os.environ.setdefault("CCS_DB_URL", f"sqlite:///{(ROOT / 'data' / 'live.db').as_posix()}")
os.environ.setdefault("CCS_BACKGROUND", "false")
sys.path.insert(0, str(ROOT / "backend"))

from app.db import Base, SessionLocal, engine  # noqa: E402
import app.models  # noqa: E402,F401
from app.models import Source, Task  # noqa: E402
from app import pipeline, services  # noqa: E402
from app.detection.registry import get_registry  # noqa: E402

BUDGET = {"max_items": 6, "max_seconds": 120, "rate_per_sec": 2.0}

TARGETS = [
    ("Gitee 公开仓库（openharmony/docs 首页目录）", "gitee", {**BUDGET, "repo": "openharmony/docs"}),
    ("中文维基百科 recentchanges", "mediawiki",
     {**BUDGET, "api_url": "https://zh.wikipedia.org/w/api.php", "namespaces": "0"}),
    ("博客园首页 RSS", "generic_web",
     {**BUDGET, "feed_url": "https://feed.cnblogs.com/blog/sitehome/rss"}),
    ("Stack Overflow 关键词", "stackoverflow",
     {**BUDGET, "q": "api key", "site": "stackoverflow"}),
]


def main() -> None:
    Base.metadata.create_all(engine)
    session = SessionLocal()
    services.sync_rule_records(session, get_registry())
    services.seed_capabilities(session)
    report = []
    try:
        for name, collector_key, config in TARGETS:
            source = Source(name=f"live-{name}", category="live_check",
                            platform=collector_key, collector_key=collector_key,
                            config_json=config, enabled=True)
            session.add(source)
            session.flush()
            task = Task(source_id=source.id, mode="manual", interval_sec=300, status="pending")
            session.add(task)
            session.commit()

            s1 = pipeline.run_task(task.id, "manual")
            s2 = pipeline.run_task(task.id, "manual")
            row = {"target": name, "collector": collector_key,
                   "round1": {k: s1.get(k) for k in
                              ("items_seen", "candidates", "new_credentials", "new_occurrences",
                               "stop_reason", "rate_limited", "error")},
                   "round2": {k: s2.get(k) for k in
                              ("items_seen", "items_skipped", "candidates", "new_credentials",
                               "new_occurrences", "stop_reason", "error")}}
            report.append(row)
            print(json.dumps(row, ensure_ascii=False, indent=2))

        stats = services.overview_stats(session)
        summary = {
            "credentials_total": stats["credentials_total"],
            "occurrences_total": stats["occurrences_total"],
            "by_type_top": stats["by_type_top"][:10],
            "detection_latency": stats["detection_latency"],
        }
        print("SUMMARY:", json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        session.close()


if __name__ == "__main__":
    main()
