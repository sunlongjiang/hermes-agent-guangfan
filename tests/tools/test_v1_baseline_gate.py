"""Wave 0 RED tests for v1 baseline regression hard gate.

Tests D-14: evolved < baseline - 0.02 (2pp) -> FAIL; no --baseline-run -> inline fallback.
Fails until 13-07 implements check_v1_baseline_gate() and compute_v1_baseline().
"""

import pytest


def test_regression_fails_run():
    """check_v1_baseline_gate returns passed=False when evolved < baseline - 0.02.

    D-14: 2pp tolerance hard gate. Message must reference '2pp' or 'regression'.
    """
    pytest.importorskip("dspy")
    from evolution.tools.evolve_tool_params import check_v1_baseline_gate  # fails until 13-07
    from evolution.core.constraints import ConstraintResult

    result = check_v1_baseline_gate(
        evolved_score=0.70,
        baseline_score=0.75,
        tolerance=0.02,
    )

    assert isinstance(result, ConstraintResult), (
        f"Expected ConstraintResult, got {type(result)}"
    )
    assert result.passed is False, (
        f"Expected passed=False when evolved(0.70) < baseline(0.75) - tolerance(0.02), "
        f"got passed={result.passed}"
    )
    # Message must mention regression context
    msg_lower = result.message.lower()
    assert "2pp" in msg_lower or "regression" in msg_lower, (
        f"Expected '2pp' or 'regression' in message, got: {result.message!r}"
    )


def test_inline_baseline_fallback():
    """compute_v1_baseline with baseline_run=None returns inline fallback dict.

    D-14: when --baseline-run is absent, compute inline baseline from original ToolModule.
    Result must include v1_baseline_source='inline' and v1_baseline_holdout in [0,1].
    """
    pytest.importorskip("dspy")
    from unittest.mock import MagicMock
    from evolution.tools.evolve_tool_params import compute_v1_baseline  # fails until 13-07

    mock_module = MagicMock()
    mock_holdout = [MagicMock() for _ in range(5)]

    result = compute_v1_baseline(
        baseline_run=None,
        baseline_module=mock_module,
        holdout=mock_holdout,
    )

    assert isinstance(result, dict), f"Expected dict, got {type(result)}"
    assert "v1_baseline_source" in result, (
        f"Expected 'v1_baseline_source' key in result, got: {list(result.keys())}"
    )
    assert result["v1_baseline_source"] == "inline", (
        f"Expected v1_baseline_source='inline' when no baseline_run provided, "
        f"got: {result['v1_baseline_source']!r}"
    )
    assert "v1_baseline_holdout" in result, (
        f"Expected 'v1_baseline_holdout' key in result, got: {list(result.keys())}"
    )
    score = result["v1_baseline_holdout"]
    assert isinstance(score, float), (
        f"v1_baseline_holdout must be float, got {type(score)}"
    )
    assert 0.0 <= score <= 1.0, (
        f"v1_baseline_holdout must be in [0,1], got {score}"
    )
