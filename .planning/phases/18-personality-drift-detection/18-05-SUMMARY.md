---
phase: 18-personality-drift-detection
plan: 05
subsystem: prompts
tags: [drift-detection, integration-tests, click-cli, regression-guard, d-out-02, d-bypass-01, d-bypass-02, d-gate-03, d-gate-04, d-rob-04]

requires:
  - phase: 18-personality-drift-detection
    plan: 04
    provides: "evolve_prompt_sections.py drift-gate wiring (step 8c DriftDetector + drift_* metrics + drift_report.txt + --drift-thresholds-path flag)"
provides:
  - "tests/prompts/test_evolve_prompt_sections_cli.py::TestDriftGate class with 6 integration tests"
  - "D-BYPASS-01 regression guard (test_no_skip_drift_flag) — locks the absence of --no-drift-check / --skip-drift-check into CI"
  - "D-ROB-04 regression guard (test_round_robin_metrics_json_has_drift_fields) — locks the 4-space indent of the drift_* metrics block; trips if a future refactor nests it inside the joint-only conditional"
affects: ["Phase 18 verify gate — fully covered"]

tech-stack:
  added: []
  patterns:
    - "Wave 4 multi-patch CLI integration test pattern: tmp_path stub thresholds file + DriftDetector mock returning caller-supplied drift_results + PromptModule spy factory + dspy mocks (LM/configure/context/GEPA) — mirrors TestABBaseline._ab_patched_run topology"
    - "Drift-result factory helper (TestDriftGate._make_drift_result) — builds Wave-1-shaped dicts with severity ladder derivation (0 exceeded → pass, 1 → warn, 2+ → reject) for legible test setup"

key-files:
  created: []
  modified:
    - "tests/prompts/test_evolve_prompt_sections_cli.py — appended class TestDriftGate (+526 LoC: _drift_run helper + _make_drift_result static + 6 test methods)"

key-decisions:
  - "Score sequence sizing differs per mode: joint mode runs 4 holdout × (baseline + evolved) interleaved + 4 A/B holdout sequential = 12 metric calls; round-robin runs only 4 × (baseline + evolved) = 8 metric calls (no A/B). The test_round_robin_metrics_json_has_drift_fields case uses an 8-element score sequence accordingly."
  - "PromptModule spy factory copies Plan 18-04's TestABBaseline pattern (real PromptModule wrapped in MagicMock + __call__ override returning dspy.Prediction) so holdout scoring is deterministic via metric.side_effect."
  - "DriftDetector mock returns caller-supplied drift_results list (one dict per section). Test author shapes severity via _make_drift_result's per_dim_overrides — keeps the test body focused on assertions, not setup."
  - "Click reject-flag assertion checks BOTH exit code != 0 AND error-text contains 'no such option' (or option name) — defends against future Click versions that might keep the error format but change the exit code, or vice versa."

duration: ~6 minutes
completed: 2026-05-16
status: complete
---

# Plan 18-05 Summary

**6 CLI integration tests added; Phase 18 verify gate fully covered. D-BYPASS-01 and D-ROB-04 regression guards locked into CI.**

## Performance

- **Duration:** ~6 minutes (single session)
- **Started:** 2026-05-16T09:30:00Z
- **Completed:** 2026-05-16T09:36:00Z
- **Tasks:** 1/1 (Task 1: append class TestDriftGate)
- **Files modified:** 1
- **LoC delta:** +526

## What Shipped

Single edit to `tests/prompts/test_evolve_prompt_sections_cli.py` — appended class `TestDriftGate` with one shared `_drift_run` helper, one `_make_drift_result` static factory, and 6 test methods. All 6 pass; full repo suite zero regression.

### Test Method Inventory

| # | Test method | Acceptance criterion | Mode | Assertion shape |
|---|-------------|---------------------|------|-----------------|
| 1 | `test_metrics_json_has_drift_fields` | D-OUT-02 | joint | metrics.json contains drift_per_dim/drift_thresholds/drift_passed/drift_exceeded_dims; per-dim per-section shape verified |
| 2 | `test_round_robin_metrics_json_has_drift_fields` | D-ROB-04 + D-OUT-02 | round-robin | Same 4 drift_* fields present; `mode == "round-robin"`; explicit D-ROB-04 REGRESSION error message if any field missing |
| 3 | `test_drift_thresholds_path_flag` | D-BYPASS-02 | joint | `metrics["drift_thresholds"]` equals custom file content verbatim |
| 4 | `test_no_skip_drift_flag` | D-BYPASS-01 | n/a (parse-time) | `--no-drift-check` and `--skip-drift-check` both fail with non-zero exit + "no such option" error |
| 5 | `test_one_dim_drift_warns_but_deploys` | D-GATE-03 | joint | exit 0, evolved_sections.json written, `drift_passed=true`, `drift_exceeded_dims` has 1 entry |
| 6 | `test_two_dim_drift_rejects_and_writes_failed_dir` | D-GATE-04 + D-OUT-03 | joint | Dir name starts `FAILED_`; drift_report.txt + evolved_sections.json + diff.txt present; markdown headers in report; `drift_passed=false`, ≥2 exceeded dims |

### ROADMAP Success Criteria → Test Mapping

| SC | Description | Test(s) covering it |
|----|-------------|---------------------|
| SC#1 | DriftDetector compares on 4 dims with 3-run averaging | Wave 1 unit tests (`tests/prompts/test_drift_detector.py`, 10 tests) |
| SC#2 | Constraint gate rejects when drift exceeds threshold on multiple dims | `test_two_dim_drift_rejects_and_writes_failed_dir` (D-GATE-04) |
| SC#3 | Drift report in optimization output | `test_metrics_json_has_drift_fields` + `test_round_robin_metrics_json_has_drift_fields` (drift_* metrics across both modes) + `test_two_dim_drift_rejects_and_writes_failed_dir` (drift_report.txt + markdown structure) |

## Regression Guards Locked Into CI

### D-BYPASS-01 (`test_no_skip_drift_flag`)

The test asserts that BOTH `--no-drift-check` AND `--skip-drift-check` are rejected by Click at parse time (`exit_code != 0`) AND the error output contains `"no such option"` (or `unrecognized` or the option name). Any PR that re-introduces a bypass flag fails with explicit message:

> "D-BYPASS-01 REGRESSION: --no-drift-check was accepted (exit 0). Phase 18 forbids bypass flags."

Lives in `tests/prompts/test_evolve_prompt_sections_cli.py::TestDriftGate::test_no_skip_drift_flag` (assertion at ~line in committed file). Exercised in every full `pytest tests/` run.

### D-ROB-04 (`test_round_robin_metrics_json_has_drift_fields`)

The test invokes the CLI with `--mode round-robin` and asserts the four drift_* fields are present in metrics.json. If any field is missing, the assertion message reads:

> "D-ROB-04 REGRESSION: round-robin metrics.json missing drift_per_dim. The drift_* assignment in evolve_prompt_sections.py is incorrectly nested inside `if effective_mode == \"joint\" ...`."

This is the executable lock on Plan 18-04 Edit-3's 4-space indent placement. If a future refactor moves the `if drift_results:` block from function-body indent (4 spaces) into the joint-only `if effective_mode == "joint" ...:` block (8 spaces), the round-robin path would silently skip the drift_* assignment and this test fires.

## Test Pass Counts

| Suite | Before Plan 18-05 | After Plan 18-05 | Delta |
|-------|-------------------|------------------|-------|
| `tests/prompts/test_evolve_prompt_sections_cli.py` | 19 passed | 25 passed | +6 |
| `tests/prompts/` (full) | 110 passed / 1 skipped | 116 passed / 1 skipped | +6 |
| Full repo `tests/` | 527 passed / 1 skipped / 1 xfailed | **533 passed / 1 skipped / 1 xfailed** | +6 |

Pre-Phase-18 baseline (from STATE.md "Test Coverage v2 baseline"): 353 tests. Phase 18 net added: 14 (Wave 0) + 13 turned green (Wave 1 implementation closed Wave 0 RED) — net +14 tests went from non-existent to GREEN through Waves 0-2 — then Wave 4 added +6 here. Final repo total: **533 passed + 1 skipped + 1 xfailed** (vs Wave 0 baseline of 514 passed; vs Wave 1 baseline of 527 passed). Math:

- 514 (pre-Phase-18) → 514 (Wave 0 added 14 tests in RED state but pytest reports them as failed/skipped, not passed) → 527 (Wave 1 turned 13 RED tests GREEN, +13) → 527 (Wave 2 same baseline, no new tests added) → 527 (Wave 3 same baseline, the 3 TestABBaseline tests were fixed by the Rule-3 compatibility patch) → **533 (Wave 4 added 6 tests, all PASS)**.

## Task Commits

1. **Task 1: Append TestDriftGate class with 6 integration tests** — `b04b108` (test)

## Files Touched

| File | Lines changed | Purpose |
|------|---------------|---------|
| `tests/prompts/test_evolve_prompt_sections_cli.py` | +526 / 0 | Append class TestDriftGate + helpers + 6 tests |

## Decisions Made

- **Mode-specific score sequence sizing:** joint mode runs 4 holdout × (baseline + evolved) interleaved + 4 A/B holdout sequential = 12 calls; round-robin runs only 4 × (baseline + evolved) = 8 calls. The two metrics tests use different scores list lengths accordingly.
- **DriftDetector mocked, not constructed:** The test patches the import-site DriftDetector class to a MagicMock; this is the minimum viable mock — DriftDetector's real `__init__` would fail to construct a real `dspy.LM` under the test mocks. The mock's `check_all` returns caller-supplied result dicts, so tests focus on integration plumbing (does the metrics block see and serialize the data?), not on DriftDetector's internals (covered by Wave 1 unit tests).
- **`pathlib.Path.read_text` NOT patched** (despite plan-template suggestion): we instead write a real thresholds file to `tmp_path` and pass its path via `--drift-thresholds-path`. This satisfies `click.Path(exists=True)` AND lets us assert real file content propagates to `metrics["drift_thresholds"]` (D-BYPASS-02 verbatim test).
- **PromptModule spy factory:** copied from TestABBaseline._ab_patched_run pattern verbatim (BLOCKER-2 fix). Real PromptModule wrapped in MagicMock with `__call__` returning `dspy.Prediction(output="mocked output")` keeps holdout scoring deterministic via metric.side_effect.

## Deviations from Plan

### Minor adjustments to plan template (not deviations from acceptance criteria)

**1. [Adherence note — not a Rule deviation] Plan template's `pathlib.Path.read_text` patch was unnecessary**

- **Plan template** (`<action>` block, line ~129): suggested patching `pathlib.Path.read_text` to stub thresholds file reads.
- **Decision:** Did not patch read_text. Instead, the helper writes a real thresholds file to `tmp_path / "test_drift_thresholds.json"` and passes its path via `--drift-thresholds-path`. This:
  1. Satisfies `click.Path(exists=True)` validator naturally (real file exists),
  2. Lets `test_drift_thresholds_path_flag` assert verbatim file content propagation to `metrics["drift_thresholds"]` (which is what D-BYPASS-02 actually requires),
  3. Avoids fragile global Path.read_text patching that could affect unrelated reads (Click's own option handling, drift_report.txt assertions).
- The plan's `<done>` criteria are still 100% met — all 6 tests with the exact names listed pass.

**2. [Adherence note] Score sequence size for round-robin test**

- **Plan template** `test_round_robin_metrics_json_has_drift_fields` used `scores = [0.5, 0.8] * 4 + [0.75] * 4` (12 elements).
- **Decision:** Used `scores = [0.5, 0.8] * 4` (8 elements) because round-robin has no A/B baseline phase, so only 8 metric calls fire (4 holdout × interleaved baseline+evolved). Using 12 elements would not have caused test failure (MagicMock side_effect tolerates surplus), but matching the actual call count makes the test more faithful to the real flow.

### Architectural changes

None — single test-only addition, no production code touched.

## Authentication Gates

None encountered. All mocks; no LLM calls; no API keys touched.

## Threat Flags

No new threat surface introduced. The plan's threat model items are now mechanically enforced:

| Threat ID | Mitigation | Live evidence |
|-----------|-----------|---------------|
| T-18-05 (Elevation via bypass flag) | `test_no_skip_drift_flag` runs in CI | Test in committed file b04b108 |
| T-18-W4-01 (Tampering on thresholds file) | `test_drift_thresholds_path_flag` runs in CI | Asserts file → metrics.json verbatim propagation |
| T-18-W4-02 (Tampering: drift_* omission in round-robin) | `test_round_robin_metrics_json_has_drift_fields` runs in CI | Explicit error message names the root cause if it fires |

## Known Stubs

None. No stub code, no placeholder text. Test-only changes.

## Remaining Manual Verifications

Per VALIDATION.md §Manual-Only Verifications: the human spot-check from Wave 2 (10/10 review of `datasets/prompts/drift_calibration.jsonl`) was a one-shot Phase 18 sign-off, not recurring. Plan 18-05 introduces no new manual verification requirements — the verify gate is now fully automated via the 6 new tests + the 13 Wave 1 unit tests + the Wave 3 integration tests covered by TestABBaseline.

Optional future spot-check (NOT required for Phase 18 closure): re-running `python -m evolution.prompts.build_drift_calibration --reuse-jsonl --eval-model <stronger-judge>` if/when a stronger judge becomes accessible. Documented in 18-03-SUMMARY.md "Resume protocol for re-tightening".

## Self-Check: PASSED

Verified items:

- [x] `tests/prompts/test_evolve_prompt_sections_cli.py` contains `class TestDriftGate:` (grep confirmed).
- [x] Exactly 6 test methods named: `test_metrics_json_has_drift_fields`, `test_round_robin_metrics_json_has_drift_fields`, `test_drift_thresholds_path_flag`, `test_no_skip_drift_flag`, `test_one_dim_drift_warns_but_deploys`, `test_two_dim_drift_rejects_and_writes_failed_dir`.
- [x] Helper `_drift_run` and static `_make_drift_result` present in TestDriftGate.
- [x] `pytest tests/prompts/test_evolve_prompt_sections_cli.py::TestDriftGate -v` returns 6 passed in 0.44s.
- [x] `pytest tests/prompts/ -q` returns 116 passed, 1 skipped (baseline 110+6).
- [x] `pytest tests/ -q` returns 533 passed, 1 skipped, 1 xfailed (baseline 527+6).
- [x] Commit `b04b108` exists in git log.
- [x] No `--no-drift-check` / `--skip-drift-check` flag exists in `evolve_prompt_sections.py` (Plan 18-04 already enforced this; `test_no_skip_drift_flag` is the executable lock).
- [x] D-ROB-04 regression guard wired (`test_round_robin_metrics_json_has_drift_fields` runs --mode round-robin and asserts drift_* fields present).
- [x] D-BYPASS-01 regression guard wired (`test_no_skip_drift_flag` asserts exit_code != 0 for both bypass flag variants).

---
*Phase: 18-personality-drift-detection*
*Plan: 05 (Wave 4 — CLI integration tests)*
*Status: complete*
*Updated: 2026-05-16*
