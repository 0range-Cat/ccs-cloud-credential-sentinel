from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Credential, VerificationJob, VerificationResult
from ..verification.base import all_verifiers

router = APIRouter()


@router.get("/verification/jobs")
def list_jobs(session: Session = Depends(get_session), status: str | None = None):
    query = session.query(VerificationJob, Credential).join(
        Credential, VerificationJob.credential_id == Credential.id)
    if status:
        query = query.filter(VerificationJob.status == status)
    rows = query.order_by(VerificationJob.id.desc()).limit(100).all()
    return [{
        "id": j.id, "credential_id": j.credential_id, "preview": c.preview,
        "type": c.type, "verifier_id": j.verifier_id, "requested_by": j.requested_by,
        "status": j.status,
        "created_at": j.created_at.isoformat() + "Z" if j.created_at else None,
        "finished_at": j.finished_at.isoformat() + "Z" if j.finished_at else None,
    } for j, c in rows]


@router.get("/verification/history")
def history(session: Session = Depends(get_session), credential_id: int | None = None):
    query = session.query(VerificationResult, Credential).join(
        Credential, VerificationResult.credential_id == Credential.id)
    if credential_id:
        query = query.filter(VerificationResult.credential_id == credential_id)
    rows = query.order_by(VerificationResult.id.desc()).limit(200).all()
    return [{
        "id": r.id, "credential_id": r.credential_id, "preview": c.preview, "type": c.type,
        "verifier_id": r.verifier_id, "verifier_version": r.verifier_version,
        "status": r.status, "evidence": r.evidence_json, "latency_ms": r.latency_ms,
        "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
    } for r, c in rows]


@router.get("/verification/verifiers")
def verifiers():
    return [v.spec() for v in all_verifiers().values()]
