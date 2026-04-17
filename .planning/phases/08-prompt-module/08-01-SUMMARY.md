---
phase: 08-prompt-module
plan: 01
subsystem: evolution/prompts
tags: [dspy, prompt-module, gepa, tdd]
dependency_graph:
  requires: [prompt_loader, PromptSection]
  provides: [PromptModule, PromptSectionSignature]
  affects: [evolution/prompts/__init__.py]
tech_stack:
  added: []
  patterns: [dict-of-Predict, frozen-string-storage, active-section-switching]
key_files:
  created:
    - evolution/prompts/prompt_module.py
    - tests/prompts/test_prompt_module.py
  modified:
    - evolution/prompts/__init__.py
decisions:
  - "Frozen sections stored as plain instruction strings instead of Predict objects to prevent DSPy named_parameters() discovery"
metrics:
  duration: "~3 min"
  completed: "2026-04-17T14:31:00Z"
  tasks: 2
  files: 3
---

# Phase 08 Plan 01: PromptModule Summary

**One-liner:** DSPy module wrapping prompt sections with per-section GEPA optimization via active/frozen Predict switching and plain-string frozen storage

## What Was Built

PromptModule is a DSPy Module that wraps hermes-agent's prompt sections as individually optimizable parameters. Only one section is active (discoverable by GEPA) at a time; others are stored as plain instruction strings, invisible to the optimizer. The frozen sections are concatenated and passed as read-only context via an InputField.

### Key Components

- **PromptSectionSignature** -- DSPy Signature with frozen_context, task_input, and output fields
- **PromptModule** -- DSPy Module with set_active_section(), forward(), _build_frozen_context(), get_evolved_sections()
- **14 unit tests** across 5 test classes covering construction, active switching, frozen context, forward pass, and evolved extraction

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] DSPy named_parameters() discovers underscore-prefixed dict Predict instances**
- **Found during:** Task 2
- **Issue:** The research document (08-RESEARCH.md) assumed `_frozen_predictors` (underscore-prefixed dict) would be hidden from DSPy's `named_parameters()`. Runtime testing showed DSPy 3.1.3 recurses into all dicts regardless of name prefix, discovering all Predict instances within.
- **Fix:** Changed frozen storage from `_frozen_predictors: dict[str, dspy.Predict]` to `_frozen_instructions: dict[str, str]` -- storing plain instruction strings instead of Predict objects. Predict instances are created on-demand when a section becomes active, and instructions are extracted back to strings when deactivated.
- **Files modified:** evolution/prompts/prompt_module.py, tests/prompts/test_prompt_module.py
- **Commit:** 0d0cb75

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Store frozen sections as plain strings, not Predict objects | DSPy 3.1.3 named_parameters() discovers Predict in underscore-prefixed dicts; plain strings are truly invisible |
| Create Predict on activation, destroy on deactivation | Ensures exactly one section Predict exists in discoverable dict at any time |

## Verification

```
.venv/bin/pytest tests/prompts/test_prompt_module.py -x -v  # 14 passed
.venv/bin/pytest tests/prompts/ -x                          # 23 passed (9 loader + 14 module)
python -c "from evolution.prompts import PromptModule"      # OK
```

## Commits

| Task | Hash | Message |
|------|------|---------|
| 1 (RED) | c2cea2c | test(08-01): add failing tests for PromptModule |
| 2 (GREEN) | 0d0cb75 | feat(08-01): implement PromptModule with per-section GEPA optimization |

## Self-Check: PASSED

All files found. All commits verified.
