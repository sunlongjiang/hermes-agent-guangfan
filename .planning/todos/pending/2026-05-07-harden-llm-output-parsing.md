---
created: 2026-05-07T07:53:18Z
title: Harden LLM-output parsing against format drift
area: evolution-core
files:
  - evolution/core/external_importers.py:546-600
  - evolution/core/dataset_builder.py:137-145
  - evolution/core/fitness.py:139-146
---

## Problem

Parse-failure paths silently degrade quality:
- `_parse_score` returning 0.5 on failure means a model that breaks JSON output gets a middling score instead of 0 — GEPA's reflective trace gets misleading signal.
- `_parse_scoring_json` returns `None` on failure → the importer just increments `errors` counter and continues. Error rate is reported but not used to halt or trigger re-run.

At v2 dataset scale (Phase 14: 200-400 examples), a 30% silent parse-failure rate is plausible and would drag GEPA toward arbitrary directions. Pitfall 11: reflection_lm cost is super-linear at v2 scale; wasting it on parse-failure-induced noise is doubly expensive.

## Solution

- Use `dspy.OutputField(desc=..., type=float)` typed outputs in DSPy 3.x where supported, replacing manual parse logic.
- Add an error-rate threshold: if `errors / total > 0.2`, halt and emit a clear "LLM output format may have drifted, re-run with verbose mode" message instead of silently completing.
- Replace 0.5 default in `_parse_score` with **0.0** + log to `metrics.json["parse_failures"]`. Misses that produce 0 are visible; misses that produce 0.5 are invisible.

**Priority:** MED. Tracked under Phase 13 (new metric design) and Phase 14 (mining at scale). Source: `.planning/codebase/CONCERNS.md` M4.
