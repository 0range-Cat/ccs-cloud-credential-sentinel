from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session, utcnow
from ..models import ScanRun, Source, Task
from .. import scheduler

router = APIRouter()


class SourceIn(BaseModel):
    name: str
    collector_key: str
    config: dict = {}
    mode: str = "continuous"          # manual / continuous
    interval_sec: int = 300
    enabled: bool = True


def _task_out(task: Task, session: Session) -> dict:
    return {
        "id": task.id, "source_id": task.source_id, "mode": task.mode,
        "status": task.status, "interval_sec": task.interval_sec,
        "next_run_at": task.next_run_at.isoformat() + "Z" if task.next_run_at else None,
        "last_run_at": task.last_run_at.isoformat() + "Z" if task.last_run_at else None,
        "last_error": task.last_error,
    }


def _source_out(source: Source, session: Session) -> dict:
    task = session.query(Task).filter(Task.source_id == source.id).first()
    return {
        "id": source.id, "name": source.name, "category": source.category,
        "platform": source.platform, "collector_key": source.collector_key,
        "config": source.config_json, "enabled": source.enabled,
        "created_at": source.created_at.isoformat() + "Z",
        "task": _task_out(task, session) if task else None,
    }


@router.get("/sources")
def list_sources(session: Session = Depends(get_session)):
    sources = session.query(Source).order_by(Source.id.desc()).all()
    return [_source_out(s, session) for s in sources]


@router.post("/sources")
def create_source(body: SourceIn, session: Session = Depends(get_session)):
    from ..collectors.base import get_collector_class
    cls = get_collector_class(body.collector_key)
    if cls is None:
        raise HTTPException(400, f"未注册的采集器: {body.collector_key}")
    if body.mode not in ("manual", "continuous"):
        raise HTTPException(400, "mode 必须是 manual 或 continuous")
    source = Source(
        name=body.name, category=cls.category, platform=cls.platform,
        collector_key=body.collector_key, config_json=body.config, enabled=body.enabled,
    )
    session.add(source)
    session.flush()
    task = Task(source_id=source.id, mode=body.mode,
                interval_sec=max(30, body.interval_sec),
                status="pending",
                next_run_at=utcnow() if body.mode == "continuous" else None)
    session.add(task)
    session.commit()
    return _source_out(source, session)


@router.patch("/sources/{source_id}")
def update_source(source_id: int, body: dict, session: Session = Depends(get_session)):
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(404, "来源不存在")
    if "name" in body:
        source.name = body["name"]
    if "config" in body:
        source.config_json = body["config"]
    if "enabled" in body:
        source.enabled = bool(body["enabled"])
    if "interval_sec" in body:
        task = session.query(Task).filter(Task.source_id == source.id).first()
        if task:
            task.interval_sec = max(30, int(body["interval_sec"]))
    session.commit()
    return _source_out(source, session)


@router.delete("/sources/{source_id}")
def delete_source(source_id: int, session: Session = Depends(get_session)):
    source = session.get(Source, source_id)
    if source is None:
        raise HTTPException(404, "来源不存在")
    session.delete(source)
    session.commit()
    return {"ok": True}


@router.post("/sources/{source_id}/run")
def run_source(source_id: int, session: Session = Depends(get_session)):
    task = session.query(Task).filter(Task.source_id == source_id).first()
    if task is None:
        raise HTTPException(404, "来源没有任务")
    result = scheduler.trigger_manual_run(task.id)
    if not result.get("ok"):
        raise HTTPException(409, result.get("message", "无法启动"))
    return result


@router.get("/tasks")
def list_tasks(session: Session = Depends(get_session)):
    rows = session.query(Task, Source).join(Source, Task.source_id == Source.id)\
        .order_by(Task.id).all()
    return [{**_task_out(t, session), "source_name": s.name,
             "collector_key": s.collector_key, "enabled": s.enabled} for t, s in rows]


def _do_task_action(session: Session, task_id: int, action: str) -> dict:
    task = session.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "任务不存在")
    if action == "pause":
        task.status = "paused"
    elif action == "resume":
        task.status = "pending"
        task.next_run_at = utcnow()
        task.last_error = None
    elif action == "cancel":
        task.status = "cancelled"
    elif action == "retry":
        task.status = "pending"
        task.next_run_at = utcnow()
        task.last_error = None
    else:
        raise HTTPException(400, "未知操作")
    session.commit()
    return _task_out(task, session)


@router.post("/tasks/{task_id}/pause")
def pause_task(task_id: int, session: Session = Depends(get_session)):
    return _do_task_action(session, task_id, "pause")


@router.post("/tasks/{task_id}/resume")
def resume_task(task_id: int, session: Session = Depends(get_session)):
    return _do_task_action(session, task_id, "resume")


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: int, session: Session = Depends(get_session)):
    return _do_task_action(session, task_id, "cancel")


@router.post("/tasks/{task_id}/retry")
def retry_task(task_id: int, session: Session = Depends(get_session)):
    return _do_task_action(session, task_id, "retry")


@router.get("/tasks/{task_id}/runs")
def task_runs(task_id: int, session: Session = Depends(get_session)):
    runs = session.query(ScanRun).filter(ScanRun.task_id == task_id)\
        .order_by(ScanRun.id.desc()).limit(50).all()
    return [{
        "id": r.id, "status": r.status, "trigger": r.trigger,
        "started_at": r.started_at.isoformat() + "Z" if r.started_at else None,
        "finished_at": r.finished_at.isoformat() + "Z" if r.finished_at else None,
        "stats": r.stats_json,
    } for r in runs]
