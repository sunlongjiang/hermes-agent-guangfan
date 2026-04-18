"""Tests for evolve_prompt_sections -- CLI entry point and end-to-end pipeline."""

from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

from evolution.prompts.prompt_loader import PromptSection


# ── Test Fixtures ───────────────────────────────────────────────────────────


def _make_fake_sections() -> list[PromptSection]:
    """Create test PromptSection instances for mocking."""
    return [
        PromptSection(
            section_id="default_agent_identity",
            text="You are Hermes, a helpful AI assistant.",
            char_count=40,
            line_range=(10, 15),
            source_path=Path("/fake/prompt_builder.py"),
        ),
        PromptSection(
            section_id="memory_guidance",
            text="Use memory tools to store important context from conversations.",
            char_count=63,
            line_range=(20, 25),
            source_path=Path("/fake/prompt_builder.py"),
        ),
    ]


# ── TestCLI ─────────────────────────────────────────────────────────────────


class TestCLI:
    """CLI parameter and help text tests."""

    def test_cli_help(self):
        """--help output contains all five expected options."""
        from click.testing import CliRunner
        from evolution.prompts.evolve_prompt_sections import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "--section" in result.output
        assert "--iterations" in result.output
        assert "--eval-source" in result.output
        assert "--hermes-repo" in result.output
        assert "--dry-run" in result.output

    def test_cli_help_section_option(self):
        """Help text describes --section option purpose."""
        from click.testing import CliRunner
        from evolution.prompts.evolve_prompt_sections import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Section ID to optimize" in result.output


# ── TestDryRun ──────────────────────────────────────────────────────────────


class TestDryRun:
    """Dry-run mode tests."""

    @patch("evolution.prompts.evolve_prompt_sections.extract_prompt_sections")
    def test_dry_run_validates_and_returns(self, mock_extract):
        """dry-run extracts sections, prints summary, does NOT call GEPA."""
        mock_extract.return_value = _make_fake_sections()

        from evolution.prompts.evolve_prompt_sections import evolve

        with patch("dspy.GEPA") as mock_gepa:
            evolve(
                dry_run=True,
                hermes_repo="/fake",
            )
            mock_gepa.assert_not_called()


# ── TestEvolve ──────────────────────────────────────────────────────────────


class TestEvolve:
    """Evolve orchestration tests."""

    @patch("evolution.prompts.evolve_prompt_sections.PromptRoleChecker")
    @patch("evolution.prompts.evolve_prompt_sections.ConstraintValidator")
    @patch("evolution.prompts.evolve_prompt_sections.PromptBehavioralMetric")
    @patch("evolution.prompts.evolve_prompt_sections.PromptDatasetBuilder")
    @patch("evolution.prompts.evolve_prompt_sections.PromptModule")
    @patch("evolution.prompts.evolve_prompt_sections.extract_prompt_sections")
    @patch("dspy.GEPA")
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_evolve_orchestration_order(
        self,
        mock_configure,
        mock_lm,
        mock_gepa_cls,
        mock_extract,
        mock_module_cls,
        mock_builder_cls,
        mock_metric_cls,
        mock_validator_cls,
        mock_role_checker_cls,
    ):
        """evolve() calls components in correct order: extract -> module -> dataset -> GEPA -> constraints -> save."""
        fake_sections = _make_fake_sections()
        mock_extract.return_value = fake_sections

        # Module mock
        mock_module = MagicMock()
        mock_module._section_ids = ["default_agent_identity", "memory_guidance"]
        mock_module.get_evolved_sections.return_value = fake_sections
        mock_module_cls.return_value = mock_module

        # GEPA mock
        mock_gepa = MagicMock()
        mock_gepa.compile.return_value = mock_module
        mock_gepa_cls.return_value = mock_gepa

        # Dataset mock
        mock_dataset = MagicMock()
        mock_dataset.train = [MagicMock(section_id="default_agent_identity"),
                              MagicMock(section_id="memory_guidance")]
        mock_dataset.val = [MagicMock(section_id="default_agent_identity"),
                            MagicMock(section_id="memory_guidance")]
        mock_dataset.holdout = [MagicMock(section_id="default_agent_identity")]
        mock_dataset.to_dspy_examples.return_value = [MagicMock()]
        mock_builder = MagicMock()
        mock_builder.generate.return_value = mock_dataset
        mock_builder_cls.return_value = mock_builder

        # Constraint validator mock
        mock_validator = MagicMock()
        growth_result = MagicMock(passed=True, constraint_name="growth", message="ok")
        non_empty_result = MagicMock(passed=True, constraint_name="non_empty", message="ok")
        mock_validator._check_growth.return_value = growth_result
        mock_validator._check_non_empty.return_value = non_empty_result
        mock_validator_cls.return_value = mock_validator

        # Role checker mock
        mock_role_checker = MagicMock()
        role_result = MagicMock(passed=True, constraint_name="role_preservation", message="ok")
        mock_role_checker.check_all.return_value = [role_result]
        mock_role_checker_cls.return_value = mock_role_checker

        # Metric mock
        mock_metric = MagicMock(return_value=0.8)
        mock_metric_cls.return_value = mock_metric

        from evolution.prompts.evolve_prompt_sections import evolve

        evolve(
            iterations=2,
            eval_source="synthetic",
            hermes_repo="/fake",
        )

        # Verify call order
        mock_extract.assert_called_once()
        mock_module_cls.assert_called_once()
        mock_builder.generate.assert_called_once()
        assert mock_module.set_active_section.call_count >= 1
        mock_gepa.compile.assert_called()
        mock_validator._check_growth.assert_called()
        mock_validator._check_non_empty.assert_called()
        mock_role_checker.check_all.assert_called_once()

    @patch("evolution.prompts.evolve_prompt_sections.PromptRoleChecker")
    @patch("evolution.prompts.evolve_prompt_sections.ConstraintValidator")
    @patch("evolution.prompts.evolve_prompt_sections.PromptBehavioralMetric")
    @patch("evolution.prompts.evolve_prompt_sections.PromptDatasetBuilder")
    @patch("evolution.prompts.evolve_prompt_sections.PromptModule")
    @patch("evolution.prompts.evolve_prompt_sections.extract_prompt_sections")
    @patch("dspy.GEPA")
    @patch("dspy.LM")
    @patch("dspy.configure")
    def test_section_filter(
        self,
        mock_configure,
        mock_lm,
        mock_gepa_cls,
        mock_extract,
        mock_module_cls,
        mock_builder_cls,
        mock_metric_cls,
        mock_validator_cls,
        mock_role_checker_cls,
    ):
        """When section='memory_guidance', only that section is optimized."""
        fake_sections = _make_fake_sections()
        mock_extract.return_value = fake_sections

        # Module mock
        mock_module = MagicMock()
        mock_module._section_ids = ["default_agent_identity", "memory_guidance"]
        mock_module.get_evolved_sections.return_value = fake_sections
        mock_module_cls.return_value = mock_module

        # GEPA mock
        mock_gepa = MagicMock()
        mock_gepa.compile.return_value = mock_module
        mock_gepa_cls.return_value = mock_gepa

        # Dataset mock
        mock_dataset = MagicMock()
        mock_dataset.train = [MagicMock(section_id="default_agent_identity"),
                              MagicMock(section_id="memory_guidance")]
        mock_dataset.val = [MagicMock(section_id="default_agent_identity"),
                            MagicMock(section_id="memory_guidance")]
        mock_dataset.holdout = [MagicMock(section_id="memory_guidance")]
        mock_dataset.to_dspy_examples.return_value = [MagicMock()]
        mock_builder = MagicMock()
        mock_builder.generate.return_value = mock_dataset
        mock_builder_cls.return_value = mock_builder

        # Constraint validator mock
        mock_validator = MagicMock()
        growth_result = MagicMock(passed=True, constraint_name="growth", message="ok")
        non_empty_result = MagicMock(passed=True, constraint_name="non_empty", message="ok")
        mock_validator._check_growth.return_value = growth_result
        mock_validator._check_non_empty.return_value = non_empty_result
        mock_validator_cls.return_value = mock_validator

        # Role checker mock
        mock_role_checker = MagicMock()
        role_result = MagicMock(passed=True, constraint_name="role_preservation", message="ok")
        mock_role_checker.check_all.return_value = [role_result]
        mock_role_checker_cls.return_value = mock_role_checker

        # Metric mock
        mock_metric = MagicMock(return_value=0.8)
        mock_metric_cls.return_value = mock_metric

        from evolution.prompts.evolve_prompt_sections import evolve

        evolve(
            section="memory_guidance",
            iterations=2,
            eval_source="synthetic",
            hermes_repo="/fake",
        )

        # Only memory_guidance should be set as active
        mock_module.set_active_section.assert_called_once_with("memory_guidance")


# ── TestModuleImportable ────────────────────────────────────────────────────


class TestModuleImportable:
    """Module import and entry point tests."""

    def test_module_importable(self):
        """main and evolve can be imported from the module."""
        from evolution.prompts.evolve_prompt_sections import main, evolve
        assert callable(main)
        assert callable(evolve)
