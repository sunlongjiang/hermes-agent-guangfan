---
phase: 15
slug: think-augmented-tool-selection
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-09
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from [15-RESEARCH.md §10 Validation Architecture](./15-RESEARCH.md).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest >=7.0` (pyproject.toml:27) |
| **Config file** | `pyproject.toml [tool.pytest.ini_options]` (pyproject.toml:41-43) — testpaths=["tests"], python_files=["test_*.py"] |
| **Quick run command** | `/Users/slj/项目/hermes-agent-self-evolution/.venv/bin/python -m pytest tests/tools/ -x --tb=short` |
| **Full suite command** | `/Users/slj/项目/hermes-agent-self-evolution/.venv/bin/python -m pytest tests/ -v` |
| **Estimated runtime** | ~15-25s (tests/tools/ subset); ~60-90s (full suite) |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/tools/ -x --tb=short`
- **After every plan wave:** Run `pytest tests/ -v` (ensure Phase 13/14 baseline stays green with +20-30 new tests)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Phase gate (additional):** `python -m evolution.tools.evolve_tool_reasoning --iterations 1 --dry-run` exits 0 with full dry-run schema echoed
- **Max feedback latency:** 25 seconds (quick run) / 90 seconds (full suite)

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| W1-enable-reasoning-ctor | TBD-01 | 1 | TOOL-V2-03 / SC-1 | — | `ToolModule(enable_reasoning=True)` 构造 reasoner | unit | `pytest tests/tools/test_tool_module.py::TestEnableReasoning::test_constructs_reasoner -x` | ❌ W0 | ⬜ pending |
| W1-disable-reasoning-ctor | TBD-01 | 1 | TOOL-V2-03 / SC-1 | — | `enable_reasoning=False` → reasoner absent/None | unit | `pytest tests/tools/test_tool_module.py::TestEnableReasoning::test_disabled_reasoner_absent -x` | ❌ W0 | ⬜ pending |
| W1-off-path-no-reasoner | TBD-01 | 1 | TOOL-V2-03 / SC-1 | — | think-off forward 不调 reasoner | unit (mock) | `pytest tests/tools/test_tool_module.py::TestEnableReasoning::test_off_path_no_reasoner_call -x` | ❌ W0 | ⬜ pending |
| W1-on-path-reasoner-first | TBD-01 | 1 | TOOL-V2-03 / SC-1 | — | think-on forward 先调 reasoner，selector 接收 reasoning | unit (mock) | `pytest tests/tools/test_tool_module.py::TestEnableReasoning::test_on_path_reasoner_first -x` | ❌ W0 | ⬜ pending |
| W1-reasoner-max-tokens | TBD-01 | 1 | D-04 | — | reasoner LM `max_tokens == 200` | unit | `pytest tests/tools/test_tool_module.py::TestEnableReasoning::test_reasoner_lm_max_tokens_200 -x` | ❌ W0 | ⬜ pending |
| W1-gepa-discovery | TBD-01 | 1 | TOOL-V2-03 / SC-2 | — | reasoner 出现在 `named_predictors()`（GEPA 可触达） | unit | `pytest tests/tools/test_tool_module.py::TestEnableReasoning::test_reasoner_in_named_predictors -x` | ❌ W0 | ⬜ pending |
| W2-ambiguous-filter | TBD-02 | 2 | D-13 | — | `len(ex.confuser_tools) >= 2` 正确过滤 | unit | `pytest tests/tools/test_think_metrics.py::TestAmbiguousFilter::test_filter_correct -x` | ❌ W0 | ⬜ pending |
| W2-full-regression-gate | TBD-02 | 2 | D-14 | — | think-on full ≥ think-off full - 2pp → passed | unit | `pytest tests/tools/test_think_metrics.py::TestThreeGate::test_full_regression_within -x` | ❌ W0 | ⬜ pending |
| W2-ambiguous-gate | TBD-02 | 2 | D-14 | — | ambiguous_on - ambiguous_off ≥ 3pp → passed | unit | `pytest tests/tools/test_think_metrics.py::TestThreeGate::test_ambiguous_improves -x` | ❌ W0 | ⬜ pending |
| W2-latency-gate | TBD-02 | 2 | D-14 | — | latency_p95 ≤ 5.0s → passed | unit | `pytest tests/tools/test_think_metrics.py::TestThreeGate::test_latency_within -x` | ❌ W0 | ⬜ pending |
| W2-three-and-logic | TBD-02 | 2 | D-14 | — | 三 AND：任一 fail → passed=False | unit (parametric) | `pytest tests/tools/test_think_metrics.py::TestThreeGate::test_three_and_logic -x` | ❌ W0 | ⬜ pending |
| W2-small-sample-skip | TBD-02 | 2 | D-16 | — | ambiguous_sample_size < 5 → skip ambiguous gate，不影响 passed | unit | `pytest tests/tools/test_think_metrics.py::TestThreeGate::test_small_sample_skip -x` | ❌ W0 | ⬜ pending |
| W2-function-api | TBD-02 | 2 | D-15 + §5.1 | — | `check_think_ab_gate()` 返回 ConstraintResult(details=sort_keys json) | unit | `pytest tests/tools/test_think_metrics.py::TestDualAPI::test_function_returns_constraint_result -x` | ❌ W0 | ⬜ pending |
| W2-class-api | TBD-02 | 2 | D-15 + §5.1 | — | `ThinkABGate.check()` 返回完整 metrics dict | unit | `pytest tests/tools/test_think_metrics.py::TestDualAPI::test_class_returns_dict -x` | ❌ W0 | ⬜ pending |
| W2-sampler-emits-stats | TBD-02 | 2 | D-17 | — | `sample_latency_tokens()` 返回 stats 含 p50 / p95 / mean | unit (mock module) | `pytest tests/tools/test_think_metrics.py::TestSampler::test_emits_p50_p95_mean -x` | ❌ W0 | ⬜ pending |
| W2-no-gepa-metric | TBD-02 | 2 | Pitfall 12 | — | think_metrics.py 不新增 GEPA-bound metric（守门） | unit | `pytest tests/tools/test_think_metrics.py::test_no_gepa_metric_added -x` | ❌ W0 | ⬜ pending |
| W3-cli-dry-run | TBD-03 | 3 | D-09 | — | `--dry-run` 退出 0，echo dry-run schema 全字段 | integration (mock LM) | `pytest tests/tools/test_evolve_tool_reasoning.py::test_dry_run_emits_setup -x` | ❌ W0 | ⬜ pending |
| W3-think-ab-failed-dir | TBD-03 | 3 | D-10 | — | ThinkABGate FAILED → FAILED_<ts>/ + exit 1 | integration (mock) | `pytest tests/tools/test_evolve_tool_reasoning.py::test_think_ab_failed_writes_failed_dir -x` | ❌ W0 | ⬜ pending |
| W3-v1-failed-think-on | TBD-03 | 3 | D-10 | — | V1BaselineGate (think-on) FAILED → FAILED_<ts>/ | integration (mock) | `pytest tests/tools/test_evolve_tool_reasoning.py::test_v1_failed_think_on_writes_failed_dir -x` | ❌ W0 | ⬜ pending |
| W3-metrics-json-schema | TBD-03 | 3 | D-11 | — | metrics.json 含 think_on_score / think_off_score / ambiguous_* / reasoning_token_stats / latency_stats / think_ab_gate | integration | `pytest tests/tools/test_evolve_tool_reasoning.py::test_metrics_json_schema -x` | ❌ W0 | ⬜ pending |
| W3-reasoning-prompt-files | TBD-03 | 3 | D-11 | — | reasoning_prompt.txt (evolved instructions) + diff.txt (unified diff) | integration | `pytest tests/tools/test_evolve_tool_reasoning.py::test_reasoning_prompt_files -x` | ❌ W0 | ⬜ pending |
| W3-ab-comparison-schema | TBD-03 | 3 | D-11 | — | ab_comparison.json 逐例含 task_id / selected_off / selected_on / is_ambiguous / reasoning_text_on / latency_seconds_* | integration | `pytest tests/tools/test_evolve_tool_reasoning.py::test_ab_comparison_schema -x` | ❌ W0 | ⬜ pending |
| W3-output-dir-isolated | TBD-03 | 3 | D-11 | — | output 落在 `output/tools_reasoning/<ts>/` 而非 `output/tools/` | integration | `pytest tests/tools/test_evolve_tool_reasoning.py::test_output_isolated_directory -x` | ❌ W0 | ⬜ pending |
| W3-cost-cap-aborts | TBD-03 | 3 | D-10 (cost) | Pitfall 4 | cost > max_cost_usd → ABORTED_<ts>/ + exit 2 | integration (mock + injected usage) | `pytest tests/tools/test_evolve_tool_reasoning.py::test_cost_cap_aborts -x` | ❌ W0 | ⬜ pending |
| W4-integration-smoke | TBD-04 | 4 | All SC | — | 真 dry-run + mock LM 100-example pipeline end-to-end | integration | `pytest tests/tools/test_evolve_tool_reasoning.py::test_e2e_mock_pipeline -x` | ❌ W0 | ⬜ pending |
| W0-ambiguous-size-check | TBD-00 | 0 | D-13 | — | `datasets/tools/holdout.jsonl` ambiguous 子集 echo 报告 | observation (non-gating) | `pytest tests/tools/test_dataset_ambiguous_size.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Plan ID column (TBD-XX) will be replaced with actual plan IDs by the planner agent.*

---

## Wave 0 Requirements

- [ ] `tests/tools/test_tool_module.py` — extend `TestEnableReasoning` class (6-7 new tests covering discovery / off-path / on-path / max_tokens / named_predictors / signature)
- [ ] `tests/tools/test_think_metrics.py` — **NEW** module (~15-20 tests covering three-gate / small-sample / dual API / sampler / no-GEPA-metric守门)
- [ ] `tests/tools/test_evolve_tool_reasoning.py` — **NEW** integration (~10-12 tests covering dry-run / dual gates / FAILED_ / ABORTED_ / metrics.json schema / ab_comparison.json schema / output dir isolation)
- [ ] `tests/tools/test_dataset_ambiguous_size.py` — **NEW** observation-only (echo real ambiguous subset size from `datasets/tools/holdout.jsonl`; non-gating but flags if < 5)
- [ ] `tests/tools/conftest.py` — add `mock_reasoning_module` fixture (construct `ToolModule(enable_reasoning=True)` with mock LM, return both pre-built baseline & evolved modules)

*(Test framework already in place from Phase 13/14 — no framework install needed.)*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real LLM E2E sanity run | All SC | Requires `OPENAI_API_KEY` / `OPENROUTER_API_KEY` + ~$2 budget; not a CI gate | Run `python -m evolution.tools.evolve_tool_reasoning --iterations 1 --max-cost-usd 2.0 --eval-source load`; inspect `output/tools_reasoning/<ts>/metrics.json` for: (a) full schema present, (b) think_ab_gate block present, (c) gate result reasonable (passed or specific-failed, not crashed). Phase-gate informational — the Nyquist-gated unit/integration tests are authoritative. |
| ambiguous subset size interpretation | D-13 / D-16 | Observation of real dataset — not a binary pass/fail | After Wave 0 `test_dataset_ambiguous_size.py` echoes N, operator decides: if N < 5, proceed anyway (D-16 small-sample skip applies) or regenerate dataset via `evolve_tool_params --eval-source synthetic --tools <subset>` to grow ambiguous slice |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 90s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
