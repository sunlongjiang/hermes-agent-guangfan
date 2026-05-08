"""Wave 0 RED test scaffolding for Phase 14 mine_tool_sessions CLI.

Covers 14-VALIDATION.md rows 20-24 — consent gate, dry-run, signal subset
flag, multiplier override parser, optional baseline-module flag. CLI is
implemented in `evolution/tools/mine_tool_sessions.py` (Plan 05).
"""

import pytest


def test_consent_required():
    """CLI exits 1 with error mentioning 'consent' when --i-have-consent is missing.

    Runs the CLI via click.testing.CliRunner without --i-have-consent.
    Expected: exit_code == 1, stderr contains 'i-have-consent' or 'consent'
    (D-16 strict consent gate — no mining without explicit opt-in).
    """
    pytest.skip("Wave 1+ 实现 — 见 14-05-PLAN.md")


def test_dry_run():
    """--dry-run prints the plan but does not call the LLM.

    CliRunner invocation with --dry-run --i-have-consent. Expected:
    LM call count == 0, exit_code == 0, stdout contains 'dry-run' or
    plan summary (candidates/signals detected without judge execution).
    """
    pytest.skip("Wave 1+ 实现 — 见 14-05-PLAN.md")


def test_signal_subset():
    """--signals=error_retry,user_correction skips the oracle (C) code path.

    CliRunner with signals flag; assert that no ToolModule (baseline oracle)
    is invoked and metrics.judge_calls_by_signal has no 'oracle_disagreement'
    key.
    """
    pytest.skip("Wave 1+ 实现 — 见 14-05-PLAN.md")


def test_multiplier_override():
    """--misselection-multiplier 'error_retry=5,user_correction=2' parses correctly.

    Parser produces dict == {'error_retry': 5, 'user_correction': 2}.
    Invalid tokens (missing `=`, non-integer) raise a click error.
    """
    pytest.skip("Wave 1+ 实现 — 见 14-05-PLAN.md")


def test_baseline_module_optional():
    """Omitted --baseline-module auto-skips C (oracle) signal with a warn.

    CliRunner without --baseline-module. Expected: oracle_disagreement
    extractor is skipped, a warn is logged, other signals still run.
    """
    pytest.skip("Wave 1+ 实现 — 见 14-05-PLAN.md")
