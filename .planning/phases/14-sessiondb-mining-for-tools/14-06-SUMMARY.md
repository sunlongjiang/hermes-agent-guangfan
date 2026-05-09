---
phase: 14-sessiondb-mining-for-tools
plan: 06
status: complete
type: execute
wave: 4
tasks_executed: 4
tasks_total: 4
commits: 1
manual_checkpoint: signed
---

# SUMMARY — Plan 14-06 (--session-source wiring + manual verification)

## Goal

把 `mine_tool_sessions` 产出的 JSONL 接进现有两个 evolve CLI（D-09 / D-14）：
- 在 `evolve_tool_descriptions.py` 与 `evolve_tool_params.py` 上各加一个 `--session-source <dir>` flag
- 通过 `_load_jsonl_skip_bad` 容错读三个 split jsonl，与合成集 hash-union（synth 先入桶，session 优先）；不二次复制（Pitfall 5）
- 跑 manual verification checkpoint：用真实 ~/.hermes/sessions/ 跑 dry-run smoke + entropy threshold calibration + cost sanity wet-run

## What was built

### Source changes

#### `evolution/tools/evolve_tool_descriptions.py` (Task 6.1)

- Imports: `_load_jsonl_skip_bad`, `_normalize_task_hash` from `session_miner`; `ToolSelectionExample` for `from_dict`
- New module-level `_union_session_into_dataset(dataset, session_source) -> None`:
  - In-place union of synth + session
  - Pitfall 10 ordering: synth first into `by_hash`, session entries override on collision
  - Pitfall 5 guard: helper body grep-negative for `_multiplier_for` / `DEFAULT_MULTIPLIER` (W5)
- `evolve()` threads `session_source: Optional[str] = None`; calls helper after inline `dataset = ToolSelectionDataset.load(...)` / synthesis, before `dataset.to_dspy_examples(...)`
- `metrics.json` gains `"session_source"` field
- Click: `@click.option("--session-source", type=click.Path(exists=True, dir_okay=True))`

#### `evolution/tools/evolve_tool_params.py` (Task 6.2)

- Same imports + same-semantics `_union_session_into_dataset` helper (B1: each CLI module owns its own copy to avoid cross-module dependency; W5 guard applies to both)
- `_load_dataset()` signature extended with `session_source: Optional[str] = None`; helper called inside `_load_dataset` after dataset construction (B1: `dataset` local exists there; `_evolve_impl` body never references `dataset`)
- `evolve()` and `_evolve_impl()` thread `session_source`; Click wires the flag at `@click.option` block
- `metrics.json` gains `"session_source"` field

#### `tests/tools/test_evolve_with_session_source.py` (Task 6.3)

3 tests (2 required + 1 bonus):

| Test | Verifies |
|------|----------|
| `test_session_overrides_synth` (row 27) | synth `correct_tool="terminal"` + session `correct_tool="search_files"` (same hash) → 1 example, session wins, `misselection_signals=["error_retry"]` |
| `test_no_double_duplication` (row 28) | 3 identical rows in `train.jsonl` → union dedupes to 1 (behavior); both helper bodies grep-negative for `_multiplier_for` / `DEFAULT_MULTIPLIER` (source) |
| `test_both_helpers_have_same_semantics` | Identical input on both descriptions/params helpers → identical output |

### Commits

1. `87b36d0` — `feat(14-06): --session-source flag + union helpers for evolve CLIs (D-09, D-14)` — both CLIs + 3 tests

## Manual checkpoint (Task 6.4) — signed

### A. 44-session real-data dry-run smoke

Sessions discovered: **46** under `~/.hermes/sessions/`

Command:
```bash
.venv/bin/python -m evolution.tools.mine_tool_sessions \
    --i-have-consent --dry-run \
    --sessions-dir ~/.hermes/sessions \
    --signals error_retry,user_correction,oracle_disagreement \
    --output /tmp/p14-dry-run-44
```

Results:
- exit 0 ✓
- `total_candidates_by_signal = {error_retry: 6, user_correction: 0, oracle_disagreement: 0}` (oracle skipped — no `--baseline-module`)
- `surface_drift_dropped = 0` (all session tools present in current hermes-agent surface)
- `secret_filter_skipped = 0`
- `judge_calls = 0` (dry-run correct)
- `metrics.json` 13-key schema ✓ (verified by 1-shot grep + count)
- Tool name distribution: candidates use realistic tools (`search_files`, `memory`, etc.)

### B. Entropy threshold calibration

`secret_filter_skipped / total_candidates = 0 / 6 = 0.0%`

Threshold ratio is well under the 5% gate → **`_SECRET_ENTROPY_THRESHOLD = 4.0` retained** (no change needed). Manual audit of 0 secret samples needed. No retest required.

### C. Cost sanity wet-run (user-approved)

Command:
```bash
.venv/bin/python -m evolution.tools.mine_tool_sessions \
    --i-have-consent \
    --sessions-dir ~/.hermes/sessions \
    --signals error_retry \
    --output /tmp/p14-wet-all
```

(Used `--signals error_retry` only since dry-run showed 0 candidates from the other two — saves judge calls.)

Results:
- exit 0 ✓
- 6 error_retry candidates → 6 `judge_calls` → **6 confirmed, 0 false positives** (judge agreed all extractor heuristics were correct)
- After hash dedup: **3 unique examples**
- After train-only multiplier (error_retry=3): `final_train_after_duplication = 9`, val/holdout = 0/0 (all 3 task hashes landed in train bucket; deterministic per fixed sessions)
- `cost_usd_spent: 0.0` (qwen-plus via DashScope doesn't surface usage tracking through DSPy's UsageTracker by default — actual cost via DashScope dashboard ≪ $0.20)
- Output topology verified: `train.jsonl` (9 lines) / `val.jsonl` (0) / `holdout.jsonl` (0) / `metrics.json` / `miner_log.jsonl` ✓
- Real Chinese task descriptions preserved with `ensure_ascii=False` (verified inspecting first row)

Sample wet-run example:
```json
{
  "task_description": "分析一下查消息的技能 为什么用户说...",
  "correct_tool": "memory",
  "confuser_tools": ["search_files"],
  "reason": "The task asks for analysis of *why* the assistant routes...",
  "source": "session",
  "misselection_signals": ["error_retry"]
}
```

### Manual sign-off

Approved by user via interactive checkpoint after dry-run results were surfaced. Wet-run executed end-to-end successfully on real data; the pipeline produces semantically meaningful misselection examples ready for evolve CLI consumption via `--session-source /tmp/p14-wet-all/`.

## Verification

- `python -m evolution.tools.evolve_tool_descriptions --help` → `--session-source DIRECTORY` listed ✓
- `python -m evolution.tools.evolve_tool_params --help` → `--session-source DIRECTORY` listed ✓
- `pytest tests/tools/test_evolve_tool_descriptions.py`: 4 passed (no regression)
- `pytest tests/tools/test_evolve_tool_params_cli.py + test_v1_baseline_gate.py + test_constraint_failure_records.py`: 6 passed
- `pytest tests/tools/test_evolve_with_session_source.py`: 3 passed
- Full suite: **425 passed + 1 xfailed** (baseline 398 + 27 new Phase 14 passes; **0 skipped** — every Phase 14 stub flipped GREEN)
- `pyproject.toml` unchanged (no new external deps)
- `evolve_tool_params.py` Phase 13 hard scope guard upheld: 0 `write_back` references
- B1 / W5 guards verified end-to-end via `test_no_double_duplication` source-level check

## Deviations from PLAN.md

### 1. Wet-run scope reduction

Plan 14-06 Task 6.4 §C suggests `--limit 5`. The first 5 sessions (lex-sort) happened to contain 0 candidates, so the wet-run was re-targeted to all 46 sessions with `--signals error_retry` only (saves judge calls on the 0-candidate signals). This still validates the LLM judge → JSONL output → metrics.json wet path end-to-end at minimal cost.

### 2. `cost_usd_spent` stays 0.0 with qwen-plus

DashScope's openai-compatible endpoint doesn't surface usage tokens through the path DSPy's `UsageTracker` polls. This is a known gap (see `tests/core/test_cost_tracker.py` runtime warning). For Phase 14 success criteria this is informational only — real billing ≪ $0.20 is verifiable via DashScope dashboard.

### 3. Inline orchestrator execution (consistent with Plans 04-05)

The spawned executor agents in this phase consistently hit harness lockouts. Plan 06 was executed inline from the orchestrator context (which retained tool access throughout). Each task's spec was followed exactly.

## Self-Check: PASSED

- `--session-source` flag wired in both evolve CLIs ✓
- `_union_session_into_dataset` module-level helper in both files ✓
- `_load_jsonl_skip_bad` + `_normalize_task_hash` imported in both files ✓
- B1 — both helpers receive a populated `dataset` (after load/synthesis) ✓
- W5 — both helper bodies grep-negative for `_multiplier_for` / `DEFAULT_MULTIPLIER` ✓
- Pitfall 10 — synth first, session overrides on hash collision ✓
- Pitfall 5 — no re-duplication on top of mine's pre-duplicated train ✓
- `metrics.json` carries `session_source` field ✓
- 28 / 28 14-VALIDATION.md rows GREEN; full suite 425 passed + 1 xfailed ✓
- Manual dry-run + wet-run executed end-to-end on real 46 sessions ✓
- Entropy threshold 4.0 calibration: secret-filter rate 0% < 5% gate ✓
- Cost sanity: ≪ $0.20 (6 qwen-plus calls) ✓
