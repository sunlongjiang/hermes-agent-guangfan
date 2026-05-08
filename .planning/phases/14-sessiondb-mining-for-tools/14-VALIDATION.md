---
phase: 14
slug: sessiondb-mining-for-tools
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-08
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Sourced from `14-RESEARCH.md §Validation Architecture`.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=7.0 (+ pytest-asyncio >=0.21 for any async paths) |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` |
| **Quick run command** | `.venv/bin/pytest tests/tools/test_session_*.py tests/tools/test_secret_patterns_v2.py tests/tools/test_jsonl_skip_bad.py tests/tools/test_surface_drift.py tests/tools/test_mine_cli.py -x --tb=short` |
| **Full suite command** | `.venv/bin/pytest tests/ -v` |
| **Estimated runtime** | ~30s quick (mock LM); ~3 min full (385 baseline + 28 new) |

---

## Sampling Rate

- **After every task commit:** Run quick command (Phase 14 unit tests only, mocked LM)
- **After every plan wave:** Run `.venv/bin/pytest tests/tools/ -v` (Phase 4/5/13 + 14 — non-regression + new)
- **Before `/gsd-verify-work`:** Full suite must be green (385 + 28 = 413 expected)
- **Max feedback latency:** 30 seconds for quick; 180 seconds for full

---

## Per-Task Verification Map

> Task IDs (`14-NN-MM`) are assigned by the planner. Rows below map REQ + test type + automated command. Planner must attach each test to a task (via `<automated>` block in PLAN.md) so Wave 0 covers the missing files.

| # | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1 | TBD | 0 | TOOL-V2-01 | — | session JSON parser tolerates `reasoning_details`/multi-`tool_calls`/missing-`role` | unit | `pytest tests/tools/test_session_signal_extract.py::test_parse_assistant_with_tool_calls -x` | ❌ W0 | ⬜ pending |
| 2 | TBD | 0 | TOOL-V2-01 | — | B (error_retry) extractor: `exit_code != 0` / truthy `error` / parse-fail conservative | unit | `pytest tests/tools/test_session_signal_extract.py::test_b_error_retry -x` | ❌ W0 | ⬜ pending |
| 3 | TBD | 0 | TOOL-V2-01 | — | A (user_correction) extractor: keyword regex hit + LLM 二判 (mock LM) | unit | `pytest tests/tools/test_session_signal_extract.py::test_a_user_correction -x` | ❌ W0 | ⬜ pending |
| 4 | TBD | 0 | TOOL-V2-01 | — | C (oracle_disagreement) extractor: baseline ToolModule mock disagrees → candidate | unit | `pytest tests/tools/test_session_signal_extract.py::test_c_oracle_disagreement -x` | ❌ W0 | ⬜ pending |
| 5 | TBD | 0 | TOOL-V2-01 | T-14-01 | LLM judge ConfirmMisselection round-trip: confirm + false_positive verdicts parsed | unit | `pytest tests/tools/test_session_judge.py::test_verdict_round_trip -x` | ❌ W0 | ⬜ pending |
| 6 | TBD | 0 | TOOL-V2-01 | T-14-01 | LLM call failure / unparsable JSON → drop candidate (fail-closed, never silent-accept) | unit | `pytest tests/tools/test_session_judge.py::test_lm_failure_drops_candidate -x` | ❌ W0 | ⬜ pending |
| 7 | TBD | 0 | TOOL-V2-01 | — | hash bucket edges: 69→train, 70→val, 84→val, 85→holdout (constructed task strings) | unit | `pytest tests/tools/test_session_split.py::test_hash_bucket_edges -x` | ❌ W0 | ⬜ pending |
| 8 | TBD | 0 | TOOL-V2-01 | — | hash determinism: same task → same bucket across runs | unit | `pytest tests/tools/test_session_split.py::test_hash_determinism -x` | ❌ W0 | ⬜ pending |
| 9 | TBD | 0 | TOOL-V2-01 | — | normalize robustness: `"Read   FILE"` == `"read file"` (lowercase + collapse_whitespace + strip) | unit | `pytest tests/tools/test_session_split.py::test_normalize_robust -x` | ❌ W0 | ⬜ pending |
| 10 | TBD | 0 | TOOL-V2-01 | — | same hash, multiple signals → 1 example with `misselection_signals` union | unit | `pytest tests/tools/test_session_split.py::test_signals_union -x` | ❌ W0 | ⬜ pending |
| 11 | TBD | 0 | TOOL-V2-01 | — | sample duplication train-only (val/holdout retain 1×) | unit | `pytest tests/tools/test_session_miner.py::test_duplicate_train_only -x` | ❌ W0 | ⬜ pending |
| 12 | TBD | 0 | TOOL-V2-01 | — | multi-source duplication multiplier = max (no accumulation) | unit | `pytest tests/tools/test_session_miner.py::test_multiplier_max -x` | ❌ W0 | ⬜ pending |
| 13 | TBD | 0 | TOOL-V2-01 | T-14-02 | secret patterns v2: JWT / AWS / high-entropy positives | unit | `pytest tests/tools/test_secret_patterns_v2.py::test_layer1_positives -x` | ❌ W0 | ⬜ pending |
| 14 | TBD | 0 | TOOL-V2-01 | T-14-02 | secret patterns v2: no regression on v1 (sk-ant-api / ghp_ / xoxb- still hit) | unit | `pytest tests/tools/test_secret_patterns_v2.py::test_v1_regression -x` | ❌ W0 | ⬜ pending |
| 15 | TBD | 0 | TOOL-V2-01 | T-14-02 | low-entropy negatives: Chinese prose / short English / UUID hex below threshold | unit | `pytest tests/tools/test_secret_patterns_v2.py::test_low_entropy_negatives -x` | ❌ W0 | ⬜ pending |
| 16 | TBD | 0 | TOOL-V2-01 | — | surface drift: tool not in current hermes → drop + count + dist tracked | unit | `pytest tests/tools/test_surface_drift.py::test_drop_unknown_tool -x` | ❌ W0 | ⬜ pending |
| 17 | TBD | 0 | TOOL-V2-01 | — | surface drift report top-N truncation; metrics.json full | unit | `pytest tests/tools/test_surface_drift.py::test_report_truncation -x` | ❌ W0 | ⬜ pending |
| 18 | TBD | 0 | TOOL-V2-01 | T-14-03 | JSONL bad-line skip: 1 corrupt line → skip + counter + 5% warn threshold | unit | `pytest tests/tools/test_jsonl_skip_bad.py::test_skip_bad_line -x` | ❌ W0 | ⬜ pending |
| 19 | TBD | 0 | TOOL-V2-01 | T-14-03 | EvalDataset.load remains strict (NOT touched by D-18 scope) | unit | `pytest tests/tools/test_jsonl_skip_bad.py::test_evaldataset_strict_unchanged -x` | ❌ W0 | ⬜ pending |
| 20 | TBD | 0 | TOOL-V2-01 | T-14-04 | mine CLI: missing `--i-have-consent` → exit 1 with explicit message | unit | `pytest tests/tools/test_mine_cli.py::test_consent_required -x` | ❌ W0 | ⬜ pending |
| 21 | TBD | 0 | TOOL-V2-01 | — | mine CLI: `--dry-run` skips LLM, prints candidate distribution | unit | `pytest tests/tools/test_mine_cli.py::test_dry_run -x` | ❌ W0 | ⬜ pending |
| 22 | TBD | 0 | TOOL-V2-01 | — | mine CLI: `--signals=error_retry,user_correction` skips oracle path | unit | `pytest tests/tools/test_mine_cli.py::test_signal_subset -x` | ❌ W0 | ⬜ pending |
| 23 | TBD | 0 | TOOL-V2-01 | — | mine CLI: `--misselection-multiplier "error_retry=5,user_correction=2"` parses | unit | `pytest tests/tools/test_mine_cli.py::test_multiplier_override -x` | ❌ W0 | ⬜ pending |
| 24 | TBD | 0 | TOOL-V2-01 | — | mine CLI: `--baseline-module` absent → C signal silently skipped (warn) | unit | `pytest tests/tools/test_mine_cli.py::test_baseline_module_optional -x` | ❌ W0 | ⬜ pending |
| 25 | TBD | 0 | TOOL-V2-01 | — | metrics.json schema: every CONTEXT specifics field present (`total_candidates_by_signal`, `judge_*`, `surface_drift_*`, `final_*`, `multiplier_used`, `secret_filter_skipped`, `jsonl_skipped_lines`) | unit | `pytest tests/tools/test_session_miner.py::test_metrics_schema -x` | ❌ W0 | ⬜ pending |
| 26 | TBD | 0 | TOOL-V2-01 | — | mine() end-to-end smoke (mock LM, fixture sessions) | unit | `pytest tests/tools/test_session_miner.py::test_mine_end_to_end -x` | ❌ W0 | ⬜ pending |
| 27 | TBD | 0 | TOOL-V2-01 | — | evolve_tool_descriptions `--session-source`: session-side hash wins on collision | integration | `pytest tests/tools/test_evolve_with_session_source.py::test_session_overrides_synth -x` | ❌ W0 | ⬜ pending |
| 28 | TBD | 0 | TOOL-V2-01 | — | evolve_tool_params `--session-source`: train.jsonl already pre-duplicated (no double duplication at evolve load time) | integration | `pytest tests/tools/test_evolve_with_session_source.py::test_no_double_duplication -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Threat refs (from PLAN threat_model — to be filled by planner):**
- `T-14-01` — Untrusted LLM judge output silently corrupts dataset (mitigation: typed Signature + try/except → drop)
- `T-14-02` — Secrets exfiltrated into JSONL output (mitigation: SECRET_PATTERNS v2 + Shannon entropy ≥4.0/4.3 threshold)
- `T-14-03` — Corrupt JSONL aborts evolve loop (mitigation: per-line try/except + skip counter + 5% warn)
- `T-14-04` — Operator runs mine without explicit consent (mitigation: `--i-have-consent` mandatory flag)

---

## Wave 0 Requirements

**Test files to create (none exist):**
- [ ] `tests/tools/test_session_signal_extract.py` — B/A/C extractors + parser tolerance
- [ ] `tests/tools/test_session_judge.py` — ConfirmMisselection Signature contract; mock LM
- [ ] `tests/tools/test_session_split.py` — hash determinism + bucket edges + normalize
- [ ] `tests/tools/test_session_miner.py` — `mine()` end-to-end + metrics + duplication
- [ ] `tests/tools/test_secret_patterns_v2.py` — Layer 1 (JWT + AWS + entropy); v1 regression
- [ ] `tests/tools/test_jsonl_skip_bad.py` — bad-line skip + EvalDataset strict-mode unchanged
- [ ] `tests/tools/test_surface_drift.py` — drop + report
- [ ] `tests/tools/test_mine_cli.py` — `click.testing.CliRunner`, all flags
- [ ] `tests/tools/test_evolve_with_session_source.py` — integration (mock LM + tiny dataset)

**Fixtures to create (under `tests/fixtures/sessions/`):**
- [ ] `error_retry_b.json` — user → assistant tool_call(A) → tool error → assistant tool_call(B) → tool success
- [ ] `user_correction_a.json` — user → assistant tool_call → tool success → user "不对，应该用 X" → assistant tool_call(X)
- [ ] `oracle_disagreement_c.json` — user → assistant tool_call(Y) → success; baseline ToolModule predicts X
- [ ] `malformed_msg.json` — message missing `role`; `tool_calls` non-array
- [ ] `multi_signal.json` — both B + A hit → max(3,3) = 3× train multiplier
- [ ] `surface_drift.json` — assistant calls `legacy_tool_v0` not in current hermes
- [ ] `secret_in_user_msg.json` — user content contains JWT and high-entropy token

**Framework install:** None — pytest 7.0+ already in `pyproject.toml`.

**Reusable fixtures from existing repo:**
- `mock_lm_with_usage` from `tests/conftest.py:7-38` — reuse for ConfirmMisselection judge mocking and user_correction LLM 二判 mocking.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 44-session real-data dry-run smoke (no LLM cost) | TOOL-V2-01 | Validates real `~/.hermes/sessions/*.json` schema variance not captured by 7 fixtures | `python -m evolution.tools.mine_tool_sessions --i-have-consent --dry-run --sessions-dir ~/.hermes/sessions --signals error_retry,user_correction,oracle_disagreement --baseline-module output/tool-descriptions/<latest> --output /tmp/dry-run-44`; verify Rich summary table prints, no API calls made (check OPENAI logs/billing), `metrics.json` written with candidate counts ≥1 per signal where applicable |
| Entropy threshold calibration | TOOL-V2-01 | Threshold (4.0 → 4.3) needs tuning against real data after first dry-run; SHA256 hex measured at ~4.20 in research, dangerous proximity to 4.0 | Run dry-run; inspect `secret_filter_skipped` count; hand-audit `miner_log.jsonl` for false-positive entropy hits; if false-positive rate > 5%, raise threshold to 4.3 in CLI default |
| First wet run cost sanity | TOOL-V2-01 | Confirm $9 estimate (gpt-4.1) holds; abort if drift > 2× | Run with `--judge-model openai/gpt-4.1-mini --limit 5`; verify cost in OpenAI dashboard ≤ $0.20; extrapolate to 44-session run |

---

## Validation Sign-Off

- [ ] All 28 tests have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all 9 missing test files + 7 fixtures
- [ ] No watch-mode flags (`-n auto`, `--watch` excluded)
- [ ] Feedback latency < 30s (quick) / 180s (full)
- [ ] `nyquist_compliant: true` set in frontmatter (after planner attaches all tests to tasks)

**Approval:** pending
