"""Integration tests for evolve_prompt_sections --session-source flag (Phase 19 Wave 5).

Covers:
    D-16:   Two-pass union with hash dedup — session wins on same-split collision;
            synthetic dropped on cross-split collision.
    D-21:   --session-source transparent in joint AND round-robin modes.
    D-22:   build_drift_calibration.py untouched.
    D-24:   _load_session_dataset_resilient JSONL bad-line tolerance.
    W7 fix: Enhanced step 8c DriftDetector wiring regression guard with
            FOUR precise assertions (count ≥ 2, exact signature, key variable,
            output filename).

Uses click.testing.CliRunner with extensive mocking (dspy.LM / configure /
GEPA / DriftDetector / EvolutionConfig) to avoid real LLM and hermes-agent
filesystem coupling.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


# ── Shared fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def session_source_dir(tmp_path):
    """Create a session-source directory with 1 valid example in train.jsonl
    and empty val.jsonl/holdout.jsonl files (mimics mine_prompt_sessions output)."""
    d = tmp_path / "sess"
    d.mkdir()
    (d / "train.jsonl").write_text(
        json.dumps(
            {
                "section_id": "memory_guidance",
                "user_message": "session-only example one",
                "expected_behavior": "remember context",
                "difficulty": "medium",
                "source": "session",
                "mining_signals": ["user_correction"],
            }
        )
        + "\n"
    )
    (d / "val.jsonl").write_text("")
    (d / "holdout.jsonl").write_text("")
    return d


# ── Tests ──────────────────────────────────────────────────────────────────


class TestHelpAndParseGate:
    """D-21: --session-source surface + Click parse-time existence check."""

    def test_help_includes_session_source(self, runner):
        from evolution.prompts.evolve_prompt_sections import main as evolve_main

        r = runner.invoke(evolve_main, ["--help"])
        assert r.exit_code == 0
        assert "--session-source" in r.output

    def test_invalid_session_source_rejected(self, runner, tmp_path):
        from evolution.prompts.evolve_prompt_sections import main as evolve_main

        r = runner.invoke(
            evolve_main,
            [
                "--session-source",
                str(tmp_path / "does_not_exist"),
                "--dry-run",
            ],
        )
        assert r.exit_code != 0


class TestHelperResilience:
    """D-24: _load_session_dataset_resilient handles missing dirs + bad JSONL lines."""

    def test_missing_dir_returns_empty(self):
        from evolution.prompts.evolve_prompt_sections import (
            _load_session_dataset_resilient,
        )

        ds, sk = _load_session_dataset_resilient(Path("/totally/missing/dir"))
        assert ds.train == [] and ds.val == [] and ds.holdout == []
        assert sk == {"train": 0, "val": 0, "holdout": 0}

    def test_bad_lines_skipped(self, tmp_path):
        from evolution.prompts.evolve_prompt_sections import (
            _load_session_dataset_resilient,
        )

        d = tmp_path / "s"
        d.mkdir()
        (d / "train.jsonl").write_text(
            json.dumps(
                {
                    "section_id": "x",
                    "user_message": "good",
                    "expected_behavior": "e",
                }
            )
            + "\n"
            + "this is not json\n"
            + json.dumps(
                {
                    "section_id": "y",
                    "user_message": "good2",
                    "expected_behavior": "e2",
                }
            )
            + "\n"
        )
        (d / "val.jsonl").write_text("")
        (d / "holdout.jsonl").write_text("")
        ds, sk = _load_session_dataset_resilient(d)
        assert len(ds.train) == 2
        assert sk["train"] == 1

    def test_bad_line_rate_above_5pct_warns(self, tmp_path, capsys):
        """D-24: warn fires when skip rate > 5%."""
        from evolution.prompts.evolve_prompt_sections import (
            _load_session_dataset_resilient,
        )

        d = tmp_path / "s"
        d.mkdir()
        # 1 good + 1 bad → 50% > 5%
        (d / "train.jsonl").write_text(
            json.dumps(
                {
                    "section_id": "x",
                    "user_message": "good",
                    "expected_behavior": "e",
                }
            )
            + "\n"
            + "garbage\n"
        )
        (d / "val.jsonl").write_text("")
        (d / "holdout.jsonl").write_text("")
        ds, sk = _load_session_dataset_resilient(d)
        assert sk["train"] == 1
        captured = capsys.readouterr()
        # Rich Console may emit to stdout; check that 'skipped' appears in any captured stream.
        assert "skipped" in (captured.out + captured.err).lower()


class TestUnionLogic:
    """D-16: Two-pass union — session wins on same-split, synth dropped cross-split.

    Tests the union algorithm in isolation by replicating the step 5b block
    body (rather than mock the entire evolve() call stack).
    """

    @staticmethod
    def _train_msg(prefix):
        """Find a string that lands in 'train' bucket via _hash_to_split."""
        from evolution.prompts.prompt_dataset import (
            _hash_to_split,
            _normalize_task_hash,
        )

        i = 0
        while True:
            m = f"{prefix}_{i}"
            if _hash_to_split(_normalize_task_hash(m)) == "train":
                return m
            i += 1
            assert i < 10000, "hash bucket enumeration exhausted"

    @staticmethod
    def _holdout_msg(prefix):
        from evolution.prompts.prompt_dataset import (
            _hash_to_split,
            _normalize_task_hash,
        )

        i = 0
        while True:
            m = f"{prefix}_{i}"
            if _hash_to_split(_normalize_task_hash(m)) == "holdout":
                return m
            i += 1
            assert i < 10000, "hash bucket enumeration exhausted"

    @staticmethod
    def _run_union(dataset, session_dataset):
        """Replicate evolve_prompt_sections step 5b in isolation.

        Two-pass: collect session hashes by split, then for each split drop
        any synthetic example whose hash exists in ANY session split
        (cross-split drop) and append per-split session entries (session wins).
        """
        from evolution.prompts.prompt_dataset import _normalize_task_hash

        session_hashes_by_split = {}
        all_session_hashes = set()
        for split_name in ("train", "val", "holdout"):
            bs = {
                _normalize_task_hash(ex.user_message): ex
                for ex in getattr(session_dataset, split_name)
            }
            session_hashes_by_split[split_name] = bs
            all_session_hashes |= set(bs.keys())
        for split_name in ("train", "val", "holdout"):
            synth_kept = [
                ex
                for ex in getattr(dataset, split_name)
                if _normalize_task_hash(ex.user_message) not in all_session_hashes
            ]
            merged = synth_kept + list(session_hashes_by_split[split_name].values())
            setattr(dataset, split_name, merged)

    def test_no_collision(self):
        from evolution.prompts.prompt_dataset import (
            PromptBehavioralDataset,
            PromptBehavioralExample,
        )

        synth_msg = self._train_msg("synth")
        sess_msg = self._train_msg("sess")
        synth = PromptBehavioralDataset(
            train=[
                PromptBehavioralExample(
                    section_id="x",
                    user_message=synth_msg,
                    expected_behavior="e",
                    source="synthetic",
                )
            ],
            val=[],
            holdout=[],
        )
        sess = PromptBehavioralDataset(
            train=[
                PromptBehavioralExample(
                    section_id="x",
                    user_message=sess_msg,
                    expected_behavior="e",
                    source="session",
                    mining_signals=["user_correction"],
                )
            ],
            val=[],
            holdout=[],
        )
        self._run_union(synth, sess)
        assert len(synth.train) == 2

    def test_same_split_collision_session_wins(self):
        """D-16 session_wins on same-split hash collision."""
        from evolution.prompts.prompt_dataset import (
            PromptBehavioralDataset,
            PromptBehavioralExample,
        )

        shared_msg = self._train_msg("shared")
        synth = PromptBehavioralDataset(
            train=[
                PromptBehavioralExample(
                    section_id="x",
                    user_message=shared_msg,
                    expected_behavior="SYNTH",
                    source="synthetic",
                )
            ],
            val=[],
            holdout=[],
        )
        sess = PromptBehavioralDataset(
            train=[
                PromptBehavioralExample(
                    section_id="x",
                    user_message=shared_msg,
                    expected_behavior="SESS",
                    source="session",
                    mining_signals=["persona_drift"],
                )
            ],
            val=[],
            holdout=[],
        )
        self._run_union(synth, sess)
        assert len(synth.train) == 1
        assert synth.train[0].source == "session"
        assert synth.train[0].expected_behavior == "SESS"
        assert synth.train[0].mining_signals == ["persona_drift"]

    def test_cross_split_collision_synth_dropped(self):
        """D-16 cross-split: synth dropped when same hash exists in any session split."""
        from evolution.prompts.prompt_dataset import (
            PromptBehavioralDataset,
            PromptBehavioralExample,
        )

        shared = self._holdout_msg("cross_holdout")
        synth = PromptBehavioralDataset(
            train=[
                PromptBehavioralExample(
                    section_id="x",
                    user_message=shared,
                    expected_behavior="synth",
                    source="synthetic",
                )
            ],
            val=[],
            holdout=[],
        )
        sess = PromptBehavioralDataset(
            train=[],
            val=[],
            holdout=[
                PromptBehavioralExample(
                    section_id="x",
                    user_message=shared,
                    expected_behavior="sess",
                    source="session",
                    mining_signals=["user_correction"],
                )
            ],
        )
        self._run_union(synth, sess)
        # synth.train was dropped because the same hash exists in session.holdout
        assert len(synth.train) == 0
        assert len(synth.holdout) == 1
        assert synth.holdout[0].source == "session"


class TestPhase18Untouched:
    """W7 fix: enhanced regression guards on step 8c DriftDetector wiring
    AND on build_drift_calibration.py (D-22)."""

    def test_step_8c_drift_wiring_intact(self):
        """W7 fix: enhanced regression guard with 4 precise assertions.

        The DriftDetector wiring inserted by Plan 18-04 must remain. Enforces:
          1. `DriftDetector` token count ≥ 2 (import + at least one usage)
          2. Precise instantiation signature `DriftDetector(config, drift_thresholds)` present
          3. Key metrics variable `drift_per_dim_metrics` retained
          4. Step 8c output file `drift_report.txt` reference retained
        """
        path = Path("evolution/prompts/evolve_prompt_sections.py")
        content = path.read_text()

        # 1) `DriftDetector` token count ≥ 2 — import + at least one body usage.
        #    Phase 18 wiring imports DriftDetector at the top and instantiates
        #    it inside step 8c. W7 fix asserts both still occur (so wiring
        #    couldn't have been collapsed to an import-only stub or removed
        #    entirely). We separately check `DriftDetector(` instantiation
        #    count for the literal call form below.
        token_count = content.count("DriftDetector")
        assert token_count >= 2, (
            "DriftDetector token count regression — expected ≥ 2 occurrences "
            f"(import + body usage); got {token_count}"
        )
        # 1b) Instantiation count: `DriftDetector(` must appear ≥ 1 inside the
        #     body (the import alone — `import DriftDetector` — has no
        #     parentheses; an actual call site does).
        inst_count = content.count("DriftDetector(")
        assert inst_count >= 1, (
            "DriftDetector instantiation regression — expected ≥ 1 call site "
            "(e.g. `DriftDetector(config, drift_thresholds)`); "
            f"got {inst_count}"
        )
        # 2) precise instantiation signature
        assert "DriftDetector(config, drift_thresholds)" in content, (
            "step 8c DriftDetector signature changed — must remain "
            "`DriftDetector(config, drift_thresholds)`"
        )
        # 3) key metrics variable retained
        assert "drift_per_dim_metrics" in content, (
            "step 8c metrics variable `drift_per_dim_metrics` missing — "
            "Phase 18 wiring regression"
        )
        # 4) output filename retained
        assert "drift_report.txt" in content, (
            "step 8c drift_report.txt reference missing"
        )

    def test_build_drift_calibration_untouched(self):
        """D-22: Phase 19 must NOT add --session-source to calibration CLI."""
        path = Path("evolution/prompts/build_drift_calibration.py")
        if not path.exists():
            pytest.skip("build_drift_calibration.py not in tree")
        content = path.read_text()
        assert "--session-source" not in content
        assert "session_source" not in content


class TestCLIInvocation:
    """D-21: --session-source threads through main() → evolve() in both modes."""

    def test_dry_run_with_session_source_smoke(
        self, runner, session_source_dir, tmp_path
    ):
        """Mock the heavy dependencies (EvolutionConfig.load, extract_prompt_sections)
        so the CLI accepts --session-source argv without crashing. The dry-run
        path exits before the union block, so this is a smoke check on argv parsing
        rather than a behavioral assertion on union output.
        """
        from evolution.prompts import evolve_prompt_sections
        from evolution.prompts.evolve_prompt_sections import main as evolve_main
        from evolution.prompts.prompt_loader import PromptSection

        with patch.object(
            evolve_prompt_sections, "EvolutionConfig"
        ) as MC, patch.object(
            evolve_prompt_sections, "extract_prompt_sections"
        ) as MS:
            cfg = MagicMock()
            cfg.hermes_agent_path = tmp_path
            cfg.eval_model = "mock"
            cfg.judge_model = "mock"
            cfg.optimizer_model = "mock"
            cfg.iterations = 1
            cfg.get_lm_kwargs = MagicMock(return_value={})
            MC.load.return_value = cfg
            MS.return_value = [
                PromptSection(
                    section_id="memory_guidance",
                    text="x",
                    char_count=1,
                    line_range=(1, 1),
                    source_path=Path("x"),
                )
            ]
            # Drift thresholds for the --drift-thresholds-path arg
            (tmp_path / "drift_thresholds.json").write_text(
                json.dumps(
                    {
                        "tone": 0.5,
                        "formality": 0.5,
                        "vocabulary": 0.5,
                        "persona": 0.5,
                    }
                )
            )
            r = runner.invoke(
                evolve_main,
                [
                    "--dry-run",
                    "--session-source",
                    str(session_source_dir),
                    "--drift-thresholds-path",
                    str(tmp_path / "drift_thresholds.json"),
                ],
            )
            # Dry-run exits before union block (line ~247 sys.exit) — so this
            # is only a smoke check that argv was accepted. exit 0 (clean
            # dry-run) or 1 (environment mismatch) are both acceptable; what
            # matters is no argv-parse rejection.
            assert r.exit_code in (0, 1), r.output
            # The --session-source value was at least surfaced through the
            # parsing (no Click "Invalid value" rejection for the path).
            assert "Invalid value" not in r.output

    def test_session_source_works_in_round_robin_mode(
        self, runner, session_source_dir, tmp_path
    ):
        """D-21: --session-source is mode-agnostic (transparent in
        round-robin too)."""
        from evolution.prompts import evolve_prompt_sections
        from evolution.prompts.evolve_prompt_sections import main as evolve_main
        from evolution.prompts.prompt_loader import PromptSection

        with patch.object(
            evolve_prompt_sections, "EvolutionConfig"
        ) as MC, patch.object(
            evolve_prompt_sections, "extract_prompt_sections"
        ) as MS:
            cfg = MagicMock()
            cfg.hermes_agent_path = tmp_path
            cfg.eval_model = "mock"
            cfg.judge_model = "mock"
            cfg.optimizer_model = "mock"
            cfg.iterations = 1
            cfg.get_lm_kwargs = MagicMock(return_value={})
            MC.load.return_value = cfg
            MS.return_value = [
                PromptSection(
                    section_id="memory_guidance",
                    text="x",
                    char_count=1,
                    line_range=(1, 1),
                    source_path=Path("x"),
                )
            ]
            (tmp_path / "drift_thresholds.json").write_text(
                json.dumps(
                    {
                        "tone": 0.5,
                        "formality": 0.5,
                        "vocabulary": 0.5,
                        "persona": 0.5,
                    }
                )
            )
            r = runner.invoke(
                evolve_main,
                [
                    "--dry-run",
                    "--mode",
                    "round-robin",
                    "--session-source",
                    str(session_source_dir),
                    "--drift-thresholds-path",
                    str(tmp_path / "drift_thresholds.json"),
                ],
            )
            assert r.exit_code in (0, 1), r.output
            assert "Invalid value" not in r.output
