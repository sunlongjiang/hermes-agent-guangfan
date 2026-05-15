---
phase: 16-per-tool-regression-dashboard
verified: 2026-05-15T12:00:00Z
status: passed
score: 6/6 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 4/6
  gaps_closed:
    - "--runs <dir> CLI flag locates the run the user points at (CR-01/CR-02): _scan_runs dual-input signature + explicit_runs channel wired in main"
    - "evolve_tool_reasoning records coherent per-tool data without corrupting the A/B gate (CR-03): _score_with_predictions now uses joint_tool_param_metric"
  gaps_remaining: []
  regressions: []
deferred:
  - truth: "WR-03: _load_run called 2-3x per path (performance)"
    addressed_in: "future"
    evidence: "Explicitly deferred in 16-05-PLAN; low impact, marked TODO"
---

# Phase 16: Per-Tool Regression Dashboard Verification Report

**Phase Goal:** Track individual tool selection rates across optimization runs
**Verified:** 2026-05-15T12:00:00Z
**Status:** PASSED
**Re-verification:** Yes — after gap closure (Plan 16-05)

## Goal Achievement

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1   | Metrics file records per-tool accuracy before and after optimization (ROADMAP SC1) | ✓ VERIFIED | `persist_per_tool_rates` + `persist_raw_predictions` wired in all 3 CLIs. WR-04 fixed: `evolve_tool_descriptions` now calls both helpers BEFORE `if not regression_result.passed:` early return (line 374-375 before line 377). REGRESSION_FAILED metrics.json contains `**metrics_extra` (line 387). Confirmed by `test_regression_failed_metrics_carry_per_tool_rates` (G7). |
| 2   | Rich console dashboard shows selection rate changes per tool (ROADMAP SC2) | ✓ VERIFIED | `regression_dashboard.py` renders LATEST (12-col table), DIFF, TREND (sparkline + quintiles), ABStudy regions. 21 dashboard tests pass. Smoke test exit 0. |
| 3   | Regression threshold configurable, default 2pp drop triggers warning (ROADMAP SC3) | ✓ VERIFIED | `--warning-threshold-pp` default 2.0; `_status_style` WARN at `delta <= -warning_threshold_pp`; warning logged per regressed tool without affecting exit code. `test_warning_threshold_no_exit` passes. |
| 4   | Standalone read-only CLI; default-scans output/tools[_reasoning]/, --runs additive (16-01 must_have) | ✓ VERIFIED | CR-01/CR-02 fixed: `_scan_runs(roots, explicit_runs=())` dual-input signature (line 54-83). `main` routes `--runs` to `explicit_runs` channel (line 664-665). Smoke test confirmed: `--runs tests/fixtures/dashboard_runs/params_complete` → `scanned_runs: 1`, `latest.run_path` contains `params_complete`. `test_scan_runs_resolves_explicit_path` (G1) does NOT patch `_scan_runs` — real glob/explicit path exercised end-to-end. |
| 5   | dashboard.json emits 8 top-level fields, default `dashboard_<ts>.json`, --output overrides (16-04 must_have) | ✓ VERIFIED | `_write_dashboard_json` writes latest/diff/trend/ab_study/source_legend/dropped_runs/summary/warnings + generated_at/scanned_runs. `test_e2e_dashboard_json_schema`, `test_dashboard_json_output_path` pass. `datetime.utcnow()` replaced with `datetime.now(timezone.utc)` — zero DeprecationWarnings confirmed. |
| 6   | evolve_tool_reasoning records coherent per-tool data without corrupting the A/B gate (16-00 must_have + ROADMAP SC1) | ✓ VERIFIED | CR-03 fixed: `_score_with_predictions` uses `joint_tool_param_metric(ex, pred)` (line 688). Old `total += 1.0 if correct == selected else 0.0` completely removed (grep confirms 0 matches). `th_*_full` (via `_score_with_predictions`) and `th_*_ambig` (via `_safe_score`) now use coherent metrics. `test_score_with_predictions_uses_joint_metric` (G5) proves case-insensitive normalization: `Read_File` vs `read_file` scores 1.0. |

**Score:** 6/6 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `evolution/tools/regression_dashboard.py` | Dual-input `_scan_runs` + timezone.utc + WR-05/WR-06 fixes | ✓ VERIFIED | `_scan_runs(roots, explicit_runs=())` at line 54; `datetime.now(timezone.utc)` at lines 599, 741; `b_src = baseline_run["source"] or "?"` at line 363; empty-key filter at line 243. |
| `evolution/tools/evolve_tool_reasoning.py` | `_score_with_predictions` uses `joint_tool_param_metric` + WR-07 logging | ✓ VERIFIED | `joint_tool_param_metric` imported at line 54; called at line 688 inside `_score_with_predictions`. Per-example yellow log at line 668. Batch-level yellow log at line 697. |
| `evolution/tools/evolve_tool_descriptions.py` | persist calls BEFORE FAILED branch; FAILED metrics.json contains per-tool data | ✓ VERIFIED | `metrics_extra` assigned at lines 374-375, before `if not regression_result.passed:` at line 377. FAILED dict contains `**metrics_extra` at line 387. |
| `tests/tools/test_regression_dashboard.py` | 21 tests; at least 1 not patching `_scan_runs` | ✓ VERIFIED | 21 tests pass. `test_scan_runs_resolves_explicit_path` at line 537 does NOT patch `_scan_runs`; uses real glob + explicit path. |
| `tests/tools/test_evolve_tool_reasoning.py` | `test_score_with_predictions_uses_joint_metric` + `test_score_with_predictions_logs_per_example_error` | ✓ VERIFIED | Both tests present (lines 597, 647). 14 tests pass total. |
| `tests/tools/test_evolve_tool_descriptions.py` | `test_regression_failed_metrics_carry_per_tool_rates` drives real evolve() path | ✓ VERIFIED | Test at line 201 drives `evolve()` through full holdout loop (calls `evolve_tool_descriptions.evolve`). 6 tests pass total. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `regression_dashboard.py:main` | `_scan_runs` | `_scan_runs(roots, explicit_runs)` where `explicit_runs = tuple(Path(r) for r in runs)` | ✓ WIRED | line 664-665; `--runs` values walk explicit_runs channel |
| `evolve_tool_reasoning.py:_score_with_predictions` | `tool_metric.joint_tool_param_metric` | `sample_score = float(joint_tool_param_metric(ex, pred))` | ✓ WIRED | import line 54, call line 688 |
| `evolve_tool_descriptions.py` | FAILED metrics.json via `**metrics_extra` | `metrics_extra` assigned before branch; spread into `failed_metrics` dict | ✓ WIRED | lines 374-387 |
| `test_scan_runs_resolves_explicit_path` | `regression_dashboard.main` | `CliRunner.invoke` + `monkeypatch.setattr(DEFAULT_ROOTS, ())` | ✓ WIRED | Does not patch `_scan_runs`; real path resolution exercised |
| `evolve_tool_params.py` | `persist_raw_predictions` | import + call at line 1029, before FAILED branch | ✓ WIRED | unchanged from Wave 0; still correct |
| `evolve_tool_reasoning.py` | `persist_per_tool_rates` + `persist_raw_predictions` | called at lines 566-567 after `_score_with_predictions` | ✓ WIRED | uses `tool_pairs_off`/`tool_pairs_on`/`raw_preds_on` from the fixed helper |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `regression_dashboard.py` | `usable_runs` / `latest_run` | `_scan_runs` → `_load_run` → `metrics.json` on disk | Yes — real filesystem reads, not hardcoded | ✓ FLOWING |
| `evolve_tool_descriptions.py` FAILED path | `metrics_extra` | `persist_per_tool_rates(baseline_rates, evolved_rates)` computed from real holdout predictions | Yes — computed from actual model outputs | ✓ FLOWING |
| `evolve_tool_reasoning.py` | `raw_preds_on` | `_score_with_predictions` → per-example `joint_tool_param_metric` loop | Yes — joint metric applied per prediction | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| `--runs <fixture-dir>` resolves `<dir>/metrics.json` directly | CliRunner.invoke + DEFAULT_ROOTS=() + `--runs params_complete` | `scanned_runs: 1`, `latest.run_path` contains `params_complete` | ✓ PASS |
| `datetime.utcnow()` zero occurrences in non-comment lines | `grep -v '^[[:space:]]*#' regression_dashboard.py | grep -c 'datetime.utcnow()'` | `0` | ✓ PASS |
| Old raw comparison removed from `_score_with_predictions` | `grep -c 'total += 1.0 if correct == selected' evolve_tool_reasoning.py` | `0` | ✓ PASS |
| Full test suite | `.venv/bin/pytest tests/ -x -q` | 500 passed, 1 xfailed, 5 warnings | ✓ PASS |
| WR-04: persist before FAILED branch | `grep -nE 'metrics_extra = persist_per_tool_rates|if not regression_result.passed:' evolve_tool_descriptions.py` | line 374 < line 377 | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| TOOL-V2-04 | 16-00 through 16-05 (all 6 plans) | Per-tool regression guard with individual selection rate tracking dashboard | ✓ SATISFIED | All 6 observable truths verified. Dashboard renders with real per-tool data. `--runs <dir>` correctly resolves fixture data. FAILED description runs carry per-tool schema. ThinkABGate receives coherent metrics from both scoring paths. REQUIREMENTS.md still shows `Pending` — should be updated to `Complete` after this verification. |

No orphaned requirements — TOOL-V2-04 is the only ID mapped to Phase 16 and appears in all 6 plan frontmatters.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `regression_dashboard.py` | 690 | `_load_run` still called once per classification pass + potentially again in TREND/DIFF — WR-03 (deferred) | ℹ️ Info | Performance concern only; data correctness not affected. Explicitly deferred in 16-05-PLAN. |
| `tests/tools/test_regression_dashboard.py` | ~600 | `test_scan_runs_glob_and_explicit_combined` references `params_complete_v2` fixture which may not exist | ℹ️ Info | If fixture is absent, test would exit 0 with scanned_runs < 2 (assertion would fail). Needs spot-check. |

### Human Verification Required

None — all must-haves are programmatically verifiable and confirmed by grep + pytest.

### Gaps Summary

All 6 must-have truths are VERIFIED. The two BLOCKERs and one WARNING from the initial verification are closed:

**CR-01/CR-02 (closed):** `_scan_runs` now has a dual-input signature with a dedicated `explicit_runs` channel. The `main` function routes `--runs` values through `explicit_runs` instead of appending to glob roots. A smoke test confirms that `--runs tests/fixtures/dashboard_runs/params_complete` delivers `scanned_runs: 1` with `params_complete` in `latest.run_path`. The new `test_scan_runs_resolves_explicit_path` test exercises the real path resolution without patching `_scan_runs`, closing the test-masking gap identified in the initial verification.

**CR-03 (closed):** `_score_with_predictions` now calls `joint_tool_param_metric(ex, pred)` (0.5 normalized tool_match + 0.5 param_match) instead of the raw case-sensitive `correct == selected`. Both `th_*_full` (via `_score_with_predictions`) and `th_*_ambig` (via `_safe_score` → `_score_module_on_holdout` → `joint_tool_param_metric_with_feedback`) now use the same normalization family. `ThinkABGate.check()` receives coherent metrics. The `test_score_with_predictions_uses_joint_metric` test proves this directly: `Read_File` vs `read_file` scores 1.0 (not 0.0 as before).

**WR-04 (closed):** `evolve_tool_descriptions` now calls `persist_per_tool_rates` and `persist_raw_predictions` before the `if not regression_result.passed:` early return. The REGRESSION_FAILED branch spreads `**metrics_extra` into its `failed_metrics` dict. This reverses the 16-00-PLAN decision and aligns descriptions with the sibling `evolve_tool_params` pattern. The `test_regression_failed_metrics_carry_per_tool_rates` test drives the real `evolve()` function through the FAILED branch and asserts schema completeness.

Additional hygiene from 16-05: `datetime.utcnow()` replaced with `datetime.now(timezone.utc)` (WR-01); `--trend-days` cutoff unified to UTC (WR-02); `_render_diff` title guards against `None` source (WR-05); frequency bar counter filters empty strings (WR-06); per-example and batch-level exceptions in `_score_with_predictions` emit yellow log (WR-07); `_load_run` docstring aligned to code (IN-01); `json_corrupt` fixture covered by new test (IN-02).

The phase goal "Track individual tool selection rates across optimization runs" is now genuinely achieved end-to-end.

---

_Verified: 2026-05-15T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
