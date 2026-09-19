"""验证模块语义测试：默认关闭、状态机、最小请求、历史追加。"""
import asyncio
import random
import string

import httpx

from app import pipeline
from app.models import Credential, Source, Task, VerificationJob, VerificationResult
from app.security import encrypt_text
from app.verification import worker
from app.verification.base import CredentialView, get_verifier, verifier_for_type


def rand_alnum(n):
    return "".join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(n))


def make_cred(db, cred_type: str, secret: str) -> Credential:
    cred = Credential(
        fingerprint=f"test-{cred_type}-{rand_alnum(16)}", type=cred_type, vendor="t",
        rule_id="test", secret_encrypted=encrypt_text(secret), preview="****",
    )
    db.add(cred)
    db.commit()
    return cred


def mock_factory(handler):
    def _make():
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=5,
                                 follow_redirects=False)
    return _make


def test_no_verifier_enqueued_by_scan(db, sample_repo_path):
    """默认关闭：扫描流程不得产生任何验证作业。"""
    before = db.query(VerificationJob).count()
    source = Source(name="noverify", category="local_import", platform="local",
                    collector_key="local_dir", config_json={"path": sample_repo_path}, enabled=True)
    db.add(source)
    db.flush()
    task = Task(source_id=source.id, mode="manual", interval_sec=300, status="pending")
    db.add(task)
    db.commit()
    pipeline.run_task(task.id, "manual")
    after = db.query(VerificationJob).count()
    assert after == before, "扫描链路不得自动发起验证"


def test_unsupported_type_keeps_detection(db):
    cred = make_cred(db, "aws_access_key_id", "AKIA" + rand_alnum(16))
    result = worker.enqueue(db, cred.id, "single")
    assert result["queued"] is False and result["status"] == "unsupported"
    db.refresh(cred)
    assert cred.verification_status == "unsupported"
    row = db.query(VerificationResult).filter(VerificationResult.credential_id == cred.id).first()
    assert row.status == "unsupported"


def test_github_verifier_status_semantics(db):
    cred = make_cred(db, "github_pat", "ghp_" + rand_alnum(36))
    assert verifier_for_type("github_pat") is not None

    cases = [
        (200, {}, "valid"),
        (401, {}, "invalid"),
        (403, {"x-ratelimit-remaining": "0"}, "rate_limited"),
        (403, {}, "inconclusive"),
        (500, {}, "inconclusive"),
    ]
    for status, headers, expected in cases:
        def handler(request: httpx.Request, _s=status, _h=headers) -> httpx.Response:
            assert request.url.host == "api.github.com"
            assert request.url.path == "/user"
            return httpx.Response(_s, headers=_h, json={})

        job_row = VerificationJob(credential_id=cred.id, verifier_id="github-pat")
        db.add(job_row)
        db.commit()
        worker._process_job(db, job_row, http_factory_override=mock_factory(handler))
        result = db.query(VerificationResult).filter(
            VerificationResult.job_id == job_row.id).order_by(VerificationResult.id.desc()).first()
        assert result.status == expected, f"HTTP {status} {headers} => {expected}"
        assert "body" not in result.evidence_json, "证据不得包含响应体"

    count = db.query(VerificationResult).filter(VerificationResult.credential_id == cred.id).count()
    assert count == len(cases), "每次验证必须追加历史"


def test_network_error_not_invalid(db):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    cred = make_cred(db, "github_pat", "ghp_" + rand_alnum(36))
    view = CredentialView(id=cred.id, type=cred.type, secret="ghp_x")
    verifier = get_verifier("github-pat")
    out = asyncio.run(verifier.verify(view, mock_factory(handler)))
    assert out.status == "network_error", "网络故障不得判为 invalid"


def test_no_redirect_following(db):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "https://evil.example.com/user"})

    cred = make_cred(db, "github_pat", "ghp_" + rand_alnum(36))
    view = CredentialView(id=cred.id, type=cred.type, secret="ghp_x")
    verifier = get_verifier("github-pat")
    out = asyncio.run(verifier.verify(view, mock_factory(handler)))
    assert out.status == "inconclusive", "不跟随重定向；302 不构成有效/无效证据"
