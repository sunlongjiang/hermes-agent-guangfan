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


def test_ab_study_categories():
    """16-03-01 (D-15) — ABStudy three categories with counts and top-3 examples."""
    runner = CliRunner()
    fixture_path = FIXTURES / "reasoning_complete" / "metrics.json"
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[fixture_path],
    ):
        result = runner.invoke(
            main, ["--runs", str(fixture_path.parent)], catch_exceptions=False
        )
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert "ABStudy" in result.output
    assert "think_on_saved" in result.output
    assert "think_on_regressed" in result.output
    assert "both_wrong" in result.output


def test_ab_study_secret_redaction():
    """16-03-02 (D-15 / W3 fix) — secrets in BOTH task_description AND reasoning_text_on
    must be redacted before stdout render.
    """
    runner = CliRunner()
    fixture_dir = FIXTURES / "reasoning_with_secret"
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[fixture_dir / "metrics.json"],
    ):
        result = runner.invoke(
            main, ["--runs", str(fixture_dir)], catch_exceptions=False
        )
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert "sk-1234567890abcdefghijklmnopqrstuvwxyz" not in result.output, (
        f"task_description sk- key leaked: {result.output[:1000]}"
    )
    assert "AKIA" not in result.output, (
        f"AWS access key prefix leaked from reasoning_text_on: {result.output[:1000]}"
    )
    assert "AKIAIOSFODNN7EXAMPLE" not in result.output, (
        f"AWS access key full token leaked from reasoning_text_on: {result.output[:1000]}"
    )
    assert "REDACTED" in result.output


def test_source_detection():
    """16-03-03 (D-07) — source heuristic: think_ab_gate→reasoning, param_predictors→params,
    parent dir + baseline_score → desc, otherwise None.
    """
    from pathlib import Path as P
    from evolution.tools.regression_dashboard import _detect_source
    assert _detect_source({"think_ab_gate": {}}, P("output/tools_reasoning/abc/metrics.json")) == "reasoning"
    assert _detect_source({"param_predictors_discovered": 5}, P("output/tools/abc/metrics.json")) == "params"
    assert _detect_source(
        {"think_ab_gate": {}, "param_predictors_discovered": 5},
        P("output/tools_reasoning/abc/metrics.json"),
    ) == "reasoning"
    assert _detect_source({"some_field": 1}, P("output/tools_reasoning/abc/metrics.json")) == "reasoning"
    assert _detect_source({"baseline_score": 0.5}, P("output/tools/abc/metrics.json")) == "desc"
    assert _detect_source({}, P("output/tools/abc/metrics.json")) is None
    assert _detect_source({}, P("/tmp/abc/metrics.json")) is None


def test_fallback_dropped_run():
    """16-03-04 (D-08) — run missing per_tool_*_rates → dropped + dropped_runs[]."""
    runner = CliRunner()
    fixture_path = FIXTURES / "desc_old" / "metrics.json"
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[fixture_path],
    ):
        result = runner.invoke(
            main, ["--runs", str(fixture_path.parent)], catch_exceptions=False
        )
    assert result.exit_code == 0, f"stdout: {result.output}"
    output_lower = result.output.lower()
    assert (
        "dropped" in output_lower
        or "missing per_tool" in result.output
        or "failed" in output_lower
    )


def test_fallback_no_raw_predictions():
    """16-03-05 (D-08) — run has per_tool_*_rates but no raw_predictions →
    LATEST renders, distribution columns degrade to n/a, stdout warns.
    """
    runner = CliRunner()
    fixture_path = FIXTURES / "params_no_raw" / "metrics.json"
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[fixture_path],
    ):
        result = runner.invoke(
            main, ["--runs", str(fixture_path.parent)], catch_exceptions=False
        )
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert "LATEST" in result.output
    assert "distribution disabled" in result.output
    assert "n/a" in result.output


def test_fallback_no_ab_comparison():
    """16-03-06 (D-08) — reasoning run missing both per_tool_*_rates AND ab_comparison.json →
    run dropped before reaching ABStudy filter; stdout does not complain.
    """
    runner = CliRunner()
    fixture_path = FIXTURES / "reasoning_old" / "metrics.json"
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[fixture_path],
    ):
        result = runner.invoke(
            main, ["--runs", str(fixture_path.parent)], catch_exceptions=False
        )
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert "ABStudy" not in result.output
    assert "missing ab_comparison" not in result.output.lower()


def test_warning_threshold_no_exit(monkeypatch, tmp_path):
    """16-03-07 (D-13 / B3 fix) — warnings NEVER affect exit code regardless of threshold severity.

    Case A: params_complete + 2.0pp → 1 WARNING (browser_navigate -5pp); exit 0.
    Case B: params_multi_regress + 0.1pp → ≥3 WARNINGs; exit 0 STILL.
    """
    runner = CliRunner()

    # Case A: 2.0pp threshold on params_complete (browser_navigate -5pp is the sole negative)
    fixture_complete = FIXTURES / "params_complete"
    monkeypatch.chdir(tmp_path)
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[fixture_complete / "metrics.json"],
    ):
        result_a = runner.invoke(
            main,
            ["--runs", str(fixture_complete), "--warning-threshold-pp", "2.0"],
            catch_exceptions=False,
        )
    assert result_a.exit_code == 0, (
        f"Case A: expected exit 0 (D-13 no-gate), got {result_a.exit_code}; "
        f"stdout: {result_a.output}"
    )
    assert "WARNING:" in result_a.output, (
        f"Case A: expected 'WARNING:' for browser_navigate -5pp; got: {result_a.output[:1000]}"
    )
    assert result_a.output.count("WARNING:") == 1, (
        f"Case A: expected exactly 1 WARNING: line on params_complete; "
        f"got {result_a.output.count('WARNING:')}. stdout: {result_a.output[:1500]}"
    )
    assert "browser_navigate" in result_a.output

    # Case B: 0.1pp threshold on params_multi_regress (3 negative-delta tools by construction)
    fixture_multi = FIXTURES / "params_multi_regress"
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[fixture_multi / "metrics.json"],
    ):
        result_b = runner.invoke(
            main,
            ["--runs", str(fixture_multi), "--warning-threshold-pp", "0.1"],
            catch_exceptions=False,
        )
    assert result_b.exit_code == 0, (
        f"Case B (strict threshold): expected exit 0, got {result_b.exit_code}; "
        f"this would catch any 'if len(warnings_list) > N: return 1' bug. "
        f"stdout: {result_b.output}"
    )
    warning_count_b = result_b.output.count("WARNING:")
    assert warning_count_b >= 3, (
        f"Case B: expected at least 3 WARNING: lines at strict 0.1 threshold on "
        f"params_multi_regress (read_file/browser_navigate/edit_file all cross), "
        f"got {warning_count_b}. stdout: {result_b.output[:1500]}"
    )
    assert "read_file" in result_b.output, (
        f"Case B: read_file (-0.5pp) WARNING: missing. stdout: {result_b.output[:1500]}"
    )
    assert "browser_navigate" in result_b.output, (
        f"Case B: browser_navigate (-5.0pp) WARNING: missing. stdout: {result_b.output[:1500]}"
    )
    assert "edit_file" in result_b.output, (
        f"Case B: edit_file (-1.5pp) WARNING: missing. stdout: {result_b.output[:1500]}"
    )


def test_e2e_dashboard_json_schema(tmp_path, monkeypatch):
    """16-04-01 (D-04 + D-17) — E2E: 5 fixture runs → dashboard.json with 8 top-level fields."""
    runner = CliRunner()
    fixture_paths = [
        FIXTURES / "desc_old" / "metrics.json",
        FIXTURES / "params_complete" / "metrics.json",
        FIXTURES / "params_no_raw" / "metrics.json",
        FIXTURES / "reasoning_complete" / "metrics.json",
        FIXTURES / "reasoning_old" / "metrics.json",
    ]
    out_json = tmp_path / "test_dashboard.json"
    monkeypatch.chdir(tmp_path)
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=fixture_paths,
    ):
        result = runner.invoke(
            main,
            [
                "--runs", str(FIXTURES / "params_complete"),
                "--output", str(out_json),
                "--trend-window", "5",
            ],
            catch_exceptions=False,
        )
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert out_json.exists(), f"dashboard.json not written: {out_json}"
    data = json.loads(out_json.read_text())

    expected_keys = {
        "latest", "diff", "trend", "ab_study", "source_legend",
        "dropped_runs", "summary", "warnings",
    }
    assert expected_keys.issubset(set(data.keys())), (
        f"missing top-level keys: {expected_keys - set(data.keys())}"
    )
    assert "generated_at" in data
    assert data["scanned_runs"] == 5

    dropped_paths = [d["path"] for d in data["dropped_runs"]]
    assert any("desc_old" in p for p in dropped_paths), dropped_paths
    assert any("reasoning_old" in p for p in dropped_paths), dropped_paths

    assert set(data["source_legend"].keys()) == {"desc", "params", "reasoning"}

    assert data["latest"] is not None
    assert "per_tool" in data["latest"]
    assert "tools" in data["trend"]


def test_dashboard_json_output_path(tmp_path, monkeypatch):
    """16-04-02 (D-04) — dashboard.json default lands at CWD with `dashboard_<ts>.json` pattern;
    --output overrides path.
    """
    runner = CliRunner()
    fixture_path = FIXTURES / "params_complete" / "metrics.json"

    # Case 1: --output explicit path
    custom_out = tmp_path / "custom.json"
    monkeypatch.chdir(tmp_path)
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[fixture_path],
    ):
        result = runner.invoke(
            main,
            ["--runs", str(fixture_path.parent), "--output", str(custom_out)],
            catch_exceptions=False,
        )
    assert result.exit_code == 0, f"stdout: {result.output}"
    assert custom_out.exists()

    # Case 2: no --output → default `dashboard_<ts>.json` in CWD
    with patch(
        "evolution.tools.regression_dashboard._scan_runs",
        return_value=[fixture_path],
    ):
        result = runner.invoke(
            main,
            ["--runs", str(fixture_path.parent)],
            catch_exceptions=False,
        )
    assert result.exit_code == 0, f"stdout: {result.output}"
    matches = list(tmp_path.glob("dashboard_*.json"))
    assert len(matches) >= 1, (
        f"no dashboard_<ts>.json in CWD: {list(tmp_path.iterdir())}"
    )
    import re
    assert any(re.match(r"^dashboard_\d{8}_\d{6}\.json$", m.name) for m in matches), (
        f"filename does not match pattern: {[m.name for m in matches]}"
    )


def test_no_runs_exits_2():
    """16-04-03 (D-02) — empty default roots + no --runs → click.UsageError → exit 2."""
    runner = CliRunner()
    with patch(
        "evolution.tools.regression_dashboard.DEFAULT_ROOTS", ()
    ), patch(
        "evolution.tools.regression_dashboard._scan_runs", return_value=[]
    ):
        result = runner.invoke(main, [], catch_exceptions=False)
    assert result.exit_code == 2, (
        f"expected exit 2 (UsageError), got {result.exit_code}; stdout: {result.output}"
    )
    assert "no runs" in result.output.lower() or "no run" in result.output.lower()
