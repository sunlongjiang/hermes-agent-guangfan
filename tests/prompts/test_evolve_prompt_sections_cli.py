"""Phase 17 -- CLI integration tests for joint mode + --mode flag.

Pattern: CliRunner + fake-GEPA mock, mirroring Phase 13
tests/tools/test_evolve_tool_params_cli.py multi-patch style. No real LM
calls; dspy.GEPA().compile is mocked to return the module unchanged.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


def _make_fake_sections(n: int = 3):
    """Build n fake PromptSection instances for CLI mock tests."""
    from evolution.prompts.prompt_loader import PromptSection

    return [
        PromptSection(
            section_id=f"section_{i}",
            text=f"Section {i} original text",
            char_count=20,
            line_range=(i * 10, i * 10 + 5),
            source_path=Path("/fake/prompt_builder.py"),
        )
        for i in range(n)
    ]


def _make_mocked_dataset():
    """Build a fake PromptBehavioralDataset with all required split data."""
    from evolution.prompts.prompt_dataset import (
        PromptBehavioralExample,
        PromptBehavioralDataset,
    )

    # Cover every fake section id (section_0, section_1, section_2) so
    # the round-robin per-section filter loop has data for each.
    examples = [
        PromptBehavioralExample(
            section_id=f"section_{i}",
            user_message=f"task for section {i}",
            expected_behavior=f"behave per section {i}",
            difficulty="easy",
        )
        for i in range(3)
    ]
    return PromptBehavioralDataset(
        train=list(examples),
        val=list(examples),
        holdout=list(examples),
    )


class TestJointPipeline:
    """Tests for --mode joint vs --mode round-robin CLI routing."""

    def _patched_run(self, argv: list[str], fake_sections=None):
        """Helper: invoke main() with full patch stack and return (result, mock_gepa, spy_module, mock_module_cls).

        We construct a real PromptModule (for state-machine correctness) and
        wrap it in a MagicMock(wraps=...) so we can assert on
        set_joint_mode / set_active_section call counts while keeping
        named_predictors / _section_ids working.
        """
        from click.testing import CliRunner
        from evolution.prompts.evolve_prompt_sections import main
        from evolution.prompts.prompt_module import PromptModule

        if fake_sections is None:
            fake_sections = _make_fake_sections(3)

        fake_ds = _make_mocked_dataset()

        mock_constraint = MagicMock()
        mock_constraint._check_growth.return_value = MagicMock(
            passed=True, message="ok", constraint_name="growth"
        )
        mock_constraint._check_non_empty.return_value = MagicMock(
            passed=True, message="ok", constraint_name="non_empty"
        )

        mock_role = MagicMock()
        mock_role.check_all.return_value = []

        mock_metric_instance = MagicMock(return_value=0.5)

        mock_builder_instance = MagicMock()
        mock_builder_instance.generate.return_value = fake_ds

        # Real PromptModule (proxied by MagicMock) — exercises the actual
        # joint-mode state machine while letting us count calls.
        real_module = PromptModule(fake_sections)
        spy_module = MagicMock(wraps=real_module)
        spy_module._section_ids = real_module._section_ids
        spy_module.section_predictors = real_module.section_predictors
        spy_module.get_evolved_sections.return_value = fake_sections
        # Drive budget math: named_predictors returns N entries (selector filtered)
        spy_module.named_predictors.return_value = [
            (f"section_predictors['{sid}']", MagicMock())
            for sid in real_module._section_ids
        ]

        runner = CliRunner()

        with patch(
            "evolution.prompts.evolve_prompt_sections.extract_prompt_sections",
            return_value=fake_sections,
        ), patch(
            "evolution.prompts.evolve_prompt_sections.PromptDatasetBuilder",
            return_value=mock_builder_instance,
        ), patch(
            "evolution.prompts.evolve_prompt_sections.PromptBehavioralMetric",
            return_value=mock_metric_instance,
        ), patch(
            "evolution.prompts.evolve_prompt_sections.ConstraintValidator",
            return_value=mock_constraint,
        ), patch(
            "evolution.prompts.evolve_prompt_sections.PromptRoleChecker",
            return_value=mock_role,
        ), patch(
            "evolution.prompts.evolve_prompt_sections.PromptModule",
            return_value=spy_module,
        ) as mock_module_cls, patch(
            "evolution.prompts.evolve_prompt_sections.dspy.GEPA"
        ) as mock_gepa, patch(
            "evolution.prompts.evolve_prompt_sections.dspy.LM"
        ), patch(
            "evolution.prompts.evolve_prompt_sections.dspy.configure"
        ), patch(
            "evolution.prompts.evolve_prompt_sections.dspy.context",
            MagicMock(),
        ):
            mock_gepa.return_value.compile.side_effect = (
                lambda mod, trainset, valset=None: mod
            )
            result = runner.invoke(main, argv, catch_exceptions=False)

        return result, mock_gepa, spy_module, mock_module_cls

    def test_joint_mode_default_calls_gepa_with_component_selector_all(self):
        """Default mode (no --mode flag) routes to joint: single GEPA.compile +
        component_selector='all' + set_joint_mode(True) called exactly once."""
        result, mock_gepa, spy_module, _ = self._patched_run(
            ["--iterations", "2", "--hermes-repo", "/fake"],
            fake_sections=_make_fake_sections(3),
        )

        assert result.exit_code == 0, (
            f"Expected exit 0, got {result.exit_code}. "
            f"Output: {result.output[:500]}"
        )
        assert mock_gepa.called, "dspy.GEPA was never instantiated in joint mode"
        init_kwargs = mock_gepa.call_args.kwargs
        assert init_kwargs.get("component_selector") == "all", (
            f"Joint mode must call GEPA with component_selector='all', "
            f"got {init_kwargs.get('component_selector')!r}"
        )
        # Joint mode does ONE compile call (not per-section)
        assert mock_gepa.return_value.compile.call_count == 1, (
            f"Joint mode expected exactly 1 GEPA.compile() call, got "
            f"{mock_gepa.return_value.compile.call_count}"
        )
        # set_joint_mode(True) was called (proves we entered joint branch)
        spy_module.set_joint_mode.assert_called_with(True)
        # set_active_section must NOT have been called for joint pipeline
        assert spy_module.set_active_section.call_count == 0, (
            f"Joint mode should not call set_active_section; got "
            f"{spy_module.set_active_section.call_count} calls"
        )

    def test_round_robin_mode_compiles_per_section(self):
        """--mode round-robin routes to per-section for-loop: N compile calls,
        N set_active_section calls, zero set_joint_mode calls."""
        fake_sections = _make_fake_sections(3)
        result, mock_gepa, spy_module, _ = self._patched_run(
            ["--mode", "round-robin", "--iterations", "2", "--hermes-repo", "/fake"],
            fake_sections=fake_sections,
        )

        assert result.exit_code == 0, f"Output: {result.output[:500]}"
        # GEPA.__init__ should NOT receive component_selector='all' in round-robin
        init_kwargs = mock_gepa.call_args.kwargs
        assert init_kwargs.get("component_selector") != "all", (
            f"Round-robin must not pass component_selector='all'; "
            f"got {init_kwargs!r}"
        )
        # One compile per section
        assert mock_gepa.return_value.compile.call_count == len(fake_sections), (
            f"Round-robin expected {len(fake_sections)} compile calls, got "
            f"{mock_gepa.return_value.compile.call_count}"
        )
        # set_active_section called per section
        assert spy_module.set_active_section.call_count == len(fake_sections)
        # set_joint_mode NEVER called
        spy_module.set_joint_mode.assert_not_called()

    def test_section_flag_forces_round_robin_even_when_mode_joint(self):
        """--section X --mode joint should still go single-section round-robin (D-RR-03)."""
        fake_sections = _make_fake_sections(3)
        target_sid = fake_sections[1].section_id
        result, mock_gepa, spy_module, _ = self._patched_run(
            [
                "--section",
                target_sid,
                "--mode",
                "joint",
                "--iterations",
                "2",
                "--hermes-repo",
                "/fake",
            ],
            fake_sections=fake_sections,
        )

        assert result.exit_code == 0, f"Output: {result.output[:500]}"
        # Only the target section was activated
        assert spy_module.set_active_section.call_count == 1
        spy_module.set_active_section.assert_called_with(target_sid)
        # Single compile (single section)
        assert mock_gepa.return_value.compile.call_count == 1
        # set_joint_mode NEVER called (D-RR-03 implicit RR)
        spy_module.set_joint_mode.assert_not_called()


class TestDryRun:
    """Tests for --dry-run + --mode joint stdout budget preview."""

    def test_dry_run_joint_prints_budget_estimate(self):
        """--dry-run --mode joint prints 3-line budget preview + does not invoke GEPA."""
        from click.testing import CliRunner
        from evolution.prompts.evolve_prompt_sections import main

        fake_sections = _make_fake_sections(5)  # deterministic section count

        with patch(
            "evolution.prompts.evolve_prompt_sections.extract_prompt_sections",
            return_value=fake_sections,
        ), patch(
            "evolution.prompts.evolve_prompt_sections.dspy.GEPA"
        ) as mock_gepa:
            runner = CliRunner()
            result = runner.invoke(
                main,
                [
                    "--dry-run",
                    "--mode",
                    "joint",
                    "--iterations",
                    "10",
                    "--hermes-repo",
                    "/fake",
                ],
                catch_exceptions=False,
            )

        assert result.exit_code == 0, f"Dry-run failed: {result.output[:500]}"
        # 3-line D-IT-03 budget preview
        assert "Joint optimization:" in result.output, (
            f"Missing 'Joint optimization:' in dry-run stdout. "
            f"Output: {result.output[:800]}"
        )
        assert "Round-robin A/B baseline:" in result.output
        assert "Total est. LM calls:" in result.output
        # Numeric proof: 10 iterations * 5 sections, joint =
        # max(10*50, 3*5) * 5 = max(500, 15) * 5 = 2500
        assert "max_metric_calls=2500" in result.output, (
            f"Expected joint budget=2500 in dry-run; output: {result.output[:800]}"
        )
        # GEPA never instantiated in dry-run
        assert not mock_gepa.called, "dspy.GEPA was instantiated during dry-run"
