---
phase: 18-personality-drift-detection
plan: 02
subsystem: prompts

tags: [drift-detection, dspy, llm-as-judge, calibration, f1-derivation, typed-outputfield, ra1, ra2, ra3, ra5]

# Dependency graph
requires:
  - phase: 10-prompt-constraints-cli
    provides: "PromptRoleChecker interface model + ConstraintResult dataclass (DriftDetector mirrors shape + uses ConstraintResult)"
  - phase: 18-personality-drift-detection
    plan: 01
    provides: "13 RED unit tests in tests/prompts/test_drift_detector.py + tests/prompts/test_drift_calibration.py; conftest fixtures; 6-row mini calibration fixture; .gitignore exceptions"
provides:
  - "DriftDetector class with 3-run averaging, conservative decision rule (mean - stdev > threshold), severity ladder (pass/warn/reject)"
  - "DriftScoreSignature with 4 typed-float OutputFields (tone_score / formality_score / vocabulary_score / persona_score) + explanation"
  - "DRIFT_DIMENSIONS module-level tuple constant (immutable contract)"
  - "_clamp_unit module-level helper"
  - "DriftCalibrationExample dataclass + DriftCalibrationDataset dataclass (single-file JSONL save/load)"
  - "DriftCalibrationBuilder using config.judge_model (not eval_model) with temperature=0.9 — generates 5 × 6 = 30 calibration variants"
  - "derive_thresholds(calibration, config) pure-stdlib F1 brute-scan over [0.10, 0.90] step 0.05"
affects: [18-03, 18-04, 18-05, evolve_prompt_sections]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Typed-float dspy.OutputField with try/except (ValidationError, ValueError, TypeError) -> 0.0 fallback (NOT 0.5) — Phase 18 establishes this pattern as the canonical M4-prevention shape for future LLM-as-judge constraints"
    - "Module-level dspy.LM construction in __init__ with explicit temperature + cache=False kwargs to ensure 3-run stochasticity (RA2)"
    - "Pure-stdlib F1 threshold derivation (range/sum/list-comprehension) — establishes that classification-metric brute-scans do not justify sklearn dependency"

key-files:
  created:
    - "evolution/prompts/drift_detector.py"
    - "evolution/prompts/drift_calibration.py"
  modified: []

key-decisions:
  - "DriftScoreSignature exposed as both module-level class AND DriftDetector.DriftScoreSignature class attribute so tests can introspect via DriftDetector.DriftScoreSignature.model_fields[...].annotation"
  - "LM construction moved into __init__ (NOT lazy per-check like PromptRoleChecker) so the temperature=0.7 + cache=False kwargs are statically grep-able and RA2 is closed at construction time"
  - "ConstraintResult.details uses json.dumps(per_dim, sort_keys=True) so downstream metrics.json + drift_report.txt consumers parse a stable schema"
  - "DriftCalibrationBuilder generates 3 drift variants per section across tone/formality/vocabulary — persona drift_dim is reserved for the no-drift trio to keep per-dim ground-truth labels clean (RA5 Mitigation 5)"
  - "derive_thresholds reuses DriftDetector._check_one_run (1-run per example per D-ROB-01) — calibration is NOT the 3-run gate path, so no stochastic noise enters threshold derivation"
  - "F1 tie-break is the ascending-strict `if f1 > best_f1` — the lowest-t candidate to hit max F1 wins, which is the most conservative threshold (flags more drift)"

requirements-completed: []  # PMPT-V2-02 is the parent requirement; Wave 1 contributes the implementation layer. PMPT-V2-02 closes only after Wave 5 (verifier passes all 9 truths).

# Metrics
duration: 4min
completed: 2026-05-15
---

# Phase 18 Plan 02: Wave 1 — DriftDetector + DriftCalibrationBuilder + derive_thresholds Summary

**Wave 0's 13 RED tests now GREEN: DriftDetector (10 tests) and DriftCalibrationBuilder/derive_thresholds (3 non-live tests) ship with typed-float DSPy Signatures, RA1/RA2/RA3/RA5 closure, and pure-stdlib F1 threshold derivation — establishing the constraint-gate analog and calibration tooling that Wave 2 will use to derive production thresholds.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-05-15T13:48:36Z
- **Completed:** 2026-05-15T13:52:23Z (227 seconds)
- **Tasks:** 2 (both auto-completed without checkpoints)
- **Files created:** 2
- **Files modified:** 0
- **LoC:** 529 total (drift_detector.py 258 LoC + drift_calibration.py 271 LoC) — exceeds plan's `min_lines: 150` + `min_lines: 180` artifacts contract by 108 LoC (72%) and 91 LoC (51%) respectively, driven by docstring rigor (RA-anchored explanations of every non-obvious decision)

## Accomplishments

- **DriftDetector** (`evolution/prompts/drift_detector.py`, 258 LoC) implements the pairwise LLM-as-judge personality-drift constraint. Compares original vs evolved sections on `tone`, `formality`, `vocabulary`, `persona` via a single typed-float DSPy `ChainOfThought`. `__init__` constructs `dspy.LM(config.eval_model, temperature=0.7, cache=False, **config.get_lm_kwargs())` so 3-run averaging yields non-zero stdev under DSPy 3.x cache semantics (RA2 / Pitfall A). `_check_one_run` wraps the judge in `try/except (ValidationError, ValueError, TypeError)` with a `{dim: 0.0}` fallback (NOT 0.5, per RA1 / M4 prevention). `check()` runs the judge 3 times, computes per-dim `mean` / `stdev` / `raw`, and applies the D-ROB-02 conservative decision `(mean - stdev) > thresholds[dim]`. Severity ladder per D-GATE-01: 0 dims = pass+passed=True, 1 dim = warn+passed=True (still deploys), 2+ dims = reject+passed=False. `check_all()` mirrors `PromptRoleChecker.check_all` signature so Wave 3 pipeline drop-in is trivial.
- **DriftScoreSignature** uses Python type annotation `float` (NOT `type=float` kwarg) on all 4 score OutputFields so `DriftScoreSignature.model_fields["tone_score"].annotation is float` holds — verified by `test_typed_float_parsing`. Docstring includes the anti-leak directive "Output each `<dim>_score` as a single decimal between 0.0 and 1.0, nothing else on the score lines" (RA1 / RESEARCH §Assumption A4).
- **DriftCalibrationBuilder** (`evolution/prompts/drift_calibration.py`, 271 LoC) generates 5 sections × 6 variants = 30 calibration examples (3 drift + 3 preserve per section, D-CAL-01..04). Constructor uses `config.judge_model` (gpt-4.1) — NOT `eval_model` — with `temperature=0.9` to diversify variants (RA5 Mitigations 1+3). `DRIFT_TARGET_DIMS_PER_SECTION = ("tone", "formality", "vocabulary")` ensures each true-drift variant has exactly one targeted dim, keeping per-dim ground-truth labels clean for `derive_thresholds` (RA5 Mitigation 5).
- **`DriftCalibrationDataset.save/load`** persists as a single JSONL file (D-CAL-02) — differs from `PromptBehavioralDataset.save` which takes a directory and writes train/val/holdout splits. Calibration is a stable evaluation asset, not a run-time split.
- **`derive_thresholds(calibration, config)`** implements pure-stdlib F1 brute scan over `range(10, 91, 5)` → 17 candidate thresholds × 30 examples × 4 dims = 2,040 ops (< 1ms verified). Reuses `DriftDetector._check_one_run` for 1-run scoring per example (D-ROB-01 — calibration is NOT the 3-run gate path). RA3 closed: zero `import sklearn|numpy|scipy` matches in source AND `sklearn` not present in `sys.modules` after import (verified by `test_no_sklearn_dependency`'s two-layer guard).
- **All 13 Wave 0 RED tests now GREEN**, with the 1 live-gated `test_f1_target_self_eval` still skipped on `RUN_LIVE_LLM=1`.
- **Zero regression**: full `tests/prompts/` suite went from 97 passed + 13 failed + 1 skipped (Wave 0 RED state) to 110 passed + 1 skipped. Full repo suite went from 514 passed + 1 xfailed to **527 passed + 1 skipped + 1 xfailed**, exactly +13 as expected.

## Task Commits

Each task was committed atomically:

1. **Task 1: DriftDetector + DriftScoreSignature + DRIFT_DIMENSIONS + _clamp_unit** — `32324aa` (feat)
2. **Task 2: DriftCalibrationBuilder + DriftCalibrationDataset + DriftCalibrationExample + derive_thresholds** — `4821678` (feat)

## Files Created/Modified

### Created

- **`evolution/prompts/drift_detector.py`** (258 LoC) — `DriftDetector` class with nested `DriftScoreSignature` (also exposed as module-level class for clean test introspection AND as `DriftDetector.DriftScoreSignature` class attribute). Module-level constants: `DRIFT_DIMENSIONS: tuple[str, ...]` (immutable 4-element tuple) and `_clamp_unit(x: float) -> float`. Imports: `json`, `statistics`, `dspy`, `pydantic.ValidationError`, `EvolutionConfig`, `ConstraintResult`. The `__init__` mandatorily calls `dspy.LM(config.eval_model, temperature=0.7, cache=False, **config.get_lm_kwargs())` — `temperature=0.7` AND `cache=False` literal strings appear in the source body and are statically grep-able by reviewers (3 + 4 occurrences respectively, the rest in docstrings). `check()` returns the full payload dict (`section_id`, `per_dim`, `exceeded_count`, `severity`, `explanation`, `constraint_result`) matching the Wave 0 test contract.

- **`evolution/prompts/drift_calibration.py`** (271 LoC) — `DriftCalibrationExample` + `DriftCalibrationDataset` dataclasses; `DriftCalibrationBuilder` class with nested `GenerateDriftVariant` DSPy Signature (drift/preserve mode + target_dim); module-level `derive_thresholds(calibration, config) -> dict` function. Imports: `json`, `random`, `dataclasses`, `datetime.timezone`, `pathlib.Path`, `dspy`, `EvolutionConfig`, `DRIFT_DIMENSIONS`, `DriftDetector`. **Zero forbidden imports** (`sklearn` / `numpy` / `scipy` — verified by source grep + sys.modules check). `DriftCalibrationBuilder.__init__` uses `dspy.LM(config.judge_model, temperature=0.9, **config.get_lm_kwargs())` — `judge_model` (not `eval_model`) appears as the first positional arg in `dspy.LM(...)` call site (line 148).

### Modified

None.

## Decisions Made

- **DriftScoreSignature exposed at module level AND as class attribute** — Defining the Signature at module scope (then bound as `DriftDetector.DriftScoreSignature = DriftScoreSignature`) gives the cleanest `pydantic.BaseModel.model_fields` introspection path for tests, while preserving the class-attribute access that PATTERNS §File 1 specified. Both `from evolution.prompts.drift_detector import DriftScoreSignature` and `DriftDetector.DriftScoreSignature.model_fields["tone_score"]` work.
- **LM constructed eagerly in `__init__`** (NOT lazily per `check()` like `PromptRoleChecker`) so the RA2 `temperature=0.7` + `cache=False` kwargs are statically grep-able and the `test_lm_constructed_with_temperature` test can assert the kwargs by patching `dspy.LM` and inspecting `mock_lm.call_args.kwargs`. Lazy construction would require patching `dspy.LM` inside `check()` and a more complex test fixture.
- **ConstraintResult.details serializes per_dim as `json.dumps(..., sort_keys=True)`** — Lets Wave 3 metrics.json + drift_report.txt consumers parse a deterministic schema without reaching into the broader payload dict. PromptRoleChecker uses free-form `explanation` text in details; DriftDetector uses structured JSON because per_dim is mechanically consumed.
- **Severity ladder uses strict `>` boundary** (`(mean - stdev) > thresholds[dim]`) per `test_conservative_decision_rule` boundary case: mean=0.5, stdev=0.1, mean-stdev=0.4, threshold=0.45 → 0.4 > 0.45 is False → exceeded=False. Strict `>` is the conservative choice (D-ROB-02 prefers false negatives).
- **`DRIFT_TARGET_DIMS_PER_SECTION` covers tone/formality/vocabulary only** — Persona drift_dim is intentionally absent from the 3 drift-variant trio per section. RA5 Mitigation 5 requires each true-drift variant to have exactly one targeted dim; the 4th dim (persona) is reserved for cross-section variation in production calibration runs. In the 30-example calibration set, persona appears as the no-drift baseline (drift_dim="none"). Future research may expand to 4 drift dims per section (= 35 examples total) once enough live data is available.
- **`derive_thresholds` reuses `DriftDetector._check_one_run`** instead of duplicating the LM call — keeps the LLM call shape identical between calibration and gate paths. The `placeholder = {dim: 0.5 for dim in DRIFT_DIMENSIONS}` is passed only to satisfy the constructor's threshold-completeness check; thresholds aren't used by `_check_one_run`.
- **F1 tie-break is the ascending-strict `if f1 > best_f1`** — When multiple thresholds yield the same F1, the FIRST candidate to hit the max (= lowest t since iteration is ascending) wins. This is the most conservative threshold (flags more drift) and matches the D-ROB-02 false-negative-preferring philosophy.
- **`from typing import Optional` removed from final drift_calibration.py** — Was in the plan template's import block but unused in the final code (no `Optional[...]` annotations). Kept the import block minimal per Python's `unused-import` convention.

## RA Closure Evidence

### RA1 (typed-float OutputField + 0.0 fallback)

```bash
$ .venv/bin/python -c "from evolution.prompts.drift_detector import DriftDetector; \
    assert DriftDetector.DriftScoreSignature.model_fields['tone_score'].annotation is float; \
    print('RA1 closed: tone_score.annotation is float')"
RA1 closed: tone_score.annotation is float
```

`_check_one_run` fallback is verified by `test_parse_failure_fallback_zero`:
- Mocks `judge` to raise `ValidationError`
- Asserts `scores == {"tone": 0.0, "formality": 0.0, "vocabulary": 0.0, "persona": 0.0}` (NOT 0.5)
- Asserts `"Parse failure" in explanation`

### RA2 (temperature=0.7 + cache=False — Pitfall A closure)

```bash
$ grep -n 'temperature=0\.7' evolution/prompts/drift_detector.py | grep -v '^#'
112:        self._lm = dspy.LM(
...

$ grep -c 'temperature=0\.7' evolution/prompts/drift_detector.py
3        # docstring (NOTE block) + RA2 inline comment + actual __init__ kwarg

$ grep -c 'cache=False' evolution/prompts/drift_detector.py
4        # docstring + RA2 inline comment + actual __init__ kwarg + test-cited reference in cache comment
```

Both literal strings present at the constructor call site (line 116-117). The `test_lm_constructed_with_temperature` test asserts `mock_lm.call_args.kwargs.get("temperature") == 0.7` AND `mock_lm.call_args.kwargs.get("cache") is False`.

### RA3 (no sklearn / numpy / scipy in derive_thresholds)

```bash
$ grep -E '^(import|from) (sklearn|numpy|scipy)' evolution/prompts/drift_calibration.py | wc -l
0

$ .venv/bin/python -c "import sys; sys.modules.pop('sklearn', None); \
    import evolution.prompts.drift_calibration; \
    assert 'sklearn' not in sys.modules; print('RA3 closed: no transitive sklearn')"
RA3 closed: no transitive sklearn
```

`test_no_sklearn_dependency` two-layer guard passes (source grep + sys.modules check).

### RA5 (calibration uses config.judge_model, not eval_model)

```bash
$ grep -n 'config\.judge_model' evolution/prompts/drift_calibration.py | head -3
5:using config.judge_model (gpt-4.1) — a different model than DriftDetector's
104:    Per D-CAL-03 + RA5: uses config.judge_model (gpt-4.1) with temperature=0.9
148:            config.judge_model,
163:        generator_model = self.config.judge_model
```

Line 148 is the `dspy.LM(config.judge_model, ...)` call site. `test_generator_uses_judge_model` asserts `mock_lm.call_args` first positional arg / `model` kwarg equals `"openai/gpt-4.1"` (the test config's `judge_model`), not `"openai/gpt-4.1-mini"` (the `eval_model`).

## Deviations from Plan

None — plan executed exactly as written. All 2 tasks completed in order, all verify commands passed first try, no Rule 1-4 auto-fixes triggered.

**Minor adherence note (not a deviation):** The plan template inlined `from typing import Optional` in `drift_calibration.py`'s import block, but the final code does not use `Optional[...]` anywhere — so the import was dropped to comply with the project's no-unused-imports convention (CLAUDE.md style guide is silent on this but the codebase consistently avoids unused imports per pyflakes-style hygiene). All other imports match the template exactly.

## Issues Encountered

None. Environment was stable (Python 3.13.3 `.venv`, dspy 3.1.3, pydantic 2.12.5). One harmless LiteLLM warning surfaced during a smoke import (`Failed to fetch remote model cost map ... falling back to local backup`) — this is upstream LiteLLM behavior when offline and does not affect test outcomes; it appeared only in the smoke-import shell session and not in any pytest run.

## Test Pass Counts

| Suite | Before (RED state) | After (this plan) | Delta |
|-------|---------------------|--------------------|-------|
| `tests/prompts/test_drift_detector.py` | 0 passed / 10 failed | 10 passed | +10 |
| `tests/prompts/test_drift_calibration.py` | 0 passed / 3 failed / 1 skipped | 3 passed / 1 skipped | +3 |
| `tests/prompts/` (full directory) | 97 passed / 13 failed / 1 skipped | 110 passed / 1 skipped | +13 |
| Full repo `tests/` | 514 passed / 13 failed / 1 skipped / 1 xfailed | **527 passed / 1 skipped / 1 xfailed** | +13 |

## Verification Performed

- **Task 1 verify** (post-commit): import smoke test succeeds, `DRIFT_DIMENSIONS == ('tone', 'formality', 'vocabulary', 'persona')`, `_clamp_unit(1.5) == 1.0` AND `_clamp_unit(-0.5) == 0.0`, `DriftScoreSignature.model_fields['tone_score'].annotation is float`, `temperature=0.7` and `cache=False` present (3 and 4 grep hits respectively). All 10 RED tests turn GREEN.
- **Task 2 verify** (post-commit): import smoke test succeeds, two-layer no-sklearn guard passes (source grep `wc -l` = 0 + post-import `sys.modules` check), `config.judge_model` appears as `dspy.LM` first positional arg at line 148. All 3 non-live RED tests turn GREEN; live `test_f1_target_self_eval` remains skipped.
- **Plan-level verification:** Full `tests/prompts/` directory: 110 passed + 1 skipped (zero regression in 97 pre-existing tests). Full `tests/` directory: 527 passed + 1 skipped + 1 xfailed. Both deletions checks post-commit returned empty (no accidental file removals).

## Next Phase Readiness

- **Wave 2 (calibration set + threshold derivation execution)** can now invoke `DriftCalibrationBuilder.generate(sections).save(Path("datasets/prompts/drift_calibration.jsonl"))` followed by `derive_thresholds(DriftCalibrationDataset.load(...), config)` and persist the result to `datasets/prompts/drift_thresholds.json`. Both are pure stdlib + DSPy ChainOfThought — no new dependencies required.
- **Wave 3 (`evolve_prompt_sections.py` integration)** can `from evolution.prompts.drift_detector import DriftDetector` and call `DriftDetector(config, thresholds).check_all(original_sections, evolved_sections)` knowing the return-shape contract is locked by the 13 GREEN tests.
- **Wave 4/5** can rely on the typed-float DSPy Signature + 0.0 fallback shape as the canonical M4-prevention pattern for any future drift-like constraints.
- No blockers, no deferred items, no architectural concerns surfaced during execution.

## Self-Check: PASSED

- FOUND: `evolution/prompts/drift_detector.py`
- FOUND: `evolution/prompts/drift_calibration.py`
- FOUND commit: `32324aa` (Task 1)
- FOUND commit: `4821678` (Task 2)
- VERIFIED: `DRIFT_DIMENSIONS == ('tone', 'formality', 'vocabulary', 'persona')`
- VERIFIED: `DriftDetector.DriftScoreSignature.model_fields['tone_score'].annotation is float`
- VERIFIED: `temperature=0.7` AND `cache=False` literal strings present in drift_detector.py source body
- VERIFIED: `config.judge_model` is `dspy.LM`'s first positional arg in drift_calibration.py (line 148)
- VERIFIED: 0 occurrences of `^(import|from) (sklearn|numpy|scipy)` in drift_calibration.py (RA3)
- VERIFIED: `sklearn` not in `sys.modules` after importing `evolution.prompts.drift_calibration` (RA3 two-layer guard)
- VERIFIED: 10 GREEN tests in `tests/prompts/test_drift_detector.py` (all from Wave 0)
- VERIFIED: 3 GREEN + 1 SKIPPED tests in `tests/prompts/test_drift_calibration.py` (live test still gated)
- VERIFIED: full `tests/prompts/` suite 110 passed + 1 skipped (zero regression vs Wave 0 baseline of 97 pre-existing tests)
- VERIFIED: full repo `tests/` suite 527 passed + 1 skipped + 1 xfailed (vs Wave 0 baseline of 514 passed + 1 xfailed, exactly +13 as expected)

---
*Phase: 18-personality-drift-detection*
*Completed: 2026-05-15*
