"""Tests for automatic signal detection + signal_score weighting."""

import json
from pathlib import Path

import pytest

from evolution.sdk.signals import (
    detect_error_in_run,
    detect_retry_pattern,
    detect_user_correction,
    detect_clean_completion,
    detect_latency_outlier,
    compute_signal_score,
    annotate_traces_with_signals,
)


FIXTURES = Path(__file__).parent.parent / "fixtures" / "traces"


def _load(name: str) -> list[dict]:
    return [json.loads(line) for line in (FIXTURES / name).read_text().splitlines() if line.strip()]


def test_detect_error_in_run_from_tool_error():
    traces = _load("error_runs.jsonl")
    assert detect_error_in_run(traces[0]) is True


def test_detect_error_in_run_from_traceback_in_signals():
    trace = {"output": "Traceback (most recent)...\nValueError: x", "tool_calls": [], "signals": {}}
    assert detect_error_in_run(trace) is True


def test_detect_error_in_run_clean():
    traces = _load("clean_runs.jsonl")
    for t in traces:
        assert detect_error_in_run(t) is False


def test_detect_retry_pattern_same_args():
    traces = _load("retry_runs.jsonl")
    assert detect_retry_pattern(traces[0]) is True


def test_detect_retry_pattern_different_args_is_not_retry():
    trace = {"tool_calls": [
        {"id": "s", "args": {"q": "a"}, "result": "ok", "error": None},
        {"id": "s", "args": {"q": "b"}, "result": "ok", "error": None},
    ]}
    assert detect_retry_pattern(trace) is False


def test_detect_user_correction_in_next_trace():
    traces = _load("correction_runs.jsonl")
    # Second trace's input contains correction phrase → first trace gets the signal.
    assert detect_user_correction(traces[0], next_trace=traces[1]) is True
    assert detect_user_correction(traces[1], next_trace=None) is False


@pytest.mark.parametrize("phrase", ["不对", "应该是", "redo", "actually", "no that's wrong"])
def test_user_correction_phrases(phrase):
    cur = {"input": {"q": "foo"}}
    nxt = {"input": {"q": f"{phrase}, do something else"}}
    assert detect_user_correction(cur, next_trace=nxt) is True


def test_detect_clean_completion():
    clean = _load("clean_runs.jsonl")
    assert detect_clean_completion(clean[0]) is True
    err = _load("error_runs.jsonl")
    assert detect_clean_completion(err[0]) is False


def test_detect_latency_outlier_high():
    # p95 of [50, 100, 100, 100, 100] is ~100; trace at 5000 → outlier (>2x p95).
    traces = [
        {"signals": {"latency_ms": x}} for x in [50, 100, 100, 100, 100]
    ]
    target = {"signals": {"latency_ms": 5000}}
    assert detect_latency_outlier(target, all_traces=traces + [target]) is True


def test_detect_latency_outlier_normal():
    traces = [{"signals": {"latency_ms": x}} for x in [50, 100, 100, 100, 100]]
    target = {"signals": {"latency_ms": 90}}
    assert detect_latency_outlier(target, all_traces=traces + [target]) is False


def test_signal_score_clean_is_1():
    score = compute_signal_score(
        error_in_run=False, retry_pattern=False,
        user_correction=False, latency_outlier=False,
    )
    assert score == 1.0


def test_signal_score_error_reduces_to_0_6():
    score = compute_signal_score(
        error_in_run=True, retry_pattern=False,
        user_correction=False, latency_outlier=False,
    )
    assert abs(score - 0.6) < 1e-9


def test_signal_score_all_negative_clamps_to_0():
    score = compute_signal_score(
        error_in_run=True, retry_pattern=True,
        user_correction=True, latency_outlier=True,
    )
    assert score == 0.0


def test_annotate_traces_populates_signal_score():
    clean = _load("clean_runs.jsonl")
    err = _load("error_runs.jsonl")
    all_traces = clean + err
    annotated = annotate_traces_with_signals(all_traces)
    assert annotated[0]["scores"]["signal_score"] == 1.0
    assert annotated[-1]["scores"]["signal_score"] < 1.0
