"""Tests for tool selection metric and cross-tool regression checker."""

import dspy
import pytest

from evolution.tools.tool_metric import (
    tool_selection_metric,
    CrossToolRegressionChecker,
    ToolRegressionResult,
)


# ── tool_selection_metric tests ──────────────────────────────────────────────


class TestToolSelectionMetric:
    """Tests for the binary tool_selection_metric function."""

    def test_exact_match_returns_1(self):
        """Exact match returns 1.0."""
        example = dspy.Example(correct_tool="memory")
        prediction = dspy.Prediction(selected_tool="memory")
        assert tool_selection_metric(example, prediction) == 1.0

    def test_case_insensitive_match_returns_1(self):
        """Case-insensitive match returns 1.0."""
        example = dspy.Example(correct_tool="Memory")
        prediction = dspy.Prediction(selected_tool="memory")
        assert tool_selection_metric(example, prediction) == 1.0

    def test_whitespace_trimmed_match_returns_1(self):
        """Whitespace-trimmed match returns 1.0."""
        example = dspy.Example(correct_tool="memory")
        prediction = dspy.Prediction(selected_tool="  memory  ")
        assert tool_selection_metric(example, prediction) == 1.0

    def test_mismatch_returns_0(self):
        """Mismatch returns 0.0."""
        example = dspy.Example(correct_tool="memory")
        prediction = dspy.Prediction(selected_tool="terminal")
        assert tool_selection_metric(example, prediction) == 0.0

    def test_empty_selected_tool_returns_0(self):
        """Empty selected_tool returns 0.0."""
        example = dspy.Example(correct_tool="memory")
        prediction = dspy.Prediction(selected_tool="")
        assert tool_selection_metric(example, prediction) == 0.0

    def test_missing_selected_tool_returns_0(self):
        """Missing selected_tool attribute returns 0.0 (getattr fallback)."""
        example = dspy.Example(correct_tool="memory")
        prediction = dspy.Prediction(other_field="something")
        assert tool_selection_metric(example, prediction) == 0.0

    def test_missing_correct_tool_returns_0(self):
        """Missing correct_tool attribute returns 0.0 (getattr fallback)."""
        example = dspy.Example(task_description="do something")
        prediction = dspy.Prediction(selected_tool="memory")
        assert tool_selection_metric(example, prediction) == 0.0

    def test_trace_parameter_accepted_but_ignored(self):
        """trace parameter is accepted but ignored (DSPy compatibility)."""
        example = dspy.Example(correct_tool="memory")
        prediction = dspy.Prediction(selected_tool="memory")
        assert tool_selection_metric(example, prediction, trace="some_trace") == 1.0
        assert tool_selection_metric(example, prediction, trace=None) == 1.0


# ── CrossToolRegressionChecker tests ─────────────────────────────────────────


class TestComputePerToolRates:
    """Tests for CrossToolRegressionChecker.compute_per_tool_rates."""

    def test_correct_per_tool_accuracy(self):
        """compute_per_tool_rates returns correct per-tool accuracy from example list."""
        checker = CrossToolRegressionChecker()
        predictions = [
            ("memory", "memory"),
            ("memory", "memory"),
            ("memory", "terminal"),
            ("terminal", "terminal"),
            ("terminal", "memory"),
        ]
        rates = checker.compute_per_tool_rates(predictions)
        assert abs(rates["memory"] - 2 / 3) < 1e-9
        assert abs(rates["terminal"] - 1 / 2) < 1e-9

    def test_empty_predictions(self):
        """Empty predictions returns empty dict."""
        checker = CrossToolRegressionChecker()
        rates = checker.compute_per_tool_rates([])
        assert rates == {}


class TestCheckRegression:
    """Tests for CrossToolRegressionChecker.check_regression."""

    def test_no_regression_passes(self):
        """ToolRegressionResult.passed is True when no tool regresses >2pp."""
        checker = CrossToolRegressionChecker()
        baseline = {"memory": 0.80, "terminal": 0.90}
        evolved = {"memory": 0.79, "terminal": 0.91}
        result = checker.check_regression(baseline, evolved)
        assert result.passed is True
        assert result.regressed_tools == []

    def test_regression_detected_fails(self):
        """ToolRegressionResult.passed is False when any tool drops >2pp."""
        checker = CrossToolRegressionChecker()
        baseline = {"memory": 0.80, "terminal": 0.90}
        evolved = {"memory": 0.77, "terminal": 0.91}
        result = checker.check_regression(baseline, evolved)
        assert result.passed is False
        assert "memory" in result.regressed_tools

    def test_regressed_tools_lists_exactly_regressed(self):
        """regressed_tools lists exactly the tools that regressed."""
        checker = CrossToolRegressionChecker()
        baseline = {"memory": 0.80, "terminal": 0.90, "search": 0.70}
        evolved = {"memory": 0.77, "terminal": 0.91, "search": 0.67}
        result = checker.check_regression(baseline, evolved)
        assert sorted(result.regressed_tools) == ["memory", "search"]

    def test_boundary_exactly_2pp_passes(self):
        """Boundary case: exactly 2pp drop (0.80 -> 0.78) passes (not strictly greater)."""
        checker = CrossToolRegressionChecker()
        baseline = {"memory": 0.80}
        evolved = {"memory": 0.78}
        result = checker.check_regression(baseline, evolved)
        assert result.passed is True

    def test_boundary_2_01pp_fails(self):
        """Boundary case: 2.01pp drop (0.80 -> 0.7799) fails."""
        checker = CrossToolRegressionChecker()
        baseline = {"memory": 0.80}
        evolved = {"memory": 0.7799}
        result = checker.check_regression(baseline, evolved)
        assert result.passed is False
        assert "memory" in result.regressed_tools

    def test_tool_with_zero_baseline_handled(self):
        """Tool with 0 baseline examples is handled gracefully."""
        checker = CrossToolRegressionChecker()
        # Tool not in baseline but in evolved -- no regression possible
        baseline = {"memory": 0.80}
        evolved = {"memory": 0.80, "new_tool": 1.0}
        result = checker.check_regression(baseline, evolved)
        assert result.passed is True

    def test_tool_missing_from_evolved_uses_zero(self):
        """Tool in baseline but missing from evolved uses 0.0 rate."""
        checker = CrossToolRegressionChecker()
        baseline = {"memory": 0.80}
        evolved = {}
        result = checker.check_regression(baseline, evolved)
        assert result.passed is False
        assert "memory" in result.regressed_tools
