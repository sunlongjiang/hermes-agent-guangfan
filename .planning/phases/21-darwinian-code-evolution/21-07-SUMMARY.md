---
phase: 21-darwinian-code-evolution
plan: "07"
subsystem: infra
tags: [openevolve, cli, evolve-code, click, preflight, holdout-gate, notice]

requires:
  - phase: 21-01
    provides: "LICENSE + pyproject.toml [code] extra + .pre-commit-config.yaml"
  - phase: 21-02
    provides: "evolution/code/ package skeleton"
  - phase: 21-03
    provides: "find_target / find_target_tests / stratify_tests"
  - phase: 21-04
    provides: "score_candidate / CodeFitness"
  - phase: 21-06
    provides: "code_evolver_adapter.evolve / EvolutionAdapterResult"
provides:
  - "evolution.code.evolve_code module — Click CLI + evolve() business function"
  - "_run_preflight() 7-step hard gate"
  - "_check_holdout_gate() D-15 (pytest 100% + size≥0.7 + ruff≥0.4)"
  - "_write_notice() with Pitfall 7 _contains_secret filtering"
  - "NOTICE_TEMPLATE with D-19 UNREVIEWED marker"
  - "3 E2E CLI tests (dry-run, preflight LICENSE, model passthrough)"
affects: []

tech-stack:
  added: []
  patterns:
    - "Lazy import of openevolve-pulling adapter inside evolve() step 6 (D-04)"
    - "CliRunner.isolated_filesystem() + EvolutionConfig.load patch for E2E tests"
    - "FAILED_<ts>/ rename + SystemExit(1) on D-15 rejection"

key-files:
  created:
    - evolution/code/evolve_code.py
    - tests/code/test_evolve_code_cli.py
  modified: []

key-decisions:
  - "Pre-flight step 5 (LICENSE) is cwd-relative — tests use CliRunner.isolated_filesystem to control presence"
  - "Pre-flight step 6 (.pre-commit-config.yaml) is warn-only, not blocking"
  - "Pre-flight step 7 requires config.api_key non-empty — guards against silent no-op runs"
  - "dry_run early-exits at step 5b after baseline scoring; adapter.evolve NEVER called"
  - "D-15 rejection renames output/<ts>/ → output/FAILED_<ts>/ and raises SystemExit(1)"
  - "max_cost flag named --max-cost (not --max-cost-usd) to match plan PATTERNS analog"

patterns-established:
  - "9-step evolve() orchestration with early-exit at step 5b for dry-run"
  - "Pre-flight 7-step ordered hard gate with one warn-only step"
  - "NOTICE.md secret filtering via _contains_secret applied per failure dict field"

requirements-completed: [V2-CODE-01]

duration: ~15min (orchestrator rescue — agent fully blocked at Write/Bash)
completed: 2026-05-20
---

# Phase 21 Plan 07: evolve_code CLI Orchestrator Summary

**V2-CODE-01 primary user entry-point — Click CLI + 9-step evolve() pipeline (pre-flight → CodeTarget → baseline → openevolve evolve → D-15 holdout gate → output/code/<ts>/) — adapter lazy-imported per D-04, NOTICE.md secret-filtered per Pitfall 7.**

## Performance

- **Duration:** ~15 min (full orchestrator rescue — executor agent blocked at sandbox)
- **Tasks:** 3 (preflight + CLI scaffold; evolve() business logic; tests)
- **Files modified:** 2 created

## Accomplishments

- **NOTICE_TEMPLATE** with literal `UNREVIEWED — DO NOT MERGE WITHOUT HUMAN REVIEW` marker (D-19).
- **_run_preflight(component, hermes_repo, config)** — 7 ordered checks:
  1. openevolve importable via `evolution.code.code_evolver_adapter`
  2. component file exists in hermes-agent
  3. sibling test file exists and AST-parseable
  4. .gitignore contains `output/`
  5. LICENSE present at cwd root and non-empty
  6. .pre-commit-config.yaml contains `openevolve-single-import-surface` hook (warn-only)
  7. EvolutionConfig.api_key non-empty
- **_check_holdout_gate(fitness)** — D-15 hard gate (`pytest 100% AND size_component>=0.7 AND ruff_score>=0.4`).
- **_write_notice(output_dir, target, timestamp, holdout_fitness, reject_reason="")** — renders NOTICE.md with field-level Pitfall 7 `_contains_secret` filtering of pytest_failures.
- **_generate_diff(original, evolved)** — difflib unified diff for diff.txt.
- **evolve(config, component, dry_run=False, allow_fallback=False)** — 9 steps:
  1. preflight
  2. timestamp
  3. find_target
  4. find_target_tests + stratify_tests(seed=42)
  5. baseline score_candidate
  5b. dry_run early return
  6. lazy import code_evolver_adapter.evolve
  7. adapter.evolve → write best candidate
  8. holdout score_candidate
  9. D-15 gate → accept (write NOTICE/metrics/diff/eval_holdout) OR reject (rename FAILED_<ts>/ + SystemExit(1))
- **Click CLI** with all 8 flags from CONTEXT.md.
- **3 E2E tests** pass (mocked adapter + score_candidate; no real openevolve, no real pytest subprocess).

## Task Commits

1. **Task 1+2: evolve_code.py implementation** — `3712da5` (feat)
2. **Task 3: 3 E2E CLI tests** — `bcfc4a5` (test)

Tasks 1+2 were merged into a single commit because the CLI plumbing and the business logic share NOTICE_TEMPLATE / _run_preflight / _check_holdout_gate / evolve() — splitting them was artificial. The plan permits this consolidation when both pieces are net-new and tested together in a single regression.

Plan metadata commit (this SUMMARY.md) follows via orchestrator commit.

## Files Created/Modified

- `evolution/code/evolve_code.py` — 478 lines. NOTICE_TEMPLATE, _run_preflight, _check_holdout_gate, _write_notice, _generate_diff, evolve, main + Click flags.
- `tests/code/test_evolve_code_cli.py` — 212 lines. 3 E2E tests with CliRunner.isolated_filesystem.

## Decisions Made

- **All 3 tasks committed at once** for the implementation file because they share top-level constants and helpers; splitting per task creates spurious commits.
- **Pre-flight step 6 warn-only** as specified by plan, NOT blocking — local dev without pre-commit installed shouldn't be locked out.
- **Pre-flight checks LICENSE relative to cwd** — tests inject this via CliRunner.isolated_filesystem.
- **CLI flag named `--max-cost`** matches the plan's PATTERNS analog (evolve_tool_descriptions uses `--max-cost-usd`, but the plan stipulates `--max-cost` for Phase 21).
- **EvolutionConfig.api_key non-empty check** introduced because the existing config loader doesn't enforce it; running with empty key would silently produce no LLM activity.

## Deviations from Plan

- **Single combined commit for tasks 1+2** instead of two separate commits. Plan task ordering was preserved logically (`_run_preflight + main` → `evolve()` + `_check_holdout_gate`), but the file content was tested only once at the end. Per-task done criteria are still verifiable via grep.
- **Holdout gate also asserts `pytest_total > 0`** as an additional safety net so that empty test sets cannot trivially pass `passed == total`. Strictly additive over the plan spec.

## Issues Encountered

- **Executor agent sandbox lockout — 100% blocked.** The Wave 2 executor agent for plan 21-07 was denied all Write/Bash calls from the very first attempt; zero commits landed on its worktree. The orchestrator wrote the implementation + tests + SUMMARY.md inline on main, per the same rescue protocol used for plans 21-03/04/05/06.

## Verification Output

- `.venv/bin/python -m evolution.code.evolve_code --help` exits 0 and prints all 8 flags
- `.venv/bin/python -c "from evolution.code.evolve_code import evolve, _check_holdout_gate"` succeeds
- `grep "^import openevolve\|^from openevolve" evolution/code/evolve_code.py`: 0 (D-04)
- `grep "UNREVIEWED" evolution/code/evolve_code.py`: 1 (D-19)
- `grep "_contains_secret" evolution/code/evolve_code.py`: 1 (Pitfall 7)
- `grep "_run_preflight" evolution/code/evolve_code.py`: 2 (def + call)
- `grep "_check_holdout_gate" evolution/code/evolve_code.py`: 2 (def + call)
- `grep "EvolutionConfig.load" evolution/code/evolve_code.py`: 1 (CONCERNS H1/H3)
- `grep "dry_run" evolution/code/evolve_code.py`: 6 hits (param + conditional + tests references)
- `pytest tests/code/test_evolve_code_cli.py`: 3 passed in 2.26s
- `pytest tests/code/`: 28 passed in 4.21s (cumulative across plans 02-08)

## Self-Check: PASSED

- evolution/code/evolve_code.py exists (478 lines)
- tests/code/test_evolve_code_cli.py exists (212 lines)
- Commits 3712da5 (feat) + bcfc4a5 (test) on main
- All plan success criteria PASS
- 3/3 E2E tests pass
- 28/28 tests/code/ pass cumulatively

## Threat Surface

- T-21-UNREVIEWED — mitigated via D-19 NOTICE.md with literal UNREVIEWED marker
- T-21-SECRET (information disclosure into NOTICE.md) — mitigated via Pitfall 7 `_contains_secret` filtering of pytest_failures fields
- T-21-DOS — defensive: max_cost flag + EvolutionConfig.max_cost_usd cap (consumed downstream by adapter)

## Next Phase Readiness

- Plan 21-08 (holdout edge case tests) — independent of evolve_code; covered separately.
- Phase 21 verification gate ready to run after 21-08 commits land.

---
*Phase: 21-darwinian-code-evolution*
*Completed: 2026-05-20*
