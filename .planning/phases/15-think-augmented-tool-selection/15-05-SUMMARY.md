---
phase: 15-think-augmented-tool-selection
plan: "05"
subsystem: tools
tags:
  - think-augmented-tool-selection
  - test-e2e-mock-pipeline
  - wave-4-smoke
  - to-dspy-examples-fix
  - confuser-tools
dependency_graph:
  requires:
    - "15-01"  # Wave 0 RED test scaffold (test_evolve_tool_reasoning.py)
    - "15-02"  # ToolModule enable_reasoning refactor
    - "15-03"  # ThinkABGate + sample_latency_tokens
    - "15-04"  # evolve_tool_reasoning.py CLI
  provides:
    - "test_e2e_mock_pipeline GREEN (11/11 tests in test_evolve_tool_reasoning.py)"
    - "to_dspy_examples() includes confuser_tools + correct_params (Rule 1 fix)"
    - "ambiguous_subset_size consistent: dry-run=75 / test_dataset_ambiguous_size=75"
  affects:
    - Phase 15 /gsd-verify-phase 15 (nyquist gate sign-off pending Task 3-4)
tech_stack:
  added: []
  patterns:
    - "Wave 4 smoke: patch external seams (LM/GEPA/forward), let real gates/writers run"
    - "Rule 1 fix: to_dspy_examples() must carry all fields needed by downstream metric + filter"
key_files:
  created: []
  modified:
    - path: tests/tools/test_evolve_tool_reasoning.py
      description: "Replace @pytest.mark.skip stub with full test_e2e_mock_pipeline (131 lines)"
    - path: evolution/tools/tool_dataset.py
      description: "to_dspy_examples() now includes correct_params + confuser_tools (Rule 1 bug fix)"
key-decisions:
  - "情形 C: evolution/tools/__init__.py 只含 docstring，无 from X import Y 模式 — 不追加 Phase 15 public symbols（与 Phase 13 只有 docstring 的状态一致）"
  - "Rule 1 Bug: to_dspy_examples() 缺少 confuser_tools 和 correct_params，导致 Phase 15 pipeline 中 ambiguous_subset_size=0；修复后两处观察均为 75"
  - "test_e2e_mock_pipeline: patch ToolModule.forward 而非内部 LM 调用，使 V1BaselineGate/ThinkABGate/_build_ab_comparison 走真实代码路径"
requirements-completed:
  - TOOL-V2-03
duration: ~20min
completed: 2026-05-11
---

# Phase 15 Plan 05: Wave 4 收尾 Summary

**test_e2e_mock_pipeline GREEN（11/11 Phase 15 集成测试）+ to_dspy_examples() confuser_tools 修复使 dry-run ambiguous_subset_size=75 与 test_dataset_ambiguous_size 一致**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-05-11T00:00:00Z
- **Completed:** 2026-05-11
- **Tasks:** 2/4 auto 完成（Task 3 = checkpoint:human-verify 等待确认，Task 4 待 Task 3 通过后执行）
- **Files modified:** 2

## Accomplishments

- Task 1: `test_e2e_mock_pipeline` stub (Plan 01 创建 + @pytest.mark.skip) 替换为完整 Wave 4 端到端 smoke，走真实 V1BaselineGate / ThinkABGate / _build_ab_comparison / _write_* 代码路径
- Task 2: 情形 C — `evolution/tools/__init__.py` 只含 docstring，遵循 Phase 13 惯例不追加 Phase 15 public symbols
- Rule 1 Bug: `to_dspy_examples()` 缺少 `confuser_tools` + `correct_params` → 修复后 dry-run ambiguous_subset_size=75，与 test_dataset_ambiguous_size 一致

## Task Commits

1. **Task 1: GREEN test_e2e_mock_pipeline** — `b480fb5` (test)
2. **Rule 1 Bug: to_dspy_examples() fix** — `621e1c1` (fix)
3. Task 2: 情形 C，无文件变更，无提交
4. Task 3: CHECKPOINT — 等待用户确认 dry-run 结果
5. Task 4: PENDING — VALIDATION.md frontmatter 更新（在 Task 3 批准后执行）

## Files Created/Modified

- `tests/tools/test_evolve_tool_reasoning.py` — 替换 `test_e2e_mock_pipeline` stub 为完整实现（+131 行），移除 `@pytest.mark.skip`，11/11 GREEN
- `evolution/tools/tool_dataset.py` — `to_dspy_examples()` 增加 `correct_params` 和 `confuser_tools` 字段（Rule 1 bug fix）

## Decisions Made

- **evolution/tools/__init__.py 情形 C（skip）**: 文件只含 `"""Phase placeholder: tools evolution."""`，无 `from X import Y` 模式，不追加 Phase 15 public symbols。`ThinkABGate` 等符号通过完整模块路径 `from evolution.tools.think_metrics import ThinkABGate` 始终可 import。
- **test_e2e_mock_pipeline patch 策略**: patch 外部 seams（`dspy.LM`, `dspy.GEPA`, `ToolModule.forward`, `_load_tool_descriptions`, `_load_dataset`）让真实门控走真实代码路径；不 patch V1BaselineGate / ThinkABGate / sample_latency_tokens / _build_ab_comparison / _write_*。

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] to_dspy_examples() 未包含 confuser_tools 和 correct_params**
- **Found during:** Task 3 dry-run 验证（pre-checkpoint）
- **Issue:** `to_dspy_examples()` 只包含 `task_description` + `correct_tool`，导致：
  1. `correct_params` 缺失 — `joint_tool_param_metric()` 评分 param_match 对比空 `{}`，偏高
  2. `confuser_tools` 缺失 — Phase 15 的 `ambiguous_subset = [ex for ex in holdout if len(ex.confuser_tools) >= 2]` 始终为空列表，dry-run 报告 `ambiguous_subset_size=0`（真实数据集中有 75 个 ambiguous examples）
- **Fix:** `to_dspy_examples()` 增加 `correct_params=ex.correct_params` 和 `confuser_tools=ex.confuser_tools`
- **Files modified:** `evolution/tools/tool_dataset.py`
- **Verification:** dry-run 现报告 `ambiguous_subset_size=75`；`test_dataset_ambiguous_size` 报告 `ambiguous_subset_size=75`（两者一致）；465 全套测试 GREEN
- **Committed in:** `621e1c1`

---

**Total deviations:** 1 auto-fixed (Rule 1 Bug)
**Impact on plan:** 必要修复 — 没有此修复，Phase 15 的 ambiguous 子集门（D-13 / D-16）在所有真实数据集场景下永远为 0，使 ThinkABGate 的核心价值（改善 confusable 工具选择）无法被正确度量。

## Checkpoint Status

**Task 3: 等待用户批准**

Agent 已代表用户执行 dry-run 并完成验证：

```
$ HERMES_AGENT_REPO=/Users/slj/.hermes/hermes-agent \
  .venv/bin/python -m evolution.tools.evolve_tool_reasoning --iterations 1 --dry-run

param_predictors_discovered=114
tools_in_scope=47
holdout_size=81
ambiguous_subset_size=75
ambiguous_gate_skipped=false
reasoning_tokens_cap=200
latency_p95_budget_sec=5.0
ab_tolerance_pp=2.0
ambiguous_improvement_pp=3.0
full_regression_tolerance_pp=2.0
iterations_planned=1
eval_source=load
max_cost_usd_cap=20.0
max_metric_calls_estimate=342
DRY RUN — setup validated.
exit=0
```

Cross-validation:
```
$ .venv/bin/python -m pytest tests/tools/test_dataset_ambiguous_size.py -v -s
[Phase 15 dataset observation] holdout_total=81 ambiguous_subset_size=75
1 passed
```

两处观察 ambiguous_subset_size=75 一致。所有 D-12 字段均存在。

**用户需要做的事情：**
1. 运行 dry-run（已由 agent 运行，结果如上）确认 OK
2. 回复 "approved" 使 continuation agent 执行 Task 4（VALIDATION.md frontmatter 更新）

## Known Stubs

无 — test_e2e_mock_pipeline 是真实 smoke，不是 stub。

## Threat Surface Scan

无新增网络端点或认证路径。`to_dspy_examples()` 修改是纯内存对象构造变更，不涉及文件 I/O 或网络调用。T-15-05-01（monkeypatch.chdir 隔离）已在 test_e2e_mock_pipeline 中正确实现。

## Self-Check: PARTIAL (awaiting Task 3 checkpoint approval + Task 4 execution)

- [x] `tests/tools/test_evolve_tool_reasoning.py` 存在（11/11 GREEN）
- [x] `evolution/tools/tool_dataset.py` confuser_tools fix 已提交（`621e1c1`）
- [x] 提交 `b480fb5` (test) 和 `621e1c1` (fix) 存在
- [x] 465 全套测试 GREEN，零退化
- [ ] VALIDATION.md frontmatter 更新（Task 4，pending Task 3 approval）
- [ ] `nyquist_compliant: true` / `wave_0_complete: true` / `status: approved`（Task 4 后）
