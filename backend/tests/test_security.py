"""安全基础测试：加密、指纹、脱敏、占位符。"""
from app.security import (
    credential_fingerprint, decrypt_text, encrypt_text, is_placeholder,
    mask_preview, shannon_entropy,
)


def test_encrypt_roundtrip():
    token = "ghp_secret_value_1234567890"
    enc = encrypt_text(token)
    assert token not in enc
    assert decrypt_text(enc) == token


def test_fingerprint_stable_and_type_separated():
    a1 = credential_fingerprint("github_pat", "ghp_abc")
    a2 = credential_fingerprint("github_pat", "ghp_abc")
    b = credential_fingerprint("slack_token", "ghp_abc")
    c = credential_fingerprint("github_pat", "ghp_abc", {"user": "u1"})
    assert a1 == a2
    assert a1 != b, "同值不同类型不得合并"
    assert a1 != c, "配对字段不同不得合并"


def test_mask_preview():
    assert mask_preview("short") == "****"
    p = mask_preview("ghp_4a9Ck2XwQqLmN8vBzR5tYuIoP1sDfGhJkL2b")
    assert p.startswith("ghp_")
    assert "****" in p
    assert "QqLmN8vBzR5t" not in p


def test_placeholder_cases():
    assert is_placeholder("your_api_key_here")
    assert is_placeholder("AKIAIOSFODNN7EXAMPLE")
    assert is_placeholder("changeme")
    assert is_placeholder("aaaaaaaaaaaaaaaa")
    assert not is_placeholder("J8kQ2wL5vB8nM4cR6tZ0aS3dF7yG1x")
    assert not is_placeholder("ghp_4a9Ck2XwQqLmN8vBzR5tYuIoP1sDfGhJkL2b")


def test_entropy():
    assert shannon_entropy("aaaaaaaaaa") < 0.1
    assert shannon_entropy("J8kQ2wL5vB8nM4cR6tZ0aS3dF7yG1x") > 4.0
