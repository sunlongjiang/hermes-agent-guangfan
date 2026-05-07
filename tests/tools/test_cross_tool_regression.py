"""Wave 0 RED tests for per-tool rate persistence in metrics.json.

Tests D-12: per_tool_baseline_rates + per_tool_evolved_rates written to metrics dict.
Fails until 13-06 adds persist_per_tool_rates() helper to evolution/tools/tool_metric.py.
"""

import pytest


def test_per_tool_persistence():
    """persist_per_tool_rates() adds per_tool_baseline_rates and per_tool_evolved_rates to metrics.

    D-12: CrossToolRegressionChecker computes per-tool rates; persist helper
    writes them into the metrics dict for D-12 traceability.
    """
    pytest.importorskip("dspy")
    from evolution.tools.tool_metric import persist_per_tool_rates  # fails until 13-06

    metrics = {
        "evolved_score": 0.88,
        "baseline_score": 0.85,
    }
    baseline_rates = {
        "search_files": 0.90,
        "memory_store": 0.80,
        "terminal_run": 0.85,
    }
    evolved_rates = {
        "search_files": 0.92,
        "memory_store": 0.83,
        "terminal_run": 0.87,
    }

    result = persist_per_tool_rates(metrics, baseline_rates, evolved_rates)

    assert "per_tool_baseline_rates" in result, (
        f"Expected 'per_tool_baseline_rates' key in metrics after persist, "
        f"got keys: {list(result.keys())}"
    )
    assert "per_tool_evolved_rates" in result, (
        f"Expected 'per_tool_evolved_rates' key in metrics after persist, "
        f"got keys: {list(result.keys())}"
    )

    # Both must be dict[str, float]
    baseline = result["per_tool_baseline_rates"]
    evolved = result["per_tool_evolved_rates"]
    assert isinstance(baseline, dict), (
        f"per_tool_baseline_rates must be dict, got {type(baseline)}"
    )
    assert isinstance(evolved, dict), (
        f"per_tool_evolved_rates must be dict, got {type(evolved)}"
    )
    for tool_name, rate in baseline.items():
        assert isinstance(tool_name, str), f"tool key must be str, got {type(tool_name)}"
        assert isinstance(rate, float), f"rate must be float, got {type(rate)}"
    for tool_name, rate in evolved.items():
        assert isinstance(tool_name, str), f"tool key must be str, got {type(tool_name)}"
        assert isinstance(rate, float), f"rate must be float, got {type(rate)}"

    # Original metrics preserved
    assert result["evolved_score"] == 0.88, "Original metrics must be preserved"
