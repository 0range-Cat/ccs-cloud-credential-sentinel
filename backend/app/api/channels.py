from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Capability, RuleRecord
from ..detection.registry import get_registry
from ..collectors.base import all_collectors
from ..verification.base import all_verifiers

router = APIRouter()


@router.get("/channels")
def channels(session: Session = Depends(get_session)):
    caps = session.query(Capability).order_by(Capability.kind, Capability.id).all()
    return {
        "capabilities": [{
            "id": c.id, "kind": c.kind, "key": c.key, "title": c.title,
            "status": c.status, "meta": c.meta_json,
            "updated_at": c.updated_at.isoformat() + "Z" if c.updated_at else None,
        } for c in caps],
        "collectors": [{
            "key": cls.key, "category": cls.category, "platform": cls.platform,
            "title": cls.title, "version": cls.version,
        } for cls in all_collectors().values()],
        "verifiers": [v.spec() for v in all_verifiers().values()],
    }


@router.get("/rules")
def list_rules(session: Session = Depends(get_session)):
    rules = session.query(RuleRecord).order_by(RuleRecord.id).all()
    reg = get_registry()
    return [{
        "id": r.id, "title": r.title, "type": r.type, "vendor": r.vendor,
        "version": r.version, "license": r.license, "enabled": r.enabled,
        "verifier_id": r.verifier_id,
        "has_tests": bool(reg.by_id.get(r.id).tests.get("positives")) if r.id in reg.by_id else False,
    } for r in rules]


class RulePatch(BaseModel):
    enabled: bool


@router.patch("/rules/{rule_id}")
def patch_rule(rule_id: str, body: RulePatch, session: Session = Depends(get_session)):
    row = session.get(RuleRecord, rule_id)
    if row is None:
        raise HTTPException(404, "规则不存在")
    row.enabled = body.enabled
    session.commit()
    return {"id": row.id, "enabled": row.enabled}
