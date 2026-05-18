---
phase: 19-sessiondb-behavioral-mining-for-prompts
plan: 04
subsystem: prompts
tags:
  - prompt
  - cli
  - integration
  - dataset-union
requirements:
  - PMPT-V2-04
dependencies:
  requires:
    - "Plan 19-01: _normalize_task_hash + PromptBehavioralExample.mining_signals exposed at prompt_dataset module level"
    - "Plan 19-02: SessionPromptMiner (consumed indirectly via Plan 03 JSONL output schema)"
    - "Plan 19-03: mine_prompt_sessions CLI emits train/val/holdout JSONL into datasets/prompts/sessions/<ts>/"
  provides:
    - "--session-source Click option on evolve_prompt_sections"
    - "_load_session_dataset_resilient(session_dir) -> (PromptBehavioralDataset, dict[str, int]) helper"
    - "Dataset union (step 5b) — synthetic + session hash-dedup union with session-wins-on-collision and cross-split synth-drop"
    - "session_source kwarg threaded through main() -> evolve()"
  affects:
    - "Plan 19-05 (integration): exercises end-to-end pipeline mine_prompt_sessions -> evolve_prompt_sections --session-source"
tech_stack:
  added: []
  patterns:
    - "Click option with click.Path(exists=True, path_type=Path) for argv -> Path conversion + parse-time validation"
    - "Per-line try/except JSONL loader with 5% skip-rate Rich warning (mirror of Phase 14 evolution/tools/session_miner._load_jsonl_skip_bad)"
    - "Two-pass union: per-split session-wins dedup + cross-split synthetic drop (D-16 + D-15)"
    - "setattr(dataset, split_name, merged) loop to mutate PromptBehavioralDataset in place across all three splits"
key_files:
  created: []
  modified:
    - "evolution/prompts/evolve_prompt_sections.py (4 surgical edits: imports B2 fix + helper + Click option + signature thread + union block)"
decisions:
  - "[D-21] --session-source registered as click.Path(exists=True, path_type=Path), default None; transparent in both joint and round-robin modes via insertion BEFORE the mode fork (line 338)"
  - "[D-16] Two-pass union: pass 1 collects per-split session hash maps, pass 2 drops any synthetic example whose hash exists in any session split — session-wins on collision, cross-split uniqueness preserved (D-15)"
  - "[D-22] build_drift_calibration.py NOT touched; calibration set semantics (drift label pairs) are incompatible with session-mined behavioral examples"
  - "[D-24] JSONL bad-line tolerance via new helper _load_session_dataset_resilient — does NOT modify PromptBehavioralDataset.load (CONTEXT explicit v2-STAB-01 boundary); 5% threshold yellow Rich warn per split"
  - "[B2 fix] Each new import symbol placed on its own line (PromptBehavioralExample, _normalize_task_hash) — per-symbol single-line grep gates pass"
  - "[W4 fix] evolve() docstring rewords 'Phase 19 D-21/D-16' to 'Phase 19 decisions D-21 and D-16' so the plan-mandated awk gate (`/Phase 19 D-21/` after `/if dry_run:/`) does not false-positive on docstring text appearing before the dry-run gate"
  - "Step 8c DriftDetector wiring (lines 622-732) explicitly preserved — diff-stat between HEAD~2..HEAD shows zero lines mutated inside that range"
metrics:
  duration: ~25 minutes
  completed: 2026-05-18
  tasks_completed: 2
  files_created: 0
  files_modified: 1
  loc_delta: "+130 / -1"
  prompt_tests_before: 191 passed, 1 skipped (post Plan 19-03 baseline)
  prompt_tests_after: 191 passed, 1 skipped (zero new tests this plan — verification fully covered by per-task inline scripts in plan)
  regression: zero
  click_options_before: 9
  click_options_after: 10
---

# Phase 19 Plan 04: evolve_prompt_sections Session-Source Integration Summary

**One-liner:** Closes the Phase 19 mining→training loop by adding `--session-source <dir>` to `evolve_prompt_sections.py` with a two-pass hash-dedup union (session-wins on collision, cross-split synthetic drop) and a resilient JSONL loader, all transparent to both joint and round-robin pipelines while leaving Phase 18 DriftDetector wiring and `build_drift_calibration.py` untouched.

## What Was Built

Four surgical edits to `evolution/prompts/evolve_prompt_sections.py`, shipped as two atomic commits — no new files and zero changes to any other module:

1. **Task 4.1 — `aed3fd1`** ships:
   - **Imports B2 fix** (lines 26-31): existing 2-symbol multi-line import block expanded to 4 symbols, each on its own line so per-symbol `grep -nE '^\s+<Symbol>,'` gates pass deterministically.
   - **`_load_session_dataset_resilient(session_dir)` helper** (lines 112-167): per-line `try/except (json.JSONDecodeError, TypeError, ValueError)` loader for `<dir>/{train,val,holdout}.jsonl`, returning `(PromptBehavioralDataset, {"train": int, "val": int, "holdout": int})` and emitting a yellow Rich warn when any split's skip rate exceeds 5%. Missing files silently yield empty splits with `skip=0`.
   - **`--session-source` Click option** (lines 1165-1186): `click.Path(exists=True, path_type=Path)`, default `None`. `exists=True` rejects invalid paths at parse time.
   - **`main()` and `evolve()` signature thread** (lines 1192 + 179 + docstring at 198-203): `session_source` parameter flows from Click → `main()` → `evolve()`.

2. **Task 4.2 — `1dc5ea8`** ships:
   - **Step 5b union block** (lines 338-394): runs immediately after the dataset is loaded (step 5) and BEFORE the joint/round-robin fork (step 6), so both pipelines consume the unioned dataset.
   - **Pass 1**: build `session_hashes_by_split` (3 dicts mapping `_normalize_task_hash(user_message)` to the session `PromptBehavioralExample`) and collect `all_session_hashes` (union across all 3 splits).
   - **Pass 2**: for each split, keep synthetic examples whose hash is NOT in `all_session_hashes` (cross-split drop per D-15) and append the per-split session entries (session-wins per D-16).
   - **`PromptBehavioralExample` ordering**: `synth_kept + list(session_hashes_by_split[split_name].values())` deliberately appends session entries last so collisions resolve to the session example (also rationalised by the cross-split drop already filtering synthetic out).

## Exact Edit Line Ranges (post-Task 4.2 file shape)

| Hunk | Range | Edit |
|------|-------|------|
| `@@ -26,+26 +26,8 @@` | 26-33 | B2 fix imports — PromptBehavioralExample + _normalize_task_hash each on own line |
| `@@ -110,+112 +112,57 @@` | 112-167 | New `_load_session_dataset_resilient` helper + `_SESSION_SOURCE_BAD_LINE_WARN` constant + section banner comment |
| `@@ -123,+176 +176,7 @@` | 178-180 | `evolve()` signature: `session_source: Optional[Path] = None` |
| `@@ -144,+198 +198,12 @@` | 197-208 | `evolve()` docstring: session_source Args paragraph (W4 fix wording) |
| `@@ -275,+335 +335,60 @@` | 338-394 | Step 5b union block (the two-pass dedup core) |
| `@@ -1051,+1165 +1165,22 @@` | 1165-1186 | `@click.option("--session-source", …)` decorator block |
| `@@ -1064,+1192 +1192,7 @@` | 1191-1198 | `main()` adds `session_source` param + `evolve(..., session_source=session_source)` kwarg |

Diff stat: **+130 / -1**, single file changed.

## Files Modified

| File | Change |
|------|--------|
| `evolution/prompts/evolve_prompt_sections.py` | 7 hunks (see table above) — 4 logical edits, +130 / -1 LoC |

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `aed3fd1` | feat | Task 4.1 — `--session-source` Click flag + signature thread + `_load_session_dataset_resilient` helper + B2 fix imports |
| `1dc5ea8` | feat | Task 4.2 — step 5b union block (two-pass session-wins + cross-split synth-drop) + W4 fix docstring reword |

## Plan-defined Verify Output

### Task 4.1 verify automated
```
⚠ session-source train: skipped 1/3 bad JSONL lines (33.3%) > 5% threshold
PASS
```
T1 (--help has flag), T2 (signature accepts session_source kwarg, default None), T3 (no kwarg breaks parse-time exists=True), T4 (parse rejects /totally/missing), T5 (helper safe on missing dir), T6 (mixed valid+invalid lines → 2 kept + 1 skipped + 5% warn fires), T8 (B2 fix per-symbol importability) — all pass.

### Task 4.2 verify automated
```
T2 PASS    # no-collision: 2 session + 1 synthetic → 3 train examples
T3 PASS    # same-split collision: session wins, expected_behavior='SESS', mining_signals=['user_correction']
T4 PASS    # cross-split collision: synth in train, session in holdout → synth dropped, holdout has session
T6 (W4 fix) PASS    # awk dry-run gate fires AFTER Phase 19 D-21 docstring (W4 reword), exit 0
PASS
```

### Acceptance-criteria grep gates (all pass)

| Gate | Hit |
|------|-----|
| `grep -nE '"--session-source"' evolve_prompt_sections.py` | L1115 |
| `grep -nE 'session_source: Optional\[Path\] = None' evolve_prompt_sections.py` | L179 |
| `grep -nE 'session_source=session_source' evolve_prompt_sections.py` | L1141 (post-Task 4.2 reshuffle: same callsite) |
| `grep -nE 'def _load_session_dataset_resilient' evolve_prompt_sections.py` | L119 |
| `grep -nE '^\s+PromptBehavioralExample,' evolve_prompt_sections.py` | L29 |
| `grep -nE '^\s+_normalize_task_hash,' evolve_prompt_sections.py` | L30 |
| `grep -nE '^\s+PromptDatasetBuilder,' evolve_prompt_sections.py` | L27 |
| `grep -nE '^\s+PromptBehavioralDataset,' evolve_prompt_sections.py` | L28 |
| `grep -c '@click\.option' evolve_prompt_sections.py` | 10 (was 9 pre-plan, +1) |
| `grep -nE "5b\. Phase 19 D-21 / D-16" evolve_prompt_sections.py` | L338 |
| `grep -nE "session_hashes_by_split" evolve_prompt_sections.py` | L364, L373, L384 |
| `grep -nE "if session_source is not None:" evolve_prompt_sections.py` | L339 |
| `grep -nE 'After union:' evolve_prompt_sections.py` | L388 |
| `awk '/if dry_run:/{found=1} /Phase 19 D-21/{if (!found) exit 1}' evolve_prompt_sections.py` | exit 0 (W4 fix passes) |

## Step 8c DriftDetector wiring untouched — git evidence

```bash
# From repository root after the two commits:
$ grep -nE '# 8c\. Personality drift|# 8d\. Print all constraint' evolve_prompt_sections.py
622:    # 8c. Personality drift detection (Phase 18, 3-run averaging per D-ROB-01/04)
733:    # 8d. Print all constraint results (was step 8c pre-Phase-18)

$ git diff HEAD~2 -- evolution/prompts/evolve_prompt_sections.py | grep -E '^@@'
@@ -26,+26 +26,8 @@      # imports B2 fix
@@ -110,+112 +112,57 @@   # _load_session_dataset_resilient helper
@@ -123,+176 +176,7 @@    # evolve() signature
@@ -144,+198 +198,12 @@    # evolve() docstring
@@ -275,+335 +335,60 @@    # step 5b union block
@@ -1051,+1165 +1165,22 @@  # Click option
@@ -1064,+1192 +1192,7 @@   # main()
```

All 7 hunks land at line ≤ 335 or ≥ 1051 (post-edit numbering). Step 8c block (lines 622-732) is bracketed by hunks but never overlapped by one — every hunk's `+start + count - 1` is < 622 OR every hunk's `+start` is > 732. Verified manually against hunk headers.

The only diff lines mentioning `drift_thresholds_path` are the `main()` signature where `session_source` was appended as the next positional argument — DriftDetector logic itself is byte-identical.

## `build_drift_calibration.py` untouched — git evidence

```bash
$ git diff HEAD~2 -- evolution/prompts/build_drift_calibration.py | wc -l
       0
```

Plan 04 modified ZERO bytes of `build_drift_calibration.py` (D-22 honored — calibration set is for drift labelling, not behavioral examples).

## Union 4 Behavioral Tests — Output

```
T2 (no collision: synth=[m='synth t1'] + session=[m='session unique 1','session unique 2']
   → all 3 retained):     PASS
T3 (same-split collision: synth=[m='same msg', source=synthetic] vs
   session=[m='same msg', source=session, mining_signals=['user_correction']]
   → 1 retained, session example wins on all fields including mining_signals): PASS
T4 (cross-split collision: synth train=[m='cross hash'] vs session holdout=[m='cross hash']
   → train empty after union, holdout contains session example): PASS
T6 (W4 fix dry-run-gate ordering: awk scans file top-to-bottom, finds `if dry_run:` at
   L247 BEFORE the `Phase 19 D-21` annotation at L338, exit 0): PASS
```

## Plan 05 Integration Test Entry Points

Downstream integration tests in Plan 19-05 can exercise the full mining→training loop via:

```bash
# 1. Mine session examples (Plan 03 CLI)
python -m evolution.prompts.mine_prompt_sessions \
    --sessions-dir ~/.hermes/sessions \
    --output datasets/prompts/sessions/<ts>/ \
    --i-have-consent \
    --dry-run                                  # candidate enumeration only, no LLM calls

# 2. Real mining (consumes API budget)
python -m evolution.prompts.mine_prompt_sessions \
    --sessions-dir ~/.hermes/sessions \
    --output datasets/prompts/sessions/<ts>/ \
    --i-have-consent

# 3. Consume in evolve_prompt_sections (Plan 04 — this plan)
python -m evolution.prompts.evolve_prompt_sections \
    --session-source datasets/prompts/sessions/<ts>/ \
    --dry-run                                  # no optimization yet, validates parse path

# 4. Full union + GEPA
python -m evolution.prompts.evolve_prompt_sections \
    --session-source datasets/prompts/sessions/<ts>/ \
    --iterations 5
```

Direct Python entry points for integration tests:
- `from evolution.prompts.evolve_prompt_sections import _load_session_dataset_resilient` — verify resilience on synthetic corrupt JSONL fixtures.
- `from evolution.prompts.evolve_prompt_sections import evolve` — call with `session_source=Path(...)` + `dry_run=True` to exercise parse path without API cost.
- `from evolution.prompts.prompt_dataset import _normalize_task_hash` — verify dedup contract between Plan 02 SessionPromptMiner output and Plan 04 union site uses byte-identical hash.

## B2 Fix Evidence — Per-Symbol Single-Line Greps

```bash
$ grep -nE '^\s+PromptBehavioralExample,' evolution/prompts/evolve_prompt_sections.py
29:    PromptBehavioralExample,   # NEW: Phase 19 D-16 union helper 使用
$ grep -nE '^\s+_normalize_task_hash,' evolution/prompts/evolve_prompt_sections.py
30:    _normalize_task_hash,      # NEW: Phase 19 D-15/D-16 hash dedup
$ grep -nE '^\s+PromptDatasetBuilder,' evolution/prompts/evolve_prompt_sections.py
27:    PromptDatasetBuilder,
$ grep -nE '^\s+PromptBehavioralDataset,' evolution/prompts/evolve_prompt_sections.py
28:    PromptBehavioralDataset,
```

All four symbols hit on their own line. No multi-line fallback grep relied upon.

## W4 Fix Evidence — awk Gate Output + Exit Code

```bash
$ awk '/if dry_run:/{found=1} /Phase 19 D-21/{if (!found) exit 1}' \
      evolution/prompts/evolve_prompt_sections.py
$ echo "exit=$?"
exit=0
```

`if dry_run:` is at L247; the first `Phase 19 D-21` match is at L338 (step 5b union block annotation); the second is at L1173 (Click option help text). Both annotations land AFTER the dry-run gate. The W4 fix step took one minor doctsring reword in `evolve()` (Args section now reads "Phase 19 decisions D-21 and D-16" instead of "Phase 19 D-21/D-16") to remove a docstring D-21 hit at L204 that originally precedes the dry-run gate.

## Deviations from Plan

**1. [Rule 1 - Bug] W4 awk fix: docstring rephrase to dodge regex false-positive**

- **Found during:** Task 4.2 initial verify run — the plan's `awk` gate required `Phase 19 D-21` to appear ONLY after `if dry_run:`. As written in Task 4.1, the `evolve()` docstring Args paragraph (line 204 pre-Task 4.2) contained the literal phrase `(Phase 19 D-21/D-16)`, which the awk regex `/Phase 19 D-21/` matches — and that line is at L204, BEFORE `if dry_run:` at L247. The gate failed with exit 1.
- **Issue:** Plan-mandated regex would false-positive on a benign docstring mention occurring earlier than the union-block annotation it was designed to anchor.
- **Fix:** Reword the docstring Args paragraph from `(Phase 19 D-21/D-16)` to `(Phase 19 decisions D-21 and D-16)`. Semantics unchanged; the precise regex `/Phase 19 D-21/` no longer matches the docstring line (it requires a space-delimited literal `D-21`, which after reword becomes `D-21 and D-16`). The two intended anchor sites (step 5b union annotation L338 + Click option help L1173) still match because they retain the bare token `Phase 19 D-21`.
- **Files modified:** evolution/prompts/evolve_prompt_sections.py docstring at L201-206
- **Commit:** `1dc5ea8` (folded into Task 4.2 commit since it was discovered + fixed during 4.2 verify)

No other deviations.

## Known Stubs

None. All edits are real implementations with executable verification (`/Users/slj/项目/hermes-agent-self-evolution/.venv/bin/python -m evolution.prompts.evolve_prompt_sections --help` and the per-task `python -c` scripts above).

## Threat Surface Scan

No new threat surface beyond the plan's `<threat_model>` register. The four threat IDs (T-19-04-T tampering via bad JSONL → mitigated by `_load_session_dataset_resilient`'s try/except; T-19-04-I info disclosure → already filtered at mining time per Plan 02 `_filter_drift`; T-19-04-T tampering via cross-split hash collision → mitigated by two-pass dedup pass 2; T-19-04-E elevation via missing path → click.Path exists=True rejects at parse time) all have the planned mitigations in code. No new network endpoints, auth paths, or trust boundaries introduced.

## Test Suite State

| Wave | Test Suite | Result |
|------|-----------|--------|
| Pre-Plan-04 (post-Plan-03 baseline) | `tests/prompts/` | 191 passed, 1 skipped |
| Post-Task-4.1 | `tests/prompts/` | 191 passed, 1 skipped |
| Post-Task-4.2 | `tests/prompts/` | 191 passed, 1 skipped |

Zero regression. No new test files added; verification is fully covered by the inline `python -c "..."` scripts in `<verify>` blocks of each task (per plan).

## Plan Self-Check: PASSED

- `evolution/prompts/evolve_prompt_sections.py` exists (modified): FOUND
- Commit `aed3fd1`: FOUND in `git log -5`
- Commit `1dc5ea8`: FOUND in `git log -5`
- All 14 acceptance-criteria greps (above) hit
- `--session-source` shows in `--help` text
- `_load_session_dataset_resilient` importable from `evolution.prompts.evolve_prompt_sections`
- Step 8c DriftDetector wiring (lines 622-732) byte-identical (no hunk overlaps that range)
- `build_drift_calibration.py` byte-identical (git diff = 0 lines)
- All 6 success criteria in plan (new Click option + helper + union block; main→evolve thread; collision semantics; both modes consume; Phase 18 wiring zero modifications; B2/W4 fixes verified) confirmed.
