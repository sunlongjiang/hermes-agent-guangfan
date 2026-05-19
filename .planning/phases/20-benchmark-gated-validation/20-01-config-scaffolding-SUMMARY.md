---
phase: 20-benchmark-gated-validation
plan: "01"
subsystem: benchmark-config
tags:
  - phase-20
  - benchmark
  - config
  - scaffolding
dependency_graph:
  requires:
    - evolution/core/config.py (Phase 13 max_cost_usd override chain pattern)
    - .gitignore (Phase 18 drift artifact git-exception pattern)
  provides:
    - evolution/benchmarks/ (lazy-import-guarded package)
    - EvolutionConfig.benchmark_max_cost_usd / tblite_estimated_cost_per_task_usd / benchmark_runs / benchmark_heartbeat_seconds
    - datasets/prompts/tblite_stratified_subset.json (W-7 tier-explicit 30-task whitelist)
    - .gitignore tblite exception lines + logs/ ignore
  affects:
    - evolution/prompts/evolve_prompt_sections.py (Wave 6: reads new config fields)
    - evolution/benchmarks/tblite_runner.py (Wave 2: reads benchmark_heartbeat_seconds)
    - evolution/benchmarks/benchmark_gate.py (Wave 3: reads benchmark_max_cost_usd, benchmark_runs)
tech_stack:
  added:
    - "evolution/benchmarks/ package (new)"
    - "datasets/prompts/tblite_stratified_subset.json (new)"
  patterns:
    - "Phase 13 max_cost_usd 4-block override chain (field/YAML/env/CLI) — 1:1 replicated for 4 new fields"
    - "Phase 18 drift artifact .gitignore exception pattern — same ! exception syntax"
    - "Lazy-import guard pattern (evolution/code/__init__.py sibling style with docstring)"
key_files:
  created:
    - evolution/benchmarks/__init__.py
    - datasets/prompts/tblite_stratified_subset.json
  modified:
    - evolution/core/config.py (+158 lines: 4 fields × 4-block override chain)
    - .gitignore (+9 lines: tblite exceptions + logs/ ignore)
decisions:
  - "W-7 schema: task_filter is list of {name, tier} objects (NOT flat string list) to eliminate brittle implicit-ordering contract"
  - "Lazy-import guard in __init__.py (D-Discretion-1): no eager submodule imports to keep --benchmark=none path working"
  - "4-block override chain (YAML < env < CLI) mirrors Phase 13 max_cost_usd 1:1 for consistency"
  - "datasets/prompts/ directory created (did not previously exist) to house tblite artifacts"
metrics:
  duration: "~12 min"
  completed: "2026-05-19"
  tasks_completed: 3
  tasks_total: 3
  files_created: 2
  files_modified: 2
---

# Phase 20 Plan 01: Config Scaffolding Summary

Wave 1 config + package scaffolding for Phase 20 benchmark-gated validation. Added 4 new EvolutionConfig fields with full YAML/env/CLI 3-tier override chain, created lazy-import-guarded evolution/benchmarks/ package, and bootstrapped the 30-task W-7 tier-explicit stratified subset JSON.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Add 4 benchmark config fields + YAML/env/CLI override chain | 392b03e | evolution/core/config.py |
| 2 | Create evolution/benchmarks/ package with lazy-import-guard | 18a0c7c | evolution/benchmarks/__init__.py |
| 3 | Create tblite_stratified_subset.json + .gitignore updates | e7a1d30 | datasets/prompts/tblite_stratified_subset.json, .gitignore |

## Diff Stats

| File | Lines Added | Lines Removed |
|------|-------------|---------------|
| evolution/core/config.py | +158 | ~0 (restructure of load() comments) |
| evolution/benchmarks/__init__.py | +15 | 0 (new file) |
| datasets/prompts/tblite_stratified_subset.json | +51 | 0 (new file) |
| .gitignore | +9 | 0 |

## Verification Results

- 4-block override chain confirmed: `grep -v '^#' evolution/core/config.py | grep -c 'benchmark_max_cost_usd'` = 15 (well above 4 minimum)
- All env vars present: EVOLUTION_BENCHMARK_MAX_COST_USD, EVOLUTION_TBLITE_COST_PER_TASK_USD, EVOLUTION_BENCHMARK_RUNS, EVOLUTION_BENCHMARK_HEARTBEAT_SECONDS
- `git check-ignore -v datasets/prompts/tblite_stratified_subset.json` shows `!datasets/prompts/tblite_stratified_subset.json` as last matching rule → file is git-trackable
- `python -c "import evolution.benchmarks"` exits 0
- `evolution.benchmarks.__doc__` contains "Lazy-import guard"
- `task_filter` is a list of `{name, tier}` dicts: all 30 items verified; tier-count consistency holds (easy:12, medium:8, hard:7, extreme:3 = 30)
- `_meta.schema_version == "2"` (W-7 revision marker)
- `pytest tests/ --collect-only` collects 640 tests with no regressions

## Known Stubs

- `datasets/prompts/tblite_stratified_subset.json`: `task_filter[].name` fields are placeholder values (`tblite-easy-01` through `tblite-extreme-03`). `_meta.placeholder: true` is set. Wave 4 (`build_tblite_calibration`) will overwrite with real TBLite task names from HuggingFace. Schema (tier field per object) is final and will not change.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Structural] config.py was earlier-version without max_cost_usd field**
- **Found during:** Task 1
- **Issue:** The plan's Task 1 described inserting after the existing `max_cost_usd` field (Phase 13 artifact), but the worktree's config.py was an older version (145 lines) without `max_cost_usd` or the 3-tier YAML/env/CLI override chain structure.
- **Fix:** Implemented the full 3-tier override chain structure from scratch on the existing `load()` method, adding the 4 new benchmark fields directly into the YAML/env/CLI sections already present in the existing load() method.
- **Files modified:** evolution/core/config.py
- **Commit:** 392b03e

**2. [Rule 3 - Blocking] datasets/prompts/ directory did not exist**
- **Found during:** Task 3
- **Issue:** The `datasets/prompts/` directory was not present in the worktree (only `datasets/skills/` and `datasets/tools/` existed).
- **Fix:** Created `datasets/prompts/` directory before writing the JSON file.
- **Files modified:** datasets/prompts/ (directory created)
- **Commit:** e7a1d30

**3. [Rule 3 - Blocking] .planning/phases/20-benchmark-gated-validation/ directory missing in worktree**
- **Found during:** SUMMARY creation
- **Issue:** Phase 20 planning directory existed in main repo but not in the worktree.
- **Fix:** Created the directory before writing SUMMARY.md.
- **Files modified:** .planning/phases/20-benchmark-gated-validation/ (directory created)

## Self-Check: PASSED

- `evolution/core/config.py`: FOUND ✓
- `evolution/benchmarks/__init__.py`: FOUND ✓
- `datasets/prompts/tblite_stratified_subset.json`: FOUND ✓
- `.gitignore` with tblite exceptions: FOUND ✓
- Commit 392b03e: FOUND ✓
- Commit 18a0c7c: FOUND ✓
- Commit e7a1d30: FOUND ✓
