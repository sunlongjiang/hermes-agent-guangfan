---
phase: 13-per-parameter-description-optimization
fixed_at: 2026-05-08T06:44:57Z
review_path: .planning/phases/13-per-parameter-description-optimization/13-REVIEW.md
iteration: 1
findings_in_scope: 13
fixed: 13
skipped: 0
status: all_fixed
---

# Phase 13: Code Review Fix Report

**Fixed at:** 2026-05-08T06:44:57Z
**Source review:** .planning/phases/13-per-parameter-description-optimization/13-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 13 (4 BLOCKER + 9 WARNING; project treats blocker == critical)
- Fixed: 13
- Skipped: 0

Pre-fix baseline: 385 passed + 1 xfailed.
Post-fix baseline: 395 passed + 1 xfailed (+10 new regression tests across 4 new/extended test files).

All fixes committed atomically on `gsd-reviewfix/13-68795`. Each commit
references its finding ID in the subject line.

## Fixed Issues

### BL-01: Cost telemetry reads stale/zero spend on the success path

**Files modified:** `evolution/tools/evolve_tool_params.py`, `tests/core/test_cost_tracker.py`
**Commit:** 62e166b
**Applied fix:** Capture `tracker.poll()` inside the `with tracker:` block as `final_spent_usd` and reuse it on every code path that writes `metrics["cost_usd_spent"]`. Post-`__exit__` poll() falls back to `_injected_usage` (empty in production) and silently returns 0.0, masking real API spend in the cost-cap audit trail (D-13). Added `test_poll_after_exit_returns_zero_regression` pinning the silent-zero behavior and the snapshot-in-block contract.

### BL-02: Constraint-failure records lose tool identity

**Files modified:** `evolution/tools/evolve_tool_params.py`, `tests/tools/test_constraint_failure_records.py` (new)
**Commit:** a6aa5b1
**Applied fix:** Both factual_accuracy and param_consistency failure dicts now carry the evolved tool's `.name` as `tool`. Mirrors `ToolFactualChecker.check_all`'s skip-when-no-original-match filter so positional zip is safe. `ParamConsistencyChecker.check_all` iterates evolved_tools in order with no skip, so positional zip is safe there. Added 2 regression tests pinning both contracts.

### BL-03: `test_loud_gepa_failure_and_opt_in` does not test what it claims

**Files modified:** `tests/tools/test_evolve_tool_params_cli.py`
**Commit:** 36297db
**Applied fix:** Restructured the test to provide a non-empty `ToolDescription` and a non-empty dataset so the pipeline reaches the `dspy.GEPA(...)` try/except. New assertions verify (1) `mock_gepa.called` AND `mock_gepa.return_value.compile.called` (proves side_effect fired); (2) default path: `RuntimeError("gepa blew up")` propagates; (3) `--allow-miprov2-fallback`: `dspy.MIPROv2` IS instantiated (proves fallback codepath reached) and its own RuntimeError propagates. Per the prompt's requirement, this is option (a): restructured the test so `dspy.GEPA` is actually reached and the side_effect fires.

### BL-04: Exception retry in holdout scoring re-raises real LM errors

**Files modified:** `evolution/tools/evolve_tool_params.py`, `evolution/tools/v1_baseline_gate.py`, `tests/tools/test_holdout_lm_error_handling.py` (new)
**Commit:** 9b7d504
**Applied fix:** Narrowed the broad `except Exception` to `except AttributeError` for the `task_description` lookup (the actual MagicMock concern). Real LM errors now skip the example via `continue` WITHOUT incrementing the denominator (so a sequence of failures does not silently dilute the average to 0.0). The CLI path logs `[yellow]` to console; the v1_baseline_gate path is silent (it is intentionally filesystem-side-effect free per its docstring). Added 3 regression tests pinning call_count==1 under LM RuntimeError, legacy MagicMock-without-task_description preserved, and v1_baseline_gate mirror contract.

### WR-01: `CostTracker.exceeded()` docstring contradicts behavior for `max_usd <= 0`

**Files modified:** `evolution/core/cost_tracker.py`
**Commit:** edf2c35
**Applied fix:** Updated the class docstring and the `exceeded()` method docstring to state the actual contract: when enforcement is disabled (`max_usd <= 0`), `exceeded()` short-circuits to False without polling. Earlier text said "still polls" — inaccurate. Telemetry callers in disabled-cap mode must use `poll()` directly.

### WR-02: Silent fallback on YAML `max_cost_usd` parse failure

**Files modified:** `evolution/core/config.py`, `tests/core/test_config.py`
**Commit:** a71b3dd
**Applied fix:** All three except blocks (YAML, env var, CLI override) now write a stderr warning matching the existing literal-key warning style instead of bare-passing. Users see when their `max_cost_usd: "twenty"` typo silently fell back to the default. Added 2 regression tests for the YAML and env-var paths (Click validates the CLI float, so the CLI branch is mostly defense-in-depth).

### WR-03: `_filter_tools` warning surface is inconsistent with `tools_filter` metric

**Files modified:** `evolution/tools/evolve_tool_params.py`
**Commit:** 9e00029
**Applied fix:** Replaced `metrics["tools_filter"] = [s.strip() for s in tools_filter.split(",")]` (which preserved empties from a malformed CLI string) with `[t.name for t in all_tools]` — the post-filter list. Now metrics.json reflects the filter that actually ran rather than a re-parse of the raw CLI input.

### WR-04: GEPA `optimizer_used` stays "gepa" even when MIPROv2 fallback ran successfully

**Files modified:** `evolution/tools/evolve_tool_params.py`
**Commit:** 9fcf4a5
**Applied fix:** Moved `optimizer_used = "miprov2"` to AFTER `mipro.compile()` returns successfully. The previous order set it before the attempt; if MIPROv2 itself raised, the local was already in a misleading state (benign today since the function then re-raises with no metrics written, but a footgun for future callers that catch the MIPROv2 exception).

### WR-05: `_write_aborted_dir` calls `tracker.write_aborted_json` BEFORE `mkdir`

**Files modified:** `evolution/tools/evolve_tool_params.py`
**Commit:** 7dbe920
**Applied fix:** Reordered `_write_aborted_dir` so the explicit `abort_dir.mkdir(parents=True, exist_ok=True)` runs FIRST, then `tracker.write_aborted_json`, then the local `(abort_dir / "partial_diff.txt").write_text(...)`. The prior order worked only because `write_aborted_json` internally `mkdir`'d as a side-effect; the local `write_text` relied on that. Making our local mkdir the first step removes the implicit dependency.

### WR-06: `_inject_usage_for_test` accumulates non-token fields with last-write-wins semantics

**Files modified:** `evolution/core/cost_tracker.py`
**Commit:** f363d5a
**Applied fix:** Documented the split-merge semantics in the docstring: token fields (`prompt_tokens`, `completion_tokens`, `total_tokens`) accumulate; all other fields use last-write-wins. Future test fixtures setting e.g. a `model` field will now know that subsequent injects silently overwrite it.

### WR-07: `_load_dataset` 'synthetic' branch always overwrites the dataset directory

**Files modified:** `evolution/tools/evolve_tool_params.py`
**Commit:** 9600a12
**Applied fix:** Added a yellow warning when `--eval-source synthetic` is about to overwrite a non-empty `datasets/tools/` directory. Users running back-to-back synthetic + load runs now see a visible signal before a curated dataset gets clobbered.

### WR-08: `_evaluate_holdout` silently drops mock-metric type errors but logs nothing

**Files modified:** `evolution/tools/evolve_tool_params.py`, `evolution/tools/v1_baseline_gate.py`
**Commit:** 28178f5
**Applied fix:** Both `_evaluate_holdout` (CLI) and `_score_module_on_holdout` (v1_baseline_gate) now log a yellow/stderr warning when a non-numeric score is dropped. Production LM should never return non-numeric, but a real-world leak is now visible instead of silently diluting the average. Contribution stays 0.0 (denominator still increments) — failing would be too aggressive given the existence of test mocks.

### WR-09: `_NullCtx` defined but never used elsewhere; bare-Exception scoring failures silently produce 0.0

**Files modified:** `evolution/tools/v1_baseline_gate.py`, `tests/tools/test_holdout_lm_error_handling.py`
**Commit:** 4d84854
**Applied fix:** Introduced `_InlineBaselineFailedError`. `_score_module_on_holdout` raises it when `n == 0` in a non-empty holdout (every example failed). `compute_v1_baseline` catches it and returns `v1_baseline_source='inline_failed'` with `v1_baseline_holdout=1.0`, forcing the V1 gate to fail closed: any evolved_score < 1.0 - tolerance is rejected, so a broken inline baseline can no longer trivially pass. Updated the BL-04 mirror test to a 2-example fixture (one fails, one succeeds) so it still proves no silent retry without colliding with the new fail-closed semantics. Added 2 new tests for the fail-closed path.

## Skipped Issues

None.

---

_Fixed: 2026-05-08T06:44:57Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
