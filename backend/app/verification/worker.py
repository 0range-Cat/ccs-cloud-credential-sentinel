"""验证队列 worker：只处理显式入队任务；自动验证策略由设置开关控制。

- 每次验证追加 VerificationResult 历史，不覆盖。
- verdict 更新凭据当前 verification_status / verified_at；历史保留。
- per-verifier 简单限速（verification.max_per_minute）。
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from datetime import timedelta

import httpx

from ..config import get_settings
from ..db import SessionLocal, utcnow
from .. import settings_service
from ..models import Credential, VerificationJob, VerificationResult
from ..security import decrypt_text
from .base import CredentialView, get_verifier, verifier_for_type

log = logging.getLogger("ccs.verification")

_stop = threading.Event()
_thread: threading.Thread | None = None


def http_factory():
    """返回可直接使用的 httpx.AsyncClient（验证器契约：http_factory() 即客户端）。"""
    session_db = SessionLocal()
    try:
        proxy = settings_service.get_setting(session_db, "network.proxy") or None
        timeout = float(settings_service.get_setting(session_db, "network.timeout_seconds") or 20)
    finally:
        session_db.close()
    return httpx.AsyncClient(timeout=timeout, proxy=proxy, follow_redirects=False)


def enqueue(session, credential_id: int, requested_by: str = "single") -> dict:
    """手动/批量入口。无验证器的类型直接落 unsupported 结果（保留检测能力）。"""
    cred = session.get(Credential, credential_id)
    if cred is None:
        raise ValueError("凭据不存在")
    verifier = verifier_for_type(cred.type)
    if verifier is None:
        result = VerificationResult(
            credential_id=cred.id, verifier_id="-", verifier_version="-",
            status="unsupported",
            evidence_json={"reason": f"类型 {cred.type} 暂无符合最小验证要求的验证器"},
        )
        session.add(result)
        cred.verification_status = "unsupported"
        session.commit()
        return {"queued": False, "status": "unsupported"}
    job = VerificationJob(credential_id=cred.id, verifier_id=verifier.id, requested_by=requested_by)
    cred.verification_status = "queued"
    session.add(job)
    session.commit()
    return {"queued": True, "job_id": job.id, "verifier": verifier.id}


def enqueue_batch(session, credential_ids: list[int], requested_by: str = "batch") -> dict:
    out = {"queued": 0, "unsupported": 0}
    for cid in credential_ids:
        try:
            if enqueue(session, cid, requested_by).get("queued"):
                out["queued"] += 1
            else:
                out["unsupported"] += 1
        except ValueError:
            continue
    return out


def auto_enqueue_due(session, limit: int = 5) -> int:
    """自动验证策略（T4.1）。仅当 verification.auto_enabled 开启时由调度 tick 调用：
    - not_requested 且类型有验证器 → 入队
    - valid/invalid 且 verified_at 超过 reverify_days → 重新入队
    - rate_limited/network_error/error/inconclusive 且 verified_at 超过 1 小时 → 重试入队
    每次调用限量（limit），防止队列积压；queued/running 不重复入队。
    """
    from .base import all_verifiers

    if not settings_service.get_setting(session, "verification.auto_enabled"):
        return 0
    supported = {t for v in all_verifiers().values() for t in v.supported_types}
    now = utcnow()
    reverify_days = int(settings_service.get_setting(session, "verification.reverify_days") or 30)
    enqueued = 0

    pending = session.query(Credential).filter(Credential.verification_status == "not_requested").all()
    for cred in pending:
        if enqueued >= limit:
            break
        if cred.type not in supported:
            continue
        if enqueue(session, cred.id, "auto").get("queued"):
            enqueued += 1

    if enqueued < limit:
        reverify_cut = now - __import__("datetime").timedelta(days=reverify_days)
        stale = session.query(Credential).filter(
            Credential.verification_status.in_(("valid", "invalid")),
            Credential.verified_at.isnot(None),
            Credential.verified_at < reverify_cut).all()
        for cred in stale:
            if enqueued >= limit:
                break
            if enqueue(session, cred.id, "auto").get("queued"):
                enqueued += 1

    if enqueued < limit:
        retry_cut = now - __import__("datetime").timedelta(hours=1)
        transient = session.query(Credential).filter(
            Credential.verification_status.in_(("rate_limited", "network_error", "error", "inconclusive")),
            Credential.verified_at.isnot(None),
            Credential.verified_at < retry_cut).all()
        for cred in transient:
            if enqueued >= limit:
                break
            if enqueue(session, cred.id, "auto").get("queued"):
                enqueued += 1
    return enqueued


def _process_job(session, job: VerificationJob, http_factory_override=None) -> None:
    cred = session.get(Credential, job.credential_id)
    verifier = get_verifier(job.verifier_id)
    if cred is None or verifier is None:
        job.status = "finished"
        job.finished_at = utcnow()
        return
    job.status = "running"
    job.started_at = utcnow()
    cred.verification_status = "running"
    session.commit()

    view = CredentialView(id=cred.id, type=cred.type,
                          secret=decrypt_text(cred.secret_encrypted) or "",
                          paired=json.loads(decrypt_text(cred.paired_encrypted) or "{}") if cred.paired_encrypted else {})
    missing = verifier.missing_context(view)
    if missing:
        outcome_status, evidence, latency = "missing_context", {"reason": missing}, None
    else:
        factory = http_factory_override or http_factory
        try:
            outcome = asyncio.run(verifier.verify(view, factory))
            outcome_status, evidence, latency = outcome.status, outcome.evidence, outcome.latency_ms
        except Exception as exc:  # 验证器自身异常
            outcome_status, evidence, latency = "error", {"reason": f"{type(exc).__name__}"}, None

    session.add(VerificationResult(
        job_id=job.id, credential_id=cred.id, verifier_id=verifier.id,
        verifier_version=verifier.version, status=outcome_status,
        evidence_json=evidence, latency_ms=latency,
    ))
    cred.verification_status = outcome_status
    cred.verified_at = utcnow()
    job.status = "finished"
    job.finished_at = utcnow()
    session.commit()
    log.info("验证完成 cred=%s verifier=%s status=%s", cred.id, verifier.id, outcome_status)


def _loop() -> None:
    settings = get_settings()
    last_run_at: dict[str, float] = {}
    while not _stop.is_set():
        session = SessionLocal()
        try:
            job = session.query(VerificationJob).filter(
                VerificationJob.status == "queued").order_by(VerificationJob.id).first()
            if job is None:
                _stop.wait(5)
                continue
            per_min = float(settings_service.get_setting(session, "verification.max_per_minute") or 10)
            min_interval = 60.0 / max(1.0, per_min)
            waited = time.monotonic() - last_run_at.get(job.verifier_id, 0)
            if waited < min_interval:
                _stop.wait(min_interval - waited)
            job = session.get(VerificationJob, job.id)
            if job is None or job.status != "queued":
                continue
            _process_job(session, job)
            last_run_at[job.verifier_id] = time.monotonic()
        except Exception:
            log.exception("验证 worker 异常")
            _stop.wait(5)
        finally:
            session.close()


def start_worker() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="ccs-verifier", daemon=True)
    _thread.start()


def stop_worker() -> None:
    _stop.set()
