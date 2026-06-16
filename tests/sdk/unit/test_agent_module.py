"""Tests for AgentModule (DSPy wrapper) + composite_metric weights."""

from pathlib import Path

import pytest

from evolution.sdk.agent_module import (
    AgentModule, build_composite_metric, JudgeConfig,
)
from evolution.sdk.artifact import EvolvableArtifact


def _mk_prompt_artifact():
    return EvolvableArtifact(
        agent_name="bot", artifact_id="sys", kind="prompt",
        baseline_text="You are helpful.", text_source="param",
        source_file=Path("/tmp/x.py"), decorator_lineno=1,
    )


def _mk_tool_artifact():
    return EvolvableArtifact(
        agent_name="bot", artifact_id="search", kind="tool",
        baseline_text="Search the web.", text_source="docstring",
        source_file=Path("/tmp/x.py"), decorator_lineno=20,
    )


def test_agent_module_construction_prompt():
    a = _mk_prompt_artifact()
    mod = AgentModule(a, judge_dimensions=("correctness",))
    assert mod.artifact.artifact_id == "sys"
    assert mod.current_text == "You are helpful."


def test_agent_module_set_text_updates_current():
    a = _mk_prompt_artifact()
    mod = AgentModule(a, judge_dimensions=("correctness",))
    mod.set_text("Be terse.")
    assert mod.current_text == "Be terse."


def test_agent_module_tool_kind_supported():
    a = _mk_tool_artifact()
    mod = AgentModule(a, judge_dimensions=("correctness",))
    assert mod.artifact.kind == "tool"


def test_composite_metric_all_three_components():
    cfg = JudgeConfig(model="mock", dimensions=("correctness",))
    metric = build_composite_metric(
        user_metric=lambda trace, output: 0.8,
        judge_config=cfg,
        signals_provider=lambda trace: 0.6,
    )
    # Score: 0.5*0.8 + 0.3*0.7 + 0.2*0.6 = 0.4 + 0.21 + 0.12 = 0.73
    # (judge_score mocked to 0.7 via stub below)
    pred = type("P", (), {"output": "x", "_judge_score": 0.7})()
    example = type("E", (), {"trace": {"ts": "2026-06-12T00:00:00Z"}})()
    s = metric(example, pred)
    assert abs(s - 0.73) < 1e-9


def test_composite_metric_no_user_metric_reweights():
    """Without metric: 0.7*judge + 0.3*signal."""
    cfg = JudgeConfig(model="mock", dimensions=("correctness",))
    metric = build_composite_metric(
        user_metric=None,
        judge_config=cfg,
        signals_provider=lambda trace: 0.6,
    )
    pred = type("P", (), {"output": "x", "_judge_score": 0.8})()
    example = type("E", (), {"trace": {"ts": "2026-06-12T00:00:00Z"}})()
    s = metric(example, pred)
    # 0.7*0.8 + 0.3*0.6 = 0.56 + 0.18 = 0.74
    assert abs(s - 0.74) < 1e-9


def test_composite_metric_no_judge_uses_signal_only():
    """Without judge dimensions: 1.0 * signal."""
    metric = build_composite_metric(
        user_metric=None,
        judge_config=None,
        signals_provider=lambda trace: 0.5,
    )
    pred = type("P", (), {"output": "x"})()
    example = type("E", (), {"trace": {}})()
    s = metric(example, pred)
    assert abs(s - 0.5) < 1e-9


def test_composite_metric_user_metric_exception_falls_back():
    """If user metric raises, the metric degrades to judge+signal weights."""
    def bad_metric(trace, output):
        raise ValueError("user code bug")
    cfg = JudgeConfig(model="mock", dimensions=("correctness",))
    metric = build_composite_metric(
        user_metric=bad_metric,
        judge_config=cfg,
        signals_provider=lambda trace: 0.5,
    )
    pred = type("P", (), {"output": "x", "_judge_score": 0.8})()
    example = type("E", (), {"trace": {}})()
    s = metric(example, pred)
    # Falls back to 0.7*0.8 + 0.3*0.5 = 0.71
    assert abs(s - 0.71) < 1e-9
