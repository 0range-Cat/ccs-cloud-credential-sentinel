"""测试环境：在任何 app 导入之前设置环境变量（临时数据目录/独立DB/禁用后台线程）。

样例凭据全部为合成假值，无法通过任何真实服务认证。
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TEST_DATA = Path(tempfile.mkdtemp(prefix="ccs-test-data-"))
os.environ["CCS_DATA_DIR"] = str(_TEST_DATA)
os.environ["CCS_DB_URL"] = f"sqlite:///{(_TEST_DATA / 'test.db').as_posix()}"
os.environ["CCS_BACKGROUND"] = "false"

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import create_app  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app import services  # noqa: E402
from app.detection.registry import get_registry  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SAMPLE_REPO = FIXTURES / "sample_repo"


@pytest.fixture(scope="session")
def _db_setup():
    Base.metadata.create_all(engine)
    session = SessionLocal()
    try:
        services.sync_rule_records(session, get_registry())
        services.seed_capabilities(session)
    finally:
        session.close()


@pytest.fixture(scope="session")
def client(_db_setup):
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db(_db_setup):
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="session")
def sample_repo_path() -> str:
    return str(SAMPLE_REPO)
