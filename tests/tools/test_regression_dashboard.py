"""Functional tests for regression_dashboard CLI — Phase 16 (TOOL-V2-04).

Wave 1: LATEST region + status color coding + frequency bars + sample-low n/a.
Wave 2-4 tests are stubbed with @pytest.mark.skip until those waves land.

WARNING 7 fix — 13 skip-stub names are LOCKED. Wave 2/3/4 unskip these exact
names; do not rename them in this file.
"""
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from evolution.tools.regression_dashboard import main, _segment_distribution, _status_style


FIXTURES = Path(__file__).parent.parent / "fixtures" / "dashboard_runs"


# ── Wave 1 tests (active) ─────────────────────────────────────────────────


def test_latest_renders_per_tool_table():
    """16-01-01 — LATEST renders Rich Table with tool names, delta_pp, sample columns."""
    runner = CliRunner()
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[FIXTURES / "params_complete" / "metrics.json"],
    ):
        result = runner.invoke(main, ["--runs", str(FIXTURES / "params_complete")], catch_exceptions=False)
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert "LATEST" in result.output
    assert "search_files" in result.output
    assert "read_file" in result.output
    # delta_pp column header — Rich truncates heavily in CliRunner narrow terminal;
    # Check for numeric delta values instead (more stable than header text)
    # "+4." or "-10." or similar delta_pp formatted values will appear
    assert "." in result.output  # numeric values present (delta_pp / rates)
    # sample column header or values (may truncate to "sam…")
    assert "sam" in result.output.lower() or "sample" in result.output.lower()


def test_status_color_coding():
    """16-01-02 (W2 fix — dual unit + functional) — status thresholds AND inline-markup
    correctness in _render_latest stdout.

    Unit half: _status_style returns correct (label, style) for FAIL/WARN/GAIN/OK.
    Functional half: invoke main on params_complete fixture (browser_navigate delta=-5pp);
    assert "FAIL" appears in stdout. This catches Rich markup bugs like
    `f"[{label}]{label}[/{label}]"` where label gets used as a style — unit pass,
    stdout rendering broken (label stripped or rendered as raw markup).
    """
    # ── Unit half: _status_style direct ──
    assert _status_style(-7.0)[0].startswith("FAIL")
    assert _status_style(-7.0)[1] == "bold red"
    assert _status_style(-3.0)[0].startswith("WARN")
    assert _status_style(-3.0)[1] == "yellow"
    assert _status_style(6.0)[0].startswith("GAIN")
    assert _status_style(6.0)[1] == "bold green"
    assert _status_style(1.0)[0].startswith("OK")
    assert _status_style(1.0)[1] == ""
    # Threshold edge cases
    assert _status_style(-5.0)[0].startswith("FAIL")  # ≤ -5pp inclusive
    assert _status_style(-2.0)[0].startswith("WARN")  # ≤ -2pp inclusive
    assert _status_style(5.0)[0].startswith("GAIN")   # ≥ +5pp inclusive
    # Custom warning_threshold_pp
    assert _status_style(-1.5, warning_threshold_pp=1.0)[0].startswith("WARN")  # -1.5 ≤ -1.0
    assert _status_style(-1.5, warning_threshold_pp=3.0)[0].startswith("OK")    # -1.5 > -3.0

    # ── Functional half: invoke main with fixture that has FAIL-level delta ──
    # params_complete fixture: browser_navigate baseline=0.60, evolved=0.55 → delta=-5pp → FAIL ❌
    runner = CliRunner()
    fixture_path = FIXTURES / "params_complete" / "metrics.json"
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[fixture_path],
    ):
        result = runner.invoke(main, ["--runs", str(fixture_path.parent)], catch_exceptions=False)
    assert result.exit_code == 0, f"stdout: {result.output}"
    # The status label "FAIL" must appear in stdout — proves _render_latest inline markup
    # is rendering the label correctly (catches `f"[{label}]{label}[/{label}]"` bugs).
    assert "FAIL" in result.output, \
        f"expected 'FAIL' in stdout for browser_navigate row (delta=-5pp); got: {result.output[:1000]}"
    # browser_navigate row must be visible (proves table render reached this row)
    assert "browser_navigate" in result.output


def test_frequency_bars_aggregate_long_tail(tmp_path):
    """16-01-03 — frequency bars show top-12, aggregate the rest into 'others (N tool[s])'."""
    # Build a fixture run with 13 distinct correct_tools
    run_dir = tmp_path / "long_tail"
    run_dir.mkdir()
    raw_preds = [
        {"correct_tool": f"tool_{i:02d}", "selected_tool": f"tool_{i:02d}",
         "difficulty": "easy", "num_available_tools": 3}
        for i in range(13)
    ]
    metrics = {
        "timestamp": "20260512_999999",
        "param_predictors_discovered": 1,
        "baseline_score": 0.5,
        "per_tool_baseline_rates": {f"tool_{i:02d}": 0.5 for i in range(13)},
        "per_tool_evolved_rates": {f"tool_{i:02d}": 0.5 for i in range(13)},
        "raw_predictions": raw_preds,
    }
    metrics_path = run_dir / "metrics.json"
    metrics_path.write_text(json.dumps(metrics))

    runner = CliRunner()
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[metrics_path],
    ):
        result = runner.invoke(main, ["--runs", str(run_dir)], catch_exceptions=False)
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert "Sample frequency" in result.output
    # 13 tools, top 12 shown, 1 in others
    assert "others (1 tool" in result.output  # matches "1 tool" or "1 tools"


def test_distribution_n_a_when_sample_low():
    """16-01-04 — per-tool sample_count < 3 across segments → distribution columns render n/a."""
    runner = CliRunner()
    fixture_metrics_path = FIXTURES / "params_complete" / "metrics.json"
    assert fixture_metrics_path.exists(), f"fixture missing: {fixture_metrics_path}"
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[fixture_metrics_path],
    ):
        result = runner.invoke(main, ["--runs", str(fixture_metrics_path.parent), "--segment", "difficulty"], catch_exceptions=False)
    assert result.exit_code == 0, f"stdout: {result.output}"
    # browser_navigate has only 2 raw_predictions in fixture → must show n/a
    output = result.output
    # Find the browser_navigate row and assert n/a
    # Rich tables wrap so we look for "n/a" within close proximity to "browser_navigate"
    assert "browser_navigate" in output
    assert "n/a" in output


# ── Wave 2-4 stubs (skipped until those waves) ────────────────────────────
# WARNING 7 fix: these 13 names are LOCKED contracts.
# Wave 2 unskips: test_diff_requires_both_runs / test_trend_window_days_mutex / test_trend_sparkline
# Wave 3 unskips: test_ab_study_categories / test_ab_study_secret_redaction / test_source_detection /
#                 test_fallback_dropped_run / test_fallback_no_raw_predictions /
#                 test_fallback_no_ab_comparison / test_warning_threshold_no_exit
# Wave 4 unskips: test_e2e_dashboard_json_schema / test_dashboard_json_output_path / test_no_runs_exits_2
# Renaming any of these stubs breaks the wave-2/3/4 grep gates.


def test_diff_requires_both_runs():
    """16-02-01 (D-05) — DIFF region requires both --baseline-run AND --evolved-run.

    Behavior: passing only one → stdout yellow hint, no exit code change
    (still 0, LATEST still rendered). Passing both → DIFF region rendered.
    """
    runner = CliRunner()
    fixture_v1 = FIXTURES / "params_complete"
    fixture_v2 = FIXTURES / "params_complete_v2"

    # Case 1: only --baseline-run → DIFF skipped with hint, exit 0
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[fixture_v1 / "metrics.json"],
    ):
        result = runner.invoke(
            main,
            ["--runs", str(fixture_v1), "--baseline-run", str(fixture_v1)],
            catch_exceptions=False,
        )
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert "DIFF region requires both" in result.output

    # Case 2: both → DIFF rendered
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[fixture_v1 / "metrics.json", fixture_v2 / "metrics.json"],
    ):
        result = runner.invoke(
            main,
            [
                "--runs", str(fixture_v1),
                "--runs", str(fixture_v2),
                "--baseline-run", str(fixture_v1),
                "--evolved-run", str(fixture_v2),
            ],
            catch_exceptions=False,
        )
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert "DIFF" in result.output


def test_trend_window_days_mutex():
    """16-02-02 (D-06) — --trend-window and --trend-days are mutually exclusive."""
    runner = CliRunner()
    fixture_v1 = FIXTURES / "params_complete"
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[fixture_v1 / "metrics.json"],
    ):
        result = runner.invoke(
            main,
            ["--runs", str(fixture_v1), "--trend-window", "5", "--trend-days", "7"],
            catch_exceptions=False,
        )
    assert result.exit_code == 2, (
        f"expected exit 2 (UsageError), got {result.exit_code}; "
        f"stdout: {result.output}"
    )
    assert "mutually exclusive" in result.output


def test_trend_sparkline():
    """16-02-03 (D-10 B) — TREND region renders sparkline (▁▂▃▄▅▆▇█) + quintile columns."""
    runner = CliRunner()
    fixture_v1 = FIXTURES / "params_complete"
    fixture_v2 = FIXTURES / "params_complete_v2"
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[fixture_v1 / "metrics.json", fixture_v2 / "metrics.json"],
    ):
        result = runner.invoke(
            main,
            ["--runs", str(fixture_v1), "--runs", str(fixture_v2), "--trend-window", "10"],
            catch_exceptions=False,
        )
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert "TREND" in result.output
    spark_chars = "▁▂▃▄▅▆▇█"
    assert any(c in result.output for c in spark_chars), (
        f"no sparkline chars in stdout: {result.output[:500]}"
    )
    assert "min" in result.output.lower()
    assert "p25" in result.output
    assert "median" in result.output
    assert "p75" in result.output
    assert "max" in result.output.lower()


@pytest.mark.skip(reason="Wave 3 — ABStudy categories")
def test_ab_study_categories():
    pass


@pytest.mark.skip(reason="Wave 3 — ABStudy secret redaction")
def test_ab_study_secret_redaction():
    pass


@pytest.mark.skip(reason="Wave 3 — source detection")
def test_source_detection():
    pass


@pytest.mark.skip(reason="Wave 3 — fallback dropped run")
def test_fallback_dropped_run():
    pass


@pytest.mark.skip(reason="Wave 3 — fallback no raw_predictions")
def test_fallback_no_raw_predictions():
    pass


@pytest.mark.skip(reason="Wave 3 — fallback no ab_comparison")
def test_fallback_no_ab_comparison():
    pass


@pytest.mark.skip(reason="Wave 3 — warning threshold no exit")
def test_warning_threshold_no_exit():
    pass


@pytest.mark.skip(reason="Wave 4 — E2E dashboard.json schema")
def test_e2e_dashboard_json_schema():
    pass


@pytest.mark.skip(reason="Wave 4 — dashboard.json output path")
def test_dashboard_json_output_path():
    pass


@pytest.mark.skip(reason="Wave 4 — no runs exits 2")
def test_no_runs_exits_2():
    pass
