"""Tests for ToolFactualChecker and size constraint reuse.

Covers:
- _parse_bool() with all branch types (bool, string true/false variants, garbage)
- ToolFactualChecker.check() pass/fail paths via mocked DSPy calls
- ToolFactualChecker.check_all() batch checking and unmatched tool handling
- ConstraintValidator._check_size() reuse for tool_description and param_description
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintResult, ConstraintValidator
from evolution.tools.tool_constraints import ToolFactualChecker, _parse_bool
from evolution.tools.tool_loader import ToolDescription


# ── _parse_bool tests ────────────────────────────────────────────────────────


class TestParseBool:
    """Test _parse_bool helper with various LLM output formats."""

    def test_bool_true(self):
        assert _parse_bool(True) is True

    def test_bool_false(self):
        assert _parse_bool(False) is False

    def test_string_true_capitalized(self):
        assert _parse_bool("True") is True

    def test_string_true_lower(self):
        assert _parse_bool("true") is True

    def test_string_yes(self):
        assert _parse_bool("yes") is True

    def test_string_one(self):
        assert _parse_bool("1") is True

    def test_string_false_capitalized(self):
        assert _parse_bool("False") is False

    def test_string_false_lower(self):
        assert _parse_bool("false") is False

    def test_string_no(self):
        assert _parse_bool("no") is False

    def test_string_zero(self):
        assert _parse_bool("0") is False

    def test_random_text(self):
        assert _parse_bool("random text") is False

    def test_whitespace_padded(self):
        assert _parse_bool("  True  ") is True


# ── ToolFactualChecker.check() tests ────────────────────────────────────────


class TestToolFactualCheckerCheck:
    """Test check() with mocked DSPy calls."""

    def _make_checker(self):
        """Create a ToolFactualChecker with mocked config."""
        config = EvolutionConfig.__new__(EvolutionConfig)
        config.eval_model = "openai/gpt-4.1-mini"
        return ToolFactualChecker(config)

    def test_false_claims_detected(self):
        """When LLM detects false claims, check() returns passed=False."""
        checker = self._make_checker()

        mock_result = MagicMock()
        mock_result.has_false_claims = "True"
        mock_result.explanation = "Added fake capability: can read minds"

        with patch.object(checker, "checker", return_value=mock_result):
            with patch("evolution.tools.tool_constraints.dspy.LM"):
                with patch("evolution.tools.tool_constraints.dspy.context"):
                    result = checker.check(
                        "test_tool",
                        "Searches files",
                        "Searches files and reads minds",
                    )

        assert isinstance(result, ConstraintResult)
        assert result.passed is False
        assert result.constraint_name == "factual_accuracy"
        assert "Added fake capability" in result.details

    def test_no_false_claims(self):
        """When LLM finds no false claims, check() returns passed=True."""
        checker = self._make_checker()

        mock_result = MagicMock()
        mock_result.has_false_claims = "False"
        mock_result.explanation = "No issues found"

        with patch.object(checker, "checker", return_value=mock_result):
            with patch("evolution.tools.tool_constraints.dspy.LM"):
                with patch("evolution.tools.tool_constraints.dspy.context"):
                    result = checker.check(
                        "test_tool",
                        "Searches files in directory",
                        "Searches files in the specified directory",
                    )

        assert isinstance(result, ConstraintResult)
        assert result.passed is True
        assert result.constraint_name == "factual_accuracy"
        assert "No issues" in result.details

    def test_constraint_name_always_factual_accuracy(self):
        """constraint_name is always 'factual_accuracy'."""
        checker = self._make_checker()

        mock_result = MagicMock()
        mock_result.has_false_claims = "False"
        mock_result.explanation = "OK"

        with patch.object(checker, "checker", return_value=mock_result):
            with patch("evolution.tools.tool_constraints.dspy.LM"):
                with patch("evolution.tools.tool_constraints.dspy.context"):
                    result = checker.check("t", "a", "b")

        assert result.constraint_name == "factual_accuracy"


# ── ToolFactualChecker.check_all() tests ────────────────────────────────────


class TestToolFactualCheckerCheckAll:
    """Test check_all() batch checking."""

    def _make_tool(self, name: str, description: str) -> ToolDescription:
        """Create a minimal ToolDescription for testing."""
        return ToolDescription(
            name=name,
            file_path=Path("/fake/path.py"),
            description=description,
        )

    def _make_checker(self):
        config = EvolutionConfig.__new__(EvolutionConfig)
        config.eval_model = "openai/gpt-4.1-mini"
        return ToolFactualChecker(config)

    def test_all_tools_matched(self):
        """When all evolved tools have originals, returns result for each."""
        checker = self._make_checker()

        originals = [
            self._make_tool("tool_a", "Does A"),
            self._make_tool("tool_b", "Does B"),
        ]
        evolved = [
            self._make_tool("tool_a", "Does A better"),
            self._make_tool("tool_b", "Does B better"),
        ]

        mock_result = MagicMock()
        mock_result.has_false_claims = "False"
        mock_result.explanation = "OK"

        with patch.object(checker, "checker", return_value=mock_result):
            with patch("evolution.tools.tool_constraints.dspy.LM"):
                with patch("evolution.tools.tool_constraints.dspy.context"):
                    results = checker.check_all(originals, evolved)

        assert len(results) == 2
        assert all(isinstance(r, ConstraintResult) for r in results)

    def test_unmatched_tools_skipped(self):
        """Evolved tools not in originals are skipped."""
        checker = self._make_checker()

        originals = [self._make_tool("tool_a", "Does A")]
        evolved = [
            self._make_tool("tool_a", "Does A better"),
            self._make_tool("tool_c", "Does C -- new tool"),
        ]

        mock_result = MagicMock()
        mock_result.has_false_claims = "False"
        mock_result.explanation = "OK"

        with patch.object(checker, "checker", return_value=mock_result):
            with patch("evolution.tools.tool_constraints.dspy.LM"):
                with patch("evolution.tools.tool_constraints.dspy.context"):
                    results = checker.check_all(originals, evolved)

        assert len(results) == 1  # Only tool_a matched


# ── Size constraint reuse tests (TOOL-10 verification) ──────────────────────


class TestSizeConstraintReuse:
    """Verify ConstraintValidator._check_size() works for tool descriptions."""

    def _make_validator(self):
        config = EvolutionConfig.__new__(EvolutionConfig)
        config.max_tool_desc_size = 500
        config.max_param_desc_size = 200
        config.max_skill_size = 15_000
        return ConstraintValidator(config)

    def test_tool_description_over_limit(self):
        v = self._make_validator()
        result = v._check_size("x" * 501, "tool_description")
        assert result.passed is False

    def test_tool_description_at_limit(self):
        v = self._make_validator()
        result = v._check_size("x" * 500, "tool_description")
        assert result.passed is True

    def test_param_description_over_limit(self):
        v = self._make_validator()
        result = v._check_size("x" * 201, "param_description")
        assert result.passed is False

    def test_param_description_at_limit(self):
        v = self._make_validator()
        result = v._check_size("x" * 200, "param_description")
        assert result.passed is True
