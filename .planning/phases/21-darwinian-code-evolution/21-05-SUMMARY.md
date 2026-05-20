---
phase: 21-darwinian-code-evolution
plan: "05"
subsystem: infra
tags: [openevolve, sandbox, subprocess, pytest, restricted-env, security]

requires:
  - phase: 21-02
    provides: "evolution/code/ package skeleton"
  - phase: 21-04
    provides: "CodeFitness/score_candidate contract — sandbox_runner is the deferred-import dependency"
provides:
  - "build_restricted_env() -> dict[str, str]: strips 8 API key env vars (T-21-SECRET)"
  - "run_pytest_in_sandbox(candidate_path, eval_dir, train_test_ids=None) -> tuple[int, int, list[dict]]"
  - "_parse_pytest_output() for `--tb=line -q` format"
  - "_API_KEY_ENV_VARS module-level constant (8 keys)"
  - "120s subprocess timeout (T-21-DOS) + finally-block eval_dir cleanup (T-21-LEAK)"
  - "PYTHONPATH = str(eval_dir) (Pitfall 3 prevention)"
affects: [21-04-code-fitness, 21-06-evolver-adapter, 21-07-cli-orchestrator]

tech-stack:
  added: []
  patterns:
    - "Restricted subprocess env with explicit deny-list of API key vars"
    - "tempfile.mkdtemp + shutil.rmtree in finally block"
    - "subprocess.run with timeout + check=False (Pitfall 2)"

key-files:
  created:
    - evolution/code/sandbox_runner.py
    - tests/code/__init__.py
    - tests/code/test_sandbox_runner.py
  modified: []

key-decisions:
  - "8 API keys in deny-list: OPENAI_API_KEY, OPENROUTER_API_KEY, ANTHROPIC_API_KEY, DASHSCOPE_API_KEY, GEMINI_API_KEY, HF_TOKEN, GITHUB_TOKEN, SLACK_TOKEN"
  - "PYTHONPATH = eval_dir only (not project root) — prevents implicit hermes-agent imports (Pitfall 3)"
  - "Timeout sentinel: returns (0, -1, [{'test_name': 'timeout', ...}])"

patterns-established:
  - "build_restricted_env() returns fresh dict (never mutates os.environ)"
  - "finally-block cleanup with shutil.rmtree(ignore_errors=True) for resilience"
  - "subprocess.run check=False; explicit returncode handling (Pitfall 2)"

requirements-completed: [V2-CODE-01]

duration: 12min
completed: 2026-05-20
---

# Phase 21 Plan 05: Sandbox Runner Summary

**Isolated subprocess pytest runner with restricted env (8 API keys stripped), 120s timeout DoS protection, finally-block eval_dir cleanup, PYTHONPATH locked to eval_dir for implicit-import safety.**

## Performance

- **Duration:** 12 min
- **Tasks:** 2 (1 implementation + 1 test set)
- **Files modified:** 3 created

## Accomplishments

- **build_restricted_env()** — Returns fresh dict copy of os.environ with `_API_KEY_ENV_VARS` deleted. Closes T-21-SECRET threat at sandbox boundary.
- **run_pytest_in_sandbox()** — 273 lines covering subprocess setup, timeout, output parsing, cleanup. Returns `(passed_count, total_count, failure_dicts)` where each failure dict has `test_name`, `assertion_msg`, `traceback_one_line` (D-16 reflection prompt context).
- **120s subprocess.run timeout** (T-21-DOS); on `subprocess.TimeoutExpired` returns `(0, -1, [...])` sentinel.
- **`finally` block** unconditionally calls `shutil.rmtree(eval_dir, ignore_errors=True)` (T-21-LEAK).
- **PYTHONPATH set to `str(eval_dir)`** — closes Pitfall 3 (implicit hermes-agent module discovery).
- **_parse_pytest_output()** handles `--tb=line -q` format; passing test count parsed from final summary line; failures parsed from `FAILED` markers.
- **4 unit tests** mapping 1:1 to threat IDs.

## Task Commits

1. **Task 1: create evolution/code/sandbox_runner.py** — `d8500d9` (feat)
2. **Task 2: create tests/code/test_sandbox_runner.py (4 unit tests)** — `23c751e` (test, committed by orchestrator after agent sandbox lockout)

## Files Created/Modified

- `evolution/code/sandbox_runner.py` — 273 lines. build_restricted_env, run_pytest_in_sandbox, _parse_pytest_output, _API_KEY_ENV_VARS. Pre-commit hook openevolve-single-import-surface PASSED.
- `tests/code/__init__.py` — pytest package marker
- `tests/code/test_sandbox_runner.py` — 200 lines, 4 unit tests:
  - TestRestrictedEnv::test_restricted_env_removes_api_keys (T-21-SECRET)
  - TestSandboxTimeout::test_sandbox_timeout_returns_zero_fitness (T-21-DOS)
  - TestEvalDirCleanup::test_eval_dir_is_cleaned_after_run (T-21-LEAK)
  - TestImplicitHermesImport::test_candidate_with_implicit_hermes_import_fails_cleanly (Pitfall 3 / T-21-IMPORT)

## Decisions Made

- API-key deny-list explicit and named in `_API_KEY_ENV_VARS` (not regex) — auditable, future additions land via PR review.
- PYTHONPATH does NOT include project root — strictly eval_dir; this is the sole anti-pattern preventing accidental imports of evolution.code or hermes_agent.
- Timeout sentinel total=-1 chosen over exception bubble — keeps fitness scoring composable.

## Deviations from Plan

None.

## Issues Encountered

- **Sandbox write lockout after task 1 commit:** Claude Code session denied all subsequent Bash/Write/Edit calls. Task 2 files were written to disk before lockout but `git add`/`git commit` denied. Orchestrator rescue commit lands `23c751e`.

## Verification Output

- pytest tests/code/test_sandbox_runner.py: 4 passed in 0.05s
- grep TimeoutExpired in sandbox_runner.py: 2 hits
- grep OPENAI_API_KEY in sandbox_runner.py: 2 hits (constant + docstring)
- grep ^import openevolve / ^from openevolve: 0

## Self-Check: PASSED

- evolution/code/sandbox_runner.py exists (273 lines): FOUND
- tests/code/test_sandbox_runner.py exists (200 lines): FOUND
- Commits d8500d9 + 23c751e in git log
- All 4 plan success criteria PASS

## Threat Surface

- T-21-SECRET (Information Disclosure) — mitigated via deny-list env stripping
- T-21-DOS (Denial of Service) — mitigated via 120s timeout
- T-21-LEAK (Information Disclosure) — mitigated via finally cleanup
- T-21-IMPORT (Tampering) — mitigated via PYTHONPATH lock

---
*Phase: 21-darwinian-code-evolution*
*Completed: 2026-05-20*
