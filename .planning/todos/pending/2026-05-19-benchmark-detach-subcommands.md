---
opened: 2026-05-19
severity: MEDIUM
phase_match_hint: 22
related_files:
  - evolution/prompts/evolve_prompt_sections.py
  - evolution/benchmarks/benchmark_gate.py
  - evolution/benchmarks/tblite_runner.py
---

# Phase 20 deferred: `--detach` + `--check-benchmark / --restore / --confirm-rollback` subcommands

Phase 20 / Plan 06 (2026-05-19) shipped the synchronous `--wait` path of
the TBLite benchmark gate but DEFERRED two pieces to a later phase (likely
Phase 22 — Continuous Evolution Loop):

1. **`--detach` background dispatch.** Today `--detach` exits 1 with a
   Phase-22 message. The real implementation needs a `subprocess.Popen`
   detached run + `output/prompts/<ts>/.benchmark_running.pid` lock file
   + Rich Live progress polling. CONTEXT §D-12 + §Discretion 7 describe
   the target shape.

2. **`--check-benchmark <ts>` / `--restore <ts>` / `--confirm-rollback <ts>` subcommands.**
   Companion to `--detach`. Lets the user query a backgrounded run's
   gate decision and roll back if `tblite_full_report.json` (Phase 22
   async full verify) finds regressions. CONTEXT §D-07 + §D-08 + §Specifics
   define the lock file + history schema.

**Why deferred:** These features cross a process boundary and need
Phase-21-era infrastructure (a daemon mode for the evolution CLI, or a
cron-like scheduler). Plan 06's scope was the synchronous integration
only; adding the async story would have pushed Plan 06 past its 2-3-task
budget.

**Acceptance:** When Phase 22 picks this up, delete this file in the same
commit that introduces the `--detach` background-process path. Verify by
running `python -m evolution.prompts.evolve_prompt_sections --benchmark=tblite --detach`
and confirming it returns a `benchmark_run_id` rather than exiting 1.
