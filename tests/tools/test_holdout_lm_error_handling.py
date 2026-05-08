"""Regression tests for BL-04 (holdout scoring LM-error handling).

Pre-fix: both evolve_tool_params._evaluate_holdout and
v1_baseline_gate._score_module_on_holdout wrapped `module(task_description=...)`
in a bare `try/except Exception` that silently retried with the SAME
argument. If the first call raised because of a real LM error (timeout,
rate limit, malformed completion), the retry would raise again uncaught,
tearing down the whole holdout loop AND silently doubling LM cost.

Post-fix: only AttributeError is caught (to tolerate MagicMock examples
that lack `.task_description`); real LM exceptions skip the example
without retrying (no double-cost) and without incrementing the
denominator (so a silent dilute-to-zero average cannot pass a trivially
comparable gate).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def test_evaluate_holdout_does_not_double_call_on_lm_error():
    """BL-04: a real LM error must NOT trigger a retry with the same arg.

    Pre-fix the retry re-called module(task_description=...) with an
    identical argument, doubling cost before finally re-raising (and
    aborting the loop). Post-fix the exception skips the example once.
    """
    pytest.importorskip("dspy")
    import dspy

    from evolution.tools.evolve_tool_params import _evaluate_holdout

    # One example with a real task_description attribute (not MagicMock-shaped)
    ex = dspy.Example(
        task_description="read foo.txt",
        correct_tool="read_file",
        correct_params={"path": "foo.txt"},
    ).with_inputs("task_description")

    module = MagicMock(side_effect=RuntimeError("LM timeout"))

    mean, tool_pairs, param_pairs = _evaluate_holdout(
        module=module,
        holdout=[ex],
        lm=None,  # will use _NullCtx-like path via dspy.context
    )

    assert module.call_count == 1, (
        f"BL-04 regression: module was called {module.call_count}x for one "
        f"holdout example with an LM error. Pre-fix: call_count=2 (silent "
        f"retry doubles cost). Post-fix: call_count=1 (example skipped)."
    )
    # Skipped example: no pair recorded.
    assert tool_pairs == []
    assert param_pairs == []
    # Mean over zero-effective-denominator: max(1, n) keeps this from
    # ZeroDivisionError, giving 0.0. (The skipped example did not dilute
    # anything because we did not increment n.)
    assert mean == 0.0


def test_evaluate_holdout_tolerates_missing_task_description():
    """BL-04: MagicMock-ish examples without .task_description still work.

    The narrow AttributeError catch preserves the legacy test-mock
    concession: `ex.task_description` raising AttributeError falls back
    to `getattr(ex, 'task_description', '')`.
    """
    pytest.importorskip("dspy")

    from evolution.tools.evolve_tool_params import _evaluate_holdout

    # MagicMock without an explicit task_description spec still returns a
    # MagicMock child on attribute access — use a plain object() instead.
    class _ExNoAttr:
        correct_tool = "x"
        correct_params: dict = {}

    ex = _ExNoAttr()
    # AttributeError on ex.task_description is caught → task = "" → module
    # called exactly once with task_description="".
    module = MagicMock(return_value=MagicMock(selected_tool="x", selected_params="{}"))

    mean, tool_pairs, param_pairs = _evaluate_holdout(
        module=module, holdout=[ex], lm=None
    )

    # Legacy behavior preserved:
    assert module.call_count == 1
    # Example WAS scored (not skipped) because module() did not raise.
    assert len(tool_pairs) == 1
    assert len(param_pairs) == 1


def test_score_module_on_holdout_does_not_double_call_on_lm_error():
    """BL-04 (v1_baseline_gate mirror): same contract for the inline baseline.

    Crucial for WR-09: a silent zero from a failing inline baseline would
    trivially pass the V1 baseline gate. Skipping (not retrying+diluting)
    makes a broken inline baseline detectable by subsequent checks.

    Post-WR-09: zero-prediction case raises _InlineBaselineFailedError so
    compute_v1_baseline can fail-closed. Use a 2-example fixture where
    only the first fails so we still get a partial average AND prove no
    silent retry happened.
    """
    pytest.importorskip("dspy")
    import dspy

    from evolution.tools.v1_baseline_gate import _score_module_on_holdout

    ex1 = dspy.Example(
        task_description="t1", correct_tool="x", correct_params={}
    ).with_inputs("task_description")
    ex2 = dspy.Example(
        task_description="t2", correct_tool="x", correct_params={}
    ).with_inputs("task_description")

    # First call raises (real LM error), second succeeds with a numeric
    # joint metric score (Prediction with selected_tool="x" matches
    # correct_tool="x" → metric returns 1.0 for tool match contribution).
    call_log = []

    def side_effect(*, task_description):
        call_log.append(task_description)
        if len(call_log) == 1:
            raise RuntimeError("LM timeout")
        return dspy.Prediction(selected_tool="x", selected_params="{}")

    module = MagicMock(side_effect=side_effect)

    score = _score_module_on_holdout(module, [ex1, ex2], lm=None)

    # Pre-fix: the first failure would retry once (silent double-cost)
    # and possibly re-raise uncaught; call_log would have length 3 if
    # both retries somehow worked, or the test would ERROR with
    # RuntimeError. Post-fix: first call raises → skipped → second call
    # runs once. call_log == ["t1", "t2"] (length 2).
    assert len(call_log) == 2, (
        f"BL-04 regression on v1_baseline_gate: expected exactly 2 module "
        f"calls (one per example, no retry on failure). Got "
        f"{len(call_log)}: {call_log}"
    )
    # n=1 (only ex2 contributed); score is the avg over n=1 examples.
    assert isinstance(score, float)


def test_score_module_on_holdout_all_fail_raises_inline_failed():
    """WR-09: if EVERY holdout example raises, the function must raise.

    Pre-fix: zero predictions silently produced 0.0 average, making the
    V1 baseline gate trivially pass (evolved_score >= 0 - tolerance).
    Post-fix: _InlineBaselineFailedError lets compute_v1_baseline fail
    closed by reporting v1_baseline_source='inline_failed' + a 1.0
    baseline that no evolved_score can reasonably exceed.
    """
    pytest.importorskip("dspy")
    import dspy

    from evolution.tools.v1_baseline_gate import (
        _score_module_on_holdout,
        _InlineBaselineFailedError,
    )

    ex = dspy.Example(
        task_description="t", correct_tool="x", correct_params={}
    ).with_inputs("task_description")
    module = MagicMock(side_effect=RuntimeError("LM timeout"))

    with pytest.raises(_InlineBaselineFailedError):
        _score_module_on_holdout(module, [ex, ex, ex], lm=None)


def test_compute_v1_baseline_inline_failed_fails_closed():
    """WR-09: compute_v1_baseline returns 'inline_failed' + baseline=1.0.

    Verifies the fail-closed semantics end-to-end:
      - source label is 'inline_failed' so callers can distinguish from
        a genuine inline run;
      - baseline value is 1.0 so any evolved_score < 1.0 - tolerance
        FAILS the V1 gate, rejecting the run.
    """
    pytest.importorskip("dspy")
    import dspy

    from evolution.tools.v1_baseline_gate import (
        compute_v1_baseline,
        V1BaselineGate,
    )

    ex = dspy.Example(
        task_description="t", correct_tool="x", correct_params={}
    ).with_inputs("task_description")
    module = MagicMock(side_effect=RuntimeError("LM timeout"))

    info = compute_v1_baseline(
        baseline_run=None,
        baseline_module=module,
        holdout=[ex, ex],
        lm=None,
    )
    assert info["v1_baseline_source"] == "inline_failed", info
    assert info["v1_baseline_holdout"] == 1.0, info
    assert info["metrics_source_path"] is None

    # End-to-end: V1BaselineGate.check() with a typical evolved_score=0.7
    # under inline_failed must FAIL (delta = 0.7 - 1.0 = -0.3 < -0.02).
    gate = V1BaselineGate(tolerance=0.02)
    result = gate.check(evolved_score=0.7, baseline=info)
    assert result["passed"] is False, (
        f"WR-09 regression: V1 baseline gate must fail closed when the "
        f"inline baseline could not be computed. Got result={result!r}."
    )
