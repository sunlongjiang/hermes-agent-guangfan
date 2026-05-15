---
phase: 17
slug: joint-section-optimization
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-15
---

# Phase 17 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (configured in `pyproject.toml [tool.pytest.ini_options]`) |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/pytest tests/prompts/test_prompt_module.py tests/prompts/test_evolve_prompt_sections_cli.py -x` |
| **Full suite command** | `.venv/bin/pytest tests/ -x` |
| **Estimated runtime** | ~10s quick / ~60s full (no LM calls — fake GEPA fixture) |

---

## Sampling Rate

- **After every task commit:** Run quick command
- **After every plan wave:** Run full suite command
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD by planner | TBD | TBD | PMPT-V2-01 | — | N/A | unit / integration | TBD | ❌ W0 | ⬜ pending |

*Planner fills this map from PLAN.md tasks after planning completes.*
*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/prompts/test_prompt_module.py` — extend with joint mode visibility tests (existing file, +N tests; preserve 14 existing)
- [ ] `tests/prompts/test_evolve_prompt_sections_cli.py` — new file for `--mode joint|round-robin` CLI integration tests with fake GEPA mock
- [ ] No new framework install needed — pytest configured

---

## Success Criteria → Test Mapping

| Phase 17 Success Criterion (ROADMAP) | Validating Artifact | Pass Condition |
|--------------------------------------|---------------------|----------------|
| PromptModule supports all-sections-active mode (all Predicts discoverable) | `tests/prompts/test_prompt_module.py::test_joint_mode_exposes_all_predictors` | `len(list(module.section_predictors.items())) == 13` after `set_joint_mode(True)`; all entries are `dspy.Predict` instances; `module.predictors()` returns 14 entries (13 sections + selector, selector frozen) |
| GEPA can mutate multiple sections in one pass | `tests/prompts/test_evolve_prompt_sections_cli.py::test_joint_mode_gepa_multi_param` | With fake GEPA mock that records compile() invocations, joint mode triggers exactly 1 `optimizer.compile()` call (vs round-robin's 13); `component_selector="all"` is passed |
| Joint optimization produces equal or better scores than round-robin on holdout | `tests/prompts/test_evolve_prompt_sections_cli.py::test_ab_baseline_soft_gate` | metrics.json contains `joint_score`, `roundrobin_baseline_score`, `epsilon_pp`; soft-gate warning emitted only when `joint_score < roundrobin_score - 0.01`; both modes write evolved_sections; no exit-2 in either branch |

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real end-to-end LM-driven joint optimization produces improvement on holdout | PMPT-V2-01 Success Criterion 3 | LM-as-judge variance + real GEPA reflection requires actual API budget; cannot mock | Run `python -m evolution.prompts.evolve_prompt_sections --iterations 5 --mode joint`, inspect `output/prompts/<ts>/metrics.json` for `improvement > 0` and `joint_score >= roundrobin_baseline_score - 0.01` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
