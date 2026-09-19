from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from ..db import get_session
from ..models import Credential, Occurrence, ReviewLog, VerificationResult
from .. import services
from ..verification import worker as verification_worker

router = APIRouter()


class ReviewIn(BaseModel):
    action: str
    note: str | None = None


class BatchIn(BaseModel):
    ids: list[int]
    action: str | None = None
    note: str | None = None


def _cred_out(cred: Credential, occ_count: int = 0, locations: list[Occurrence] | None = None) -> dict:
    out = {
        "id": cred.id, "type": cred.type, "vendor": cred.vendor,
        "confidence": cred.confidence, "preview": cred.preview,
        "review_status": cred.review_status, "verification_status": cred.verification_status,
        "verified_at": cred.verified_at.isoformat() + "Z" if cred.verified_at else None,
        "rule_id": cred.rule_id,
        "first_seen_at": cred.first_seen_at.isoformat() + "Z" if cred.first_seen_at else None,
        "last_seen_at": cred.last_seen_at.isoformat() + "Z" if cred.last_seen_at else None,
        "occurrence_count": occ_count,
    }
    if locations is not None:
        out["locations"] = [{
            "id": o.id, "category": o.category, "platform": o.platform,
            "origin_url": o.origin_url, "repo": o.repo, "path": o.path,
            "line_start": o.line_start, "version_id": o.version_id,
            "version_kind": o.version_kind, "context_masked": o.context_masked,
            "detected_at": o.detected_at.isoformat() + "Z" if o.detected_at else None,
            "first_seen_at": o.first_seen_at.isoformat() + "Z" if o.first_seen_at else None,
            "last_seen_at": o.last_seen_at.isoformat() + "Z" if o.last_seen_at else None,
            "evidence": o.evidence_json,
        } for o in locations]
    return out


@router.get("/findings")
def list_findings(
    session: Session = Depends(get_session),
    q: str | None = None,
    type: str | None = None,
    review: str | None = None,
    verify: str | None = None,
    platform: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = session.query(Credential)
    if type:
        query = query.filter(Credential.type == type)
    if review:
        query = query.filter(Credential.review_status == review)
    if verify:
        query = query.filter(Credential.verification_status == verify)
    if q:
        like = f"%{q}%"
        query = query.filter((Credential.preview.like(like)) | (Credential.type.like(like)) | (Credential.vendor.like(like)))
    total = query.count()
    creds = query.order_by(Credential.last_seen_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    ids = [c.id for c in creds]
    counts: dict[int, int] = {}
    if ids:
        rows = session.query(Occurrence.credential_id, func.count(Occurrence.id))\
            .filter(Occurrence.credential_id.in_(ids)).group_by(Occurrence.credential_id).all()
        counts = dict(rows)
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_cred_out(c, counts.get(c.id, 0)) for c in creds]}


@router.get("/findings/{credential_id}")
def finding_detail(credential_id: int, session: Session = Depends(get_session)):
    cred = session.get(Credential, credential_id)
    if cred is None:
        raise HTTPException(404, "凭据不存在")
    locations = session.query(Occurrence).filter(Occurrence.credential_id == cred.id)\
        .order_by(Occurrence.first_seen_at).all()
    logs = session.query(ReviewLog).filter(ReviewLog.credential_id == cred.id)\
        .order_by(ReviewLog.id.desc()).all()
    history = session.query(VerificationResult).filter(VerificationResult.credential_id == cred.id)\
        .order_by(VerificationResult.id.desc()).all()
    out = _cred_out(cred, len(locations), locations)
    out["review_logs"] = [{
        "action": l.action, "note": l.note, "actor": l.actor,
        "created_at": l.created_at.isoformat() + "Z",
    } for l in logs]
    out["verification_history"] = [{
        "verifier_id": h.verifier_id, "verifier_version": h.verifier_version,
        "status": h.status, "evidence": h.evidence_json, "latency_ms": h.latency_ms,
        "created_at": h.created_at.isoformat() + "Z",
    } for h in history]
    return out


@router.post("/findings/{credential_id}/reveal")
def reveal(credential_id: int, session: Session = Depends(get_session)):
    """显式查看原文（写审计）。非必要不调用。"""
    try:
        secret = services.reveal_credential(session, credential_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"secret": secret}


@router.post("/findings/{credential_id}/review")
def review(credential_id: int, body: ReviewIn, session: Session = Depends(get_session)):
    try:
        cred = services.review_credential(session, credential_id, body.action, body.note)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"ok": True, "review_status": cred.review_status}


@router.post("/findings/batch-review")
def batch_review(body: BatchIn, session: Session = Depends(get_session)):
    ok, failed = 0, []
    for cid in body.ids:
        try:
            services.review_credential(session, cid, body.action or "", body.note)
            ok += 1
        except (ValueError, Exception):  # noqa: BLE001 - 单条失败不中断批量
            failed.append(cid)
    return {"ok": ok, "failed": failed}


@router.post("/findings/{credential_id}/verify")
def verify_single(credential_id: int, session: Session = Depends(get_session)):
    """提交单条验证。验证默认关闭；此处为显式手动请求。"""
    try:
        return verification_worker.enqueue(session, credential_id, "single")
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.post("/findings/batch-verify")
def verify_batch(body: BatchIn, session: Session = Depends(get_session)):
    return verification_worker.enqueue_batch(session, body.ids, "batch")
