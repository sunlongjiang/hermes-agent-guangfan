"""Tests for required_patterns gate + GEPA reflection sanitize.

Both behaviours were uncovered while integrating the SDK with a real
LangChain memory agent: the optimizer dropped a {skill_summaries}
placeholder GEPA was supposed to preserve, and GEPA's reflection LM
inlined training trace scores ("得分为 0.342") into candidate prompts.
"""

import pytest
from pathlib import Path

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.optimizer import apply_gates
from evolution.sdk.sanitize import sanitize_candidate, find_leak_markers


def _mk_artifact(baseline="baseline {placeholder} text", **constraint_overrides):
    constraints = {"max_chars": 100000, **constraint_overrides}
    return EvolvableArtifact(
        agent_name="test",
        artifact_id="art",
        kind="prompt",
        baseline_text=baseline,
        text_source="param",
        source_file=Path("/tmp/x.py"),
        decorator_lineno=1,
        constraints=constraints,
    )


# ── required_patterns gate ────────────────────────────────────────────


def test_required_pattern_present_passes():
    art = _mk_artifact(required_patterns=[r"\{placeholder\}"])
    res = apply_gates(
        artifact=art,
        candidate_text="new candidate still has {placeholder} in it",
        baseline_score=0.5,
        candidate_holdout_score=0.5,
    )
    assert res.passed


def test_required_pattern_missing_rejects():
    """The motivating bug: GEPA dropped `{skill_summaries}` so the agent's
    .format() call silently lost the skill list."""
    art = _mk_artifact(required_patterns=[r"\{skill_summaries\}"])
    res = apply_gates(
        artifact=art,
        candidate_text="new candidate without the placeholder",
        baseline_score=0.5,
        candidate_holdout_score=0.5,
    )
    assert not res.passed
    assert res.failed_gate == "gate_1_required_missing"
    assert "skill_summaries" in res.reason


def test_required_pattern_multi_one_missing_rejects():
    art = _mk_artifact(required_patterns=[r"alpha", r"beta", r"gamma"])
    res = apply_gates(
        artifact=art,
        candidate_text="alpha and gamma but no second token",
        baseline_score=0.5,
        candidate_holdout_score=0.5,
    )
    assert not res.passed
    assert res.failed_gate == "gate_1_required_missing"
    assert "beta" in res.reason


def test_required_and_forbidden_compose():
    """Both lists evaluated; forbidden checked first."""
    art = _mk_artifact(
        forbidden_patterns=[r"DEBUG_MODE"],
        required_patterns=[r"prod"],
    )
    res = apply_gates(
        artifact=art,
        candidate_text="DEBUG_MODE active in prod environment",
        baseline_score=0.5,
        candidate_holdout_score=0.5,
    )
    assert not res.passed
    assert res.failed_gate == "gate_1_forbidden"


# ── sanitize_candidate ────────────────────────────────────────────────


def test_sanitize_clean_returns_unchanged():
    text = "# Task\nDo the thing. ## Examples\n- Good example."
    cleaned, markers = sanitize_candidate(text)
    assert cleaned == text
    assert markers == []


def test_sanitize_trims_trailing_feedback_section():
    """Real shape we observed: GEPA reflection appends a `## 示例与反馈`
    section containing trace scores."""
    text = (
        "# Task\nDo the thing.\n\n"
        "## 关键点\n- Be terse.\n\n"
        "## 示例与反馈解读\n"
        "Example 1: 得分为 0.342, 表现一般。"
    )
    cleaned, markers = sanitize_candidate(text)
    assert markers, "must detect the leak"
    assert "得分为" not in cleaned
    assert "## 关键点" in cleaned  # body preserved


def test_sanitize_trims_english_score_section():
    text = (
        "# Task\nDo the thing.\n\n"
        "## Body\n- Be terse.\n\n"
        "## Example feedback\n"
        "Example A: Score: 0.461 — good."
    )
    cleaned, markers = sanitize_candidate(text)
    assert markers
    assert "Score:" not in cleaned
    assert "## Body" in cleaned


def test_sanitize_interleaved_leak_refuses():
    """When the leak is in the body itself (not a trailing section), the
    sanitizer must NOT silently mangle the prompt — it returns the
    markers so the caller can reject."""
    text = "# Task\nGenerate (得分为 0.5 noted) commit messages."
    cleaned, markers = sanitize_candidate(text)
    assert markers, "leak must be detected"
    assert cleaned == text, "cannot safely localise → leave untouched"


def test_find_leak_markers_catches_execute_tags():
    text = "Do this: <execute>load_skill('memory-create')</execute>"
    markers = find_leak_markers(text)
    assert any("execute" in m for m in markers)


def test_sanitize_idempotent():
    """Running twice on a sanitizable input must converge."""
    text = (
        "# Task\nDo the thing.\n\n"
        "## 实际案例反馈\n"
        "- Example 1: 得分为 0.5。"
    )
    once, _ = sanitize_candidate(text)
    twice, markers_twice = sanitize_candidate(once)
    assert twice == once
    assert markers_twice == []
