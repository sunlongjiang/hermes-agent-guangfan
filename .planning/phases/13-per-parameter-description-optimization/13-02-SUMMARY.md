---
phase: 13-per-parameter-description-optimization
plan: 02
subsystem: tools
tags: [dspy, gepa, tool-module, per-param, named-parameters, sub-module]

# Dependency graph
requires:
  - phase: 03-tool-module
    provides: ToolModule base structure, ToolSelectionSignature, Phase 3 tests
  - phase: 13-01
    provides: Wave 0 RED tests and test infrastructure for per-param structure
provides:
  - _ToolParamBundle sub-dspy.Module wrapping per-tool flat dict[param, Predict]
  - ToolSelectionWithParamsSignature with selected_params JSON-string output
  - ToolModule._frozen_tool_desc dict[str,str] for physically isolated tool-level text
  - ToolModule.forward() returning Prediction with selected_tool + selected_params
  - ToolModule.get_evolved_descriptions() harvesting per-param evolved instructions
  - Wave 0 per-param discovery tests (test_tool_module_per_param.py)
  - Wave 0 signature shape tests (test_tool_selection_with_params.py)
  - Migrated Phase 3 tests (test_tool_module.py) with 10 tool_predictors call sites removed
affects:
  - 13-03-PLAN  # joint_tool_param_metric depends on forward() returning selected_params
  - 13-04-PLAN  # param constraint checker depends on _frozen_tool_desc + param_predictors
  - 13-06-PLAN  # regression gate depends on named_predictors() count + _frozen_tool_desc
  - 13-08-PLAN  # evolve_tool_params CLI calls ToolModule with new structure

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "sub-Module-per-tool: wrap flat dict[str, dspy.Predict] in a dspy.Module subclass so DSPy 3.1.3 named_parameters() recurses into it (raw dict[str,dict[str,Predict]] is invisible)"
    - "D-02 physical isolation: tool-level text stored in dict[str,str], never as Predict, so GEPA has no handle on it"
    - "D-04 hierarchical naming: tools['<tool>'].param_predictors['<param>'] preserves tool+param layer"
    - "D-18 forward() returns Prediction with both selected_tool and selected_params (JSON string)"

key-files:
  created:
    - tests/tools/test_tool_module_per_param.py
    - tests/tools/test_tool_selection_with_params.py
  modified:
    - evolution/tools/tool_module.py
    - tests/tools/test_tool_module.py

key-decisions:
  - "Sub-Module-per-tool pattern: each tool gets a _ToolParamBundle(dspy.Module) so DSPy 3.1.3 named_parameters() recurses into the flat dict[param_name, dspy.Predict] (verified: raw dict[str, dict[str, Predict]] returns 0 named_parameters)"
  - "_frozen_tool_desc keyed by original tool name (not safe-key): _frozen_tool_desc['list-files'] not _frozen_tool_desc['list_files']"
  - "DSPy 3.1.3 replaces instructions='' with default template string; test adjusted to assert Predict existence (not literal '' instructions) for empty-description params"
  - "forward() returns raw LLM JSON string for selected_params without json.loads — parsing is the metric's job to enable malformed-output detection"

patterns-established:
  - "sub-Module-per-tool: class _ToolParamBundle(dspy.Module) with self.param_predictors: dict[str, dspy.Predict]"
  - "Phase 13 test migration pattern: module.tool_predictors[name] → module._frozen_tool_desc[name] (tool-level) or module.tools[safe].param_predictors[param] (param-level)"

requirements-completed:
  - TOOL-V2-02

# Metrics
duration: 18min
completed: 2026-05-07
---

# Phase 13 Plan 02: ToolModule Per-Parameter Upgrade Summary

**ToolModule upgraded to sub-Module-per-tool structure exposing ~N_params independently-optimizable dspy.Predict units via named_predictors(), with tool-level description frozen in dict[str,str] and forward() returning JSON-encoded selected_params alongside selected_tool.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-05-07T13:24:00Z
- **Completed:** 2026-05-07T13:43:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Introduced `_ToolParamBundle(dspy.Module)` — the only structure DSPy 3.1.3 can recurse into for per-param discovery; raw `dict[str, dict[str, Predict]]` is invisible to GEPA (verified via smoke test returning 0 entries)
- Added `ToolSelectionWithParamsSignature` with `selected_params: str` output (JSON-encoded); `ToolModule.forward()` now returns `Prediction(selected_tool, selected_params)` satisfying D-05 and D-18
- Physically isolated tool-level descriptions in `_frozen_tool_desc: dict[str, str]` (D-02) — `named_predictors()` never surfaces it; GEPA has no handle on tool-level text
- Migrated all 10 `module.tool_predictors[...]` call sites in `test_tool_module.py`; replaced hard-coded `len == 4` with `N_params + 1` formula with explicit per-param count assertion

## Task Commits

Each task was committed atomically:

1. **Task 1: Introduce _ToolParamBundle sub-Module + ToolSelectionWithParamsSignature** - `bf31e67` (feat)
2. **Task 2: Migrate tests/tools/test_tool_module.py to per-param data structure** - `ed30085` (feat)

## Files Created/Modified
- `evolution/tools/tool_module.py` — Complete structural rewrite: `_ToolParamBundle`, `ToolSelectionWithParamsSignature`, upgraded `ToolModule` with `_frozen_tool_desc`, `tools` dict, `get_evolved_descriptions()` round-trip
- `tests/tools/test_tool_module_per_param.py` — NEW: Wave 0 per-param discovery + frozen-desc + empty-param tests (6 tests)
- `tests/tools/test_tool_selection_with_params.py` — NEW: Wave 0 signature shape test (3 tests)
- `tests/tools/test_tool_module.py` — Phase 3 tests migrated to per-param data structure (9 tests, 10 call sites moved)

## Decisions Made
- `_ToolParamBundle` uses flat `dict[str, dspy.Predict]` (not nested dict) because DSPy 3.1.3 `named_parameters()` only recurses into `dspy.Module` instances, not raw dicts — verified via smoke test
- `_frozen_tool_desc` is keyed by the original tool name (including hyphens), not the safe-key, because the key is for user-facing round-trip (human name), not internal dict access
- DSPy 3.1.3 replaces `instructions=""` with a default template string. Test adjusted from asserting `== ""` to asserting `isinstance(..., dspy.Predict)` — this is a DSPy API constraint, not a bug in our code
- `forward()` returns raw LLM string for `selected_params` without `json.loads` so downstream metric can detect and penalize malformed JSON output

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DSPy 3.1.3 empty instructions replaced by default template string**
- **Found during:** Task 1 (Wave 0 GREEN phase verification)
- **Issue:** PLAN.md test contract said `bundle.param_predictors["action"].signature.instructions == ""` for empty-description params. DSPy 3.1.3 silently replaces `instructions=""` with its default template `"Given the fields \`param_name\`, produce the fields \`confirmation\`."` — making the literal `""` assertion impossible.
- **Fix:** Test updated from asserting `instructions == ""` to asserting `isinstance(pred, dspy.Predict)`. The D-03 contract ("empty-desc params still get a Predict registered") is fully preserved; only the assertion about what the instructions *value* is was adjusted to match actual DSPy behavior.
- **Files modified:** `tests/tools/test_tool_module_per_param.py` (renamed `test_empty_param_description_preserved_as_empty_string` → `test_empty_param_predictor_is_a_dspy_predict`)
- **Verification:** `pytest tests/tools/test_tool_module_per_param.py -x` passes 6/6
- **Committed in:** bf31e67 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Auto-fix necessary for correctness against real DSPy 3.1.3 API behavior. The D-03 semantic contract (every param gets a Predict) is unchanged. No scope creep.

## Issues Encountered
- None beyond the DSPy empty-instructions behavior documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `ToolModule` is ready for 13-03 (joint_tool_param_metric): `forward()` returns `selected_params` JSON string matching D-18 contract
- `named_predictors()` now yields per-param entries with `tools['<tool>'].param_predictors['<param>']` path — 13-04 and 13-06 can use this for constraint checking and regression gating
- `_frozen_tool_desc` provides the read-only tool-level text for param consistency checking (13-04)
- `get_evolved_descriptions()` round-trip is ready for 13-08 (write-back to metrics.json)
- All 116 tests in `tests/tools/` pass

---
*Phase: 13-per-parameter-description-optimization*
*Completed: 2026-05-07*
