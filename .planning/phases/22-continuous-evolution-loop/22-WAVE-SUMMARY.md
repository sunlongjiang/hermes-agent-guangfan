# Phase 22 Wave Summary

Generated 2026-05-21 during planning.

## Final wave structure (after SDK validation)

| Plan | Wave | depends_on | files_modified |
|------|------|-----------|----------------|
| 22-01 deploy_mode gate (D-11) | 1 | [] | evolution/core/config.py + tool_loader.py + prompt_loader.py + tests/test_deploy_mode_gate.py |
| 22-02 loop yaml schema (D-06/D-08) | 2 | [22-01] | evolution/core/config.py + evolution.yaml + tests/test_loop_config.py |
| 22-03 run_loop.py (D-06/D-07/D-08/D-10) | 3 | [22-02] | evolution/loop/__init__.py + run_loop.py |
| 22-04 pr_creator.py (D-03/D-04/D-05/D-09) | 1 | [] | evolution/loop/pr_creator.py |
| 22-05 GH Actions yaml (D-01/D-02/D-11) | 4 | [22-01, 22-03, 22-04] | .github/workflows/evolution-loop.yml |
| 22-06 tests/loop/ (Plan 03 + Plan 04 coverage) | 4 | [22-03, 22-04] | tests/loop/__init__.py + test_run_loop.py + test_pr_creator.py |
| 22-07 branch protection runbook (D-09) | 1 | [] | docs/setup-hermes-agent-branch-protection.md |

## Execution waves

**Wave 1** (parallel — 22-01, 22-04, 22-07): three independent plans, can run in any order or fully parallel.
- 22-01 touches evolution/core/config.py (file lock — blocks 22-02)
- 22-04 touches evolution/loop/pr_creator.py (independent file)
- 22-07 touches docs/ (independent file)

**Wave 2** (22-02): blocked on 22-01 due to file lock (both modify evolution/core/config.py).

**Wave 3** (22-03): blocked on 22-02 because run_loop.py imports `LOOP_CLI_NAMES` from config.

**Wave 4** (22-05, 22-06): parallel internally; both depend on Wave 3 (run_loop.py) and 22-04 (pr_creator.py).
- 22-05 GH Actions workflow yaml — invokes run_loop, needs pr_creator on disk to verify the subprocess argv.
- 22-06 unit tests — imports both modules to test.

## D-coverage map

| Decision | Addressed by |
|----------|--------------|
| D-01 (GH Actions scheduler) | 22-05 |
| D-02 (cron + workflow_dispatch) | 22-05 |
| D-03 (PR → hermes-agent) | 22-04 |
| D-04 (gh CLI subprocess) | 22-04 |
| D-05 (branch naming) | 22-04 |
| D-06 (all 6 CLIs in loop) | 22-02, 22-03 |
| D-07 (serial + non-blocking) | 22-03 |
| D-08 (per-CLI max-cost) | 22-02, 22-03 |
| D-09 (branch protection + CODEOWNERS) | 22-04 (NOTICE body), 22-07 (runbook) |
| D-10 (holdout gate reuse, no loop-level gate) | 22-03 (dir-name classification + metrics.json fallback) |
| D-11 (deploy_mode gate) | 22-01, 22-05 (env var) |

All 11 decisions covered.
