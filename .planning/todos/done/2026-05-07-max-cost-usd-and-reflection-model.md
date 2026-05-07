---
created: 2026-05-07T07:53:18Z
title: Add max_cost_usd cost-cap + cheaper reflection_model slot
area: evolution-core
files:
  - evolution/core/config.py:11-49
  - evolution/tools/evolve_tool_descriptions.py:188
---

## Problem

Today: ~50 tools × 1 description each = 50 optimizable units. `max_metric_calls=iterations * 50` is acceptable (≈$2-10 per run per CLAUDE.md).

Phase 13: ~50 tools × 3 avg params + 50 top-level = ~200 units. Naively reusing `iterations * 50` gives 4× the GEPA budget — and per-param GEPA candidates each invoke `reflection_lm` (v2 research Pitfall 11 — at the expensive `optimizer_model`). Total cost projection: **$30-100 per run**, breaking the documented $2-10 cost claim.

Combinatorial explosion (Pitfall 1): a tool with 8 params × N candidates = N⁸ design space.

No `max_cost_usd` halt mechanism exists today — runs continue until `max_metric_calls` exhausted regardless of token spend.

## Solution

- Add `EvolutionConfig.max_cost_usd: float = 20.0` field. Track token usage per LLM call (DSPy 3.x emits usage in result objects), abort optimization when threshold crossed.
- Add `reflection_model: Optional[str] = None` field — when set, use cheaper model for reflection (Pitfall 11 prevention).
- For Phase 13: cap params optimized per generation to 3 (frozen others) when `len(params) > 5` (Pitfall 1 prevention #3).
- Per-phase cost projection required in plan files (Pitfall 11).

**Priority:** MED. **Phase 13 blocker** — Phase 13 plan must include cost projection and `max_cost_usd` integration. Source: `.planning/codebase/CONCERNS.md` M8.
