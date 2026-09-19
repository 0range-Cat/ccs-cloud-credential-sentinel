from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_session
from .. import services

router = APIRouter()


@router.get("/overview/stats")
def stats(session: Session = Depends(get_session)):
    return services.overview_stats(session)


@router.get("/system/info")
def system_info(session: Session = Depends(get_session)):
    from ..detection.registry import get_registry
    from ..collectors.base import all_collectors
    from ..verification.base import all_verifiers
    s = get_settings()
    return {
        "app": s.app_name,
        "version": s.app_version,
        "db_url": s.resolved_db_url().split("///")[-1],
        "timezone_display": s.display_timezone,
        "rules_loaded": len(get_registry().rules),
        "collectors": sorted(all_collectors().keys()),
        "verifiers": sorted(all_verifiers().keys()),
    }
