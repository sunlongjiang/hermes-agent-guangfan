---
phase: 18-personality-drift-detection
plan: 01
subsystem: testing

tags: [pytest, dspy, drift-detection, conftest, gitignore, red-tests, calibration-fixture]

# Dependency graph
requires:
  - phase: 10-prompt-constraints-cli
    provides: "PromptRoleChecker interface model + ConstraintResult dataclass that DriftDetector mirrors"
  - phase: 17-joint-section-optimization
    provides: "evolve_prompt_sections.py step-8 constraint-gate pipeline that Wave 3 will splice into"
provides:
  - "tests/prompts/conftest.py with mock_drift_lm + dummy_thresholds + drift_calibration_mini_path fixtures"
  - "10 RED unit-test stubs for DriftDetector covering RA1/RA2/D-ROB-02/D-GATE-01 severity ladder"
  - "4 RED unit-test stubs for DriftCalibrationBuilder + derive_thresholds (F1 optimality, no-sklearn guard, judge_model wiring, live-LLM skeleton)"
  - "6-row deterministic mini calibration fixture (1 section x 6 variants) for offline derive_thresholds tests"
  - ".gitignore exception lines exempting datasets/prompts/drift_calibration.jsonl and drift_thresholds.json from datasets/**/*.{jsonl,json} block (D-CAL-02 closure)"
affects: [18-02, 18-03, 18-04, 18-05, drift_detector, drift_calibration, derive_thresholds]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared tests/prompts/conftest.py module (first conftest in this directory) — pytest fixtures for drift-specific mocking"
    - "Lazy module imports inside helper functions (_make_detector) so pytest can collect RED test files before production code exists"
    - "Multi-layer dependency guard pattern (source grep + sys.modules check) for forbidding sklearn/numpy/scipy in derive_thresholds"

key-files:
  created:
    - "tests/prompts/conftest.py"
    - "tests/prompts/test_drift_detector.py"
    - "tests/prompts/test_drift_calibration.py"
    - "tests/prompts/fixtures/drift_calibration_mini.jsonl"
  modified:
    - ".gitignore"

key-decisions:
  - "Lazy module imports inside helper functions instead of file-top-level imports so pytest --collect-only succeeds even before Wave 3 lands drift_detector.py"
  - "Mini fixture covers exactly the 3 drift_dim values that have explicit drift labels (tone/formality/vocabulary) — persona dim has no positive example in the 6-row mini set; test_derive_thresholds_f1_optimal asserts (0, 1) bounds only on the 3 dims with positives"
  - "test_no_sklearn_dependency uses two-layer guard (source grep + sys.modules check) to prevent silent transitive sklearn import"

patterns-established:
  - "Wave-0 RED scaffold pattern for Phase 18 — tests collect (syntactically valid) but fail at runtime with ModuleNotFoundError, establishing executable verify targets for all Wave 1-5 success criteria"
  - "Drift mini-fixture schema: section_id / original_text / evolved_text / is_drift / drift_dim / generation_metadata — matches future DriftCalibrationExample dataclass 1:1"
  - "Pytest fixture cohabitation — module-local _make_checker helpers (test_prompt_constraints.py) coexist with new shared conftest fixtures without collisions"

requirements-completed: []  # PMPT-V2-02 is the parent requirement; Wave 0 contributes verify scaffolding, not requirement completion. The requirement closes only after Wave 5.

# Metrics
duration: 6min
completed: 2026-05-15
---

# Phase 18 Plan 01: Wave 0 RED Test Scaffolds Summary

**14 failing pytest scaffolds (10 DriftDetector + 4 DriftCalibrationBuilder/derive_thresholds) plus shared conftest fixtures and gitignore exceptions establish executable verify targets for every Wave 1-5 success criterion before any production code is written.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-15T13:34:42Z
- **Completed:** 2026-05-15T13:40:35Z
- **Tasks:** 3 (all auto-completed without checkpoints)
- **Files created:** 4
- **Files modified:** 1

## Accomplishments
- Created `tests/prompts/conftest.py` (first conftest in this directory) exposing `mock_drift_lm`, `dummy_thresholds`, and `drift_calibration_mini_path` fixtures for downstream Wave 1-5 tests.
- Authored 10 RED unit-test stubs in `tests/prompts/test_drift_detector.py` covering typed-float OutputField parsing (RA1), 0.0 fallback on ValidationError (RA1), `temperature=0.7 / cache=False` LM construction (RA2), 3-run stdev>0 (RA2), conservative `mean - 1*stdev > threshold` decision rule (D-ROB-02), and the full pass/warn/reject severity ladder (D-GATE-01).
- Authored 4 RED unit-test stubs in `tests/prompts/test_drift_calibration.py` covering F1-optimal threshold derivation on the mini fixture, two-layer no-sklearn dependency guard (source grep + `sys.modules` check), `judge_model` (not `eval_model`) wiring on `DriftCalibrationBuilder`, and a `RUN_LIVE_LLM`-gated F1 self-eval skeleton.
- Committed the deterministic 6-row mini calibration fixture (`tests/prompts/fixtures/drift_calibration_mini.jsonl`) so `derive_thresholds` unit tests can run offline.
- Added two negation lines to `.gitignore` exempting `datasets/prompts/drift_calibration.jsonl` and `datasets/prompts/drift_thresholds.json` from the `datasets/**/*.{jsonl,json}` block — closes D-CAL-02 and makes future threshold derivation reproducible across machines.

## Task Commits

Each task was committed atomically:

1. **Task 1: conftest.py + mini fixture** — `97f8c08` (test)
2. **Task 2: 10 RED DriftDetector tests** — `bba021c` (test)
3. **Task 3: 4 RED drift_calibration tests + .gitignore exceptions** — `c00ad1f` (test)

## Files Created/Modified
- `tests/prompts/conftest.py` — shared pytest fixtures: `dummy_thresholds` (D-CAL-01 placeholder values), `mock_drift_lm` (patches `evolution.prompts.drift_detector.dspy.LM` with a controllable `_MockDriftLM` whose `set_scores(...)` lets each test compose a deterministic `dspy.Prediction`), `drift_calibration_mini_path` (filesystem path to the 6-row mini fixture).
- `tests/prompts/test_drift_detector.py` — `TestDriftDetector` class (9 scenarios) + `TestDriftDetectorCheckAll` class (1 scenario for `check_all` payload schema). Helper `_make_detector(thresholds=None)` uses `EvolutionConfig.__new__` to skip post-init env discovery and patches `dspy.LM` so construction succeeds without API keys.
- `tests/prompts/test_drift_calibration.py` — `TestDeriveThresholds` (F1 optimality + no-sklearn dependency) + `TestDriftCalibrationBuilder` (`judge_model` wiring + live-LLM skeleton). Loads the mini fixture via the `drift_calibration_mini_path` fixture and asserts `0 < threshold < 1` only on the 3 dims with positive examples.
- `tests/prompts/fixtures/drift_calibration_mini.jsonl` — 6 deterministic JSON rows for section `memory_guidance`: 3 drift rows covering tone/formality/vocabulary + 3 no-drift rows. Schema mirrors the future `DriftCalibrationExample` dataclass 1:1.
- `.gitignore` — appended 2 negation lines (`!datasets/prompts/drift_calibration.jsonl`, `!datasets/prompts/drift_thresholds.json`) plus a comment block right after the existing `!datasets/.gitkeep` exception. Ordering preserved (negations must follow the original ignore line per gitignore semantics).

## Decisions Made
- **Lazy imports inside helper functions** rather than top-level `from evolution.prompts.drift_detector import ...` so that `pytest --collect-only` does not raise `ModuleNotFoundError` before Wave 3 lands the module. Tests still fail at run time with `ModuleNotFoundError` (RED state confirmed).
- **`EvolutionConfig.__new__(EvolutionConfig)`** in both helpers and tests to bypass `__post_init__`'s hermes-agent path discovery (which would require `HERMES_AGENT_REPO` env or filesystem checkout). Each test then sets only the fields it actually exercises (`eval_model`, `api_base`, `api_key`, and where relevant `judge_model`).
- **F1-optimal bound assertion (Task 3 `test_derive_thresholds_f1_optimal`)** restricted to `0.0 < t < 1.0` on tone/formality/vocabulary; persona is omitted because the 6-row mini fixture has no positive persona example. The full-set 30-example calibration in Wave 1 will exercise persona.
- **Two-layer no-sklearn guard** (source grep + post-import `sys.modules` check) rather than a single `import sklearn` ImportError test — the latter would not catch a transitive sklearn import pulled in by a sub-dependency.
- **Mock pattern for 3-run averaging** uses `MagicMock(side_effect=[p1, p2, p3])` rather than `return_value=...` so each of the 3 `judge(...)` calls returns a distinct `dspy.Prediction` (RA2 stochasticity simulated in unit tests).

## Deviations from Plan

None - plan executed exactly as written. All 3 tasks completed in the specified order, all verify commands passed first try, and no auto-fix rules (Rule 1-4) triggered.

## Issues Encountered

None. Environment was clean (Python 3.13.3 `.venv`, dspy 3.1.3, pydantic 2.12.5), pytest collection and run produced the expected RED-state output on the first attempt for each task.

## Verification Performed

- **Task 1 verify** (post-commit): `tests/prompts/conftest.py` and `tests/prompts/fixtures/drift_calibration_mini.jsonl` exist; fixture is exactly 6 lines with 3 drift / 3 no-drift rows; `drift_dim` coverage is `{tone, formality, vocabulary}`; pytest collects `conftest.py` without errors.
- **Task 2 verify** (post-commit): 10 test names collected from `test_drift_detector.py` exactly matching VALIDATION map plus the additional `test_drift_report_payload`; `.venv/bin/pytest tests/prompts/test_drift_detector.py -x` fails with `ModuleNotFoundError: No module named 'evolution.prompts.drift_detector'`.
- **Task 3 verify** (post-commit): 4 test names collected from `test_drift_calibration.py`; `.gitignore` contains both `!datasets/prompts/drift_calibration.jsonl` and `!datasets/prompts/drift_thresholds.json` verbatim; pytest run fails with `ModuleNotFoundError: No module named 'evolution.prompts.drift_calibration'`.
- **Plan-level verification:** `.venv/bin/pytest tests/prompts/test_drift_detector.py tests/prompts/test_drift_calibration.py --collect-only` collects exactly 14 tests; run exits non-zero with 13 failed + 1 skipped (live-LLM skeleton). Whole-dir `pytest tests/prompts/ --collect-only` rises from 97 to 111 tests (no regression in pre-existing 97 tests).

## Next Phase Readiness

- **Wave 1 (drift_calibration.py)** can now treat `test_drift_calibration.py::TestDeriveThresholds` and `test_drift_calibration.py::TestDriftCalibrationBuilder::test_generator_uses_judge_model` as executable verify targets. The 6-row mini fixture lets `derive_thresholds` be unit-tested without LLM calls.
- **Wave 3 (drift_detector.py)** can target the 10 `test_drift_detector.py` scenarios. Every contract decision in `<interfaces>` (DRIFT_DIMENSIONS tuple, DriftScoreSignature field types, `_check_one_run` fallback shape, `check()` dict schema, severity ladder mapping) is now pinned by an executable test.
- **Wave 4 (evolve_prompt_sections.py integration)** will be able to import `DriftDetector` and `derive_thresholds` knowing their contracts are already locked.
- No blockers, no deferred items, no architectural concerns surfaced during Wave 0.

## Self-Check: PASSED

- FOUND: `tests/prompts/conftest.py`
- FOUND: `tests/prompts/test_drift_detector.py`
- FOUND: `tests/prompts/test_drift_calibration.py`
- FOUND: `tests/prompts/fixtures/drift_calibration_mini.jsonl`
- FOUND: `.gitignore` (modified — 2 negation lines added)
- FOUND commit: `97f8c08` (Task 1)
- FOUND commit: `bba021c` (Task 2)
- FOUND commit: `c00ad1f` (Task 3)
- VERIFIED: 14 tests collected across the 2 new test files (10 + 4); run exits non-zero with 13 failed + 1 skipped (RED state)
- VERIFIED: existing `tests/prompts/` test count rose from 97 to 111 — no pre-existing tests broken

---
*Phase: 18-personality-drift-detection*
*Completed: 2026-05-15*
