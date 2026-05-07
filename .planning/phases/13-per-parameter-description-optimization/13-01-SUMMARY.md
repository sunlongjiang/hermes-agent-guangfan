---
phase: 13
plan: "01"
subsystem: tools
tags: [tdd, wave-0, test-scaffold, dataset-inspection]
dependency_graph:
  requires: []
  provides:
    - Wave 0 failing test stubs for all downstream Phase 13 plans (9 files, 23 tests)
    - mock_lm_with_usage fixture in tests/conftest.py
    - correct_params value-type distribution evidence (NORMALIZATION_RULE=strip_plus_coerce)
  affects:
    - 13-02-PLAN (ToolModule per-param sub-Module): test_tool_module_per_param.py pins D-01/D-02/D-03
    - 13-03-PLAN (joint_tool_param_metric): test_joint_metric.py pins D-10/D-17 + B2 feedback contract
    - 13-04-PLAN (ParamConsistencyChecker): test_param_consistency.py pins D-11
    - 13-05-PLAN (CostTracker): test_cost_tracker.py pins D-13 + W4/W5 scaffold
    - 13-06-PLAN (per-tool persistence): test_cross_tool_regression.py pins D-12
    - 13-07-PLAN (v1 baseline gate): test_v1_baseline_gate.py pins D-14
    - 13-08-PLAN (evolve_tool_params CLI): test_evolve_tool_params_cli.py pins D-15a/W2
    - 13-03-PLAN normalization rule: NORMALIZATION_RULE=strip_plus_coerce (6 types) mandates strip+coerce
tech_stack:
  added: []
  patterns:
    - pytest.importorskip guard for not-yet-implemented symbols (RED test pattern)
    - xfail scaffold for deferred W5 honest-gap documentation
    - B2 attribute-access guard: ret.score / ret.feedback (not dict-key)
key_files:
  created:
    - tests/conftest.py
    - tests/tools/test_tool_module_per_param.py
    - tests/tools/test_tool_selection_with_params.py
    - tests/tools/test_joint_metric.py
    - tests/tools/test_param_consistency.py
    - tests/core/test_cost_tracker.py
    - tests/tools/test_cross_tool_regression.py
    - tests/tools/test_v1_baseline_gate.py
    - tests/tools/test_evolve_tool_params_cli.py
    - tests/tools/test_param_size_gate.py
    - scripts/__init__.py
    - scripts/inspect_correct_params_types.py
    - .planning/phases/13-per-parameter-description-optimization/13-correct-params-type-inspection.txt
  modified: []
decisions:
  - "NORMALIZATION_RULE=strip_plus_coerce: dataset has 6 value types (str/int/bool/list/dict/float); str dominates (363/433 = 84%) but int(26)/bool(15)/list(19)/dict(7)/float(3) presence requires coerce. 13-03 must implement strip+numeric/type coerce for param_match."
  - "test_feedback_metric_shape uses dspy.Prediction attribute syntax (.score/.feedback) as B2 guard — stub only passes when 13-03 returns dspy.Prediction (not plain dict or namedtuple)"
  - "test_param_size_gate.py is GREEN at Wave 0 (exercises existing _check_size branch in constraints.py:101-102) — serves as SC3 regression test and traceability hook to B3 requirement"
  - "test_cost_tracker.py::test_poll_side_empty_usage_warning marked @pytest.mark.xfail(strict=False) as W5 honest-gap scaffold — auto-converts to XPASS if 13-05 implements poll-side guard"
metrics:
  duration_minutes: 25
  completed_date: "2026-05-07"
  tasks_completed: 3
  tasks_total: 3
  files_created: 13
  files_modified: 0
---

# Phase 13 Plan 01: Wave 0 Test Scaffold + Dataset Inspection Summary

**One-liner:** Wave 0 failing test stubs (23 tests across 9 files) + `mock_lm_with_usage` fixture + NORMALIZATION_RULE=strip_plus_coerce evidence from dataset type inspection.

## What Was Built

### Task 1: Wave 0 Test Package Scaffolding + Shared Fixture
- `tests/conftest.py`: `mock_lm_with_usage` factory fixture providing mock dspy.LM objects with `_usage_records` for cost_tracker downstream tests
- `tests/core/__init__.py`: already existed as 0-byte package marker (no action needed)

### Task 2: 9 RED Test Files (Wave 0 Scaffolding)

| File | Tests | Target Plan | Key Contract |
|------|-------|-------------|--------------|
| `tests/tools/test_tool_module_per_param.py` | 3 | 13-02 | named_predictors()==9, _frozen_tool_desc is dict[str,str], empty param registered |
| `tests/tools/test_tool_selection_with_params.py` | 1 | 13-02 | selected_params annotation is str (JSON), has task_description+available_tools inputs |
| `tests/tools/test_joint_metric.py` | 4 | 13-03 | 4 match matrix cases, 5-param GEPA sig, invalid-JSON→0.0, B2: dspy.Prediction return |
| `tests/tools/test_param_consistency.py` | 3 | 13-04 | detects conflicts, malformed→False, whole-tool rejection via check_all |
| `tests/core/test_cost_tracker.py` | 5 | 13-05 | accumulation, abort-threshold, aborted.json schema, W4 track_usage warning, W5 xfail |
| `tests/tools/test_cross_tool_regression.py` | 1 | 13-06 | persist_per_tool_rates() adds per_tool_baseline_rates + per_tool_evolved_rates |
| `tests/tools/test_v1_baseline_gate.py` | 2 | 13-07 | regression fails (2pp), inline fallback when no --baseline-run |
| `tests/tools/test_evolve_tool_params_cli.py` | 2 | 13-08 | loud GEPA failure, NO-OP in Phase 13 warning for --param-group-size |
| `tests/tools/test_param_size_gate.py` | 2 | 13-08 | B3 SC3: 201-char rejected, 200-char accepted (GREEN at Wave 0) |

**Total: 23 tests collected. B3 param_size_gate: 2 GREEN (exercises existing branch). All others: RED (pending downstream implementation).**

### Task 3: correct_params Type Distribution Inspection

Script output recorded at `.planning/phases/13-per-parameter-description-optimization/13-correct-params-type-inspection.txt` (47 lines).

**Key findings:**
- `total_examples=324` (162 train + 81 val + 81 holdout)
- Value type distribution: `str=363, int=26, list=19, bool=15, dict=7, float=3`
- `NORMALIZATION_RULE=strip_plus_coerce` (6 types present; not str-only)
- This resolves RESEARCH Open Question #2 and mandates that 13-03's `joint_tool_param_metric` must implement strip + numeric/type coerce for `param_match`.

## Deviations from Plan

None — plan executed exactly as written.

## Acceptance Criteria Verification

| Criterion | Status |
|-----------|--------|
| test_tool_module_per_param.py has 3 test functions | PASS (grep -c: 3) |
| test_joint_metric.py has 4 test functions | PASS (grep -c: 4) |
| test_param_consistency.py has 3 test functions | PASS (grep -c: 3) |
| test_cost_tracker.py has >= 4 test functions | PASS (grep -c: 5) |
| test_cross_tool_regression.py has 1 test function | PASS (grep -c: 1) |
| test_v1_baseline_gate.py has 2 test functions | PASS (grep -c: 2) |
| test_evolve_tool_params_cli.py has >= 2 test functions | PASS (grep -c: 2) |
| test_tool_selection_with_params.py has 1 test function | PASS (grep -c: 1) |
| test_param_size_gate.py has 2 test functions (B3) | PASS (grep -c: 2) |
| Total >= 19 test functions | PASS (23 collected) |
| pytest --collect-only exits 0 | PASS |
| B2 no dict-key access in test_joint_metric.py | PASS (0 matches for `ret["score"]`) |
| B2 >= 4 attribute reads in test_joint_metric.py | PASS (6 matches for `ret.score`/`ret.feedback`) |
| test_param_size_gate.py GREEN at Wave 0 | PASS (2 passed) |
| NORMALIZATION_RULE= line in inspection file | PASS (strip_plus_coerce) |
| Existing 353 tests still pass | PASS (355 passed including 2 new GREEN B3 tests) |
| mock_lm_with_usage fixture importable | PASS |
| scripts module importable | PASS |

## Known Stubs

None — all test bodies are complete with explicit assertions. No `pass` stubs or `assert True`.

## Threat Flags

None — plan only adds test files and a read-only inspection script. No new network endpoints, auth paths, or schema changes at trust boundaries.

## Self-Check: PASSED

All created files verified to exist:
- tests/conftest.py: FOUND
- tests/tools/test_tool_module_per_param.py: FOUND
- tests/tools/test_tool_selection_with_params.py: FOUND
- tests/tools/test_joint_metric.py: FOUND
- tests/tools/test_param_consistency.py: FOUND
- tests/core/test_cost_tracker.py: FOUND
- tests/tools/test_cross_tool_regression.py: FOUND
- tests/tools/test_v1_baseline_gate.py: FOUND
- tests/tools/test_evolve_tool_params_cli.py: FOUND
- tests/tools/test_param_size_gate.py: FOUND
- scripts/inspect_correct_params_types.py: FOUND
- 13-correct-params-type-inspection.txt: FOUND (47 lines)

All commits verified:
- 41f3946: feat(13-01): add Wave 0 test package scaffold + mock_lm_with_usage fixture
- f9a88e7: test(13-01): add 9 Wave 0 RED test files covering all Phase 13 plans
- d6c319f: feat(13-01): add correct_params type inspection script + recorded output
