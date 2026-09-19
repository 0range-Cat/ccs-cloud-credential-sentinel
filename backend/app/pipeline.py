"""扫描流水线：领取任务 → 采集 → 检测 → 入库去重 → 更新统计。

预算控制（items/bytes/time）在迭代中逐项检查；限流属正常停止而非失败；
本流水线不调用任何验证逻辑（验证模块独立，默认关闭）。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from datetime import timedelta

from sqlalchemy.orm import Session

from .collectors.base import BaseCollector, CollectorError, get_collector_class
from .db import SessionLocal, utcnow
from .detection.engine import DetectionEngine
from .detection.registry import get_registry
from . import services, settings_service
from .models import ScanRun, Source, SourceContent, Task

ENGINE = DetectionEngine()


def _merge_config(session: Session, source: Source) -> dict:
    cfg = dict(source.config_json or {})
    # 默认预算来自设置（来源配置可覆盖）
    cfg.setdefault("max_file_bytes", settings_service.get_setting(session, "scan.max_file_bytes"))
    cfg.setdefault("max_items", settings_service.get_setting(session, "scan.max_items"))
    cfg.setdefault("max_bytes", settings_service.get_setting(session, "scan.max_bytes"))
    cfg.setdefault("max_seconds", settings_service.get_setting(session, "scan.max_seconds"))
    return cfg


def _build_collector(session: Session, source: Source, config: dict) -> BaseCollector:
    cls = get_collector_class(source.collector_key)
    if cls is None:
        raise CollectorError(f"未注册的采集器: {source.collector_key}")
    kwargs: dict = {}
    if source.collector_key == "github":
        kwargs["token"] = settings_service.get_setting(session, "platform.github.token") or ""
    return cls(config, **kwargs)


def run_task(task_id: int, trigger: str = "manual") -> dict:
    session: Session = SessionLocal()
    stats: dict = {
        "items_seen": 0, "items_new": 0, "items_skipped": 0, "candidates": 0,
        "new_credentials": 0, "new_occurrences": 0, "errors": 0,
        "stop_reason": "completed", "rate_limited": False,
    }
    try:
        task = session.get(Task, task_id)
        if task is None:
            return {"skipped": "task_missing"}
        if task.status == "running":
            return {"skipped": "already_running"}
        source = session.get(Source, task.source_id)
        if source is None or not source.enabled:
            task.status = "paused"
            task.last_error = "来源已禁用"
            session.commit()
            return {"skipped": "source_disabled"}

        task.status = "running"
        task.last_error = None
        run = ScanRun(task_id=task.id, status="running", trigger=trigger)
        session.add(run)
        session.commit()

        config = _merge_config(session, source)
        try:
            collector = _build_collector(session, source, config)
            _execute(session, collector, source, run, config, stats)
        except CollectorError as exc:
            stats["stop_reason"] = "collector_error"
            stats["error"] = str(exc)
            run.status = "failed"
            task.status = "failed"
            task.last_error = str(exc)
        except Exception as exc:  # 未知异常：记录并让任务失败，不影响其他渠道
            stats["stop_reason"] = "internal_error"
            stats["error"] = f"{type(exc).__name__}: {exc}"
            run.status = "failed"
            task.status = "failed"
            task.last_error = stats["error"]
        else:
            run.status = "completed"
            task.status = "pending" if task.mode == "continuous" else "done"

        run.stats_json = stats
        run.finished_at = utcnow()
        task.last_run_at = utcnow()
        if task.status == "pending":
            interval = max(30, int(task.interval_sec or 300))
            task.next_run_at = utcnow() + timedelta(seconds=interval * random.uniform(0.9, 1.1))
        session.commit()
        return stats
    finally:
        session.close()


def _execute(session: Session, collector: BaseCollector, source: Source,
             run: ScanRun, config: dict, stats: dict) -> None:
    deadline = time.monotonic() + int(config.get("max_seconds") or 1800)
    max_items = int(config.get("max_items") or 2000)
    max_bytes = int(config.get("max_bytes") or 512 * 1024 * 1024)
    seen_bytes = 0
    ignore_loaded = False
    registry = get_registry()

    async def _run() -> None:
        nonlocal seen_bytes, ignore_loaded
        ignore_rules = None
        async for item in collector.items():
            stats["items_seen"] += 1
            seen_bytes += item.size or 0
            if stats["items_seen"] > max_items:
                stats["stop_reason"] = "budget_items"
                break
            if seen_bytes > max_bytes:
                stats["stop_reason"] = "budget_bytes"
                break
            if time.monotonic() > deadline:
                stats["stop_reason"] = "budget_time"
                break

            text = item.text or ""
            content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            exists = session.query(SourceContent.id).filter_by(
                source_id=source.id, version_id=item.version_id,
                path=item.path, content_hash=content_hash).first()
            if exists:
                stats["items_skipped"] += 1
                continue

            stored = text
            truncated = False
            if len(text) > 200_000:
                stored, truncated = text[:200_000], True
            row = SourceContent(
                source_id=source.id, run_id=run.id, kind=item.kind,
                platform=item.platform, origin_url=item.origin_url, repo=item.repo,
                path=item.path, version_id=item.version_id,
                version_kind=item.version_kind, content_hash=content_hash,
                content=stored, content_truncated=truncated, size=item.size,
                published_at=item.published_at, published_source=item.published_source,
                published_confidence=item.published_confidence,
                source_updated_at=item.source_updated_at, fetched_at=item.fetched_at,
                detection_status="done",
            )
            session.add(row)
            session.flush()

            if not ignore_loaded:
                ignore_rules = True
                ignore_loaded = True
            candidates = [c for c in ENGINE.scan(text, path=item.path)
                          if not c.evidence.get("rejected_candidate")]
            stats["candidates"] += len(candidates)
            for cand in candidates:
                reason = services.match_ignore_rules(session, cand, _source_category(source), item.path)
                result = services.ingest_candidate(session, item, row.id, run.id, cand, reason)
                stats["new_credentials"] += 1 if result["credential_created"] else 0
                stats["new_occurrences"] += 1 if result["occurrence_created"] else 0
            session.commit()
            if collector.rate_limited:
                stats["rate_limited"] = True
                stats["stop_reason"] = "rate_limited"
                break

    asyncio.run(_run())


def _source_category(source: Source) -> str:
    cls = get_collector_class(source.collector_key)
    return cls.category if cls else source.category
