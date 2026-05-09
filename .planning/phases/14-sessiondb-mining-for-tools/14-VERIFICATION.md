---
phase: 14-sessiondb-mining-for-tools
status: passed
verifier: orchestrator-inline
verified_at: 2026-05-09
plans_complete: 6/6
phase_req_ids: [TOOL-V2-01]
must_haves_verified: 3/3
threats_mitigated: [T-14-01, T-14-02, T-14-03, T-14-04]
---

# VERIFICATION — Phase 14: SessionDB Mining for Tools

## Phase Goal

> Mine hermes-agent session transcripts for tool misselection patterns as high-value training data (TOOL-V2-01).

## Verifier method

Goal-backward verification performed inline by the orchestrator (after spawned `gsd-verifier` agents in this phase consistently hit harness lockouts). Method:

1. Cross-reference each ROADMAP must-have against actual codebase artifacts via grep
2. Verify the claimed test count and full-suite GREEN
3. Audit the manual checkpoint sign-off (Task 6.4) against real-data dry-run + wet-run outputs

## Must-haves — verification evidence

### Must-have 1: Importer extracts tool selection ground truth from session transcripts

**Status: VERIFIED**

Evidence:
- `evolution/tools/session_miner.py::SessionToolMiner` (line 127) — main class
- Three extractors (lines 346 / 444 / 500): `_extract_error_retry` (B), `_extract_user_correction` (A), `_extract_oracle_disagreement` (C)
- Public `mine(sessions_dir, current_tools, limit)` (line 667) orchestrates discovery + filter + judge + reduce
- LLM judge `_judge_candidate` produces structured `Verdict(label, correct_tool, rationale)` — that's the "ground truth" output (D-03)
- Schema-tolerant parsers (`.get()` + `isinstance` throughout, Pitfall 1) handle malformed_msg.json fixture without crashing — `tests/tools/test_session_signal_extract.py::test_parse_assistant_with_tool_calls` PASS
- **Real-world validation**: dry-run on 46 actual `~/.hermes/sessions/*.json` files extracted 6 error_retry candidates (Plan 06 Task 6.4 §A); wet-run confirmed all 6 via LLM judge (judge_confirmed_by_signal.error_retry = 6)

### Must-have 2: Misselection patterns weighted higher in training dataset

**Status: VERIFIED**

Evidence:
- `DEFAULT_MULTIPLIER` (line 40): `{"error_retry": 3, "user_correction": 3, "oracle_disagreement": 2}` — per-signal weights
- `_multiplier_for(signals, override)` (line 66): `max(merged[s] for s in signals)` policy (D-11 max, not accumulation)
- `SessionToolMiner.split_and_duplicate(examples)` (line 736): bucket-splits then duplicates **train-only** by max multiplier (Pitfall 5 — val/holdout untouched)
- CLI `--misselection-multiplier "error_retry=5,..."` flag for runtime override; rejected when signal unknown or value non-int
- Tests: `test_duplicate_train_only` (3/1/1 split — train multiplied, val/holdout single), `test_multiplier_max` (max(3,2)=3 for combined signals; override 5 wins)
- **Real-world validation**: wet-run produced 3 unique examples → `final_train_after_duplication = 9` (multiplier 3 applied train-only); val=0, holdout=0 untouched

### Must-have 3: Integration with existing ToolDatasetBuilder as additional data source

**Status: VERIFIED**

Evidence:
- `evolution/tools/evolve_tool_descriptions.py::_union_session_into_dataset` (line 38) — module-level helper
- `evolution/tools/evolve_tool_params.py::_union_session_into_dataset` (line 222) — same-semantics helper in Phase 13 CLI
- Both CLIs expose `--session-source <dir>` flag (lines 451 / 584)
- Both call sites integrate after dataset construction, before `to_dspy_examples`:
  - descriptions.py:209 — after `dataset = ToolSelectionDataset.load(...)` / `builder.generate(...)`, before split conversion
  - params.py:304 — inside `_load_dataset()` after dataset built, before split conversion
- Pitfall 10 ordering: synth enters `by_hash` first; session entries override on hash collision (D-14)
- Pitfall 5 guard: helper bodies grep-negative for `_multiplier_for` / `DEFAULT_MULTIPLIER` (W5; double-checked by `test_no_double_duplication` source-level inspect)
- `metrics.json` carries `"session_source"` field for traceability
- Tests: `test_session_overrides_synth` (session wins on collision), `test_no_double_duplication` (3 identical → dedup to 1, helpers don't re-multiply), `test_both_helpers_have_same_semantics` (both helpers produce identical output)

## Threat mitigations — verification evidence

| Threat | Owner plan | Mitigation evidence |
|--------|-----------|---------------------|
| **T-14-01** Tampering / LLM judge fail-closed | Plan 04 | `_judge_candidate` (line 580) wraps `self.judge(...)` in `try/except Exception` → returns `Verdict(label="false_positive", rationale=f"judge_error: {e}")`. Unknown verdict label → false_positive. `correct_tool ∉ available_tools` → false_positive. Test: `test_lm_failure_drops_candidate` patches `judge` to raise RuntimeError → asserts `verdict.label == "false_positive"`. PASS. |
| **T-14-02** Information disclosure / privacy | Plan 03 + Plan 04 | `evolution/core/external_importers.py::_contains_secret` extended with JWT regex + AWS-secret proximity + Shannon entropy ≥4.0 over ≥24-char base64-like tokens. Mining pipeline applies `_contains_secret` to `task` AND `downstream_context` (line 661). 3/3 v2 tests GREEN. **Real-world**: 0 false positives on 46 sessions (0% secret-filter rate << 5% threshold). |
| **T-14-03** Denial of service | Plan 04 | `_load_jsonl_skip_bad` (line 76) implements line-level `try/except json.JSONDecodeError` + skipped counter + 5% Rich console warn. EvalDataset.load remains strict (D-18 scope guard). Tests: `test_skip_bad_line` (90/10 split + warn), `test_evaldataset_strict_unchanged`. |
| **T-14-04** Unauthorized mining | Plan 05 | `mine_tool_sessions::mine()` first action: missing `--i-have-consent` → stderr "consent is REQUIRED" + return 1. Test: `test_consent_required` (CliRunner exit_code == 1, stderr contains "consent"). **Real-world**: bare `python -m evolution.tools.mine_tool_sessions` exits 1. |

## End-to-end pipeline check (real-data wet-run)

Plan 06 Task 6.4 §C executed `mine_tool_sessions` on all 46 real sessions:

| Stage | Result |
|-------|--------|
| Sessions discovered | 46 |
| Extractors (error_retry only) | 6 candidates |
| Surface-drift filter | 0 dropped (all tools in current hermes surface) |
| Privacy filter (`_contains_secret`) | 0 skipped |
| LLM judge calls | 6 (all confirmed; 0 false positives) |
| Hash-union dedup | 6 → 3 unique examples |
| Train multiplier (×3) | 3 → 9 train rows |
| Output topology | `train.jsonl` (9), `val.jsonl` (0), `holdout.jsonl` (0), `metrics.json`, `miner_log.jsonl` ✓ |
| metrics.json schema | All 13 keys present ✓ |
| CJK preservation | `ensure_ascii=False` retained Chinese task descriptions ✓ |

## Test suite

- 28 / 28 14-VALIDATION.md rows GREEN (every Wave 0 stub flipped from `pytest.skip` to PASS)
- 8 bonus tests added (test_parse_signals_helper, test_both_helpers_have_same_semantics, etc.)
- Full suite: **425 passed + 1 xfailed** (baseline at phase start: 395; Phase 14 adds 30 net passes)
- 0 skipped tests remaining in `tests/tools/test_session_*.py`, `test_secret_patterns_v2.py`, `test_jsonl_skip_bad.py`, `test_surface_drift.py`, `test_mine_cli.py`, `test_evolve_with_session_source.py`
- No regressions in pre-existing Phase 5 / Phase 13 / Phase 12 test suites

## Read-only guarantee

- `grep -E 'write_back_description|write_back_param' evolution/tools/session_miner.py evolution/tools/mine_tool_sessions.py evolution/tools/evolve_tool_descriptions.py evolution/tools/evolve_tool_params.py` → 0 hits ✓
- Phase 14 only adds new modules + extends existing `_contains_secret`; never imports from hermes-agent write paths

## No-new-deps guarantee

- `pyproject.toml` unchanged across the phase (verified via `git diff fc55e79..HEAD -- pyproject.toml` empty)
- Stdlib-only additions: `hashlib`, `re`, `json`, `math`, `collections.Counter`
- DSPy + Click + Rich already in deps

## Deviations & risks

### 1. Spawned executor agents hit mid-session harness lockouts

5 of 6 plans had their first spawned executor lose Write/Edit/Bash-write permissions mid-session. Each was completed inline by the orchestrator (Plans 01, 03, 04, 05, 06) or completed cleanly by the spawned agent (Plan 02). All artifacts are byte-for-byte spec-compliant; the only impact is execution path (recorded in each SUMMARY.md `Deviations` section).

### 2. cost_usd_spent reads 0.0 with DashScope/qwen-plus

DashScope's openai-compatible endpoint doesn't surface usage tokens through DSPy's `UsageTracker.poll()`, so `cost_usd_spent` stays at the placeholder. This is informational-only for Phase 14 success criteria; real billing (≪ $0.20 for 6 wet-run judge calls) is verifiable via DashScope dashboard. Pre-existing limitation flagged in `tests/core/test_cost_tracker.py` runtime warning.

### 3. user_correction signal extracted 0 candidates from real sessions

The Chinese keyword regex (`应该用 / 错了 / ...`) and English equivalents (`should have used / use \w+ instead`) didn't match in the user's 46 sessions. This isn't a defect — it reflects the actual conversation patterns in the session log. The extractor's correctness is verified by `test_a_user_correction` (mocked LLM 二判) and the `user_correction_a.json` fixture which DOES match.

## Verdict

**Status: PASSED**

All 3 must-haves verified with codebase + test + real-data evidence. All 4 threats covered with explicit fail-closed mitigations and tests. End-to-end pipeline validated by user-approved wet-run on 46 real sessions. Test suite GREEN with 0 skipped Phase 14 stubs.

Phase 14 closes the SessionDB mining capability requirement (TOOL-V2-01) — users can now run `python -m evolution.tools.mine_tool_sessions --i-have-consent ...` followed by `python -m evolution.tools.evolve_tool_descriptions --session-source <dir>` (or `evolve_tool_params`) to feed real-world misselection patterns into the GEPA optimization loop.
