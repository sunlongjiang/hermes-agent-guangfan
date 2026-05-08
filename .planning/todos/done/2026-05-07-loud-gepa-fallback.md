---
created: 2026-05-07T07:53:18Z
title: Make GEPA-to-MIPROv2 fallback loud (record optimizer_used)
area: evolution-pipelines
files:
  - evolution/skills/evolve_skill.py:167-182
  - evolution/tools/evolve_tool_descriptions.py:196-206
  - evolution/prompts/evolve_prompt_sections.py:264-284
---

## Problem

All three pipelines wrap `dspy.GEPA(...)` in `try/except Exception` and fall back to `dspy.MIPROv2`. The exception message is printed in yellow and execution continues. MIPROv2 has different semantics (no reflective trace, no `reflection_lm`), so the resulting evolved artifact is qualitatively different but indistinguishable in `metrics.json` (which records `optimizer_model` but not the actually-used optimizer name).

The fix from commit `262af2a` was itself a reaction to a silent fallback. Future DSPy upgrades will fall into the same trap. Per v2 research Pitfall 12 prevention strategy: "Convert the silent fallback to LOUD — fail-fast unless `--allow-miprov2-fallback` flag set."

## Solution

- Add `--allow-miprov2-fallback` CLI flag (default off). Without it, re-raise the exception with a clear message including the original GEPA error.
- Record `optimizer_used: "gepa"|"miprov2"` in `metrics.json` so post-hoc audits can detect silent fallbacks in past runs.
- Add per-pipeline metric-signature unit tests (pattern already done for skill in `tests/core/test_config.py::test_skill_fitness_metric_is_5_param` — replicate for tool_selection_metric and prompt_behavioral_metric).

**Priority:** MED. Tracked under Phase 12 follow-up + Phase 13 prerequisite. Source: `.planning/codebase/CONCERNS.md` M2.
