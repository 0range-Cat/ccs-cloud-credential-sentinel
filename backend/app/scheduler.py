"""持久化调度：APScheduler 心跳 + 数据库任务声明，重启可恢复，任务不重叠。"""
from __future__ import annotations

import logging
import random
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session

from .config import get_settings
from .db import SessionLocal, utcnow
from .models import ScanRun, Task
from .pipeline import run_task

log = logging.getLogger("ccs.scheduler")

_executor: ThreadPoolExecutor | None = None
_scheduler: BackgroundScheduler | None = None


def recover_interrupted(session: Session) -> int:
    """启动恢复：上次运行中的批次标记 interrupted，任务回到 pending 等待重新调度。"""
    n = 0
    for run in session.query(ScanRun).filter(ScanRun.status == "running").all():
        run.status = "interrupted"
        run.finished_at = utcnow()
        run.stats_json = {**(run.stats_json or {}), "stop_reason": "interrupted_by_restart"}
        n += 1
    for task in session.query(Task).filter(Task.status == "running").all():
        task.status = "pending"
        task.next_run_at = utcnow()
    session.commit()
    return n


def _tick() -> None:
    session: Session = SessionLocal()
    try:
        now = utcnow()
        due = session.query(Task).filter(
            Task.mode == "continuous",
            Task.status == "pending",
            Task.next_run_at <= now,
        ).all()
        for task in due:
            interval = max(30, int(task.interval_sec or 300))
            task.status = "running"
            task.next_run_at = now + timedelta(seconds=interval * random.uniform(0.9, 1.1))
            session.commit()
            assert _executor is not None
            _executor.submit(run_task, task.id, "schedule")
    finally:
        session.close()


def trigger_manual_run(task_id: int) -> dict:
    session: Session = SessionLocal()
    try:
        task = session.get(Task, task_id)
        if task is None:
            raise ValueError("任务不存在")
        if task.status == "running":
            return {"ok": False, "message": "任务正在运行中"}
        task.status = "running"
        session.commit()
    finally:
        session.close()
    if _executor is None:
        # 执行器未启动（测试/嵌入式调用）时同步执行，保证行为确定
        run_task(task_id, "manual")
        return {"ok": True, "message": "已同步执行完成"}
    _executor.submit(run_task, task_id, "manual")
    return {"ok": True, "message": "已提交执行"}


def start_background() -> None:
    global _executor, _scheduler
    settings = get_settings()
    if _executor is not None:
        return
    _executor = ThreadPoolExecutor(max_workers=max(1, settings.workers), thread_name_prefix="ccs-worker")
    session = SessionLocal()
    try:
        recovered = recover_interrupted(session)
        if recovered:
            log.warning("已恢复 %d 个中断批次", recovered)
    finally:
        session.close()
    _scheduler = BackgroundScheduler(timezone="UTC")
    _scheduler.add_job(_tick, "interval", seconds=settings.scheduler_tick_seconds,
                       id="ccs-tick", max_instances=1, coalesce=True)
    _scheduler.start()


def shutdown_background() -> None:
    global _executor, _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
    if _executor is not None:
        _executor.shutdown(wait=False, cancel_futures=True)
        _executor = None
