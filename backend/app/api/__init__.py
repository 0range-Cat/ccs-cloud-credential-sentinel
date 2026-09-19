"""API 路由组装。默认脱敏；reveal 需显式请求并留审计。"""
from __future__ import annotations

from fastapi import APIRouter

from . import overview, sources, findings, verification_api, channels, settings_api, export_api, discover

api_router = APIRouter()
api_router.include_router(overview.router)
api_router.include_router(sources.router)
api_router.include_router(findings.router)
api_router.include_router(verification_api.router)
api_router.include_router(channels.router)
api_router.include_router(settings_api.router)
api_router.include_router(export_api.router)
api_router.include_router(discover.router)
