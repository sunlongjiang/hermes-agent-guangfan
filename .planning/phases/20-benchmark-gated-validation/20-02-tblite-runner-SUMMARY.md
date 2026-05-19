---
phase: 20-benchmark-gated-validation
plan: "02"
subsystem: evolution.benchmarks
tags:
  - phase-20
  - benchmark
  - subprocess
  - tdd
dependency_graph:
  requires:
    - 20-01-config-scaffolding (EvolutionConfig.benchmark_heartbeat_seconds + benchmark_max_cost_usd + benchmark_runs fields)
  provides:
    - TBLiteRunner (subprocess wrapper with Async Stream Pipe + State Monitor)
    - TBLiteRunResult (result dataclass with per_task / infra_fail / hang_count)
    - compute_artifact_hash (D-15 cache key formula)
    - TBLITE_RUNNER_VERSION (module-level constant for cache invalidation)
    - tests/benchmarks/ (9 unit tests, all passing)
  affects:
    - 20-03-benchmark-gate (consumes TBLiteRunner + TBLiteRunResult + compute_artifact_hash)
    - 20-04-calibration-cli (consumes TBLiteRunner + compute_artifact_hash + TBLITE_RUNNER_VERSION)
    - 20-06-evolve-integration (consumes TBLiteRunner indirectly via BenchmarkGate)
tech_stack:
  added:
    - subprocess.Popen (streaming, not blocking subprocess.run)
    - threading.Thread daemon=True × 2 (stdout + stderr pumps)
    - queue.Queue (heartbeat-based hang detection)
    - hashlib.sha256 (D-15 cache fingerprint)
  patterns:
    - Async Stream Pipe + State Monitor (new to evolution package — no prior analog)
    - Per-line try/except json.JSONDecodeError (Phase 19 D-24 mirror)
    - infra_fail flagging (Risk Anchor 3 — distinguish Modal failures from prompt failures)
    - T-20-05 whitelist regex validation (shell metachar injection prevention)
key_files:
  created:
    - evolution/benchmarks/tblite_runner.py
    - tests/benchmarks/__init__.py
    - tests/benchmarks/test_tblite_runner.py
  modified: []
decisions:
  - heartbeat_seconds clamped to max(1, int(hb_raw)) via constructor (T-20-04)
  - task_filter validated against ^[A-Za-z0-9][A-Za-z0-9_\-./]{0,127}$ BEFORE Popen (T-20-05)
  - test heartbeat set to 2s (not 60s default) for fast CI execution
  - _pump_stream uses broad try/except (ValueError + OSError) to survive race with terminate()
  - category/difficulty/tier normalization: first non-empty field wins, lowercased
metrics:
  duration: "~12 minutes"
  completed_date: "2026-05-19"
  tasks_completed: 3
  files_created: 3
  tests_added: 9
---

# Phase 20 Plan 02: TBLite Runner Summary

**One-liner:** TBLiteRunner subprocess wrapper with Async Stream Pipe + State Monitor, daemon-thread stdout/stderr pumps, heartbeat hang detection, per-line JSONL parsing with infra_fail flagging, and sha256 D-15 cache key.

## What Was Built

### evolution/benchmarks/tblite_runner.py (431 lines)

The core subprocess wrapper that Plans 03, 04, and 06 all depend on. Key components:

1. **TBLiteRunResult dataclass** — result type with `per_task` (list of dicts), `hang_count`, `infra_fail` per row, `jsonl_skipped_lines`, `stderr_tail`, `status: ok|hang_timeout|error`.

2. **Async Stream Pipe + State Monitor** (new to evolution package):
   - `subprocess.Popen(args, cwd=hermes_agent_path, stdout=PIPE, stderr=PIPE, text=True, bufsize=1)`
   - Two `threading.Thread(daemon=True)` pumps push `(stream_name, line)` tuples onto `queue.Queue`
   - Main loop: `q.get(timeout=heartbeat_seconds)` → `queue.Empty` → `hang_count += 1`; at `max_hangs` → `proc.terminate()` → `status='hang_timeout'`

3. **samples_*.jsonl parser** (Phase 19 D-24 mirror):
   - Per-line `try/except json.JSONDecodeError` + `jsonl_skipped_lines` counter
   - Warns at > 5% skip rate (`_JSONL_BAD_LINE_WARN_THRESHOLD`)
   - `infra_fail` flag: row with non-empty `error` field is excluded from tier pass-rate denominators

4. **T-20-05 mitigation** — `_validate_task_filter()` rejects task names not matching `^[A-Za-z0-9][A-Za-z0-9_\-./]{0,127}$` BEFORE `subprocess.Popen` args are constructed.

5. **compute_artifact_hash()** — D-15 cache key: `sha256(canonical_json(evolved) + dataset_revision_hash + seed.to_bytes(4) + TBLITE_RUNNER_VERSION)[:16]`

6. **TBLITE_RUNNER_VERSION = "1.0"** — module-level constant for cache invalidation across runner upgrades.

### tests/benchmarks/__init__.py (1 line)

Empty package marker allowing pytest to discover `tests/benchmarks/test_tblite_runner.py`.

### tests/benchmarks/test_tblite_runner.py (255 lines, 9 tests)

All tests mock `subprocess` via `patch.object(tblite_runner_module, "subprocess")` — no real subprocess invocations.

| Test | What It Covers |
|------|----------------|
| test_popen_args_constructed | cwd, text=True, bufsize=1, --env.task_filter CSV |
| test_popen_rejects_unsafe_task_names | T-20-05 regression guard (ValueError before Popen) |
| test_stream_pipe_parses_pass_fail_markers | [START]/[PASS]/[FAIL] consumed without hanging |
| test_heartbeat_timeout_triggers_hang | queue.Empty → hang_count → terminate() called |
| test_samples_jsonl_per_task_parse | per-task rows with category lowercased |
| test_jsonl_skip_bad_lines | malformed line counted, valid rows still parsed (D-24) |
| test_infra_failure_marked_separately | error field → infra_fail=True (Risk Anchor 3) |
| test_cache_key_deterministic | same inputs → same 16-char hex; different inputs → different |
| test_tblite_runner_version_constant | TBLITE_RUNNER_VERSION == '1.0' |

## Verification Evidence

```
grep -c 'subprocess\.Popen' evolution/benchmarks/tblite_runner.py → 4
grep -c 'queue\.Empty' evolution/benchmarks/tblite_runner.py → 3
grep -c 'daemon=True' evolution/benchmarks/tblite_runner.py → 2 (stdout pump + stderr pump)
grep -c 'subprocess\.run' evolution/benchmarks/tblite_runner.py → 0 (blocking call ABSENT)
wc -l evolution/benchmarks/tblite_runner.py → 431 (>= 180 requirement met)
pytest tests/benchmarks/test_tblite_runner.py -v → 9 passed in 12.20s
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Performance] Test heartbeat reduced from 60s default to 2s for CI**
- **Found during:** Task 3 execution (tests 3, 5, 6, 7 were waiting 60 seconds for queue timeout)
- **Issue:** Default `heartbeat_seconds=60` meant tests with mock streams that end immediately would wait 60 seconds for each `q.get()` timeout before the main loop checked `proc.poll()`.
- **Fix:** All tests that don't specifically test hang behavior now pass `heartbeat=2` to `_make_runner()`.
- **Impact:** Tests complete in ~12 seconds instead of ~70+ seconds. Behavior is identical — heartbeat only affects timing, not logic.
- **Files modified:** tests/benchmarks/test_tblite_runner.py

## Commits

| Hash | Message |
|------|---------|
| 42bed57 | feat(20-02): implement TBLiteRunner with async stream pipe + state monitor |
| a6d5ca0 | chore(20-02): add tests/benchmarks/__init__.py package marker |
| 7b29570 | test(20-02): add 9 unit tests for TBLiteRunner covering all behaviors |

## Known Stubs

None — all public symbols are fully implemented and testable.

## Threat Flags

No new security surface introduced beyond what the plan's threat model covers:
- T-20-05: `_validate_task_filter` whitelist regex implemented and tested
- T-20-06: hang detection (heartbeat × max_hangs → SIGTERM) implemented
- T-20-08: per-line JSONL parse + skip counter implemented
- T-20-09: stderr_buf capped at 1000 lines; result.stderr_tail capped at 20
- T-20-10: `max(1, int(hb_raw))` constructor clamp prevents heartbeat=0 bypass

## Self-Check: PASSED
