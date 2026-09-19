"""检测引擎行为测试：上下文/配对/解码/结构化/过滤/重叠消解。"""
import base64
import json
import random
import string

from app.detection.engine import DetectionEngine
from app.detection.registry import RuleRegistry


def make_engine() -> DetectionEngine:
    reg = RuleRegistry()
    reg.load()
    return DetectionEngine(reg)


def rand_alnum(n: int) -> str:
    return "".join(random.SystemRandom().choice(string.ascii_letters + string.digits) for _ in range(n))


def positives(engine, text, rule_id=None):
    cands = [c for c in engine.scan(text) if not c.evidence.get("rejected_candidate")]
    if rule_id:
        cands = [c for c in cands if c.rule_id == rule_id]
    return cands


def test_aws_pairing_boost():
    e = make_engine()
    ak = "AKIA" + rand_alnum(16).upper().replace("O", "A").replace("I", "B").replace("0", "2").replace("1", "3")
    sk = rand_alnum(40)
    alone = e.scan(f"aws_secret_access_key = {sk}")
    sk_alone = [c for c in alone if c.rule_id == "aws-secret-access-key" and c.secret == sk]
    assert sk_alone and sk_alone[0].confidence == 60

    paired_text = f"aws_access_key_id = {ak}\naws_secret_access_key = {sk}"
    sk_paired = [c for c in e.scan(paired_text) if c.rule_id == "aws-secret-access-key" and c.secret == sk]
    assert sk_paired[0].confidence == 80
    assert sk_paired[0].evidence.get("paired_with", {}).get("rule") == "aws-access-key-id"


def test_base64_bounded_decode():
    e = make_engine()
    token = "ghp_" + rand_alnum(36)
    encoded = base64.b64encode(token.encode()).decode()
    hits = positives(e, f"data: {encoded}", "github-pat")
    assert hits and hits[0].secret == token
    assert hits[0].evidence.get("decoded_base64") is True


def test_private_key_block_and_encrypted_state():
    e = make_engine()
    plain = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA1234\n-----END RSA PRIVATE KEY-----"
    hits = positives(e, plain, "private-key-block")
    assert hits and hits[0].evidence["encrypted"] is False
    enc = plain.replace("RSA PRIVATE KEY", "ENCRYPTED PRIVATE KEY")
    hits2 = positives(e, enc, "private-key-block")
    assert hits2 and hits2[0].evidence["encrypted"] is True
    openssh = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaA==\n-----END OPENSSH PRIVATE KEY-----"
    hits3 = positives(e, openssh, "private-key-block")
    assert hits3 and hits3[0].evidence["encrypted"] == "unknown"


def test_gcp_service_account_structured():
    e = make_engine()
    obj = {
        "type": "service_account", "project_id": "p1",
        "private_key": "-----BEGIN PRIVATE KEY-----\nMIIE\n-----END PRIVATE KEY-----\n",
        "client_email": "svc@p1.iam.gserviceaccount.com",
    }
    hits = positives(e, json.dumps(obj), "gcp-service-account-json")
    assert hits and hits[0].evidence["paired"].get("client_email") == obj["client_email"]
    # 非 service_account 类型不命中
    obj["type"] = "authorized_user"
    assert not positives(e, json.dumps(obj), "gcp-service-account-json")


def test_placeholder_and_known_example_rejected():
    e = make_engine()
    assert not positives(e, "key = AKIAIOSFODNN7EXAMPLE", "aws-access-key-id")
    assert not positives(e, "TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx", "github-pat")
    assert not positives(e, "SECRET_KEY=aaaaaaaaaaaaaaaaaaaaaaaa", "generic-env-assignment")


def test_db_url_forbidden_passwords():
    e = make_engine()
    assert positives(e, "DATABASE_URL=mysql://u:S3cretPassX9@h:3306/db", "db-connection-url")
    assert not positives(e, "DATABASE_URL=mysql://u:password@h:3306/db", "db-connection-url")
    assert not positives(e, "postgres://user@localhost:5432/db", "db-connection-url")


def test_context_required_rules():
    e = make_engine()
    tok = "".join(random.SystemRandom().choice("0123456789abcdef") for _ in range(32))
    assert not positives(e, f"hash = {tok}", "gitee-token")
    assert positives(e, f"gitee token = {tok}", "gitee-token")


def test_overlap_resolution_single_candidate():
    e = make_engine()
    key = "sk-proj-" + rand_alnum(40)
    cands = positives(e, f"OPENAI_API_KEY={key}", "openai-api-key")
    assert len(cands) == 1, "同一命中被多条模式捕获时应消解为一条"


def test_input_truncation_flag():
    e = make_engine()
    token = "ghp_" + rand_alnum(36)
    big = "x" * 999_000 + f"\ntoken: {token}\n" + "y" * 2_000
    assert len(big) > 1_000_000
    cands = positives(e, big, "github-pat")
    assert cands and cands[0].evidence.get("input_truncated") is True
