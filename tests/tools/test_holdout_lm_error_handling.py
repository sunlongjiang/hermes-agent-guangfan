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
    """
    pytest.importorskip("dspy")
    import dspy

    from evolution.tools.v1_baseline_gate import _score_module_on_holdout

    ex = dspy.Example(
        task_description="t",
        correct_tool="x",
        correct_params={},
    ).with_inputs("task_description")

    module = MagicMock(side_effect=RuntimeError("LM timeout"))

    score = _score_module_on_holdout(module, [ex], lm=None)

    assert module.call_count == 1, (
        f"BL-04 regression on v1_baseline_gate: module called "
        f"{module.call_count}x with an LM error. Pre-fix silent retry "
        f"doubled LM cost and re-raised uncaught."
    )
    assert score == 0.0
