"""Integration: candidate goes through all three gates with realistic data."""

from pathlib import Path

import pytest

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.optimizer import apply_gates


def _mk(kind="prompt", text="Be helpful.", max_chars=200, max_growth=2.0):
    return EvolvableArtifact(
        agent_name="bot", artifact_id="a", kind=kind,
        baseline_text=text, text_source="param",
        source_file=Path("/tmp/x.py"), decorator_lineno=1,
        constraints={"max_chars": max_chars, "max_growth": max_growth},
    )


def test_improved_candidate_passes_all_gates():
    a = _mk()
    res = apply_gates(
        artifact=a,
        candidate_text="Be terse and helpful.",
        baseline_score=0.60,
        candidate_holdout_score=0.78,
    )
    assert res.passed is True


def test_oversize_candidate_fails_gate_1():
    a = _mk(max_chars=50)
    res = apply_gates(
        artifact=a, candidate_text="x" * 200,
        baseline_score=0.5, candidate_holdout_score=0.6,
    )
    assert not res.passed and "size" in res.failed_gate


def test_growth_violation_fails_gate_1():
    a = _mk(text="hi", max_growth=0.1)
    res = apply_gates(
        artifact=a, candidate_text="hi" * 5,  # 200% growth
        baseline_score=0.5, candidate_holdout_score=0.6,
    )
    assert not res.passed and "growth" in res.failed_gate


def test_regression_just_inside_tolerance_passes():
    a = _mk()
    res = apply_gates(
        artifact=a, candidate_text="Be helpful and clear.",
        baseline_score=1.0, candidate_holdout_score=0.99,
        regression_tolerance=0.02,
    )
    assert res.passed is True


def test_regression_just_outside_tolerance_fails():
    a = _mk()
    res = apply_gates(
        artifact=a, candidate_text="Be helpful and clear.",
        baseline_score=1.0, candidate_holdout_score=0.97,
        regression_tolerance=0.02,
    )
    assert not res.passed and "holdout" in res.failed_gate


def test_tool_placeholder_preserved_passes():
    a = _mk(kind="tool", text="search for {query} in {source}")
    res = apply_gates(
        artifact=a,
        candidate_text="Search {source} for {query}, return top 3 results.",
        baseline_score=0.5, candidate_holdout_score=0.6,
    )
    assert res.passed is True


def test_tool_placeholder_lost_fails():
    a = _mk(kind="tool", text="search for {query}")
    res = apply_gates(
        artifact=a, candidate_text="search the web",
        baseline_score=0.5, candidate_holdout_score=0.6,
    )
    assert not res.passed and "placeholder" in res.failed_gate
