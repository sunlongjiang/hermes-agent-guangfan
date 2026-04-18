---
phase: 10-prompt-constraints-cli
plan: 01
subsystem: evolution/prompts
tags: [constraints, role-preservation, llm-judge, tdd]
dependency_graph:
  requires:
    - evolution/core/constraints.py (ConstraintResult, ConstraintValidator)
    - evolution/core/config.py (EvolutionConfig)
    - evolution/prompts/prompt_loader.py (PromptSection)
    - evolution/tools/tool_constraints.py (ToolFactualChecker pattern reference)
  provides:
    - evolution/prompts/prompt_constraints.py (PromptRoleChecker, _parse_bool)
    - tests/prompts/test_prompt_constraints.py (25 test methods)
  affects:
    - evolution/prompts/ (adds constraint gate for prompt evolution pipeline)
tech_stack:
  added: []
  patterns:
    - DSPy ChainOfThought for LLM-based role preservation validation
    - Conservative _parse_bool for untrusted LLM boolean output
key_files:
  created:
    - evolution/prompts/prompt_constraints.py
    - tests/prompts/test_prompt_constraints.py
  modified: []
decisions:
  - "Positive boolean direction: role_preserved=True -> passed=True (opposite of ToolFactualChecker's has_false_claims=True -> passed=False)"
  - "Copied _parse_bool verbatim from tool_constraints.py for consistent conservative parsing"
metrics:
  duration: "13 minutes"
  completed: "2026-04-18T07:42:26Z"
  tasks_completed: 1
  tasks_total: 1
  test_count: 25
  lines_added: 435
---

# Phase 10 Plan 01: Prompt Constraints Summary

LLM-based PromptRoleChecker validates evolved prompt sections maintain their functional role, with _parse_bool conservative parsing and growth constraint reuse from ConstraintValidator.

## Task Completion

| Task | Name | Type | Commits | Key Files |
|------|------|------|---------|-----------|
| 1 | PromptRoleChecker + _parse_bool + tests | auto (TDD) | `573f14c` (RED), `2ba3821` (GREEN) | `evolution/prompts/prompt_constraints.py`, `tests/prompts/test_prompt_constraints.py` |

## What Was Built

### PromptRoleChecker (`evolution/prompts/prompt_constraints.py`, 147 lines)

- **RoleCheckSignature**: DSPy Signature with `section_id`, `original_text`, `evolved_text` inputs and `role_preserved` (bool), `explanation` outputs
- **check()**: Single section validation via ChainOfThought LLM call, returns ConstraintResult
- **check_all()**: Batch validation matching sections by `section_id`, skips unmatched evolved sections
- **_parse_bool()**: Conservative boolean parser -- only `True`, `"true"`, `"yes"`, `"1"` return True

### Key Design: Positive Boolean Direction

Unlike ToolFactualChecker (`has_false_claims=True` -> FAIL), PromptRoleChecker uses `role_preserved=True` -> PASS. This positive direction is more natural for role preservation and matches the Signature's semantic intent.

### Test Coverage (`tests/prompts/test_prompt_constraints.py`, 288 lines, 25 tests)

- **TestParseBool** (14 tests): bool True/False, string variants, garbage, whitespace
- **TestPromptRoleChecker** (5 tests): check() pass/fail, check_all() matching/skipping, constraint_name consistency
- **TestGrowthConstraint** (6 tests): ConstraintValidator._check_growth() reuse at/within/exceeds 20%, _check_non_empty() pass/fail/whitespace

## Verification Results

- `python -m pytest tests/prompts/test_prompt_constraints.py -x -q`: 25 passed
- `from evolution.prompts.prompt_constraints import PromptRoleChecker, _parse_bool`: OK
- All 9 acceptance criteria grep checks: PASS

## Deviations from Plan

None -- plan executed exactly as written.

## Decisions Made

1. **Positive boolean direction**: `role_preserved=True` maps to `ConstraintResult(passed=True)`. This is the opposite of ToolFactualChecker's `has_false_claims=True` -> `passed=False`, but semantically clearer for the role preservation domain.

2. **Verbatim _parse_bool copy**: Identical to `tool_constraints.py` version for consistency across the codebase.

## Self-Check: PASSED

- [x] `evolution/prompts/prompt_constraints.py` exists
- [x] `tests/prompts/test_prompt_constraints.py` exists
- [x] `.planning/phases/10-prompt-constraints-cli/10-01-SUMMARY.md` exists
- [x] Commit `573f14c` (RED) found
- [x] Commit `2ba3821` (GREEN) found
