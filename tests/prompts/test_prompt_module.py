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
        # memory_guidance should be back in frozen instructions
        assert "memory_guidance" in module._frozen_instructions


# ── TestFrozenContext ──────────────────────────────────────────────────────

class TestFrozenContext:
    """Tests for frozen context construction."""

    def test_frozen_context_includes_active(self):
        """_build_frozen_context() includes ALL sections (Phase 17 / Pitfall 1 fix).

        Pre-Phase-17 the active section was excluded from frozen_context, which
        meant GEPA mutations to the active section's Predict.signature.instructions
        had no path to the selector's input — mutations were effectively no-ops.
        Phase 17 fixes this: the active section's CURRENT instructions (read from
        section_predictors[active].signature.instructions) are now part of
        frozen_context. See evolution/prompts/prompt_module.py _build_frozen_context.
        """
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_active_section("memory_guidance")
        context = module._build_frozen_context()

        # Phase 17 / Pitfall 1 fix: active section text now flows into frozen_context
        assert "[memory_guidance]:" in context
        # Active text content (from the Predict's signature.instructions) is present
        assert "Use memory tools to store important context." in context
        assert "[default_agent_identity]:" in context
        assert "[skills_guidance]:" in context

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


# ── TestJointMode (Phase 17) ───────────────────────────────────────────────


class TestJointMode:
    """Tests for Phase 17 joint mode: all sections simultaneously optimizable."""

    def test_set_joint_mode_exposes_all_predictors(self):
        """set_joint_mode(True) promotes all sections to section_predictors."""
        from evolution.prompts.prompt_module import JOINT_SENTINEL

        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_joint_mode(True)

        assert len(module.section_predictors) == 3
        assert set(module.section_predictors.keys()) == {
            "default_agent_identity",
            "memory_guidance",
            "skills_guidance",
        }
        assert len(module._frozen_instructions) == 0
        assert module._active_section == JOINT_SENTINEL
        # Each predictor has the original instructions
        assert (
            module.section_predictors["memory_guidance"].signature.instructions
            == "Use memory tools to store important context."
        )

    def test_set_joint_mode_idempotent(self):
        """Calling set_joint_mode(True) twice is a no-op (no errors, no state change)."""
        from evolution.prompts.prompt_module import JOINT_SENTINEL

        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_joint_mode(True)
        module.set_joint_mode(True)  # Should not raise or duplicate

        assert len(module.section_predictors) == 3
        assert module._active_section == JOINT_SENTINEL

    def test_set_joint_mode_false_demotes_all(self):
        """set_joint_mode(False) reverses joint mode — all sections back to frozen."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_joint_mode(True)
        module.set_joint_mode(False)

        assert len(module.section_predictors) == 0
        assert len(module._frozen_instructions) == 3
        assert module._active_section is None

    def test_joint_then_set_active_section_auto_demotes(self):
        """Calling set_active_section after set_joint_mode auto-demotes joint (Pitfall 3 fix).

        Without the auto-demote guard, set_active_section would try to
        pop JOINT_SENTINEL from section_predictors -> KeyError.
        """
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_joint_mode(True)
        module.set_active_section("memory_guidance")  # Must not raise

        assert module._active_section == "memory_guidance"
        assert len(module.section_predictors) == 1
        assert "memory_guidance" in module.section_predictors
        # Other two are back in frozen
        assert "default_agent_identity" in module._frozen_instructions
        assert "skills_guidance" in module._frozen_instructions

    def test_named_predictors_in_joint_mode_excludes_selector(self):
        """In joint mode, named_predictors() yields exactly N section_predictors
        entries, NOT selector.predict (Phase 17 Resolved Decision 2 — selector freeze).

        W4 revision: tightened from substring `"selector" in n` to exact-token
        checks. The previous loose substring match would silently pass if a
        future DSPy version introduced subcomponents like `selector.reasoning`
        that happen to contain the substring `"selector"` but are NOT the
        routing Predict we intend to freeze. We now check:
          (1) `selector.predict` is not in names (the exact name that
              super().named_predictors() yields for the ChainOfThought's
              underlying Predict — see RESEARCH §Pattern 4 dspy 3.1.3 inspection).
          (2) total length equals exactly 3 (one per fixture section), which
              fails loudly if any new subcomponent slips through.
        """
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_joint_mode(True)

        named = list(module.named_predictors())
        names = [n for n, _ in named]
        # Must contain all 3 section_predictors entries
        for sid in ["default_agent_identity", "memory_guidance", "skills_guidance"]:
            matching = [n for n in names if sid in n]
            assert len(matching) >= 1, (
                f"section_predictors[{sid}] missing from named_predictors(): {names}"
            )
        # W4: Tight selector exclusion check — exact-name, not substring
        assert "selector.predict" not in names, (
            f"selector.predict must be excluded in joint mode, but it's in: {names}"
        )
        # W4: Total entry count must equal section count exactly — fails loud
        # if dspy adds any new sub-predictor that bypasses _frozen_predictor_ids
        assert len(named) == 3, (
            f"Joint mode must expose exactly 3 predictors (one per section); "
            f"got {len(named)}: {names}. If dspy version added new subcomponents, "
            f"update _frozen_predictor_ids in PromptModule.__init__ accordingly."
        )

    def test_forward_in_joint_mode_uses_all_section_texts(self):
        """In joint mode, forward() builds frozen_context containing ALL N section texts."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_joint_mode(True)

        mock_result = dspy.Prediction(output="joint mocked response")
        with patch.object(module.selector, "forward", return_value=mock_result) as mock_sel:
            result = module.forward("test input")

        assert isinstance(result, dspy.Prediction)
        assert result.output == "joint mocked response"
        mock_sel.assert_called_once()
        kwargs = mock_sel.call_args.kwargs
        assert "frozen_context" in kwargs
        ctx = kwargs["frozen_context"]
        # All 3 sections must appear in frozen_context with their texts
        assert "[default_agent_identity]:" in ctx
        assert "You are a helpful AI assistant." in ctx
        assert "[memory_guidance]:" in ctx
        assert "Use memory tools to store important context." in ctx
        assert "[skills_guidance]:" in ctx
        assert "Leverage available skills for complex tasks." in ctx
        assert kwargs["task_input"] == "test input"

    def test_forward_in_round_robin_includes_active_text(self):
        """In round-robin (single active) mode, forward() includes active section's
        CURRENT Predict instructions in frozen_context (Pitfall 1 fix)."""
        sections = _make_prompt_sections()
        module = PromptModule(sections)
        module.set_active_section("memory_guidance")

        mock_result = dspy.Prediction(output="rr mocked response")
        with patch.object(module.selector, "forward", return_value=mock_result) as mock_sel:
            module.forward("test input")

        kwargs = mock_sel.call_args.kwargs
        ctx = kwargs["frozen_context"]
        # Pitfall 1 fix: active section text flows into frozen_context
        assert "[memory_guidance]:" in ctx
        assert "Use memory tools to store important context." in ctx
        # Other sections also present
        assert "[default_agent_identity]:" in ctx
        assert "[skills_guidance]:" in ctx
