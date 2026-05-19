---
phase: 20-benchmark-gated-validation
plan: "04"
subsystem: evolution.benchmarks
tags:
  - phase-20
  - benchmark
  - cli
  - calibration
dependency_graph:
  requires:
    - 20-01-config-scaffolding (EvolutionConfig.benchmark_max_cost_usd + tblite_estimated_cost_per_task_usd + benchmark_runs fields)
    - 20-02-tblite-runner (TBLiteRunner + TBLiteRunResult + TBLITE_RUNNER_VERSION)
    - 20-03-benchmark-gate (TIERS constant)
  provides:
    - build_tblite_calibration.py (Click CLI producing tblite_anchor.json)
    - _hf_dataset_revision() (D-15 HF fail-open)
    - _check_hermes_clean() (D-10 dirty-tree gate)
    - _git_head() (hermes-agent commit reader)
    - _one_run_per_tier_pass_rate() (local tier aggregation)
    - tests/benchmarks/test_build_tblite_calibration.py (8 CliRunner tests)
  affects:
    - 20-05-anchor-generation-checkpoint (this CLI is what Plan 05 executes)
    - 20-06-evolve-integration (prerequisite: tblite_anchor.json must exist before --benchmark=tblite)
tech_stack:
  added:
    - statistics.mean + statistics.stdev (stdlib, no numpy — CLAUDE.md no-new-deps)
    - huggingface_hub.HfApi (optional import inside try/except for D-15 fail-open)
  patterns:
    - Phase 18 build_drift_calibration.py structural analog (~85% overlap)
    - D-17 Pre-flight Watermark check (cost-per-task × tasks × runs × 3 safety factor)
    - D-16 Dual-track CostTracker (independent from GEPA max_cost_usd)
    - D-15 HF fail-open: unknown_v<TBLITE_RUNNER_VERSION> fallback
    - D-10 git-dirty block with --accept-stale-anchor escape hatch
    - Rich Table with dynamic Run 1..N columns driven by --runs
key_files:
  created:
    - evolution/benchmarks/build_tblite_calibration.py
    - tests/benchmarks/test_build_tblite_calibration.py
  modified: []
decisions:
  - "CostTracker wired around multi-run loop (D-16) with RuntimeWarning suppressed in tests via expect behavior — the warning is correct behavior (no real LM calls in tests)"
  - "stratified_subset_seed read from subset JSON, not --seed CLI flag — subset file is the authoritative source"
  - "TDD: wrote 8 failing tests first (RED commit f92a17a), then implementation (GREEN commit cff2fb4)"
  - "W-7 dual-schema tolerance: task_filter items accepted as both {name, tier} dict (new) or plain str (legacy)"
metrics:
  duration: "~4 minutes"
  completed_date: "2026-05-19"
  tasks_completed: 2
  files_created: 2
  tests_added: 8
---

# Phase 20 Plan 04: Build Calibration CLI Summary

**One-liner:** Click CLI building `datasets/prompts/tblite_anchor.json` with Pre-flight Watermark (D-17), CostTracker dual-track (D-16), 3-run TBLite aggregation, and HuggingFace dataset revision fingerprint with fail-open fallback (D-15).

## What Was Built

### evolution/benchmarks/build_tblite_calibration.py (488 lines)

The standalone CLI that produces `datasets/prompts/tblite_anchor.json` — the prerequisite artifact for Plan 05 (anchor generation checkpoint) and Plan 06 (evolve-integration gate).

**Key components:**

1. **8 Click flags** — `--hermes-repo`, `--seed`, `--runs`, `--output-json`, `--benchmark-max-cost`, `--model`, `--api-base`, `--accept-stale-anchor`

2. **Pre-flight suite (steps 1-3):**
   - Path existence + `prompt_builder.py` anchor check (D-14)
   - `git status --porcelain` dirty-tree block with `--accept-stale-anchor` escape (D-10)
   - `~/.hermes/tmp` + `~/.hermes/backups` mkdir + write-check
   - **Watermark check (D-17):** `estimated_cost × 3 <= benchmark_max_cost_usd` BEFORE subprocess

3. **HuggingFace `_hf_dataset_revision()`** (D-15 + Risk Anchor 5):
   - Calls `HfApi().dataset_info("NousResearch/openthoughts-tblite").sha`
   - Catches ALL exceptions → falls back to `unknown_v{TBLITE_RUNNER_VERSION}`
   - Fallback string still invalidates cache on runner version bumps

4. **Multi-run loop with CostTracker** (D-16):
   - `CostTracker(max_usd=budget)` is separate from GEPA's tracker
   - Each `TBLiteRunner.run()` output processed by local `_one_run_per_tier_pass_rate()`
   - `tracker.exceeded()` checked after each run

5. **Per-tier aggregation** — `statistics.mean` + `statistics.stdev` (stdlib, no numpy)

6. **Rich Table** — columns: Tier | N tasks | Run 1 | ... | Run N | Mean | Stdev (dynamic Run N columns driven by `--runs`)

7. **D-CAL-01 schema** — anchor JSON contains all required keys: `anchor_per_tier`, `dataset_revision_hash`, `hermes_agent_commit`, `stratified_subset_seed`, `tblite_estimated_cost_per_task_usd` (MEASURED, not config default), `calibration_timestamp`, `calibration_model`, `tblite_runner_version`

### tests/benchmarks/test_build_tblite_calibration.py (330 lines, 8 tests)

| Test | What It Covers |
|------|----------------|
| test_anchor_json_schema_complete | D-CAL-01 all 8 top-level keys + all 4 tiers with mean/stdev/n |
| test_seed_is_persisted_from_subset | subset JSON seed wins over --seed CLI flag |
| test_huggingface_fallback_on_api_error | HF API raises → unknown_v1.0 in anchor (no exit) |
| test_git_dirty_check_blocks_calibration | _check_hermes_clean raises → exit_code != 0, anchor NOT written |
| test_pre_flight_watermark_blocks_when_insufficient_budget | 8 tasks × 3 runs × $0.4 = watermark $28.8 > $5 → abort |
| test_tblite_cost_per_task_measured_and_written | measured cost field present + numeric type |
| test_runs_aggregates_mean_stdev | 3 runs [0.5, 1.0, 1.0] → mean ≈ 0.833, stdev > 0, n=3 |
| test_accept_stale_anchor_bypasses_git_check | _check_hermes_clean NOT called with flag |

## Verification Evidence

```
python -m evolution.benchmarks.build_tblite_calibration --help → shows 8 flags (actually 9 with --help)
grep -c 'CostTracker' evolution/benchmarks/build_tblite_calibration.py → 2
grep -c 'watermark' evolution/benchmarks/build_tblite_calibration.py → 4
grep -c 'huggingface_hub' evolution/benchmarks/build_tblite_calibration.py → 2
grep -c 'dataset_revision_hash' evolution/benchmarks/build_tblite_calibration.py → 5
grep -c 'hermes_agent_commit' evolution/benchmarks/build_tblite_calibration.py → 2
wc -l evolution/benchmarks/build_tblite_calibration.py → 488 (>= 280 requirement met)
pytest tests/benchmarks/test_build_tblite_calibration.py -v → 8 passed in 6.19s
pytest tests/benchmarks/ → 35 passed (18 gate + 8 calibration + 9 runner, NO REGRESSION)
```

### `python -m evolution.benchmarks.build_tblite_calibration --help` (first 25 lines)

```
Usage: python -m evolution.benchmarks.build_tblite_calibration
           [OPTIONS]

  Build TBLite anchor + persist datasets/prompts/tblite_anchor.json.

Options:
  --hermes-repo PATH          Override HERMES_AGENT_REPO. Defaults to env /
                              ~/.hermes/hermes-agent.
  --seed INTEGER              Random seed persisted in anchor (D-CAL-01).
  --runs INTEGER              TBLite invocations per calibration run (D-03
                              median-of-N). Defaults to config.benchmark_runs
                              (3).
  --output-json PATH          Output path for anchor JSON. Default is git-
                              tracked per .gitignore exception added in Plan
                              01.
  --benchmark-max-cost FLOAT  Phase 20 D-16 dual-track budget for this
                              calibration run (USD). Defaults to
                              config.benchmark_max_cost_usd (50.0).
  --model TEXT                Override calibration_model field (e.g.
                              openai/gpt-4.1).
  --api-base TEXT             Override API base URL.
  --accept-stale-anchor       [unsafe] Allow writing the anchor even if
                              hermes-agent has uncommitted changes.
```

## Commits

| Hash | Message |
|------|---------|
| f92a17a | test(20-04): add 8 failing CliRunner tests for build_tblite_calibration RED phase |
| cff2fb4 | feat(20-04): implement build_tblite_calibration CLI — Pre-flight + Watermark + 3-run + HF revision + Rich Table |

## Deviations from Plan

None — plan executed exactly as written.

The plan provided complete code skeletons that were followed closely. One minor structural adjustment: the `anchor` dict uses `sort_keys=True` in `json.dumps` as specified, which means the keys will be sorted alphabetically in the output file regardless of insertion order. This matches the plan's requirement.

## Known Stubs

None — all functionality is implemented. The CLI is not wired to a real `tblite_anchor.json` production run (that is Plan 05's job), but the code itself is complete and testable.

## Notes

- This CLI alone does NOT produce a real anchor.json — Plan 05 is the BLOCKING task that runs this CLI against live TBLite + Modal.
- `CostTracker` emits a `RuntimeWarning` during tests because `dspy.settings.track_usage` is `False` (no real LM calls in tests). This is expected and documented behavior from Phase 13 (Pitfall 2 / W4). The warning does not indicate a defect.
- Wave-1 imports (`TBLiteRunner`, `TBLITE_RUNNER_VERSION` from Plan 02; `TIERS` from Plan 03) resolve correctly after base reset to 843dae0.

## Threat Flags

No new security surface introduced beyond the plan's threat model (T-20-18..T-20-23). All mitigations implemented:
- T-20-18: Watermark check still fires when budget=-1 (watermark > -1 always)
- T-20-19: HuggingFace try/except catches all exceptions including TimeoutError
- T-20-20: calibration_model field is model name (not API key) — safe to persist
- T-20-21: _meta.placeholder warning emitted but not blocking (correct behavior)
- T-20-22: --accept-stale-anchor is_flag=True, marked [unsafe] in help text
- T-20-23: git stash list check deferred to Plan 06+ (accepted, same as T-20-12)

## Self-Check: PASSED
