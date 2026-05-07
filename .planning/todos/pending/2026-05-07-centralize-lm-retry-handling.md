---
created: 2026-05-07T07:53:18Z
title: Centralize LLM creation with retry and rate-limit handling
area: evolution-core
files:
  - evolution/core/fitness.py:75-83
  - evolution/core/external_importers.py:493-530
  - evolution/core/dataset_builder.py:126-133
---

## Problem

Code relies entirely on DSPy/LiteLLM defaults for rate-limit handling. DSPy 3.x has improved this, but there is no explicit `dspy.LM(..., max_retries=...)` or backoff_strategy configuration.

At Phase 14 scale (200-400 examples × N relevance-scoring + judge-scoring calls), a single 429 burst from the upstream API will cascade — no graceful degradation.

When Pitfall 11 plays out (reflection_lm cost spike), rate-limit hits become more likely as the optimizer sustains high QPS.

## Solution

- Centralize LM creation in `evolution/core/config.py`: add `EvolutionConfig.create_lm(model_name)` that injects `max_retries`, `temperature`, and `**get_lm_kwargs()`. Replace all bare `dspy.LM(...)` calls.
- Add exponential backoff wrapper around `RelevanceFilter.filter_and_score` per-candidate loop.
- Document recommended rate-limit headroom in README ("Use a key with ≥600 req/min for full eval-dataset runs").

**Priority:** MED. Tracked under Phase 14 readiness (high-volume mining). Source: `.planning/codebase/CONCERNS.md` M9.
