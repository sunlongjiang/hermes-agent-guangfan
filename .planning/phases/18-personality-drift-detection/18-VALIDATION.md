---
phase: 18
slug: personality-drift-detection
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-15
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=7.0 (declared in `pyproject.toml`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (testpaths = ["tests"], python_files = ["test_*.py"]) |
| **Quick run command** | `.venv/bin/pytest tests/prompts/test_drift_detector.py tests/prompts/test_drift_calibration.py -xvs` |
| **Full suite command** | `.venv/bin/pytest tests/ -v` |
| **Estimated runtime** | quick ~5s · full ~60s |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/pytest tests/prompts/test_drift_detector.py tests/prompts/test_drift_calibration.py -xvs`
- **After every plan wave:** Run `.venv/bin/pytest tests/prompts/ -v`
- **Before `/gsd-verify-work`:** Full suite (`.venv/bin/pytest tests/ -v`) must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

> Concrete task IDs will be filled by the planner after PLAN.md generation. The rows below pre-allocate
> rows per RESEARCH §Validation Architecture table; planner updates Task ID + Plan + Wave columns.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | 0 | — | — | RED stubs exist | scaffold | `test -f tests/prompts/test_drift_detector.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | 0 | — | — | RED stubs exist | scaffold | `test -f tests/prompts/test_drift_calibration.py` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1+ | PMPT-V2-02 | — | DriftDetector returns 4-dim float scores | unit | `pytest tests/prompts/test_drift_detector.py::test_check_returns_4_dim_scores -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1+ | PMPT-V2-02 | — | 2+ dim exceeded → REJECT | unit | `pytest tests/prompts/test_drift_detector.py::test_severity_ladder_reject -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1+ | PMPT-V2-02 | — | 1 dim exceeded → warn but still passes | unit | `pytest tests/prompts/test_drift_detector.py::test_severity_ladder_warn -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1+ | PMPT-V2-02 | — | Drift report present in optimization output | integration | `pytest tests/prompts/test_drift_detector.py::test_drift_report_payload -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1+ | PMPT-V2-02 (RA1) | — | Typed float OutputField parses correctly | unit | `pytest tests/prompts/test_drift_detector.py::test_typed_float_parsing -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1+ | PMPT-V2-02 (RA1) | — | Parse failure falls back to 0.0 (NOT 0.5) | unit | `pytest tests/prompts/test_drift_detector.py::test_parse_failure_fallback_zero -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1+ | PMPT-V2-02 (RA2) | — | `temperature=0.7` is passed to `dspy.LM` | unit | `pytest tests/prompts/test_drift_detector.py::test_lm_constructed_with_temperature -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1+ | PMPT-V2-02 (RA2) | — | 3-run averaging yields non-zero stdev when LM stochastic | unit | `pytest tests/prompts/test_drift_detector.py::test_three_run_stdev_nonzero -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1+ | PMPT-V2-02 (RA2) | — | `mean - 1·stdev > threshold` is the decision rule | unit | `pytest tests/prompts/test_drift_detector.py::test_conservative_decision_rule -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1+ | PMPT-V2-02 (RA3) | — | F1 derivation finds optimal threshold per dim | unit | `pytest tests/prompts/test_drift_calibration.py::test_derive_thresholds_f1_optimal -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1+ | PMPT-V2-02 (RA3) | — | F1 derivation uses pure stdlib (no sklearn import) | unit | `pytest tests/prompts/test_drift_calibration.py::test_no_sklearn_dependency -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1+ | PMPT-V2-02 (RA5) | — | DriftCalibrationBuilder uses `judge_model` (not `eval_model`) | unit | `pytest tests/prompts/test_drift_calibration.py::test_generator_uses_judge_model -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | verify | PMPT-V2-02 (RA6) | — | F1 ≥ 0.85 on calibration self-eval (live LLM gated) | integration | `RUN_LIVE_LLM=1 pytest tests/prompts/test_drift_calibration.py::test_f1_target_self_eval -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1+ | PMPT-V2-02 | — | metrics.json contains `drift_per_dim`, `drift_thresholds`, `drift_passed` | integration | `pytest tests/prompts/test_evolve_prompt_sections_cli.py::test_metrics_json_has_drift_fields -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1+ | PMPT-V2-02 | — | `--drift-thresholds-path` flag accepted, default resolved | unit | `pytest tests/prompts/test_evolve_prompt_sections_cli.py::test_drift_thresholds_path_flag -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | 1+ | PMPT-V2-02 (D-BYPASS-01) | — | Bypass flag is **absent** (regression guard) | unit | `pytest tests/prompts/test_evolve_prompt_sections_cli.py::test_no_skip_drift_flag -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/prompts/test_drift_detector.py` — RED stubs for 9 unit scenarios (typed parsing, fallback, temperature wiring, 3-run stdev, conservative rule, severity ladder warn/reject, drift report payload, 4-dim scores)
- [ ] `tests/prompts/test_drift_calibration.py` — RED stubs for 4 scenarios (F1 derivation optimum, stdlib-only path, judge_model wiring, live-gated F1 ≥ 0.85)
- [ ] `tests/prompts/test_evolve_prompt_sections_cli.py` — extend with 3 new tests (metrics.json drift fields, `--drift-thresholds-path` flag, regression guard for `--no-drift-check` absence)
- [ ] `tests/prompts/conftest.py` — add `mock_drift_lm` fixture + `dummy_thresholds` fixture (placeholder `{tone: 0.55, formality: 0.50, vocabulary: 0.45, persona: 0.65}` per D-CAL-01)
- [ ] `tests/prompts/fixtures/drift_calibration_mini.jsonl` — 6-example mini set (1 section × 6 variants) for offline `derive_thresholds` tests
- [ ] `.gitignore` exception: append `!datasets/prompts/drift_calibration.jsonl` and `!datasets/prompts/drift_thresholds.json` (D-CAL-02)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Spot-check 10/30 calibration examples for plausibility (synthetic-bias mitigation, RA5) | PMPT-V2-02 | Synthetic LLM generator + LLM judge = same-model bias risk; humans must sanity-check labels | After `python -m evolution.prompts.build_drift_calibration` (or chosen CLI), open `datasets/prompts/drift_calibration.jsonl`, sample 10 rows; verify `is_drift` labels match human reading of `original_text` vs `variant_text`; if ≥ 2 of 10 are mislabeled, regenerate with different seed |
| Visual review of `drift_report.txt` after first live evolve run | PMPT-V2-02 | Rich Table layout + explanation text quality is subjective | Run `python -m evolution.prompts.evolve_prompt_sections` (or current entry), open `output/prompts/<ts>/drift_report.txt`, confirm per-section × per-dim layout, decision lines, and explanation readable |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (drift_detector.py, drift_calibration.py, conftest fixtures, mini fixture JSONL, gitignore exception)
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s on quick run
- [ ] `nyquist_compliant: true` set in frontmatter after Wave 0 lands

**Approval:** pending
