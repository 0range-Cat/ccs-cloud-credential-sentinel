from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_session
from ..models import Source, Task
from .. import scheduler, settings_service
from ..collectors.base import all_collectors

router = APIRouter()


@router.get("/settings")
def get_settings_api(session: Session = Depends(get_session)):
    return settings_service.all_settings(session, include_secrets=False)


class SettingsIn(BaseModel):
    values: dict


@router.put("/settings")
def put_settings(body: SettingsIn, session: Session = Depends(get_session)):
    changed = []
    for key, value in body.values.items():
        if key not in settings_service.DEFAULTS:
            raise HTTPException(400, f"未知设置项: {key}")
        settings_service.set_setting(session, key, value)
        changed.append(key)
    session.commit()
    return {"ok": True, "changed": changed}


class TestConnIn(BaseModel):
    target: str          # collector_key，如 github / local_dir / archive
    config: dict = {}


@router.post("/settings/test-connection")
def test_connection(body: TestConnIn, session: Session = Depends(get_session)):
    """连接测试使用【设置页配置的采集账号】，绝不使用扫描发现的凭据。"""
    cls = all_collectors().get(body.target)
    if cls is None:
        raise HTTPException(400, f"未知采集器: {body.target}")
    config = dict(body.config)
    kwargs: dict = {}
    if body.target == "github":
        kwargs["token"] = settings_service.get_setting(session, "platform.github.token") or ""
    collector = cls(config, **kwargs)
    return collector.test_connection()


class ImportIn(BaseModel):
    name: str = ""
    path: str
    interval_sec: int = 0   # 0 表示仅手动


@router.post("/import/directory")
def import_directory(body: ImportIn, session: Session = Depends(get_session)):
    """本地目录导入：分析/测试入口，不虚增公开渠道类别。"""
    return _create_import(session, "local_dir", body)


@router.post("/import/git-local")
def import_git_local(body: ImportIn, session: Session = Depends(get_session)):
    """Git 仓库副本（本地工作区）导入。远程克隆在阶段2 提供。"""
    return _create_import(session, "local_dir", body)


def _create_import(session: Session, collector_key: str, body: ImportIn) -> dict:
    cls = all_collectors()[collector_key]
    source = Source(
        name=body.name or f"导入-{uuid.uuid4().hex[:6]}",
        category=cls.category, platform=cls.platform,
        collector_key=collector_key,
        config_json={"path": body.path, "max_file_bytes": 1024 * 1024},
        enabled=True,
    )
    session.add(source)
    session.flush()
    task = Task(source_id=source.id, mode="manual", interval_sec=300, status="pending")
    session.add(task)
    session.commit()
    result = scheduler.trigger_manual_run(task.id)
    return {"source_id": source.id, "task_id": task.id, "triggered": result.get("ok", False)}


MAX_UPLOAD_BYTES = 200 * 1024 * 1024


@router.post("/import/archive")
async def import_archive(upload: UploadFile, session: Session = Depends(get_session)):
    """压缩包上传导入（≤200MB），保存到 data/tmp 后按本地导入流程扫描。"""
    settings = get_settings()
    tmp_dir = settings.data_dir / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    suffix = ".".join((upload.filename or "archive.zip").split(".")[-2:])[:40]
    if not suffix.endswith((".zip", ".tar", ".gz", ".tgz", ".bz2")):
        suffix = (suffix + ".zip") if suffix.endswith(".tar") else ".zip"
    dest = tmp_dir / f"upload-{uuid.uuid4().hex[:8]}-{suffix}"
    size = 0
    with dest.open("wb") as f:
        while chunk := await upload.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, "上传超过 200MB 上限")
            f.write(chunk)
    body = ImportIn(name=upload.filename or "压缩包导入", path=str(dest))
    return _create_import(session, "archive", body)
