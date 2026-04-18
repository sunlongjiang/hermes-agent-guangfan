---
phase: 09-prompt-evaluation
plan: 01
subsystem: evolution/prompts
tags: [dataset, tdd, behavioral-evaluation, prompt-sections]
dependency_graph:
  requires: [evolution/core/config.py, evolution/prompts/prompt_loader.py, dspy]
  provides: [PromptBehavioralExample, PromptBehavioralDataset, PromptDatasetBuilder]
  affects: [evolution/prompts/__init__.py]
tech_stack:
  added: []
  patterns: [per-section-weighted-generation, section_texts-injection]
key_files:
  created:
    - evolution/prompts/prompt_dataset.py
    - tests/prompts/test_prompt_dataset.py
  modified:
    - evolution/prompts/__init__.py
decisions:
  - "Mirrored ToolDatasetBuilder pattern exactly for consistency"
  - "Platform hints weight divided evenly with remainder to first keys"
  - "section_texts injection is optional in to_dspy_examples for flexibility"
metrics:
  duration: "4m 36s"
  completed: "2026-04-18T06:04:03Z"
  tasks_completed: 2
  tasks_total: 2
  test_count: 15
  lines_added: 728
---

# Phase 9 Plan 01: Prompt Behavioral Dataset Summary

TDD implementation of PromptBehavioralExample/Dataset dataclasses and PromptDatasetBuilder with D2 weighted per-section scenario generation (80 total: identity=20, memory=15, skills=15, platform=20, session=10).

## What Was Built

### PromptBehavioralExample
- `@dataclass` with fields: section_id, user_message, expected_behavior, difficulty, source
- `to_dict()` / `from_dict()` with unknown key filtering (mirrors ToolSelectionExample)

### PromptBehavioralDataset
- Train/val/holdout splits with JSONL persistence (`save()` / `load()`)
- `all_examples` property for concatenation
- `to_dspy_examples(split, section_texts=None)` -- converts to `dspy.Example` with optional `section_text` injection from a lookup dict

### PromptDatasetBuilder
- `SECTION_WEIGHTS` class constant with D2 allocation
- Nested `GenerateSectionScenarios(dspy.Signature)` with section_text, section_id, num_scenarios, difficulty_mix inputs
- `generate(sections)` -- per-section weighted generation with platform_hints weight distribution across sub-keys
- Two-stage JSON parsing (direct + regex fallback)
- Empty user_message filtering

## Task Commits

| Task | Type | Commit | Description |
|------|------|--------|-------------|
| 1 | RED | 98df71a | Failing tests for dataclass round-trip, JSONL, DSPy conversion, builder |
| 2 | GREEN | c0fe7b5 | Full implementation passing all 15 tests |

## Test Results

```
38 passed in 11.87s (all tests/prompts/)
15 passed in 9.36s (test_prompt_dataset.py only)
```

## Deviations from Plan

None - plan executed exactly as written.

## Decisions Made

1. **Platform hints weight distribution**: 20 scenarios divided evenly across N platform sub-keys, remainder distributed to first keys (e.g., 2 keys = 10 each)
2. **section_texts as Optional parameter**: Keeps to_dspy_examples compatible with both section-aware and section-agnostic evaluation modes
3. **Mirrored ToolDatasetBuilder pattern**: Used identical structure (nested Signature, ChainOfThought, _parse_json_array) for consistency

## Self-Check: PASSED
