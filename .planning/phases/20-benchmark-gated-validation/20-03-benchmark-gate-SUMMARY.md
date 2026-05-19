---
phase: 20-benchmark-gated-validation
plan: "03"
subsystem: evolution.benchmarks
tags:
  - phase-20
  - benchmark
  - gate
  - virtual-overlay
dependency_graph:
  requires:
    - 20-01-config-scaffolding-PLAN.md
  provides:
    - TBLiteBenchmarkGate class
    - Risk_Score algorithm (D-01 + D-02)
    - Virtual Prompt Overlay (D-09)
    - write_back_section dest= extension (D-09)
  affects:
    - evolution/prompts/prompt_loader.py (extended)
    - evolution/benchmarks/benchmark_gate.py (new)
    - tests/benchmarks/test_benchmark_gate.py (new)
tech_stack:
  added: []
  patterns:
    - tier-weighted Risk_Score breach accumulation
    - Virtual Prompt Overlay with try/finally always-restore
    - content-addressed cache (D-15 sha256[:16])
    - infra_fail row exclusion from tier denominators
key_files:
  created:
    - evolution/benchmarks/benchmark_gate.py
    - evolution/benchmarks/tblite_runner.py (Wave 2 stub)
    - tests/benchmarks/__init__.py
    - tests/benchmarks/test_benchmark_gate.py
  modified:
    - evolution/prompts/prompt_loader.py (dest= param added to write_back_section)
decisions:
  - "Virtual Prompt Overlay uses write_back_section(dest=overlay_path) option (a) — minimal invasive, backward-compatible"
  - "Cache write only on accept (not reject) so same evolved set re-runs deterministically"
  - "tblite_runner.py stub created in worktree for Wave 2 test isolation; Plan 02 replaces at merge"
  - "infra_fail detection uses task.get('infra_fail') flag set by tblite_runner"
metrics:
  duration: "~25 minutes"
  completed: "2026-05-19"
  tasks_completed: 3
  tasks_total: 3
  files_created: 4
  files_modified: 1
---

# Phase 20 Plan 03: Benchmark Gate Summary

## One-Liner

TBLiteBenchmarkGate with tier-weighted Risk_Score (D-02), Virtual Prompt Overlay atomic replace + try/finally restore (D-09), and write_back_section dest= extension for staging evolved copies.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Extend write_back_section with dest= param | d60c164 | evolution/prompts/prompt_loader.py |
| 2 | Create TBLiteBenchmarkGate class | dd35e4b | evolution/benchmarks/benchmark_gate.py, tests/benchmarks/__init__.py |
| 3 | Create 18 unit tests + tblite_runner stub | 4685e0a | tests/benchmarks/test_benchmark_gate.py, evolution/benchmarks/tblite_runner.py |

## File Metrics

- `benchmark_gate.py`: 648 lines
- `prompt_loader.py`: +21 lines (dest= parameter + docstring)
- `test_benchmark_gate.py`: 415 lines, 18 tests
- `tblite_runner.py` (stub): 109 lines

## Grep Evidence

- `os.replace` count in benchmark_gate.py: **4** (>= 2 required)
- `shutil.copy2` count in benchmark_gate.py: **6** (>= 2 required)
- `finally:` count in benchmark_gate.py: **1** (>= 1 required, D-09 step 5)
- `sys.exit(1)` count in benchmark_gate.py: **8** (>= 2 required, D-10 + D-14 hard fails)
- `compute_artifact_hash` count in benchmark_gate.py: **3** (>= 1 required)
- `subprocess.run` count in benchmark_gate.py: **2** (git status + git rev-parse)

## Test Results

```
tests/benchmarks/test_benchmark_gate.py: 18 passed in 5.86s
tests/prompts/ baseline: 221 passed, 1 skipped (NO REGRESSION after prompt_loader.py edit)
```

## Acceptance Criteria Verification

| Criterion | Status |
|-----------|--------|
| `from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate, TIER_WEIGHTS, REJECT_THRESHOLD, CONFIDENCE_Z, TIERS` succeeds | PASS |
| `TIER_WEIGHTS == {"easy":1.0,"medium":1.5,"hard":2.0,"extreme":4.0}` | PASS |
| `REJECT_THRESHOLD == 4.0` | PASS |
| `CONFIDENCE_Z == 1.96` | PASS |
| `os.replace` count >= 2 | PASS (4) |
| `shutil.copy2` count >= 2 | PASS (6) |
| `finally:` count >= 1 | PASS (1) |
| `sys.exit(1)` count >= 2 | PASS (8) |
| `compute_artifact_hash` count >= 1 | PASS (3) |
| benchmark_gate.py line count >= 350 | PASS (648) |
| test_benchmark_gate.py: 14+ tests passing | PASS (18) |
| write_back_section dest= parameter | PASS |
| Phase 7-19 tests/prompts/ no regression | PASS |

## Deviations from Plan

### Auto-added: Wave 2 tblite_runner.py stub (Rule 3 - Blocking Issue)

**Found during:** Task 3 (test creation)
**Issue:** Tests in `tests/benchmarks/test_benchmark_gate.py` import from `evolution.benchmarks.tblite_runner` (via `benchmark_gate.py` imports), but tblite_runner.py is created by Plan 02 running in a parallel worktree. Without it, the test file cannot be collected by pytest.
**Fix:** Created `evolution/benchmarks/tblite_runner.py` as a minimal stub providing:
- `TBLITE_RUNNER_VERSION = "1.0"` (same value as Plan 02)
- `TBLiteRunResult` dataclass (matching Plan 02 interface)
- `TBLiteRunner` class with `run()` raising `NotImplementedError`
- `compute_artifact_hash()` full implementation (matches Plan 02 D-15 formula)
**Files modified:** `evolution/benchmarks/tblite_runner.py` (created)
**Commit:** 4685e0a
**Note:** When Plan 02's worktree merges, the stub is replaced by the full implementation. The `compute_artifact_hash()` function is implemented fully (not stubbed) because the test `test_cache_hit_short_circuits_subprocess` needs to produce the same hash as `benchmark_gate.check()`.

## Key Decisions

1. **Virtual Prompt Overlay write strategy:** Used option (a) — extend `write_back_section` with `dest=` keyword param. This is the minimum-invasive approach preserving Phase 7-19 backward compatibility. All existing callers work without modification.

2. **Cache write policy:** Cache is written ONLY on `decision == "accept"`. Rejected runs are not cached so retries re-execute deterministically — important for diagnosing prompt regressions.

3. **fs-boundary detection:** `_run_overlay` and `_restore_overlay` both check `target.parent.stat().st_dev == overlay.parent.stat().st_dev`. Mismatch triggers `shutil.copy2` fallback. This is verified by `test_fs_boundary_cross_fs_uses_copy2_fallback`.

4. **subprocess-level error handling:** `run_status_any_error` flag overrides accept → reject when any `TBLiteRunResult.status != "ok"`. This prevents erroneously accepting results when TBLite hung or errored.

5. **Wave 2 integration note:** Plan 02 creates full `tblite_runner.py`; Plan 03's stub is a placeholder. Both are committed to different worktree branches. The orchestrator merges them at wave-end. The stub's `compute_artifact_hash()` matches Plan 02's formula exactly to ensure cache key compatibility.

## Known Stubs

None — all required functionality is implemented. `tblite_runner.py` is a Wave 2 integration stub (intentional), not a feature stub. Tests mock `TBLiteRunner.run()` via `patch.object`.

## Threat Flags

No new trust boundaries introduced beyond those in the plan's threat model (T-20-11..T-20-17). All mitigations implemented:
- T-20-11: snapshot + try/finally restore (`test_restore_overlay_called_on_subprocess_error`)
- T-20-13: anchor schema validation in constructor
- T-20-14: cache key includes dataset_revision_hash + TBLITE_RUNNER_VERSION
- T-20-16: subprocess.run(timeout=10) in git checks

## Self-Check: PASSED
