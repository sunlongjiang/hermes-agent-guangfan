"""Wave 0 RED test scaffolding for Phase 14 secret-patterns v2 extensions.

Covers 14-VALIDATION.md rows 13-15 — Layer 1 positives (JWT / AWS-secret
proximity / high-entropy base64), v1 regression (existing patterns still
detected), low-entropy negatives (prose / SHA256 hex / short strings).

B3/B4 rule: this file MUST NOT import `_shannon_entropy` at module top level
— that symbol lands in Plan 03 Task 3.2 and importing it at collect time
would ImportError and mis-classify the RED gate as ERROR. Plan 01 only
provides skip stubs; Plan 03 Task 3.1 replaces them with real RED assertions
that still avoid the forbidden import (the helper is exercised indirectly
through `_contains_secret`).
"""

import pytest


def test_layer1_positives():
    """New Layer 1 patterns detected: JWT / AWS-secret proximity / high entropy.

    Expected positives (must all be detected via `_contains_secret`):
      - JWT: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ1c2VyIn0.<sig>
      - AWS secret proximity: "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
      - High-entropy ≥24-char base64-like (no prefix) with Shannon entropy > 4.0
    """
    pytest.skip("Wave 1+ 实现 — 见 14-03-PLAN.md")


def test_v1_regression():
    """Existing v1 SECRET_PATTERNS still detected (no regression).

    Subset of strings that MUST still be detected:
      sk-ant-api..., ghp_..., xoxb-..., AKIA..., sk-or-v1-...,
      Bearer <jwt>, -----BEGIN PRIVATE KEY-----, password=xxx,
      ANTHROPIC_API_KEY=...
    """
    pytest.skip("Wave 1+ 实现 — 见 14-03-PLAN.md")


def test_low_entropy_negatives():
    """Low-entropy or short strings NOT flagged by Layer 2 entropy branch.

    Must NOT be flagged (avoid false positives on normal prose / IDs):
      - Chinese prose "这是一段中文测试"
      - Short English "hello world"
      - SHA256 hex (64-char, letters a-f + digits only → entropy ≈ 3.9, below threshold)
    Threshold 4.0 TBD at Plan 03 Task 3.2 calibration — if changed, update here.
    """
    pytest.skip("Wave 1+ 实现 — 见 14-03-PLAN.md")
