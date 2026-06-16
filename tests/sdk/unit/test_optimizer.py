"""Tests for optimizer main loop + three-gate filtering + run_summary."""

import json
from pathlib import Path

import pytest

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.optimizer import (
    OptimizationBudget,
    OptimizationOutcome,
    apply_gates,
    write_optimized_file,
    write_run_summary,
    GateFailure,
)


def _mk_artifact():
    return EvolvableArtifact(
        agent_name="bot", artifact_id="sys", kind="prompt",
        baseline_text="hello world and more text here!",  # 31 chars: long enough that hello world / secret don't trip growth
        text_source="param",
        source_file=Path("/tmp/x.py"), decorator_lineno=1,
        constraints={"max_chars": 100, "max_growth": 0.2},
    )


def test_budget_can_afford_and_spend():
    b = OptimizationBudget(max_cost_usd=5.0)
    assert b.remaining() == 5.0
    assert b.can_afford(2.0) is True
    b.spend(3.0)
    assert b.remaining() == 2.0
    assert b.can_afford(3.0) is False


def test_gate_1_size_limit_rejects_oversize():
    a = _mk_artifact()  # max_chars=100
    res = apply_gates(
        artifact=a,
        candidate_text="x" * 200,
        baseline_score=0.5,
        candidate_holdout_score=0.6,
        regression_tolerance=0.02,
    )
    assert res.passed is False
    assert "size" in res.failed_gate.lower() or "max_chars" in res.reason


def test_gate_1_growth_limit_rejects():
    a = _mk_artifact()
    res = apply_gates(
        artifact=a,
        candidate_text="x" * 70,  # 31 → 70 = 126% growth, way over 20%
        baseline_score=0.5,
        candidate_holdout_score=0.6,
        regression_tolerance=0.02,
    )
    assert res.passed is False
    assert "growth" in res.failed_gate.lower()


def test_gate_2_holdout_regression_rejects():
    a = _mk_artifact()
    res = apply_gates(
        artifact=a,
        candidate_text="hello world",  # within size + growth
        baseline_score=0.80,
        candidate_holdout_score=0.50,  # big drop
        regression_tolerance=0.02,
    )
    assert res.passed is False
    assert "holdout" in res.failed_gate.lower()


def test_gates_accept_improvement():
    a = _mk_artifact()
    res = apply_gates(
        artifact=a,
        candidate_text="hi",  # smaller is fine
        baseline_score=0.50,
        candidate_holdout_score=0.78,
        regression_tolerance=0.02,
    )
    assert res.passed is True


def test_secret_pattern_in_candidate_rejected():
    a = _mk_artifact()
    res = apply_gates(
        artifact=a,
        candidate_text="hi (sk-ant-api-secret123)",
        baseline_score=0.5,
        candidate_holdout_score=0.6,
        regression_tolerance=0.02,
    )
    assert res.passed is False
    assert "secret" in res.failed_gate.lower()


def test_tool_kind_must_keep_placeholders():
    a = EvolvableArtifact(
        agent_name="bot", artifact_id="t", kind="tool",
        baseline_text="search for {query} on the web",
        text_source="docstring",
        source_file=Path("/tmp/x.py"), decorator_lineno=1,
        constraints={"max_chars": 500, "max_growth": 0.5},
    )
    res = apply_gates(
        artifact=a,
        candidate_text="search for X on the web",  # lost {query}
        baseline_score=0.5,
        candidate_holdout_score=0.6,
        regression_tolerance=0.02,
    )
    assert res.passed is False
    assert "placeholder" in res.failed_gate.lower()


def test_write_optimized_file_atomic(tmp_evolution_home):
    a = _mk_artifact()
    path = write_optimized_file(
        artifact=a,
        agent_version="0.1.0",
        optimized_text="improved",
        optimization_metadata={
            "run_id": "uuid",
            "ts": "2026-06-13T00:00:00Z",
            "optimizer": "GEPA",
            "judge_model": "openai/gpt-4.1",
            "baseline_score": 0.5,
            "optimized_score": 0.7,
            "holdout_score": 0.65,
            "dataset_size": 100,
            "cost_usd": 1.0,
        },
    )
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["optimized_text"] == "improved"
    assert data["baseline_hash"] == a.baseline_hash


def test_write_run_summary_includes_all_artifacts(tmp_evolution_home):
    outcomes = [
        OptimizationOutcome(artifact_id="sys", status="improved",
                            baseline_score=0.5, optimized_score=0.7,
                            rejection_reason=None, cost_usd=1.0),
        OptimizationOutcome(artifact_id="search", status="rejected",
                            baseline_score=0.6, optimized_score=None,
                            rejection_reason="holdout_regression", cost_usd=0.5),
    ]
    path = write_run_summary(
        agent_name="bot",
        trigger="manual",
        outcomes=outcomes,
        dataset_path=Path("/tmp/ds"),
        total_cost_usd=1.5,
        duration_seconds=42,
    )
    data = json.loads(path.read_text())
    assert data["agent"] == "bot"
    assert len(data["artifacts"]) == 2
    assert data["artifacts"][1]["rejection_reason"] == "holdout_regression"
