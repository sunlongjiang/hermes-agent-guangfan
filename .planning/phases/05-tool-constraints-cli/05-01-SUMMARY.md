---
phase: 05-tool-constraints-cli
plan: 01
subsystem: constraints
tags: [dspy, llm-judge, factual-accuracy, tool-descriptions, constraint-validation]

# Dependency graph
requires:
  - phase: 02-tool-loading
    provides: "ToolDescription dataclass, ConstraintResult, ConstraintValidator._check_size()"
provides:
  - "ToolFactualChecker class for factual accuracy validation of evolved tool descriptions"
  - "_parse_bool helper for parsing LLM boolean outputs"
  - "Verified ConstraintValidator._check_size() reuse for tool_description and param_description"
affects: [05-tool-constraints-cli plan 02, tool evolution CLI pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns: ["LLM-based factual accuracy checking via DSPy ChainOfThought", "Conservative boolean parsing for LLM outputs"]

key-files:
  created:
    - evolution/tools/tool_constraints.py
    - tests/tools/test_tool_constraints.py
  modified: []

key-decisions:
  - "Conservative _parse_bool: only explicit truthy values (true/yes/1) return True, everything else False -- prevents false negatives in constraint checking"
  - "check_all() silently skips evolved tools without original counterpart -- new tools cannot be factually checked"

patterns-established:
  - "_parse_bool pattern: defensive LLM boolean output parsing for constraint checkers"
  - "ToolFactualChecker pattern: nested DSPy Signature + ChainOfThought for tool-level constraint checking"

requirements-completed: [TOOL-09, TOOL-10]

# Metrics
duration: 16min
completed: 2026-04-16
---

# Phase 5 Plan 01: Tool Constraints Summary

**ToolFactualChecker with LLM-based false-claim detection using DSPy ChainOfThought, plus verified size constraint reuse for tool/param descriptions**

## Performance

- **Duration:** 16 min
- **Started:** 2026-04-16T15:17:40Z
- **Completed:** 2026-04-16T15:33:40Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- ToolFactualChecker class with FactualCheckSignature inner DSPy Signature for LLM-based factual accuracy checking
- _parse_bool helper function with conservative boolean parsing (defense against T-05-01 tampering threat)
- check() method for single-tool factual validation, check_all() for batch validation with name-based matching
- Verified ConstraintValidator._check_size() correctly gates tool_description (500 chars) and param_description (200 chars)
- 21 passing tests covering all code paths

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests** - `42b9dd5` (test)
2. **Task 1 GREEN: ToolFactualChecker implementation** - `0556aaa` (feat)

_TDD task with RED/GREEN commits._

## Files Created/Modified
- `evolution/tools/tool_constraints.py` - ToolFactualChecker class with FactualCheckSignature, check(), check_all(), and _parse_bool helper (146 lines)
- `tests/tools/test_tool_constraints.py` - 21 tests: _parse_bool variants, check() pass/fail, check_all() batch/unmatched, size constraint reuse (233 lines)

## Decisions Made
- Conservative _parse_bool: only explicit truthy values (true/yes/1) return True. This aligns with threat model T-05-01 (tampering mitigation) -- better to reject a valid evolution than accept a false claim.
- check_all() silently skips evolved tools not found in originals. New tools have no baseline for factual comparison.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ToolFactualChecker ready for Plan 02 CLI pipeline integration
- ConstraintValidator._check_size() verified reusable for tool descriptions
- Both TOOL-09 (factual accuracy) and TOOL-10 (size constraints) requirements satisfied

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 05-tool-constraints-cli*
*Completed: 2026-04-16*
