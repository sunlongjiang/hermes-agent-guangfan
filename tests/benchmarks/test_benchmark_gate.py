"""Unit tests for evolution/benchmarks/benchmark_gate.py.

All subprocess calls are mocked — both:
  (a) the git status / git rev-parse calls inside _check_overlay_sanity
      and _check_anchor_existence (patch
      evolution.benchmarks.benchmark_gate.subprocess.run)
  (b) the TBLiteRunner.run subprocess wrapper (patch.object on the
      gate.runner attribute)
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from evolution.core.config import EvolutionConfig


# ── Helpers ───────────────────────────────────────────────────────────────────

class _FakeSection:
    def __init__(self, section_id, text="orig", line_range=(1, 1),
                 source_path=Path("/tmp/pb.py")):
        self.section_id = section_id
        self.text = text
        self.line_range = line_range
        self.source_path = source_path


def _make_anchor(easy=0.85, medium=0.70, hard=0.50, extreme=0.30, stdev=0.02,
                 hermes_commit="def456", revision_hash="abc123"):
    return {
        "anchor_per_tier": {
            "easy":    {"mean": easy,    "stdev": stdev, "n": 3, "scores": [easy]*3},
            "medium":  {"mean": medium,  "stdev": stdev, "n": 3, "scores": [medium]*3},
            "hard":    {"mean": hard,    "stdev": stdev, "n": 3, "scores": [hard]*3},
            "extreme": {"mean": extreme, "stdev": stdev, "n": 3, "scores": [extreme]*3},
        },
        "dataset_revision_hash": revision_hash,
        "hermes_agent_commit": hermes_commit,
        "stratified_subset_seed": 42,
        "tblite_estimated_cost_per_task_usd": 0.4,
        "calibration_timestamp": "2026-05-19T00:00:00Z",
        "calibration_model": "test/model",
        "tblite_runner_version": "1.0",
    }


def _make_subset(tasks=None):
    return {
        "seed": 42,
        "per_tier_counts": {"easy": 1, "medium": 1, "hard": 1, "extreme": 1},
        "task_filter": tasks or ["t-easy", "t-medium", "t-hard", "t-extreme"],
        "source": "NousResearch/openthoughts-tblite",
        "generated_timestamp": "2026-05-19T00:00:00Z",
    }


def _make_config(hermes_path: Path):
    config = EvolutionConfig.__new__(EvolutionConfig)
    config.hermes_agent_path = hermes_path
    config.benchmark_max_cost_usd = 50.0
    config.tblite_estimated_cost_per_task_usd = 0.4
    config.benchmark_runs = 3
    config.benchmark_heartbeat_seconds = 60
    return config


def _make_gate(tmp_path, *, anchor=None, subset=None, moving_avg_history=None,
               reject_threshold=4.0, runs=3):
    from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate
    hermes = tmp_path / "hermes-agent"
    (hermes / "agent").mkdir(parents=True, exist_ok=True)
    (hermes / "agent" / "prompt_builder.py").write_text(
        "MEMORY_GUIDANCE = (\n    \"baseline\"\n)\n"
    )
    config = _make_config(hermes)
    return TBLiteBenchmarkGate(
        config,
        anchor=anchor or _make_anchor(),
        stratified_subset=subset or _make_subset(),
        moving_avg_history=moving_avg_history,
        reject_threshold=reject_threshold,
        runs=runs,
    )


def _fake_run_result(per_tier_passed: dict, *, runtime=1.0, status="ok"):
    """Build a fake TBLiteRunResult from {tier: [True/False, ...]}.

    Uses a dataclass-like object to avoid depending on tblite_runner being
    importable at test collection time (Plan 02 is parallel).
    """
    per_task = []
    for tier, results in per_tier_passed.items():
        for i, passed in enumerate(results):
            per_task.append({
                "task_name": f"{tier}-{i}",
                "category": tier,
                "passed": passed,
                "infra_fail": False,
            })

    # Build a duck-typed result object matching TBLiteRunResult fields
    @dataclass
    class _FakeRunResult:
        per_task: list = field(default_factory=list)
        subprocess_runtime_seconds: float = 1.0
        hang_count: int = 0
        cost_breakdown: dict = field(default_factory=lambda: {"modal_compute_usd": 1.0})
        samples_jsonl_path: Optional[Path] = Path("/tmp/fake_samples.jsonl")
        exit_code: int = 0
        status: str = "ok"
        jsonl_skipped_lines: int = 0
        stderr_tail: list = field(default_factory=list)

    return _FakeRunResult(
        per_task=per_task,
        subprocess_runtime_seconds=runtime,
        status=status,
    )


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestTBLiteBenchmarkGate:

    def test_constructor_validates_anchor_top_level_keys(self, tmp_path):
        from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate
        config = _make_config(tmp_path)
        bad_anchor = _make_anchor()
        bad_anchor.pop("dataset_revision_hash")
        with pytest.raises(ValueError, match="dataset_revision_hash"):
            TBLiteBenchmarkGate(config, bad_anchor, _make_subset())

    def test_constructor_validates_anchor_per_tier_tiers(self, tmp_path):
        from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate
        config = _make_config(tmp_path)
        bad_anchor = _make_anchor()
        bad_anchor["anchor_per_tier"].pop("extreme")
        with pytest.raises(ValueError, match="extreme"):
            TBLiteBenchmarkGate(config, bad_anchor, _make_subset())

    def test_constructor_validates_stratified_subset_task_filter(self, tmp_path):
        from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate
        config = _make_config(tmp_path)
        with pytest.raises(ValueError, match="task_filter"):
            TBLiteBenchmarkGate(
                config, _make_anchor(), {"seed": 1, "per_tier_counts": {}},
            )

    def test_check_anchor_existence_stale_commit_fails(self, tmp_path):
        from evolution.benchmarks import benchmark_gate as mod
        gate = _make_gate(tmp_path, anchor=_make_anchor(hermes_commit="STALE111"))
        # Mock git rev-parse to return a DIFFERENT commit.
        with patch.object(mod, "subprocess") as mock_subp:
            mock_subp.run.return_value = MagicMock(stdout="CURRENT222\n")
            mock_subp.TimeoutExpired = Exception
            mock_subp.CalledProcessError = Exception
            with pytest.raises(SystemExit) as ei:
                gate._check_anchor_existence()
            assert ei.value.code == 1

    def test_check_overlay_sanity_dirty_git_fails(self, tmp_path):
        from evolution.benchmarks import benchmark_gate as mod
        gate = _make_gate(tmp_path)
        with patch.object(mod, "subprocess") as mock_subp:
            mock_subp.run.return_value = MagicMock(stdout=" M agent/prompt_builder.py\n")
            mock_subp.TimeoutExpired = Exception
            with pytest.raises(SystemExit) as ei:
                gate._check_overlay_sanity()
            assert ei.value.code == 1

    def test_check_overlay_sanity_unwritable_path_fails(self, tmp_path, monkeypatch):
        gate = _make_gate(tmp_path)
        # Force os.access to return False for prompt_builder.py's dir.
        real_access = __import__("os").access
        target_parent = gate._target_path.parent
        def fake_access(p, mode):
            if Path(p) == target_parent:
                return False
            return real_access(p, mode)
        monkeypatch.setattr("os.access", fake_access)
        with pytest.raises(SystemExit) as ei:
            gate._check_overlay_sanity()
        assert ei.value.code == 1

    def test_risk_score_extreme_single_breach_rejects(self, tmp_path):
        gate = _make_gate(tmp_path)
        per_tier_report = {
            "easy":    {"breach": False},
            "medium":  {"breach": False},
            "hard":    {"breach": False},
            "extreme": {"breach": True},
        }
        risk = gate._compute_risk_score(per_tier_report)
        assert risk == 4.0, f"single extreme breach must give 4.0, got {risk}"
        assert risk >= gate.reject_threshold

    def test_risk_score_cumulative_low_tier_rejects(self, tmp_path):
        gate = _make_gate(tmp_path)
        per_tier_report = {
            "easy":    {"breach": True},
            "medium":  {"breach": True},
            "hard":    {"breach": True},
            "extreme": {"breach": False},
        }
        risk = gate._compute_risk_score(per_tier_report)
        assert risk == pytest.approx(4.5), f"cumulative breach must be 4.5, got {risk}"
        assert risk >= gate.reject_threshold

    def test_risk_score_below_threshold_accepts(self, tmp_path):
        gate = _make_gate(tmp_path)
        per_tier_report = {
            "easy":    {"breach": True},
            "medium":  {"breach": True},
            "hard":    {"breach": False},
            "extreme": {"breach": False},
        }
        risk = gate._compute_risk_score(per_tier_report)
        assert risk == pytest.approx(2.5), f"easy+medium breach must be 2.5, got {risk}"
        assert risk < gate.reject_threshold

    def test_threshold_uses_z_1_96_and_stdev(self, tmp_path):
        gate = _make_gate(tmp_path, anchor=_make_anchor(easy=0.85, stdev=0.02))
        # 3-run with slight variance -> stdev > 0
        per_run = [
            {"easy": 0.85, "medium": 0.70, "hard": 0.50, "extreme": 0.30},
            {"easy": 0.86, "medium": 0.70, "hard": 0.50, "extreme": 0.30},
            {"easy": 0.84, "medium": 0.70, "hard": 0.50, "extreme": 0.30},
        ]
        per_tier = gate._aggregate_per_tier(per_run)
        # statistics.stdev([0.85, 0.86, 0.84]) ≈ 0.01
        expected_threshold = 0.85 - 1.96 * per_tier["easy"]["stdev"]
        assert abs(per_tier["easy"]["threshold"] - round(expected_threshold, 4)) < 1e-4, \
            f"threshold wrong: {per_tier['easy']['threshold']} expected {expected_threshold}"

    def test_moving_avg_falls_back_to_anchor_on_first_run(self, tmp_path):
        gate = _make_gate(tmp_path, anchor=_make_anchor(easy=0.85, extreme=0.30),
                          moving_avg_history=[])
        ma = gate._moving_avg_per_tier()
        assert ma["easy"] == 0.85
        assert ma["extreme"] == 0.30

    def test_infra_fail_skipped_in_pass_rate(self, tmp_path):
        gate = _make_gate(tmp_path)

        @dataclass
        class _RunResult:
            per_task: list = field(default_factory=list)
            subprocess_runtime_seconds: float = 1.0
            hang_count: int = 0
            cost_breakdown: dict = field(default_factory=dict)
            samples_jsonl_path: Optional[Path] = None
            exit_code: int = 0
            status: str = "ok"
            jsonl_skipped_lines: int = 0
            stderr_tail: list = field(default_factory=list)

        result = _RunResult(per_task=[
            {"task_name": "a", "category": "easy", "passed": True, "infra_fail": False},
            {"task_name": "b", "category": "easy", "passed": False, "infra_fail": True},
            {"task_name": "c", "category": "easy", "passed": True, "infra_fail": False},
        ])
        rate = gate._one_run_per_tier_pass_rate(result)
        # Without infra_fail: 2 valid (a passed, c passed) -> 1.0
        assert rate["easy"] == 1.0, f"infra_fail not excluded: {rate['easy']}"

    def test_cache_hit_short_circuits_subprocess(self, tmp_path):
        from evolution.benchmarks import benchmark_gate as mod
        gate = _make_gate(tmp_path)
        # Pre-write a cache entry.
        sections = [_FakeSection("memory_guidance", "evolved")]
        cache_dir = tmp_path / "cache"

        # Compute expected hash using the same logic as benchmark_gate
        import hashlib
        import json as _json
        def _canonical_json(obj) -> str:
            return _json.dumps(obj, sort_keys=True, separators=(",", ":"))
        h = hashlib.sha256()
        h.update(_canonical_json(
            [{"section_id": s.section_id, "text": s.text} for s in sections]
        ).encode("utf-8"))
        h.update(gate.anchor["dataset_revision_hash"].encode("utf-8"))
        h.update(int(gate.anchor.get("stratified_subset_seed", 42)).to_bytes(4, "big"))
        from evolution.benchmarks.tblite_runner import TBLITE_RUNNER_VERSION
        h.update(TBLITE_RUNNER_VERSION.encode("utf-8"))
        key = h.hexdigest()[:16]

        (cache_dir / key).mkdir(parents=True)
        cached_report = {
            "decision": "accept",
            "risk_score": 0.0,
            "per_tier": {"easy": {"mean": 0.85, "breach": False}},
        }
        (cache_dir / key / "result.json").write_text(json.dumps(cached_report))

        # Mock runner — must NOT be called.
        mock_runner = MagicMock()
        gate.runner = mock_runner

        report = gate.check(sections, cache_dir=cache_dir, use_cache=True)
        assert report["decision"] == "accept"
        assert report["cache_hit"] is True
        assert not mock_runner.run.called, "cache hit must NOT invoke runner.run"

    def test_cache_miss_writes_result_only_on_accept(self, tmp_path):
        from evolution.benchmarks import benchmark_gate as mod
        gate = _make_gate(tmp_path, runs=1)
        # No pre-existing cache. Mock pre-flight + runner.
        cache_dir = tmp_path / "cache"
        with patch.object(mod, "subprocess") as mock_subp, \
             patch.object(gate.runner, "run") as mock_run, \
             patch.object(gate, "_check_overlay_sanity"), \
             patch.object(gate, "_check_anchor_existence"), \
             patch.object(gate, "_run_overlay", return_value=(tmp_path / "snap", tmp_path / "ovl")), \
             patch.object(gate, "_restore_overlay"):
            mock_subp.TimeoutExpired = Exception
            # All 4 tiers pass -> no breach -> accept.
            mock_run.return_value = _fake_run_result({
                "easy":    [True] * 4,
                "medium":  [True] * 4,
                "hard":    [True] * 4,
                "extreme": [True] * 4,
            })
            sections = [_FakeSection("memory_guidance", "evolved")]
            report = gate.check(sections, cache_dir=cache_dir, use_cache=True)
        assert report["decision"] == "accept"

        # Find the cache key from report
        key = report.get("artifact_hash")
        assert key is not None, "artifact_hash should be in report"
        assert (cache_dir / key / "result.json").exists(), "accept path must write cache"

    def test_fs_boundary_cross_fs_uses_copy2_fallback(self, tmp_path, monkeypatch):
        """When st_dev differs, _run_overlay falls back to shutil.copy2 instead of os.replace."""
        gate = _make_gate(tmp_path)
        # Force stat().st_dev to differ between target and overlay dirs.
        real_stat = Path.stat
        def fake_stat(self, *args, **kwargs):
            s = real_stat(self, *args, **kwargs)
            import os as _os
            class _S:
                def __init__(self, base, dev):
                    self._b = base
                    self.st_dev = dev
                def __getattr__(self, name):
                    return getattr(self._b, name)
            # ~/.hermes/tmp gets dev=999; everything else gets dev=1.
            if str(self).startswith(str(Path.home() / ".hermes")):
                return _S(s, 999)
            return _S(s, 1)
        monkeypatch.setattr(Path, "stat", fake_stat)

        sections = [_FakeSection("memory_guidance", "evolved", (1, 3),
                                  gate._target_path)]
        # Patch write_back_section into a no-op: post-CR-01 the overlay
        # threads edits through overlay_path, so it needs the file to
        # exist on disk. shutil.copy2 is mocked below, so the overlay
        # would never be created — patch write_back_section to skip the
        # body but stay observable.
        with patch(
            "evolution.benchmarks.benchmark_gate.shutil.copy2"
        ) as mock_copy, patch(
            "evolution.benchmarks.benchmark_gate.os.replace"
        ) as mock_replace, patch(
            "evolution.prompts.prompt_loader.write_back_section"
        ):
            gate._run_overlay(sections)
            # Snapshot (always copy2) + cross-fs replace fallback (copy2)
            # = at least 2 copy2 calls; os.replace NOT called for the
            # target swap.
            assert mock_copy.call_count >= 2, \
                f"copy2 fallback not taken: {mock_copy.call_count}"
            # os.replace should NOT replace the target file (cross-fs branch).
            target_replace_calls = [
                c for c in mock_replace.call_args_list
                if str(c.args[1]) == str(gate._target_path)
            ]
            assert len(target_replace_calls) == 0, \
                f"cross-fs path must NOT call os.replace on target: {target_replace_calls}"

    def test_restore_overlay_called_on_subprocess_error(self, tmp_path):
        """try/finally guarantee: even when runner.run raises, restore runs."""
        from evolution.benchmarks import benchmark_gate as mod
        gate = _make_gate(tmp_path, runs=1)
        cache_dir = tmp_path / "cache"
        sections = [_FakeSection("memory_guidance", "evolved")]
        snap = tmp_path / "snapshot"
        with patch.object(mod, "subprocess"), \
             patch.object(gate, "_check_overlay_sanity"), \
             patch.object(gate, "_check_anchor_existence"), \
             patch.object(gate, "_run_overlay", return_value=(snap, tmp_path / "ovl")), \
             patch.object(gate, "_restore_overlay") as mock_restore, \
             patch.object(gate.runner, "run", side_effect=RuntimeError("boom")):
            with pytest.raises(RuntimeError, match="boom"):
                gate.check(sections, cache_dir=cache_dir, use_cache=True)
        mock_restore.assert_called_once_with(snap)

    def test_moving_avg_uses_history_when_provided(self, tmp_path):
        """When history is non-empty, moving_avg uses last 10 entries."""
        history = [
            {"per_tier": {"easy": {"mean": 0.90}, "medium": {"mean": 0.75},
                          "hard": {"mean": 0.55}, "extreme": {"mean": 0.35}}}
            for _ in range(3)
        ]
        gate = _make_gate(tmp_path, anchor=_make_anchor(easy=0.85),
                          moving_avg_history=history)
        ma = gate._moving_avg_per_tier()
        assert abs(ma["easy"] - 0.90) < 1e-6, f"moving_avg should be 0.90, got {ma['easy']}"

    def test_constructor_raises_on_empty_task_filter(self, tmp_path):
        from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate
        config = _make_config(tmp_path)
        bad_subset = {
            "seed": 42,
            "per_tier_counts": {"easy": 1},
            "task_filter": [],  # empty is invalid
        }
        with pytest.raises(ValueError, match="task_filter is empty"):
            TBLiteBenchmarkGate(config, _make_anchor(), bad_subset)

    def test_check_extracts_task_names_from_w7_dict_subset(self, tmp_path):
        """CR-02 regression: W-7 dict task_filter items must be extracted
        to plain strings before being passed to TBLiteRunner.run, which
        rejects non-str items via _validate_task_filter.
        """
        from evolution.benchmarks import benchmark_gate as mod
        # Build a W-7 shaped subset (list of {name, tier} dicts).
        w7_subset = {
            "seed": 42,
            "per_tier_counts": {"easy": 1, "medium": 1, "hard": 1, "extreme": 1},
            "task_filter": [
                {"name": "tblite-easy-01", "tier": "easy"},
                {"name": "tblite-medium-01", "tier": "medium"},
                {"name": "tblite-hard-01", "tier": "hard"},
                {"name": "tblite-extreme-01", "tier": "extreme"},
            ],
        }
        gate = _make_gate(tmp_path, subset=w7_subset, runs=1)
        cache_dir = tmp_path / "cache"
        sections = [_FakeSection("memory_guidance", "evolved")]
        captured_task_filter: list = []

        def _capture_run(*, task_filter, output_dir):
            captured_task_filter.append(task_filter)
            return _fake_run_result({
                "easy":    [True],
                "medium":  [True],
                "hard":    [True],
                "extreme": [True],
            })

        with patch.object(mod, "subprocess"), \
             patch.object(gate, "_check_overlay_sanity"), \
             patch.object(gate, "_check_anchor_existence"), \
             patch.object(gate, "_run_overlay",
                          return_value=(tmp_path / "snap", tmp_path / "ovl")), \
             patch.object(gate, "_restore_overlay"), \
             patch.object(gate.runner, "run", side_effect=_capture_run):
            gate.check(sections, cache_dir=cache_dir, use_cache=True)

        assert captured_task_filter, "runner.run was never invoked"
        names = captured_task_filter[0]
        assert all(isinstance(n, str) for n in names), (
            f"runner received non-str task_filter items: {names}"
        )
        assert names == [
            "tblite-easy-01", "tblite-medium-01",
            "tblite-hard-01", "tblite-extreme-01",
        ], f"name extraction wrong: {names}"

    def test_constructor_accepts_w7_dict_task_filter(self, tmp_path):
        """CR-02 / WR-03 regression: constructor must accept list[dict] subset
        items as well as legacy list[str].
        """
        from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate
        config = _make_config(tmp_path)
        w7_subset = {
            "seed": 42,
            "per_tier_counts": {"easy": 1, "medium": 1, "hard": 1, "extreme": 1},
            "task_filter": [
                {"name": "tblite-easy-01", "tier": "easy"},
                {"name": "tblite-medium-01", "tier": "medium"},
                {"name": "tblite-hard-01", "tier": "hard"},
                {"name": "tblite-extreme-01", "tier": "extreme"},
            ],
        }
        # Must not raise — W-7 schema is accepted.
        TBLiteBenchmarkGate(config, _make_anchor(), w7_subset)

    def test_constructor_rejects_dict_missing_name_key(self, tmp_path):
        """CR-02: dict task_filter items must carry a 'name' key."""
        from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate
        config = _make_config(tmp_path)
        bad_subset = {
            "seed": 42,
            "per_tier_counts": {"easy": 1},
            "task_filter": [{"tier": "easy"}],  # missing name
        }
        with pytest.raises(ValueError, match="missing 'name'"):
            TBLiteBenchmarkGate(config, _make_anchor(), bad_subset)

    def test_run_overlay_preserves_all_sections(self, tmp_path):
        """CR-01 regression: multi-section overlay must keep every evolved section.

        Before the fix, write_back_section(self._target_path, ..., dest=overlay_path)
        re-read the (unmodified) target file on every iteration and wrote the
        full body to overlay_path, overwriting prior iterations' edits. Only
        the section processed LAST survived in the overlay. With N>=2 evolved
        sections this silently benchmarks the original prompt with a single
        section swapped.
        """
        from evolution.prompts.prompt_loader import PromptSection
        # Build a prompt_builder.py with two evolvable top-level str vars
        # whose line ranges do not overlap (otherwise write_back_section
        # bottom-up assumption breaks).
        hermes = tmp_path / "hermes-agent"
        (hermes / "agent").mkdir(parents=True, exist_ok=True)
        prompt_builder = hermes / "agent" / "prompt_builder.py"
        prompt_builder.write_text(
            'MEMORY_GUIDANCE = (\n'
            '    "ORIGINAL_MEMORY"\n'
            ')\n'
            'SKILLS_GUIDANCE = (\n'
            '    "ORIGINAL_SKILLS"\n'
            ')\n'
        )
        config = _make_config(hermes)
        from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate
        gate = TBLiteBenchmarkGate(
            config,
            anchor=_make_anchor(),
            stratified_subset=_make_subset(),
        )

        # Two real PromptSection objects with non-overlapping line ranges.
        # source_path is the SAME as the target (real-world shape).
        evolved = [
            PromptSection(
                section_id="memory_guidance",
                text="EVOLVED_MEMORY",
                char_count=len("EVOLVED_MEMORY"),
                line_range=(1, 3),
                source_path=prompt_builder,
            ),
            PromptSection(
                section_id="skills_guidance",
                text="EVOLVED_SKILLS",
                char_count=len("EVOLVED_SKILLS"),
                line_range=(4, 6),
                source_path=prompt_builder,
            ),
        ]
        snapshot_path, overlay_path = gate._run_overlay(evolved)

        # The TARGET should now contain BOTH evolved sections — verify the
        # target file (which os.replace promoted from overlay_path) holds
        # both evolved strings.
        target_text = prompt_builder.read_text()
        assert "EVOLVED_MEMORY" in target_text, (
            f"first evolved section dropped: target file is\n{target_text}"
        )
        assert "EVOLVED_SKILLS" in target_text, (
            f"second evolved section dropped: target file is\n{target_text}"
        )
        assert "ORIGINAL_MEMORY" not in target_text, (
            f"original memory text leaked past overlay: {target_text}"
        )
        assert "ORIGINAL_SKILLS" not in target_text, (
            f"original skills text leaked past overlay: {target_text}"
        )

        # Restore so the rest of the test suite sees a clean tree.
        gate._restore_overlay(snapshot_path)
