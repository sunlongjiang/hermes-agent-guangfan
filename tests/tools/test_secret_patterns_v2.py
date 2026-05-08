"""Phase 14 Wave 1 — secret patterns v2 tests (Plan 03 Task 3.1).

Target: 14-VALIDATION.md rows 13-15 — D-15 Layer 1 (JWT / AWS-secret proximity)
+ Shannon-entropy branch over ≥24-char base64-like tokens.

B3 rule: **DO NOT** import `_shannon_entropy` at module top level. That symbol
lands in Task 3.2; importing it here would ImportError at pytest collect time
and mis-classify the RED gate as ERROR instead of FAILED. Top-level imports
stay limited to `_contains_secret` and `SECRET_PATTERNS`.
"""

import pytest

from evolution.core.external_importers import _contains_secret, SECRET_PATTERNS


def test_layer1_positives():
    """JWT / AWS-secret 邻近 / 高熵 ≥32-char base64 token 必须被 _contains_secret 检出。"""
    # JWT 字面 — 与 fixture secret_in_user_msg.json 中的字符串完全一致。
    # D-15 正则: eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+
    jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
    assert _contains_secret(f"Token: {jwt}"), "JWT must be detected"

    # AWS 邻近模式 — "aws_secret_access_key=" 后跟 ≥32-char base64-like (D-15 正则)
    aws_pat = "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    assert _contains_secret(aws_pat), "AWS-secret proximity must be detected"

    # 高熵 ≥32-char base64 token — 无 prefix，仅靠熵命中 (Layer 2 / D-15 第二条)。
    # 字符集 26 letters upper + 26 lower + digits ≈ 5-bit full alphabet, 熵 > 4.5.
    high_entropy_token = "qP3xN9vK2mR8tL5wQ7yU1iA4eB6oC0sD"  # 32 chars
    assert _contains_secret(high_entropy_token), "High-entropy token must be detected"


def test_v1_regression():
    """Phase 1 SECRET_PATTERNS 现有命中行为必须保留（D-15 不破坏 v1）。"""
    v1_positive_strings = [
        "sk-ant-api03-abcdefghij1234567890",  # Anthropic
        "sk-or-v1-abcdefghij1234567890",  # OpenRouter
        "sk-1234567890abcdefghij1234567890",  # Generic OpenAI
        "ghp_abcdefghij1234567890ABC",  # GitHub PAT
        "xoxb-1234-5678-abcdefghij",  # Slack bot
        "AKIA1234567890ABCDEF",  # AWS access key id
        "Bearer abcdefghij1234567890ABCDEF",  # Bearer auth
        "-----BEGIN RSA PRIVATE KEY-----",  # PEM
        "ANTHROPIC_API_KEY",  # env var name
        "OPENAI_API_KEY",
        "password=hunter2longenough",  # password assignment
    ]
    for s in v1_positive_strings:
        assert _contains_secret(s), f"v1 regression: {s!r} should still hit"


def test_low_entropy_negatives():
    """中文散文 / 短英文 / 真实 SHA256 hex 不应被熵分支误判。

    SHA256 hex 熵 ~4.20（RESEARCH §Pitfall 6 实测）— 阈值 4.0 处于边界。
    Calibration (Plan 06 manual checkpoint) 若把阈值调到 ≥4.3 此 test 仍会
    通过；当前 4.0 阈值下 SHA256 hex 字符集仅 16（0-9a-f），上界熵 = log2(16) = 4.0，
    所以即便阈值 4.0 亦不会命中。
    """
    low_entropy_strings = [
        "这是一段中文散文，谈论项目目标和开发计划。",
        "Hello world short message.",
        # SHA256 hex (64 hex chars) — fixture 中字面值；16-char alphabet → 熵 ≤4.0
        "a665a45920422f9d417e4867efdc4fb8a04a1f3fff1fa07e998e86f7f7a27ae3",
        # MD5 hex (32 hex chars) — 同理 ≤4.0
        "5d41402abc4b2a76b9719d911017c592",
        # UUID — 36 chars 含 dash，字符集 17 → 熵 ≤4.1 但 dash 拉低且集合小
        "550e8400-e29b-41d4-a716-446655440000",
        # 普通短英文 token < 24 chars (不进熵分支)
        "shortNotEntropyChecked",
    ]
    for s in low_entropy_strings:
        assert not _contains_secret(s), f"low-entropy false positive: {s!r}"
