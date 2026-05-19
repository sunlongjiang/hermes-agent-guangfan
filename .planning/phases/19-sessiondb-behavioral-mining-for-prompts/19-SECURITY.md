---
phase: 19
slug: sessiondb-behavioral-mining-for-prompts
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-19
---

# Phase 19 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| `~/.hermes/sessions/*.json` → `SessionPromptMiner` | Layer-3 PII boundary — real user transcripts enter the mining pipeline only after `--i-have-consent` gate | session JSON (`role`/`content`); may contain user secrets pre-filter |
| `SessionPromptMiner` → DSPy LLM judge | Confirmed candidates sent to external LLM (`openai/gpt-4.1`) for verdict + difficulty + rubric | task text + assistant summary + downstream turns (already secret-filtered) |
| `mine_prompt_sessions.mine()` → `datasets/prompts/sessions/<ts>/` | On-disk persistence of session-derived examples | counts + section_ids + user_message[:200] (no raw secrets, JWT/AWS filtered upstream) |
| `evolve_prompt_sections.py --session-source` → in-memory `PromptBehavioralDataset` | Cross-source union with synthetic dataset | session JSONL parsed via per-line try/except; cross-split hash dedup |
| `HERMES_AGENT_REPO` → `extract_prompt_sections()` | Read-only access to `prompt_builder.py` for current section_id surface | prompt section text (read-only; no writeback path imported) |

---

## Threat Register

### Plan 19-01 — Dataset Schema Extension

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-19-01-S | Spoofing | `PromptBehavioralExample.from_dict` | mitigate | `__dataclass_fields__` filter drops unknown keys (`prompt_dataset.py:102`); `mining_signals` reuses same path | closed |
| T-19-01-T | Tampering | persistence schema | mitigate | `mining_signals: list[str] = field(default_factory=list)` (`prompt_dataset.py:81`) — pre-Phase-19 JSONL round-trips unchanged | closed |
| T-19-01-I | Info Disclosure | dataclass field set | mitigate | `prompt_dataset.py:76-81` — verified `session_path`/`turn_idx`/`verdict_rationale` NOT present in fields (grep returns 0 hits in module) | closed |
| T-19-01-D | DoS | `_normalize_task_hash` | accept | `prompt_dataset.py:32-40` — pure SHA-256 over a single bounded string; O(len), inputs capped by session JSON sizes | closed |
| T-19-01-E | Elevation | `_hash_to_split` | accept | `prompt_dataset.py:43-54` — pure function (no side effects, no I/O) | closed |

### Plan 19-02 — SessionPromptMiner Core

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-19-02-T | Tampering/Info-Disc | candidate.task / downstream_context | mitigate | `_filter_secrets` (`session_prompt_miner.py:298-310`) calls `_contains_secret` on task/downstream_context/originally_observed_behavior BEFORE LLM judge; increments `secret_filter_skipped` metric | closed |
| T-19-02-D | DoS | `_load_session` corrupted JSON | mitigate | `try/except` (`session_prompt_miner.py:292-296`) → `session_load_failures += 1`; 5% warn threshold at `mine()` (`session_prompt_miner.py:687-695`); B3 fix separates file-level vs line-level skip channels | closed |
| T-19-02-I (T4) | Info Disclosure | section_id surface drift | mitigate | `_filter_drift` (`session_prompt_miner.py:312-328`) drops verdicts where `section_id ∉ current_section_ids` AFTER judge; metrics records `surface_drift_dropped` + per-section count | closed |
| T-19-02-I (T5) | Info Disclosure | LLM judge parsing | mitigate | `_judge_candidates` (`session_prompt_miner.py:587-617`) try/except wraps `self.judge()`; verdict ∉ `{confirm_example, false_positive}` → `false_positive`; difficulty ∉ `DIFFICULTY_VALUES` → `medium` | closed |
| T-19-02-E | Elevation | DriftDetector lazy init | accept | `session_prompt_miner.py:233-243` — missing `drift_thresholds` → silent disable + Rich warn; no privilege escalation path | closed |
| T-19-02-R | Repudiation | judge_calls metrics | mitigate | All verdicts persisted in `judge_calls_by_signal`, `judge_confirmed_by_signal`, `judge_false_positives_by_signal` (`session_prompt_miner.py:613-624`) | closed |

### Plan 19-03 — mine_prompt_sessions CLI

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-19-03-S | Spoofing | `--i-have-consent` | mitigate | `mine_prompt_sessions.py:271-280` — missing flag → `click.echo(err=True)` referencing `~/.hermes/sessions/` + `return 1`; tested via `TestConsentGate` (3 tests) | closed |
| T-19-03-T | Tampering | `_parse_signals` / `_parse_multiplier_override` | mitigate | `mine_prompt_sessions.py:56-99` — whitelist via `VALID_SIGNALS`; unknown signal/key/non-int/missing `=` → `click.UsageError` | closed |
| T-19-03-I | Info Disclosure | metrics.json content | mitigate | `metrics.json` only contains counts + section_id names (no raw text); `miner_log.jsonl` truncates `user_message_excerpt` to `[:200]` (`mine_prompt_sessions.py:463`); user warned via consent gate copy | closed |
| T-19-03-I | Info Disclosure | FAILED_<ts>/metrics.json detail | mitigate | `_write_failed` extras carry only path strings + `type(e).__name__: str(e)` (`mine_prompt_sessions.py:315/325/352/381/432`); `no_examples_post_judge` writes `miner.metrics` which itself contains only counts/section_id names (no raw session text) | closed |
| T-19-03-D | DoS | `--limit` / unbounded sessions_dir | mitigate | `--limit` Click option (default 0=all, user-cappable); `--dry-run` skips LLM judge; Plan 19-02 inherits 5% bad-lines warn | closed |
| T-19-03-E | Elevation | `--hermes-repo` / `HERMES_AGENT_REPO` | accept | Reuses Phase 14 `EvolutionConfig.load` (`mine_prompt_sessions.py:310-312`); read-only access to `prompt_builder.py` via `extract_prompt_sections`; no write paths imported | closed |

### Plan 19-04 — evolve_prompt_sections Integration

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-19-04-T (T3) | Tampering/DoS | session JSONL bad lines | mitigate | `_load_session_dataset_resilient` (`evolve_prompt_sections.py:119-163`) — per-line try/except `(JSONDecodeError, TypeError, ValueError)`; >5% Rich warn at `_SESSION_SOURCE_BAD_LINE_WARN = 0.05` | closed |
| T-19-04-I (T4) | Info Disclosure | session-derived drift in train | mitigate | Already filtered upstream by Plan 02 `_filter_drift` before union; cross-confirmed in `TestPhase18Untouched.test_step_8c_drift_wiring_intact` | closed |
| T-19-04-T | Tampering | hash collision cross-split | mitigate | `evolve_prompt_sections.py:364-385` — two-pass union: pass 1 builds `all_session_hashes` across all splits; pass 2 drops any synthetic example whose hash ∈ `all_session_hashes` (D-15/D-16) | closed |
| T-19-04-E | Elevation | `--session-source` path missing | mitigate | `click.Path(exists=True, path_type=Path)` (`evolve_prompt_sections.py:1170`) rejects at Click parse time | closed |
| T-19-04-R | Repudiation | session_skipped count | accept | Console-only in evolve (resilient loader); persisted in mine `metrics.json` per Plan 03 — dual-channel audit trail preserved via B3 fix | closed |

### Plan 19-05 — Integration Tests (test code)

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-19-05-S | Spoofing | fixture JWT | accept | `tests/prompts/fixtures/sessions/session_with_secret.json:5` uses synthetic `eyJhbGciOiJIUzI1NiJ9.eyJpZCI6MX0.signaturesignaturesignature_more_padding...` shape — not a real token; comments document test purpose | closed |
| T-19-05-T | Tampering | tmp_path FAILED_<ts>/ | mitigate | `chdir_tmp` fixture monkeypatches cwd to `tmp_path`; `CliRunner` captures stdout/stderr independently; tests confine all writes to scoped tmp dir | closed |
| T-19-05-I | Info Disclosure | `session_with_secret.json` fixture | mitigate | JWT payload is synthetic + intentionally formed to trigger SECRET_PATTERNS regex; `_filter_secrets` test asserts the message is dropped before reaching judge or output writer | closed |
| T-19-05-D | DoS | mock chain depth | mitigate | Each test ≤ 0.5s; full `tests/prompts/` suite finishes in 46s (~3.23s without DSPy import warmup); 221 tests passing with zero regression | closed |
| T-19-05-E | Elevation | `_train_msg` / `_holdout_msg` brute force | accept | Hash-bucket enumeration helpers bound by `assert i < 10000` (`test_evolve_prompt_sections_session_source.py:179, 194`); deterministic hash distribution makes practical iteration count small | closed |

*Status: all 27 threats closed.*
*Disposition: mitigate (15) · accept (12).*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-19-01 | T-19-01-D | `_normalize_task_hash` is a pure SHA-256 over a single bounded string (≤500 chars per `_first_user_task`/`task[:500]` caps in extractors). Input size bounded by upstream `_load_session` + extractor truncation. No DoS surface. | Phase planner | 2026-05-18 |
| AR-19-02 | T-19-01-E | `_hash_to_split` is a pure function (`int(h[:8], 16) % 100`) with no side effects, no I/O, no LLM calls. Cannot mutate state. | Phase planner | 2026-05-18 |
| AR-19-03 | T-19-02-E | DriftDetector lazy init returns `None` and prints a Rich warn when thresholds missing — no privilege state changes; mirror of `oracle_disagreement` disabled-without-baseline pattern. | Phase planner | 2026-05-18 |
| AR-19-04 | T-19-03-E | `--hermes-repo` override is delegated to `EvolutionConfig.load` (Phase 14 contract). Path is used only for read access via `extract_prompt_sections`; no write paths imported (verified — `prompt_loader.write_back_section` import grep returns 0 hits in `mine_prompt_sessions.py`). | Phase planner | 2026-05-18 |
| AR-19-05 | T-19-04-R | Session-source loader skip counts are console-only in `evolve_prompt_sections`; persistent audit trail lives in mine pipeline `metrics.json` via Plan 19-03. Dual-channel B3 fix prevents conflation. | Phase planner | 2026-05-18 |
| AR-19-06 | T-19-05-S | Fixture JWT `eyJhbGciOiJIUzI1NiJ9.eyJpZCI6MX0.signature...` is synthetic, padded to satisfy SECRET_PATTERNS regex. Not a real credential — used only to validate filter behavior. | Phase planner | 2026-05-18 |
| AR-19-07 | T-19-05-E | Hash-bucket enumeration helpers `_train_msg` / `_holdout_msg` in tests are bounded by `i < 10000`. Empirically each terminates in <100 iterations because `_hash_to_split` distributes ~70/15/15 across SHA-256-uniform input. | Phase planner | 2026-05-18 |

*Accepted risks do not resurface in future audit runs.*

---

## Unregistered Flags

None — all Threat Flags in SUMMARYs 19-01..19-05 map to existing threat IDs. The "Threat Surface Scan" section of each SUMMARY explicitly asserts "No new threat surface beyond the plan's `<threat_model>`."

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-19 | 27 | 27 | 0 | /gsd-secure-phase (Claude Opus 4.7) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-19
