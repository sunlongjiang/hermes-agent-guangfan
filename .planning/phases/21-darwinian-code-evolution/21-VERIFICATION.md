---
phase: 21-darwinian-code-evolution
verified: 2026-05-20T13:42:11Z
status: human_needed
score: 3/3 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 2/3 must-haves verified (1 fully VERIFIED, 1 PARTIAL, 1 FAILED)
  gaps_closed:
    - "At least one code component (tools/ansi_strip.py) evolvable end-to-end — signature drift between code_fitness.score_candidate ↔ sandbox_runner.run_pytest_in_sandbox repaired in commit c9498f4; dry-run end-to-end now exits 0 with pytest 30/30, composite=1.0"
    - "Fitness function: pytest binary gate (80%) + size penalty (10%) + ruff lint (10%), no LLM judge — math was already correct, but is now reachable end-to-end (no longer PARTIAL)"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "Live one-iteration openevolve smoke test with real LLM credentials"
    expected: "`python -m evolution.code.evolve_code --component tools/ansi_strip.py --iterations 1 --max-cost 1.0 --hermes-repo ~/.hermes/hermes-agent` produces `output/code/<ts>/{NOTICE.md,metrics.json,diff.txt,eval_holdout.json}` on accept OR `output/code/FAILED_<ts>/` with a real D-15 reject_reason (not a TypeError trace). CLI exits 0 (accept) or 1 (reject). NOTICE.md contains the literal 'UNREVIEWED — DO NOT MERGE WITHOUT HUMAN REVIEW' marker."
    why_human: "Requires a funded LLM API key (~$1-5 in optimizer cost). CI cannot run openevolve. The dry-run path is now provably green (verifier reproduced it), but the full evolve loop — including openevolve's subprocess-spawned evaluator and the holdout gate — has only been exercised in unit-mocked form. This is the final V2-CODE-01 sign-off and must be human-witnessed before the phase is closed."
---

# Phase 21: Darwinian Code Evolution Verification Report

**Phase Goal:** Integrate darwinian-evolver (substitute: openevolve, Apache-2.0) for code-level evolution of hermes-agent components.
**Verified:** 2026-05-20T13:42:11Z
**Status:** human_needed (all programmatic checks pass; one live-cost smoke test pending human execution)
**Re-verification:** Yes — after BLOCKER fix in commit c9498f4

## Re-verification Context

Prior run (2026-05-20T12:47:52Z) found one BLOCKER: `code_fitness.score_candidate` called
`run_pytest_in_sandbox(eval_dir=..., train_test_ids=...)` but the real
`sandbox_runner.run_pytest_in_sandbox` requires positional args
`(candidate_path, eval_dir_base, test_file_path, run_id, timeout_seconds=120)`.
The 28-test suite missed it because all mocks copied the 21-04 SUMMARY's incorrect 3-arg signature.

Commit `c9498f4` ("fix(21): repair cross-plan signature drift") landed the fix. This re-verification
performs:
- **Full 3-level re-check on the failed item** (Truth 2: end-to-end evolvability).
- **Quick regression re-check on previously-passing items** (Truth 1, Truth 3, all artifacts, all
  key links).
- **Live behavioral spot-check**: re-ran the same dry-run command that previously crashed.

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | openevolve (Apache-2.0, ≥0.2.27) integrated and tested as code evolution substrate | VERIFIED | `pyproject.toml` line 32: `code = ["openevolve>=0.2.27"]`; `.venv` has openevolve 0.2.27 installed; D-03 single import surface intact (0 imports outside `evolution/code/code_evolver_adapter.py`, verified by grep + test_import_boundary.py); LICENSE (MIT) at repo root; `.pre-commit-config.yaml` carries `openevolve-single-import-surface` hook. **No regression from prior run.** |
| 2 | At least one code component (`tools/ansi_strip.py`) evolvable end-to-end | VERIFIED | Re-ran the same command that previously crashed with TypeError: `python -m evolution.code.evolve_code --component tools/ansi_strip.py --dry-run --hermes-repo ~/.hermes/hermes-agent`. Now exits 0 with Pre-flight 1-7 PASS, CodeTarget panel rendered (component path, test path, baseline=1784 bytes, hermes_agent_commit=ff6a86cb), Test split 20 train / 10 holdout, Baseline Fitness panel showing pytest 30/30, size_component 1.0, ruff_score 1.0, composite 1.0. New `tests/code/test_code_fitness.py::TestRealSandboxIntegration::test_score_candidate_real_sandbox_baseline` passes — exercises score_candidate against the REAL sandbox_runner (no monkeypatch.setitem) end-to-end. Signature alignment confirmed by `inspect.signature` at runtime. The remaining 1-iteration live-LLM smoke test is moved to human verification (cost-bearing). |
| 3 | Fitness function: pytest binary gate (80%) + size penalty (10%) + ruff lint (10%), no LLM judge | VERIFIED | `code_fitness.score_candidate` correctly implements `composite = pytest_score*0.80 + size_component*0.10 + ruff_score*0.10` (line 363-365). Pytest binary gate (D-11), size piecewise linear (D-12 soft=1.3 / hard=1.5), ruff buckets (D-13: 0→1.0, 1-2→0.7, 3-5→0.4, 6-10→0.1, >10→0.0). No `import dspy` / `import openai` (D-14 honored — file-grep). All 7 unit tests cover the math (6 mocked + 1 real-sandbox integration). **Math was correct in prior run; previously PARTIAL because the call site was unreachable — now reachable, so promoted to VERIFIED.** |

**Score:** 3/3 truths VERIFIED (was 2/3 with 1 FAILED, 1 PARTIAL).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `LICENSE` | MIT text at repo root (D-17) | VERIFIED | (regression check) 22 lines, "MIT License", "Copyright (c) 2026 Longjiang Sun". |
| `pyproject.toml` | `[code]` extra with `openevolve>=0.2.27`; `[darwinian]` removed | VERIFIED | (regression check) Lines 31-33, 46-48. No `[darwinian]` extra. |
| `.pre-commit-config.yaml` | `openevolve-single-import-surface` local hook (D-18 layer-1) | VERIFIED | (regression check) Exact grep gate intact. |
| `evolution/code/__init__.py` | Lazy-import guard, no `import openevolve` | VERIFIED | (regression check) Docstring-only, no module-level statements. |
| `evolution/code/LICENSING.md` | License boundary doc (D-21) | VERIFIED | (regression check) "Apache-2.0", "MIT License" present. |
| `evolution/code/code_target_loader.py` | CodeTarget + find_target + find_target_tests + stratify_tests; reject evolution/ path | VERIFIED | (regression check) 402 lines, AST-only test discovery, stratification deterministic with seed=42. |
| `evolution/code/code_fitness.py` | CodeFitness + score_candidate; pytest hard gate; size & ruff; no LLM | **FIXED → VERIFIED** | 382 lines (was 352). Lines 254-261 now correctly import + call `run_pytest_in_sandbox(evolved_path, eval_dir, Path(test_file_path), run_id)` with the actual 5-arg signature (uuid-based run_id at line 276, sibling-test inference fallback at lines 267-273). `test_file_path` added as keyword-only param (line 209). No `import dspy`/`openai` (verified by file-grep). All 7 unit tests pass. |
| `evolution/code/sandbox_runner.py` | build_restricted_env + run_pytest_in_sandbox with restricted env + timeout + eval_dir cleanup | VERIFIED | (regression check) 273 lines, signature unchanged: `(candidate_path, eval_dir_base, test_file_path, run_id, timeout_seconds=120)`. 4 unit tests pass. **Now reachable from score_candidate.** |
| `evolution/code/code_evolver_adapter.py` | Single openevolve import surface; EVOLVE-BLOCK marker; self-contained evaluator | **FIXED → VERIFIED** | 344 lines (was 342). Sole openevolve importer. `_EVALUATOR_TEMPLATE` line 100-109 now passes `test_file_path=TEST_FILE_PATH` to `score_candidate` — the TEST_FILE_PATH variable was already present in template scope from `_generate_evaluator_file` (line 82). Template rendered and AST-parsed cleanly during verification. |
| `evolution/code/evolve_code.py` | Click CLI with 8 flags; pre-flight 7 steps; 9-step orchestration; FAILED_<ts> path | **FIXED → VERIFIED** | 481 lines (was 478). Both `score_candidate` call sites now pass `test_file_path=target.test_file_path`: step 5 baseline (line 282-289) and step 8 holdout (line 332-339). Real dry-run end-to-end verified by verifier (see behavioral spot-check below). |
| `tests/code/test_import_boundary.py` | D-18 layer-2 pytest gate | VERIFIED | (regression check) Passes. |
| `tests/code/test_code_target_loader.py` | 4 unit tests | VERIFIED | (regression check) 4 tests pass. |
| `tests/code/test_code_fitness.py` | 6 unit tests + 1 real-sandbox integration test | **FIXED → VERIFIED** | 7 tests total now (was 6). The fake `sandbox_runner` stub at line 37 now uses the **real** 5-arg signature `(candidate_path, eval_dir_base, test_file_path, run_id, timeout_seconds=120)`. New `TestRealSandboxIntegration::test_score_candidate_real_sandbox_baseline` (lines 268-319) exercises score_candidate against the actual sandbox_runner subprocess pytest run — skips when hermes-agent unreachable, passes when present. |
| `tests/code/test_sandbox_runner.py` | 4 unit tests covering restricted_env / timeout / cleanup / hermes_import | VERIFIED | (regression check) 4 tests pass. |
| `tests/code/test_evolve_code_cli.py` | 3 E2E CLI tests | VERIFIED | (regression check) 3 tests pass. Mocks `score_candidate` at the CLI boundary (intentional — keeps CLI tests fast); the real integration path is now covered by `TestRealSandboxIntegration`. |
| `tests/code/test_ansi_strip_holdout.py` | 9-10 edge case tests | VERIFIED | (regression check) 10 tests pass. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `pyproject.toml [code] extra` | `evolution/code/code_evolver_adapter.py` | `pip install .[code]` | WIRED | openevolve 0.2.27 installed. |
| `.pre-commit-config.yaml hook` | `evolution/code/code_evolver_adapter.py` | grep gate excludes adapter | WIRED | (regression check) Intact. |
| `code_target_loader.find_target()` | `~/.hermes/hermes-agent/tools/ansi_strip.py` | Path resolution | WIRED | Resolution succeeded in dry-run (CodeTarget panel rendered). |
| `code_fitness.score_candidate()` | `sandbox_runner.run_pytest_in_sandbox()` | Deferred import | **WIRED (REPAIRED)** | Signatures now compatible (verified by `inspect.signature` and a real test run). Was the single BLOCKER in prior verification. |
| `code_evolver_adapter.evolve()` | `openevolve.run_evolution()` | `_EVALUATOR_TEMPLATE` | WIRED | Rendered template parses cleanly; `score_candidate(test_file_path=TEST_FILE_PATH, ...)` call site is consistent with the production signature. End-to-end LLM-driven invocation still requires the human spot-check. |
| `evolve_code.evolve()` step 5 baseline | `code_fitness.score_candidate()` | direct call | WIRED | Re-verified in dry-run end-to-end. |
| `evolve_code.evolve()` step 8 holdout | `code_fitness.score_candidate()` | direct call | WIRED (code-level) | Code path correct; runtime exercise requires the live evolve step (human spot-check). |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `evolve_code.evolve()` | `baseline_fitness` | `score_candidate(target.component_path, ...)` via real sandbox_runner | YES — confirmed pytest 30/30 on real ansi_strip.py | FLOWING |
| `code_fitness.score_candidate()` | `pytest_passed, pytest_total, pytest_failures` | `run_pytest_in_sandbox(...)` real subprocess | YES — pytest 30/30, no TypeError | FLOWING |
| `code_evolver_adapter._EVALUATOR_TEMPLATE` | `fitness` | `score_candidate(test_file_path=TEST_FILE_PATH, ...)` | YES at rendering / template level; final runtime confirmation requires a live evolve iteration | FLOWING (static) — human spot-check confirms dynamic |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| CLI `--help` lists all 8 flags | `python -m evolution.code.evolve_code --help` | All 8 flags shown | PASS |
| D-03 single import surface | `grep -rn "^import openevolve\|^from openevolve" evolution/ --include="*.py" --exclude-dir=__pycache__ \| grep -v "code_evolver_adapter.py" \| wc -l` | 0 | PASS |
| All 29 tests/code/ tests pass | `pytest tests/code/ -v` | 29 passed in 3.11s (was 28; +1 real-sandbox integration) | PASS |
| `evolve_code --dry-run` end-to-end against real hermes-agent | `python -m evolution.code.evolve_code --component tools/ansi_strip.py --dry-run --hermes-repo ~/.hermes/hermes-agent` | Pre-flight 1-7 PASS; CodeTarget panel rendered; Test split 20/10; Baseline Fitness pytest 30/30, size_component 1.0, ruff_score 1.0, composite 1.0; DRY RUN exits 0 | **PASS** (was FAIL with TypeError) |
| `score_candidate` direct call against real sandbox_runner (integration test) | `pytest tests/code/test_code_fitness.py::TestRealSandboxIntegration -v` | 1 passed | **PASS** (was N/A — test did not exist) |
| Interface alignment check | `inspect.signature(run_pytest_in_sandbox)` + `inspect.signature(score_candidate)` | `(candidate_path, eval_dir_base, test_file_path, run_id, timeout_seconds=120)` and score_candidate call site at code_fitness.py:281-286 passes those 4 positional args correctly | **PASS** (was FAIL — kwargs mismatched) |
| Evaluator template parses as valid Python | `ast.parse(_EVALUATOR_TEMPLATE.format(...))` | Parses cleanly; `test_file_path=TEST_FILE_PATH` confirmed in rendered output | PASS |
| openevolve import succeeds | `python -c "import openevolve; print(openevolve.__version__)"` | 0.2.27 | PASS |
| Repo-wide regression | `pytest tests/ --ignore=tests/code -q` | 695 passed, 1 skipped, 1 xfailed in 62s | PASS — no regression |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| V2-CODE-01 | 21-01..21-08 (all 8 plans claim it) | "Darwinian code evolution — at least one hermes-agent code component evolvable" | **SATISFIED (programmatic)** — pending human live-LLM confirmation | The dry-run / baseline path is fully wired and exercises the real pytest sandbox against `tools/ansi_strip.py` (pytest 30/30, composite 1.0). The full LLM-driven evolve loop is wired at template-render time but its first live iteration is the human verification item. Per REQUIREMENTS.md the row reads "V2-CODE-01 | Phase 21 | Pending" — the verifier recommends updating to "In Progress" or similar after the human spot-check, but that update belongs to the closing step, not this verification. |

No orphaned requirements — every requirement ID declared in plans' `requirements:` frontmatter is V2-CODE-01.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `evolution/code/code_evolver_adapter.py` | 100 | `target_path = Path("{test_file_path}").parent.parent / "ansi_strip.py"` — hardcoded "ansi_strip.py" filename and assumes test layout `…/tests/tools/test_*.py` with the target at `…/tools/ansi_strip.py` | Info | This was flagged as "looks suspicious" in the prior run. For the V2-CODE-01 PoC (single-component target by design — see Success Criterion #2 "**at least one** code component (tools/ansi_strip.py)") this is intentional scaffolding; broader component support is out of scope. Document as known limitation for any Phase 22+ generalization. |
| `21-04-SUMMARY.md` / `21-05-SUMMARY.md` | provides blocks | SUMMARYs still document the obsolete 3-param contract for `run_pytest_in_sandbox` | Info | Documentation drift remains; the SUMMARYs are immutable historical records of what each executor *claimed*. The verifier-facing source of truth is now the live signature in `sandbox_runner.py` + the new `TestRealSandboxIntegration` test, which is the canonical contract check going forward. No action required; flag is informational. |

No blocker or warning anti-patterns remain. The two warning/blocker entries from the prior run
(broken keyword call in `code_fitness.py` and `_EVALUATOR_TEMPLATE`) are resolved.

### Human Verification Required

#### 1. Live one-iteration openevolve smoke test (cost-bearing)

**Test:** With a funded LLM API key configured (env var `EVOLUTION_API_KEY` or equivalent for the chosen provider), run:

```bash
python -m evolution.code.evolve_code \
    --component tools/ansi_strip.py \
    --iterations 1 \
    --max-cost 1.0 \
    --hermes-repo ~/.hermes/hermes-agent
```

**Expected:** Either `output/code/<ts>/{component.py, NOTICE.md, metrics.json, diff.txt, eval_holdout.json}` is created with a real candidate **and** CLI exits 0 (accept), OR `output/code/FAILED_<ts>/{NOTICE.md, metrics.json, diff.txt}` is created with a real D-15 reject_reason (not a TypeError trace) and CLI exits 1 (reject). NOTICE.md must contain the literal "UNREVIEWED — DO NOT MERGE WITHOUT HUMAN REVIEW".

**Why human:** Requires a funded LLM API key (~$1-5 in optimizer cost; the default optimizer model is `openai/gpt-4.1`). CI does not have credentials. The dry-run path is now provably green (verifier reproduced it 30/30 pytest), and the evaluator template is shown to parse + match the production signature, so the residual risk is small — but only a live iteration can confirm openevolve actually drives at least one mutation, the evaluator subprocess loads correctly, and the holdout gate path produces real artifacts.

### Gaps Summary

The single BLOCKER from the prior run is **closed**. Commit `c9498f4` ("fix(21): repair cross-plan
signature drift") aligned the four interfaces (`score_candidate`, `run_pytest_in_sandbox`,
`evolve_code` orchestrator, `_EVALUATOR_TEMPLATE`) onto the 5-arg contract that
`sandbox_runner.py` actually ships with:

```
run_pytest_in_sandbox(candidate_path, eval_dir_base, test_file_path, run_id, timeout_seconds=120)
```

`score_candidate` gained a keyword-only `test_file_path` parameter (with a sibling-test inference
fallback for callers that don't pass it) and generates a uuid-based `run_id` internally. Both
`evolve_code` step 5 baseline and step 8 holdout call sites now forward
`test_file_path=target.test_file_path`. The evaluator template threads
`test_file_path=TEST_FILE_PATH` to `score_candidate` (the variable was already in template scope).

Verifier-side proof that the wiring works end-to-end:
1. The exact dry-run command that previously crashed (`python -m evolution.code.evolve_code
   --component tools/ansi_strip.py --dry-run --hermes-repo ~/.hermes/hermes-agent`) now exits 0
   with pytest 30/30, composite 1.0.
2. A new integration test `TestRealSandboxIntegration::test_score_candidate_real_sandbox_baseline`
   exercises `score_candidate` against the **real** `sandbox_runner` (no `monkeypatch.setitem`
   injection) and asserts pytest 30/30 + composite > 0.7. This is the regression net the prior
   verification said was missing.
3. `pytest tests/code/`: 29 passed (was 28; +1 real integration test).
4. `pytest tests/ --ignore=tests/code -q`: 695 passed, 1 skipped, 1 xfailed — no regression in the
   broader suite.
5. D-03 single-import-surface mechanical check: 0 openevolve imports outside the adapter.

**Status:** `human_needed`. All 3 ROADMAP Success Criteria are programmatically verified, all 14
required artifacts are in place and substantive, all key links are wired, and no blocker / warning
anti-patterns remain. One remaining item — a live one-iteration evolve with real LLM credentials —
requires a funded API key (~$1-5 cost) and is therefore moved to human verification rather than
being a phase-blocking gap. The verifier recommends running it before declaring V2-CODE-01 "Done"
in REQUIREMENTS.md, but the goal-backward contract for Phase 21 is otherwise fulfilled.

---

_Verified: 2026-05-20T13:42:11Z_
_Verifier: Claude (gsd-verifier) — re-verification of commit c9498f4_
