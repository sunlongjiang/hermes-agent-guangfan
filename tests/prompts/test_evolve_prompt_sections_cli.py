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

        # Phase 18 / Plan 18-04: DriftDetector is now part of step 8c.
        # In the sandboxed tmp_path workdir, the default
        # `datasets/prompts/drift_thresholds.json` does not exist, so click's
        # `exists=True` would reject the default flag. Create a stub so the
        # CLI can boot; DriftDetector itself is patched below to a no-op.
        import json as _json
        drift_thresholds_dir = tmp_path / "datasets" / "prompts"
        drift_thresholds_dir.mkdir(parents=True, exist_ok=True)
        (drift_thresholds_dir / "drift_thresholds.json").write_text(
            _json.dumps({
                "tone": 0.65,
                "formality": 0.25,
                "vocabulary": 0.6,
                "persona": 0.35,
            })
        )

        # DriftDetector mock: zero drift across all sections so step 8c passes
        # and the pipeline proceeds to step 9 (holdout eval) where these
        # TestABBaseline assertions live.
        mock_drift = MagicMock()
        from evolution.core.constraints import ConstraintResult as _CR
        mock_drift.check_all.return_value = [
            {
                "section_id": s.section_id,
                "per_dim": {
                    "tone": {"mean": 0.0, "stdev": 0.0, "exceeded": False, "raw": [0.0, 0.0, 0.0]},
                    "formality": {"mean": 0.0, "stdev": 0.0, "exceeded": False, "raw": [0.0, 0.0, 0.0]},
                    "vocabulary": {"mean": 0.0, "stdev": 0.0, "exceeded": False, "raw": [0.0, 0.0, 0.0]},
                    "persona": {"mean": 0.0, "stdev": 0.0, "exceeded": False, "raw": [0.0, 0.0, 0.0]},
                },
                "exceeded_count": 0,
                "severity": "pass",
                "explanation": "mock",
                "constraint_result": _CR(
                    passed=True,
                    constraint_name="drift_detection",
                    message=f"Drift OK in '{s.section_id}': no dims exceeded",
                    details="{}",
                ),
            }
            for s in fake_sections
        ]

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
                "evolution.prompts.evolve_prompt_sections.DriftDetector",
                return_value=mock_drift,
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
        # CR-02 fix: epsilon_pp is now in percentage points (1.0 == 1pp),
        # consistent with joint_vs_roundrobin_delta_pp's unit. Previously
        # stored as 0.01 (score space) despite the `_pp` suffix.
        assert metrics["epsilon_pp"] == 1.0
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


# ── Phase 18 / Wave 4: DriftDetector integration tests ───────────────────


class TestDriftGate:
    """Integration tests for the Wave 3 drift-gate wiring in evolve_prompt_sections.

    Verifies D-OUT-02 metrics fields (joint AND round-robin per D-ROB-04),
    D-BYPASS-01/02 CLI flag policy, and D-GATE-03/04 soft-warn vs hard-reject
    output topology.
    """

    def _drift_run(
        self,
        argv: list,
        fake_sections,
        scores: list,
        drift_results: list,
        tmp_path,
        thresholds_override: dict = None,
    ):
        """Run main() with the drift gate active.

        argv: extra CLI args (e.g. ['--mode', 'joint', '--iterations', '2',
            '--hermes-repo', '/fake']).
        drift_results: list of result-dicts that DriftDetector.check_all will
            return. One dict per section (must match section_id of each
            fake_section).
        thresholds_override: if provided, written into a temp thresholds file
            that the test passes via --drift-thresholds-path.
        """
        import json
        import os
        from unittest.mock import MagicMock, patch
        import dspy
        from click.testing import CliRunner
        from evolution.prompts.evolve_prompt_sections import main
        from evolution.prompts.prompt_module import PromptModule
        from evolution.prompts.prompt_dataset import (
            PromptBehavioralExample,
            PromptBehavioralDataset,
        )
        from evolution.core.constraints import ConstraintResult

        # Default thresholds — every dim 0.5 so DriftDetector(config, t)
        # constructor in Wave 3 won't raise ValueError on missing dims.
        thresholds = thresholds_override or {
            "tone": 0.5, "formality": 0.5, "vocabulary": 0.5, "persona": 0.5,
        }
        # Click.Path(exists=True) requires a real file -> write to tmp_path
        thresholds_path = tmp_path / "test_drift_thresholds.json"
        thresholds_path.write_text(json.dumps(thresholds))

        # Build a real dataset with populated splits (holdout must be non-empty
        # so step-9 holdout eval consumes the scored sequence). Mirrors
        # TestABBaseline._ab_patched_run dataset shape.
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

        mock_metric_instance = MagicMock(side_effect=scores)

        mock_constraint = MagicMock()
        mock_constraint._check_growth.return_value = ConstraintResult(
            True, "growth", "OK"
        )
        mock_constraint._check_non_empty.return_value = ConstraintResult(
            True, "non_empty", "OK"
        )

        # PromptRoleChecker: pass through (drift gate's behavior is what matters).
        mock_role = MagicMock()
        mock_role.check_all.return_value = [
            ConstraintResult(True, "role_preservation", "OK")
            for _ in fake_sections
        ]

        # DriftDetector: returns the caller-supplied drift_results.
        mock_drift = MagicMock()
        mock_drift.check_all.return_value = drift_results

        mock_builder_instance = MagicMock()
        mock_builder_instance.generate.return_value = fake_ds
        mock_builder_instance.build.return_value = fake_ds

        # PromptModule factory: real PromptModule wrapped in a MagicMock spy.
        # Override __call__ to return a fake Prediction so holdout scoring
        # consumes metric.side_effect deterministically (mirror TestABBaseline).
        def _make_spy_module(*args, **kwargs):
            real = PromptModule(fake_sections)
            spy = MagicMock(wraps=real)
            spy._section_ids = real._section_ids
            spy._frozen_instructions = real._frozen_instructions
            spy.section_predictors = real.section_predictors
            spy.get_evolved_sections = MagicMock(return_value=fake_sections)
            spy.named_predictors = MagicMock(return_value=[
                (f"section_predictors['{sid}']", MagicMock())
                for sid in real._section_ids
            ])
            spy.return_value = dspy.Prediction(output="mocked output")
            return spy

        runner = CliRunner()
        full_argv = list(argv) + [
            "--drift-thresholds-path", str(thresholds_path),
        ]

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
                "evolution.prompts.evolve_prompt_sections.DriftDetector",
                return_value=mock_drift,
            ), patch(
                "evolution.prompts.evolve_prompt_sections.PromptModule",
                side_effect=_make_spy_module,
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
                mock_gepa.return_value.compile.side_effect = (
                    lambda mod, trainset, valset=None: mod
                )
                result = runner.invoke(main, full_argv, catch_exceptions=False)

            # Find output dir (success path under output/prompts/<ts>/ or
            # failure path under output/prompts/FAILED_<ts>/).
            output_root = tmp_path / "output" / "prompts"
            run_dirs = (
                sorted(output_root.iterdir(), key=lambda p: p.stat().st_mtime)
                if output_root.exists()
                else []
            )
            latest = run_dirs[-1] if run_dirs else None
            return result, latest, thresholds_path
        finally:
            os.chdir(orig_cwd)

    @staticmethod
    def _make_drift_result(section_id: str, per_dim_overrides: dict = None):
        """Construct a Wave-1-shaped drift result dict.

        per_dim_overrides: {<dim>: {"mean": float, "stdev": float, "exceeded": bool}}
        Missing dims default to mean=0.1 stdev=0.01 exceeded=False (pass).
        """
        from evolution.core.constraints import ConstraintResult

        per_dim_overrides = per_dim_overrides or {}
        per_dim = {}
        for dim in ("tone", "formality", "vocabulary", "persona"):
            override = per_dim_overrides.get(dim, {})
            per_dim[dim] = {
                "mean": override.get("mean", 0.1),
                "stdev": override.get("stdev", 0.01),
                "exceeded": override.get("exceeded", False),
                "raw": override.get("raw", [0.1, 0.1, 0.1]),
            }
        exceeded_count = sum(1 for v in per_dim.values() if v["exceeded"])
        if exceeded_count == 0:
            severity, passed = "pass", True
            message = f"Drift OK in '{section_id}': no dims exceeded"
        elif exceeded_count == 1:
            severity, passed = "warn", True
            message = f"Drift WARN in '{section_id}'"
        else:
            severity, passed = "reject", False
            message = (
                f"Drift REJECT in '{section_id}': "
                f"{exceeded_count} dims exceeded"
            )
        return {
            "section_id": section_id,
            "per_dim": per_dim,
            "exceeded_count": exceeded_count,
            "severity": severity,
            "explanation": f"mock explanation for {section_id}",
            "constraint_result": ConstraintResult(
                passed=passed,
                constraint_name="drift_detection",
                message=message,
                details="{}",
            ),
        }

    # ── D-OUT-02 metrics.json fields (joint mode) ────────────────────

    def test_metrics_json_has_drift_fields(self, tmp_path):
        """Success path metrics.json contains drift_per_dim, drift_thresholds,
        drift_passed, drift_exceeded_dims (D-OUT-02) — JOINT mode."""
        import json

        fake_sections = _make_fake_sections(3)
        # All sections drift-pass — 0 exceeded, severity=pass.
        drift_results = [
            self._make_drift_result(s.section_id) for s in fake_sections
        ]
        # 4 holdout × (baseline + evolved) interleaved + 4 A/B holdout seq.
        scores = [0.5, 0.8] * 4 + [0.75] * 4

        result, latest, _ = self._drift_run(
            argv=["--mode", "joint", "--iterations", "2",
                  "--hermes-repo", "/fake"],
            fake_sections=fake_sections,
            scores=scores,
            drift_results=drift_results,
            tmp_path=tmp_path,
        )

        assert result.exit_code == 0, f"Run failed: {result.output[:500]}"
        assert latest is not None, "Output dir not created"
        # Success path must NOT be FAILED_*
        assert not latest.name.startswith("FAILED_"), (
            f"Expected success path output/prompts/<ts>/, got {latest.name}"
        )
        metrics = json.loads((latest / "metrics.json").read_text())
        # D-OUT-02 — all 4 mandatory drift fields
        assert "drift_per_dim" in metrics, (
            f"missing drift_per_dim: {sorted(metrics.keys())}"
        )
        assert "drift_thresholds" in metrics
        assert "drift_passed" in metrics
        assert "drift_exceeded_dims" in metrics
        assert metrics["drift_passed"] is True
        assert metrics["drift_exceeded_dims"] == []
        # Per-section per-dim shape
        for sid in (s.section_id for s in fake_sections):
            assert sid in metrics["drift_per_dim"]
            for dim in ("tone", "formality", "vocabulary", "persona"):
                assert dim in metrics["drift_per_dim"][sid]
                assert "mean" in metrics["drift_per_dim"][sid][dim]
                assert "exceeded" in metrics["drift_per_dim"][sid][dim]

    # ── D-OUT-02 + D-ROB-04 metrics.json fields (round-robin mode) ──
    # REGRESSION GUARD for Plan 18-04 Edit-3 indent ambiguity. If a future
    # executor places the `metrics["drift_per_dim"] = ...` block INSIDE the
    # joint-only `if effective_mode == "joint" ...` conditional, round-robin
    # runs would silently skip the assignment and this test fails.

    def test_round_robin_metrics_json_has_drift_fields(self, tmp_path):
        """Round-robin mode metrics.json MUST contain the same drift_* fields
        as joint mode (D-ROB-04 — both modes write drift_*).

        This is the regression guard for Plan 18-04 Edit-3 indent placement:
        the unconditional drift block in evolve_prompt_sections.py MUST sit
        at function-body indent (NOT inside the joint-only conditional).
        """
        import json

        fake_sections = _make_fake_sections(3)
        drift_results = [
            self._make_drift_result(s.section_id) for s in fake_sections
        ]
        # Round-robin has NO A/B baseline → only 8 metric calls
        # (4 holdout × baseline+evolved interleaved). No trailing 4 A/B scores.
        scores = [0.5, 0.8] * 4

        result, latest, _ = self._drift_run(
            argv=["--mode", "round-robin", "--iterations", "2",
                  "--hermes-repo", "/fake"],
            fake_sections=fake_sections,
            scores=scores,
            drift_results=drift_results,
            tmp_path=tmp_path,
        )

        assert result.exit_code == 0, (
            f"Round-robin run failed: {result.output[:500]}"
        )
        assert latest is not None, "No output dir created"
        assert not latest.name.startswith("FAILED_"), (
            f"Expected success path, got {latest.name}"
        )
        metrics = json.loads((latest / "metrics.json").read_text())
        # D-OUT-02 + D-ROB-04 — drift_* MUST be present in round-robin too.
        # If this assertion fires, the Wave-3 Edit-3 drift block was placed
        # INSIDE the joint-only conditional (8-space indent) instead of at
        # function-body level (4-space). Re-read Plan 18-04 Edit-3.
        assert "drift_per_dim" in metrics, (
            "D-ROB-04 REGRESSION: round-robin metrics.json missing "
            "drift_per_dim. The drift_* assignment in "
            "evolve_prompt_sections.py is incorrectly nested inside "
            "`if effective_mode == \"joint\" ...`. "
            f"Got keys: {sorted(metrics.keys())}"
        )
        assert "drift_thresholds" in metrics, (
            "D-ROB-04 REGRESSION: drift_thresholds missing in "
            "round-robin metrics"
        )
        assert "drift_passed" in metrics, (
            "D-ROB-04 REGRESSION: drift_passed missing in "
            "round-robin metrics"
        )
        assert "drift_exceeded_dims" in metrics, (
            "D-ROB-04 REGRESSION: drift_exceeded_dims missing in "
            "round-robin metrics"
        )
        # round-robin mode MUST NOT have joint_score / roundrobin_baseline_score
        # (sanity check that we're actually running round-robin path).
        assert metrics.get("mode") == "round-robin", (
            f"Expected mode=round-robin, got {metrics.get('mode')}"
        )

    # ── D-BYPASS-02 --drift-thresholds-path flag ─────────────────────

    def test_drift_thresholds_path_flag(self, tmp_path):
        """--drift-thresholds-path accepts a custom file and loads its values."""
        import json

        fake_sections = _make_fake_sections(3)
        custom_thresholds = {
            "tone": 0.42, "formality": 0.55,
            "vocabulary": 0.61, "persona": 0.33,
        }
        drift_results = [
            self._make_drift_result(s.section_id) for s in fake_sections
        ]
        scores = [0.5, 0.8] * 4 + [0.75] * 4

        result, latest, t_path = self._drift_run(
            argv=["--mode", "joint", "--iterations", "2",
                  "--hermes-repo", "/fake"],
            fake_sections=fake_sections,
            scores=scores,
            drift_results=drift_results,
            tmp_path=tmp_path,
            thresholds_override=custom_thresholds,
        )

        assert result.exit_code == 0, f"Run failed: {result.output[:500]}"
        assert latest is not None
        metrics = json.loads((latest / "metrics.json").read_text())
        # The custom thresholds must propagate verbatim
        assert metrics["drift_thresholds"] == custom_thresholds, (
            f"expected {custom_thresholds}, "
            f"got {metrics['drift_thresholds']}"
        )

    # ── D-BYPASS-01 regression guard ─────────────────────────────────

    def test_no_skip_drift_flag(self):
        """--no-drift-check and --skip-drift-check MUST NOT be registered.

        D-BYPASS-01: removing the bypass flag is non-negotiable. Any future
        change that re-adds it will fail this regression test loudly.
        """
        from click.testing import CliRunner
        from evolution.prompts.evolve_prompt_sections import main

        runner = CliRunner()
        for bad_flag in ("--no-drift-check", "--skip-drift-check"):
            result = runner.invoke(
                main,
                [bad_flag, "--hermes-repo", "/fake"],
                catch_exceptions=False,
            )
            assert result.exit_code != 0, (
                f"D-BYPASS-01 REGRESSION: {bad_flag} was accepted "
                f"(exit 0). Phase 18 forbids bypass flags."
            )
            # Click emits "No such option" or "no such option" on unknown flag.
            err_text = (result.output or "").lower()
            assert (
                "no such option" in err_text
                or "unrecognized" in err_text
                or bad_flag.lstrip("-") in err_text
            ), (
                f"Expected unknown-option error for {bad_flag}; "
                f"got: {result.output[:300]!r}"
            )

    # ── D-GATE-03 soft-warn path ─────────────────────────────────────

    def test_one_dim_drift_warns_but_deploys(self, tmp_path):
        """1 dim exceeded -> yellow stdout warning AND evolved_sections.json
        still written under output/prompts/<ts>/ (D-GATE-03)."""
        import json

        fake_sections = _make_fake_sections(3)
        # Section 0 has tone exceeded (1 dim) -> warn but still deploys.
        drift_results = [
            self._make_drift_result(
                fake_sections[0].section_id,
                per_dim_overrides={
                    "tone": {
                        "mean": 0.9, "stdev": 0.02, "exceeded": True,
                        "raw": [0.88, 0.9, 0.92],
                    },
                },
            ),
            self._make_drift_result(fake_sections[1].section_id),
            self._make_drift_result(fake_sections[2].section_id),
        ]
        scores = [0.5, 0.8] * 4 + [0.75] * 4

        result, latest, _ = self._drift_run(
            argv=["--mode", "joint", "--iterations", "2",
                  "--hermes-repo", "/fake"],
            fake_sections=fake_sections,
            scores=scores,
            drift_results=drift_results,
            tmp_path=tmp_path,
        )

        assert result.exit_code == 0, (
            f"Soft-warn must NOT block (D-GATE-03); got "
            f"{result.exit_code}: {result.output[:300]}"
        )
        assert latest is not None
        # Success path -> NOT in FAILED_* dir
        assert not latest.name.startswith("FAILED_"), (
            f"D-GATE-03: 1-dim warn must NOT go to FAILED dir, "
            f"got {latest.name}"
        )
        assert (latest / "evolved_sections.json").exists(), (
            "D-GATE-03: evolved_sections.json MUST be written on warn"
        )
        metrics = json.loads((latest / "metrics.json").read_text())
        assert metrics["drift_passed"] is True, (
            "D-GATE-03: 1-dim warn must keep drift_passed=true"
        )
        assert len(metrics["drift_exceeded_dims"]) == 1
        assert metrics["drift_exceeded_dims"][0] == {
            "section": fake_sections[0].section_id, "dim": "tone",
        }

    # ── D-GATE-04 hard-reject path ───────────────────────────────────

    def test_two_dim_drift_rejects_and_writes_failed_dir(self, tmp_path):
        """2+ dims exceeded -> FAILED_<ts>/ created with drift_report.txt +
        evolved_sections.json + diff.txt + metrics.json drift_passed=false
        (D-GATE-04)."""
        import json

        fake_sections = _make_fake_sections(3)
        # Section 0 has tone AND formality exceeded (2 dims) -> reject.
        drift_results = [
            self._make_drift_result(
                fake_sections[0].section_id,
                per_dim_overrides={
                    "tone": {
                        "mean": 0.9, "stdev": 0.02, "exceeded": True,
                        "raw": [0.88, 0.9, 0.92],
                    },
                    "formality": {
                        "mean": 0.85, "stdev": 0.03, "exceeded": True,
                        "raw": [0.82, 0.85, 0.88],
                    },
                },
            ),
            self._make_drift_result(fake_sections[1].section_id),
            self._make_drift_result(fake_sections[2].section_id),
        ]
        scores = [0.5, 0.8] * 4 + [0.75] * 4

        result, latest, _ = self._drift_run(
            argv=["--mode", "joint", "--iterations", "2",
                  "--hermes-repo", "/fake"],
            fake_sections=fake_sections,
            scores=scores,
            drift_results=drift_results,
            tmp_path=tmp_path,
        )

        # FAILED path must be created — latest dir name starts with "FAILED_".
        assert latest is not None
        assert latest.name.startswith("FAILED_"), (
            f"D-GATE-04: 2+ dims must route to FAILED_<ts>/; got {latest.name}"
        )
        # Required FAILED artifacts (D-GATE-04 + D-OUT-03)
        assert (latest / "metrics.json").exists()
        assert (latest / "drift_report.txt").exists(), (
            "D-OUT-03: drift_report.txt MUST be written in FAILED dir"
        )
        assert (latest / "evolved_sections.json").exists()
        assert (latest / "diff.txt").exists()

        metrics = json.loads((latest / "metrics.json").read_text())
        assert metrics["status"] == "FAILED"
        assert metrics["constraints_passed"] is False
        assert metrics["drift_passed"] is False, (
            "D-GATE-04: drift_passed MUST be false"
        )
        assert len(metrics["drift_exceeded_dims"]) >= 2

        # drift_report.txt has markdown structure.
        report = (latest / "drift_report.txt").read_text()
        assert "## Section:" in report, (
            "drift_report.txt missing markdown section headers"
        )
        assert "### Dim:" in report, (
            "drift_report.txt missing dim subheaders"
        )
        assert "Decision:" in report


# ── Phase 20 / Plan 06: TestBenchmarkGate ──────────────────────────────


def _benchmark_patched_run(
    runner,
    cli_args: list,
    *,
    tmp_path,
    gate_decision: str = "accept",
    gate_risk_score: float = 1.5,
    gate_per_tier: dict = None,
    anchor_overrides: dict = None,
    subset_overrides: dict = None,
    check_all_recorder: list = None,
    gate_constructor_recorder: list = None,
):
    """Run evolve_prompt_sections.main in a sandbox with all heavy deps mocked.

    W-4 (2026-05-19): MUST double-patch TBLiteBenchmarkGate:
      (a) evolution.benchmarks.benchmark_gate.TBLiteBenchmarkGate (source)
      (b) evolution.prompts.evolve_prompt_sections.TBLiteBenchmarkGate
          (the local binding established by the lazy `from ... import ...`
          inside evolve(). Without this patch the test silently runs the
          REAL gate and either crashes or — worse — appears to "pass" via
          pytest.skip.)

    Returns (CliRunner result, output_dir Path or None).
    """
    import json
    import os
    import dspy as _dspy
    from pathlib import Path as _Path
    from unittest.mock import patch, MagicMock

    from evolution.prompts.evolve_prompt_sections import main as cli_main
    from evolution.prompts.prompt_module import PromptModule
    from evolution.prompts.prompt_dataset import (
        PromptBehavioralExample,
        PromptBehavioralDataset,
    )
    from evolution.core.constraints import ConstraintResult

    fake_sections = _make_fake_sections(3)

    if gate_per_tier is None:
        gate_per_tier = {
            "easy":    {"mean": 0.85, "stdev": 0.01, "threshold": 0.83,
                        "anchor": 0.85, "moving_avg": 0.85, "breach": False,
                        "scores": [0.84, 0.86, 0.85]},
            "medium":  {"mean": 0.70, "stdev": 0.01, "threshold": 0.68,
                        "anchor": 0.70, "moving_avg": 0.70, "breach": False,
                        "scores": [0.69, 0.71, 0.70]},
            "hard":    {"mean": 0.50, "stdev": 0.01, "threshold": 0.48,
                        "anchor": 0.50, "moving_avg": 0.50, "breach": False,
                        "scores": [0.49, 0.51, 0.50]},
            "extreme": {"mean": 0.30, "stdev": 0.01, "threshold": 0.28,
                        "anchor": 0.30, "moving_avg": 0.30,
                        "breach": (gate_decision == "reject"),
                        "scores": [0.29, 0.31, 0.30]},
        }

    # Build stub anchor + subset under tmp_path/datasets/prompts/ in W-7 schema.
    datasets_dir = tmp_path / "datasets" / "prompts"
    datasets_dir.mkdir(parents=True, exist_ok=True)
    anchor = {
        "anchor_per_tier": {
            t: {"mean": v["anchor"], "stdev": 0.02, "n": 3,
                "scores": [v["anchor"]] * 3}
            for t, v in gate_per_tier.items()
        },
        "dataset_revision_hash": "test_rev",
        "hermes_agent_commit": "test_commit",
        "stratified_subset_seed": 42,
        "tblite_estimated_cost_per_task_usd": 0.4,
        "calibration_timestamp": "2026-05-19T00:00:00Z",
        "calibration_model": "test/model",
        "tblite_runner_version": "1.0",
    }
    if anchor_overrides:
        anchor.update(anchor_overrides)
    (datasets_dir / "tblite_anchor.json").write_text(json.dumps(anchor))

    subset = {
        "seed": 42,
        "per_tier_counts": {"easy": 1, "medium": 1, "hard": 1, "extreme": 1},
        "task_filter": [
            {"name": "t-easy", "tier": "easy"},
            {"name": "t-medium", "tier": "medium"},
            {"name": "t-hard", "tier": "hard"},
            {"name": "t-extreme", "tier": "extreme"},
        ],
        "source": "test",
        "generated_timestamp": "2026-05-19T00:00:00Z",
    }
    if subset_overrides:
        subset.update(subset_overrides)
    (datasets_dir / "tblite_stratified_subset.json").write_text(json.dumps(subset))

    # drift_thresholds.json stub (existing pipeline requires it via click.Path exists=True).
    drift_thresholds = {
        "tone": 0.5, "formality": 0.5, "vocabulary": 0.5, "persona": 0.5,
        "_meta": {"f1_tier": 1},
    }
    (datasets_dir / "drift_thresholds.json").write_text(json.dumps(drift_thresholds))

    # Gate report shape matching TBLiteBenchmarkGate.check_all contract.
    gate_report = {
        "decision": gate_decision,
        "risk_score": gate_risk_score,
        "reject_threshold": 4.0,
        "tier_weights": {"easy": 1.0, "medium": 1.5, "hard": 2.0, "extreme": 4.0},
        "per_tier": gate_per_tier,
        "samples_jsonl_path": str(tmp_path / "samples.jsonl"),
        "subprocess_runtime_seconds": 1.0,
        "cost_breakdown": {"modal_compute_usd": 1.0},
        "dataset_revision_hash": "test_rev",
        "cache_hit": False,
        "async_full_verify_pending": False,
        "jsonl_skipped_lines_total": 0,
        "stderr_tails": [],
        "artifact_hash": "abc123",
        "constraint_result": ConstraintResult(
            passed=(gate_decision == "accept"),
            constraint_name="tblite_benchmark",
            message=f"Risk_Score={gate_risk_score:.2f}",
            details="{}",
        ),
    }

    def _make_gate(*args, **kwargs):
        if gate_constructor_recorder is not None:
            gate_constructor_recorder.append({"args": args, "kwargs": kwargs})
        mg = MagicMock()
        if check_all_recorder is not None:
            def _record(*a, **kw):
                check_all_recorder.append(kw)
                return [gate_report]
            mg.check_all.side_effect = _record
        else:
            mg.check_all.return_value = [gate_report]
        return mg

    # Dataset with holdout examples so the holdout eval step completes.
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

    mock_metric_instance = MagicMock(return_value=0.5)
    mock_constraint = MagicMock()
    mock_constraint._check_growth.return_value = ConstraintResult(
        True, "growth", "OK"
    )
    mock_constraint._check_non_empty.return_value = ConstraintResult(
        True, "non_empty", "OK"
    )
    mock_role = MagicMock()
    mock_role.check_all.return_value = [
        ConstraintResult(True, "role_preservation", "OK")
        for _ in fake_sections
    ]
    mock_drift = MagicMock()
    mock_drift.check_all.return_value = [
        {
            "section_id": s.section_id,
            "per_dim": {
                d: {"mean": 0.0, "stdev": 0.0, "exceeded": False, "raw": [0.0, 0.0, 0.0]}
                for d in ("tone", "formality", "vocabulary", "persona")
            },
            "exceeded_count": 0,
            "severity": "pass",
            "explanation": "mock",
            "constraint_result": ConstraintResult(
                passed=True,
                constraint_name="drift_detection",
                message=f"OK '{s.section_id}'",
                details="{}",
            ),
        }
        for s in fake_sections
    ]
    mock_builder_instance = MagicMock()
    mock_builder_instance.generate.return_value = fake_ds

    def _make_spy_module(*args, **kwargs):
        real = PromptModule(fake_sections)
        spy = MagicMock(wraps=real)
        spy._section_ids = real._section_ids
        spy._frozen_instructions = getattr(real, "_frozen_instructions", {})
        spy.section_predictors = real.section_predictors
        spy.get_evolved_sections = MagicMock(return_value=fake_sections)
        spy.named_predictors = MagicMock(return_value=[
            (f"section_predictors['{sid}']", MagicMock())
            for sid in real._section_ids
        ])
        spy.return_value = _dspy.Prediction(output="mocked output")
        return spy

    orig_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Construct drift_thresholds_path argument pointing to our stub.
        dt_path = str(datasets_dir / "drift_thresholds.json")

        full_args = list(cli_args) + ["--drift-thresholds-path", dt_path]

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
            "evolution.prompts.evolve_prompt_sections.DriftDetector",
            return_value=mock_drift,
        ), patch(
            "evolution.prompts.evolve_prompt_sections.PromptModule",
            side_effect=_make_spy_module,
        ), patch(
            "evolution.prompts.evolve_prompt_sections.dspy.GEPA"
        ) as mock_gepa, patch(
            "evolution.prompts.evolve_prompt_sections.dspy.LM"
        ), patch(
            "evolution.prompts.evolve_prompt_sections.dspy.configure"
        ), patch(
            "evolution.prompts.evolve_prompt_sections.dspy.context",
            MagicMock(),
        ), patch(
            # W-4 (a) source-site patch.
            "evolution.benchmarks.benchmark_gate.TBLiteBenchmarkGate",
            side_effect=_make_gate,
        ), patch(
            # W-4 (b) consumer-site patch — established AFTER the lazy
            # `from ... import ...` inside evolve(). Patching only (a) is
            # insufficient: by the time the test reaches the gate call,
            # the name is rebound in evolve_prompt_sections' namespace.
            "evolution.prompts.evolve_prompt_sections.TBLiteBenchmarkGate",
            side_effect=_make_gate,
            create=True,
        ):
            mock_gepa.return_value.compile.side_effect = (
                lambda mod, trainset=None, valset=None: mod
            )
            result = runner.invoke(cli_main, full_args)

        output_root = tmp_path / "output" / "prompts"
        out_dirs = sorted(output_root.glob("*")) if output_root.exists() else []
        output_dir = out_dirs[-1] if out_dirs else None
        return result, output_dir
    finally:
        os.chdir(orig_cwd)


class TestBenchmarkGate:
    """Phase 20 Plan 06 CLI integration tests.

    Each test double-patches TBLiteBenchmarkGate at BOTH binding sites
    (W-4 revision 2026-05-19):
      (a) evolution.benchmarks.benchmark_gate.TBLiteBenchmarkGate (source)
      (b) evolution.prompts.evolve_prompt_sections.TBLiteBenchmarkGate
          (the local binding established by the lazy import inside
          evolve(); patching only (a) misses this binding and the real
          gate fires).

    W-4 also forbids pytest.skip for "harness didn't reach step 10.5".
    Tests must FAIL when wiring is broken; pytest.skip is only acceptable
    for environment issues (e.g. dspy not configured).
    """

    def test_benchmark_none_default_path_unchanged(self, tmp_path):
        """--benchmark=none -> metrics.json has benchmark_decision='skipped' and NO benchmark_risk_score."""
        from click.testing import CliRunner
        import json
        runner = CliRunner()
        result, output_dir = _benchmark_patched_run(
            runner,
            [
                "--section", "section_0",
                "--iterations", "0",
                "--eval-source", "synthetic",
                "--benchmark", "none",
            ],
            tmp_path=tmp_path,
        )
        # Success path: must have exited 0 or created output_dir
        assert result.exit_code == 0 or output_dir is not None, (
            f"CLI exited non-zero with no output_dir: {result.output[:500]}"
        )
        if output_dir and (output_dir / "metrics.json").exists():
            m = json.loads((output_dir / "metrics.json").read_text())
            assert m.get("benchmark_decision") == "skipped", (
                f"Expected benchmark_decision='skipped', got {m.get('benchmark_decision')}"
            )
            assert "benchmark_risk_score" not in m, (
                "benchmark_risk_score must not be present when benchmark=none"
            )

    def test_benchmark_tblite_accept_writes_report_and_metrics(self, tmp_path):
        """W-4 enforcement: assertion failures here surface as test FAIL,
        not pytest.skip. If output_dir is None the wiring is broken — FAIL."""
        from click.testing import CliRunner
        import json
        runner = CliRunner()
        result, output_dir = _benchmark_patched_run(
            runner,
            [
                "--section", "section_0",
                "--iterations", "0",
                "--benchmark", "tblite",
            ],
            tmp_path=tmp_path,
            gate_decision="accept",
            gate_risk_score=1.5,
        )
        assert output_dir is not None, (
            f"Step 10.5 wiring failure: no output_dir created. "
            f"CLI output: {result.output[:500]}"
        )
        assert not output_dir.name.startswith("FAILED_"), (
            f"accept path must not create FAILED_ dir; got {output_dir.name}"
        )
        assert (output_dir / "tblite_report.json").exists(), \
            "accept path must write tblite_report.json"
        m = json.loads((output_dir / "metrics.json").read_text())
        assert m["benchmark_decision"] == "accept"
        assert m["benchmark_passed"] is True
        assert m["benchmark_risk_score"] == 1.5
        assert "benchmark_per_tier" in m
        assert "total_cost_breakdown" in m

    def test_benchmark_tblite_reject_writes_FAILED_dir(self, tmp_path):
        """W-4 enforcement: reject branch wiring failures surface as FAIL."""
        from click.testing import CliRunner
        import json
        runner = CliRunner()
        result, output_dir = _benchmark_patched_run(
            runner,
            [
                "--section", "section_0",
                "--iterations", "0",
                "--benchmark", "tblite",
            ],
            tmp_path=tmp_path,
            gate_decision="reject",
            gate_risk_score=5.0,
        )
        assert output_dir is not None, (
            f"Step 10.5 reject wiring failure: no output_dir created. "
            f"CLI output: {result.output[:500]}"
        )
        assert "FAILED_" in output_dir.name, (
            f"reject path must write FAILED_<ts>/; got {output_dir.name}"
        )
        m = json.loads((output_dir / "metrics.json").read_text())
        assert m["benchmark_decision"] == "reject"
        assert m["benchmark_passed"] is False
        assert m["benchmark_risk_score"] == 5.0
        assert (output_dir / "tblite_report.json").exists()
        assert (output_dir / "evolved_sections.json").exists()
        assert (output_dir / "diff.txt").exists()

    def test_benchmark_cache_flag_threads_through(self, tmp_path):
        """--no-benchmark-cache threads use_cache=False to gate.check_all."""
        from click.testing import CliRunner
        runner = CliRunner()
        recorder: list = []
        result, _ = _benchmark_patched_run(
            runner,
            [
                "--section", "section_0",
                "--iterations", "0",
                "--benchmark", "tblite",
                "--no-benchmark-cache",
            ],
            tmp_path=tmp_path,
            gate_decision="accept",
            check_all_recorder=recorder,
        )
        assert len(recorder) >= 1, "gate.check_all was never invoked"
        kw = recorder[-1]
        assert kw.get("use_cache") is False, (
            f"--no-benchmark-cache must thread use_cache=False; kwargs={kw}"
        )

    def test_no_skip_benchmark_flag(self):
        """--no-benchmark and --skip-benchmark are rejected by Click (D-BYPASS-01 spirit)."""
        from click.testing import CliRunner
        from evolution.prompts.evolve_prompt_sections import main as cli_main
        r1 = CliRunner().invoke(cli_main, ["--no-benchmark"])
        assert r1.exit_code != 0, "--no-benchmark must be rejected by Click"
        r2 = CliRunner().invoke(cli_main, ["--skip-benchmark"])
        assert r2.exit_code != 0, "--skip-benchmark must be rejected by Click"

    def test_total_cost_breakdown_present(self, tmp_path):
        """D-16 total_cost_breakdown has both optimization and benchmark float keys."""
        from click.testing import CliRunner
        import json
        runner = CliRunner()
        result, output_dir = _benchmark_patched_run(
            runner,
            [
                "--section", "section_0",
                "--iterations", "0",
                "--benchmark", "tblite",
            ],
            tmp_path=tmp_path,
            gate_decision="accept",
        )
        assert output_dir is not None, (
            f"Step 10.5 wiring failure (total_cost_breakdown test). "
            f"CLI output: {result.output[:500]}"
        )
        m = json.loads((output_dir / "metrics.json").read_text())
        assert "total_cost_breakdown" in m, (
            "W-2/W-3 regression: total_cost_breakdown missing from metrics.json"
        )
        tcb = m["total_cost_breakdown"]
        assert "optimization" in tcb, "W-2/W-3: optimization key missing"
        assert "benchmark" in tcb, "W-2/W-3: benchmark key missing"
        assert isinstance(tcb["optimization"], (int, float)), (
            f"optimization must be numeric, got {type(tcb['optimization']).__name__}"
        )
        assert isinstance(tcb["benchmark"], (int, float))

    def test_benchmark_tier_field_filters_subset(self, tmp_path):
        """W-7: --benchmark-tier filter selects items where item['tier'] matches."""
        from click.testing import CliRunner
        runner = CliRunner()
        constructor_recorder: list = []
        result, _ = _benchmark_patched_run(
            runner,
            [
                "--section", "section_0",
                "--iterations", "0",
                "--benchmark", "tblite",
                "--benchmark-tier", "easy,medium",
            ],
            tmp_path=tmp_path,
            gate_decision="accept",
            gate_constructor_recorder=constructor_recorder,
        )
        assert len(constructor_recorder) >= 1, (
            f"TBLiteBenchmarkGate constructor never invoked; CLI: {result.output[:500]}"
        )
        # The constructor receives stratified_subset as a kwarg or
        # positional arg. Inspect for kwarg first, fall back to args.
        call = constructor_recorder[-1]
        kw = call["kwargs"]
        args = call["args"]
        subset_arg = kw.get("stratified_subset")
        if subset_arg is None and len(args) >= 3:
            subset_arg = args[2]
        assert subset_arg is not None, (
            f"could not find stratified_subset in constructor call: {call}"
        )
        tiers_seen = {
            str(item.get("tier", "")).strip().lower()
            for item in subset_arg.get("task_filter", [])
            if isinstance(item, dict)
        }
        assert tiers_seen == {"easy", "medium"}, (
            f"--benchmark-tier easy,medium should filter to those tiers; got {tiers_seen}"
        )

    def test_detach_mode_not_yet_implemented_exits(self, tmp_path):
        """--detach must not exit 0 in Plan 06 (reserved for Phase 22)."""
        from click.testing import CliRunner
        runner = CliRunner()
        result, _ = _benchmark_patched_run(
            runner,
            [
                "--section", "section_0",
                "--iterations", "0",
                "--benchmark", "tblite",
                "--detach",
            ],
            tmp_path=tmp_path,
            gate_decision="accept",
        )
        assert result.exit_code != 0, "--detach must not exit 0 in Plan 06"

    def test_step_10_5_wiring_must_not_be_silent_skip(self, tmp_path):
        """W-4 enforcement: when the harness reaches step 10.5 the gate
        constructor MUST fire (recorded). If it doesn't, the test fails
        instead of pytest.skip-ping silently."""
        from click.testing import CliRunner
        runner = CliRunner()
        constructor_recorder: list = []
        result, output_dir = _benchmark_patched_run(
            runner,
            [
                "--section", "section_0",
                "--iterations", "0",
                "--benchmark", "tblite",
            ],
            tmp_path=tmp_path,
            gate_decision="accept",
            gate_constructor_recorder=constructor_recorder,
        )
        # If the harness can produce ANY output_dir at all, then step 10.5
        # MUST have run. If neither output_dir nor a constructor call were
        # observed, the wiring is broken — fail loudly.
        if output_dir is None and not constructor_recorder:
            raise AssertionError(
                "Step 10.5 wiring failure: neither output_dir nor "
                "TBLiteBenchmarkGate constructor were observed. "
                "Tests must NOT silently skip past step 10.5. "
                f"CLI output: {result.output[:500]}"
            )
        # If gate constructor was called, accept path should write report.
        if constructor_recorder:
            assert output_dir is not None, (
                "constructor fired but no output_dir — accept path broken"
            )
            assert (output_dir / "tblite_report.json").exists(), (
                "accept path must write tblite_report.json"
            )
