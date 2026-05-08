"""Wave 1 GREEN tests for Phase 14 mine_tool_sessions CLI.

Covers 14-VALIDATION.md rows 20-24 — consent gate, dry-run, signal subset
flag, multiplier override parser, optional baseline-module flag.
"""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from evolution.tools.mine_tool_sessions import (
    _parse_multiplier_override,
    _parse_signals,
    main,
)

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "sessions"


class _StubTool:
    def __init__(self, name: str):
        self.name = name


def _prep_sessions(tmp_path: Path) -> Path:
    """Copy 1 fixture session into a tmp dir and return its path."""
    sdir = tmp_path / "sessions"
    sdir.mkdir()
    shutil.copy(FIXTURE_DIR / "error_retry_b.json", sdir / "session_1.json")
    return sdir


def test_consent_required():
    """CLI exits 1 with stderr containing 'consent' when --i-have-consent missing."""
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(main, [])
    assert result.exit_code == 1, f"expected exit 1, got {result.exit_code}"
    assert "consent" in (result.stderr or result.output or "").lower()


def test_dry_run(tmp_path):
    """--dry-run does not call the LLM (judge_calls == 0) + writes metrics.json."""
    sdir = _prep_sessions(tmp_path)
    outdir = tmp_path / "out"
    # Patch tool discovery so the CLI doesn't need a real hermes-agent repo
    stub_tools = [
        _StubTool("legacy_grep"),
        _StubTool("search_files"),
        _StubTool("terminal"),
    ]
    with patch(
        "evolution.tools.mine_tool_sessions.discover_tool_files"
    ) as mock_discover, patch(
        "evolution.tools.mine_tool_sessions.extract_tool_descriptions"
    ) as mock_extract:
        mock_discover.return_value = [Path("/fake")]
        mock_extract.return_value = stub_tools
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--i-have-consent",
                "--dry-run",
                "--sessions-dir",
                str(sdir),
                "--output",
                str(outdir),
            ],
        )
    assert result.exit_code == 0, (
        f"expected exit 0, got {result.exit_code}\noutput:\n{result.output}"
    )
    metrics_path = outdir / "metrics.json"
    assert metrics_path.exists()
    metrics = json.loads(metrics_path.read_text())
    assert metrics["judge_calls"] == 0, (
        f"dry-run should not call LLM, got judge_calls={metrics['judge_calls']}"
    )


def test_signal_subset(tmp_path):
    """--signals=error_retry,user_correction skips oracle path entirely."""
    sdir = _prep_sessions(tmp_path)
    outdir = tmp_path / "out"
    stub_tools = [_StubTool("terminal"), _StubTool("search_files")]
    with patch(
        "evolution.tools.mine_tool_sessions.discover_tool_files"
    ) as mock_discover, patch(
        "evolution.tools.mine_tool_sessions.extract_tool_descriptions"
    ) as mock_extract:
        mock_discover.return_value = [Path("/fake")]
        mock_extract.return_value = stub_tools
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--i-have-consent",
                "--dry-run",
                "--signals",
                "error_retry,user_correction",
                "--sessions-dir",
                str(sdir),
                "--output",
                str(outdir),
            ],
        )
    assert result.exit_code == 0, (
        f"expected exit 0, got {result.exit_code}\n{result.output}"
    )
    metrics = json.loads((outdir / "metrics.json").read_text())
    # oracle_disagreement bucket untouched
    assert metrics["judge_calls_by_signal"]["oracle_disagreement"] == 0
    assert metrics["total_candidates_by_signal"]["oracle_disagreement"] == 0


def test_multiplier_override():
    """--misselection-multiplier 'error_retry=5,user_correction=2' parses to dict."""
    out = _parse_multiplier_override("error_retry=5,user_correction=2")
    assert out == {"error_retry": 5, "user_correction": 2}

    # Empty / None returns {}
    assert _parse_multiplier_override(None) == {}
    assert _parse_multiplier_override("") == {}

    # Invalid format raises
    with pytest.raises(click.UsageError):
        _parse_multiplier_override("error_retry=abc")
    with pytest.raises(click.UsageError):
        _parse_multiplier_override("unknown_signal=1")
    with pytest.raises(click.UsageError):
        _parse_multiplier_override("error_retry")  # missing =


def test_baseline_module_optional(tmp_path):
    """Omitted --baseline-module with oracle signal emits warn + no oracle candidates."""
    sdir = _prep_sessions(tmp_path)
    outdir = tmp_path / "out"
    stub_tools = [_StubTool("terminal"), _StubTool("search_files")]
    with patch(
        "evolution.tools.mine_tool_sessions.discover_tool_files"
    ) as mock_discover, patch(
        "evolution.tools.mine_tool_sessions.extract_tool_descriptions"
    ) as mock_extract:
        mock_discover.return_value = [Path("/fake")]
        mock_extract.return_value = stub_tools
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--i-have-consent",
                "--dry-run",
                "--signals",
                "error_retry,oracle_disagreement",
                "--sessions-dir",
                str(sdir),
                "--output",
                str(outdir),
            ],
        )
    assert result.exit_code == 0, f"expected exit 0, got {result.exit_code}\n{result.output}"
    # The warn message about oracle skipping should appear in output
    combined = result.output.lower()
    assert "baseline-module" in combined or "oracle" in combined or "skip" in combined
    metrics = json.loads((outdir / "metrics.json").read_text())
    # oracle_disagreement produced 0 candidates (no baseline_module means extractor skips)
    assert metrics["total_candidates_by_signal"]["oracle_disagreement"] == 0


def test_parse_signals_helper():
    """_parse_signals rejects unknown signals + dedupes."""
    assert _parse_signals("error_retry,user_correction") == [
        "error_retry",
        "user_correction",
    ]
    assert _parse_signals("error_retry,error_retry") == ["error_retry"]
    with pytest.raises(click.UsageError):
        _parse_signals("error_retry,unknown_signal")
    with pytest.raises(click.UsageError):
        _parse_signals("")
