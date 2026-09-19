"""应用入口：uvicorn app.main:app 启动。静态托管 frontend/dist。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from .api import api_router
from .config import REPO_ROOT, get_settings
from .db import Base, engine
from . import scheduler

log = logging.getLogger("ccs.main")


def init_db() -> None:
    """优先 Alembic 迁移；异常时回退 create_all（保证可启动）。"""
    try:
        from alembic import command
        from alembic.config import Config

        cfg = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
        cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))
        cfg.set_main_option("sqlalchemy.url", get_settings().resolved_db_url())
        command.upgrade(cfg, "head")
    except Exception as exc:  # noqa: BLE001
        log.warning("Alembic 迁移失败，回退 create_all: %s", exc)
        Base.metadata.create_all(engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    init_db()
    # 规则与能力清单同步
    from .db import SessionLocal
    from .detection.registry import get_registry
    from . import services
    session = SessionLocal()
    try:
        services.sync_rule_records(session, get_registry())
        services.seed_capabilities(session)
    finally:
        session.close()
    # 后台任务：调度器（含重启恢复）与验证 worker
    if settings.background:
        scheduler.start_background()
        from .verification import worker as verification_worker
        verification_worker.start_worker()
    log.info("%s v%s 启动完成", settings.app_name, settings.app_version)
    yield
    if settings.background:
        from .verification import worker as verification_worker
        verification_worker.stop_worker()
        scheduler.shutdown_background()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version=settings.app_version, lifespan=lifespan)
    app.include_router(api_router, prefix="/api")

    @app.post("/api/login")
    async def login(request: Request):
        """可选单用户访问保护：CCS_ACCESS_TOKEN 设置后生效。"""
        if not settings.access_token:
            return {"ok": True, "message": "未启用访问保护"}
        body = await request.json()
        if body.get("token") != settings.access_token:
            raise HTTPException(401, "访问令牌错误")
        resp = JSONResponse({"ok": True})
        resp.set_cookie("ccs_token", settings.access_token, max_age=7 * 24 * 3600, httponly=True)
        return resp

    if settings.access_token:
        @app.middleware("http")
        async def token_guard(request: Request, call_next):
            if request.url.path.startswith("/api/login"):
                return await call_next(request)
            if request.url.path.startswith("/api"):
                cookie = request.cookies.get("ccs_token")
                header = request.headers.get("authorization", "")
                if cookie != settings.access_token and header != f"Bearer {settings.access_token}":
                    return JSONResponse({"detail": "未授权"}, status_code=401)
            return await call_next(request)

    dist = Path(settings.static_dir) if settings.static_dir else (REPO_ROOT / "frontend" / "dist")
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="ui")
    else:
        @app.get("/")
        async def root():
            return RedirectResponse(url="/docs")

    return app


app = create_app()
