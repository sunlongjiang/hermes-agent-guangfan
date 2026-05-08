---
phase: 13-per-parameter-description-optimization
reviewed: 2026-05-08T00:00:00Z
depth: standard
files_reviewed: 21
files_reviewed_list:
  - evolution/core/config.py
  - evolution/core/cost_tracker.py
  - evolution/tools/evolve_tool_params.py
  - evolution/tools/tool_constraints.py
  - evolution/tools/tool_metric.py
  - evolution/tools/tool_module.py
  - evolution/tools/v1_baseline_gate.py
  - scripts/__init__.py
  - scripts/inspect_correct_params_types.py
  - tests/conftest.py
  - tests/core/test_config.py
  - tests/core/test_cost_tracker.py
  - tests/tools/test_cross_tool_regression.py
  - tests/tools/test_evolve_tool_params_cli.py
  - tests/tools/test_joint_metric.py
  - tests/tools/test_param_consistency.py
  - tests/tools/test_param_size_gate.py
  - tests/tools/test_tool_module.py
  - tests/tools/test_tool_module_per_param.py
  - tests/tools/test_tool_selection_with_params.py
  - tests/tools/test_v1_baseline_gate.py
findings:
  blocker: 4
  warning: 9
  total: 13
status: issues_found
---

# Phase 13: Code Review Report

**Reviewed:** 2026-05-08T00:00:00Z
**Depth:** standard
**Files Reviewed:** 21
**Status:** issues_found

## Summary

Phase 13 wires per-parameter description optimization through a new ToolModule
shape, a cost-capped GEPA runner, two new constraint checkers, and a v1
regression gate. The core data structures (per-tool sub-Module, frozen
top-level descriptions, joint metric) look correct in isolation. However,
adversarial review surfaces **four BLOCKER-class defects** in the orchestration
layer and around cost telemetry, plus several quality issues in tests and
error-handling.

The most severe issue is that `cost_usd_spent` written to `metrics.json` on
the success path is reported AFTER `tracker.__exit__` has been invoked,
which clears the live UsageTracker — meaning the value can silently report
`0.0` regardless of actual API spend. Three other BLOCKER findings cover
constraint-failure provenance loss, a Wave 0 test that doesn't actually
test what its name claims, and a brittle exception-retry pattern that
re-raises real LM errors instead of degrading gracefully.

## Blockers

### BL-01: Cost telemetry reads stale/zero spend on the success path

**File:** `evolution/tools/evolve_tool_params.py:774, 919`
**Issue:** `tracker.poll()` is called AFTER the `with tracker:` block exits
(lines 686–712). On exit, `CostTracker.__exit__` (cost_tracker.py:161-166)
calls `self._ctx.__exit__(...)` and sets `self._tracker = None`. After this,
`poll()` (cost_tracker.py:208-236) takes the branch where `self._tracker is
None`, builds `combined` from `self._injected_usage` only (empty in
production), and returns either the previous `self.spent_usd` (if a poll
ran inside the `with` block) or `0.0`. In the production happy-path no
in-block `poll()` happens — `_CostStopper.__call__` polls only when stop_callbacks
fire, and stop_callbacks fire only when budget is exceeded — so a
non-aborted run reports `cost_usd_spent: 0.0` in metrics.json regardless of
actual API spend. This silently breaks the cost-cap audit trail (D-13) and
masks budget overruns that finished just under cap.
**Fix:** Poll inside the `with tracker:` block at least once before exit, and
cache the value, e.g.:
```python
with tracker:
    ...
    optimized_module = optimizer.compile(baseline_module, trainset=trainset, valset=valset)
    final_spent = tracker.poll()  # capture before context exits
# now use `final_spent` for metrics; do not call tracker.poll() post-exit
metrics["cost_usd_spent"] = float(round(final_spent, 6))
```
Or capture the final breakdown into `tracker.spent_usd` in `__exit__` before
disposing the underlying ctx.

---

### BL-02: Constraint-failure records lose tool identity

**File:** `evolution/tools/evolve_tool_params.py:817-826, 836-845`
**Issue:** Two places construct failure dicts with the wrong `tool` field.

1. Line 821: `"tool": getattr(r, "constraint_name", "factual_accuracy")`.
   `ConstraintResult.constraint_name` is the **constraint type** ("factual_accuracy"),
   never the tool name. Every factual-accuracy failure ends up with
   `tool="factual_accuracy"`, making downstream triage (e.g. Phase 16
   dashboard) unable to identify which tool failed.
2. Line 839: `"tool": None` for every consistency failure, even though
   `ParamConsistencyChecker.check()` is per-tool and the tool name is
   available in `r.message` ("Param description inconsistency detected in
   '{tool_name}'") but not in any structured field.

`ConstraintResult` has no tool-name field, so the call site must thread it
through explicitly.
**Fix:** Pass tool names alongside the results:
```python
# 11b
for evolved, r in zip(evolved_tools, factual_results):
    if not r.passed:
        constraint_failures.append({
            "tool": evolved.name,
            "param": None,
            "constraint": "factual_accuracy",
            "message": r.message,
        })
# 11c
for evolved, r in zip(evolved_tools, consistency_results):
    if not r.passed:
        constraint_failures.append({
            "tool": evolved.name,
            "param": None,
            "constraint": "param_consistency",
            "message": r.message,
            "details": r.details,
        })
```
Note: `factual_checker.check_all` skips evolved tools whose name has no
match in `original_tools`, so a positional zip is unsafe — refactor
`check_all` to return `(tool_name, ConstraintResult)` tuples or store the
name in `ConstraintResult.details` as a structured JSON field.

---

### BL-03: `test_loud_gepa_failure_and_opt_in` does not test what it claims

**File:** `tests/tools/test_evolve_tool_params_cli.py:11-44`
**Issue:** The test patches `_load_tool_descriptions` to return `[]`. In the
implementation (`evolve_tool_params.py:614-628`) an empty tool list short-
circuits with `return 1` BEFORE `dspy.GEPA(...)` is ever instantiated. So the
patched `mock_dspy.GEPA.return_value.compile.side_effect = RuntimeError(...)`
never fires and the loud-fail-vs-opt-in branching at lines 727-743 is never
exercised. The assertion `"gepa blew up" in result.output or result.exit_code != 0`
trivially passes via the `exit_code != 0` clause from the empty-tools path.

This means **D-15a (loud GEPA failure default)** — explicitly named in the
implementation comment "default loud raise per D-15a" — has zero test
coverage despite a Wave 0 test claiming to cover it.
**Fix:** Provide at least one non-empty `ToolDescription` from the patch and
provide a non-empty dataset, then verify GEPA failure actually raises.
Example:
```python
fake_tool = ToolDescription(
    name="x", file_path=Path("/fake/x.py"),
    description="x", params=[ToolParam(name="p", type="string", required=True)],
)
fake_ds = [dspy.Example(task_description="t", correct_tool="x", correct_params={}).with_inputs("task_description")]
with patch("evolution.tools.evolve_tool_params._load_tool_descriptions", return_value=[fake_tool]), \
     patch("evolution.tools.evolve_tool_params._load_dataset", return_value=(fake_ds, fake_ds, fake_ds)), \
     patch("evolution.tools.evolve_tool_params.dspy.GEPA") as mock_gepa, \
     patch("evolution.tools.evolve_tool_params.dspy.LM"):
    mock_gepa.return_value.compile.side_effect = RuntimeError("gepa blew up")
    # default: must raise (loud) rather than fall back
    result = runner.invoke(evolve, [], catch_exceptions=True)
    assert result.exit_code != 0
    assert isinstance(result.exception, RuntimeError)
    assert "gepa blew up" in str(result.exception)
    # opt-in: must fall back gracefully
    mock_gepa.return_value.compile.side_effect = RuntimeError("gepa blew up")
    result2 = runner.invoke(evolve, ["--allow-miprov2-fallback"], catch_exceptions=True)
    # ... assert miprov2 path was attempted
```

---

### BL-04: Exception retry in holdout scoring re-raises real LM errors

**File:** `evolution/tools/evolve_tool_params.py:323-326` and
`evolution/tools/v1_baseline_gate.py:170-175`
**Issue:** Both holdout scorers wrap the `module(task_description=...)` call
in a `try/except Exception` that simply retries with
`getattr(ex, "task_description", "")`. The retry's only difference is the
fallback-empty argument. If the original call raised because `ex` lacks
`task_description`, the retry succeeds with `""`. But if the call raised
because of a real LM error (timeout, rate limit, malformed completion,
network failure), `ex.task_description` exists and is identical to the first
attempt — the retry will raise the same exception, which is now uncaught,
aborting the entire holdout loop and tearing down the pipeline.

For Phase 13 production this is worse than crashing on the first error: the
silent retry makes diagnostics harder (no error logged on the first try),
and the pattern ALWAYS doubles LM cost on failure. The comment "MagicMock
holdout examples in unit tests may not have a real task_description
attribute" reveals the intent — but real LM errors fall into the same path.
**Fix:** Catch only `AttributeError` (the actual concern) and treat real LM
failures as a per-example skip with logged details:
```python
for ex in holdout_examples:
    try:
        task = ex.task_description
    except AttributeError:
        task = getattr(ex, "task_description", "")
    try:
        pred = module(task_description=task)
    except Exception as e:
        console.print(f"[yellow]holdout example skipped due to LM error: {e}[/yellow]")
        n += 1  # count toward denominator? (decide policy explicitly)
        continue
    ...
```

## Warnings

### WR-01: `CostTracker.exceeded()` docstring contradicts behavior for `max_usd <= 0`

**File:** `evolution/core/cost_tracker.py:130-131, 238-242`
**Issue:** Class docstring says "Set to <= 0 to disable enforcement (not
recommended; still polls)." But `exceeded()` returns `False` immediately
when `max_usd <= 0`, never polling. Either the comment is wrong or polling
should still happen for telemetry.
**Fix:** Either update the docstring or change `exceeded()` to call
`self.poll()` for telemetry side-effects before short-circuiting.

---

### WR-02: Silent fallback on YAML `max_cost_usd` parse failure

**File:** `evolution/core/config.py:124-127, 147-150, 169-172`
**Issue:** Three try/except blocks wrap `float(...)` conversions for
`max_cost_usd` and silently `pass` on `TypeError`/`ValueError`. A typo'd
`max_cost_usd: "twenty"` in evolution.yaml is silently ignored and the
default `20.0` is used. Users have no way to know their config setting was
discarded.
**Fix:** Emit a stderr warning (same pattern as the literal-key warning at
line 178-183):
```python
except (TypeError, ValueError):
    sys.stderr.write(
        f"⚠️  evolution.yaml max_cost_usd={data['max_cost_usd']!r} is not a number; "
        f"falling back to default {config.max_cost_usd}.\n"
    )
```

---

### WR-03: `_filter_tools` warning surface is inconsistent with `tools_filter` metric

**File:** `evolution/tools/evolve_tool_params.py:171-194, 782-784`
**Issue:** `_filter_tools` strips empties from the parsed list and warns on
unknowns. The metrics dump at line 782 re-parses `tools_filter.split(",")`
without filtering empties or de-duping. So `--tools "memory,,terminal"`
results in `metrics["tools_filter"] == ["memory", "", "terminal"]` while
the actually applied filter is `["memory", "terminal"]`. Minor data-quality
issue for downstream consumers.
**Fix:** Use the same parse helper for both call sites, or persist the
already-filtered `[t.name for t in all_tools]` instead of the raw input.

---

### WR-04: GEPA `optimizer_used` stays "gepa" even when MIPROv2 fallback ran successfully

**File:** `evolution/tools/evolve_tool_params.py:684-743`
**Issue:** `optimizer_used = "miprov2"` is set BEFORE the MIPROv2 compile
attempt (line 737). If MIPROv2 itself raises (line 741-743), the function
re-raises but `optimizer_used` has already mutated to "miprov2" in the local
scope. Because the function then propagates the exception, no metrics are
written, so this is benign — but the variable's order of mutation (set
before attempt, never reset on attempt failure) is a footgun for any future
caller that catches the MIPROv2 exception and tries to record state.
**Fix:** Set `optimizer_used = "miprov2"` only after MIPROv2 succeeds.

---

### WR-05: `_write_aborted_dir` calls `tracker.write_aborted_json` BEFORE `mkdir`

**File:** `evolution/tools/evolve_tool_params.py:444-458`
**Issue:** `tracker.write_aborted_json(abort_dir, ...)` runs first (line
445) — but `write_aborted_json` itself calls `output_dir.mkdir(parents=True,
exist_ok=True)` (cost_tracker.py:303), which works. Then `_write_aborted_dir`
calls `abort_dir.mkdir(parents=True, exist_ok=True)` (line 454) and writes
`partial_diff.txt`. The double-mkdir is redundant but harmless. However,
ordering matters if `write_aborted_json` is changed in the future to NOT
mkdir — code becomes order-dependent without documentation. Document the
contract or move the explicit mkdir to before the write call.
**Fix:**
```python
abort_dir.mkdir(parents=True, exist_ok=True)
tracker.write_aborted_json(abort_dir, ...)
(abort_dir / "partial_diff.txt").write_text(...)
```

---

### WR-06: `_inject_usage_for_test` accumulates non-token fields with last-write-wins semantics

**File:** `evolution/core/cost_tracker.py:180-191`
**Issue:** Token fields accumulate across `_inject_usage_for_test` calls,
but non-token fields use last-write-wins. This split semantic is
undocumented at the call site and can lead to confusing test fixtures
(e.g., a `model` field set on first inject silently overwrites on second).
Since no tests currently exercise non-token fields, this is latent — but
the function reads as if it does the right thing.
**Fix:** Either document the split-semantic explicitly, or normalize on a
single semantic (e.g., raise on conflicting non-token field).

---

### WR-07: `_load_dataset` 'synthetic' branch always overwrites the dataset directory

**File:** `evolution/tools/evolve_tool_params.py:241-252`
**Issue:** When `eval_source="synthetic"` is selected, `dataset.save(dataset_path)`
unconditionally writes to `datasets/tools/`, clobbering whatever existed.
There is no warning, no backup, no `--force` flag. Users running back-to-back
synthetic + load runs may unintentionally lose a curated dataset.
**Fix:** Either save under a timestamped sub-directory, or print a warning
when overwriting an existing directory.

---

### WR-08: `_evaluate_holdout` silently drops mock-metric type errors but logs nothing

**File:** `evolution/tools/evolve_tool_params.py:328-331` and
`evolution/tools/v1_baseline_gate.py:177-181`
**Issue:** `try: total += float(score) except (TypeError, ValueError): pass`
silently treats non-numeric `score` as 0.0 contribution but still increments
`n` (denominator). Production LM should never return non-numeric scores;
this is purely test-mock accommodation. Production deployments would
silently dilute the holdout average if a metric ever does return a non-numeric
value, with no logged signal.
**Fix:** Use a logging-only fallback in production code; keep the
test-mock concession behind an explicit flag or move the tolerant behavior
into a separate test helper.

---

### WR-09: `_NullCtx` defined but never used elsewhere; bare-Exception scoring failures silently produce 0.0

**File:** `evolution/tools/v1_baseline_gate.py:137-144, 162-183`
**Issue:** `_NullCtx` is a no-op context manager used when `lm` is `None`.
Combined with the bare-except retry pattern (covered in BL-04), an inline
baseline that fails on every example silently returns `0.0` — the V1
baseline gate then compares `evolved_score >= 0.0 - tolerance` and trivially
passes (`v1_baseline_source='inline'`). A failed inline baseline run is
indistinguishable from a successful zero-score baseline. This degrades the
gate's safety guarantee silently.
**Fix:** Track whether any holdout example produced a real prediction; if
zero produced predictions, raise an explicit error or set
`v1_baseline_source='inline_failed'` and force the gate to fail closed.

## Additional Notes (non-finding observations)

- **Test scope:** `tests/tools/test_param_consistency.py` mocks `checker.checker`
  but does not exercise the LLM-error fallback at `tool_constraints.py:255-262`
  (which catches all exceptions and returns `passed=False`). Suggest adding
  a `mock_checker.side_effect = RuntimeError("LM down")` test case.

- **Test gap:** `tests/tools/test_v1_baseline_gate.py` does not test the
  historical-baseline path (`baseline_run` pointing at a real
  `metrics.json`). The `_load_historical_baseline` function has range guards
  that should be exercised: malformed JSON, out-of-range scores, bool-typed
  scores, missing `evolved_score` key.

- **Test gap:** `tests/core/test_cost_tracker.py::test_aborted_json_schema`
  manually sets `tracker.spent_usd = 20.34` to bypass the tracker; this
  hides the bug described in BL-01 because the test never exits a `with`
  block before calling `write_aborted_json`. A test that polls inside the
  block, exits the block, then checks the post-exit `poll()` value would
  catch BL-01 directly.

- **Documentation drift:** `evolve_tool_params.py:32-34` describes a
  failure-branching matrix that includes "FAILED_<ts>/" for all gate
  failures, but the constraint-failures path uses
  `_write_failed_dir("CONSTRAINTS_FAILED", ...)` whose `reason` is set as
  `metrics["status"]` only when not already present (uses `setdefault`).
  Outside contributors may not realize that `metrics["status"]` from earlier
  pipeline assignments wins over the explicit reason. Consider hard-setting.

- **Phase scope guard:** `evolve_tool_params.py:36-38` notes "Phase 13
  scope guard ... MUST NOT import or invoke the writeback path from
  evolution.tools.tool_loader." Verified — `evolve_tool_params.py` does not
  import `write_back_description`. Good.

---

_Reviewed: 2026-05-08T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
