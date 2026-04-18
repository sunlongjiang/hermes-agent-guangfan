---
phase: 10-prompt-constraints-cli
plan: 02
subsystem: evolution/prompts
tags: [cli, pipeline, gepa, per-section-optimization, tdd]
dependency_graph:
  requires:
    - evolution/prompts/prompt_loader.py (extract_prompt_sections, PromptSection)
    - evolution/prompts/prompt_module.py (PromptModule, set_active_section, get_evolved_sections)
    - evolution/prompts/prompt_dataset.py (PromptDatasetBuilder, PromptBehavioralDataset)
    - evolution/prompts/prompt_metric.py (PromptBehavioralMetric)
    - evolution/prompts/prompt_constraints.py (PromptRoleChecker)
    - evolution/core/constraints.py (ConstraintValidator)
    - evolution/core/config.py (EvolutionConfig)
  provides:
    - evolution/prompts/evolve_prompt_sections.py (main, evolve, _generate_diff)
    - tests/prompts/test_evolve_prompt_sections.py (6 test methods)
  affects:
    - evolution/prompts/__init__.py (added PromptRoleChecker export)
tech_stack:
  added: []
  patterns:
    - Per-section GEPA optimization with dataset filtering by section_id
    - Click CLI symmetric with evolve_tool_descriptions.py
key_files:
  created:
    - evolution/prompts/evolve_prompt_sections.py
    - tests/prompts/test_evolve_prompt_sections.py
  modified:
    - evolution/prompts/__init__.py
decisions:
  - "Per-section GEPA: each section gets its own filtered dataset and separate GEPA.compile() call"
  - "Baseline module created separately for holdout comparison (two PromptModule instances)"
  - "Constraint gate order: growth + non_empty per section, then role_preservation batch check"
metrics:
  duration: "5 minutes"
  completed: "2026-04-18T08:02:00Z"
  tasks_completed: 1
  tasks_total: 1
  test_count: 6
  lines_added: 772
---

# Phase 10 Plan 02: Prompt CLI Summary

End-to-end evolve_prompt_sections.py CLI wiring Phase 7-10 components into per-section GEPA optimization pipeline with constraint gating and holdout evaluation.

## Task Completion

| Task | Name | Type | Commits | Key Files |
|------|------|------|---------|-----------|
| 1 | evolve_prompt_sections.py CLI + evolve() + tests | auto (TDD) | `34bc4b8` (RED), `06504a1` (GREEN) | `evolution/prompts/evolve_prompt_sections.py`, `tests/prompts/test_evolve_prompt_sections.py`, `evolution/prompts/__init__.py` |

## What Was Built

### evolve_prompt_sections.py (504 lines)

- **Click CLI**: 5 options (--section, --iterations, --eval-source, --hermes-repo, --dry-run)
- **evolve()**: 11-step pipeline: config -> extract -> dry-run gate -> module -> dataset -> per-section GEPA -> extract evolved -> constraints -> holdout -> report -> save
- **Per-section optimization**: Filters dataset.train/val by section_id before each GEPA pass, creates temporary PromptBehavioralDataset per section
- **Constraint gate (per D4)**: growth + non_empty + role_preservation after GEPA, before holdout
- **GEPA -> MIPROv2 fallback**: Same pattern as evolve_tool_descriptions.py
- **_generate_diff()**: difflib.unified_diff on section text fields
- **Output**: evolved_sections.json, metrics.json, diff.txt saved to output/prompts/{timestamp}/

### Key Design: Per-Section Round-Robin

Unlike the tool CLI (joint optimization), the prompt CLI iterates over sections_to_optimize, calling set_active_section() + GEPA.compile() for each. The --section flag allows targeting a single section.

### Test Coverage (268 lines, 6 tests)

- **TestCLI** (2 tests): --help shows all 5 options, "Section ID to optimize" in help text
- **TestDryRun** (1 test): extracts sections, prints summary, does NOT call GEPA
- **TestEvolve** (2 tests): orchestration order verification, section filter with --section
- **TestModuleImportable** (1 test): main and evolve importable

### __init__.py Update

Added `PromptRoleChecker` import and export to `__all__`.

## Verification Results

- `python -m pytest tests/prompts/test_evolve_prompt_sections.py -x -q`: 6 passed
- `python -m pytest tests/prompts/ -x -q`: 83 passed (full prompt suite)
- `from evolution.prompts.evolve_prompt_sections import main, evolve`: OK
- All 12 acceptance criteria grep checks: PASS

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Test assertion for PromptModule call count**
- **Found during:** GREEN phase
- **Issue:** Test asserted PromptModule called once, but evolve() creates two instances (one for optimization, one for baseline holdout comparison)
- **Fix:** Changed assertion to `assert mock_module_cls.call_count == 2`
- **Files modified:** tests/prompts/test_evolve_prompt_sections.py

**2. [Rule 1 - Bug] Test assertion for set_active_section with --section filter**
- **Found during:** GREEN phase
- **Issue:** assert_called_once_with("memory_guidance") failed because baseline module also calls set_active_section during holdout eval (both modules share the same mock)
- **Fix:** Changed to check first call in call_args_list instead of assert_called_once_with
- **Files modified:** tests/prompts/test_evolve_prompt_sections.py

## Decisions Made

1. **Per-section GEPA optimization**: Each section gets its own filtered dataset and separate GEPA.compile() call, matching PromptModule.set_active_section() design.

2. **Separate baseline module for holdout**: Creates a fresh PromptModule(original_sections) for holdout comparison, ensuring evolved module's optimized parameters are compared against unmodified baseline.

3. **Constraint gate order (per D4)**: growth + non_empty checks per evolved section first, then PromptRoleChecker.check_all() batch check -- all after GEPA, before holdout.

## Self-Check: PASSED

- [x] `evolution/prompts/evolve_prompt_sections.py` exists (504 lines)
- [x] `tests/prompts/test_evolve_prompt_sections.py` exists (268 lines)
- [x] `evolution/prompts/__init__.py` updated with PromptRoleChecker
- [x] Commit `34bc4b8` (RED) found
- [x] Commit `06504a1` (GREEN) found
