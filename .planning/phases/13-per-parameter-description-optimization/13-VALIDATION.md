---
phase: 13
slug: per-parameter-description-optimization
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-07
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `.planning/phases/13-per-parameter-description-optimization/13-RESEARCH.md` §Validation Architecture.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (configured in `pyproject.toml [tool.pytest.ini_options]`) |
| **Config file** | `pyproject.toml` (no separate pytest.ini) |
| **Quick run command** | `pytest tests/tools/ -x --tb=short` |
| **Full suite command** | `pytest tests/ -x` |
| **Estimated runtime** | Quick: ~5s (unit); Full: ~30s (unit + integration w/o live LLM) |

Live-LLM integration tests (baseline hard-gate, ParamConsistencyChecker contract) are marked `@pytest.mark.live` and excluded from the default suite. Invoke explicitly: `pytest tests/ -m live`.

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/tools/ -x --tb=short`
- **After every plan wave:** Run `pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green, plus one `pytest -m live` dry-run of baseline hard-gate
- **Max feedback latency:** 30 seconds (quick); 120 seconds (full excluding live)

---

## Per-Task Verification Map

> Row populated during planning. Rows below seed the 17 tests identified in RESEARCH.md §Validation Architecture so gsd-planner can map tasks → tests.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 13-02.T1 | 01 | 1 | TOOL-V2-02 | — | ToolModule.named_parameters() discovers per-param Predicts (sub-Module pattern from RESEARCH §1) | unit | `pytest tests/tools/test_tool_module_per_param.py::test_named_parameters_discovery` | ❌ W0 | ⬜ pending |
| 13-02.T1 | 01 | 1 | TOOL-V2-02 | — | Tool-level description stays frozen — never appears in named_parameters() | unit | `pytest tests/tools/test_tool_module_per_param.py::test_tool_description_frozen` | ❌ W0 | ⬜ pending |
| 13-02.T1 | 01 | 1 | TOOL-V2-02 | — | Empty param description registered as Predict (GEPA generates from zero) | unit | `pytest tests/tools/test_tool_module_per_param.py::test_empty_param_registered` | ❌ W0 | ⬜ pending |
| 13-02.T1 | 02 | 1 | TOOL-V2-02 | — | `ToolSelectionWithParamsSignature` returns JSON-parseable selected_params | unit | `pytest tests/tools/test_tool_selection_with_params.py::test_selected_params_json_shape` | ❌ W0 | ⬜ pending |
| 13-03.T1 | 03 | 2 | TOOL-V2-02 | — | `joint_tool_param_metric` = 0.5*tool + 0.5*param exact-match | unit | `pytest tests/tools/test_joint_metric.py::test_exact_match_cases` | ❌ W0 | ⬜ pending |
| 13-03.T1 | 03 | 2 | TOOL-V2-02 | — | joint_tool_param_metric has full 5-param DSPy 3.x signature (gepa.py:368 contract) | unit | `pytest tests/tools/test_joint_metric.py::test_5_param_signature` | ❌ W0 | ⬜ pending |
| 13-03.T1 | 03 | 2 | TOOL-V2-02 | — | JSON parse failure → param_match=0.0 (no crash) | unit | `pytest tests/tools/test_joint_metric.py::test_json_decode_error_handling` | ❌ W0 | ⬜ pending |
| 13-03.T1 | 03 | 2 | TOOL-V2-02 | — | `joint_tool_param_metric_with_feedback` returns ScoreWithFeedback for GEPA reflection | unit | `pytest tests/tools/test_joint_metric.py::test_feedback_metric_shape` | ❌ W0 | ⬜ pending |
| 13-04.T1 | 04 | 2 | TOOL-V2-02 | — | ParamConsistencyChecker flags frozen↔evolved naming/required/semantic conflicts | unit | `pytest tests/tools/test_param_consistency.py::test_detects_conflicts` | ❌ W0 | ⬜ pending |
| 13-04.T1 | 04 | 2 | TOOL-V2-02 | — | ParamConsistencyChecker retry-with-defaults on malformed LLM JSON | unit | `pytest tests/tools/test_param_consistency.py::test_malformed_json_fallback` | ❌ W0 | ⬜ pending |
| 13-04.T1 | 04 | 2 | TOOL-V2-02 | — | One failing param rejects the whole tool variant | unit | `pytest tests/tools/test_param_consistency.py::test_whole_tool_rejection` | ❌ W0 | ⬜ pending |
| 13-05.T2 | 05 | 2 | TOOL-V2-02 | — | cost_tracker accumulates litellm.cost_per_token across LM calls | unit | `pytest tests/core/test_cost_tracker.py::test_accumulation` | ❌ W0 | ⬜ pending |
| 13-05.T2 | 05 | 2 | TOOL-V2-02 | — | cost_tracker aborts when cost_usd_spent > max_cost_usd | unit | `pytest tests/core/test_cost_tracker.py::test_abort_threshold` | ❌ W0 | ⬜ pending |
| 13-05.T2 | 05 | 2 | TOOL-V2-02 | — | ABORTED_<ts>/aborted.json schema (final_cost_usd, evaluated_candidates, partial_diff) | unit | `pytest tests/core/test_cost_tracker.py::test_aborted_json_schema` | ❌ W0 | ⬜ pending |
| 13-06.T1 | 06 | 3 | TOOL-V2-02 | — | CrossToolRegressionChecker persists per_tool_baseline_rates + per_tool_evolved_rates in metrics.json | unit | `pytest tests/tools/test_cross_tool_regression.py::test_per_tool_persistence` | ❌ W0 | ⬜ pending |
| 13-07.T1 | 07 | 3 | TOOL-V2-02 | — | v1 baseline hard-gate: per-param evolved holdout < baseline − 0.02 → FAIL | unit | `pytest tests/tools/test_v1_baseline_gate.py::test_regression_fails_run` | ❌ W0 | ⬜ pending |
| 13-07.T1 | 07 | 3 | TOOL-V2-02 | — | Fallback: missing --baseline-run → inline Phase 5 baseline computation | unit | `pytest tests/tools/test_v1_baseline_gate.py::test_inline_baseline_fallback` | ❌ W0 | ⬜ pending |
| 13-08.T1 | 08 | 4 | TOOL-V2-02 | — | evolve_tool_params default GEPA fail → raise (no silent MIPROv2); `--allow-miprov2-fallback` opt-in; metrics.json has `optimizer_used` | unit | `pytest tests/tools/test_evolve_tool_params_cli.py::test_loud_gepa_failure_and_opt_in` | ❌ W0 | ⬜ pending |
| 13-01.T-SIZE-RED | 01 | 0 | TOOL-V2-02 | — | Param size gate rejects 201-char description (B3 SC3 coverage) | unit | `pytest tests/tools/test_param_size_gate.py::test_param_desc_201_chars_rejected` | ❌ W0 | ⬜ pending |
| 13-01.T-SIZE-RED | 01 | 0 | TOOL-V2-02 | — | Param size gate accepts exactly 200-char description | unit | `pytest tests/tools/test_param_size_gate.py::test_param_desc_200_chars_accepted` | ❌ W0 | ⬜ pending |
| 13-08.T1 | 08 | 4 | TOOL-V2-02 | — | evolve_tool_params wires `_check_size('param_description')` into constraint chain (B3 SC3 wire-through) | integration | `grep -nE "_check_size\(\s*[^,]+,\s*['\"]param_description['\"]" evolution/tools/evolve_tool_params.py` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/tools/test_tool_module_per_param.py` — stubs for TOOL-V2-02 (ToolModule per-param expansion)
- [ ] `tests/tools/test_tool_selection_with_params.py` — `ToolSelectionWithParamsSignature` contract
- [ ] `tests/tools/test_joint_metric.py` — joint + feedback metrics
- [ ] `tests/tools/test_param_consistency.py` — ParamConsistencyChecker contract
- [ ] `tests/core/test_cost_tracker.py` — cost accumulation + abort behaviour
- [ ] `tests/tools/test_cross_tool_regression.py` — per-tool rates persistence
- [ ] `tests/tools/test_v1_baseline_gate.py` — v1 baseline hard-gate + inline fallback
- [ ] `tests/tools/test_evolve_tool_params_cli.py` — loud-fail GEPA + `--allow-miprov2-fallback` + `optimizer_used` + W2 `--param-group-size` noop warning
- [ ] `tests/tools/test_param_size_gate.py` — **B3 new file:** SC3 200-char per-param size gate via `ConstraintValidator._check_size(text, 'param_description')` (2 tests: 201-reject + 200-accept)
- [ ] `tests/conftest.py` — extend with `mock_lm_with_usage` fixture (feeds `Prediction.usage` for cost_tracker unit tests)

*pytest + pytest-asyncio already installed; no framework install needed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| GEPA 在 ~150 predictor fan-out 下的 reflection_lm 实际成本与质量 | TOOL-V2-02 | 依赖真实 LLM + 完整 holdout，运行 >10 min + 真实费用 | 跑 `python -m evolution.tools.evolve_tool_params --dry-run` 检查 discovered param 数；跑 `--max-cost-usd 5` 小预算 smoke test，确认 cost_tracker 触发 abort 并写 ABORTED_<ts>/ |
| ParamConsistencyChecker 对 hermes-agent 真实工具的实际拒绝率 | TOOL-V2-02 | 真实工具描述 + 真实 LLM；实测会否卡死合理变体 | 在一次 smoke 运行后 `cat metrics.json \| jq .param_consistency_failures`，人工抽样 3 次 fail 看是否确实是冲突 |
| v1 baseline 硬门在干净仓库（无 Phase 5 output）下的 fallback 行为 | TOOL-V2-02 | 需要真实 hermes-agent repo + 完整 Phase 5 pipeline | 在一个没跑过 Phase 5 的目录跑 `python -m evolution.tools.evolve_tool_params`，确认自动 inline 计算 baseline 且写入 metrics.json |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (9 test files + conftest fixture)
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s (quick) / 120s (full)
- [ ] `nyquist_compliant: true` set in frontmatter after planner fills in Task IDs

**Approval:** planner-assigned task IDs 2026-05-07 (execute-phase will validate)
