"""Tests for PromptModule -- DSPy module wrapping prompt sections for GEPA optimization."""

from pathlib import Path
from unittest.mock import patch

import dspy
import pytest

from evolution.prompts.prompt_loader import PromptSection
from evolution.prompts.prompt_module import PromptModule


# ── Test Fixtures ───────────────────────────────────────────────────────────

def _make_prompt_sections() -> list[PromptSection]:
    """Create 3 test PromptSection instances for testing."""
    return [
        PromptSection(
            section_id="default_agent_identity",
            text="You are a helpful AI assistant.",
            char_count=30,
            line_range=(10, 15),
            source_path=Path("/fake/prompt_builder.py"),
        ),
        PromptSection(
            section_id="memory_guidance",
            text="Use memory tools to store important context.",
            char_count=45,
            line_range=(20, 25),
            source_path=Path("/fake/prompt_builder.py"),
        ),
        PromptSection(
            section_id="skills_guidance",
            text="Leverage available skills for complex tasks.",
            char_count=44,
            line_range=(30, 35),
            source_path=Path("/fake/prompt_builder.py"),
        ),
    ]


# ── TestPromptModule ───────────────────────────────────────────────────────

class TestPromptModule:
    """Core PromptModule construction tests."""

    def test_constructor_accepts_prompt_sections(self):
        """PromptModule(sections) constructs without error."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        assert module is not None

    def test_section_predictor_instructions(self):
        """After set_active_section, the active predictor's instructions equal the original text."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_active_section("memory_guidance")
        pred = module.section_predictors["memory_guidance"]
        assert pred.signature.instructions == "Use memory tools to store important context."

    def test_no_predictors_before_active_set(self):
        """Before set_active_section(), named_parameters() returns only the selector."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        # section_predictors should be empty before set_active_section
        assert len(module.section_predictors) == 0


# ── TestActiveSection ──────────────────────────────────────────────────────

class TestActiveSection:
    """Tests for set_active_section switching behavior."""

    def test_set_active_section_moves_to_discoverable(self):
        """After set_active_section, named_parameters() includes exactly 1 section predictor."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_active_section("memory_guidance")

        # Count section predictors (exclude selector)
        assert len(module.section_predictors) == 1
        assert "memory_guidance" in module.section_predictors

    def test_set_active_section_invalid_raises(self):
        """set_active_section with unknown section raises ValueError."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        with pytest.raises(ValueError, match="Unknown section"):
            module.set_active_section("nonexistent")

    def test_switch_active_section(self):
        """Switching active section moves previous back to frozen."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_active_section("memory_guidance")
        module.set_active_section("skills_guidance")

        # Only skills_guidance should be in section_predictors
        assert len(module.section_predictors) == 1
        assert "skills_guidance" in module.section_predictors
        assert "memory_guidance" not in module.section_predictors
        # memory_guidance should be back in frozen
        assert "memory_guidance" in module._frozen_predictors


# ── TestFrozenContext ──────────────────────────────────────────────────────

class TestFrozenContext:
    """Tests for frozen context construction."""

    def test_frozen_context_excludes_active(self):
        """_build_frozen_context() excludes active section, includes others."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_active_section("memory_guidance")
        context = module._build_frozen_context()

        assert "[memory_guidance]" not in context
        assert "[default_agent_identity]" in context
        assert "[skills_guidance]" in context

    def test_only_active_in_named_parameters(self):
        """After set_active_section, only active section's Predict is in named_parameters()."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_active_section("skills_guidance")

        param_names = [name for name, _ in module.named_parameters()]
        # Should find skills_guidance predictor but not others
        matching = [n for n in param_names if "skills_guidance" in n]
        assert len(matching) >= 1
        # Other sections should NOT appear
        for other in ["default_agent_identity", "memory_guidance"]:
            other_matching = [n for n in param_names if other in n]
            assert len(other_matching) == 0, (
                f"Found frozen section {other} in named_parameters: {param_names}"
            )


# ── TestForward ────────────────────────────────────────────────────────────

class TestForward:
    """Tests for forward() method."""

    def test_forward_without_active_raises(self):
        """Calling forward() before set_active_section() raises RuntimeError."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        with pytest.raises(RuntimeError, match="No active section"):
            module.forward("test input")

    def test_forward_returns_prediction(self):
        """With active section set and selector mocked, forward returns Prediction."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_active_section("memory_guidance")

        mock_result = dspy.Prediction(output="mocked response")
        with patch.object(module.selector, "forward", return_value=mock_result):
            result = module.forward("test input")

        assert isinstance(result, dspy.Prediction)
        assert result.output == "mocked response"


# ── TestGetEvolvedSections ─────────────────────────────────────────────────

class TestGetEvolvedSections:
    """Tests for get_evolved_sections() output."""

    def test_returns_prompt_section_list(self):
        """get_evolved_sections() returns list[PromptSection] with correct length."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        evolved = module.get_evolved_sections()

        assert isinstance(evolved, list)
        assert len(evolved) == 3
        assert all(isinstance(s, PromptSection) for s in evolved)

    def test_evolved_text_reflects_predictor(self):
        """After updating predictor instructions, evolved text reflects the change."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_active_section("memory_guidance")

        # Simulate GEPA evolving the instructions
        module.section_predictors["memory_guidance"].signature = (
            module.section_predictors["memory_guidance"].signature.with_instructions(
                "EVOLVED memory guidance text"
            )
        )

        evolved = module.get_evolved_sections()
        memory = next(s for s in evolved if s.section_id == "memory_guidance")
        assert memory.text == "EVOLVED memory guidance text"

    def test_char_count_updated(self):
        """Evolved section's char_count equals len(evolved_text), not original."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_active_section("memory_guidance")

        new_text = "SHORT"
        module.section_predictors["memory_guidance"].signature = (
            module.section_predictors["memory_guidance"].signature.with_instructions(new_text)
        )

        evolved = module.get_evolved_sections()
        memory = next(s for s in evolved if s.section_id == "memory_guidance")
        assert memory.char_count == len(new_text)
        assert memory.char_count == 5

    def test_frozen_metadata_preserved(self):
        """Evolved section preserves original section_id, line_range, source_path."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        evolved = module.get_evolved_sections()

        memory = next(s for s in evolved if s.section_id == "memory_guidance")
        assert memory.section_id == "memory_guidance"
        assert memory.line_range == (20, 25)
        assert memory.source_path == Path("/fake/prompt_builder.py")
