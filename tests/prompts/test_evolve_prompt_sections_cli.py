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
    """Build a fake PromptBehavioralDataset with all required split data.

    holdout is intentionally LEFT EMPTY so we don't run holdout evaluation
    (which would invoke baseline_module(task_input=...) → ChainOfThought →
    real LM, AND would inflate set_active_section.call_count via the
    baseline-priming for-loop). For these CLI tests we only assert
    optimization-step shape; holdout regression is covered by the existing
    tests/prompts/test_evolve_prompt_sections.py::TestEvolve suite.
    """
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
        holdout=[],
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
        # Bypass real forward() during holdout eval — we only assert on
        # set_*_mode / GEPA.compile call shape, not on LM-driven scoring.
        # Without this, baseline_module(task_input=...) would invoke
        # ChainOfThought which requires a configured LM.
        import dspy as _dspy
        spy_module.return_value = _dspy.Prediction(output="mock output")

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
        """Default mode (no --mode flag) routes to joint: GEPA invoked with
        component_selector='all' at least once + set_joint_mode(True) called.

        Plan 17-03 update: In joint mode, A/B baseline also instantiates GEPA
        per-section (with component_selector='round_robin'). So
        `mock_gepa.call_args` reflects the LAST call (round_robin A/B), not
        the joint call. We must inspect ALL calls for a joint signature.
        """
        fake_sections = _make_fake_sections(3)
        result, mock_gepa, spy_module, _ = self._patched_run(
            ["--iterations", "2", "--hermes-repo", "/fake"],
            fake_sections=fake_sections,
        )

        assert result.exit_code == 0, (
            f"Expected exit 0, got {result.exit_code}. "
            f"Output: {result.output[:500]}"
        )
        assert mock_gepa.called, "dspy.GEPA was never instantiated in joint mode"
        # Plan 17-03: inspect all GEPA constructor calls. At least one must
        # carry component_selector='all' (the joint optimizer).
        joint_selectors = [
            c.kwargs.get("component_selector") for c in mock_gepa.call_args_list
        ]
        assert "all" in joint_selectors, (
            f"Joint mode must call GEPA at least once with "
            f"component_selector='all'; got {joint_selectors!r}"
        )
        # Plan 17-03: total compile calls = 1 (joint) + N (A/B per-section).
        # The joint mode itself still does exactly one compile.
        expected_compiles = 1 + len(fake_sections)
        assert mock_gepa.return_value.compile.call_count == expected_compiles, (
            f"Joint mode + A/B baseline expected {expected_compiles} compile "
            f"calls (1 joint + {len(fake_sections)} A/B), got "
            f"{mock_gepa.return_value.compile.call_count}"
        )
        # set_joint_mode(True) was called (proves we entered joint branch).
        # NOTE: set_joint_mode is called once on the main module (joint branch
        # via PromptModule patch returning spy_module). A/B baseline uses a
        # fresh PromptModule(original_sections) which is NOT the spy
        # (PromptModule is patched with return_value=spy_module — every call
        # returns the SAME spy, so spy_module.set_joint_mode.call_count would
        # actually grow if any AB construction also called it; but A/B path
        # uses set_active_section, never set_joint_mode).
        spy_module.set_joint_mode.assert_called_with(True)

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


class TestABBaseline:
    """Phase 17 — inline A/B baseline + soft gate + metrics.json schema tests.

    These tests verify that joint mode:
      (1) actually runs the round-robin baseline inline after holdout eval
      (2) writes 5 new metrics.json fields
          (mode/joint_score/rr_baseline_score/epsilon_pp/joint_vs_roundrobin_delta_pp)
      (3) writes roundrobin_baseline_*.{json,txt} sibling files
      (4) warns (yellow stdout) but does not exit when joint regresses past epsilon
      (5) round-robin --mode skips A/B and the extra files

    BLOCKER fixes applied (revision pass):
      B1: PromptBehavioralExample fixture uses real dataclass fields only —
          section_id/user_message/expected_behavior/difficulty (NO task_input,
          which is a dspy.Example attribute injected by to_dspy_examples()).
      B2: PromptModule class is patched at the module import site to return
          spy modules wrapping real instances — prevents the fresh
          PromptModule(original_sections) inside the A/B branch from
          instantiating a real dspy.ChainOfThought selector and firing real
          LM calls during holdout scoring. The spy's __call__ is overridden
          to return a deterministic dspy.Prediction, so metric.side_effect
          controls the score sequence.
    """

    def _ab_patched_run(self, argv, fake_sections, score_sequence, tmp_path):
        """Like TestJointPipeline._patched_run but with:
          - dataset.holdout populated so step-9 holdout eval runs
          - metric.side_effect = score_sequence (deterministic A/B scores)
          - output dir redirected to tmp_path via cwd patching
          - PromptModule patched to return spy modules wrapping real instances
            (BLOCKER-2 fix: prevents real LM calls in evolved/baseline/AB scoring)
        """
        import os
        import dspy
        from click.testing import CliRunner
        from evolution.prompts.evolve_prompt_sections import main
        from evolution.prompts.prompt_module import PromptModule
        from evolution.prompts.prompt_dataset import (
            PromptBehavioralExample,
            PromptBehavioralDataset,
        )

        # BLOCKER-1 fix: PromptBehavioralExample uses real dataclass fields.
        # task_input is NOT a field — it appears on dspy.Example after
        # to_dspy_examples() maps user_message -> task_input.
        examples = [
            PromptBehavioralExample(
                section_id=fake_sections[i % len(fake_sections)].section_id,
                user_message=f"task {i}",
                expected_behavior=f"behavior {i}",
                difficulty="easy",
            )
            for i in range(4)
        ]
        fake_ds = PromptBehavioralDataset(
            train=examples,
            val=examples,
            holdout=examples,
        )

        mock_constraint = MagicMock()
        mock_constraint._check_growth.return_value = MagicMock(
            passed=True, message="ok", constraint_name="growth"
        )
        mock_constraint._check_non_empty.return_value = MagicMock(
            passed=True, message="ok", constraint_name="non_empty"
        )

        mock_role = MagicMock()
        mock_role.check_all.return_value = []

        mock_metric_instance = MagicMock(side_effect=score_sequence)

        mock_builder_instance = MagicMock()
        mock_builder_instance.generate.return_value = fake_ds

        # BLOCKER-2 fix: PromptModule factory returns spy modules wrapping
        # a real PromptModule (so _section_ids / set_active_section /
        # set_joint_mode / get_evolved_sections / named_predictors all work),
        # but with __call__ overridden to return a Prediction without
        # invoking the real dspy.ChainOfThought selector (which would
        # require an LM and fire a network call).
        def _make_spy_module(*args, **kwargs):
            real = PromptModule(fake_sections)
            spy = MagicMock(wraps=real)
            # Expose real attributes (MagicMock-wraps proxies methods but
            # bare attribute reads come from the spy itself)
            spy._section_ids = real._section_ids
            spy._frozen_instructions = real._frozen_instructions
            spy.section_predictors = real.section_predictors
            # get_evolved_sections returns the fake sections as-is
            spy.get_evolved_sections = MagicMock(return_value=fake_sections)
            # named_predictors yields N entries (drives joint budget formula)
            spy.named_predictors = MagicMock(return_value=[
                (f"section_predictors['{sid}']", MagicMock())
                for sid in real._section_ids
            ])
            # __call__ → fake Prediction (avoids real selector LM call).
            # This is what makes metric.side_effect deterministic: every
            # module(...) returns the same Prediction shape and metric
            # consumes the next score in side_effect sequence.
            spy.return_value = dspy.Prediction(output="mocked output")
            # set_joint_mode / set_active_section delegate to the real
            # instance via wraps (MagicMock auto-proxies); no override.
            return spy

        runner = CliRunner()

        # Run in tmp_path so output/ folder is sandboxed
        orig_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

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
                side_effect=_make_spy_module,  # BLOCKER-2: factory per call
            ), patch(
                "evolution.prompts.evolve_prompt_sections.dspy.GEPA"
            ) as mock_gepa, patch(
                "evolution.prompts.evolve_prompt_sections.dspy.LM"
            ), patch(
                "evolution.prompts.evolve_prompt_sections.dspy.configure"
            ), patch(
                "evolution.prompts.evolve_prompt_sections.dspy.context",
                MagicMock(),
            ):
                # GEPA.compile returns the module unchanged
                mock_gepa.return_value.compile.side_effect = (
                    lambda mod, trainset, valset=None: mod
                )
                result = runner.invoke(main, argv, catch_exceptions=False)

            # Find output_dir created under tmp_path
            output_root = tmp_path / "output" / "prompts"
            run_dirs = (
                sorted(output_root.iterdir(), key=lambda p: p.stat().st_mtime)
                if output_root.exists()
                else []
            )
            latest = run_dirs[-1] if run_dirs else None

            return result, mock_gepa, latest
        finally:
            os.chdir(orig_cwd)

    def test_joint_mode_runs_inline_ab_baseline(self, tmp_path):
        """Joint mode: A/B baseline runs after holdout, metrics.json has 5 new fields,
        baseline副本文件 exist."""
        import json

        fake_sections = _make_fake_sections(3)
        # Score sequence: 4 holdout examples × (baseline call + evolved call)
        # interleaved (Step 9 loop calls baseline THEN evolved per example),
        # followed by 4 A/B baseline holdout calls (sequential).
        # We want joint_score=0.8, baseline_score=0.5, rr_baseline_score=0.75.
        # Total 12 calls: [0.5, 0.8] × 4 + [0.75] × 4
        scores = [0.5, 0.8] * 4 + [0.75] * 4

        result, mock_gepa, latest = self._ab_patched_run(
            ["--mode", "joint", "--iterations", "2", "--hermes-repo", "/fake"],
            fake_sections,
            scores,
            tmp_path,
        )

        assert result.exit_code == 0, f"Joint mode failed: {result.output[:500]}"
        assert latest is not None, "Output directory was not created"
        metrics_path = latest / "metrics.json"
        assert metrics_path.exists(), f"metrics.json missing in {latest}"
        metrics = json.loads(metrics_path.read_text())

        # D-OUT-02: 5 new fields (W3 revision adds joint_vs_roundrobin_delta_pp)
        assert metrics["mode"] == "joint"
        assert "joint_score" in metrics
        assert "roundrobin_baseline_score" in metrics
        assert metrics["epsilon_pp"] == 0.01
        assert "joint_vs_roundrobin_delta_pp" in metrics  # W3 new field
        assert metrics["joint_score"] == 0.8
        assert metrics["roundrobin_baseline_score"] == 0.75
        # Delta is positive when joint wins
        assert metrics["joint_vs_roundrobin_delta_pp"] == pytest.approx(5.0, abs=0.01)

        # D-OUT-01 shared-prefix baseline files
        assert (latest / "roundrobin_baseline_evolved_sections.json").exists(), (
            f"Missing baseline副本 in {latest}"
        )
        assert (latest / "roundrobin_baseline_diff.txt").exists()
        # Joint main artifacts also present
        assert (latest / "evolved_sections.json").exists()
        assert (latest / "diff.txt").exists()

        # GEPA called once for joint + N for A/B baseline per-section
        assert mock_gepa.return_value.compile.call_count == 1 + len(fake_sections), (
            f"Expected {1 + len(fake_sections)} compile calls (1 joint + "
            f"{len(fake_sections)} A/B), got {mock_gepa.return_value.compile.call_count}"
        )

    def test_soft_gate_warns_but_does_not_block(self, tmp_path):
        """When joint_score < rr_baseline - 0.01, stdout warns but exit==0 and
        evolved_sections.json still written."""
        import json

        fake_sections = _make_fake_sections(3)
        # Score sequence: 4 holdout × (baseline + evolved) interleaved
        # + 4 A/B holdout sequential. joint=0.50, rr_baseline=0.60 →
        # delta = 10pp > 1pp epsilon → warn.
        # joint_vs_roundrobin_delta_pp = (0.50 - 0.60) * 100 = -10.0 (negative = regression)
        scores = [0.4, 0.50] * 4 + [0.60] * 4

        result, mock_gepa, latest = self._ab_patched_run(
            ["--mode", "joint", "--iterations", "2", "--hermes-repo", "/fake"],
            fake_sections,
            scores,
            tmp_path,
        )

        # Soft-gate must NOT exit non-zero
        assert result.exit_code == 0, (
            f"Soft gate must not exit non-zero, got {result.exit_code}. "
            f"Output: {result.output[:500]}"
        )
        # Yellow warning text must be in stdout. Rich may wrap long lines at
        # terminal width, so check for both ends of the phrase as separate
        # tokens (the phrase itself contains a space that rich may split on).
        output_normalized = " ".join(result.output.split())
        assert "review before deploying" in output_normalized, (
            f"Soft-gate warning text missing. Stdout: {result.output[:800]}"
        )
        # evolved_sections.json still written (not blocked)
        assert latest is not None
        assert (latest / "evolved_sections.json").exists()
        assert (latest / "metrics.json").exists()
        metrics = json.loads((latest / "metrics.json").read_text())
        assert metrics["constraints_passed"] is True
        assert metrics["joint_score"] == 0.50
        assert metrics["roundrobin_baseline_score"] == 0.60
        # W3: delta is NEGATIVE on regression
        assert metrics["joint_vs_roundrobin_delta_pp"] == pytest.approx(-10.0, abs=0.01)

    def test_round_robin_mode_skips_ab_baseline_and_extra_files(self, tmp_path):
        """--mode round-robin: no A/B baseline, no extra files, metrics.json has
        only mode field (no joint_score/rr_score/epsilon_pp/joint_vs_rr_delta)."""
        import json

        fake_sections = _make_fake_sections(3)
        # 4 holdout × (baseline + evolved) interleaved = 8 metric calls
        # No A/B baseline in round-robin mode.
        scores = [0.5, 0.7] * 4

        result, mock_gepa, latest = self._ab_patched_run(
            ["--mode", "round-robin", "--iterations", "2", "--hermes-repo", "/fake"],
            fake_sections,
            scores,
            tmp_path,
        )

        assert result.exit_code == 0, f"RR mode failed: {result.output[:500]}"
        assert latest is not None

        metrics = json.loads((latest / "metrics.json").read_text())
        assert metrics["mode"] == "round-robin"
        # No joint-mode fields
        assert "joint_score" not in metrics
        assert "roundrobin_baseline_score" not in metrics
        assert "epsilon_pp" not in metrics
        assert "joint_vs_roundrobin_delta_pp" not in metrics  # W3 new field also absent

        # No baseline副本 files in round-robin mode
        assert not (latest / "roundrobin_baseline_evolved_sections.json").exists()
        assert not (latest / "roundrobin_baseline_diff.txt").exists()

        # GEPA called N times for per-section round-robin, no extra A/B calls
        assert mock_gepa.return_value.compile.call_count == len(fake_sections)
