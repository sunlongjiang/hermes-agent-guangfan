---
phase: 14-sessiondb-mining-for-tools
plan: 01
status: complete
type: execute
wave: 0
tasks_executed: 3
tasks_total: 3
commits: 2
duration_ms: recovery
---

# SUMMARY — Plan 14-01 (Test Scaffolding + Fixtures)

## Goal

为 Phase 14 Wave 1+ 落地 TDD 红灯基线：创建全部 9 个新测试文件（28 个测试函数 stub）+ 7 个 session fixture JSON，让 14-VALIDATION.md 的每一行 `<automated>` 命令都能定位到真实的目标函数；本 plan 不写任何生产代码。

## What was built

### Artifacts (16 new files, all committed)

| Artifact | Purpose |
|----------|---------|
| `tests/fixtures/sessions/error_retry_b.json` | B 信号 fixture — tool error (exit_code=1) → retry |
| `tests/fixtures/sessions/user_correction_a.json` | A 信号 fixture — 中文 "应该用 X" 纠正 |
| `tests/fixtures/sessions/oracle_disagreement_c.json` | C 信号 fixture — 单次成功 tool_call |
| `tests/fixtures/sessions/malformed_msg.json` | schema-tolerance fixture — 缺 role + 非数组 tool_calls |
| `tests/fixtures/sessions/multi_signal.json` | B+A 双源命中 fixture |
| `tests/fixtures/sessions/surface_drift.json` | 工具表面漂移 fixture — `legacy_tool_v0` (不在 current hermes) |
| `tests/fixtures/sessions/secret_in_user_msg.json` | 隐私 gate fixture — JWT + SHA256 hex |
| `tests/tools/test_session_signal_extract.py` | rows 1-4 — B/A/C extractor + parser tolerance |
| `tests/tools/test_session_judge.py` | rows 5-6 — ConfirmMisselection round-trip + LM fail-closed |
| `tests/tools/test_session_split.py` | rows 7-10 — hash bucket edges / determinism / normalize / signals union |
| `tests/tools/test_session_miner.py` | rows 11, 12, 25, 26 — duplication + multiplier max + metrics schema + end-to-end |
| `tests/tools/test_secret_patterns_v2.py` | rows 13-15 — layer1 positives / v1 regression / low-entropy negatives |
| `tests/tools/test_jsonl_skip_bad.py` | rows 18-19 — skip bad line + EvalDataset strict unchanged |
| `tests/tools/test_surface_drift.py` | rows 16-17 — drop unknown tool + report truncation |
| `tests/tools/test_mine_cli.py` | rows 20-24 — consent / dry-run / signal subset / multiplier / baseline optional |
| `tests/tools/test_evolve_with_session_source.py` | rows 27-28 — session 优先 + 不重复 duplication |

### Commits

1. `8a1aff0` — `test(14-01): add 7 session fixtures for Phase 14 miner tests` — Task 1.1 (7 fixtures, all JSON-valid, RESEARCH §Pitfall 1 schema)
2. `92cc936` — `test(14-01): scaffold 9 test files with 28 pytest.skip stubs (Task 1.2 + rescue)` — 9 test files, 28 stub functions

## Verification

- `pytest --collect-only` on the 9 new files → **28 tests collected** ✓ (target ≥ 28)
- Full suite: **395 passed + 28 skipped + 1 xfailed** (existing 385 baseline intact; 10 passed are a pre-existing delta, not from this plan)
- `git diff --name-only evolution/` → empty ✓ (no source changes)
- `git diff pyproject.toml` → empty ✓ (no dependency changes)
- Guards held:
  - No top-level `_shannon_entropy` import in `test_secret_patterns_v2.py` (Plan 03 Task 3.2 symbol not yet landed)
  - No top-level `evolution.tools.session_miner` import anywhere (Plan 04 symbol not yet landed)
  - `mock_lm_with_usage` reused via pytest auto-discovery, never redefined

## Deviations from PLAN.md

### 1. Execution recovery — mid-session harness lockout

The Plan 01 executor agent committed Task 1.1 cleanly (`8a1aff0`) then lost Write/Edit/Bash-write permissions mid-session while creating the 9 test files — only 3 of 9 stubs (`test_session_signal_extract.py`, `test_session_judge.py`, `test_session_split.py`) were written to the working tree before the lockout (uncommitted).

The orchestrator completed the plan by:

1. Preserving the 3 untracked files written by the agent (content unchanged from agent output)
2. Authoring the 6 missing files (`test_session_miner`, `test_secret_patterns_v2`, `test_jsonl_skip_bad`, `test_surface_drift`, `test_mine_cli`, `test_evolve_with_session_source`) per exact spec in 14-01-PLAN.md §Task 1.2
3. Running `pytest --collect-only` (28 collected) and full suite (GREEN) in the worktree
4. Committing the 9-file bundle as `92cc936`
5. Writing this SUMMARY.md

No spec was diluted — every acceptance criterion from 14-01-PLAN.md Task 1.2 and Task 1.3 was met on the final state of the branch.

### 2. Cross-plan fixture overlap (informational)

Plan 03's agent also hit a harness lockout and its "Rule 3 auto-fix bootstrap" commit (`8f3c894` on Plan 03 branch) independently created `tests/fixtures/sessions/secret_in_user_msg.json` and a stub version of `tests/tools/test_secret_patterns_v2.py`. When merging Wave 1 branches back to main, the orchestrator must resolve:

- **Fixture** (`secret_in_user_msg.json`): Plan 01 is authoritative (per plan spec) — use Plan 01's version, discard Plan 03's bootstrap copy. Both contain the JWT + SHA256 literals Plan 03's RED tests reference.
- **Test file** (`test_secret_patterns_v2.py`): Plan 03 supersedes Plan 01 — use Plan 03's RED-assertion version (it intentionally replaces Plan 01's skip stubs with real assertions for Task 3.1 RED gate).

This resolution is applied by the orchestrator's wave-merge step; Plan 01's deliverable state is correct as committed on its own branch.

## Self-Check: PASSED

- 9 test files present ✓
- 7 fixture files present ✓
- 28 test functions collected ✓
- All acceptance criteria from 14-01-PLAN.md Task 1.1/1.2/1.3 verified ✓
- No regressions to baseline test suite ✓
- No `evolution/` source changes ✓
- No `pyproject.toml` changes ✓
