---
phase: 09-prompt-evaluation
plan: 02
subsystem: evolution/prompts
tags: [metric, tdd, behavioral-evaluation, prompt-sections, gepa]
dependency_graph:
  requires: [evolution/core/fitness.py, evolution/core/config.py, evolution/prompts/prompt_dataset.py]
  provides: [PromptBehavioralMetric]
  affects: [evolution/prompts/__init__.py]
tech_stack:
  added: []
  patterns: [dual-path-metric, keyword-heuristic, llm-judge-reuse]
key_files:
  created:
    - evolution/prompts/prompt_metric.py
    - tests/prompts/test_prompt_metric.py
  modified:
    - evolution/prompts/__init__.py
decisions:
  - "Reused LLMJudge skill_text param for section text per Pitfall 4 (no interface change needed)"
  - "Keyword heuristic uses 0.3 base + 0.7*overlap (matching skill_fitness_metric pattern)"
  - "Fixed test_call_signature to mock LLMJudge (unmocked call would hang on real API)"
metrics:
  duration: "10m 31s"
  completed: "2026-04-18T06:17:23Z"
  tasks_completed: 2
  tasks_total: 2
  test_count: 14
  lines_added: 384
---

# Phase 9 Plan 02: Prompt Behavioral Metric Summary

TDD implementation of PromptBehavioralMetric callable class -- DSPy-compatible metric for prompt section optimization with dual-path scoring (fast keyword heuristic for GEPA optimization loop, full LLMJudge for final evaluation) and PMPT-07 feedback propagation.

## What Was Built

### PromptBehavioralMetric

- Callable class with `__call__(example, prediction, trace=None) -> float`
- Returns 0.0 for empty/None/whitespace-only agent output
- **Heuristic path** (trace is not None): keyword overlap scoring (0.3 base + 0.7 * overlap ratio), no LLM call -- used during GEPA optimization loops for speed
- **Full scoring path** (trace is None): delegates to `LLMJudge.score()` returning `FitnessScore.composite` (correctness 0.5 + procedure_following 0.3 + conciseness 0.2)
- Maps `section_text` to LLMJudge's `skill_text` parameter (Pitfall 4 from RESEARCH.md)
- Attaches `score.feedback` to `prediction.feedback` for GEPA reflective analysis (PMPT-07)
- Exported from `evolution.prompts` package

### Test Coverage

14 test functions across 5 test classes:
- `TestPromptBehavioralMetricInit` (3): construction, callable check, call signature
- `TestPromptBehavioralMetricEmpty` (3): empty string, None, whitespace-only
- `TestPromptBehavioralMetricHeuristic` (3): no judge call, returns float, keyword overlap ordering
- `TestPromptBehavioralMetricFull` (3): calls judge, skill_text mapping, composite return
- `TestPromptBehavioralMetricFeedback` (2): feedback attached, non-empty string

## Task Commits

| Task | Type | Commit | Description |
|------|------|--------|-------------|
| 1 | RED | 1ec8c91 | Failing tests for PromptBehavioralMetric (14 tests, stub class) |
| 2 | GREEN | c89bd5d | Full implementation passing all 14 tests + 38 existing |

## Test Results

```
52 passed in 10.63s (all tests/prompts/)
14 passed in 9.57s (test_prompt_metric.py only)
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed unmocked LLMJudge in test_call_signature**
- **Found during:** Task 2 (GREEN phase)
- **Issue:** `test_call_signature` called `metric(example, prediction, trace=None)` without mocking LLMJudge, causing the test to hang attempting a real API call
- **Fix:** Added `@patch("evolution.prompts.prompt_metric.LLMJudge")` decorator and mock FitnessScore return value
- **Files modified:** tests/prompts/test_prompt_metric.py
- **Commit:** c89bd5d (included in GREEN commit)

## Decisions Made

1. **Reused LLMJudge skill_text param**: Maps section_text to skill_text without requiring LLMJudge interface changes (per Pitfall 4)
2. **Heuristic base score 0.3**: Uses `0.3 + 0.7 * overlap` (slightly different from skill_fitness_metric's `0.3 + 0.7 * overlap`) for consistency with Phase 1 pattern
3. **Mock all LLMJudge paths in tests**: Every test that could reach the full scoring path mocks LLMJudge to prevent real API calls

## Self-Check: PASSED
