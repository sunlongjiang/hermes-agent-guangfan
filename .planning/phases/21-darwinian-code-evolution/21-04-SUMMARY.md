---
phase: 21-darwinian-code-evolution
plan: "04"
subsystem: infra
tags: [openevolve, fitness, pytest, ruff, deterministic-scoring]

requires:
  - phase: 21-02
    provides: "evolution/code/ package skeleton"
  - phase: 21-01
    provides: "[code] extra, ruff dev dep, pre-commit gate, LICENSE"
provides:
  - "CodeFitness dataclass (D-11 + D-16 fields)"
  - "score_candidate(target_path, evolved_path, eval_dir, baseline_size, train_test_ids) -> CodeFitness"
  - "_size_to_component piecewise linear (D-12) soft=1.3, hard=1.5"
  - "_ruff_to_score bucketed (D-13)"
  - "_run_ruff subprocess wrapper (check=False, Pitfall 2-safe)"
  - "to_dict() emitting code_*-prefixed fields"
  - "Lazy sandbox_runner import with RuntimeError on missing"
  - "6 deterministic unit tests"
affects: [21-05-sandbox-runner, 21-06-evolver-adapter, 21-07-cli-orchestrator]

tech-stack:
  added: []
  patterns:
    - "Three-stage deterministic fitness with early-return short-circuits"
    - "Deferred-import + loud RuntimeError for cross-plan dependency"
    - "sys.modules stub injection for unit-testing"
    - "Dataclass.to_dict with code_* prefix"

key-files:
  created:
    - evolution/code/code_fitness.py
    - tests/code/__init__.py
    - tests/code/test_code_fitness.py
  modified: []

key-decisions:
  - "Soft threshold widened to 1.3 (Claude's Discretion permitted by plan); hard 1.5 unchanged"
  - "sandbox_runner imported lazily; missing raises RuntimeError (no silent stub)"
  - "Tests inject fake sandbox_runner via monkeypatch.setitem(sys.modules, ...)"
  - "subprocess.run patched at module-attribute scope; Pitfall 2 verified by returncode=1 path"

patterns-established:
  - "Three-stage fitness with binary hard gates and early-return on stage 1/2 failures"
  - "code_* metric prefix for metrics.json (mirrors benchmark_* / drift_*)"
  - "Loud RuntimeError on cross-plan dependency rather than silent stub"

requirements-completed: [V2-CODE-01]

duration: 11min
completed: 2026-05-20
---

# Phase 21 Plan 04: Code Fitness Function Summary

**Three-stage deterministic fitness (pytest binary hard gate + size piecewise + ruff bucketed) with code_*-prefixed metrics serialization, zero LLM judges (D-14), Pitfall-2-safe ruff subprocess.**

## Performance

- **Duration:** 11 min
- **Tasks:** 2 (both TDD-tagged; executed implementation-first per plan task ordering)
- **Files modified:** 3 created

## Accomplishments

- **CodeFitness dataclass** with full D-11 / D-16 field set: pytest_passed/total, size_baseline/evolved bytes, ruff_violations, pytest_score/size_component/ruff_score, composite, decision, reject_reason, pytest_failures, ruff_findings.
- **score_candidate() public surface** — single entry-point consumed by the openevolve evaluator (Plan 21-06 generates). Three short-circuit stages enforce hard gates; sandbox_runner integration deferred but loudly required via RuntimeError.
- **_size_to_component()** D-12 piecewise linear with soft=1.3 (widened from default 1.2) and hard=1.5 (unchanged). Parametrized for future tuning.
- **_ruff_to_score()** D-13 buckets (0->1.0, 1-2->0.7, 3-5->0.4, 6-10->0.1, >10->0.0).
- **_run_ruff()** subprocess wrapper — check=False (Pitfall 2), 10s timeout, JSON parse with graceful fallback, returncode=2 (ruff internal error) maps to empty findings.
- **to_dict()** emits 14 code_*-prefixed fields including derived code_size_ratio and openevolve-consumed code_composite_fitness.
- **6 deterministic unit tests** covering all three scoring stages × pass/fail/partial. Total runtime 0.04s; CI-safe without openevolve installed.

## Task Commits

1. **Task 1: create evolution/code/code_fitness.py** — `0145b34` (feat)
2. **Task 2: create tests/code/test_code_fitness.py (6 unit tests)** — `7c9076a` (test)

Plan metadata commit (this SUMMARY.md) follows via orchestrator-driven rescue commit.

## Files Created/Modified

- `evolution/code/code_fitness.py` — 352 lines. CodeFitness dataclass, score_candidate, _size_to_component, _ruff_to_score, _run_ruff. Zero LLM imports, zero openevolve imports, zero check=True. Lazy sandbox_runner import.
- `tests/code/__init__.py` — empty package marker
- `tests/code/test_code_fitness.py` — 262 lines, 6 unit tests + 3 helpers

## Decisions Made

- Soft threshold widened to 1.3 (plan-permitted Claude's Discretion). Baseline 1784 bytes / 44 lines makes ×1.2 = 53 lines untenable for legitimate refactors; ×1.3 = 57 lines preserves penalty curve.
- Loud failure for missing sandbox_runner — RuntimeError rather than silent None.
- Test mocking via sys.modules stub rather than patching code_fitness internals.
- Ruff returncode=2 → (0, []) → ruff_score=1.0 (candidate-favorable; documented in docstring).
- size_ratio added as explicit code_size_ratio derived field in to_dict().

## Deviations from Plan

None — plan executed exactly as written. Soft threshold 1.3 widening was explicitly permitted under Claude's Discretion.

## Issues Encountered

- **Sandbox write lockout after task 2 commit:** Claude Code session denied SUMMARY.md Write. Orchestrator rescue commit lands SUMMARY.md via main-session Write tool. All code/tests fully committed by agent.

## Verification Output

- pytest tests/code/test_code_fitness.py: 6 passed in 0.04s
- grep dspy/openai/LLMJudge in code_fitness.py: 0 (D-14)
- grep check=True in code_fitness.py: 0 (Pitfall 2)
- grep ^import openevolve / ^from openevolve in code_fitness.py: 0 (D-03)
- grep code_composite_fitness in code_fitness.py: 1
- pytest tests/code/: 6 passed (no regression)

## Self-Check: PASSED

- evolution/code/code_fitness.py exists (352 lines ≥ 120 min): FOUND
- tests/code/__init__.py exists: FOUND
- tests/code/test_code_fitness.py exists (262 lines ≥ 100 min): FOUND
- Commit 0145b34 (feat) + 7c9076a (test) in git log
- All 5 plan success criteria PASS

## Next Phase Readiness

- Plan 21-05 (sandbox_runner.py): contract fixed — `run_pytest_in_sandbox(candidate_path, eval_dir, train_test_ids=None) -> tuple[int, int, list[dict]]`
- Plan 21-06 (code_evolver_adapter.py): generates openevolve evaluator .py; evaluator imports `from evolution.code.code_fitness import score_candidate`; returns `{"combined_score": fitness.composite, **fitness.to_dict()}`.

---
*Phase: 21-darwinian-code-evolution*
*Completed: 2026-05-20*
