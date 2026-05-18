"""Tests for evolution.prompts.mine_prompt_sessions CLI (Phase 19 Plan 03).

RED phase covers BOTH Task 3.1 (CLI skeleton + 13 Click options + helpers +
consent gate) and Task 3.2 (mine() body + FAILED_<ts>/ paths + Rich summary +
graceful disable of persona_drift / oracle_disagreement).

Tests use Click's CliRunner and unittest.mock to avoid LLM calls.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner


# ── Task 3.1: skeleton + helpers + consent gate ───────────────────────────


class TestTask31_ImportSurface:
    def test_module_imports(self):
        """T1: Module is importable; main + mine exist; helpers exported."""
        import evolution.prompts.mine_prompt_sessions as mod
        assert hasattr(mod, "main")
        assert hasattr(mod, "mine")
        assert hasattr(mod, "_parse_signals")
        assert hasattr(mod, "_parse_multiplier_override")

    def test_main_is_click_command(self):
        from evolution.prompts.mine_prompt_sessions import main
        assert isinstance(main, click.Command)


class TestTask31_HelpFlag:
    def test_help_exits_zero(self):
        """T2: --help returns exit 0 and lists all 13 flag names."""
        r = subprocess.run(
            [sys.executable, "-m", "evolution.prompts.mine_prompt_sessions", "--help"],
            capture_output=True,
            text=True,
        )
        assert r.returncode == 0, f"stderr: {r.stderr}"
        flags = [
            "--sessions-dir", "--output", "--limit", "--i-have-consent",
            "--signals", "--baseline-module", "--judge-model",
            "--behavioral-multiplier", "--hermes-repo", "--model",
            "--api-base", "--dry-run", "--drift-thresholds-path",
        ]
        for f in flags:
            assert f in r.stdout, f"missing flag {f!r} in --help output"

    def test_help_via_clirunner(self):
        from evolution.prompts.mine_prompt_sessions import main
        runner = CliRunner()
        r = runner.invoke(main, ["--help"])
        assert r.exit_code == 0
        # CliRunner sometimes wraps text; just check key tokens
        assert "--i-have-consent" in r.output
        assert "--drift-thresholds-path" in r.output
        assert "--behavioral-multiplier" in r.output


class TestTask31_ConsentGate:
    def test_no_consent_subprocess_exits_nonzero(self):
        """T3: no --i-have-consent → exit code !=0; stderr has flag + path."""
        r = subprocess.run(
            [sys.executable, "-m", "evolution.prompts.mine_prompt_sessions"],
            capture_output=True,
            text=True,
        )
        assert r.returncode != 0
        # Errors may land on either stderr or stdout depending on Click version;
        # Phase 14 mirror uses err=True so stderr is canonical, but accept either.
        combined = r.stderr + r.stdout
        assert "--i-have-consent" in combined
        assert "~/.hermes/sessions" in combined

    def test_no_consent_clirunner(self):
        from evolution.prompts.mine_prompt_sessions import main
        runner = CliRunner()
        r = runner.invoke(main, [])
        assert r.exit_code != 0


class TestTask31_DriftThresholdsLazy:
    def test_default_drift_thresholds_path_does_not_block_consent(self):
        """T10 (W2 fix): default --drift-thresholds-path file missing must NOT
        cause Click 'Invalid value' rejection BEFORE consent gate / before mine().

        i.e. Click option must not have exists=True; the existence check is
        lazy inside mine() and only triggered when persona_drift is in signals.
        """
        r = subprocess.run(
            [
                sys.executable, "-m", "evolution.prompts.mine_prompt_sessions",
                "--i-have-consent", "--sessions-dir", "/definitely/not/there",
            ],
            capture_output=True,
            text=True,
        )
        # CRITICAL: must NOT be 'Invalid value for --drift-thresholds-path'
        combined = r.stderr + r.stdout
        assert "Invalid value" not in combined, (
            "W2 regression: Click rejected default --drift-thresholds-path "
            "before reaching mine() body / consent gate"
        )


class TestTask31_ParseSignals:
    def test_parse_signals_valid(self):
        from evolution.prompts.mine_prompt_sessions import _parse_signals
        assert _parse_signals("user_correction,persona_drift") == [
            "user_correction", "persona_drift",
        ]

    def test_parse_signals_dedup_preserves_order(self):
        from evolution.prompts.mine_prompt_sessions import _parse_signals
        result = _parse_signals("user_correction,user_correction,persona_drift")
        assert result == ["user_correction", "persona_drift"]

    def test_parse_signals_unknown_raises(self):
        from evolution.prompts.mine_prompt_sessions import _parse_signals
        with pytest.raises(click.UsageError) as exc:
            _parse_signals("user_correction,unknown_signal")
        assert "unknown" in str(exc.value).lower()

    def test_parse_signals_empty_raises(self):
        from evolution.prompts.mine_prompt_sessions import _parse_signals
        with pytest.raises(click.UsageError) as exc:
            _parse_signals("")
        assert "empty" in str(exc.value).lower()

    def test_parse_signals_whitespace_only_raises(self):
        from evolution.prompts.mine_prompt_sessions import _parse_signals
        with pytest.raises(click.UsageError):
            _parse_signals("  , ,  ")


class TestTask31_ParseMultiplier:
    def test_parse_multiplier_valid(self):
        from evolution.prompts.mine_prompt_sessions import _parse_multiplier_override
        assert _parse_multiplier_override("user_correction=5,persona_drift=2") == {
            "user_correction": 5,
            "persona_drift": 2,
        }

    def test_parse_multiplier_none_returns_empty(self):
        from evolution.prompts.mine_prompt_sessions import _parse_multiplier_override
        assert _parse_multiplier_override(None) == {}
        assert _parse_multiplier_override("") == {}

    def test_parse_multiplier_non_int_raises(self):
        from evolution.prompts.mine_prompt_sessions import _parse_multiplier_override
        with pytest.raises(click.UsageError) as exc:
            _parse_multiplier_override("user_correction=NaN")
        assert "int" in str(exc.value).lower()

    def test_parse_multiplier_unknown_signal_raises(self):
        from evolution.prompts.mine_prompt_sessions import _parse_multiplier_override
        with pytest.raises(click.UsageError) as exc:
            _parse_multiplier_override("unknown_sig=3")
        assert "unknown" in str(exc.value).lower()

    def test_parse_multiplier_missing_equals_raises(self):
        from evolution.prompts.mine_prompt_sessions import _parse_multiplier_override
        with pytest.raises(click.UsageError):
            _parse_multiplier_override("user_correction3")


# ── Task 3.2: mine() body + failure paths + dry-run ───────────────────────


@pytest.fixture
def chdir_tmp(tmp_path, monkeypatch):
    """Helper: chdir into a tmp dir so FAILED_/<output>/ paths land in isolation."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _make_mock_section(section_id="memory_guidance", text="mock section text"):
    """Build a minimal PromptSection that mine() accepts."""
    from evolution.prompts.prompt_loader import PromptSection
    return PromptSection(
        section_id=section_id,
        text=text,
        char_count=len(text),
        line_range=(1, 1),
        source_path=Path("/mock/prompt_builder.py"),
    )


class TestTask32_MineFailedPaths:
    def test_sessions_dir_missing_writes_failed_marker(self, chdir_tmp):
        """T1: non-existent sessions-dir → FAILED_/ with sessions_dir_missing."""
        from evolution.prompts.mine_prompt_sessions import main
        runner = CliRunner()
        r = runner.invoke(main, [
            "--i-have-consent",
            "--sessions-dir", "/definitely/not/here_xyz123",
        ])
        assert r.exit_code == 1, f"output: {r.output}"
        failed = list((chdir_tmp / "datasets" / "prompts" / "sessions").glob("FAILED_*"))
        assert len(failed) == 1, f"expected 1 FAILED dir, found {failed}"
        metrics = json.loads((failed[0] / "metrics.json").read_text())
        assert metrics["error"] == "sessions_dir_missing"

    def test_no_sections_found_writes_failed_marker(self, chdir_tmp):
        """T3: prompt_builder unreachable → FAILED_/ with no_sections_found
        (or prompt_extraction_failed). Mock extract_prompt_sections to return []."""
        from evolution.prompts import mine_prompt_sessions
        sessions = chdir_tmp / "sessions"
        sessions.mkdir()
        # Need at least an empty sessions_dir that exists
        with patch.object(mine_prompt_sessions, "EvolutionConfig") as MC, \
             patch.object(mine_prompt_sessions, "extract_prompt_sections") as MS:
            cfg = MagicMock()
            cfg.hermes_agent_path = chdir_tmp / "fake_hermes"
            cfg.judge_model = "mock"
            cfg.eval_model = "mock"
            cfg.get_lm_kwargs = MagicMock(return_value={})
            MC.load.return_value = cfg
            MS.return_value = []  # ← simulates no_sections_found

            runner = CliRunner()
            r = runner.invoke(mine_prompt_sessions.main, [
                "--i-have-consent",
                "--sessions-dir", str(sessions),
            ])
            assert r.exit_code == 1
            failed = list((chdir_tmp / "datasets" / "prompts" / "sessions").glob("FAILED_*"))
            assert len(failed) == 1
            metrics = json.loads((failed[0] / "metrics.json").read_text())
            assert metrics["error"] in ("no_sections_found", "prompt_extraction_failed")


class TestTask32_DryRun:
    def test_dry_run_does_not_call_miner_mine(self, chdir_tmp):
        """T4: --dry-run skips LLM judge; miner.mine is never invoked."""
        from evolution.prompts import mine_prompt_sessions
        sessions = chdir_tmp / "sessions"
        sessions.mkdir()
        (sessions / "s1.json").write_text(json.dumps({
            "messages": [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi"},
            ],
        }))

        with patch.object(mine_prompt_sessions, "EvolutionConfig") as MC, \
             patch.object(mine_prompt_sessions, "extract_prompt_sections") as MS, \
             patch.object(mine_prompt_sessions, "SessionPromptMiner") as MM:
            cfg = MagicMock()
            cfg.hermes_agent_path = chdir_tmp / "fake_hermes"
            cfg.judge_model = "mock"
            cfg.eval_model = "mock"
            cfg.get_lm_kwargs = MagicMock(return_value={})
            MC.load.return_value = cfg
            MS.return_value = [_make_mock_section()]
            miner_inst = MagicMock()
            miner_inst._load_session.return_value = {
                "messages": [{"role": "user", "content": "x"}]
            }
            miner_inst._extract_user_correction.return_value = []
            miner_inst._extract_section_specific_failure.return_value = []
            miner_inst._extract_oracle_disagreement.return_value = []
            miner_inst._extract_persona_drift.return_value = []
            miner_inst._filter_secrets.side_effect = lambda x: x
            miner_inst.metrics = {}
            MM.return_value = miner_inst

            runner = CliRunner()
            r = runner.invoke(mine_prompt_sessions.main, [
                "--i-have-consent",
                "--sessions-dir", str(sessions),
                "--dry-run",
                "--signals", "user_correction",
            ])
            assert r.exit_code == 0, r.output
            miner_inst.mine.assert_not_called()


class TestTask32_GracefulDisable:
    def test_persona_drift_thresholds_missing_disabled(self, chdir_tmp):
        """T7 (W2 fix): persona_drift signal enabled + drift_thresholds_path
        file missing → silent disable + Rich warn + removed from signals_list;
        does NOT fail mine()."""
        from evolution.prompts import mine_prompt_sessions
        sessions = chdir_tmp / "sessions"
        sessions.mkdir()  # empty but exists

        with patch.object(mine_prompt_sessions, "EvolutionConfig") as MC, \
             patch.object(mine_prompt_sessions, "extract_prompt_sections") as MS, \
             patch.object(mine_prompt_sessions, "SessionPromptMiner") as MM:
            cfg = MagicMock()
            cfg.hermes_agent_path = chdir_tmp / "fake_hermes"
            cfg.judge_model = "mock"
            cfg.eval_model = "mock"
            cfg.get_lm_kwargs = MagicMock(return_value={})
            MC.load.return_value = cfg
            MS.return_value = [_make_mock_section()]
            miner_inst = MagicMock()
            miner_inst.mine.return_value = []  # empty examples → no_examples_post_judge
            miner_inst.metrics = {}
            MM.return_value = miner_inst

            runner = CliRunner()
            r = runner.invoke(mine_prompt_sessions.main, [
                "--i-have-consent",
                "--sessions-dir", str(sessions),
                "--signals", "persona_drift,user_correction",
                "--drift-thresholds-path", "/nonexistent/drift_thresholds.json",
            ])
            # Either exit 0 (succeeded with empty result fine) or 1 (no_examples_post_judge);
            # what matters is NO Click 'Invalid value' rejection.
            assert "Invalid value" not in r.output
            # The persona_drift disable warn must appear
            assert "persona_drift" in r.output.lower() or "drift" in r.output.lower()
            # The SessionPromptMiner instance should have been built with signals
            # list that does NOT include 'persona_drift' (it was lazily dropped).
            assert MM.called
            call_kwargs = MM.call_args.kwargs
            signals_passed = call_kwargs.get("signals", [])
            assert "persona_drift" not in signals_passed, (
                f"persona_drift should be removed from signals when thresholds_path "
                f"is missing; got signals={signals_passed}"
            )

    def test_oracle_no_baseline_module_disabled(self, chdir_tmp):
        """T8b: oracle_disagreement signal enabled + no --baseline-module →
        Rich warn + signal continues other paths (does NOT fail)."""
        from evolution.prompts import mine_prompt_sessions
        sessions = chdir_tmp / "sessions"
        sessions.mkdir()

        with patch.object(mine_prompt_sessions, "EvolutionConfig") as MC, \
             patch.object(mine_prompt_sessions, "extract_prompt_sections") as MS, \
             patch.object(mine_prompt_sessions, "SessionPromptMiner") as MM:
            cfg = MagicMock()
            cfg.hermes_agent_path = chdir_tmp / "fake_hermes"
            cfg.judge_model = "mock"
            cfg.eval_model = "mock"
            cfg.get_lm_kwargs = MagicMock(return_value={})
            MC.load.return_value = cfg
            MS.return_value = [_make_mock_section()]
            miner_inst = MagicMock()
            miner_inst.mine.return_value = []
            miner_inst.metrics = {}
            MM.return_value = miner_inst

            runner = CliRunner()
            r = runner.invoke(mine_prompt_sessions.main, [
                "--i-have-consent",
                "--sessions-dir", str(sessions),
                "--signals", "oracle_disagreement,user_correction",
            ])
            # Must reach mine() body — Rich warn about oracle baseline missing
            assert "oracle" in r.output.lower() or r.exit_code in (0, 1)
            # SessionPromptMiner constructed with baseline_module=None
            assert MM.called
            call_kwargs = MM.call_args.kwargs
            assert call_kwargs.get("baseline_module") is None


class TestTask32_JudgeModelOverride:
    def test_judge_model_overrides_config(self, chdir_tmp):
        """T8: --judge-model overrides config.judge_model before constructing miner."""
        from evolution.prompts import mine_prompt_sessions
        sessions = chdir_tmp / "sessions"
        sessions.mkdir()
        with patch.object(mine_prompt_sessions, "EvolutionConfig") as MC, \
             patch.object(mine_prompt_sessions, "extract_prompt_sections") as MS, \
             patch.object(mine_prompt_sessions, "SessionPromptMiner") as MM:
            cfg = MagicMock()
            cfg.hermes_agent_path = chdir_tmp / "fake_hermes"
            cfg.judge_model = "default-judge"
            cfg.eval_model = "mock"
            cfg.get_lm_kwargs = MagicMock(return_value={})
            MC.load.return_value = cfg
            MS.return_value = [_make_mock_section()]
            miner_inst = MagicMock()
            miner_inst.mine.return_value = []
            miner_inst.metrics = {}
            MM.return_value = miner_inst

            runner = CliRunner()
            r = runner.invoke(mine_prompt_sessions.main, [
                "--i-have-consent",
                "--sessions-dir", str(sessions),
                "--judge-model", "override-judge-model",
                "--signals", "user_correction",  # avoid persona_drift complication
            ])
            # config.judge_model should have been set to override-judge-model
            assert cfg.judge_model == "override-judge-model"


class TestTask32_SuccessfulMine:
    def test_full_success_path_writes_5_files(self, chdir_tmp):
        """T5: complete success path → out_dir has train/val/holdout.jsonl +
        metrics.json + miner_log.jsonl five files, exit 0."""
        from evolution.prompts import mine_prompt_sessions
        from evolution.prompts.prompt_dataset import PromptBehavioralExample
        sessions = chdir_tmp / "sessions"
        sessions.mkdir()
        (sessions / "s1.json").write_text(json.dumps({
            "messages": [
                {"role": "user", "content": "ignored mock"},
                {"role": "assistant", "content": "ignored mock"},
            ],
        }))

        # Build a single example to flow through split_and_duplicate
        ex = PromptBehavioralExample(
            section_id="memory_guidance",
            user_message="I already told you the answer",
            expected_behavior="Recall the prior fact",
            difficulty="medium",
            source="session",
            mining_signals=["user_correction"],
        )

        # split_and_duplicate is a module-level callable in session_prompt_miner,
        # imported into mine_prompt_sessions; patch the binding there.
        out_dir = chdir_tmp / "out"

        with patch.object(mine_prompt_sessions, "EvolutionConfig") as MC, \
             patch.object(mine_prompt_sessions, "extract_prompt_sections") as MS, \
             patch.object(mine_prompt_sessions, "SessionPromptMiner") as MM, \
             patch.object(mine_prompt_sessions, "split_and_duplicate") as MSD:
            cfg = MagicMock()
            cfg.hermes_agent_path = chdir_tmp / "fake_hermes"
            cfg.judge_model = "mock"
            cfg.eval_model = "mock"
            cfg.get_lm_kwargs = MagicMock(return_value={})
            MC.load.return_value = cfg
            MS.return_value = [_make_mock_section()]
            miner_inst = MagicMock()
            miner_inst.mine.return_value = [ex]
            miner_inst.metrics = {
                "total_candidates_by_signal": {
                    "user_correction": 1, "section_specific_failure": 0,
                    "oracle_disagreement": 0, "persona_drift": 0,
                },
                "judge_confirmed_by_signal": {
                    "user_correction": 1, "section_specific_failure": 0,
                    "oracle_disagreement": 0, "persona_drift": 0,
                },
                "judge_false_positives_by_signal": {
                    "user_correction": 0, "section_specific_failure": 0,
                    "oracle_disagreement": 0, "persona_drift": 0,
                },
                "judge_calls_by_signal": {
                    "user_correction": 1, "section_specific_failure": 0,
                    "oracle_disagreement": 0, "persona_drift": 0,
                },
                "judge_calls": 1,
                "surface_drift_dropped": 0,
                "surface_drift_sections": {},
                "secret_filter_skipped": 0,
                "session_load_failures": 0,
                "jsonl_skipped_lines": 0,
                "final_examples_by_split": {"train": 1, "val": 0, "holdout": 0},
                "final_train_after_duplication": 3,
                "mining_multiplier_used": {
                    "user_correction": 3, "section_specific_failure": 3,
                    "oracle_disagreement": 2, "persona_drift": 2,
                },
                "judge_model": "mock",
                "oracle_baseline_path": None,
                "persona_drift_thresholds_used": {},
            }
            MM.return_value = miner_inst
            MSD.return_value = ([ex, ex, ex], [], [])  # train (after dup), val, holdout

            runner = CliRunner()
            r = runner.invoke(mine_prompt_sessions.main, [
                "--i-have-consent",
                "--sessions-dir", str(sessions),
                "--output", str(out_dir),
                "--signals", "user_correction",
            ])
            assert r.exit_code == 0, r.output
            for fname in ("train.jsonl", "val.jsonl", "holdout.jsonl",
                          "metrics.json", "miner_log.jsonl"):
                assert (out_dir / fname).exists(), f"missing {fname} in {out_dir}"
            # train.jsonl should have 3 lines (the duplicated example)
            train_lines = (out_dir / "train.jsonl").read_text().strip().splitlines()
            assert len(train_lines) == 3
            # metrics.json contains expected schema
            saved = json.loads((out_dir / "metrics.json").read_text())
            assert saved["judge_calls"] == 1
            assert saved["final_train_after_duplication"] == 3
            # Rich summary contains 4 signal rows + B3 fix labels
            assert "user_correction" in r.output
            assert "persona_drift" in r.output
            # B3 fix: both session_load_failures and jsonl_skipped_lines labels appear
            assert "session_load_failures" in r.output.lower() or "Session load failures" in r.output
            assert "JSONL skipped lines" in r.output or "jsonl_skipped_lines" in r.output.lower()
