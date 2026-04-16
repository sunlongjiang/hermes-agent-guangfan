"""Tests for tool selection metric and cross-tool regression checker."""

import dspy
import pytest

from evolution.tools.tool_metric import tool_selection_metric


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
