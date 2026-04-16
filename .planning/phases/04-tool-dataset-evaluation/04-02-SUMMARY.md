---
phase: 04-tool-dataset-evaluation
plan: 02
subsystem: evolution/tools
tags: [metric, regression, evaluation, dspy]
dependency_graph:
  requires: []
  provides: [tool_selection_metric, ToolRegressionResult, CrossToolRegressionChecker]
  affects: [evolution/tools/evolve_tool (future Phase 5 CLI)]
tech_stack:
  added: []
  patterns: [binary-metric, regression-gate, rich-table-output]
key_files:
  created:
    - evolution/tools/tool_metric.py
    - tests/tools/test_tool_metric.py
  modified: []
decisions:
  - Used round(delta, 10) to avoid floating-point comparison artifacts at 2pp boundary
  - CrossToolRegressionChecker accepts pre-computed (correct_tool, selected_tool) pairs rather than calling ToolModule.forward() directly, keeping it testable without LLM calls
metrics:
  duration: 5min
  completed: "2026-04-16T09:45:05Z"
  tasks: 2
  files: 2
---

# Phase 04 Plan 02: Tool Selection Metric and Regression Checker Summary

Binary 0/1 tool selection metric for GEPA optimization plus per-tool regression gate with absolute 2pp threshold using Rich table output.

## What Was Built

### Task 1: Binary tool_selection_metric function
- DSPy-compatible metric function `tool_selection_metric(example, prediction, trace=None) -> float`
- Returns exactly 0.0 or 1.0 based on `strip().lower()` exact match of `selected_tool` vs `correct_tool`
- Uses `getattr` with empty-string defaults for safe attribute access (threat T-04-04 mitigated)
- `correct_params` intentionally not used in scoring (per D-11)
- 8 unit tests covering: exact match, case insensitive, whitespace trimming, mismatch, empty, missing attributes, trace parameter

### Task 2: CrossToolRegressionChecker with per-tool baseline comparison
- `ToolRegressionResult` dataclass: `passed`, `tool_results`, `regression_threshold`, `regressed_tools`, `message`
- `CrossToolRegressionChecker` class with two methods:
  - `compute_per_tool_rates(predictions)`: computes per-tool accuracy from (correct, selected) tuples
  - `check_regression(baseline_rates, evolved_rates)`: compares rates with absolute 2pp threshold
- Strictly-greater comparison (`delta > threshold`), not greater-or-equal
- Float rounding to 10 decimal places to avoid `0.80 - 0.78 == 0.020000000000000018` artifact
- Rich table output showing tool name, baseline rate, evolved rate, delta, and pass/fail status
- 9 unit tests covering: no regression, regression detected, multiple regressions, boundary at exactly 2pp (passes), boundary at 2.01pp (fails), empty predictions, missing tools

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | 2d8b7b1 | feat(04-02): add binary tool_selection_metric function |
| 2 | 1a82714 | feat(04-02): add CrossToolRegressionChecker with per-tool baseline comparison |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed floating-point comparison at 2pp boundary**
- **Found during:** Task 2 GREEN phase
- **Issue:** `0.80 - 0.78` evaluates to `0.020000000000000018` in IEEE 754 float, causing `> 0.02` to be True when it should be False (exactly 2pp drop should pass)
- **Fix:** Added `round(delta, 10)` before comparison to eliminate floating-point noise
- **Files modified:** evolution/tools/tool_metric.py
- **Commit:** 1a82714

## Verification Results

- `python -m pytest tests/tools/test_tool_metric.py -x -q` -- 17 passed
- `python -c "from evolution.tools.tool_metric import tool_selection_metric, CrossToolRegressionChecker, ToolRegressionResult"` -- imports succeed
- Metric returns only 0.0 or 1.0 for all test cases (verified via 8 tests)
- Regression checker correctly identifies 2pp boundary (verified via 2 boundary tests)

## Self-Check: PASSED

- [x] evolution/tools/tool_metric.py exists
- [x] tests/tools/test_tool_metric.py exists
- [x] 04-02-SUMMARY.md exists
- [x] Commit 2d8b7b1 found
- [x] Commit 1a82714 found
