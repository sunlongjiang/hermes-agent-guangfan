---
phase: 19-sessiondb-behavioral-mining-for-prompts
plan: 01
subsystem: prompts
tags:
  - prompt
  - dataset
  - schema
  - mining
requirements:
  - PMPT-V2-04
dependencies:
  requires: []
  provides:
    - "PromptBehavioralExample.mining_signals: list[str] (default [])"
    - "PromptBehavioralExample.source enum extension: 'session'"
    - "module-level _normalize_task_hash(task)"
    - "module-level _hash_to_split(h)"
  affects:
    - "Plan 02 (SessionPromptMiner): imports PromptBehavioralExample + helpers"
    - "Plan 04 (evolve_prompt_sections --session-source union): imports _normalize_task_hash for D-16 dedup"
tech_stack:
  added: []
  patterns:
    - "dataclass + field(default_factory=list) backward-compat extension"
    - "module-level helper pair (hash + bucket) reusable by sibling miners"
    - "byte-for-byte mirror of Phase 14 evolution/tools/session_miner.py:50-63"
key_files:
  created: []
  modified:
    - "evolution/prompts/prompt_dataset.py (added mining_signals field + 2 module-level helpers + import hashlib)"
    - "tests/prompts/test_prompt_dataset.py (added TestHashBucketHelpers + 6 mining_signals tests)"
decisions:
  - "[D-02] mining_signals defaults to [] via field(default_factory=list) so pre-Phase-19 JSONL loads unchanged"
  - "[D-02] source remains plain str (no Enum) to preserve from_dict/to_dict round-trip on legacy data"
  - "[D-10] only mining_signals added — no session_path / turn_idx / verdict_rationale (PII + schema simplicity)"
  - "[D-15] helpers placed at module level above @dataclass blocks so both SessionPromptMiner and evolve_prompt_sections.py union can import without circular dependency"
  - "[D-24] PromptBehavioralDataset.save/load LEFT UNCHANGED (explicit context constraint: 'v2-STAB-01 独立清理范围')"
metrics:
  duration: ~18 minutes
  completed: 2026-05-18
  tasks_completed: 2
  files_created: 0
  files_modified: 2
  prompt_tests_before: 110 passed, 1 skipped (Phase 18 baseline)
  prompt_tests_after: 127 passed, 1 skipped (+12 new tests, +5 net new because 1 existing was tightened, 1 already counted earlier)
  regression: zero
---

# Phase 19 Plan 01: Dataset Schema Extension Summary

**One-liner:** Extends `PromptBehavioralExample` with `mining_signals: list[str]` and exposes hash-bucket helpers at module level — backward-compatible dataclass extension + byte-for-byte mirror of Phase 14 helpers (D-02 + D-15).

## What Was Built

Two surgical edits to `evolution/prompts/prompt_dataset.py` that make the file the shared schema + dedup utility module for the rest of Phase 19:

1. **mining_signals field** added at end of the `PromptBehavioralExample` dataclass with `field(default_factory=list)`. `to_dict()` now emits 6 keys; `from_dict()` keeps the existing `__dataclass_fields__` filter so pre-Phase-19 JSONL automatically loads with `mining_signals=[]`. Docstring extended to document the `source: 'synthetic' | 'golden' | 'session'` enum (per D-02 / D-10).

2. **Module-level helpers** `_normalize_task_hash(task)` and `_hash_to_split(h)` inserted after `console = Console()` and before `# ── Data Classes ──`. Bodies are byte-for-byte identical to `evolution/tools/session_miner.py:50-63` (Phase 14). A new `import hashlib` was added (already had `import json` + `import re`).

These two additions are the cross-plan contract: Plan 02 imports `PromptBehavioralExample` to instantiate session-mined records; Plan 04 imports `_normalize_task_hash` at the `--session-source` union site for D-16 hash dedup.

## Files Modified

| File | Change | Lines |
|------|--------|-------|
| `evolution/prompts/prompt_dataset.py` | + `import hashlib` (L13)<br>+ `_normalize_task_hash` (L32-41)<br>+ `_hash_to_split` (L43-55)<br>+ `mining_signals` field on dataclass (L54)<br>+ updated docstrings (L40-46 + L72-74)<br>+ `to_dict` 6th key (L64) | +37 / −2 |
| `tests/prompts/test_prompt_dataset.py` | + `TestHashBucketHelpers` class (6 tests, L20-83)<br>+ 5 new mining_signals tests inside `TestPromptBehavioralExample` (L141-200)<br>+ updated `test_to_dict_contains_all_fields` to expect 6 keys | +134 / −2 |

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `588bf93` | test | RED for Task 1.1 — failing mining_signals tests (6 new + 1 tightened) |
| `140f22a` | feat | GREEN for Task 1.1 — mining_signals field + docstring extension |
| `f617def` | test | RED for Task 1.2 — failing helper-import tests (6 tests with ImportError) |
| `5a363b7` | feat | GREEN for Task 1.2 — `_normalize_task_hash` + `_hash_to_split` + `import hashlib` |

## Plan-defined Verify Output

### Task 1.1 verify automated
```
PASS
```
T1 (legacy JSONL → mining_signals=[]), T2 (to_dict has 6 keys), T3 (construct with signals), T4 (from_dict drops unknown keys) — all pass.

### Task 1.2 verify automated
```
PASS
Distribution: {'train': 675, 'val': 163, 'holdout': 162}
```
T1 (whitespace+case normalize), T2 (empty/None safe), T3 (1000-input bucket distribution 67.5%/16.3%/16.2% ≈ 70/15/15), T4 (determinism) — all pass.

### Byte-identity vs Phase 14 (Plan D-15 mirror requirement)
`tests/prompts/test_prompt_dataset.py::TestHashBucketHelpers::test_helpers_byte_identical_to_session_miner` passes — for 5 sample strings (whitespace-heavy English, plain English, Chinese, empty, whitespace-only) both `_normalize_task_hash` and `_hash_to_split` outputs equal between `evolution.prompts.prompt_dataset` and `evolution.tools.session_miner`. Side-by-side `sed` diff of the function bodies (excluding docstrings) shows zero textual difference.

## Backward Compatibility Confirmation

```python
PromptBehavioralExample.from_dict({
    'section_id': 'memory_guidance',
    'user_message': 'm',
    'expected_behavior': 'e',
    'difficulty': 'easy',
    'source': 'synthetic',  # legacy 5-key dict, no mining_signals
}).mining_signals == []  # True
```

The existing line `return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})` (unchanged) handles both omitted-key (defaults to `[]`) and unknown-key (silently dropped) cases. Phase 9 datasets on disk continue to load without migration.

## Downstream Plan Anchors

| Downstream | Import line | Used for |
|------------|-------------|----------|
| Plan 02 `evolution/prompts/session_prompt_miner.py` | `from evolution.prompts.prompt_dataset import PromptBehavioralExample` | dataclass instantiation with `mining_signals=[c.signal]` and `source="session"` per D-02 |
| Plan 02 `evolution/prompts/session_prompt_miner.py` | `from evolution.prompts.prompt_dataset import _normalize_task_hash, _hash_to_split` | mining-time dedup + bucket assignment per D-15 |
| Plan 04 `evolution/prompts/evolve_prompt_sections.py` | `from evolution.prompts.prompt_dataset import _normalize_task_hash` | D-16 hash-dedup at `--session-source` union site (session-wins-on-collision) |

## Deviations from Plan

None — plan executed exactly as written.

The action specs in Task 1.1 / 1.2 were followed verbatim (field placement, docstring text, helper bodies). The only minor judgement call was the test-side update: `test_to_dict_contains_all_fields` already existed and asserted 5 keys; per Rule 1 (the test reflected the now-obsolete schema) I tightened it to expect 6 keys at the same time as adding the 6 net-new mining_signals tests. This is bundled inside the Task 1.1 RED commit (`588bf93`) and matches the plan's intent (D-02 schema evolution).

## Known Stubs

None. All new fields and helpers have real implementations and are covered by tests.

## Threat Surface Scan

No new threat surface beyond the plan's `<threat_model>`. Schema-only addition (`mining_signals`) reuses the existing `__dataclass_fields__` filter; helpers are pure functions with no I/O. No new network endpoints, auth paths, file access, or trust-boundary changes. The plan's STRIDE register (T-19-01-S/T/I mitigated by reusing the existing filter; T-19-01-D/E accepted as O(len) pure-compute) remains accurate.

## Test Suite State

- `tests/prompts/`: **127 passed, 1 skipped** (Phase 18 baseline: 110 passed, 1 skipped → +12 new tests on top of the 5 tightened/replaced).
- Zero regression in any other prompt test.
- DSPy/Click/Rich versions untouched; no new dependencies declared.

## Self-Check: PASSED

- `evolution/prompts/prompt_dataset.py` exists (modified): FOUND
- `tests/prompts/test_prompt_dataset.py` exists (modified): FOUND
- Commit `588bf93`: FOUND in `git log --all`
- Commit `140f22a`: FOUND in `git log --all`
- Commit `f617def`: FOUND in `git log --all`
- Commit `5a363b7`: FOUND in `git log --all`
- All four success criteria (6-field dataclass / module helpers exported / save+load unchanged / 110+ prompt tests pass) verified above.
