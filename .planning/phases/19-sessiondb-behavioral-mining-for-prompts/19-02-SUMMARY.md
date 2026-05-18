---
phase: 19-sessiondb-behavioral-mining-for-prompts
plan: 02
subsystem: prompts
tags:
  - prompt
  - mining
  - dspy-judge
  - drift-detector
requirements:
  - PMPT-V2-04
dependencies:
  requires:
    - "Plan 19-01: PromptBehavioralExample.mining_signals + _normalize_task_hash + _hash_to_split"
  provides:
    - "SessionPromptMiner class (4 extractors + LLM judge + mine orchestration)"
    - "ConfirmBehavioralExample(dspy.Signature) — single-call 5-output judge"
    - "DetectUserCorrection(dspy.Signature) — LLM 二判 for keyword candidates"
    - "Candidate / Verdict dataclasses"
    - "DEFAULT_MULTIPLIER (4-key dict) + VALID_SIGNALS (frozenset)"
    - "_multiplier_for(signals, override) module-level helper"
    - "split_and_duplicate(examples, multiplier_override, metrics) module-level function"
  affects:
    - "Plan 03 (mine_prompt_sessions CLI): imports SessionPromptMiner + split_and_duplicate"
    - "Plan 04 (evolve_prompt_sections --session-source union): not consumed directly, but D-15 helpers come via prompt_dataset module from Wave 1"
    - "Plan 05 (integration tests): import surface anchors validated"
tech_stack:
  added: []
  patterns:
    - "DSPy Signature with 5 OutputFields for single-call multi-field LLM judgement (D-03)"
    - "dataclass Candidate with task_hash() method for cross-split dedup"
    - "OrderedDict double-key (task_hash, section_id) for D-07 same-task multi-section split"
    - "Phase 18 DriftDetector._check_one_run (1-run) override for candidate-recall stage cost control (D-04)"
    - "Conservative default false_positive + difficulty='medium' fallback on LLM parse failure (D-05/D-12)"
    - "B3 fix metric channel separation: file-level session_load_failures vs line-level jsonl_skipped_lines"
key_files:
  created:
    - "evolution/prompts/session_prompt_miner.py (789 LoC)"
    - "tests/prompts/test_session_prompt_miner.py (667 LoC, 40 tests)"
  modified: []
decisions:
  - "[D-03] Single LLM call emits 5 outputs (verdict, section_id, expected_behavior, difficulty, rationale) via ConfirmBehavioralExample — saves ~5x judge calls vs per-field calls"
  - "[D-04] DriftDetector reused via ._check_one_run (1-run), NOT .check (3-run); min_turns=6 gate; lazy-init only when persona_drift in signals AND thresholds provided"
  - "[D-05] false_positive verdicts recorded in judge_false_positives_by_signal but dropped from examples — audit trail for noise"
  - "[D-07] Same task_hash + different section_id → multiple examples; same task_hash + same section_id → union mining_signals"
  - "[D-09] Surface drift filter runs AFTER LLM judge (section_id comes from verdict), not before"
  - "[D-12] difficulty parse failure → 'medium' default; verdict parse failure → 'false_positive' default"
  - "[D-13] Train-only multiplier; max-across-signals (NOT product) for multi-signal examples"
  - "[D-18] SessionPromptMiner class structure mirrors SessionToolMiner (Phase 14): constructor + 4 _extract_* + _judge_* + _load_session + _filter_* + mine"
  - "[B3 fix] metrics schema splits session_load_failures (file-level, mine scope) and jsonl_skipped_lines (line-level, Plan 04 helper scope); mine never touches jsonl_skipped_lines"
  - "[W3 fix] _extract_persona_drift docstring explicitly documents 4-dim multi-candidate emission + dedup behavior + mining_signals does NOT distinguish dim (dim info recorded only in downstream_context)"
  - "[W5 fix] Signature OutputField validation in tests uses public __annotations__ API, not DSPy private __dspy_field_type marker (cross-version stable)"
metrics:
  duration: ~28 minutes
  completed: 2026-05-18
  tasks_completed: 4
  files_created: 2
  files_modified: 0
  prompt_tests_before: 127 passed, 1 skipped (after Plan 19-01)
  prompt_tests_after: 167 passed, 1 skipped (+40 new tests)
  regression: zero
  module_loc: 789
---

# Phase 19 Plan 02: SessionPromptMiner Core Service Summary

**One-liner:** Implements 4-way SessionDB behavioral mining service (`SessionPromptMiner`) with regex-recall + DSPy LLM-as-judge confirmation (5-output single-call), Phase 18 DriftDetector reuse as persona_drift candidate proposer (1-run override), and D-07/D-13/D-15 hash-keyed dedup + train-only multiplier — 789 LoC mirror of Phase 14 `SessionToolMiner` extended for prompt domain.

## What Was Built

A single new module `evolution/prompts/session_prompt_miner.py` shipped in 4 RED/GREEN cycles (one per Task), each commit independently passing all prior Tasks' tests:

1. **Task 2.1 (skeleton):** module docstring + imports + 4-key `DEFAULT_MULTIPLIER` + `VALID_SIGNALS` frozenset + keyword pattern banks (`_USER_CORRECTION_PATTERNS` + 4 per-section in `_SECTION_SPECIFIC_PATTERNS`) + `Candidate` / `Verdict` dataclasses + `_multiplier_for` helper + `ConfirmBehavioralExample` (5 inputs / 5 outputs) + `DetectUserCorrection` Signatures + placeholder `SessionPromptMiner` / `split_and_duplicate`.

2. **Task 2.2 (constructor + helpers):** `__init__` with lazy `DriftDetector` init only when `persona_drift in signals AND drift_thresholds is not None` (graceful warn-and-disable otherwise); `_fresh_metrics` returning 16-key dict per B3 fix; `_load_session` with `try/except json` (B3: increments `session_load_failures`, NOT `jsonl_skipped_lines`); `_filter_secrets` (D-23 via `_contains_secret`) and `_filter_drift` (D-09 surface drift drop after LLM judge).

3. **Task 2.3 (4 extractors + judge):** four candidate proposers — `_extract_user_correction` (regex + LLM 二判 via `DetectUserCorrection`), `_extract_section_specific_failure` (per-section pattern bank + platform_token×correction matcher for `platform_hints.<key>` proposer guess), `_extract_oracle_disagreement` (returns `[]` when `baseline_module is None`), `_extract_persona_drift` (1-run `DriftDetector._check_one_run`, `min_turns=6`, multi-dim → multi-candidate) — plus `_judge_candidates` single-call 5-field LLM judge with conservative fallbacks (D-05/D-12).

4. **Task 2.4 (orchestration + split):** `mine()` end-to-end pipeline (load → extract → secret filter → judge → drift filter → hash-dedup union) returning `list[PromptBehavioralExample]` with `source='session'`; module-level `split_and_duplicate()` for D-13 train-only max-multiplier duplication + D-15 hash-bucket split.

## Files Created

| File | LoC | Role | Lines |
|------|-----|------|-------|
| `evolution/prompts/session_prompt_miner.py` | 789 | mining service module | full file |
| `tests/prompts/test_session_prompt_miner.py` | 667 | unit tests (40 cases) | full file |

### Line ranges (session_prompt_miner.py)

| Symbol | Lines |
|--------|-------|
| Module docstring | 1-27 |
| Imports | 29-44 |
| Constants (`DEFAULT_MULTIPLIER`, `VALID_SIGNALS`, `JSONL_BAD_LINE_WARN_THRESHOLD`, `DIFFICULTY_VALUES`, keyword banks) | 48-90 |
| `Candidate` dataclass | 95-110 |
| `Verdict` dataclass | 114-120 |
| `_multiplier_for` helper | 124-131 |
| `DetectUserCorrection` Signature | 136-150 |
| `ConfirmBehavioralExample` Signature | 153-196 |
| `SessionPromptMiner.__init__` | 213-248 |
| `SessionPromptMiner._fresh_metrics` | 250-286 |
| `SessionPromptMiner._load_session` | 288-296 |
| `SessionPromptMiner._filter_secrets` | 298-310 |
| `SessionPromptMiner._filter_drift` | 312-328 |
| Static helpers `_assistant_summary_at` / `_first_user_task` / `_downstream_context` | 332-368 |
| `SessionPromptMiner._extract_user_correction` | 371-413 |
| `SessionPromptMiner._extract_section_specific_failure` | 415-464 |
| `SessionPromptMiner._extract_oracle_disagreement` | 466-508 |
| `SessionPromptMiner._extract_persona_drift` | 510-571 |
| `SessionPromptMiner._judge_candidates` | 573-634 |
| `SessionPromptMiner._format_sections_summary` | 636-645 |
| `SessionPromptMiner.mine` | 647-728 |
| Module-level `split_and_duplicate` | 730-789 |

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `5d41e81` | test | RED for Task 2.1-2.4 — 40 failing tests covering exports, constructor, extractors, mine, split |
| `cf3fb8f` | feat | GREEN for Task 2.1 — skeleton (constants, dataclasses, Signatures, helper, placeholders) |
| `87a05fb` | feat | GREEN for Task 2.2 — `__init__` + 5 helpers (`_fresh_metrics`, `_load_session`, `_filter_secrets`, `_filter_drift`) |
| `90a89e9` | feat | GREEN for Task 2.3 — 4 `_extract_*` extractors + `_judge_candidates` + static helpers |
| `7cb7956` | feat | GREEN for Task 2.4 — `mine()` orchestration + module-level `split_and_duplicate` |

## Plan-defined Verify Output

### Task 2.1 verify automated
```
PASS
```
All 4 named imports, `DEFAULT_MULTIPLIER` exact 4 keys, `VALID_SIGNALS` derived, `Candidate.task_hash()` returns 16-char string, both Signatures are `dspy.Signature` subclasses with required OutputFields in `__annotations__`, `_multiplier_for` max-across-signals + empty fallback.

### Task 2.2 verify automated
```
⚠ persona_drift signal requested but drift_thresholds not provided; signal will
be skipped.
⚠ persona_drift signal requested but drift_thresholds not provided; signal will
be skipped.
PASS
```
Default construction, signals subset (DriftDetector None), persona_drift requested without thresholds (graceful disable + Rich warn), 16-key metrics schema, B3 fix: `_load_session` failure → `session_load_failures += 1` while `jsonl_skipped_lines == 0`; JWT secret filter; `_filter_drift` drops unknown section_id and records in `surface_drift_sections`.

### Task 2.3 verify automated
```
⚠ persona_drift signal requested but drift_thresholds not provided; signal will
be skipped.
⚠ persona_drift signal requested but drift_thresholds not provided; signal will
be skipped.
⚠ persona_drift signal requested but drift_thresholds not provided; signal will
be skipped.
⚠ persona_drift signal requested but drift_thresholds not provided; signal will
be skipped.
PASS
```
user_correction keyword hit + LLM-confirm, no-keyword empty, section_specific memory_guidance hit, oracle disabled-without-baseline, persona_drift signals requested without detector → `[]`, persona_drift 2-dim exceed → 2 candidates, judge difficulty fallback `LARGE`→`medium` + verdict `LARGE`→`false_positive`, `judge_calls` + `judge_false_positives_by_signal` incremented.

### Task 2.4 verify automated
```
⚠ persona_drift signal requested but drift_thresholds not provided; signal will
be skipped.
PASS
```
Empty dir returns `[]`, single user_correction session emits one `PromptBehavioralExample(source='session', mining_signals=['user_correction'])`, train-only `split_and_duplicate` produces `len(train) == 3 + 2 == 5`, multi-signal combo `len(train) == max(3,2) == 3` not product, limit=3 skips remaining 7 sessions.

### Full pytest run
```
tests/prompts/ — 167 passed, 1 skipped in 3.23s
```
127 baseline + 40 new = 167 total (1 skipped pre-existing Phase 18 test). Zero regression.

## DriftDetector 1-run Override Evidence (W3 fix anchor)

```
$ grep -nE "drift_detector\._check_one_run|drift_detector\.check\(" evolution/prompts/session_prompt_miner.py
550:            scores, _ = self.drift_detector._check_one_run(

$ grep -nE "len\(assistant_turns\) < 6" evolution/prompts/session_prompt_miner.py
544:        if len(assistant_turns) < 6:

$ grep -nE "4-dim DriftDetector candidate proposer|mining_signals 仅含" evolution/prompts/session_prompt_miner.py
515:        """4-dim DriftDetector candidate proposer (1-run, candidate 召回)。
525:            mining_signals 仅含 ['persona_drift']（不区分 dim — dim 信息
```

Single `_check_one_run` call (line 550); zero `.check(` calls (3-run is deliberately bypassed at candidate-recall stage per D-04 cost control). `min_turns=6` gate at line 544. W3 docstring at lines 515 + 525 explicitly documents 4-dim multi-candidate emission and that `mining_signals` does NOT distinguish dim.

## B3 Fix Evidence — Metric Channel Separation

```
$ grep -nE "session_load_failures|jsonl_skipped_lines" evolution/prompts/session_prompt_miner.py
17:    B3 fix:     metrics schema explicitly separates session_load_failures
18:                (file-level, mine scope) vs jsonl_skipped_lines (line-level,
253:        session_load_failures (B3 fix: separates file-level session JSON
257:            session_load_failures: int
261:            jsonl_skipped_lines: int
276:            "session_load_failures": 0,  # B3 fix: file-level load failures (mine scope)
277:            "jsonl_skipped_lines": 0,  # D-24 line-level (Plan 04 helper scope; stays 0 here)
290:        session_load_failures (B3 fix: file-level counter; distinct from
291:        jsonl_skipped_lines which is line-level in Plan 04 helper scope)."""
295:            self.metrics["session_load_failures"] += 1
687:        # D-24 + B3 fix: skip-rate warn monitors session_load_failures
688:        # (file-level mining scope), NOT jsonl_skipped_lines (Plan 04 helper scope).
690:        session_failures = self.metrics["session_load_failures"]

$ grep -nE 'self\.metrics\[.jsonl_skipped_lines.\] \+= 1' evolution/prompts/session_prompt_miner.py
(empty — confirmed: this module never increments jsonl_skipped_lines)
```

`_load_session` (line 295) increments `session_load_failures` only; the mining `mine()` 5% threshold warn (lines 687-693) monitors `session_load_failures` rather than `jsonl_skipped_lines`. The latter remains initialized to 0 (line 277) and is reserved for Plan 04's `_load_session_dataset_resilient` line-level scope. A direct unit test (`test_session_load_failures_warns_at_threshold`) asserts both fields after 19/20 bad sessions: `session_load_failures == 19` AND `jsonl_skipped_lines == 0`.

## W5 Fix Evidence — Public Signature Field API

```
$ grep -nE "__dspy_field_type" tests/prompts/test_session_prompt_miner.py
(empty — confirmed: tests use only public __annotations__ API)

$ grep -nE "__annotations__" tests/prompts/test_session_prompt_miner.py
77:        """W5 fix: validate via __annotations__ public API, NOT __dspy_field_type."""
80:        actual_annots = set(ConfirmBehavioralExample.__annotations__.keys())
86:        assert "is_correction" in DetectUserCorrection.__annotations__
```

`ConfirmBehavioralExample`'s 5 OutputField names (`verdict, section_id, expected_behavior, difficulty, rationale`) are validated through `cls.__annotations__` set membership — DSPy version-stable.

## Robust LLM-output Parsing Evidence (D-05/D-12)

`_judge_candidates` lines 587-617 — single try/except around `self.judge(...)` returns 5 default values on any exception (`raw_verdict='false_positive'`, `section_id=''`, `expected=''`, `difficulty='medium'`, `rationale='[Parse failure: ...]'`). Verdict normalization at line 590-592 (verdict not in `{'confirm_example','false_positive'}` → `false_positive`). Difficulty normalization at lines 601-603 (`difficulty not in DIFFICULTY_VALUES → 'medium'`). Direct unit test `test_judge_difficulty_fallback` asserts bogus LLM output `LARGE` / `HUGE` collapses to `false_positive` / `medium`.

## Downstream Plan Anchors

| Downstream | Import | Used for |
|------------|--------|----------|
| Plan 03 `evolution/prompts/mine_prompt_sessions.py` | `from evolution.prompts.session_prompt_miner import SessionPromptMiner, split_and_duplicate, VALID_SIGNALS, DEFAULT_MULTIPLIER` | CLI orchestration: instantiate miner, drive mine() + split_and_duplicate, write JSONL + metrics.json |
| Plan 04 `evolution/prompts/evolve_prompt_sections.py` (--session-source union) | `from evolution.prompts.prompt_dataset import _normalize_task_hash` (transitively — Wave 1 anchor; this Plan does not require direct import in Plan 04) | D-16 hash-dedup at union site |
| Plan 05 integration tests | `from evolution.prompts.session_prompt_miner import SessionPromptMiner, Candidate, Verdict, ConfirmBehavioralExample, DetectUserCorrection` + the 40 existing unit tests as regression cover | E2E mine pipeline + CLI integration |

## Deviations from Plan

**None — plan executed exactly as written.**

Two minor judgement calls (both inside the plan's `<action>` scope):

1. **OrderedDict dual-key form rewrite (Task 2.4):** initial implementation used a temporary `key = (c.task_hash(), v.section_id)` variable for readability. Acceptance grep `grep -nE "by_key\[\(c\.task_hash\(\), v\.section_id\)\]"` required the literal indexed form, so the loop was rewritten to inline the tuple twice. Semantically identical. Not classified as a deviation — the acceptance criterion is part of the plan and was satisfied as-written.

2. **`OrderedDict` import placement (Task 2.4):** imported inside `mine()` rather than at module top. The plan's `<action>` snippet places it inline (line 1279 in the plan markup) and the spec's intent is clarity (only needed inside this single method). Followed plan verbatim.

## Authentication Gates

None. Pure offline implementation — no LLM calls during testing (judges are mocked); no auth-protected APIs touched. Real-world usage requires `OPENAI_API_KEY` / `OPENROUTER_API_KEY` via DSPy's standard path, identical to Phase 14 (no Phase 19 escalation).

## Known Stubs

None. All 4 placeholder `NotImplementedError`s from Task 2.1 (`SessionPromptMiner.__init__`, `SessionPromptMiner.mine`, module-level `split_and_duplicate`) were replaced in Tasks 2.2/2.4. `grep -c "NotImplementedError" evolution/prompts/session_prompt_miner.py` = 0.

## Threat Surface Scan

No new threat surface beyond the plan's `<threat_model>`. All listed STRIDE entries are mitigated:

| Threat ID | Mitigation Implementation Anchor |
|-----------|----------------------------------|
| T-19-02-T (secret leakage) | `_filter_secrets` lines 298-310 calls `_contains_secret` on task / downstream_context / originally_observed_behavior. Test `test_filter_secrets_drops_jwt`. |
| T-19-02-D (corrupted JSON DoS) | `_load_session` lines 288-296 `try/except`; `mine()` 5% threshold warn (lines 691-695). Test `test_session_load_failures_warns_at_threshold`. |
| T-19-02-I (surface drift) | `_filter_drift` lines 312-328 drops unknown section_id post-judge; records `surface_drift_dropped` + `surface_drift_sections`. Test `test_filter_drift_drops_unknown_section`. |
| T-19-02-I (LLM parse) | `_judge_candidates` lines 587-617 try/except with 5 conservative defaults; difficulty/verdict normalization. Test `test_judge_difficulty_fallback`. |
| T-19-02-E (DriftDetector lazy init) | `__init__` lines 230-243 graceful disable + Rich warn on missing thresholds. Test `test_persona_drift_without_thresholds_graceful_disable`. |
| T-19-02-R (audit) | All judge verdicts + false positives recorded in `judge_calls_by_signal` + `judge_confirmed_by_signal` + `judge_false_positives_by_signal`. Test `test_judge_confirm_records_metrics`. |

No new threat flags emerged — module is read-only (no `extract_prompt_sections` writeback path imported); no network endpoints; no auth or trust-boundary changes vs Wave 1.

## Self-Check: PASSED

- `evolution/prompts/session_prompt_miner.py` (789 LoC): FOUND
- `tests/prompts/test_session_prompt_miner.py` (40 tests): FOUND
- Commit `5d41e81` (RED): FOUND in `git log`
- Commit `cf3fb8f` (Task 2.1 GREEN): FOUND
- Commit `87a05fb` (Task 2.2 GREEN): FOUND
- Commit `90a89e9` (Task 2.3 GREEN): FOUND
- Commit `7cb7956` (Task 2.4 GREEN): FOUND
- 0 NotImplementedError remaining: verified
- 1 `_check_one_run` call vs 0 `.check(` calls: verified
- 16-key metrics schema (B3 fix `session_load_failures` + `jsonl_skipped_lines` separate): verified
- W3 docstring 4-dim multi-candidate + W5 `__annotations__` public API: verified
- 167 prompt tests passing, 1 skipped, zero regression: verified
