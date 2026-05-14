---
phase: 16-per-tool-regression-dashboard
verified: 2026-05-14T00:00:00Z
status: gaps_found
score: 4/6 must-haves verified
overrides_applied: 0
gaps:
  - truth: "--runs <dir> CLI flag locates the run the user points at (TOOL-V2-04: track tool selection rates across optimization runs)"
    status: failed
    reason: >-
      _scan_runs treats every --runs value as a glob ROOT (root.glob('*/metrics.json')),
      but the docstring and --help both document --runs as a run DIRECTORY containing
      metrics.json directly. Smoke test confirmed: `--runs tests/fixtures/dashboard_runs/params_complete`
      contributed ZERO runs (params_complete/*/metrics.json matches nothing) and the dashboard
      silently rendered 27 unrelated runs from the default output/tools_reasoning/ root instead.
      Every test patches _scan_runs(return_value=[...]) so the real glob is never exercised —
      the 17 passing dashboard tests fully mask this defect. A user cannot target a specific
      run, which is the core "track across optimization runs" capability.
    artifacts:
      - path: evolution/tools/regression_dashboard.py
        issue: "_scan_runs (line 54-60) globs */metrics.json one level below --runs values; main (line 624-627) appends --runs to roots. --baseline-run (line 675-676) reads <dir>/metrics.json directly — two incompatible path semantics for the same conceptual input."
    missing:
      - "Unify --runs and --baseline-run path semantics: both accept a run directory and resolve <dir>/metrics.json"
      - "Add a test that does NOT patch _scan_runs so the glob / explicit-path resolution is actually covered"
  - truth: "evolve_tool_reasoning metrics.json records coherent per-tool accuracy before and after optimization (ROADMAP SC1) without corrupting the existing A/B gate"
    status: failed
    reason: >-
      Phase 16 replaced the th_off_full/th_on_full scoring calls with _score_with_predictions,
      which scores via raw case-sensitive `correct == selected` tool-only match (line 670).
      But th_off_ambig/th_on_ambig still come from _safe_score -> _score_module_on_holdout ->
      joint_tool_param_metric, which is normalized (strip().lower()) and a 0.5 tool + 0.5 param
      composite. Both metric pairs feed the SAME ThinkABGate.check() (line 489-500). The
      full-regression sub-gate now compares metric A while the ambiguous-improvement sub-gate
      compares metric B — an incoherent apples-vs-oranges gate. Pre-Phase-16 code used _safe_score
      for th_*_full too, so this is a regression introduced by this phase's wiring change.
    artifacts:
      - path: evolution/tools/evolve_tool_reasoning.py
        issue: "_score_with_predictions (line ~660-680) uses raw `total += 1.0 if correct == selected` instead of the normalized joint_tool_param_metric used everywhere else; th_*_full (line 470-471) and th_*_ambig (line 472-473) now use different metrics but are gated together (line 489-500)."
    missing:
      - "Make _score_with_predictions compute its score with the same metric as the rest of the pipeline (joint_tool_param_metric, or at minimum normalize correct/selected with .strip().lower())"
      - "Confirm with Phase 15 gate authors which metric is contractually correct for th_*_full and apply it consistently to both full and ambiguous scores"
deferred: []
---

# Phase 16: Per-Tool Regression Dashboard Verification Report

**Phase Goal:** Track individual tool selection rates across optimization runs
**Verified:** 2026-05-14T00:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1   | Metrics file records per-tool accuracy before and after optimization (ROADMAP SC1) | ⚠️ PARTIAL → counted FAILED via truth #6 | `persist_per_tool_rates` + `persist_raw_predictions` wired into all 3 CLIs: `evolve_tool_params.py:1018,1029`, `evolve_tool_descriptions.py:405-406`, `evolve_tool_reasoning.py:566-567`. params writes per_tool data BEFORE its FAILED branch (correct). BUT descriptions writes them AFTER the `if not regression_result.passed: return` early-return (line 368-381 vs 405-406) — regressed desc runs write metrics.json with NO per-tool data, so the dashboard drops the exact runs it exists to surface (WR-04). reasoning records data but via an incoherent metric (truth #6). |
| 2   | Rich console dashboard shows selection rate changes per tool (ROADMAP SC2) | ✓ VERIFIED | `regression_dashboard.py` renders LATEST (12-col table, line 192-274), DIFF (line 314-364), TREND (sparkline + quintiles, line 367-431), ABStudy (line 489-542). Smoke test against real `output/tools_reasoning/` rendered all regions, exit 0. |
| 3   | Regression threshold configurable, default 2pp drop triggers warning (ROADMAP SC3) | ✓ VERIFIED | `--warning-threshold-pp` default 2.0 (line 601-602); `_status_style` WARN at `delta <= -warning_threshold_pp` (line 118); main emits `WARNING:` yellow line per regressed tool (line 746-749); does not affect exit code (line 783-784). `test_warning_threshold_no_exit` dual-case guard passes. |
| 4   | Standalone read-only CLI; default-scans output/tools[_reasoning]/, --runs additive (16-01 must_have) | ✗ FAILED | CLI exists and is Click-based, default roots correct. BUT `--runs` is broken: it is treated as a glob root, not a run directory (CR-01). Smoke test: `--runs <fixture-dir>` contributed 0 runs, dashboard silently used default roots instead. |
| 5   | dashboard.json emits 8 top-level fields, default `dashboard_<ts>.json`, --output overrides (16-04 must_have) | ✓ VERIFIED | `_write_dashboard_json` (line 545-581) writes latest/diff/trend/ab_study/source_legend/dropped_runs/summary/warnings + generated_at/scanned_runs. `test_e2e_dashboard_json_schema`, `test_dashboard_json_output_path` pass. Smoke-test JSON confirmed all keys present. |
| 6   | evolve_tool_reasoning records coherent per-tool data without corrupting the A/B gate (16-00 must_have + ROADMAP SC1) | ✗ FAILED | `_score_with_predictions` uses raw case-sensitive tool-only match (`correct == selected`); `_safe_score` path uses normalized joint tool+param composite. Both feed the same `ThinkABGate.check()` → incoherent gate (CR-03). Regression introduced by Phase 16. |

**Score:** 4/6 truths verified (truths 1 and 6 overlap on the reasoning metric defect; 2 distinct FAILED gaps reported)

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `evolution/tools/regression_dashboard.py` | Dashboard CLI, 15 helpers + main, ~250-788 LoC | ⚠️ ORPHANED at `--runs` boundary | 789 lines, all 15 helpers present, imports cleanly. Substantive and mostly wired, but `--runs` flag is functionally disconnected from its documented contract (CR-01/CR-02). |
| `evolution/tools/tool_metric.py:persist_raw_predictions` | Immutable helper, signature `(metrics, raw_predictions) -> dict`, size warning | ✓ VERIFIED | Defined line 483, size-warning string line 518, `test_persist_raw_predictions.py` 4 tests pass. |
| `evolution/tools/tool_dataset.py:to_dspy_examples` | Carries `difficulty` field | ✓ VERIFIED | `difficulty=ex.difficulty` line 156, docstring updated line 141, `TestToDspyExamplesDifficulty` passes. |
| `evolution/tools/evolve_tool_params.py` | metrics.json gains per_tool_*_rates + raw_predictions | ✓ VERIFIED | Wired line 1018 + 1021-1029, BEFORE the REGRESSION_FAILED branch — regressed params runs DO carry per-tool data. |
| `evolution/tools/evolve_tool_descriptions.py` | metrics.json gains per_tool_*_rates + raw_predictions | ⚠️ HOLLOW for FAILED runs | Wired line 405-406, but AFTER the `if not regression_result.passed: return` at line 368-381 — regressed runs (the dashboard's primary use case) write metrics.json without per-tool data (WR-04). |
| `evolution/tools/evolve_tool_reasoning.py` | metrics.json gains per_tool_*_rates + raw_predictions via _score_with_predictions | ✗ STUB-QUALITY | Data is recorded (line 566-567) but `_score_with_predictions` uses a different (raw, case-sensitive, tool-only) metric than the rest of the pipeline, corrupting the A/B gate (CR-03). |
| `tests/tools/test_regression_dashboard.py` | 17 functional tests | ✓ VERIFIED (but masks CR-01) | 17 active tests, 0 skipped, all pass. Every test patches `_scan_runs`, so the real glob path is never exercised — this is why CR-01 escaped. |
| `tests/fixtures/dashboard_runs/` | 9-11 fixture files | ✓ VERIFIED | 11 files present (9 metrics.json + 2 ab_comparison.json). `json_corrupt/` fixture exists but is unreferenced by any test (IN-02). |
| `.gitignore` | `dashboard_*.json` entry | ✓ VERIFIED | Line 29 `dashboard_*.json`. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | --- | --- | ------ | ------- |
| `evolve_tool_params.py` | `tool_metric.persist_raw_predictions` | import + call after persist_per_tool_rates | ✓ WIRED | import line 76, call line 1029, before FAILED branch |
| `evolve_tool_descriptions.py` | `tool_metric.persist_per_tool_rates+persist_raw_predictions` | import + 2 calls before metrics.json write | ⚠️ PARTIAL | imports line 31-32, calls line 405-406 — but AFTER FAILED-branch early return; happy-path only |
| `evolve_tool_reasoning.py` | `_score_with_predictions` | new helper + 2 calls before metrics.json write | ⚠️ WIRED-BUT-INCOHERENT | helper present, calls line 470-471 + persist line 566-567, but metric mismatch poisons ThinkABGate |
| `regression_dashboard.py` | `tests/fixtures/dashboard_runs/` | `_scan_runs` glob + CliRunner patch | ⚠️ TEST-ONLY | Wired only because tests patch `_scan_runs`; real `--runs` glob does not resolve fixture dirs (CR-01) |
| `test_regression_dashboard.py` | `regression_dashboard.main` | `CliRunner.invoke` | ✓ WIRED | 17 invoke sites, all pass |
| `regression_dashboard.py` | `external_importers._contains_secret` | import + `_safe_truncate` | ✓ WIRED | import line 36, used in `_safe_truncate` line 443 |
| `regression_dashboard.py` | `dashboard.json` (filesystem) | `json.dumps` + `write_text` | ✓ WIRED | `_write_dashboard_json` line 578-580 |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Dashboard runs end-to-end, exit 0 | `python -m evolution.tools.regression_dashboard --runs <fixture> --output /tmp/v.json` | exit 0, all regions rendered | ✓ PASS |
| `--runs <fixture-dir>` targets that run | same command, inspect `dashboard.json` `scanned_runs` / `latest.run_path` | `scanned_runs: 27`, `latest.run_path: output/tools_reasoning/20260514_162120` — fixture data ABSENT, default roots used instead | ✗ FAIL (CR-01) |
| dashboard.json has 8 top-level fields | `json.load` + key check | all 8 + generated_at + scanned_runs present | ✓ PASS |
| Full test suite passes | `.venv/bin/pytest tests/` | 493 passed, 1 xfailed | ✓ PASS |
| evolve_tool CLI tests pass | `pytest tests/tools/test_evolve_tool_*` | 20 passed | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| TOOL-V2-04 | 16-00, 16-01, 16-02, 16-03, 16-04 (all 5 plans) | Per-tool regression guard with individual selection rate tracking dashboard | ✗ BLOCKED | Dashboard renders and dashboard.json schema is complete (SC2, SC3 met), but the "track individual tool selection rates across optimization runs" core capability is undermined: (a) `--runs` cannot target a specific run (CR-01), (b) regressed evolve_tool_descriptions runs are invisible to the dashboard (WR-04), (c) evolve_tool_reasoning records data via an incoherent metric that corrupts its own A/B gate (CR-03). REQUIREMENTS.md line 141 still marks TOOL-V2-04 as Pending. |

No orphaned requirements — TOOL-V2-04 is the only ID mapped to Phase 16 and it appears in all 5 plan frontmatters.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `regression_dashboard.py` | 54-60, 624-627 | `--runs` glob-root vs documented run-dir semantics | 🛑 Blocker | User cannot target a run; silently wrong output |
| `evolve_tool_reasoning.py` | ~660-680 | `_score_with_predictions` uses a different metric than the rest of the pipeline | 🛑 Blocker | Incoherent ThinkABGate; pass/fail decisions unreliable |
| `evolve_tool_descriptions.py` | 405-406 after 368-381 | persist calls after FAILED-branch early return | ⚠️ Warning | Regressed desc runs invisible to dashboard (the exact case the dashboard exists for) |
| `regression_dashboard.py` | 563 | `datetime.utcnow()` deprecated, emits DeprecationWarning on every run | ⚠️ Warning | Confirmed: 17 DeprecationWarnings in test run; CLAUDE.md pins Python 3.13 |
| `regression_dashboard.py` | 691-698, 675-676 | `_load_run` called 2-3× per path (classification, TREND, DIFF passes) | ⚠️ Warning | Redundant disk reads; TOCTOU risk; re-parses known-bad json_corrupt |
| `regression_dashboard.py` | 642, 645 | `loaded is None` branches are dead code (`_load_run` never returns None) | ℹ️ Info | Docstring contradicts code |
| `tests/fixtures/dashboard_runs/json_corrupt/` | — | Fixture added but never referenced by any test | ℹ️ Info | JSON-parse-error drop path has no functional coverage |
| `test_regression_dashboard.py` | 51-53, 74, 367 | Comments say `browser_navigate delta=-5pp`, fixture is actually `-10pp` | ℹ️ Info | Misleading comments; assertions still pass |

### Human Verification Required

None — all gaps are observable programmatically.

### Gaps Summary

Phase 16 delivered a working, well-structured dashboard CLI with a complete dashboard.json
schema, and ROADMAP success criteria 2 (Rich console dashboard) and 3 (configurable
threshold) are genuinely met. The full test suite (493 passed) is green and the dashboard
runs end-to-end on real data.

However, goal-backward verification surfaces two BLOCKER-level gaps that prevent the phase
goal — "track individual tool selection rates across optimization runs" — from being
genuinely achieved:

1. **`--runs` flag is functionally broken (CR-01/CR-02).** It is implemented as a glob root
   but documented as a run directory. A user pointing `--runs` at a real run directory gets
   zero runs from that flag and silently falls back to the default roots. This was directly
   reproduced: `--runs <fixture-dir>` produced `scanned_runs: 27` from `output/tools_reasoning/`
   with the fixture's data entirely absent. The 17 passing dashboard tests all patch
   `_scan_runs`, so the test suite provides false confidence here — high task-completion,
   missed goal. The flag is the primary mechanism for "tracking across runs" the user chooses.

2. **`evolve_tool_reasoning` mixes two metrics into one A/B gate (CR-03).** Phase 16's wiring
   change made `_score_with_predictions` score with a raw case-sensitive tool-only comparison,
   while the ambiguous-subset path still uses the normalized joint tool+param composite. Both
   feed the same `ThinkABGate.check()`. The "metrics file records per-tool accuracy" criterion
   (SC1) is technically satisfied for reasoning runs, but the data is produced by a metric that
   silently corrupts the gate it shares — a regression introduced by this phase.

A closely-related WARNING (WR-04): `evolve_tool_descriptions` persists per-tool data only on
the happy path, after the regression-FAILED early return — so regressed description runs,
which are exactly what a regression dashboard exists to surface, are dropped by `_load_run`
for "missing per_tool_*_rates". This was a planned decision in 16-00-PLAN ("不在 FAILED 分支
注入 metrics_extra") but it directly undercuts the phase goal and contradicts the
`evolve_tool_params` sibling which correctly persists before its FAILED branch. Recommend
revisiting as part of closing gap #1's planning.

These three issues match the 3 BLOCKERs independently flagged in 16-REVIEW.md (CR-01, CR-02,
CR-03) plus WR-04. The phase should not proceed to Phase 17 until at minimum CR-01 and CR-03
are closed.

---

_Verified: 2026-05-14T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
