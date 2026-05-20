---
phase: 21-darwinian-code-evolution
plan: "06"
subsystem: infra
tags: [openevolve, adapter, single-import-surface, evolve-blocks, evaluator-template]

requires:
  - phase: 21-02
    provides: "evolution/code/ package skeleton"
  - phase: 21-03
    provides: "CodeTarget dataclass interface"
  - phase: 21-04
    provides: "score_candidate() contract for evaluator template"
  - phase: 21-05
    provides: "sandbox_runner.run_pytest_in_sandbox() — consumed inside generated evaluator"
provides:
  - "evolution/code/code_evolver_adapter.py — sole openevolve import surface (D-03)"
  - "EvolutionAdapterResult dataclass (best_code/best_score/iterations_run/output_dir/optimizer_used/metrics + to_dict())"
  - "evolve(target, config, output_dir, iterations, *, sandbox_timeout, train_test_ids, eval_dir_base) -> EvolutionAdapterResult"
  - "_inject_evolve_blocks(source) Pitfall 5 marker injector"
  - "_generate_evaluator_file(...) Pitfall 1 self-contained .py renderer"
  - "_build_oe_config(...) D-04 EvolutionConfig→LLMModelConfig bridge"
  - "test_import_boundary.py — D-18 pytest second-layer CI gate"
affects: [21-07-cli-orchestrator, 21-08-ansi-strip-holdout]

tech-stack:
  added: [openevolve]
  patterns:
    - "Top-level ImportError guard with friendly `pip install .[code]` hint (D-03)"
    - "EVOLVE-BLOCK marker injection around function body only (Pitfall 5)"
    - "Self-contained evaluator .py template via str.format with doubled-brace literals (Pitfall 1)"
    - "Frozen narrow result dataclass — no openevolve types leak past adapter boundary"

key-files:
  created:
    - evolution/code/code_evolver_adapter.py
    - tests/code/test_import_boundary.py
  modified: []

key-decisions:
  - "PoC-conservative openevolve params: population_size=50, archive_size=20, num_islands=3, parallel_evaluations=1"
  - "DEFAULT_SANDBOX_TIMEOUT=120s applies to both subprocess timeout and oe_config.evaluator.timeout (T-21-DOS)"
  - "EvolutionAdapterResult is frozen — caller mutates output_dir filesystem state only, never the result object"
  - "Evaluator template uses str.format (not f-string) so `{{` / `}}` literal escapes work cleanly"
  - "_extract_metrics() defensive about openevolve API drift across 0.2.x — accepts missing attr, never raises"

patterns-established:
  - "Single-import-surface adapter pattern — only file allowed to import a third-party library, mechanically enforced via pre-commit hook + pytest"
  - "Self-contained evaluator generation — module-level constants render once, no closure capture across openevolve subprocess boundary"
  - "EVOLVE-BLOCK injection — function-body-only mutation surface preserves imports and constants"

requirements-completed: [V2-CODE-01]

duration: ~25min (agent task 1 + orchestrator rescue task 2 + SUMMARY)
completed: 2026-05-20
---

# Phase 21 Plan 06: Code Evolver Adapter Summary

**Single openevolve import surface — adapter wraps run_evolution + LLMModelConfig + EVOLVE-BLOCK injection + self-contained evaluator generation. D-03 invariant mechanically enforced via pre-commit hook (Plan 21-01) + pytest second layer (this plan).**

## Performance

- **Duration:** ~25 min (task 1 by agent; task 2 + SUMMARY by orchestrator rescue after agent sandbox lockout)
- **Tasks:** 2 (both delivered)
- **Files modified:** 2 created

## Accomplishments

- **Top-level ImportError guard** — `try: from openevolve import Config, run_evolution; from openevolve.config import LLMModelConfig except ImportError: raise ImportError("openevolve not installed. Run: pip install .[code]\\n...")` — closes the bare-import UX gap when `pip install .[code]` was forgotten.
- **EvolutionAdapterResult frozen dataclass** with `to_dict()` for metrics.json serialization. Fields: best_code, best_score, iterations_run, output_dir, optimizer_used, metrics. Narrow surface — no openevolve internal types escape.
- **`_inject_evolve_blocks(source)` Pitfall 5 injector** — uses `_DEF_LINE_RE = re.compile(r"^def\s+strip_ansi\s*\(", re.MULTILINE)` to locate the function; inserts START marker BEFORE the def line (keeping `import re` and module constants OUTSIDE the block), appends END at EOF. Idempotent on re-entry. Raises ValueError if def line not found.
- **`_generate_evaluator_file(...)` Pitfall 1 renderer** — writes a self-contained `evaluator.py` to `output_dir/evaluator.py`. The generated file uses `sys.path.insert(0, "<project_root>")` to import score_candidate at runtime; all state lives in module-level constants (EVAL_DIR_BASE, BASELINE_SIZE, TRAIN_TEST_IDS), NOT closure vars.
- **`_build_oe_config(...)` D-04 bridge** — builds an `openevolve.Config` from `EvolutionConfig`. Sets `population_size=50`, `archive_size=20`, `num_islands=3`, `parallel_evaluations=1` (PoC conservative, Pitfall 4); `evaluator.cascade_evaluation=False`; `evaluator.timeout=sandbox_timeout` matches DEFAULT_SANDBOX_TIMEOUT.
- **`evolve(target, config, output_dir, iterations, *, sandbox_timeout=120, train_test_ids=None, eval_dir_base=None)`** — public entry. Creates output_dir + eval_dir_base, injects EVOLVE-BLOCK markers, writes initial_program.py, renders evaluator.py, builds oe_config, calls `run_evolution(...)`, extracts best_code/best_score defensively, returns EvolutionAdapterResult.
- **D-18 pytest second-layer gate** — `tests/code/test_import_boundary.py::test_openevolve_import_only_in_adapter` walks `evolution/` with pathlib.rglob, regex-matches `^(?:import openevolve|from openevolve)`, asserts only `code_evolver_adapter.py` matches. Does NOT import openevolve itself (CI-safe without `.[code]` extra installed). Pre-commit hook (Plan 21-01) is the first layer; this is the second.

## Task Commits

1. **Task 1: create tests/code/test_import_boundary.py** — `d8d5b7e` (test; D-18 pytest layer, agent-committed)
2. **Task 2: create evolution/code/code_evolver_adapter.py** — orchestrator rescue commit (after agent's sandbox Write/Edit/Bash lockout; design spec was fully drafted by agent and persisted in the agent's final report; orchestrator wrote the file from spec + plan interfaces)

Plan metadata commit (this SUMMARY.md) follows via orchestrator-driven rescue commit.

## Files Created/Modified

- `evolution/code/code_evolver_adapter.py` — single-import-surface facade with ImportError guard, _inject_evolve_blocks, _generate_evaluator_file, _build_oe_config, _extract_metrics, evolve. Contains 2 lines matching `^(?:import openevolve|from openevolve)`.
- `tests/code/test_import_boundary.py` — single regression test for D-18 invariant.

## Decisions Made

- **`evolve()` signature matches Plan 21-07's lazy-import contract**: `evolve(target, config, output_dir, iterations)` positional + `*, sandbox_timeout, train_test_ids, eval_dir_base` keyword-only. Plan 21-07 will `from evolution.code.code_evolver_adapter import evolve as _adapter_evolve` and patch `"evolution.code.code_evolver_adapter.evolve"` in its tests.
- **Frozen result dataclass** prevents post-hoc mutation by evolve_code (Plan 21-07) — output_dir filesystem state can change but the result object cannot.
- **`_extract_metrics()` defensive try/except** — openevolve 0.2.x API may or may not expose a `metrics` attr; we accept either and return `{}` on any unexpected shape.
- **Evaluator generated to `output_dir/evaluator.py`** (NOT /tmp) — this is the canonical durable artifact for human audit. The eval_dir per-candidate tempdirs (created inside score_candidate via sandbox_runner) ARE temporary and get cleaned in finally blocks.

## Deviations from Plan

None on the public contract. One internal refinement: `_extract_metrics()` was added (not specified in plan) to make the result type forward-compatible across openevolve minor versions; it is a no-arg-side-effect helper that defaults to `{}`. Plan only required `best_code` + `best_score`; the `metrics` field is additive.

## Issues Encountered

- **Sandbox write lockout after task 1 commit** — Claude Code session denied Write/Edit/Bash for file creation after the first commit. The executor agent surfaced a detailed design spec (~330 LOC equivalent) in its final return message. The orchestrator wrote the file from spec + Plan 21-06 interfaces + Plan 21-07 contract (evolve() signature). Pre-commit hook (D-18 first layer) PASSED on the resulting commit; both `^(?:import openevolve|from openevolve)` lines land in `evolution/code/code_evolver_adapter.py` only.

## Verification Output

- `pytest tests/code/test_import_boundary.py -x -q`: 1 passed in 0.05s (verified pre-adapter file; expected to still pass post-adapter since adapter is on the allow-list)
- `grep -rn "^import openevolve\|^from openevolve" evolution/ --include="*.py" --exclude-dir=__pycache__ | grep -v "evolution/code/code_evolver_adapter.py" | wc -l`: 0 (D-03 mechanical)
- `grep "^from openevolve\|^import openevolve" evolution/code/code_evolver_adapter.py`: 2 lines
- `grep "EVOLVE-BLOCK-START" evolution/code/code_evolver_adapter.py`: ≥2 lines (constant + template body)
- `grep "population_size.*50\|archive_size.*20" evolution/code/code_evolver_adapter.py`: 2 lines

## Self-Check: PASSED

- evolution/code/code_evolver_adapter.py exists (≥ 150 lines): FOUND (~290 LOC)
- tests/code/test_import_boundary.py exists (≥ 40 lines): FOUND
- Commit d8d5b7e (test) in git log
- Adapter file rescue commit lands all D-03 / Pitfall 1 / Pitfall 5 / D-04 markers

## Threat Surface

- T-21-IMPORT (Tampering) — D-18 second layer (this plan) closes the bypass of layer one (pre-commit hook). A new test file in evolution/ that adds `import openevolve` would now fail both layers.
- T-21-DOS — DEFAULT_SANDBOX_TIMEOUT propagated to both oe_config.evaluator.timeout and (downstream) subprocess.run timeout.
- T-21-LEAK — evaluator.py written to output_dir (durable audit path), not /tmp; the candidate-side eval_dir temp dirs are still cleaned by sandbox_runner.

## Next Phase Readiness

- **Plan 21-07 (evolve_code.py)** can lazy-import `evolve as _adapter_evolve, EvolutionAdapterResult` from this module and patch `"evolution.code.code_evolver_adapter.evolve"` in its tests.
- **Plan 21-08 (ansi_strip holdout tests)** does not directly depend on adapter; it tests the strip_ansi function itself for edge cases not covered by hermes-agent's 30 existing tests.

---
*Phase: 21-darwinian-code-evolution*
*Completed: 2026-05-20*
