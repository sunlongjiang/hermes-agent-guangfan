---
created: 2026-05-07T07:53:18Z
title: Persist per-tool regression rates in metrics.json
area: evolution-tools
files:
  - evolution/tools/tool_metric.py:72-187
  - evolution/tools/evolve_tool_descriptions.py:308-327
  - evolution/tools/evolve_tool_descriptions.py:365-378
---

## Problem

`CrossToolRegressionChecker` reports per-tool delta in a Rich table at run-time, but `metrics.json` records only aggregate `baseline_score` / `evolved_score`. There is no persistent per-tool record across runs.

Phase 13 fans out optimization to per-parameter (~50 tools × 3 avg params = ~150 optimizable units). Description theft (v2 research Pitfall 1: "tool X improved by stealing semantics from tool Y") becomes geometrically more likely.

Pitfall 10: dashboard must report distribution (min/p25/median/p75/max) and operate the regression gate on **p25**, not the mean.

## Solution

- Persist per-tool rates to `metrics.json`: `per_tool_baseline_rates`, `per_tool_evolved_rates` (dict keyed by tool name).
- Add a `param_consistency` LLM check in `ConstraintValidator` (Pitfall 1 prevention): scan all params + top-level for self-contradictions before fitness scoring.
- Cap optimization fan-out: `if len(params) > 5`, optimize 3 params at a time with rest frozen (Pitfall 1 prevention #3).

**Priority:** MED. **Phase 13 blocker** — this is also planned as Phase 16, but Phase 13 cannot ship without at least the persistence piece. Source: `.planning/codebase/CONCERNS.md` M3.
