---
phase: 03-tool-module
plan: 01
subsystem: evolution/tools
tags: [dspy-module, tool-description, gepa, tdd]
dependency_graph:
  requires: [tool_loader.py (Phase 2)]
  provides: [ToolModule, ToolSelectionSignature]
  affects: [Phase 03-02 evaluation, Phase 03-03 CLI]
tech_stack:
  added: []
  patterns: [per-tool dspy.Predict wrapping, frozen schema dict, safe_name sanitization]
key_files:
  created:
    - evolution/tools/tool_module.py
    - tests/tools/test_tool_module.py
  modified: []
decisions:
  - Used dspy.Signature with instructions parameter for per-tool predictors (follows SkillModule pattern)
  - Stored frozen schema in plain dict (_frozen_tools) to keep it invisible to named_parameters()
  - ToolSelectionSignature as module-level class (not nested) since it is a public export
metrics:
  duration: 486s
  completed: 2026-04-16T07:18:10Z
  tasks: 2/2
  files_created: 2
  files_modified: 0
  test_count: 9
  test_pass: 9
requirements:
  - TOOL-03
  - TOOL-04
---

# Phase 03 Plan 01: ToolModule DSPy Module Summary

ToolModule wraps hermes-agent tool descriptions as GEPA-optimizable dspy.Predict instances with frozen schema isolation, enabling joint tool description optimization.

## What Was Built

- **`evolution/tools/tool_module.py`** (103 lines): Core DSPy module that accepts `list[ToolDescription]` and creates per-tool `dspy.Predict` instances whose signature instructions hold the description text. GEPA discovers these via `named_predictors()` and can independently mutate each tool's description.

- **`tests/tools/test_tool_module.py`** (169 lines): 9 unit tests across 3 test classes validating predictor count, instruction matching, forward prediction, empty description defaults, hyphenated name safety, frozen field isolation, and evolved description preservation.

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Per-tool `dspy.Predict` with `Signature(instructions=desc)` | Each tool description becomes an independently optimizable parameter via DSPy's parameter system |
| `_frozen_tools` as plain dict (not dspy attribute) | Ensures `named_parameters()` cannot discover schema fields -- only description text is optimizable |
| `safe_name = name.replace("-", "_")` | Python dict keys cannot contain hyphens; consistent with DSPy module naming |
| Default `"Tool: {name}"` for empty descriptions | Ensures GEPA always has text to work with (threat T-03-03 mitigation) |
| `ToolSelectionSignature` as module-level class | Public export needed by downstream plans; nested class pattern reserved for private signatures |

## Task Execution

| Task | Name | Type | Commit | Files |
|------|------|------|--------|-------|
| 1 | Write failing tests (RED) | test | `9296c5e` | tests/tools/test_tool_module.py |
| 2 | Implement ToolModule (GREEN) | feat | `acdf179` | evolution/tools/tool_module.py, tests/tools/test_tool_module.py |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed forward() test mock strategy**
- **Found during:** Task 2 (GREEN verification)
- **Issue:** `patch.object(module.selector, "__call__")` did not intercept DSPy's internal call routing; the selector still attempted an LLM call
- **Fix:** Changed mock target to `forward` method: `patch.object(module.selector, "forward", return_value=mock_result)`
- **Files modified:** tests/tools/test_tool_module.py
- **Commit:** `acdf179`

**2. [Rule 3 - Blocking] Installed dspy dependency**
- **Found during:** Task 1 (RED verification)
- **Issue:** `dspy>=3.0.0` was declared in pyproject.toml but not installed in `.venv`; tests could not import dspy
- **Fix:** Ran `pip3 install "dspy>=3.0.0"` in the project venv
- **Files modified:** none (runtime dependency)
- **Commit:** N/A (environment setup)

## Verification Results

1. `python -m pytest tests/tools/test_tool_module.py -x -v` -- 9/9 passed
2. `python -m pytest tests/ -x` -- 188/188 passed (full suite green)
3. `from evolution.tools.tool_module import ToolModule, ToolSelectionSignature` -- import OK
4. Integration check: `ToolModule([single_tool])` produces 2 predictors, 1 evolved description

## Self-Check: PASSED

All created files exist. All commit hashes verified.
