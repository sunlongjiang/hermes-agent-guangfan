---
phase: 18-personality-drift-detection
plan: 04
subsystem: prompts
tags: [drift-detection, integration, click, constraint-gate, d-bypass-01, d-rob-04, d-out-02]

requires:
  - phase: 18-personality-drift-detection
    provides: "DriftDetector class + DRIFT_DIMENSIONS (Wave 1 / Plan 18-02)"
  - phase: 18-personality-drift-detection
    provides: "datasets/prompts/drift_thresholds.json (Wave 2 / Plan 18-03)"
provides:
  - "evolve_prompt_sections.py step 8c DriftDetector integration + 3-run gate (severity ladder pass/warn/reject)"
  - "drift_* metrics fields written UNCONDITIONALLY for BOTH joint AND round-robin modes (D-ROB-04 / D-OUT-02)"
  - "drift_report.txt on success and FAILED paths (D-OUT-03)"
  - "Rich Table 'Drift Detection (per-section x per-dim, 3-run averaged)' (D-OUT-01)"
  - "--drift-thresholds-path Click flag with default datasets/prompts/drift_thresholds.json (D-BYPASS-02)"
  - "Regression guard: NO --no-drift-check / --skip-drift-check Click option exists (D-BYPASS-01)"
affects: ["Plan 18-05 (CLI integration tests) — UNBLOCKED"]

tech-stack:
  added: []
  patterns:
    - "Wave 3 integration pattern: import → instantiate at gate position → aggregate per-section results → 6-field metrics block (4-space function-body indent) → drift_report.txt on both success + FAILED paths"
    - "Backward-compatible default-flag pattern: `click.Path(exists=True, path_type=Path)` + default `datasets/prompts/drift_thresholds.json` (git-tracked from Plan 18-03), so users don't need to pass the flag"
    - "Existing-test compatibility pattern: when introducing a new required artifact (drift_thresholds.json) into a sandboxed test workdir (tmp_path + chdir), tests must (a) materialize a stub file before runner.invoke and (b) patch the consuming class (DriftDetector) to a no-op mock"

key-files:
  created: []
  modified:
    - "evolution/prompts/evolve_prompt_sections.py (5 insertion points: import, step 8c block, success metrics drift_* fields, success-path drift_report.txt write, --drift-thresholds-path Click option + main()/evolve() signature threading)"
    - "tests/prompts/test_evolve_prompt_sections_cli.py (TestABBaseline._ab_patched_run — added drift_thresholds.json stub + DriftDetector no-op mock for sandboxed tmp_path workdir; Rule-3 deviation, see Deviations below)"

key-decisions:
  - "Edit-3 drift_* metrics block placed at 4-space (function-body) indent, OUTSIDE the joint-only conditional — both joint AND round-robin pipelines write drift_* fields (D-ROB-04)"
  - "drift_report.txt written on BOTH success path (output/prompts/<ts>/drift_report.txt) and FAILED path (output/prompts/FAILED_<ts>/drift_report.txt) — D-OUT-03 satisfied at both call sites"
  - "FAILED path also writes evolved_sections.json + diff.txt + drift_report.txt + drift_* metrics fields so human review of REJECT decision is fully self-contained (D-GATE-04)"
  - "Click help text for --drift-thresholds-path intentionally avoids literal 'WARNING' and '--no-drift-check'/'--skip-drift-check' tokens so the D-BYPASS-01 grep guard cannot be defeated by help-text wording. Wording: 'There is no bypass flag (D-BYPASS-01). Do not bypass drift detection without re-calibrating thresholds.'"
  - "_meta field in drift_thresholds.json is stripped before passing to DriftDetector — only per-dim threshold floats forwarded (DriftDetector raises ValueError on unknown keys via missing-dims validation)"

duration: ~25 minutes (single session)
completed: 2026-05-16
status: complete
---

# Plan 18-04 Summary

**DriftDetector wired into evolve_prompt_sections.py step 8c constraint gate; metrics/drift_report emit on both joint and round-robin pipelines; D-BYPASS-01 regression guard verified.**

## Performance

- **Duration:** ~25 minutes
- **Started:** 2026-05-16
- **Completed:** 2026-05-16

## What Shipped

5 precise edits to `evolution/prompts/evolve_prompt_sections.py` plus one compatibility patch to `tests/prompts/test_evolve_prompt_sections_cli.py`:

| Edit | Location (post-edit) | Change |
|------|----------------------|--------|
| 1 | line 32 | `from evolution.prompts.drift_detector import DRIFT_DIMENSIONS, DriftDetector` |
| 2 | lines 493-666 | Step 8b kept; step 8c (drift gate, 3-run, Rich Table, severity ladder) inserted; step 8c → 8d renumber; FAILED path block extended with drift_* metrics + drift_report.txt + evolved_sections.json + diff.txt |
| 3 | lines 934-953 | drift_* metrics block at 4-space function-body indent, OUTSIDE joint conditional (D-OUT-02 + D-ROB-04) |
| 4 | lines 962-966 | Success-path drift_report.txt write parallel with diff.txt (D-OUT-03) |
| 5 | lines 115-145 (evolve signature) + lines 1023-1067 (Click option + main signature + evolve() call) | `--drift-thresholds-path` Click flag + threading through main()→evolve(); default `datasets/prompts/drift_thresholds.json` (git-tracked artifact from Plan 18-03); `type=click.Path(exists=True, path_type=Path)` |

### Insertion-point line ranges (before → after)

| Insertion point | Pre-edit lines | Post-edit lines | Delta |
|-----------------|----------------|------------------|-------|
| Import block | line 31 was `from ... PromptRoleChecker` | lines 31-32 (added line 32: `from ... DriftDetector`) | +1 |
| Step 8b → 8d region | lines 493-528 (8b role + 8c print + FAILED block, 36 lines) | lines 493-666 (8b role + 8c drift gate + 8d print + extended FAILED block, 174 lines) | +138 |
| Success metrics block | lines 786-793 (joint-only `if effective_mode == "joint"`) | lines 927-956 (joint-only block + new 4-space-indent `if drift_results:` block) | +28 |
| Success-path drift_report.txt | line 800 was last write (diff.txt) | lines 962-966 (new drift_report.txt write parallel with diff.txt) | +5 |
| --drift-thresholds-path Click option + signature | lines 116-124 (evolve signature) + lines 839-888 (Click + main + evolve call) | lines 115-125 (evolve signature with new param) + lines 1023-1067 (Click + main signature + evolve call) | +25 |

## D-BYPASS-01 grep evidence (decorator-pattern guard)

```
$ grep -nE '@click\.option\(\s*"--(no|skip)-drift-check"' evolution/prompts/evolve_prompt_sections.py | wc -l
0
```

The tightened decorator-pattern grep returns 0 — no `@click.option("--no-drift-check"` or `@click.option("--skip-drift-check"` exists anywhere in the file. The grep is decorator-anchored so help-text wording cannot defeat it (Wave 5 will lock this into a permanent regression test).

```
$ .venv/bin/python -m evolution.prompts.evolve_prompt_sections --no-drift-check 2>&1; echo "EXIT=$?"
Usage: python -m evolution.prompts.evolve_prompt_sections [OPTIONS]
Try 'python -m evolution.prompts.evolve_prompt_sections --help' for help.

Error: No such option: --no-drift-check
EXIT=2
```

Click rejects the flag at parse time, exit code 2.

## D-OUT-02 / D-ROB-04 fields present in metrics.json

Grep evidence for drift_* metric assignments:

```
$ grep -nE '"drift_(per_dim|thresholds|exceeded_dims|passed|max_section|max_dim)"' evolution/prompts/evolve_prompt_sections.py
641:            failed_metrics["drift_per_dim"] = drift_per_dim_metrics
642:            failed_metrics["drift_thresholds"] = drift_thresholds
643:            failed_metrics["drift_exceeded_dims"] = drift_exceeded_dims
640:            failed_metrics["drift_passed"] = drift_passed
938:        metrics["drift_per_dim"] = drift_per_dim_metrics
939:        metrics["drift_thresholds"] = drift_thresholds
940:        metrics["drift_exceeded_dims"] = drift_exceeded_dims
941:        metrics["drift_passed"] = drift_passed
952:        metrics["drift_max_section"] = max_entry[0]
953:        metrics["drift_max_dim"] = max_entry[1]
```

All 6 fields written on success path (line 937-953); 4 of 6 written on FAILED path (640-643 — `drift_max_*` only emit on success when `drift_exceeded_dims` is non-empty, since FAILED implies reject which means 2+ dims exceeded; this is handled by the `if drift_exceeded_dims:` guard).

## D-ROB-04 indent verification — drift block sits at 4-space function-body indent

Context window around Edit-3 (lines 927-941):

```python
    # Joint-mode-only A/B baseline fields (D-OUT-02 + W3 explicit A/B delta)
    if effective_mode == "joint" and roundrobin_baseline_score is not None:
        metrics["joint_score"] = evolved_score
        metrics["roundrobin_baseline_score"] = roundrobin_baseline_score
        metrics["epsilon_pp"] = EPSILON_PP
        metrics["joint_vs_roundrobin_delta_pp"] = joint_vs_roundrobin_delta_pp
        metrics["ab_elapsed_seconds"] = ab_elapsed
    # Phase 18 / D-OUT-02 + D-ROB-04: drift_* fields written UNCONDITIONALLY
    # for BOTH joint AND round-robin modes. This block sits at 4-space indent
    # (function-body level), OUTSIDE the joint-only `if` block above.
    if drift_results:
        metrics["drift_per_dim"] = drift_per_dim_metrics
        metrics["drift_thresholds"] = drift_thresholds
        metrics["drift_exceeded_dims"] = drift_exceeded_dims
        metrics["drift_passed"] = drift_passed
```

Line 928 (`if effective_mode == "joint"`) and line 937 (`if drift_results:`) both start at column 5 (4 leading spaces). The `if drift_results:` is at function-body level, NOT nested under the joint-only conditional. D-ROB-04 mechanically satisfied.

## CLI `--help` reflects the new flag and excludes bypass flags

```
$ .venv/bin/python -m evolution.prompts.evolve_prompt_sections --help 2>&1 | grep -A 5 -e 'drift\|no-drift\|skip-drift'
  --drift-thresholds-path PATH    Path to drift_thresholds.json (per-dim
                                  F1-optimized thresholds derived by `python
                                  -m
                                  evolution.prompts.build_drift_calibration`).
                                  Phase 18 D-BYPASS-02. There is no bypass
                                  flag (D-BYPASS-01). Do not bypass drift
                                  detection without re-calibrating thresholds.
```

`--drift-thresholds-path` present; no `--no-drift-check` or `--skip-drift-check` listed in `--help`.

## Test results

```
$ .venv/bin/pytest tests/prompts/ -q
110 passed, 1 skipped in 1.12s

$ .venv/bin/pytest tests/ -q
527 passed, 1 skipped, 1 xfailed, 5 warnings in 10.70s
```

Repo baseline 527 retained; tests/prompts/ baseline 110 retained. Zero regressions.

Wave 1 unit tests (drift_detector + drift_calibration) still all GREEN:

```
$ .venv/bin/pytest tests/prompts/test_drift_detector.py tests/prompts/test_drift_calibration.py -v
13 passed, 1 skipped in 0.10s
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking Issue] tests/prompts/test_evolve_prompt_sections_cli.py::TestABBaseline broke when DriftDetector + click.Path(exists=True) was introduced**

- **Found during:** Edit-5 verification (full pytest run after all 5 edits landed).
- **Issue:** Three existing tests (`test_joint_mode_runs_inline_ab_baseline`, `test_soft_gate_warns_but_does_not_block`, `test_round_robin_mode_skips_ab_baseline_and_extra_files`) chdir into `tmp_path` to sandbox `output/` writes. After Plan 18-04, the default `--drift-thresholds-path datasets/prompts/drift_thresholds.json` does not exist in tmp_path, so `click.Path(exists=True)` rejects the flag at parse time → exit code 2 → tests fail with `Invalid value for '--drift-thresholds-path'`.
- **Fix:** In the shared `_ab_patched_run` helper, before `runner.invoke`:
  1. Materialize a stub `tmp_path/datasets/prompts/drift_thresholds.json` containing the live Tier-2 threshold floats (so the test exercises real values, not synthetic ones).
  2. Patch `evolution.prompts.evolve_prompt_sections.DriftDetector` to a `MagicMock` whose `check_all` returns one pre-built drift dict per fake section with `severity="pass"`, `exceeded_count=0`, and a passing `ConstraintResult` — so step 8c runs but doesn't gate, and the test continues to assert on the A/B baseline behavior (the original test target).
- **Files modified:** `tests/prompts/test_evolve_prompt_sections_cli.py` (TestABBaseline._ab_patched_run helper — added ~47 lines).
- **Why Rule 3:** Direct blocker — the integration introduced a new required artifact that the sandboxed test workdir doesn't have. The fix is mechanical and preserves the original tests' assertions. The alternative (don't fix → leave 3 tests broken) would violate the plan's success criterion "All 110 tests in tests/prompts/ still pass".
- **Verification:** `pytest tests/prompts/test_evolve_prompt_sections_cli.py -q` returns 19 passed; full `tests/` suite returns 527 passed (matches Wave 1 baseline).

**Why not done in TestJointPipeline (lines 63-254):** TestJointPipeline runs in the project root cwd (no `chdir`), so the default `datasets/prompts/drift_thresholds.json` (git-tracked from Plan 18-03) is resolvable; `dspy.LM` is patched, DriftDetector's `__init__` succeeds, and `check_all` calls hit the mocked judge whose `MagicMock` outputs trigger DriftDetector's `try/except (ValidationError, ValueError, TypeError)` fallback → all dims become 0.0 → severity="pass" → step 8c passes silently. No test code change needed. This works by happy accident from Wave 1's typed-float fallback design; Wave 5 may want to add explicit mocks there too for robustness.

### Architectural changes

None — followed the plan's 5-edit recipe exactly with no surprises in the production code paths.

## Authentication Gates

None encountered. No live LLM calls, no API keys touched.

## Threat Flags

No new threat surface introduced. The plan's threat model items are unchanged:

- **T-18-02 (Tampering on drift_thresholds.json):** Mitigation in place via DriftDetector's `ValueError` on missing-dims (Wave 1 contract, unchanged).
- **T-18-05 (drift bypass via flag):** Mitigation in place — D-BYPASS-01 grep guard returns 0, D-BYPASS-02 flag exists with `click.Path(exists=True)`.
- **T-18-03 (drift_report.txt content disclosure):** Accepted risk — file lives under `output/prompts/` which is gitignored.

## Known Stubs

None. No stub code, no placeholder text, no UI components added.

## Files Touched

| File | Lines Changed | Purpose |
|------|---------------|---------|
| evolution/prompts/evolve_prompt_sections.py | +190 / -11 | 5 insertion points (Edit-1 through Edit-5) |
| tests/prompts/test_evolve_prompt_sections_cli.py | +47 / 0 | Compatibility patch for TestABBaseline._ab_patched_run (Rule-3 deviation) |

## Self-Check: PASSED

Verified items:

- [x] `evolution/prompts/evolve_prompt_sections.py` exists and imports cleanly (`.venv/bin/python -c "import evolution.prompts.evolve_prompt_sections"` → OK).
- [x] `evolve()` signature contains `drift_thresholds_path` parameter (inspect.signature → True).
- [x] `main.callback` signature contains `drift_thresholds_path` parameter (inspect.signature → True).
- [x] Grep `from evolution.prompts.drift_detector import` returns 1 match (line 32).
- [x] Grep `DriftDetector(config, drift_thresholds)` returns 1 match (line 515).
- [x] Grep `"drift_per_dim"` returns 2 matches (line 641 failed_metrics + line 938 success metrics).
- [x] Grep `drift_report\.txt` returns 5 matches (1 comment + 1 FAILED-path write + 1 success-path comment + 1 success-path write + 1 success comment string).
- [x] Grep `@click.option("--no-drift-check"` returns 0 matches (D-BYPASS-01).
- [x] Grep `@click.option("--skip-drift-check"` returns 0 matches (D-BYPASS-01).
- [x] Grep `^    if drift_results:` returns 2 matches (line 937 success metrics block + line 963 success drift_report.txt write — both at 4-space function-body indent).
- [x] `python -m evolution.prompts.evolve_prompt_sections --help` lists `--drift-thresholds-path`.
- [x] `python -m evolution.prompts.evolve_prompt_sections --no-drift-check` returns exit 2 with "No such option" error.
- [x] `pytest tests/prompts/` returns 110 passed (matches pre-plan baseline).
- [x] `pytest tests/` returns 527 passed, 1 skipped, 1 xfailed (matches pre-plan baseline).
- [x] `pytest tests/prompts/test_drift_detector.py tests/prompts/test_drift_calibration.py` returns 13 passed (Wave 1 sanity).
- [x] `.planning/phases/18-personality-drift-detection/18-04-SUMMARY.md` written.
