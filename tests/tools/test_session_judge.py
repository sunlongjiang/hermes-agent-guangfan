"""Wave 0 RED test scaffolding for Phase 14 ConfirmMisselection LLM judge.

Covers 14-VALIDATION.md rows 5-6 (judge verdict round-trip + fail-closed on
LM errors). Reuses `mock_lm_with_usage` from tests/conftest.py:7-38 via
pytest auto-discovery (no import needed).
"""

import pytest


def test_verdict_round_trip(mock_lm_with_usage):
    """Judge parses both `confirm_misselection` and `false_positive` verdicts.

    Feeds mock LM responses carrying each label; asserts Verdict.label is
    normalized to lowercase exact token, and unknown labels fall back to
    `false_positive` (fail-closed per RESEARCH Pattern 1 / CONCERNS §M4).
    """
    pytest.skip("Wave 1+ 实现 — 见 14-03-PLAN.md")


def test_lm_failure_drops_candidate(mock_lm_with_usage):
    """LLM call raising any Exception → candidate dropped (fail-closed).

    Patches judge.predict to raise RuntimeError; asserts
    `_judge_candidate` returns verdict='false_positive' with a rationale
    containing the exception message; does NOT accept as misselection
    (threat T-14-01 mitigation).
    """
    pytest.skip("Wave 1+ 实现 — 见 14-03-PLAN.md")
