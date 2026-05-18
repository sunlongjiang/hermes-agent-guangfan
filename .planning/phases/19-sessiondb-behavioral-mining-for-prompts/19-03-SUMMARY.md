---
phase: 19-sessiondb-behavioral-mining-for-prompts
plan: 03
subsystem: prompts
tags:
  - prompt
  - cli
  - mining
  - privacy-gate
requirements:
  - PMPT-V2-04
dependencies:
  requires:
    - "Plan 19-01: PromptBehavioralExample.mining_signals + _normalize_task_hash + _hash_to_split"
    - "Plan 19-02: SessionPromptMiner + split_and_duplicate + DEFAULT_MULTIPLIER + VALID_SIGNALS"
  provides:
    - "evolution.prompts.mine_prompt_sessions: Click CLI module"
    - "main: Click command — 13 options + --i-have-consent gate"
    - "mine(): orchestration entry — returns int exit code"
    - "_parse_signals / _parse_multiplier_override: CSV / kv helpers"
    - "_print_summary_table: Rich 4-signal table + B3 fix labels"
    - "_write_failed: FAILED_<ts>/metrics.json marker writer"
  affects:
    - "Plan 19-04 (evolve_prompt_sections --session-source): consumes datasets/prompts/sessions/<ts>/ output directory layout"
    - "Plan 19-05 (integration tests): exercises CLI end-to-end"
tech_stack:
  added: []
  patterns:
    - "Click @command + 13 @option decorators (Phase 14 mirror)"
    - "Rich Panel intro + Table summary + colored warn (yellow/red/green)"
    - "Lazy file-existence check for --drift-thresholds-path (W2 fix: no exists=True)"
    - "B3 fix metric-channel separation: session_load_failures vs jsonl_skipped_lines"
    - "FAILED_<ts>/metrics.json structured failure marker with error_key + diagnostic extras"
    - "Dry-run path bypasses LLM judge for API cost estimation"
key_files:
  created:
    - "evolution/prompts/mine_prompt_sessions.py (472 LoC)"
    - "tests/prompts/test_mine_prompt_sessions.py (503 LoC, 24 tests)"
  modified: []
decisions:
  - "[D-17] CLI exposes 13 Click options — 12 Phase 14 symmetric flags + 1 NEW --drift-thresholds-path"
  - "[D-20] Success output: train/val/holdout.jsonl + metrics.json + miner_log.jsonl five-file topology"
  - "[D-25] --i-have-consent enforced via click.echo(err=True) + return 1 (catchable by tests), not raise SystemExit"
  - "[W2 fix] --drift-thresholds-path uses click.Path(path_type=Path) WITHOUT exists=True; lazy check inside mine() only when persona_drift signal active; missing file → Rich warn + remove from signals_list (symmetric with oracle_disagreement disabled-on-missing-baseline)"
  - "[B3 fix] Rich summary explicitly labels session_load_failures (file-level, mine scope) and JSONL skipped lines (line-level, Plan 04 helper scope) as separate metric channels to avoid audit log conflation"
  - "[D-04] oracle_disagreement signal gracefully disabled when --baseline-module absent OR when the path is given but evolved_sections.json is missing (warn, continue other signals)"
  - "miner_log.jsonl truncates user_message to 200 chars per T-19-03-I threat mitigation (no raw secrets since _filter_secrets ran in mine())"
metrics:
  duration: ~10 minutes
  completed: 2026-05-18
  tasks_completed: 2
  files_created: 2
  files_modified: 0
  prompt_tests_before: 167 passed, 1 skipped (after Plan 19-02)
  prompt_tests_after: 191 passed, 1 skipped (+24 new tests)
  regression: zero
  module_loc: 472
  click_options: 13
---

# Phase 19 Plan 03: SessionDB Prompt Mining CLI Summary

**One-liner:** Ships `python -m evolution.prompts.mine_prompt_sessions` — a 13-flag Click CLI wrapping `SessionPromptMiner.mine()` + `split_and_duplicate` to produce 5-file behavioral-mining output directories from `~/.hermes/sessions/*.json`, with hard `--i-have-consent` privacy gate, lazy `--drift-thresholds-path` (W2 fix), labeled session-load vs JSONL-line metric channels (B3 fix), dry-run for LLM-cost estimation, and `FAILED_<ts>/` markers for 5 failure scenarios.

## What Was Built

Two RED/GREEN cycles delivered the CLI module + 24-test coverage:

1. **Task 3.1 (skeleton, 17 tests):** module docstring + imports + `_parse_signals` / `_parse_multiplier_override` (UsageError on unknown signal / empty input / non-int multiplier) + 13 Click options (12 Phase 14 symmetric + new `--drift-thresholds-path`) + `--i-have-consent` hard gate (click.echo to stderr + return 1) + `mine()` stub raising `NotImplementedError`. W2 fix: `--drift-thresholds-path` registered with `click.Path(path_type=Path)` **without** `exists=True` so the default path missing on a user box does not block the consent gate.

2. **Task 3.2 (mine body, 7 tests):** `_print_summary_table` (Rich Table — 4 signal rows + TOTAL + B3 fix dual-channel labels for session-load vs JSONL-line skips) + `_write_failed` helper (consolidates 6 failure scenarios — `sessions_dir_missing`, `config_load_failed`, `prompt_extraction_failed`, `no_sections_found`, `no_examples_post_judge`, `mine_exception` — into a single `FAILED_<ts>/metrics.json` writer) + full `mine()` orchestration (consent gate → parse → resolve paths → load config/sections → lazy drift_thresholds load with graceful disable → optional baseline_module check with graceful disable → SessionPromptMiner instantiation → dry-run candidate enumeration OR real mine + split_and_duplicate + PromptBehavioralDataset.save + metrics.json + miner_log.jsonl).

## Files Created

| File | LoC | Role |
|------|-----|------|
| `evolution/prompts/mine_prompt_sessions.py` | 472 | Click CLI module + mine() orchestrator |
| `tests/prompts/test_mine_prompt_sessions.py` | 503 | 24 unit tests (17 Task 3.1 + 7 Task 3.2) |

### Line ranges (mine_prompt_sessions.py)

| Symbol | Lines |
|--------|-------|
| Module docstring | 1-28 |
| Imports | 30-49 |
| `_parse_signals` | 53-65 |
| `_parse_multiplier_override` | 68-97 |
| Click `main` command (13 options) | 100-168 |
| `_print_summary_table` | 173-232 |
| `_write_failed` | 235-250 |
| `mine()` body | 253-470 |
| `if __name__ == "__main__"` | 472-473 |

## CLI 13-Flag Reference (with defaults)

| Flag | Default | Purpose |
|------|---------|---------|
| `--sessions-dir` | `~/.hermes/sessions` | Directory containing session_*.json |
| `--output` | `datasets/prompts/sessions/<YYYYMMDD_HHMMSS>/` | Output directory |
| `--limit` | `0` (all) | Max sessions to scan |
| `--i-have-consent` | (required flag) | Layer 3 privacy gate (D-25) |
| `--signals` | `user_correction,section_specific_failure,oracle_disagreement,persona_drift` | 4-way default (vs Phase 14 3-way) |
| `--baseline-module` | `None` | Phase 10/17/18 output dir for oracle_disagreement |
| `--judge-model` | `None` (use config.judge_model) | Override judge LLM |
| `--behavioral-multiplier` | `None` (use D-13 defaults) | "user_correction=3,..." override |
| `--hermes-repo` | `None` (use HERMES_AGENT_REPO env) | Override hermes-agent location |
| `--model` | `None` | Override non-judge LLM |
| `--api-base` | `None` | Override API base URL |
| `--dry-run` | `False` | Enumerate candidates without LLM judge |
| `--drift-thresholds-path` | `Path("datasets/prompts/drift_thresholds.json")` | persona_drift thresholds (lazy check; W2 fix) |

## 3 Documented Failure Scenarios (D-20 FAILED_<ts>/ contract)

| Scenario | error_key | Trigger | extra fields |
|----------|-----------|---------|--------------|
| sessions-dir not on disk | `sessions_dir_missing` | `not sessions_path.exists()` | `sessions_dir: <resolved path>` |
| prompt_builder unreachable / parse error | `prompt_extraction_failed` | `extract_prompt_sections()` raises | `detail: <type>: <msg>`, `prompt_builder_path` |
| extract returns empty list | `no_sections_found` | `not current_sections` | `prompt_builder_path` |
| miner.mine() raises | `mine_exception` | wrapping mine() try/except | `detail: <type>: <msg>` |
| zero examples after LLM judge | `no_examples_post_judge` | `not examples` after mine() | `metrics: <miner.metrics snapshot>` |
| EvolutionConfig.load raises | `config_load_failed` | env / hermes_repo resolution fails | `detail: <type>: <msg>` |

Each scenario writes `datasets/prompts/sessions/FAILED_<YYYYMMDD_HHMMSS>/metrics.json` and returns exit code 1. Diagnostic extras never include raw session content (T-19-03-I mitigation).

## Sample dry-run Output

```
╭───────────────────────────────╮
│ SessionDB Behavioral Mining   │
│   Timestamp: 20260518_120000  │
│   Signals:   user_correction  │
│   Dry-run:   True             │
╰───────────────────────────────╯
DRY RUN — skipping LLM judge
  Sessions scanned: 45
  Candidates before LLM judge: 87
  Estimated LLM judge calls (no dry-run): 87
```

(`split_and_duplicate` not invoked in dry-run; no JSONL files written.)

## Plan 19-04 Integration Entry

Plan 04 (`evolve_prompt_sections.py --session-source <path>`) consumes the success-path directory layout exactly as documented in D-20:

```
datasets/prompts/sessions/<YYYYMMDD_HHMMSS>/
├── train.jsonl       # PromptBehavioralDataset.train serialized line-by-line
├── val.jsonl
├── holdout.jsonl
├── metrics.json      # 16-key schema from Plan 19-02 SessionPromptMiner.metrics
└── miner_log.jsonl   # one audit line per accepted example (user_message ≤ 200 chars)
```

`PromptBehavioralDataset.load(out_dir)` (existing API from Plan 19-01) round-trips train/val/holdout. Plan 04's union step uses `_normalize_task_hash` from Plan 19-01 to dedup across synthetic + session sources.

## Commits

| Hash | Type | Description |
|------|------|-------------|
| `4216dd9` | test | RED — 24 failing tests for Task 3.1 + 3.2 |
| `2993ad7` | feat | GREEN for Task 3.1 — CLI skeleton + 13 options + helpers + consent gate + W2 fix |
| `389fa20` | feat | GREEN for Task 3.2 — mine() body + Rich summary + 5-file output + FAILED markers + lazy graceful disable |

## Plan-defined Verify Output

### Task 3.1 verify automated
All 17 Task 3.1 tests pass:
- import surface (main + mine + 2 helpers exported, main is click.Command)
- `--help` exit 0 + lists all 13 flag names (verified both via subprocess and CliRunner)
- no `--i-have-consent` → exit !=0 with `--i-have-consent` + `~/.hermes/sessions` in error output
- W2 fix: default `--drift-thresholds-path` missing must NOT yield "Invalid value" before consent gate (regression guard)
- `_parse_signals`: valid CSV, dedup-preserves-order, unknown raises with "unknown", empty raises with "empty", whitespace-only raises
- `_parse_multiplier_override`: valid kv, None / "" → {}, non-int raises with "int", unknown signal raises with "unknown", missing `=` raises

### Task 3.2 verify automated
All 7 Task 3.2 tests pass:
- sessions_dir missing → FAILED_/ with `error: sessions_dir_missing`
- no_sections_found (mocked `extract_prompt_sections` → []) → FAILED_/ with `error: no_sections_found` or `prompt_extraction_failed`
- `--dry-run` does NOT call `miner.mine` (mocked SessionPromptMiner; verified `mine.assert_not_called()`)
- persona_drift requested + drift_thresholds_path missing → Rich warn + signal removed from `signals_list` passed to `SessionPromptMiner(...)` (W2 fix lazy disable; NOT Click 'Invalid value' rejection)
- oracle_disagreement requested + no `--baseline-module` → Rich warn + `baseline_module=None` passed to miner constructor (graceful disable, continue)
- `--judge-model override-judge-model` → `config.judge_model == "override-judge-model"` before miner construction
- Full success path with mocked miner returning 1 example + `split_and_duplicate` mocked → out_dir contains 5 files (train.jsonl with 3 dup lines, val.jsonl, holdout.jsonl, metrics.json with judge_calls=1, miner_log.jsonl), exit 0; Rich summary contains all 4 signal names + B3 fix dual labels for `session_load_failures` and `JSONL skipped lines`

### Full pytest run
```
tests/prompts/ — 191 passed, 1 skipped in 20.16s
```
Wave 2 baseline 167 passed + 24 new Wave 3 tests = 191. Single pre-existing Phase 18 skip is unchanged. Zero regression.

## W2 Fix Evidence — Lazy drift_thresholds Check

```
$ grep -nE 'click\.Path\(.*exists=True' evolution/prompts/mine_prompt_sessions.py
(empty — no Click param uses exists=True)

$ grep -nE '"persona_drift" in signals_list' evolution/prompts/mine_prompt_sessions.py
337:    if "persona_drift" in signals_list:

$ grep -nE 'signals_list = \[s for s in signals_list if s != "persona_drift"\]' evolution/prompts/mine_prompt_sessions.py
344:            signals_list = [s for s in signals_list if s != "persona_drift"]
356:                signals_list = [s for s in signals_list if s != "persona_drift"]
```

Line 337-344 (file-missing branch) and 350-356 (parse-error branch) implement symmetric graceful disable. The only `exists=True` token in the file appears in a help-string explaining the design decision (line 155), not in actual Click parameter code. Regression test `test_default_drift_thresholds_path_does_not_block_consent` asserts the absence of `"Invalid value"` in CLI output when the default path is missing on disk.

## B3 Fix Evidence — Metric Channel Separation in Summary

```
$ grep -nE 'session_load_failures|Session load failures' evolution/prompts/mine_prompt_sessions.py
176:    B3 fix: explicitly prints BOTH session_load_failures (file-level, mine
219:        f"  Session load failures (file-level, mine_prompt_sessions scope): "
220:        f"{metrics.get('session_load_failures', 0)}"

$ grep -nE 'JSONL skipped lines' evolution/prompts/mine_prompt_sessions.py
223:        f"  JSONL skipped lines (line-level, evolve_prompt_sections session-source scope): "
```

`_print_summary_table` (lines 173-232) writes the two channels with explicit scope labels so a glance at the terminal output makes clear which counter relates to whole-file JSON load failures (mine() scope, Plan 19-03 owns) vs which counter relates to JSONL line-skips (Plan 19-04's `_load_session_dataset_resilient` scope). The B3 fix anchor is also reflected in the corresponding unit test — `test_full_success_path_writes_5_files` asserts both labels appear in CLI output.

## Deviations from Plan

**Two minor adjustments inside the plan's `<action>` scope; no semantic deviation.**

1. **Plan grep regex `@click\.option\(\s*"--<name>"` did not match because Click options are multi-line in the file** (decorator opens with `@click.option(`, option string starts on the next line). All 13 options exist with the correct names; verified with `grep -nE '"--drift-thresholds-path"|"--behavioral-multiplier"'`. The plan's grep predicate was tied to a single-line layout convention. The CLI behavior — what `--help` reports and what CliRunner accepts — is identical. Not classified as a deviation: acceptance via `--help` flag enumeration + 13-option count + CliRunner integration tests all pass.

2. **Plan grep `exists=True` outputs **empty** for Click params, but the file contains the string "NO exists=True" in a help docstring** (line 155) explaining the W2 fix. The plan's intent was to ensure no Click parameter uses `exists=True`; that constraint is satisfied (`grep -nE 'click\.Path\(.*exists=True'` returns empty). The substring "exists=True" appearing inside a help string is a deliberate annotation explaining why the decision differs from Phase 14, and is not a regression.

The CONFIRM check `grep -nE "if .persona_drift. in signals_list" evolution/prompts/mine_prompt_sessions.py` from the plan was satisfied by the equivalent `if "persona_drift" in signals_list:` at line 337 (Python normalizes quote style; the grep escape sequences `.` matched the literal quote characters in the plan's regex; verified content-equivalent).

## Authentication Gates

None. Pure offline implementation — all tests use `unittest.mock` to bypass `EvolutionConfig.load`, `extract_prompt_sections`, and `SessionPromptMiner`. No LLM calls; no auth-protected APIs touched. Real-world `python -m evolution.prompts.mine_prompt_sessions --i-have-consent ...` requires `OPENAI_API_KEY` / `OPENROUTER_API_KEY` via DSPy's standard path (inherited from Phase 14; no Phase 19 escalation).

## Known Stubs

None. `grep -c 'NotImplementedError' evolution/prompts/mine_prompt_sessions.py` = 0 (the Task 3.1 placeholder was replaced in Task 3.2). No hardcoded empty arrays or placeholder text routed to user-visible output.

## Threat Surface Scan

No new threat surface beyond the plan's `<threat_model>`. All 6 STRIDE entries are mitigated:

| Threat ID | Mitigation Implementation Anchor |
|-----------|----------------------------------|
| T-19-03-S (consent spoof) | `if not i_have_consent:` line 190 — `click.echo(err=True)` + `return 1`; error message explicitly names `~/.hermes/sessions/` data source so auditors understand the scope. Test `test_no_consent_subprocess_exits_nonzero`. |
| T-19-03-T (input tamper) | `_parse_signals` / `_parse_multiplier_override` — whitelist via `VALID_SIGNALS`; non-int / unknown signal / empty / missing `=` raise `click.UsageError`. 11 covering tests in `TestTask31_ParseSignals` + `TestTask31_ParseMultiplier`. |
| T-19-03-I (metrics leak) | `_write_failed` extra dict carries only path strings + `type(e).__name__: str(e)` — never raw session content. `miner_log.jsonl` truncates `user_message_excerpt` to 200 chars (line 460) and SECRET_PATTERNS filter ran in mine() before reaching this point. |
| T-19-03-I (FAILED detail) | Same `_write_failed` contract; verified by inspection in `test_sessions_dir_missing_writes_failed_marker` and `test_no_sections_found_writes_failed_marker`. |
| T-19-03-D (DoS) | `--limit` Click option (default 0 = all, user can cap); `--dry-run` enumerates candidates without spending LLM budget; Plan 19-02 inherits the 5% bad-lines warn. |
| T-19-03-E (hermes-repo override) | Accepted in threat register — Phase 14 EvolutionConfig.load path is reused; only-read access to prompt_builder.py via `extract_prompt_sections`. No write paths invoked. |

No new threat flags emerged — module imports nothing from hermes-agent write paths (`grep -nE 'write_back_section|hermes_agent.*write' evolution/prompts/mine_prompt_sessions.py` empty), no new network endpoints, no auth or trust-boundary changes vs Wave 2.

## Self-Check: PASSED

- `evolution/prompts/mine_prompt_sessions.py` (472 LoC): FOUND
- `tests/prompts/test_mine_prompt_sessions.py` (24 tests, 503 LoC): FOUND
- Commit `4216dd9` (RED): FOUND in `git log`
- Commit `2993ad7` (Task 3.1 GREEN): FOUND
- Commit `389fa20` (Task 3.2 GREEN): FOUND
- `--help` lists all 13 flag names: verified
- No-consent path exits non-zero with required substrings: verified
- W2 fix `exists=True` absent from Click params: verified
- B3 fix dual labels `Session load failures` + `JSONL skipped lines` in summary: verified
- 191 prompt tests passing, 1 skipped, zero regression: verified
- 0 `NotImplementedError` remaining: verified
- Click options count == 13: verified
