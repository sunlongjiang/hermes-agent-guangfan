---
phase: "16"
plan: "16-05"
subsystem: tools
tags: [gap-closure, regression-dashboard, metric-consistency, persist-order, datetime-utc, cr-01, cr-02, cr-03, wr-04, wr-07]
dependency_graph:
  requires: [16-04-schema-e2e]
  provides: [TOOL-V2-04-complete]
  affects: [evolution/tools/regression_dashboard.py, evolution/tools/evolve_tool_reasoning.py, evolution/tools/evolve_tool_descriptions.py]
tech_stack:
  added: []
  patterns: [explicit-path-channel, joint-metric-consistency, persist-before-branch]
key_files:
  created: []
  modified:
    - evolution/tools/regression_dashboard.py
    - evolution/tools/evolve_tool_reasoning.py
    - evolution/tools/evolve_tool_descriptions.py
    - tests/tools/test_regression_dashboard.py
    - tests/tools/test_evolve_tool_reasoning.py
    - tests/tools/test_evolve_tool_descriptions.py
decisions:
  - "WR-04 reversed: 16-00-PLAN decision to skip metrics_extra in FAILED branch inverted; REGRESSION_FAILED runs now carry per_tool_*_rates + raw_predictions before the early return"
  - "CR-03 fix: _score_with_predictions adopts joint_tool_param_metric (0.5 tool + 0.5 param, normalized) to match _safe_score → _score_module_on_holdout; ThinkABGate gate coherence restored"
  - "CR-01/CR-02 fix: _scan_runs dual-input signature adds explicit_runs channel; --runs values treated as run directories not glob roots"
  - "IN-01 fix: _load_run docstring aligned to code (never returns None; returns dict with metrics=None on parse error)"
metrics:
  duration_minutes: ~50
  completed: "2026-05-15"
  tasks_completed: 2
  tasks_total: 2
  files_changed: 6
  tests_added: 7
  tests_total_after: 499
---

# Phase 16 Plan 05: Gap Closure SUMMARY

**One-liner:** Phase 16 gap closure closing 3 BLOCKERs (CR-01/02/03) + 1 WARNING (WR-04) + 7 hygiene items via `_scan_runs` dual-input, `joint_tool_param_metric` adoption, and FAILED-branch persist order reversal.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | dashboard CLI semantics + datetime/UTC hygiene | 3131e20 | regression_dashboard.py, test_regression_dashboard.py |
| 2 | reasoning metric consistency + descriptions FAILED persist order | beec2c3 | evolve_tool_reasoning.py, evolve_tool_descriptions.py, test_evolve_tool_reasoning.py, test_evolve_tool_descriptions.py |

## Closed Gaps

### BLOCKER (3 closed)

**CR-01 / CR-02 — `--runs` glob-root vs run-directory semantics**
- `_scan_runs` given dual-input signature: `(roots, explicit_runs=())`. Roots are globbed for `*/metrics.json`; explicit_runs resolve `<dir>/metrics.json` directly.
- `main()` now routes `--runs` values to `explicit_runs` channel instead of appending to roots.
- Matches `--baseline-run` / `--evolved-run` semantics (both accept run directories).
- Smoke test confirmed: `--runs tests/fixtures/dashboard_runs/params_complete` contributes 1 run; fixture data present in `latest.run_path`.

**CR-03 — `_score_with_predictions` metric incoherence**
- Replaced `total += 1.0 if correct == selected else 0.0` (raw case-sensitive tool-only) with `joint_tool_param_metric(ex, pred)` (0.5 tool_match normalized + 0.5 param_match).
- Both `th_*_full` (via `_score_with_predictions`) and `th_*_ambig` (via `_safe_score`) now use the same metric in `ThinkABGate.check()`.
- Import of `joint_tool_param_metric` added to `evolve_tool_reasoning.py`.

### WARNING (1 closed)

**WR-04 — REGRESSION_FAILED metrics.json missing per-tool data (16-00-PLAN decision reversed)**
- Moved `persist_per_tool_rates` + `persist_raw_predictions` calls to **before** `if not regression_result.passed:` early return.
- Added `**metrics_extra` spread into the FAILED branch metrics dict literal.
- Decision rationale: `evolve_tool_params.py:1018-1029` sibling already uses correct pattern; regressed description runs are exactly the runs the dashboard exists to surface; 16-00-PLAN Out-of-scope §6 refers to historical runs (not future ones).
- Historical FAILED runs NOT backfilled (Out-of-scope §6 still holds).

### Hygiene (7 closed)

**WR-01 — `datetime.utcnow()` deprecated**
- Replaced with `datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")`.
- Import updated: `from datetime import datetime, timezone`.
- Zero DeprecationWarnings on import confirmed.

**WR-02 — `--trend-days` cutoff used local time**
- Changed `datetime.now().timestamp()` to `datetime.now(timezone.utc).timestamp()`.
- `stat().st_mtime` is epoch UTC; cutoff now consistent.

**WR-05 — `_render_diff` title `None vs None`**
- Added `b_src = baseline_run["source"] or "?"` and `e_src = evolved_run["source"] or "?"` guards before table title.

**WR-06 — `_render_frequency_bars` empty-string ghost bar**
- Filtered empty strings in Counter construction: `Counter(tool for tool in (...) if tool)`.

**WR-07 — `_score_with_predictions` silent exception swallowing**
- Per-example exception: now logs `[yellow]holdout example skipped due to LM error: {type}: {e}[/yellow]`.
- Batch-level exception: now logs partial result info instead of silently returning 0.0; returns accumulated partial score.

**IN-01 — `_load_run` docstring vs code mismatch**
- Updated docstring to state "Never returns None; returns dict with metrics=None on parse error".
- Changed return type annotation from `Optional[dict]` to `dict`.
- Fixed `str(metrics_path)` to `str(metrics_path.parent)` in parse error return so `dropped_runs[*].path` uses run directory convention.

**IN-02 — `json_corrupt` fixture unreferenced**
- New test `test_json_corrupt_fixture_drops_with_reason` exercises the fixture.
- Asserts `dropped_runs` contains an entry with `"json_corrupt"` in path and `"json parse error"` in reason.

## Deviations from Plan

None — plan executed exactly as written.

## Reversed Decision (documented)

**16-00-PLAN decision "不在 FAILED 分支注入 metrics_extra" (Out-of-scope §6) — REVERSED for WR-04**

Original justification: avoid back-filling historical FAILED_<old_ts>/ runs.

Reversal rationale (per 16-05-PLAN.md objective):
1. `evolve_tool_params.py:1018-1029` already uses the correct pattern (persist before FAILED branch) — descriptions was the outlier.
2. REGRESSION_FAILED runs are the primary use case for the dashboard; hiding their per-tool data defeats the phase goal.
3. Out-of-scope §6 refers to **historical** runs not being backfilled — this decision only affects future runs and does not conflict.

The historical runs remain unaffected.

## Metric Choice (CR-03)

`_score_with_predictions` now uses `joint_tool_param_metric`:
- **Why**: `_safe_score → _score_module_on_holdout` already uses `joint_tool_param_metric_with_feedback` (same normalization); using a different metric in `_score_with_predictions` caused `ThinkABGate.check()` to compare apples-vs-oranges.
- **Alignment**: `evolve_tool_params._evaluate_holdout` also uses `joint_tool_param_metric`-based scoring.
- **Effect**: tool name comparison is now case-insensitive (`.strip().lower()`); score is 0.5 tool_match + 0.5 param_match instead of raw boolean.

## Test Coverage Delta

| Test | File | Purpose |
|------|------|---------|
| `test_scan_runs_resolves_explicit_path` (G1) | test_regression_dashboard.py | CR-01/CR-02: does NOT patch `_scan_runs`, real glob/explicit path end-to-end |
| `test_scan_runs_glob_and_explicit_combined` (G2) | test_regression_dashboard.py | CR-01: glob roots + explicit --runs both contribute |
| `test_json_corrupt_fixture_drops_with_reason` (G3) | test_regression_dashboard.py | IN-02: json_corrupt fixture covered |
| `test_dashboard_json_no_datetime_deprecation_warning` (G4) | test_regression_dashboard.py | WR-01: no utcnow DeprecationWarning |
| `test_score_with_predictions_uses_joint_metric` (G5) | test_evolve_tool_reasoning.py | CR-03: joint_tool_param_metric, case-insensitive |
| `test_score_with_predictions_logs_per_example_error` (G6) | test_evolve_tool_reasoning.py | WR-07: yellow per-example log |
| `test_regression_failed_metrics_carry_per_tool_rates` (G7) | test_evolve_tool_descriptions.py | WR-04: FAILED branch schema completeness, drives real evolve() holdout |

**Total: 7 new tests** (4 dashboard + 2 reasoning + 1 descriptions).

## Known Stubs

None — all wired data paths complete.

## Deferred Items

Per 16-05-PLAN.md explicit deferred list:
- **WR-03** (`_load_run` called 2-3× per path — performance, low impact)
- **IN-03** (test comment delta=-5pp vs -10pp — cosmetic)
- **IN-04 / IN-05 / IN-06** (other cosmetic / cross-phase refactoring)

## Self-Check

**Created files:**
- [ ] `.planning/phases/16-per-tool-regression-dashboard/16-05-SUMMARY.md` — this file

**Commits exist:**
- Task 1: `3131e20` — dashboard CLI semantics + datetime/UTC hygiene
- Task 2: `beec2c3` — reasoning metric consistency + descriptions FAILED persist order

**Test results:**
- `pytest tests/tools/test_regression_dashboard.py` — 21 passed
- `pytest tests/tools/test_evolve_tool_reasoning.py` — 14 passed
- `pytest tests/tools/test_evolve_tool_descriptions.py` — 6 passed
- `pytest tests/` — 499 passed, 1 skipped, 1 xfailed

## Self-Check: PASSED
