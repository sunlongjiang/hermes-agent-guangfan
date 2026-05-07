---
created: 2026-05-07T07:53:18Z
title: Make JSONL loaders skip bad lines instead of aborting
area: evolution-core
files:
  - evolution/core/dataset_builder.py:62-75
  - evolution/core/dataset_builder.py:186-190
  - evolution/core/external_importers.py:185-188
---

## Problem

Dataset JSONL loaders abort on first malformed line:
- `EvalDataset.load` (line 62-75) — raises on first malformed line.
- `GoldenDatasetLoader.load` (line 186-190) — same pattern.
- Compare to `external_importers.py:185-188` — the importer DOES catch `json.JSONDecodeError` per-line and continue. **Inconsistent within the same module family.**

Realistic triggers:
- A power-loss / disk-full event during `EvalDataset.save()` produces a truncated last line that aborts all future loads.
- User-provided `golden.jsonl` files often have hand-edited last lines. One typo permanently breaks load.
- Phase 14 auto-importers will produce 100s of MB of JSONL — partial writes are realistic.

## Solution

- Wrap per-line `json.loads(line)` in `try/except json.JSONDecodeError` and increment a `skipped` counter.
- Log skip count (warn if > 5% of lines).
- Add `EvalDataset.load_strict()` for CI test fixture cases where strict validation is desired.

**Priority:** MED. Low-risk hygiene fix. Tracked under v2-STAB-01. Source: `.planning/codebase/CONCERNS.md` M7.
