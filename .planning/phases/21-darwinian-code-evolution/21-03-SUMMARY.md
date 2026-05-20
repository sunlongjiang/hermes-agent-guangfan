---
phase: 21-darwinian-code-evolution
plan: "03"
subsystem: infra
tags: [openevolve, ast, hermes-agent, code-target, stratified-split]

requires:
  - phase: 21-02
    provides: "evolution/code/ package skeleton, tests/code/ test package"
  - phase: 21-01
    provides: "MIT LICENSE, [code] extra, pre-commit gate"
provides:
  - "CodeTarget dataclass (component_path, test_file_path, baseline_size_bytes, original_source, schema_version, hermes_agent_commit)"
  - "find_target(component_path) -> CodeTarget: HERMES_AGENT_REPO resolution + T-21-RECURSE blacklist + best-effort git SHA"
  - "find_target_tests(component_path, test_root) -> list[str]: ast.parse static scan of test files"
  - "stratify_tests(test_ids, holdout_ratio, seed) -> tuple[list, list]: deterministic 4-bucket split"
affects: [21-04-code-fitness, 21-06-evolver-adapter, 21-07-cli-orchestrator]

tech-stack:
  added: []
  patterns:
    - "AST-based test discovery without import side effects"
    - "Stratified train/holdout split with deterministic seed=42"
    - "Path-prefix blacklist for self-evolution prevention"

key-files:
  created:
    - evolution/code/code_target_loader.py
    - tests/code/__init__.py
    - tests/code/test_code_target_loader.py
  modified: []

key-decisions:
  - "AST static parse (not import) for test discovery — zero side effects, no hermes dependencies"
  - "Path blacklist `_FORBIDDEN_PATH_PREFIXES` denies evolution/ component_path (T-21-RECURSE)"
  - "Deterministic seed=42 + 4-bucket stratify + round-robin overflow"

patterns-established:
  - "AST parser walks Module → ClassDef → FunctionDef, captures top-level and class-nested test_* functions"
  - "Best-effort hermes-agent commit SHA via subprocess git rev-parse, fail gracefully on missing"

requirements-completed: [V2-CODE-01]

duration: 22min
completed: 2026-05-20
---

# Phase 21 Plan 03: Code Target Loader Summary

**CodeTarget dataclass + AST-based test discovery + deterministic stratified train/holdout split — the data layer for openevolve evaluation, with T-21-RECURSE blacklist enforced at find_target boundary.**

## Performance

- **Duration:** 22 min
- **Tasks:** 2 (1 implementation + 1 test set)
- **Files modified:** 3 created

## Accomplishments

- **CodeTarget dataclass** with full field set + to_dict() serialization for metrics.json embedding
- **find_target()** resolves HERMES_AGENT_REPO env var, fallback to ~/.hermes/hermes-agent and ../hermes-agent siblings; rejects evolution/ paths with `ValueError("path is in evolution/ — self-evolution forbidden")`
- **find_target_tests()** AST parses test file, walks `ast.Module.body` for `ast.FunctionDef` and `ast.ClassDef` nested defs, returns `["test_module::TestClass::test_name", ...]`
- **stratify_tests()** seed=42 deterministic shuffle, 4 buckets (assert/raises/property/integration heuristics), holdout_ratio sliced per-bucket with round-robin remainder
- **4 unit tests** covering happy path + integration + stratify quotas + T-21-RECURSE guard

## Task Commits

1. **Task 1: create evolution/code/code_target_loader.py** — `47a30b3` (feat)
2. **Task 2: create tests/code/test_code_target_loader.py** — `d92fcb1` (test, committed by orchestrator after agent sandbox lockout)

## Files Created/Modified

- `evolution/code/code_target_loader.py` — 402 lines. CodeTarget, find_target, find_target_tests, stratify_tests, _FORBIDDEN_PATH_PREFIXES. Zero openevolve imports (D-03).
- `tests/code/__init__.py` — 0 bytes pytest marker
- `tests/code/test_code_target_loader.py` — 4 unit tests

## Decisions Made

- AST static parse over importlib import — avoids importing hermes-agent code (and its DSPy/openai etc. side effects)
- seed=42 for stratify_tests — matches Phase 4/5 dataset_builder convention
- T-21-RECURSE enforced at find_target() boundary, not deferred to consumer

## Deviations from Plan

None.

## Issues Encountered

- **Sandbox write lockout after task 1 commit:** Claude Code session denied all subsequent Bash/Write/Edit calls. Task 2 files written to disk via early Write call (before lockout) but `git add`/`git commit` denied. Orchestrator rescue commit landed `d92fcb1`.

## Self-Check: PASSED

- evolution/code/code_target_loader.py exists (402 lines)
- tests/code/test_code_target_loader.py exists
- Commits 47a30b3 + d92fcb1 in git log
- All 4 success criteria PASS (import smoke, raise ValueError ≥2, ast.parse ≥1, openevolve grep = 0)
- pytest tests/code/test_code_target_loader.py: 4 passed in 0.09s

---
*Phase: 21-darwinian-code-evolution*
*Completed: 2026-05-20*
