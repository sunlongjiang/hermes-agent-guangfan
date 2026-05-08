---
phase: 13
plan: "07"
subsystem: tools
tags: [wave-3, d-14, v1-baseline, regression-gate, hard-gate]
dependency_graph:
  requires:
    - 13-01 (Wave 0 RED tests in tests/tools/test_v1_baseline_gate.py)
    - 13-02 (ToolModule per-param sub-Module — used as inline baseline carrier downstream)
    - 13-03 (joint_tool_param_metric — consumed by inline scoring path)
  provides:
    - check_v1_baseline_gate(evolved_score, baseline_score, tolerance) -> ConstraintResult
    - compute_v1_baseline(baseline_run, *, baseline_module, holdout, lm) -> dict
    - V1BaselineGate(tolerance) facade combining resolve() + check()
    - evolution.tools.evolve_tool_params shell module re-exporting the gate symbols
  affects:
    - 13-08-PLAN (evolve_tool_params CLI): will import V1BaselineGate / compute_v1_baseline /
      check_v1_baseline_gate; will replace evolve_tool_params.py shell with full CLI while
      keeping these symbols exported.
    - tests/tools/test_evolve_tool_params_cli.py: cascades from SKIPPED -> FAILED (still RED,
      now under module-exists-but-no-`evolve` regime; 13-08 turns it GREEN).
tech_stack:
  added: []
  patterns:
    - ConstraintResult-shaped public API (Wave 0 RED test contract) with details JSON for
      machine-readable raw metrics (delta / tolerance_pp / evolved_score / baseline_score).
    - dict-shaped V1BaselineGate.check() facade that merges resolve() output with raw gate
      metrics — for 13-08 CLI's metrics.json persistence (PLAN.md spec).
    - Three-tier baseline source resolution (historical -> inline -> missing) with
      explicit v1_baseline_source label so CLI can surface degraded-gate semantics.
    - Type-safe historical metrics.json loader: bool / string / OOR / malformed-JSON /
      missing-key all return None and degrade to inline path (T-13-21 mitigation).
key_files:
  created:
    - evolution/tools/v1_baseline_gate.py
    - evolution/tools/evolve_tool_params.py
    - .planning/phases/13-per-parameter-description-optimization/13-07-SUMMARY.md
  modified: []
decisions:
  - "Wave 0 RED tests (locked at 13-01) require check_v1_baseline_gate() to return
    evolution.core.constraints.ConstraintResult — not a dict — and compute_v1_baseline()
    to accept `baseline_module=` (not `inline_module=` per PLAN.md naming). Tests are the
    contract per GSD; deviations applied to PLAN.md-spec function signatures (Rule 1)."
  - "PLAN.md required dict shape with keys passed/delta/tolerance_pp/evolved_score/
    baseline_score/message is preserved on the V1BaselineGate.check() facade (which 13-08
    will use to populate metrics.json) and inside ConstraintResult.details as JSON
    string. _compute_baseline_gate_metrics() is the shared internal helper."
  - "evolve_tool_params.py shell module created NOW (not in 13-08) so the Wave 0 RED tests
    `test_regression_fails_run` and `test_inline_baseline_fallback` can resolve the import
    `from evolution.tools.evolve_tool_params import check_v1_baseline_gate`. 13-08 will
    extend this module into the full Click CLI; the public symbol names remain stable."
  - "Inline scoring path uses joint_tool_param_metric (13-03) for parity with Phase 13's
    acceptance metric, ensuring inline-baseline numbers are directly comparable to evolved
    holdout numbers in the same units (RESEARCH Pitfall 8 semantics: when inline is used,
    the gate degrades from 'do not regress against v1' to 'do not regress against self'
    — but is still a meaningful 2pp stability guard)."
  - "Historical loader rejects bool typed evolved_score even though bool is a numeric
    subclass — semantically a Phase 5 metrics.json with `evolved_score: true` is malformed
    and should fall back to inline rather than silently coerce to 1.0."
  - "Phase 13 scope guard (CONTEXT.md Deferred): module imports no write_back symbol;
    grep on `^\\s*(import|from)\\s+.*write_back|write_back_description\\s*\\(` returns
    zero — only docstring mention of write_back exists, in a 'MUST NOT' guard comment."
metrics:
  duration_minutes: 35
  completed_date: "2026-05-08"
  tasks_completed: 1
  tasks_total: 1
  files_created: 3
  files_modified: 0
  lines_added: 356
---

# Phase 13 Plan 07: V1 Baseline Hard-Gate (D-14) Summary

**One-liner:** New `evolution/tools/v1_baseline_gate.py` exposes `check_v1_baseline_gate` (ConstraintResult-typed 2pp regression gate, D-14) + `compute_v1_baseline` (historical / inline / missing baseline source resolution, RESEARCH Pitfall 8) + `V1BaselineGate` facade — backed by a minimal `evolve_tool_params.py` re-export shell so Wave 0 RED tests turn GREEN; full CLI is 13-08's responsibility.

## What Was Built

### Task 1: `evolution/tools/v1_baseline_gate.py` (new module, 290 LoC)

**Public surface (3 symbols):**

| Symbol | Type | Purpose |
|--------|------|---------|
| `check_v1_baseline_gate(evolved_score, baseline_score, tolerance=0.02)` | function -> `ConstraintResult` | 2pp hard-gate decision (D-14). `passed=False` when `evolved < baseline - tolerance`. `details` field is JSON-encoded `{delta, tolerance_pp, evolved_score, baseline_score}` for 13-08 CLI to dump into metrics.json. |
| `compute_v1_baseline(baseline_run, *, baseline_module=None, holdout=None, lm=None)` | function -> `dict` | Resolves the v1 baseline value with three-tier preference: `historical` (Phase 5 `metrics.json:evolved_score`) -> `inline` (rerun joint_tool_param_metric on baseline ToolModule + holdout) -> `missing` (degraded). Always returns dict with keys `v1_baseline_holdout` / `v1_baseline_source` / `metrics_source_path`. |
| `V1BaselineGate(tolerance=0.02)` | class | OO wrapper. `resolve(...)` calls `compute_v1_baseline`; `check(evolved_score=, baseline=)` merges the resolved baseline dict with raw gate metrics into a single dict (for 13-08 metrics.json schema). |

**Internal helpers:**

- `_compute_baseline_gate_metrics(...)` — single source of truth for the dict shape (`passed/delta/tolerance_pp/evolved_score/baseline_score/message`); shared between `check_v1_baseline_gate` (wraps in ConstraintResult) and `V1BaselineGate.check` (returns dict).
- `_score_module_on_holdout(module, holdout, lm)` — averages `joint_tool_param_metric` across the holdout, with optional `dspy.context(lm=...)` wrapping; tolerant to MagicMock-style examples in unit tests (defensive `getattr` on `task_description`).
- `_load_historical_baseline(baseline_run)` — type-safe Phase 5 `metrics.json:evolved_score` loader. Rejects: missing file, malformed JSON, non-dict root, missing key, bool, non-numeric, out-of-range `[0,1]`. Returns None on any rejection (which routes upstream to inline fallback).
- `_NullCtx` — no-op context manager for the `lm=None` inline scoring path (avoids `with` branching in the loop body).

**Floating-point hygiene:** `delta` is rounded to 10 decimal places before threshold comparison (matches CrossToolRegressionChecker's pattern from `tool_metric.py`).

### Task 2 (sidecar): `evolution/tools/evolve_tool_params.py` (new shell module, 31 LoC)

Re-exports the three v1 baseline gate symbols so:
1. The Wave 0 RED tests in `tests/tools/test_v1_baseline_gate.py` can resolve `from evolution.tools.evolve_tool_params import check_v1_baseline_gate, compute_v1_baseline`.
2. 13-08 has a stable extension point: replace the shell with the full Click CLI while keeping these three exports.

The shell intentionally does NOT define `evolve` (the Click command). 13-08 will add that. Today's status of `tests/tools/test_evolve_tool_params_cli.py`: was SKIPPED (module not found) before this plan; now FAILED with `AssertionError: evolution.tools.evolve_tool_params must have a 'evolve' Click command`. This is a state-transition from skip-RED to fail-RED — both are RED states pointing at 13-08; no new regression introduced. (See Deviations.)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] PLAN.md function signatures conflict with locked Wave 0 RED test contract**

- **Found during:** Task 1 implementation, after reading `tests/tools/test_v1_baseline_gate.py`.
- **Issue:** PLAN.md specifies `check_v1_baseline_gate(...) -> dict` and `compute_v1_baseline(*, inline_module=...)`. The Wave 0 RED tests (locked since 13-01, the immutable test contract) require:
  - `check_v1_baseline_gate(...)` returns `evolution.core.constraints.ConstraintResult`, not a dict; the test does `assert isinstance(result, ConstraintResult)` and `result.passed is False`.
  - `compute_v1_baseline(baseline_run=None, baseline_module=mock_module, holdout=mock_holdout)` — keyword `baseline_module=`, not `inline_module=`.
- **Fix:** Honored the test contract — tests-are-the-contract per GSD TDD discipline. Functions return `ConstraintResult` and accept `baseline_module=`. The dict shape mandated by PLAN.md (passed / delta / tolerance_pp / evolved_score / baseline_score / message) is preserved in two places: (a) `_compute_baseline_gate_metrics()` internal helper, (b) `V1BaselineGate.check()` facade output (for 13-08 metrics.json), (c) `ConstraintResult.details` JSON-encoded payload (for the same purpose with serializable shape). 13-08 CLI can use either the facade or parse details — both yield the same data.
- **Files modified:** `evolution/tools/v1_baseline_gate.py` (signatures and class facade match both the Wave 0 contract and PLAN.md's data spec).
- **Commit:** 77d9718

**2. [Rule 3 — Blocking issue] Wave 0 RED test imports `from evolution.tools.evolve_tool_params`, but PLAN.md says module is `evolution.tools.v1_baseline_gate`**

- **Found during:** Task 1 verification — running `pytest tests/tools/test_v1_baseline_gate.py` after creating only `v1_baseline_gate.py` would still ERROR with `ModuleNotFoundError: evolve_tool_params`.
- **Issue:** The Wave 0 tests reach into `evolution.tools.evolve_tool_params` (since 13-08 will own that import path long-term). Without an `evolve_tool_params` module, the tests can't resolve their imports.
- **Fix:** Created a minimal `evolution/tools/evolve_tool_params.py` shell that does `from evolution.tools.v1_baseline_gate import check_v1_baseline_gate, compute_v1_baseline, V1BaselineGate`. Module exists; symbols resolve; tests turn GREEN. 13-08's CLI implementation will replace the body of this file with the full Click CLI but keep the same three exports for backward compatibility.
- **Files modified:** new `evolution/tools/evolve_tool_params.py`.
- **Commit:** 77d9718

**3. [Cascade] `tests/tools/test_evolve_tool_params_cli.py` flips from SKIPPED -> FAILED**

- **Found during:** Final non-regression sweep (`pytest tests/`).
- **Issue:** That test file uses `pytest.importorskip("evolution.tools.evolve_tool_params")`. Before 13-07, the module didn't exist -> tests SKIPPED. After 13-07, the module exists (re-export shell) but lacks the `evolve` Click command -> 2 tests FAIL with `AssertionError: ... must have a 'evolve' Click command`.
- **Fix:** No fix applied. This is the expected RED state for 13-08's Wave 0 contract. Both SKIPPED and FAILED are "RED targeting 13-08"; the semantic state (test pending implementation) is unchanged. 13-08's PLAN.md `must_haves.truths` already lists "Wave 0 RED test test_loud_gepa_failure_and_opt_in passes" as 13-08's gate. Verified equivalent by inspecting 13-06 SUMMARY: "test_evolve_tool_params_cli.py remain RED — these are Wave 0 stubs targeting plans 13-07 / 13-08".
- **Files modified:** none.

## Acceptance Criteria Verification

From PLAN.md `<acceptance_criteria>`:

| Criterion | Status |
|-----------|--------|
| `test -f evolution/tools/v1_baseline_gate.py` | PASS |
| `grep -nE "^def check_v1_baseline_gate" evolution/tools/v1_baseline_gate.py` returns 1 match | PASS (line 95) |
| `grep -nE "^def compute_v1_baseline" evolution/tools/v1_baseline_gate.py` returns 1 match | PASS (line 197) |
| `grep -n "class V1BaselineGate" evolution/tools/v1_baseline_gate.py` returns 1 match | PASS |
| `grep -n "write_back" evolution/tools/v1_baseline_gate.py` returns 0 matches | NEAR-PASS (1 match — appears only inside docstring's "MUST NOT use write_back" scope guard, not in any import or call). Effective scope guard verified via stricter regex `^\s*(import\|from)\s+.*write_back\|write_back_description\s*\(` returning 0 matches. |
| Smoke: `gate OK` | PASS (delta extracted from `ConstraintResult.details` JSON) |
| Smoke: `missing path OK` | PASS |
| `pytest tests/tools/test_v1_baseline_gate.py -x --tb=short` exits 0 with 2 tests passing | PASS (2 passed in 5.30s) |
| Historical-path bash smoke `hist OK` | PASS (`v1_baseline_source='historical', v1_baseline_holdout=0.85`) |

From PLAN.md `<verification>`:

| Check | Status |
|-------|--------|
| Type-safety smoke (string score / OOR score / valid score) | PASS, plus expanded coverage for bool / negative / missing-key / malformed-JSON — all 7 cases reject correctly |
| Scope guard `! grep -n "write_back" ...` | NEAR-PASS — 1 docstring mention; structural `import/call` regex confirms no actual import/call. |
| Non-regression `pytest tests/tools/ -x --tb=short -q` | PASS for all tests EXCEPT 2 pre-existing `test_evolve_tool_params_cli.py` Wave 0 RED tests targeting 13-08 (cascade from SKIP -> FAIL, not a regression — see Deviation 3) |

Final non-regression sweep across `tests/`:
```
383 passed, 1 xfailed, 3 warnings (CostTracker xfail W5 deferred)
2 failed (test_evolve_tool_params_cli.py — Wave 0 RED, awaiting 13-08)
```

## Threat Model Compliance

Per PLAN.md `<threat_model>`:

| Threat ID | Category | Disposition | Implementation |
|-----------|----------|-------------|----------------|
| T-13-21 | Tampering — Malicious `--baseline-run` payload | mitigate | `_load_historical_baseline` chains `Path.is_file()` -> `json.loads` -> `isinstance(data, dict)` -> not-bool -> `float()` coercion -> range check `0.0 <= score <= 1.0`. Out-of-range, non-numeric, missing key, bool, malformed JSON all return None -> upstream falls back to inline. No subprocess, no exec, no symlink chasing beyond Python's default Path semantics. Verified by 7-case type-safety smoke. |
| T-13-22 | Tampering — Path traversal via `baseline_run` | accept | Single-user CLI threat model. Read target is fixed at `<baseline_run>/metrics.json`; user can read what user can read — same trust boundary as the CLI process. No fix attempted (per disposition). |
| T-13-23 | DoS — Large metrics.json | mitigate | Single `json.loads` on a typical ≤10KB file; no unbounded fan-out. Accepted as residual risk. |
| T-13-24 | Repudiation — Inline fallback masquerading as v1 baseline | mitigate | `v1_baseline_source` field is always populated with `'historical'` / `'inline'` / `'missing'` so the 13-08 CLI can surface the distinction in Rich output and in `metrics.json` for auditability. Tests assert `v1_baseline_source == 'inline'` on the no-baseline-run path. |

No threat-flag-worthy new surface introduced beyond what the threat model already covered.

## Known Stubs

`evolution/tools/evolve_tool_params.py` is a thin re-export shell. It is documented as such in its module docstring and is the planned extension point for 13-08's CLI. It is NOT a "stub-blocking-the-goal" of 13-07 — it is the deliberate seam between waves 3 and 4 of Phase 13. Removal date: 13-08 (will be replaced by full Click CLI body, exports preserved).

## TDD Gate Compliance

PLAN type is `execute`, but Task 1 has `tdd="true"` per the plan's own task block. Gate sequence:

- RED gate commit: `f9a88e7 test(13-01): add 9 Wave 0 RED test files covering all Phase 13 plans` — includes `tests/tools/test_v1_baseline_gate.py` with two failing tests.
- GREEN gate commit: `77d9718 feat(13-07): add v1 baseline regression hard-gate (D-14)` (this plan).
- REFACTOR: none — module is 290 LoC, single-pass design driven directly by the test contract + PLAN.md spec; no cleanup pass needed.

## Self-Check: PASSED

All claims verified:

- `evolution/tools/v1_baseline_gate.py` (290 LoC): FOUND.
- `evolution/tools/evolve_tool_params.py` (31 LoC): FOUND.
- Commit `77d9718` on main: FOUND (`git rev-parse --short HEAD` returns `77d9718`).
- Wave 0 RED tests `test_regression_fails_run` + `test_inline_baseline_fallback`: BOTH PASS (`pytest tests/tools/test_v1_baseline_gate.py -v` -> 2 passed).
- Three smoke tests (`gate OK`, `missing path OK`, `hist OK`): ALL PASS.
- Type-safety extended smoke (7 cases): ALL PASS.
- Phase 13 scope guard (no import or call of `write_back`): VERIFIED via `grep -nE "^\s*(import|from)\s+.*write_back|write_back_description\s*\("` returning 0.
