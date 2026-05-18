"""End-to-end integration tests for mine_prompt_sessions CLI (Phase 19 Wave 5).

These complement the Wave 3 unit tests in test_mine_prompt_sessions.py by
exercising the full mine() pipeline through CliRunner with extensive but
shallow mocks (EvolutionConfig / extract_prompt_sections / SessionPromptMiner
/ split_and_duplicate). The aim is to validate plan-defined integration
acceptance criteria:

Decisions covered:
    D-04:  persona_drift / oracle_disagreement graceful disable (lazy)
    D-13:  --behavioral-multiplier parameter threading into SessionPromptMiner
    D-17:  13 Click flags discoverable via --help
    D-20:  5-file success output topology (train/val/holdout.jsonl + metrics.json + miner_log.jsonl)
    D-25:  --i-have-consent hard gate
    W2 fix: --drift-thresholds-path missing must NOT block at Click parse stage
            (lazy check in mine() body, symmetric with oracle disabled)

Uses click.testing.CliRunner and unittest.mock to avoid LLM and filesystem
coupling. All temporary FAILED_<ts>/ writes are confined to tmp_path via
monkeypatch.chdir.
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
def chdir_tmp(tmp_path, monkeypatch):
    """Isolate FAILED_<ts>/<output>/ filesystem writes to tmp_path."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _make_section(section_id="memory_guidance"):
    """Construct a real PromptSection accepted by mine()."""
    from evolution.prompts.prompt_loader import PromptSection

    return PromptSection(
        section_id=section_id,
        text="mock body",
        char_count=9,
        line_range=(1, 1),
        source_path=Path("/mock/prompt_builder.py"),
    )


@pytest.fixture
def mock_environment(chdir_tmp):
    """Patch the 4 external dependencies of mine() — EvolutionConfig +
    extract_prompt_sections + SessionPromptMiner + split_and_duplicate —
    AND pre-create a valid drift_thresholds.json so default Click path
    doesn't block (W2 fix scenario uses a dedicated missing-thresholds
    test below).
    """
    from evolution.prompts import mine_prompt_sessions

    cfg = MagicMock()
    cfg.hermes_agent_path = chdir_tmp / "fake_hermes"
    cfg.judge_model = "default-mock"
    cfg.eval_model = "default-mock"
    cfg.get_lm_kwargs = MagicMock(return_value={})

    thresholds = chdir_tmp / "drift_thresholds.json"
    thresholds.write_text(
        json.dumps(
            {
                "tone": 0.5,
                "formality": 0.5,
                "vocabulary": 0.5,
                "persona": 0.5,
            }
        )
    )

    with patch.object(mine_prompt_sessions, "EvolutionConfig") as MC, patch.object(
        mine_prompt_sessions, "extract_prompt_sections"
    ) as MS, patch.object(
        mine_prompt_sessions, "SessionPromptMiner"
    ) as MM, patch.object(
        mine_prompt_sessions, "split_and_duplicate"
    ) as SAD:
        MC.load.return_value = cfg
        MS.return_value = [_make_section()]

        miner_inst = MagicMock()
        miner_inst.metrics = {
            "total_candidates_by_signal": {
                "user_correction": 0,
                "section_specific_failure": 0,
                "oracle_disagreement": 0,
                "persona_drift": 0,
            },
            "judge_confirmed_by_signal": {
                "user_correction": 0,
                "section_specific_failure": 0,
                "oracle_disagreement": 0,
                "persona_drift": 0,
            },
            "judge_false_positives_by_signal": {
                "user_correction": 0,
                "section_specific_failure": 0,
                "oracle_disagreement": 0,
                "persona_drift": 0,
            },
            "judge_calls_by_signal": {
                "user_correction": 0,
                "section_specific_failure": 0,
                "oracle_disagreement": 0,
                "persona_drift": 0,
            },
            "surface_drift_dropped": 0,
            "surface_drift_sections": {},
            "secret_filter_skipped": 0,
            "session_load_failures": 0,
            "jsonl_skipped_lines": 0,
            "judge_calls": 0,
            "final_examples_by_split": {"train": 0, "val": 0, "holdout": 0},
            "final_train_after_duplication": 0,
            "mining_multiplier_used": {},
            "persona_drift_thresholds_used": {},
            "oracle_baseline_path": None,
            "judge_model": "default-mock",
        }
        miner_inst._load_session = MagicMock(return_value={"messages": []})
        miner_inst._extract_user_correction = MagicMock(return_value=[])
        miner_inst._extract_section_specific_failure = MagicMock(return_value=[])
        miner_inst._extract_oracle_disagreement = MagicMock(return_value=[])
        miner_inst._extract_persona_drift = MagicMock(return_value=[])
        miner_inst._filter_secrets = MagicMock(side_effect=lambda x: x)
        miner_inst.mine = MagicMock(return_value=[])
        MM.return_value = miner_inst
        SAD.return_value = ([], [], [])

        yield {
            "EvolutionConfig": MC,
            "extract_prompt_sections": MS,
            "SessionPromptMiner": MM,
            "split_and_duplicate": SAD,
            "miner_inst": miner_inst,
            "config": cfg,
            "tmp_path": chdir_tmp,
            "thresholds_path": thresholds,
        }


# ── Test classes ───────────────────────────────────────────────────────────


class TestHelpAndFlags:
    def test_help_lists_all_13_flags(self, runner):
        """D-17 acceptance: --help discoverability of every flag."""
        from evolution.prompts.mine_prompt_sessions import main as cli_main

        r = runner.invoke(cli_main, ["--help"])
        assert r.exit_code == 0
        for flag in [
            "--sessions-dir",
            "--output",
            "--limit",
            "--i-have-consent",
            "--signals",
            "--baseline-module",
            "--judge-model",
            "--behavioral-multiplier",
            "--hermes-repo",
            "--model",
            "--api-base",
            "--dry-run",
            "--drift-thresholds-path",
        ]:
            assert flag in r.output, f"missing flag {flag!r} in --help"


class TestConsentGate:
    """D-25: --i-have-consent is the Layer-3 privacy gate."""

    def test_consent_missing_exits_nonzero(self, runner):
        from evolution.prompts.mine_prompt_sessions import main as cli_main

        # mix_stderr=False ensures click.echo(err=True) is captured separately;
        # without this, accessing r.stderr raises ValueError on older Click.
        # We use combined stream by default (mix_stderr default True) and read
        # r.output which contains stdout+stderr.
        r = runner.invoke(cli_main, [])
        assert r.exit_code != 0
        assert "--i-have-consent" in r.output

    def test_consent_present_proceeds_to_mine(self, runner, mock_environment):
        from evolution.prompts.mine_prompt_sessions import main as cli_main

        sessions = mock_environment["tmp_path"] / "sessions"
        sessions.mkdir()
        r = runner.invoke(
            cli_main,
            [
                "--i-have-consent",
                "--sessions-dir",
                str(sessions),
                "--drift-thresholds-path",
                str(mock_environment["thresholds_path"]),
                "--dry-run",
                "--signals",
                "user_correction",
            ],
        )
        # Dry-run with no candidates exits 0 (success)
        assert r.exit_code == 0, r.output

    def test_consent_present_signals_hermes_sessions_path_in_help(self, runner):
        """D-25 audit guidance: the consent error message names the data path
        so audit reviewers can find the source."""
        from evolution.prompts.mine_prompt_sessions import main as cli_main

        r = runner.invoke(cli_main, [])
        assert r.exit_code != 0
        # Phase 14 D-16 mirror — the error message must reference the path so
        # an auditor reviewing the failure can identify the data source.
        assert "~/.hermes/sessions" in r.output


class TestFailurePaths:
    """D-20 FAILED_<ts>/ contract — 5 distinct error_keys with metrics.json."""

    def test_sessions_dir_missing(self, runner, mock_environment):
        from evolution.prompts.mine_prompt_sessions import main as cli_main

        r = runner.invoke(
            cli_main,
            [
                "--i-have-consent",
                "--sessions-dir",
                str(mock_environment["tmp_path"] / "nonexistent"),
                "--drift-thresholds-path",
                str(mock_environment["thresholds_path"]),
            ],
        )
        assert r.exit_code == 1
        failed_dirs = list(
            (mock_environment["tmp_path"] / "datasets" / "prompts" / "sessions").glob(
                "FAILED_*"
            )
        )
        assert len(failed_dirs) >= 1
        metrics = json.loads((failed_dirs[0] / "metrics.json").read_text())
        assert metrics["error"] == "sessions_dir_missing"

    def test_no_examples_post_judge(self, runner, mock_environment):
        from evolution.prompts.mine_prompt_sessions import main as cli_main

        sessions = mock_environment["tmp_path"] / "sessions"
        sessions.mkdir()
        (sessions / "s.json").write_text(json.dumps({"messages": []}))
        # miner.mine returns [] (default mock value)
        r = runner.invoke(
            cli_main,
            [
                "--i-have-consent",
                "--sessions-dir",
                str(sessions),
                "--drift-thresholds-path",
                str(mock_environment["thresholds_path"]),
                "--signals",
                "user_correction",
            ],
        )
        assert r.exit_code == 1
        failed_dirs = list(
            (mock_environment["tmp_path"] / "datasets" / "prompts" / "sessions").glob(
                "FAILED_*"
            )
        )
        assert len(failed_dirs) >= 1
        metrics = json.loads((failed_dirs[0] / "metrics.json").read_text())
        assert metrics["error"] == "no_examples_post_judge"


class TestGracefulDisable:
    """D-04: missing dependencies for a signal disable that signal only,
    do NOT abort the run when other signals can still produce examples."""

    def test_oracle_missing_baseline_warns_and_continues(
        self, runner, mock_environment
    ):
        from evolution.prompts.mine_prompt_sessions import main as cli_main

        sessions = mock_environment["tmp_path"] / "sessions"
        sessions.mkdir()
        (sessions / "s.json").write_text(json.dumps({"messages": []}))
        r = runner.invoke(
            cli_main,
            [
                "--i-have-consent",
                "--sessions-dir",
                str(sessions),
                "--drift-thresholds-path",
                str(mock_environment["thresholds_path"]),
                "--dry-run",
                "--signals",
                "oracle_disagreement,user_correction",
            ],
        )
        assert r.exit_code == 0
        # The yellow warn must mention oracle_disagreement disabled / baseline
        assert (
            "oracle_disagreement signal disabled" in r.output
            or "baseline" in r.output.lower()
        )

    def test_persona_drift_missing_thresholds_graceful(self, runner, mock_environment):
        """W2 fix regression sentinel: missing --drift-thresholds-path file MUST
        NOT block at Click parse stage; must be lazy-checked in mine() and
        disable persona_drift symmetric with oracle_disagreement graceful
        disable. The literal assertion `"Invalid value" not in r.output` is
        the key regression guard."""
        from evolution.prompts.mine_prompt_sessions import main as cli_main

        sessions = mock_environment["tmp_path"] / "sessions"
        sessions.mkdir()
        (sessions / "s.json").write_text(json.dumps({"messages": []}))
        missing_thresholds = mock_environment["tmp_path"] / "missing_thresholds.json"
        assert not missing_thresholds.exists()
        r = runner.invoke(
            cli_main,
            [
                "--i-have-consent",
                "--sessions-dir",
                str(sessions),
                "--drift-thresholds-path",
                str(missing_thresholds),
                "--dry-run",
                "--signals",
                "persona_drift,user_correction",
            ],
        )
        # CRITICAL W2 regression assertion
        assert "Invalid value" not in r.output, (
            "W2 fix regression: Click rejected missing --drift-thresholds-path "
            "before reaching consent/mine() body. The option must NOT have "
            "exists=True; existence is lazy-checked inside mine()."
        )
        # Should reach mine() body, warn about persona_drift, and continue.
        assert r.exit_code == 0, r.output
        assert "persona_drift" in r.output.lower() or "drift" in r.output.lower()


class TestSuccessOutput:
    """D-20: success path writes 5 files (train/val/holdout.jsonl + metrics.json + miner_log.jsonl)."""

    def test_writes_5_files(self, runner, mock_environment):
        from evolution.prompts.mine_prompt_sessions import main as cli_main
        from evolution.prompts.prompt_dataset import PromptBehavioralExample

        sessions = mock_environment["tmp_path"] / "sessions"
        sessions.mkdir()
        (sessions / "s.json").write_text(json.dumps({"messages": []}))

        # Make miner.mine return a real PromptBehavioralExample to populate
        # split_and_duplicate's output.
        ex = PromptBehavioralExample(
            section_id="memory_guidance",
            user_message="m",
            expected_behavior="e",
            difficulty="medium",
            source="session",
            mining_signals=["user_correction"],
        )
        mock_environment["miner_inst"].mine.return_value = [ex]
        mock_environment["split_and_duplicate"].return_value = ([ex] * 3, [], [])

        out_dir = mock_environment["tmp_path"] / "out"
        r = runner.invoke(
            cli_main,
            [
                "--i-have-consent",
                "--sessions-dir",
                str(sessions),
                "--drift-thresholds-path",
                str(mock_environment["thresholds_path"]),
                "--output",
                str(out_dir),
                "--signals",
                "user_correction",
            ],
        )
        assert r.exit_code == 0, r.output
        for fname in [
            "train.jsonl",
            "val.jsonl",
            "holdout.jsonl",
            "metrics.json",
            "miner_log.jsonl",
        ]:
            assert (out_dir / fname).exists(), f"D-20: missing output file {fname!r}"


class TestDryRunBehavior:
    """D-25 + Plan 5.2: --dry-run skips LLM judge entirely."""

    def test_dry_run_does_not_call_miner_mine(self, runner, mock_environment):
        from evolution.prompts.mine_prompt_sessions import main as cli_main

        sessions = mock_environment["tmp_path"] / "sessions"
        sessions.mkdir()
        (sessions / "s.json").write_text(json.dumps({"messages": []}))
        r = runner.invoke(
            cli_main,
            [
                "--i-have-consent",
                "--sessions-dir",
                str(sessions),
                "--drift-thresholds-path",
                str(mock_environment["thresholds_path"]),
                "--dry-run",
                "--signals",
                "user_correction",
            ],
        )
        assert r.exit_code == 0, r.output
        # miner.mine NOT invoked under --dry-run; candidate enumeration uses
        # _extract_* / _filter_secrets directly.
        assert not mock_environment["miner_inst"].mine.called


class TestParserIntegration:
    """Plan 5.2: integration smoke for the two CLI parsers via the public API."""

    def test_parse_signals_via_invocation(self, runner, mock_environment):
        """Invalid --signals value must surface as a UsageError, not a silent miner build."""
        from evolution.prompts.mine_prompt_sessions import main as cli_main

        sessions = mock_environment["tmp_path"] / "sessions"
        sessions.mkdir()
        r = runner.invoke(
            cli_main,
            [
                "--i-have-consent",
                "--sessions-dir",
                str(sessions),
                "--drift-thresholds-path",
                str(mock_environment["thresholds_path"]),
                "--signals",
                "bogus_signal_name",
            ],
        )
        assert r.exit_code != 0
        # Should NOT have constructed SessionPromptMiner
        assert not mock_environment["SessionPromptMiner"].called

    def test_parse_multiplier_via_invocation(self, runner, mock_environment):
        """Invalid --behavioral-multiplier must surface as a UsageError."""
        from evolution.prompts.mine_prompt_sessions import main as cli_main

        sessions = mock_environment["tmp_path"] / "sessions"
        sessions.mkdir()
        r = runner.invoke(
            cli_main,
            [
                "--i-have-consent",
                "--sessions-dir",
                str(sessions),
                "--drift-thresholds-path",
                str(mock_environment["thresholds_path"]),
                "--behavioral-multiplier",
                "user_correction=notanint",
            ],
        )
        assert r.exit_code != 0
        # SessionPromptMiner must not have been built
        assert not mock_environment["SessionPromptMiner"].called


class TestParameterThreading:
    """D-13/D-17: CLI override flags must thread through to SessionPromptMiner construction."""

    def test_judge_model_override(self, runner, mock_environment):
        from evolution.prompts.mine_prompt_sessions import main as cli_main

        sessions = mock_environment["tmp_path"] / "sessions"
        sessions.mkdir()
        (sessions / "s.json").write_text(json.dumps({"messages": []}))
        runner.invoke(
            cli_main,
            [
                "--i-have-consent",
                "--sessions-dir",
                str(sessions),
                "--drift-thresholds-path",
                str(mock_environment["thresholds_path"]),
                "--judge-model",
                "my-test-model",
                "--dry-run",
                "--signals",
                "user_correction",
            ],
        )
        # config.judge_model overridden BEFORE miner construction
        assert mock_environment["config"].judge_model == "my-test-model"

    def test_behavioral_multiplier_threaded(self, runner, mock_environment):
        from evolution.prompts.mine_prompt_sessions import main as cli_main

        sessions = mock_environment["tmp_path"] / "sessions"
        sessions.mkdir()
        (sessions / "s.json").write_text(json.dumps({"messages": []}))
        runner.invoke(
            cli_main,
            [
                "--i-have-consent",
                "--sessions-dir",
                str(sessions),
                "--drift-thresholds-path",
                str(mock_environment["thresholds_path"]),
                "--behavioral-multiplier",
                "user_correction=7",
                "--dry-run",
                "--signals",
                "user_correction",
            ],
        )
        # SessionPromptMiner was called with multiplier_override
        call_kwargs = mock_environment["SessionPromptMiner"].call_args.kwargs
        assert call_kwargs["multiplier_override"] == {"user_correction": 7}
