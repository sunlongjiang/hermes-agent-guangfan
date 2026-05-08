---
phase: 13
plan: "06"
subsystem: tools
tags: [wave-3, d-12, per-tool-rates, metrics-persistence, folded-todo-closure]
dependency_graph:
  requires:
    - 13-01 (Wave 0 RED test: tests/tools/test_cross_tool_regression.py::test_per_tool_persistence)
    - 13-02 (ToolModule per-param sub-Module upgrade — shared-file sequencing rationale, no API coupling)
  provides:
    - persist_per_tool_rates(metrics, baseline_rates, evolved_rates) -> dict helper
    - per_tool_baseline_rates / per_tool_evolved_rates schema contract for metrics.json
  affects:
    - 13-08-PLAN (evolve_tool_params CLI): will call persist_per_tool_rates() before writing metrics.json
    - Phase 16 (Per-Tool Regression Dashboard): will read per_tool_baseline_rates / per_tool_evolved_rates as input data
tech_stack:
  added: []
  patterns:
    - Pure helper function, side-effect-free on inputs (shallow-copy + fresh sub-dicts)
    - Alphabetical key sorting for stable run-to-run diffs of metrics.json
    - float() coercion to guarantee json.dumps safety across numeric source types
key_files:
  created:
    - .planning/phases/13-per-parameter-description-optimization/13-06-SUMMARY.md
  modified:
    - evolution/tools/tool_metric.py
  moved:
    - .planning/todos/pending/2026-05-07-persist-per-tool-regression-rates.md -> .planning/todos/done/
decisions:
  - "Helper returns a shallow copy of metrics (dict(metrics)); does NOT mutate caller input — documented in docstring and verified by acceptance criterion (the 'must not mutate input' assert in the one-liner smoke)."
  - "Rate dicts are re-materialized as new dict comprehensions with float-coerced values and alphabetically sorted keys — guarantees json.dumps safety AND stable cross-run diffs (important for Phase 16 dashboard and for human review of metrics.json)."
  - "CrossToolRegressionChecker.check_regression pass/fail gate behavior intentionally UNCHANGED. This plan is purely additive: the helper is a data-persistence sidecar, not a gate modifier. Preserves Phase 5 backwards compat (T-13-20 disposition: mitigate via shallow copy)."
  - "None-safe input handling via `(baseline_rates or {}).items()` — avoids AttributeError if upstream passes None for a tool-free evaluation run."
metrics:
  duration_minutes: 8
  completed_date: "2026-05-08"
  tasks_completed: 1
  tasks_total: 1
  files_created: 1
  files_modified: 1
  lines_added: 41
---

# Phase 13 Plan 06: Per-Tool Rate Persistence Summary

**One-liner:** New `persist_per_tool_rates(metrics, baseline_rates, evolved_rates) -> dict` helper in `evolution/tools/tool_metric.py` writes per-tool accuracy dicts into `metrics.json` (D-12 / CONCERNS §M3 closure) without touching existing `CrossToolRegressionChecker` pass/fail gate behavior — closes folded todo `2026-05-07-persist-per-tool-regression-rates.md`.

## What Was Built

### Task 1: `persist_per_tool_rates` helper

- **Location:** `evolution/tools/tool_metric.py` lines 442-482 (appended after `joint_tool_param_metric_with_feedback`).
- **Signature:**
  ```python
  def persist_per_tool_rates(
      metrics: dict,
      baseline_rates: dict[str, float],
      evolved_rates: dict[str, float],
  ) -> dict
  ```
- **Behavior:**
  - Shallow-copies `metrics` into a new dict (never mutates caller input).
  - Writes two keys into the copy:
    - `per_tool_baseline_rates`: `{tool: float}` from `baseline_rates`.
    - `per_tool_evolved_rates`: `{tool: float}` from `evolved_rates`.
  - Both rate dicts are freshly constructed with:
    - Keys sorted alphabetically (stable run-to-run diffs).
    - Values coerced via `float(v)` (safe `json.dumps`; handles int / NumPy scalar / Decimal upstream).
  - `None`-safe: `(baseline_rates or {}).items()` tolerates either rate dict being missing.
  - Returns the augmented dict.

### Folded todo closure

- Moved `.planning/todos/pending/2026-05-07-persist-per-tool-regression-rates.md` → `.planning/todos/done/`.
- CONCERNS §M3 data-persistence gap closed at the helper level. The remaining work (wiring the helper into the CLI) belongs to plan 13-08; Phase 16's dashboard will consume these fields.

## Deviations from Plan

None — plan executed exactly as written. No deviation rules triggered; the change is a minimal purely-additive helper whose contract was already fully pinned by the Wave 0 RED test.

## Acceptance Criteria Verification

| Criterion | Status |
|-----------|--------|
| `grep -n "^def persist_per_tool_rates" evolution/tools/tool_metric.py` returns exactly 1 match | PASS (line 442) |
| `grep -c "^def " evolution/tools/tool_metric.py` >= 4 | PASS (8: `tool_selection_metric`, `_coerce_scalar`, `_normalize_param_value`, `_parse_selected_params_json`, `_param_match_score`, `joint_tool_param_metric`, `joint_tool_param_metric_with_feedback`, `persist_per_tool_rates`) |
| one-liner smoke `.venv/bin/python -c "..."` prints `helper OK` | PASS (asserts cover dict content AND input non-mutation) |
| `.venv/bin/python -m pytest tests/tools/test_cross_tool_regression.py -x --tb=short` exits 0 | PASS (1 passed) |
| `.venv/bin/python -m pytest tests/tools/ -x --tb=short -q` non-regression | PASS for this plan's scope. Note: `tests/tools/test_v1_baseline_gate.py` (2 tests) and `tests/tools/test_evolve_tool_params_cli.py` remain RED — these are Wave 0 stubs targeting plans 13-07 / 13-08, pre-existing before this plan, unrelated to 13-06 (verified via `git stash` round-trip). |

### Verification block results

```
# 1. D-12 test passes
.venv/bin/python -m pytest tests/tools/test_cross_tool_regression.py -v
→ 1 passed

# 2. Phase 5 non-regression (tool_selection_metric, CrossToolRegressionChecker)
.venv/bin/python -m pytest tests/tools/test_tool_metric.py -v
→ 17 passed

# 3. Phase 13 joint metric non-regression
.venv/bin/python -m pytest tests/tools/test_joint_metric.py -v
→ 4 passed

# Total scoped verification: 22 / 22 passing.

# 4. Integration sanity
.venv/bin/python -c "<integration script>"
→ integration OK
```

## Threat Model Compliance

Per plan's `<threat_model>`:

| Threat ID | Category | Disposition | Implementation |
|-----------|----------|-------------|----------------|
| T-13-19 | Information Disclosure (rates → metrics.json) | accept | Unchanged; rates are aggregate accuracy numbers over public tool names — no PII, no secrets leaked. |
| T-13-20 | Tampering (caller mutation of returned dict) | mitigate | Helper returns `dict(metrics)` shallow copy; rate sub-dicts are freshly constructed (no shared reference to caller's `baseline_rates` / `evolved_rates`). Verified by the one-liner acceptance smoke (`assert 'per_tool_baseline_rates' not in m`). |

No new threat surface introduced — no network endpoints, no auth paths, no file I/O, no schema changes at trust boundaries.

## Known Stubs

None — helper is fully implemented (not a placeholder). The Phase 16 dashboard **consumer** of this data is itself scoped to Phase 16 per decisions D-12 / `.planning/phases/13-per-parameter-description-optimization/13-CONTEXT.md`, so the per-tool rate fields are persisted-but-not-yet-visualized for the duration of Phases 13-15 — that is by design, not a stub.

## TDD Gate Compliance

Plan type is `execute`, not `tdd`. A single-task TDD inner loop (RED → GREEN) was followed implicitly:

- RED gate commit: `f9a88e7 test(13-01): add 9 Wave 0 RED test files covering all Phase 13 plans` — includes `test_per_tool_persistence` (committed 2026-05-07).
- GREEN gate commit: `756eff9 feat(13-06): add persist_per_tool_rates helper for metrics.json` (this plan).
- REFACTOR: none needed — helper is 15 lines, no cleanup required.

## Self-Check: PASSED

All claims verified:

- `evolution/tools/tool_metric.py` modified (helper present at line 442): FOUND.
- `.planning/todos/done/2026-05-07-persist-per-tool-regression-rates.md` (moved from pending): FOUND.
- `.planning/todos/pending/2026-05-07-persist-per-tool-regression-rates.md`: CORRECTLY ABSENT.
- Commit `756eff9` on main: FOUND (`git log --oneline -1`).
- All 22 scoped verification tests pass.
