"""Tests for PromptRoleChecker and growth constraint reuse.

Covers:
- _parse_bool() with all branch types (bool, string true/false variants, garbage)
- PromptRoleChecker.check() pass/fail paths via mocked DSPy calls
- PromptRoleChecker.check_all() batch checking and unmatched section handling
- ConstraintValidator._check_growth() reuse for prompt sections
- ConstraintValidator._check_non_empty() reuse verification
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintResult, ConstraintValidator
from evolution.prompts.prompt_constraints import PromptRoleChecker, _parse_bool
from evolution.prompts.prompt_loader import PromptSection


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

    def test_empty_string(self):
        assert _parse_bool("") is False

    def test_whitespace_padded(self):
        assert _parse_bool("  True  ") is True

    def test_maybe_returns_false(self):
        """Conservative: ambiguous text returns False."""
        assert _parse_bool("maybe") is False


# ── PromptRoleChecker.check() tests ─────────────────────────────────────────


class TestPromptRoleChecker:
    """Test PromptRoleChecker with mocked DSPy calls."""

    def _make_checker(self):
        """Create a PromptRoleChecker with mocked config."""
        config = EvolutionConfig.__new__(EvolutionConfig)
        config.eval_model = "openai/gpt-4.1-mini"
        return PromptRoleChecker(config)

    def test_check_role_preserved(self):
        """When LLM says role is preserved, check() returns passed=True."""
        checker = self._make_checker()

        mock_result = MagicMock()
        mock_result.role_preserved = "True"
        mock_result.explanation = "Role maintained: still provides memory guidance"

        with patch.object(checker, "checker", return_value=mock_result):
            with patch("evolution.prompts.prompt_constraints.dspy.LM"):
                with patch("evolution.prompts.prompt_constraints.dspy.context"):
                    result = checker.check(
                        "memory_guidance",
                        "Guide the agent on memory usage.",
                        "Help the agent use memory effectively.",
                    )

        assert isinstance(result, ConstraintResult)
        assert result.passed is True
        assert result.constraint_name == "role_preservation"
        assert "memory_guidance" in result.message
        assert "Role maintained" in result.details

    def test_check_role_changed(self):
        """When LLM says role changed, check() returns passed=False."""
        checker = self._make_checker()

        mock_result = MagicMock()
        mock_result.role_preserved = "False"
        mock_result.explanation = "Role shifted: now about identity, not memory"

        with patch.object(checker, "checker", return_value=mock_result):
            with patch("evolution.prompts.prompt_constraints.dspy.LM"):
                with patch("evolution.prompts.prompt_constraints.dspy.context"):
                    result = checker.check(
                        "memory_guidance",
                        "Guide the agent on memory usage.",
                        "You are a helpful AI assistant named Hermes.",
                    )

        assert isinstance(result, ConstraintResult)
        assert result.passed is False
        assert result.constraint_name == "role_preservation"
        assert "memory_guidance" in result.message
        assert "Role shifted" in result.details

    def test_constraint_name_always_role_preservation(self):
        """constraint_name is always 'role_preservation'."""
        checker = self._make_checker()

        mock_result = MagicMock()
        mock_result.role_preserved = "True"
        mock_result.explanation = "OK"

        with patch.object(checker, "checker", return_value=mock_result):
            with patch("evolution.prompts.prompt_constraints.dspy.LM"):
                with patch("evolution.prompts.prompt_constraints.dspy.context"):
                    result = checker.check("sid", "a", "b")

        assert result.constraint_name == "role_preservation"

    def test_check_all_matches_by_section_id(self):
        """check_all() matches sections by section_id and returns results."""
        checker = self._make_checker()

        originals = [
            PromptSection(
                section_id="memory_guidance",
                text="Guide memory usage.",
                char_count=19,
                line_range=(10, 15),
                source_path=Path("/fake/prompt_builder.py"),
            ),
            PromptSection(
                section_id="skills_guidance",
                text="Guide skill usage.",
                char_count=18,
                line_range=(20, 25),
                source_path=Path("/fake/prompt_builder.py"),
            ),
        ]
        evolved = [
            PromptSection(
                section_id="memory_guidance",
                text="Use memory effectively.",
                char_count=22,
                line_range=(10, 15),
                source_path=Path("/fake/prompt_builder.py"),
            ),
            PromptSection(
                section_id="skills_guidance",
                text="Use skills wisely.",
                char_count=18,
                line_range=(20, 25),
                source_path=Path("/fake/prompt_builder.py"),
            ),
        ]

        mock_result = MagicMock()
        mock_result.role_preserved = "True"
        mock_result.explanation = "OK"

        with patch.object(checker, "checker", return_value=mock_result):
            with patch("evolution.prompts.prompt_constraints.dspy.LM"):
                with patch("evolution.prompts.prompt_constraints.dspy.context"):
                    results = checker.check_all(originals, evolved)

        assert len(results) == 2
        assert all(isinstance(r, ConstraintResult) for r in results)

    def test_check_all_skips_unmatched(self):
        """Evolved sections with no matching original are skipped."""
        checker = self._make_checker()

        originals = [
            PromptSection(
                section_id="memory_guidance",
                text="Guide memory usage.",
                char_count=19,
                line_range=(10, 15),
                source_path=Path("/fake/prompt_builder.py"),
            ),
        ]
        evolved = [
            PromptSection(
                section_id="memory_guidance",
                text="Use memory effectively.",
                char_count=22,
                line_range=(10, 15),
                source_path=Path("/fake/prompt_builder.py"),
            ),
            PromptSection(
                section_id="nonexistent_section",
                text="This has no original.",
                char_count=21,
                line_range=(30, 35),
                source_path=Path("/fake/prompt_builder.py"),
            ),
        ]

        mock_result = MagicMock()
        mock_result.role_preserved = "True"
        mock_result.explanation = "OK"

        with patch.object(checker, "checker", return_value=mock_result):
            with patch("evolution.prompts.prompt_constraints.dspy.LM"):
                with patch("evolution.prompts.prompt_constraints.dspy.context"):
                    results = checker.check_all(originals, evolved)

        assert len(results) == 1  # Only memory_guidance matched


# ── Growth constraint reuse tests (PMPT-08 verification) ────────────────────


class TestGrowthConstraint:
    """Verify ConstraintValidator._check_growth() works for prompt sections."""

    def _make_validator(self):
        config = EvolutionConfig.__new__(EvolutionConfig)
        config.max_prompt_growth = 0.2  # 20% ceiling
        config.max_skill_size = 15_000
        return ConstraintValidator(config)

    def test_growth_within_limit(self):
        """10% growth (<=20%) passes."""
        v = self._make_validator()
        baseline = "x" * 100
        evolved = "x" * 110  # 10% growth
        result = v._check_growth(evolved, baseline, "prompt_section")
        assert result.passed is True

    def test_growth_exceeds_limit(self):
        """30% growth (>20%) fails."""
        v = self._make_validator()
        baseline = "x" * 100
        evolved = "x" * 130  # 30% growth
        result = v._check_growth(evolved, baseline, "prompt_section")
        assert result.passed is False

    def test_growth_at_exact_limit(self):
        """Exactly 20% growth passes (<=20%)."""
        v = self._make_validator()
        baseline = "x" * 100
        evolved = "x" * 120  # 20% growth exactly
        result = v._check_growth(evolved, baseline, "prompt_section")
        assert result.passed is True

    def test_non_empty_passes(self):
        """Non-empty text passes."""
        v = self._make_validator()
        result = v._check_non_empty("some text")
        assert result.passed is True

    def test_non_empty_fails(self):
        """Empty string fails."""
        v = self._make_validator()
        result = v._check_non_empty("")
        assert result.passed is False

    def test_non_empty_whitespace_fails(self):
        """Whitespace-only string fails."""
        v = self._make_validator()
        result = v._check_non_empty("   ")
        assert result.passed is False
