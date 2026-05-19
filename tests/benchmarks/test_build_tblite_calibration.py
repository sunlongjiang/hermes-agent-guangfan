"""CliRunner unit tests for build_tblite_calibration.

Every external call mocked:
  - subprocess.run for git status / git rev-parse
  - huggingface_hub.HfApi (via patch of _hf_dataset_revision)
  - TBLiteRunner.run (via patch of the class so .run returns fake result)
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from evolution.benchmarks.tblite_runner import TBLiteRunResult


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_run_result(per_tier_passed: dict[str, list[bool]], runtime=1.0):
    per_task = []
    for tier, results in per_tier_passed.items():
        for i, passed in enumerate(results):
            per_task.append({
                "task_name": f"{tier}-{i}",
                "category": tier,
                "passed": passed,
                "infra_fail": False,
            })
    return TBLiteRunResult(
        per_task=per_task,
        subprocess_runtime_seconds=runtime,
        hang_count=0,
        cost_breakdown={"modal_compute_usd": 0.1},
        samples_jsonl_path=Path("/tmp/fake_samples.jsonl"),
        exit_code=0,
        status="ok",
        jsonl_skipped_lines=0,
        stderr_tail=[],
    )


@pytest.fixture
def fake_hermes(tmp_path):
    """Create a minimal fake hermes-agent dir with an empty git repo."""
    hermes = tmp_path / "hermes-agent"
    (hermes / "agent").mkdir(parents=True)
    (hermes / "agent" / "prompt_builder.py").write_text(
        'MEMORY_GUIDANCE = (\n    "baseline"\n)\n'
    )
    return hermes


@pytest.fixture
def fake_subset(tmp_path, monkeypatch):
    """Place datasets/prompts/tblite_stratified_subset.json in cwd."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "datasets" / "prompts").mkdir(parents=True)
    subset_path = tmp_path / "datasets" / "prompts" / "tblite_stratified_subset.json"
    # W-7 schema: task_filter is list of {name, tier} objects.
    subset = {
        "seed": 42,
        "per_tier_counts": {"easy": 2, "medium": 2, "hard": 2, "extreme": 2},
        "task_filter": [
            {"name": "t-easy-0", "tier": "easy"},
            {"name": "t-easy-1", "tier": "easy"},
            {"name": "t-medium-0", "tier": "medium"},
            {"name": "t-medium-1", "tier": "medium"},
            {"name": "t-hard-0", "tier": "hard"},
            {"name": "t-hard-1", "tier": "hard"},
            {"name": "t-extreme-0", "tier": "extreme"},
            {"name": "t-extreme-1", "tier": "extreme"},
        ],
        "source": "test",
        "generated_timestamp": "2026-05-19T00:00:00Z",
    }
    subset_path.write_text(json.dumps(subset))
    return subset_path


def _patches_for_happy_path(module, per_tier_passed=None):
    """Common patches for a successful calibration run."""
    per_tier_passed = per_tier_passed or {
        "easy":    [True, True],
        "medium":  [True, False],
        "hard":    [False, False],
        "extreme": [False, False],
    }
    ps = []
    ps.append(patch.object(module, "_check_hermes_clean"))
    ps.append(patch.object(module, "_git_head", return_value="commit_abc12345"))
    ps.append(patch.object(module, "_hf_dataset_revision", return_value="hf_rev_xyz"))
    mock_runner_cls = MagicMock()
    mock_runner_cls.return_value.run.return_value = _make_run_result(per_tier_passed)
    ps.append(patch.object(module, "TBLiteRunner", mock_runner_cls))
    return ps


# ── Tests ───────────────────────────────────────────────────────────────

class TestBuildTBLiteCalibration:

    def test_anchor_json_schema_complete(self, fake_hermes, fake_subset, tmp_path):
        from evolution.benchmarks import build_tblite_calibration as mod
        anchor_out = tmp_path / "anchor.json"
        runner = CliRunner()
        patches = _patches_for_happy_path(mod)
        for p in patches:
            p.start()
        try:
            result = runner.invoke(mod.main, [
                "--hermes-repo", str(fake_hermes),
                "--seed", "42",
                "--runs", "1",
                "--output-json", str(anchor_out),
                "--benchmark-max-cost", "1000.0",
            ])
        finally:
            for p in patches:
                p.stop()
        assert result.exit_code == 0, f"CLI failed: {result.output}"
        anchor = json.loads(anchor_out.read_text())
        for key in (
            "anchor_per_tier", "dataset_revision_hash",
            "hermes_agent_commit", "stratified_subset_seed",
            "tblite_estimated_cost_per_task_usd",
            "calibration_timestamp", "calibration_model",
            "tblite_runner_version",
        ):
            assert key in anchor, f"missing top-level key {key!r}"
        for tier in ("easy", "medium", "hard", "extreme"):
            assert tier in anchor["anchor_per_tier"], f"missing tier {tier}"
            for inner in ("mean", "stdev", "n"):
                assert inner in anchor["anchor_per_tier"][tier], \
                    f"missing {tier}.{inner}"

    def test_seed_is_persisted_from_subset(self, fake_hermes, fake_subset, tmp_path):
        """stratified_subset_seed comes from the subset JSON, not the --seed flag."""
        from evolution.benchmarks import build_tblite_calibration as mod
        # Mutate subset to seed=7.
        subset_data = json.loads(fake_subset.read_text())
        subset_data["seed"] = 7
        fake_subset.write_text(json.dumps(subset_data))
        anchor_out = tmp_path / "anchor.json"
        patches = _patches_for_happy_path(mod)
        for p in patches:
            p.start()
        try:
            result = CliRunner().invoke(mod.main, [
                "--hermes-repo", str(fake_hermes),
                "--seed", "999",  # SHOULD BE IGNORED — subset's seed wins
                "--runs", "1",
                "--output-json", str(anchor_out),
                "--benchmark-max-cost", "1000",
            ])
        finally:
            for p in patches:
                p.stop()
        assert result.exit_code == 0, result.output
        anchor = json.loads(anchor_out.read_text())
        assert anchor["stratified_subset_seed"] == 7, \
            f"subset seed not persisted: {anchor['stratified_subset_seed']}"

    def test_huggingface_fallback_on_api_error(self, fake_hermes, fake_subset, tmp_path):
        from evolution.benchmarks import build_tblite_calibration as mod
        anchor_out = tmp_path / "anchor.json"
        with patch.object(mod, "_check_hermes_clean"), \
             patch.object(mod, "_git_head", return_value="commit_x"), \
             patch.object(mod, "TBLiteRunner") as mock_runner_cls:
            mock_runner_cls.return_value.run.return_value = _make_run_result({
                "easy": [True], "medium": [True], "hard": [True], "extreme": [True],
            })
            # Force HfApi.dataset_info to raise.
            import sys
            fake_hf = MagicMock()
            fake_hf.HfApi.return_value.dataset_info.side_effect = RuntimeError("no network")
            sys.modules["huggingface_hub"] = fake_hf
            try:
                result = CliRunner().invoke(mod.main, [
                    "--hermes-repo", str(fake_hermes),
                    "--output-json", str(anchor_out),
                    "--runs", "1",
                    "--benchmark-max-cost", "1000",
                ])
            finally:
                sys.modules.pop("huggingface_hub", None)
        assert result.exit_code == 0, result.output
        anchor = json.loads(anchor_out.read_text())
        # Fallback string is 'unknown_v<runner version>'.
        assert anchor["dataset_revision_hash"].startswith("unknown_v"), \
            f"HF fallback not applied: {anchor['dataset_revision_hash']}"

    def test_git_dirty_check_blocks_calibration(self, fake_hermes, fake_subset, tmp_path):
        from evolution.benchmarks import build_tblite_calibration as mod
        anchor_out = tmp_path / "anchor.json"
        # _check_hermes_clean RAISES ClickException — simulate dirty tree.
        def raise_dirty(_):
            raise __import__("click").ClickException("uncommitted changes")
        with patch.object(mod, "_check_hermes_clean", side_effect=raise_dirty):
            result = CliRunner().invoke(mod.main, [
                "--hermes-repo", str(fake_hermes),
                "--output-json", str(anchor_out),
                "--runs", "1",
                "--benchmark-max-cost", "1000",
            ])
        assert result.exit_code != 0, "dirty git should block calibration"
        assert "uncommitted" in result.output.lower(), \
            f"missing dirty-tree message: {result.output}"
        assert not anchor_out.exists(), "anchor must NOT be written on dirty tree"

    def test_pre_flight_watermark_blocks_when_insufficient_budget(
        self, fake_hermes, fake_subset, tmp_path,
    ):
        """8 tasks × 3 runs × $0.4/task = $9.6; watermark = $28.8.

        With --benchmark-max-cost 5 -> watermark $28.8 > 5 -> abort.
        """
        from evolution.benchmarks import build_tblite_calibration as mod
        anchor_out = tmp_path / "anchor.json"
        patches = _patches_for_happy_path(mod)
        for p in patches:
            p.start()
        try:
            result = CliRunner().invoke(mod.main, [
                "--hermes-repo", str(fake_hermes),
                "--output-json", str(anchor_out),
                "--runs", "3",
                "--benchmark-max-cost", "5",
            ])
        finally:
            for p in patches:
                p.stop()
        assert result.exit_code != 0, "insufficient budget must block"
        assert "watermark" in result.output.lower() or \
               "budget" in result.output.lower(), \
               f"missing Watermark error message: {result.output}"
        assert not anchor_out.exists(), \
            "anchor must NOT be written when Watermark fails"

    def test_tblite_cost_per_task_measured_and_written(
        self, fake_hermes, fake_subset, tmp_path,
    ):
        """anchor['tblite_estimated_cost_per_task_usd'] = measured (tracker.spent / (n_tasks * runs)).

        Note: CostTracker's spent_usd depends on DSPy track_usage integration
        which is not invoked in the mocked subprocess path. The field MUST
        still be written; the value may be 0.0 (no LM calls in test) or
        inherited from the default. We assert presence + numeric type.
        """
        from evolution.benchmarks import build_tblite_calibration as mod
        anchor_out = tmp_path / "anchor.json"
        patches = _patches_for_happy_path(mod)
        for p in patches:
            p.start()
        try:
            result = CliRunner().invoke(mod.main, [
                "--hermes-repo", str(fake_hermes),
                "--output-json", str(anchor_out),
                "--runs", "1",
                "--benchmark-max-cost", "1000",
            ])
        finally:
            for p in patches:
                p.stop()
        assert result.exit_code == 0, result.output
        anchor = json.loads(anchor_out.read_text())
        assert "tblite_estimated_cost_per_task_usd" in anchor
        assert isinstance(anchor["tblite_estimated_cost_per_task_usd"], (int, float))

    def test_runs_aggregates_mean_stdev(self, fake_hermes, fake_subset, tmp_path):
        """3 runs with varied easy pass rates -> mean ≈ 0.833, stdev > 0."""
        from evolution.benchmarks import build_tblite_calibration as mod
        anchor_out = tmp_path / "anchor.json"
        mock_runner_cls = MagicMock()
        # Different easy pass rates per run: 1/2, 2/2, 2/2 -> [0.5, 1.0, 1.0].
        results = [
            _make_run_result({"easy": [True, False], "medium": [True, True],
                               "hard": [True, True], "extreme": [True, True]}),
            _make_run_result({"easy": [True, True], "medium": [True, True],
                               "hard": [True, True], "extreme": [True, True]}),
            _make_run_result({"easy": [True, True], "medium": [True, True],
                               "hard": [True, True], "extreme": [True, True]}),
        ]
        mock_runner_cls.return_value.run.side_effect = results
        with patch.object(mod, "_check_hermes_clean"), \
             patch.object(mod, "_git_head", return_value="commit_x"), \
             patch.object(mod, "_hf_dataset_revision", return_value="rev"), \
             patch.object(mod, "TBLiteRunner", mock_runner_cls):
            cli_result = CliRunner().invoke(mod.main, [
                "--hermes-repo", str(fake_hermes),
                "--output-json", str(anchor_out),
                "--runs", "3",
                "--benchmark-max-cost", "1000",
            ])
        assert cli_result.exit_code == 0, cli_result.output
        anchor = json.loads(anchor_out.read_text())
        easy = anchor["anchor_per_tier"]["easy"]
        assert abs(easy["mean"] - 0.8333) < 0.01, \
            f"easy mean wrong: {easy['mean']} expected ≈ 0.833"
        assert easy["stdev"] > 0, \
            f"easy stdev should be > 0 with varied scores: {easy['stdev']}"
        assert easy["n"] == 3
        assert len(easy["scores"]) == 3

    def test_allow_dirty_tree_bypasses_git_check(
        self, fake_hermes, fake_subset, tmp_path,
    ):
        """WR-07: --allow-dirty-tree (the new name) skips _check_hermes_clean."""
        from evolution.benchmarks import build_tblite_calibration as mod
        anchor_out = tmp_path / "anchor.json"
        check_clean_calls = MagicMock()
        with patch.object(mod, "_check_hermes_clean", check_clean_calls), \
             patch.object(mod, "_git_head", return_value="commit_x"), \
             patch.object(mod, "_hf_dataset_revision", return_value="rev"), \
             patch.object(mod, "TBLiteRunner") as mock_runner_cls:
            mock_runner_cls.return_value.run.return_value = _make_run_result({
                "easy": [True], "medium": [True], "hard": [True], "extreme": [True],
            })
            result = CliRunner().invoke(mod.main, [
                "--hermes-repo", str(fake_hermes),
                "--output-json", str(anchor_out),
                "--runs", "1",
                "--benchmark-max-cost", "1000",
                "--allow-dirty-tree",
            ])
        assert result.exit_code == 0, result.output
        assert not check_clean_calls.called, \
            "_check_hermes_clean must be skipped with --allow-dirty-tree"

    def test_accept_stale_anchor_bypasses_git_check(
        self, fake_hermes, fake_subset, tmp_path,
    ):
        """--accept-stale-anchor lets calibration run even on dirty tree.

        WR-07: kept as a deprecated alias for --allow-dirty-tree.
        """
        from evolution.benchmarks import build_tblite_calibration as mod
        anchor_out = tmp_path / "anchor.json"
        # If accept-stale-anchor works, _check_hermes_clean is NEVER called.
        check_clean_calls = MagicMock()
        with patch.object(mod, "_check_hermes_clean", check_clean_calls), \
             patch.object(mod, "_git_head", return_value="commit_x"), \
             patch.object(mod, "_hf_dataset_revision", return_value="rev"), \
             patch.object(mod, "TBLiteRunner") as mock_runner_cls:
            mock_runner_cls.return_value.run.return_value = _make_run_result({
                "easy": [True], "medium": [True], "hard": [True], "extreme": [True],
            })
            result = CliRunner().invoke(mod.main, [
                "--hermes-repo", str(fake_hermes),
                "--output-json", str(anchor_out),
                "--runs", "1",
                "--benchmark-max-cost", "1000",
                "--accept-stale-anchor",
            ])
        assert result.exit_code == 0, result.output
        assert not check_clean_calls.called, \
            "_check_hermes_clean must be skipped with --accept-stale-anchor"

    def test_zero_sample_tier_fails_loudly(self, fake_hermes, fake_subset, tmp_path):
        """WR-04 regression: a tier with 0 valid samples (mistyped key,
        all infra_fail, etc.) must raise ClickException rather than
        silently anchor at 0.0 — which would make the gate permanently
        accept that tier.
        """
        from evolution.benchmarks import build_tblite_calibration as mod
        anchor_out = tmp_path / "anchor.json"
        # Drop 'extreme' entirely from the run result; the other 3 tiers
        # still produce samples.
        empty_extreme = {
            "easy":    [True, True],
            "medium":  [True, False],
            "hard":    [False, True],
            # no 'extreme' -> 0 valid samples
        }
        patches = _patches_for_happy_path(mod, per_tier_passed=empty_extreme)
        for p in patches:
            p.start()
        try:
            result = CliRunner().invoke(mod.main, [
                "--hermes-repo", str(fake_hermes),
                "--seed", "42",
                "--runs", "1",
                "--output-json", str(anchor_out),
                "--benchmark-max-cost", "1000.0",
            ])
        finally:
            for p in patches:
                p.stop()
        # Should fail with the WR-04 actionable error.
        assert result.exit_code != 0, (
            f"empty tier should abort calibration: {result.output}"
        )
        assert "extreme" in result.output, (
            f"error must name the empty tier: {result.output}"
        )
        assert not anchor_out.exists(), (
            "anchor must NOT be written when a tier is empty"
        )
