---
phase: 13
plan: "05"
subsystem: core
tags: [config, cost-tracking, budget-cap, gepa, folded-todo-closure]
dependency_graph:
  requires:
    - 13-01 (Wave 0 RED scaffold — test_cost_tracker.py turns GREEN here)
  provides:
    - EvolutionConfig.max_cost_usd + reflection_model (consumed by 13-08 CLI)
    - CostTracker + CostBudgetExceeded + estimate_cost_usd (consumed by 13-08 CLI via gepa_kwargs.stop_callbacks)
  affects:
    - 13-08-PLAN (evolve_tool_params CLI wires CostTracker into optimizer.compile context)
tech_stack:
  added: []  # no new external deps — uses DSPy 3.1.3 usage_tracker + already-transitive litellm 1.83.8
  patterns:
    - Extended layered config resolution (YAML < env < CLI) to two new fields matching existing api_base/api_key/model pattern
    - Context manager wrapping dspy.utils.usage_tracker.track_usage() + merge-injected-usage path for test ergonomics
    - Dual calling convention on write_aborted_json (kwargs + extra={...}) to satisfy Wave 0 test contract without foreclosing the cleaner per-kwarg API for 13-08
key_files:
  created:
    - evolution/core/cost_tracker.py
  modified:
    - evolution/core/config.py
    - tests/core/test_config.py
    - .planning/todos/pending/2026-05-07-max-cost-usd-and-reflection-model.md → .planning/todos/done/
decisions:
  - "D-13 cost_tracker poll() merges real UsageTracker output with `_injected_usage` so Wave 0 tests can exercise accumulation/threshold math without spinning up a live LM + track_usage=True. The injection path is documented as test-only in the CostTracker docstring; production callers get the Pitfall 2 RuntimeWarning from __enter__ when they forget dspy.configure(track_usage=True)."
  - "write_aborted_json accepts both `extra={...}` dict (Wave 0 test contract from 13-01 test_aborted_json_schema) and explicit kwargs (plan-spec API for 13-08). kwargs override extra. evaluated_candidates defaults to 0 and partial_diff defaults to [] when neither caller form supplies them, so downstream callers can't accidentally produce a malformed payload."
  - "W5 poll-side empty-usage warning NOT implemented (xfail preserved). Rationale: 13-01 scaffolded it as honest-gap; adding the second RuntimeWarning inside poll() would couple cost_tracker to a polling-frequency heuristic that the Phase 13 CLI surface doesn't yet justify. 14-xx can remove the xfail + add the guard if poll cadence becomes a concern."
metrics:
  duration_minutes: 11
  completed_date: "2026-05-07"
  tasks_completed: 2
  tasks_total: 2
  files_created: 1
  files_modified: 2
  commits: 3
  lines_added: 407  # 85 config + 322 cost_tracker
---

# Phase 13 Plan 05: Cost Cap + Reflection Model Config Summary

**One-liner:** EvolutionConfig gains max_cost_usd/reflection_model with YAML/env/CLI resolution + evolution/core/cost_tracker.py turns 4 Wave 0 RED tests GREEN for GEPA budget enforcement; folded todo `2026-05-07-max-cost-usd-and-reflection-model.md` closed.

## What Was Built

### Task 1: Extend EvolutionConfig with max_cost_usd + reflection_model (commit 9883046)

- Added two new dataclass fields to `evolution/core/config.py`:
  - `reflection_model: Optional[str] = None` (D-08) — placed next to `judge_model` in the "LLM configuration" block so the model-name cluster stays tight.
  - `max_cost_usd: float = 20.0` (D-13) — placed after the size constraints block with a comment spelling out the `<= 0 → disabled (not recommended)` convention.
- Extended `EvolutionConfig.load()` with three new resolution layers:
  - YAML: `models.reflection` reads reflection_model; top-level `max_cost_usd` reads the cost cap (invalid numeric values fall back silently to previous layer, matching the literal-key graceful handling pattern already in place).
  - env vars: `EVOLUTION_REFLECTION_MODEL` and `EVOLUTION_MAX_COST_USD` slot in between YAML and CLI, matching the existing `EVOLUTION_API_BASE` / `EVOLUTION_API_KEY` / `EVOLUTION_MODEL` pattern.
  - CLI overrides: `reflection_model=...` and `max_cost_usd=...` kwargs (CLI winner).
- Appended 5 Phase 13 tests to `tests/core/test_config.py` (the plan referenced `tests/test_config.py` but the actual path is `tests/core/test_config.py` — adjusted without changing intent):
  - `test_evolution_config_defaults_phase13`
  - `test_evolution_config_max_cost_usd_from_yaml`
  - `test_evolution_config_max_cost_usd_env_overrides_yaml`
  - `test_evolution_config_max_cost_usd_cli_overrides_env`
  - `test_evolution_config_reflection_model_env_and_cli`

### Task 2: Create evolution/core/cost_tracker.py (commit 8fcbbb1)

New module with three public exports:

- **`CostTracker(max_usd: float)`** — context manager wrapping `dspy.utils.usage_tracker.track_usage()`.
  - `__enter__` emits `RuntimeWarning` when `dspy.settings.track_usage` is False (Pitfall 2 / W4 guard).
  - `poll()` merges real UsageTracker output with manually-injected usage and returns current total USD; sets `self.spent_usd` and `self.breakdown` as side-effects.
  - `exceeded()` returns `self.poll() > self.max_usd` (strict `>` matching the `CrossToolRegressionChecker` convention noted in the plan); returns False when `max_usd <= 0`.
  - `write_aborted_json(output_dir, *, extra=None, **kwargs)` — persists `aborted.json` with required keys `{final_cost_usd, max_cost_usd, evaluated_candidates, aborted_at_iso, partial_diff, spent_breakdown_by_lm, status}` plus any extra/kwargs.
  - `_inject_usage_for_test(usage_by_lm)` — test-only hook used by Wave 0 tests to bypass the dspy.settings gate; accumulates across calls.
- **`estimate_cost_usd(usage_by_lm) -> (total_usd, breakdown)`** — pure helper that converts UsageTracker output to USD via `litellm.cost_per_token`, with conservative fallback ($0.001/$0.003 per 1K prompt/completion) when litellm raises or returns non-finite. The `fallback: True` flag surfaces in the per-LM breakdown dict.
- **`CostBudgetExceeded(spent_usd, max_usd)`** — exception that downstream CLI code raises after `tracker.exceeded()` + `tracker.write_aborted_json()`.

### Task 3: Close folded todo (commit 873b5f7)

Moved `.planning/todos/pending/2026-05-07-max-cost-usd-and-reflection-model.md` → `done/` — both closure conditions (D-08 config fields + D-13 cost_tracker abort primitives) were delivered by commits 9883046 + 8fcbbb1.

## Deviations from Plan

### 1. [Rule 3 - Blocking] Test file path differs from plan

- **Found during:** Task 1 read_first
- **Issue:** Plan referenced `tests/test_config.py`, but the actual existing config test file is at `tests/core/test_config.py` (mirrors `evolution/core/config.py` nesting — matches the pattern `tests/core/test_cost_tracker.py` for the Wave 0 RED file).
- **Fix:** Appended the 5 Phase 13 tests to `tests/core/test_config.py`. Plan intent preserved — same 5 test functions with identical names and assertions.
- **Files modified:** `tests/core/test_config.py`
- **Commit:** 9883046

### 2. [Rule 3 - Blocking] Wave 0 test calling convention diverges from plan's `write_aborted_json` API

- **Found during:** Task 2 read_first (reviewing `tests/core/test_cost_tracker.py::test_aborted_json_schema`)
- **Issue:** The Wave 0 RED test calls `tracker.write_aborted_json(output_dir=output_dir, extra={"evaluated_candidates": 5, "partial_diff": []})` — it passes an `extra` dict rather than the individual `evaluated_candidates=` / `partial_diff=` kwargs the plan's <action> block prescribes. A plan-literal implementation would leave `evaluated_candidates=0` and `partial_diff=[]` in the payload and fail the test's top-level-keys assertion depending on ordering.
- **Fix:** Implemented a dual signature — `write_aborted_json(output_dir, *, extra=None, **kwargs)`. `extra` is merged into the payload first, then `kwargs` (so kwargs win on collisions). Both `evaluated_candidates` and `partial_diff` are popped out of the merged dict so they can be injected as required typed keys. Result: the Wave 0 test passes AND the plan-spec kwargs API documented in the CostTracker docstring works for downstream 13-08.
- **Files modified:** `evolution/core/cost_tracker.py`
- **Commit:** 8fcbbb1

### 3. [Rule 2 - Missing functionality] Plan `poll()` ignores `_injected_usage`

- **Found during:** Task 2 implementation, rerunning Wave 0 tests
- **Issue:** Plan's literal `poll()` body reads only from `self._tracker.get_total_tokens()`. But Wave 0 `test_accumulation` and `test_abort_threshold` inject usage via `tracker._inject_usage_for_test(mock_usage)` and expect `poll()` to then return a nonzero cost. Without merging the injection path, both tests fail — the RED→GREEN bridge the plan required would be impossible.
- **Fix:** Added `_injected_usage: dict[str, dict]` attribute + `_inject_usage_for_test()` accumulator method + merge logic in `poll()`. The injection path is documented in the CostTracker docstring as test-only with an explicit steer toward `dspy.configure(track_usage=True)` for production callers.
- **Files modified:** `evolution/core/cost_tracker.py`
- **Commit:** 8fcbbb1

### 4. [Rule 2 - Missing functionality] `test_aborted_json_schema` calls `write_aborted_json` without entering the context manager

- **Found during:** Task 2 implementation
- **Issue:** The test constructs `CostTracker(max_usd=20.0)`, sets `tracker.spent_usd = 20.34`, then immediately calls `tracker.write_aborted_json(...)` without any `with tracker:` block. The plan's literal body calls `self.poll()` inside `write_aborted_json` to refresh — but with `self._tracker is None` the plan's poll() overwrote `self.spent_usd` to 0.0 (via `estimate_cost_usd({}) → 0.0`), corrupting the test's 20.34 setup. Final assertion `data["final_cost_usd"]` would then be 0.0 (still a float, still passes the isinstance check) but semantically wrong and a landmine for 13-08.
- **Fix:** In `poll()`, short-circuit: when there is no live tracker AND no injected usage, return `self.spent_usd` unchanged. This preserves the manual-set value for the schema test while still exercising the estimate path when there's real or injected usage.
- **Files modified:** `evolution/core/cost_tracker.py`
- **Commit:** 8fcbbb1

Total deviations: 4. All Rule 1-3 auto-fixes (no architectural changes). No user intervention was needed.

## TDD Gate Compliance

This plan is `type: execute` (not `type: tdd`) — Wave 0 RED tests were scaffolded in 13-01 and this plan turns them GREEN. The 3 commits split feat/feat/chore correctly: two `feat(13-05)` commits for the implementation (RED→GREEN bridge for pre-existing failing tests + config extension), one `chore(13-05)` for todo housekeeping. No separate test-only commit because the new config tests landed alongside the config extension they cover (per-task commit model, not TDD-cycle model).

## Acceptance Criteria Verification

### Task 1

| Criterion | Status |
|-----------|--------|
| `grep -n "max_cost_usd" evolution/core/config.py` >= 4 matches | PASS (9) |
| `grep -n "reflection_model" evolution/core/config.py` >= 4 matches | PASS (8) |
| `grep -n "EVOLUTION_MAX_COST_USD" evolution/core/config.py` == 1 match | PASS (1) |
| `grep -n "EVOLUTION_REFLECTION_MODEL" evolution/core/config.py` == 1 match | PASS (1) |
| `python -c "from evolution.core.config import EvolutionConfig; c = EvolutionConfig(); assert c.max_cost_usd == 20.0 and c.reflection_model is None; print('OK')"` prints OK | PASS |
| `pytest tests/core/test_config.py -k phase13 -v` exits 0 with 5 tests passing | PASS (5 passed) |
| `pytest tests/core/test_config.py -v --tb=short` overall exits 0 | PASS (29 passed) |

### Task 2

| Criterion | Status |
|-----------|--------|
| `test -f evolution/core/cost_tracker.py` | PASS |
| `grep -n "class CostTracker:"` == 1 match | PASS (1) |
| `grep -n "class CostBudgetExceeded"` == 1 match | PASS (1) |
| `grep -n "def estimate_cost_usd"` == 1 match | PASS (1) |
| `grep -n "write_aborted_json"` >= 1 match | PASS (4) |
| `grep -n "from dspy.utils.usage_tracker import track_usage"` == 1 match | PASS (1) |
| `grep -n "import litellm"` == 1 match | PASS (1) |
| `pytest tests/core/test_cost_tracker.py -v` exits 0 with 3 tests passing | PASS (4 passed + 1 xfail per 13-01 W5 scaffold) |
| W4 `test_track_usage_false_warning` uses `pytest.warns(RuntimeWarning, match=r"track_usage")` + exits 0 | PASS |

### Plan-level

| Criterion | Status |
|-----------|--------|
| EvolutionConfig has max_cost_usd (default 20.0) + reflection_model (default None) | PASS |
| Layered resolution works (default → YAML → env → CLI) | PASS (5 config tests exercise all 4 layers for both fields) |
| New `evolution/core/cost_tracker.py` with CostTracker + estimate_cost_usd + CostBudgetExceeded | PASS |
| track_usage=False caller guard emits RuntimeWarning | PASS (test_track_usage_false_warning GREEN) |
| Wave 0 cost_tracker tests GREEN | PASS (4/4 explicit tests + 1 xfail W5 scaffold retained) |
| 5 new config tests GREEN | PASS |
| Existing config tests still pass (was 24) | PASS (now 29 total) |
| Existing 353 total tests still pass | PASS (364 passed + 1 xfail across non-RED suite; the "failures" in other files are Wave 0 RED stubs for 13-02/03/04/06/07/08 that this plan is not responsible for turning GREEN) |
| Folded todo `2026-05-07-max-cost-usd-and-reflection-model.md` closure conditions met (moved to done/) | PASS |

## Smoke Verification — estimate_cost_usd across project models

```
openai/gpt-4.1-mini   $0.000720  (no fallback, real litellm pricing)
openrouter/google/gemini-2.5-flash   $0.000800  (no fallback)
dashscope/qwen-plus   $0.000640  (no fallback)
```

All three default project models are recognized by `litellm.cost_per_token` natively — no fallback path exercised in the happy case. Fallback constants ($0.001/$0.003 per 1K) are conservative over-estimates chosen to fail-safe toward over-counting cost.

## Known Stubs

None. Every function body is fully implemented; no `pass` or `raise NotImplementedError`. The only deliberately-deferred behavior is the W5 poll-side empty-usage warning, which remains as a `@pytest.mark.xfail` per the 13-01 honest-gap scaffold.

## Threat Flags

No new threat-model surfaces beyond the plan's declared register (T-13-15 through T-13-18). `write_aborted_json` writes only the documented allow-listed keys plus caller-supplied `extra`/`kwargs` — per T-13-16 mitigation, the docstring explicitly warns callers (13-08) that `partial_diff` entries must not include full prompts.

## Self-Check: PASSED

Files verified to exist:
- evolution/core/cost_tracker.py: FOUND
- evolution/core/config.py (modified): FOUND
- tests/core/test_config.py (modified): FOUND
- .planning/todos/done/2026-05-07-max-cost-usd-and-reflection-model.md: FOUND
- .planning/todos/pending/2026-05-07-max-cost-usd-and-reflection-model.md: MOVED (git rename recorded)

Commits verified:
- 9883046: feat(13-05): extend EvolutionConfig with max_cost_usd + reflection_model
- 8fcbbb1: feat(13-05): add CostTracker + estimate_cost_usd for GEPA budget enforcement
- 873b5f7: chore(13-05): close folded todo — move max-cost-usd-and-reflection-model to done
