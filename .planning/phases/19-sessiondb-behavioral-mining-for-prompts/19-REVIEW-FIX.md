---
phase: 19-sessiondb-behavioral-mining-for-prompts
fixed_at: 2026-05-19T00:00:00Z
review_path: .planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-REVIEW.md
iteration: 1
findings_in_scope: 10
fixed: 9
skipped: 1
status: partial
---

# Phase 19: Code Review Fix Report

**Fixed at:** 2026-05-19T00:00:00Z
**Source review:** .planning/phases/19-sessiondb-behavioral-mining-for-prompts/19-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope (Critical + Warning): 10
- Fixed: 9
- Skipped: 1
- Full repo test suite: 637 passed / 2 skipped / 1 xfailed (matches baseline of 640 collected; no regressions)
- Phase 19 prompts suite: 221 passed / 1 skipped

## Fixed Issues

### CR-01: `split_and_duplicate` 的 `seen_hashes` 是死代码

**Files modified:** `evolution/prompts/session_prompt_miner.py`
**Commit:** cf2cb28
**Applied fix:** Removed the dead `seen_hashes` bookkeeping (set, `if/pass` block, redundant comment) in `split_and_duplicate`. Replaced with a one-line comment documenting why no bookkeeping is required: `_hash_to_split` is a pure function of the hash, so same-hash → same-split is guaranteed deterministically, and `mine()`'s `by_key[(task_hash, section_id)]` dedup already ensures uniqueness. Behavior is preserved (allowing same-hash multi-section examples to coexist in one split); only the misleading dead code was removed. All 44 `test_session_prompt_miner.py` tests pass.

### CR-02: `_write_failed` 硬编码失败路径,忽略 `--output`

**Files modified:** `evolution/prompts/mine_prompt_sessions.py`
**Commit:** 50e6202
**Applied fix:** Added a `_resolve_failed_base(output)` helper that derives the FAILED_<ts>/ parent directory from `--output` (using `Path(output).parent` so the failure marker is a SIBLING of the user-named output dir, not nested inside it). Refactored `_write_failed` to take a `base_dir` parameter, updated all five call sites in `mine()` to pass the resolved `failed_base`. When `--output` is omitted, behavior is unchanged (falls back to the historical `datasets/prompts/sessions/` default). All 38 `test_mine_prompt_sessions*.py` tests pass.

### WR-01: `_load_session_dataset_resilient` 与 docstring/metrics 不一致

**Files modified:** `evolution/prompts/evolve_prompt_sections.py`
**Commit:** f65fae6
**Applied fix:** Method A — honored the docstring contract. Added an optional `metrics: dict` parameter to `_load_session_dataset_resilient`; when provided, the helper now writes `metrics["jsonl_skipped_lines"] = prior + sum(per-split skips)` so the field documented in `_fresh_metrics` actually reflects skipped JSONL lines. Backward-compatible: callers that omit `metrics` see unchanged behavior. Note: this finding is **logic-related** — the metric was provably wrong (always 0), and the fix is mechanical, so the verification level is straightforward. Existing 12 `test_evolve_prompt_sections_session_source.py` tests pass; the helper continues to return `(dataset, skipped)`.

### WR-02: 未使用的 `import hashlib`

**Files modified:** `evolution/prompts/session_prompt_miner.py`
**Commit:** df7762a
**Applied fix:** Deleted the unused `import hashlib` line. Confirmed via grep that `hashlib` is never referenced anywhere in the module (all hashing is delegated to `_normalize_task_hash` from `prompt_dataset`). All 44 `test_session_prompt_miner.py` tests still pass.

### WR-03: `_extract_persona_drift` 假设 `drift_detector.thresholds[dim]` 存在

**Files modified:** `evolution/prompts/session_prompt_miner.py`
**Commit:** 1308262
**Applied fix:** Added a defensive guard before the per-dim loop: if `_check_one_run` returns a partial scores dict (missing one or more of `DRIFT_DIMENSIONS`), emit a yellow Rich warning naming the session path and the missing dims, then `return cands` early. This mirrors `DriftDetector`'s all-or-nothing semantics and prevents silent 0.0 fallback from masking the detector signal. The all-4-dim-present test (`test_persona_drift_multi_dim_candidates`) still passes.

### WR-04: `_extract_oracle_disagreement` 占位实现无 cheap rule

**Files modified:** `evolution/prompts/session_prompt_miner.py`
**Commit:** 08f686d
**Applied fix:** Implemented the cheap-rule the comment had been promising: skip the candidate when `len(next_assistant) >= 50`. This prevents 100% LLM-judge cost on the `oracle_disagreement` path. Threshold (50) is a conservative initial floor; the LLM judge remains source-of-truth per D-04. Updated the surrounding comment to drop the now-obsolete "length-style sanity check" prose. Both existing tests (`test_oracle_disagreement_disabled_without_baseline` and `test_oracle_no_baseline_module_disabled`) pass — they cover the disabled path which is unaffected.

### WR-05: `expected_behavior` 未过滤 secrets

**Files modified:** `evolution/prompts/session_prompt_miner.py`
**Commit:** de7974f
**Applied fix:** After the judge call (and after `judge_calls` is incremented to reflect the actual LLM cost), added a `_contains_secret(expected) or _contains_secret(rationale)` check. On a positive hit, increment `secret_filter_skipped` and `continue` (drop the verdict, do not emit a Verdict tuple — this avoids polluting `train/val/holdout.jsonl`). Comment notes that confirmed/false_positive counters are deliberately NOT incremented because the verdict is discarded.

### WR-06: `judge_calls` 计数过载,未区分 LLM 调用失败

**Files modified:** `evolution/prompts/session_prompt_miner.py`
**Commit:** d1e7ba4
**Applied fix:** Added a `call_failed` flag in the per-candidate loop. The `except Exception` branch now sets `call_failed = True` and `metrics["judge_call_failures"] += 1`; the success branch increments `judge_calls` + `judge_calls_by_signal[c.signal]` as before. Also added `judge_call_failures: 0` to `_fresh_metrics` so the field always exists. Test `test_judge_parse_failure_defaults_difficulty_medium` (which asserts `judge_calls == 1` on a *successful* judge call returning bogus `difficulty="HUGE"`) still passes because that test path does NOT raise — only true LLM exceptions are now counted as failures. All 82 prompts tests for sessions still pass.

### WR-07: `messages` 非 list 未计 metric

**Files modified:** `evolution/prompts/session_prompt_miner.py`
**Commit:** 1f12c1f
**Applied fix:** In `mine()`'s per-session loop, when `messages` is not a list (schema-invalid), increment a new `metrics["session_schema_invalid"]` counter (using `setdefault`-style `metrics.get(...) + 1`) before `continue`. Added `session_schema_invalid: 0` to `_fresh_metrics` for explicit initialization. As REVIEW.md suggests, this is a separate key (not folded into `session_load_failures`) to preserve the B3 fix's "file-level vs line-level" semantic — schema-invalid is a third distinct failure mode. The existing metrics-keys assertion (`>= expected`) tolerates the new key without modification.

## Skipped Issues

### WR-08: `evolve_prompt_sections.py:624` drift_thresholds 解析无 try/except

**File:** `evolution/prompts/evolve_prompt_sections.py:624`
**Reason:** Skipped — code context is inside the explicitly protected region. The user-provided constraints state: "Phase 18 DriftDetector wiring at evolve_prompt_sections.py lines 622-732 MUST remain untouched." Line 624 is within 622-732. The proposed fix (wrap `json.loads(drift_thresholds_path.read_text())` and the `{d: raw[d] for d in DRIFT_DIMENSIONS}` projection in `try/except (json.JSONDecodeError, KeyError)` with a clear console message + `sys.exit(1)`) would otherwise be applied cleanly, but cannot be applied without crossing the off-limits boundary. Recommended follow-up: address in a dedicated Phase 18 hardening pass once the protected-region invariant is lifted.
**Original issue:** Drift thresholds JSON parsing is unguarded; a malformed `drift_thresholds.json` will raise `json.JSONDecodeError` / `KeyError` directly into `evolve()`, killing the run after GEPA may have already consumed LLM budget. Compare to `mine_prompt_sessions.py:346-356` which has graceful disable on parse failure.

---

_Fixed: 2026-05-19T00:00:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
