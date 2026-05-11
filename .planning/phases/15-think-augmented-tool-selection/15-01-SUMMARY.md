---
phase: 15
plan: "01"
subsystem: tools
tags: [tdd, wave-0, red-scaffold, test-fixtures, think-augmented, ambiguous-subset]
dependency_graph:
  requires: []
  provides:
    - tests/tools/conftest.py (fake_tools + mock_reasoning_module fixtures)
    - tests/tools/test_think_metrics.py (Wave 2 RED contract: 21 tests)
    - tests/tools/test_evolve_tool_reasoning.py (Wave 3 RED contract: 11 tests)
    - tests/tools/test_dataset_ambiguous_size.py (observation script)
  affects:
    - Wave 1: conftest.py enable_reasoning kwarg contract
    - Wave 2: think_metrics.py GREEN-fill target (21 tests)
    - Wave 3: evolve_tool_reasoning.py GREEN-fill target (11 tests)
tech_stack:
  added: []
  patterns:
    - pytest.importorskip guard for optional-dependency test skipping
    - Click CliRunner + patch seams for integration test isolation
    - Wave 0 RED-first TDD scaffold pattern
key_files:
  created:
    - tests/tools/conftest.py
    - tests/tools/test_think_metrics.py
    - tests/tools/test_evolve_tool_reasoning.py
    - tests/tools/test_dataset_ambiguous_size.py
  modified: []
decisions:
  - "TestAmbiguousFilter placed in test_think_metrics.py rather than a separate file; D-13 filter logic is pure Python (no module dep), so it turns GREEN immediately in Wave 0"
  - "pytest.importorskip used for evolve_tool_reasoning tests so they skip cleanly vs crashing pytest collection when Wave 3 module is absent"
  - "conftest.py mock_reasoning_module fixture intentionally RED until Wave 1 adds enable_reasoning kwarg — documented explicitly in fixture docstring"
metrics:
  duration_seconds: 954
  completed_date: "2026-05-11"
  tasks_completed: 4
  files_created: 4
---

# Phase 15 Plan 01: Wave 0 Test Scaffold Summary

Wave 0 RED 测试脚手架建立完成，为 Phase 15 的 Wave 1-4 TDD GREEN-fill 提供完整接收容器。

## What Was Built

Wave 0 新建 4 个测试文件（共 817 行），覆盖 Phase 15 全部新模块的行为契约：

| 文件 | LOC | 测试函数数 | 角色 |
|------|-----|-----------|------|
| `tests/tools/conftest.py` | 66 | 2 fixtures | Phase 15 共享 fixture 容器 |
| `tests/tools/test_think_metrics.py` | 309 | 21 tests | Wave 2 RED 单测骨架 |
| `tests/tools/test_evolve_tool_reasoning.py` | 388 | 11 tests | Wave 3 RED 集成测试骨架 |
| `tests/tools/test_dataset_ambiguous_size.py` | 54 | 1 test | Wave 0 数据集观察脚本 |

## 数据集观察结果

`datasets/tools/holdout.jsonl` 在当前 checkout 中**不存在**（clean repo）。

- `test_dataset_ambiguous_size.py` 正确 SKIP（无崩溃）
- D-16 触发情况：**未知**，需在实际 holdout 数据就绪后运行观察
- 结论：Wave 1-4 实现期间需先构建 holdout 数据集；若 ambiguous 子集 `< 5`，ThinkABGate 将在运行时跳过 ambiguous 门（D-16 小样本保护激活）

## Wave 0 RED 状态确认

| 测试文件 | RED 机制 | 预期变为 GREEN 的 Wave |
|---------|---------|---------------------|
| `test_think_metrics.py` | `from evolution.tools.think_metrics import ThinkABGate` → `ModuleNotFoundError` | Wave 2 |
| `test_evolve_tool_reasoning.py` | `pytest.importorskip("evolution.tools.evolve_tool_reasoning")` → skip | Wave 3/4 |
| `conftest.py mock_reasoning_module` | `ToolModule(fake_tools, enable_reasoning=True)` → `TypeError` (kwarg 不存在) | Wave 1 |
| `test_dataset_ambiguous_size.py` | `pytest.skip` (holdout.jsonl 缺失) | 数据就绪后 |

**TestAmbiguousFilter 例外**：该测试类只测 Python 列表操作（`len(ex.confuser_tools) >= 2`），不依赖任何待实现模块，Wave 0 立即 GREEN（1 passed）。

## 现有测试套件回归结果

运行 `pytest tests/ --ignore=tests/tools/test_think_metrics.py --ignore=tests/tools/test_evolve_tool_reasoning.py`：

**425 passed, 1 skipped, 1 xfailed** — 基线完全无退化。

## Wave 2 GREEN 目标（test_think_metrics.py 21 个测试）

Wave 2 完成 `evolution/tools/think_metrics.py` 后需逐一 GREEN：

- `TestAmbiguousFilter`（1）: confuser_tools >= 2 过滤 ← 已 GREEN
- `TestThreeGate`（9）: 全集不回归 / ambiguous +3pp / latency p95 ≤5s / 8行真值表 / D-16 skip
- `TestDualAPI`（2）: `check_think_ab_gate` 返回 ConstraintResult / `ThinkABGate.check` 返回 dict
- `TestSampler`（2）: p50/p95/mean stats + 失败跳过不中断
- `TestGuard`（1）: Pitfall-12 — think_metrics 不新增 GEPA 5-param metric

## Wave 3 GREEN 目标（test_evolve_tool_reasoning.py 10 个测试）

Wave 3 完成 `evolution/tools/evolve_tool_reasoning.py` 后需逐一 GREEN：

- dry-run 输出 Phase 15 schema 字段
- 两个 ToolModule 构造（enable_reasoning=False/True）
- V1BaselineGate 调用 2 次
- ThinkABGate 失败 → `FAILED_<ts>/` + exit 1
- v1 门 think-on 失败 → `FAILED_<ts>/`
- `metrics.json` 完整 schema（12 个必须 key）
- `reasoning_prompt.txt` + `diff.txt` 存在
- `ab_comparison.json` 完整 per-example schema（13 个字段）
- 输出目录物理隔离（不写 output/tools/）
- CostBudgetExceeded → `ABORTED_<ts>/aborted.json` + exit 2

## Deviations from Plan

None — 计划按原样执行。

### Wave 0 注意事项

`mock_reasoning_module` fixture（conftest.py）在 Wave 0 运行时会 TypeError（`ToolModule.__init__` 不接受 `enable_reasoning` kwarg，Wave 1 尚未实现）。这是**预期 RED 状态**，已在 fixture docstring 中明确记录。Wave 2/3 测试不直接使用该 fixture；它是 Wave 1 完成后的接收容器。

## Known Stubs

无 stubs — Wave 0 计划只创建测试文件，不实现任何生产代码。

## Threat Flags

无新增安全相关 surface — 仅新建测试文件，所有 LM 调用均通过 MagicMock 屏蔽（满足 T-15-01-03 mitigate 要求）。

## Self-Check: PASSED

Files exist:
- tests/tools/conftest.py: FOUND
- tests/tools/test_think_metrics.py: FOUND
- tests/tools/test_evolve_tool_reasoning.py: FOUND
- tests/tools/test_dataset_ambiguous_size.py: FOUND

Commits exist:
- 9d05983: test(15-01): add Wave 0 conftest.py with fake_tools and mock_reasoning_module fixtures
- 824a547: test(15-01): add Wave 0 RED test skeleton for think_metrics (5 test classes, 21 tests)
- 42e23c4: test(15-01): add Wave 0 RED integration test skeleton for evolve_tool_reasoning (11 tests)
- 88352b5: test(15-01): add Wave 0 observation script for datasets/tools/holdout.jsonl ambiguous subset size
