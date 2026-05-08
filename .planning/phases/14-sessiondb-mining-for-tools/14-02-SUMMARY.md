---
phase: 14-sessiondb-mining-for-tools
plan: 02
subsystem: tool-dataset
tags: [phase-14, wave-1, data-contract, dataclass, jsonl-tolerance]
requires:
  - "evolution/tools/tool_dataset.py::ToolSelectionExample (pre-existing dataclass + filtered from_dict)"
provides:
  - "ToolSelectionExample.misselection_signals: list[str] — D-02 field"
  - "to_dict round-trip preserves misselection_signals"
  - "Legacy Phase 4 JSONL backward compat (missing key → default [])"
affects:
  - evolution/tools/tool_dataset.py (lines 47, 58, 70)
tech-stack:
  added: []
  patterns:
    - "dataclass field(default_factory=list) for mutable defaults"
    - "to_dict explicit per-field serialization"
    - "from_dict __dataclass_fields__ filter (unchanged — auto-defaults new fields)"
key-files:
  created: []
  modified:
    - evolution/tools/tool_dataset.py
decisions:
  - "Skipped Task 2.1 (RED test in tests/tools/test_session_split.py). Plan 01 owns creation of that stub file in a parallel Wave 1 worktree — the file does not exist in this worktree at execution time. Plan 02 files_modified correctly scopes to tool_dataset.py only. The RED gate for misselection_signals semantics is instead provided via an inline smoke script that was executed before the commit (5 invariants: field default, to_dict round-trip, from_dict round-trip, legacy JSONL default, default_factory list independence)."
  - "Did NOT touch ToolSelectionExample.from_dict — existing filter pattern on __dataclass_fields__ (line 76) already auto-handles missing keys with dataclass defaults, which is exactly the backward-compat mechanism D-02 requires."
  - "Did NOT touch ToolSelectionDataset.save/load (D-18 scope guard). Bad-line JSONL tolerance is Plan 04's scope via a new _load_jsonl_skip_bad helper."
metrics:
  duration: ~15 min
  completed: 2026-05-08
---

# Phase 14 Plan 02: ToolSelectionExample misselection_signals (D-02) Summary

Added `misselection_signals: list[str]` field to `ToolSelectionExample`, with explicit
`to_dict` serialization and automatic legacy JSONL backward compat via the existing
`__dataclass_fields__` filter in `from_dict`. Scope strictly bounded to the dataclass
surface — no imports added, no `ToolSelectionDataset.save/load` modifications, no new
helpers.

## Tasks Executed

| Task | Name                                                                 | Status        | Commit    | Files                             |
| ---- | -------------------------------------------------------------------- | ------------- | --------- | --------------------------------- |
| 2.1  | Replace Plan 01 stub `test_signals_union`                            | **Skipped**   | —         | (deferred — see Deviations)       |
| 2.2  | Add `misselection_signals` field + to_dict                           | Complete      | `f6a9e32` | `evolution/tools/tool_dataset.py` |
| 2.3  | Backward-compat verification (tool suite + simulated legacy reload)  | Complete      | —         | (verification only)               |

## One-liner

D-02 data contract: `ToolSelectionExample` now carries `misselection_signals`
(subset of `{error_retry, user_correction, oracle_disagreement}`), defaulting
empty for synthetic/golden examples; old Phase 4 JSONL auto-compatible through
pre-existing `from_dict` filter.

## What Changed

### `evolution/tools/tool_dataset.py` (3 hunks, +5 lines, 0 deletions)

1. **Docstring (line 47):** Added one entry under `Args:` describing
   `misselection_signals` — subset of signal-source strings, empty for
   synthetic / golden examples, per D-02.

2. **Dataclass field (line 58):** After `source: str = "synthetic"`, appended
   `misselection_signals: list[str] = field(default_factory=list)`.

3. **`to_dict` (line 70):** Appended `"misselection_signals": self.misselection_signals,`
   to the returned dict, preserving field-definition-order key sequence.

### Explicitly NOT Changed

- `ToolSelectionExample.from_dict` (line 75-76) — the existing
  `cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})` pattern
  **already** auto-populates missing `misselection_signals` with the dataclass
  default (`[]`) when loading legacy Phase 4 JSONL. Modifying `from_dict` here
  would be redundant and is called out in 14-PATTERNS.md lines 432-435 as
  forbidden.
- `ToolSelectionDataset.save/load` (lines 90-128) — D-18 scope guard: JSONL
  bad-line tolerance belongs to Plan 04's `_load_jsonl_skip_bad` helper.
- `ToolDatasetBuilder` — no call-site updates needed; new field defaults to
  `[]` for all synthetic examples automatically.
- No new imports, no changes to `pyproject.toml`.

## Verification

### Direct field semantics (inline smoke, pre-commit)

5 invariants asserted via Python one-liner with the modified dataclass:

1. `ToolSelectionExample(..., misselection_signals=["error_retry", "user_correction"])`
   creates the instance with the expected list.
2. `to_dict()` serializes the key with the full list intact.
3. `from_dict(to_dict(ex))` round-trip preserves the list identity.
4. Legacy dict (no `misselection_signals` key) deserializes with
   `misselection_signals == []`.
5. `default_factory=list` produces independent lists — mutating one instance's
   list does not affect another (regression guard against `default=[]` mistake).

### Legacy Phase 4 JSONL simulation (Task 2.3 supplement)

Real `datasets/tools/train.jsonl` does not exist in this worktree, so the
literal plan command short-circuits on the guard `test -f datasets/tools/train.jsonl`.
Instead, the verification simulated the scenario in a `tempfile.TemporaryDirectory`:

- Wrote 5 JSONL records per split (train / val / holdout) with the **old** schema
  (no `misselection_signals` key).
- `ToolSelectionDataset.load(tmp)` returned 5 examples per split; every
  `ex.misselection_signals == []`.
- Re-saved via `.save()`, then re-loaded — new JSONL contains the key;
  load still returns `misselection_signals == []` for all records.

This verifies the full **JSONL → dataclass → JSONL** round-trip, not just the
in-memory dataclass round-trip.

### Regression

`.venv/bin/pytest tests/tools/ --ignore=tests/tools/test_secret_patterns_v2.py -q --tb=no`
→ **137 passed** (all pre-existing Phase 4/5/13 + current Wave 0 tool tests
unaffected). 0 failed, 0 errors.

`test_tool_dataset.py` specifically (the class owning `ToolSelectionExample`
coverage) → 16 passed, no changes needed to its assertions because the
`round_trip_serialization` test already passes with the new field implicitly
(default `[]` round-trips cleanly).

## Deviations from Plan

### Rule 3 (unblock) — Task 2.1 skipped

**Found during:** initial context load, before any source edits.

**Issue:** Task 2.1 instructs the executor to replace the `pytest.skip(...)`
stub for `test_signals_union` inside `tests/tools/test_session_split.py`.
That test file is a **Wave 0 stub created by Plan 01** of this same phase. In
the parallel Wave 1 execution model, Plan 01 and Plan 02 run in **independent
worktrees** and land their commits concurrently — so the stub file does
not yet exist on the Plan 02 worktree branch at execution time:

```
$ ls tests/tools/test_session_split.py
ls: cannot access 'tests/tools/test_session_split.py': No such file
```

**Consistency check with plan contract:** Plan 02's frontmatter
`files_modified: [evolution/tools/tool_dataset.py]` already scopes this plan
to the dataclass module only, and `must_haves.truths[3]` states explicitly
"两 plan 各自只改自己的目标文件，无 files_modified 冲突." Writing to
`tests/tools/test_session_split.py` here would **break** that contract by
creating a cross-plan `files_modified` overlap and forcing a merge conflict at
Wave 1 integration.

**Fix:** Honored `files_modified` and skipped Task 2.1. Substituted the RED
gate semantics with an inline 5-invariant smoke script that exercises the exact
field contract Task 2.1 would have asserted (field creation, to_dict key,
from_dict round-trip, legacy backward compat, default_factory independence).
The smoke script ran against the unmodified dataclass first (confirmed
`TypeError: unexpected keyword 'misselection_signals'` — RED), then against the
modified dataclass (GREEN).

**Plan 01's responsibility:** Plan 01 must produce `test_signals_union` in its
stub form (pytest.skip) OR Plan 01's own executor may write the real assertion
directly since Plan 01 creates the file. Either way Plan 02's field landing
(this commit) precedes any test that depends on it, so Wave 1 merge order is
unaffected.

**No user permission needed** — this is Rule 3 scope-guard enforcement per
the plan's own `must_haves.truths[3]` and `files_modified` contract.

### None of Rules 1, 2, 4 triggered

No bugs found in scope. No missing critical functionality (the new field has
no downstream consumers yet — those are Plan 04's SessionToolMiner and the
session-aware evolve CLIs in Plan 05/06). No architectural decisions surfaced.

## Deferred Issues

None.

## TDD Gate Compliance

Plan frontmatter has `type: execute` (not `type: tdd`), so the plan-level
RED→GREEN→REFACTOR commit sequence is not required. Per-task TDD flags were
not set (`tdd` attribute absent on all three tasks). Task 2.1 would have been
a RED step for field semantics, but was skipped per the deviation above; the
inline smoke script confirmed RED-before-GREEN manually.

## Files

- **Modified:** `evolution/tools/tool_dataset.py` (+5 lines: docstring row,
  field declaration, to_dict entry — spanning lines 47, 58, 70 in the new file)
- **Created:** none

## Commits

- `f6a9e32` — feat(14-02): add misselection_signals field to ToolSelectionExample (D-02)

## Success Criteria Check

- [x] D-02 field added and serialized via to_dict
- [x] Legacy Phase 4 JSONL auto-compatible (default `[]`) — verified via
      simulated reload
- [x] Tests/tools/ suite unchanged: 137 passed, 0 failed, 0 errors
- [x] ToolSelectionDataset.save/load source not modified (D-18)
- [x] No new imports, `pyproject.toml` untouched
- [x] `files_modified: [evolution/tools/tool_dataset.py]` contract honored
      (Task 2.1 skipped to avoid cross-plan overlap with Plan 01)

## Self-Check: PASSED

- File exists: `evolution/tools/tool_dataset.py` — FOUND
- Field present: `grep "misselection_signals: list\[str\] = field(default_factory=list)"` — FOUND
- to_dict key present: `grep '"misselection_signals": self.misselection_signals'` — FOUND
- Commit exists: `git log --oneline | grep f6a9e32` — FOUND
- SUMMARY file: `.planning/phases/14-sessiondb-mining-for-tools/14-02-SUMMARY.md` — FOUND (this file)
