---
phase: 15-think-augmented-tool-selection
plan: "06"
subsystem: tools
tags:
  - gap-closure
  - tool-dataset
  - dspy-example
  - confuser-tools
  - d13-ambiguous-filter
dependency_graph:
  requires:
    - "15-05"
  provides:
    - "to_dspy_examples() carries correct_params + confuser_tools"
    - "D-13 ambiguous filter produces ambiguous_subset_size=75 (consistent with test_dataset_ambiguous_size)"
  affects:
    - Phase 13 joint_tool_param_metric (correct_params now non-empty)
    - Phase 15 ThinkABGate D-13 ambiguous-improvement gate (ambiguous_subset_size now > 0)
    - 15-05 VALIDATION.md sign-off (unblocked)
tech_stack:
  added: []
  patterns:
    - "dspy.Example with 4 fields: task_description (input) + correct_tool/correct_params/confuser_tools (labels)"
key_files:
  created: []
  modified:
    - path: evolution/tools/tool_dataset.py
      description: "to_dspy_examples() adds correct_params + confuser_tools to dspy.Example"
    - path: tests/tools/test_tool_dataset.py
      description: "Strengthen test_to_dspy_examples + add test_to_dspy_examples_supports_ambiguous_filter"
key-decisions:
  - "Gap-closure plan: 修复 621e1c1 的 revert (b78e70b) 导致的 bug，to_dspy_examples() 只在本 plan 的 files_modified 范围内处理"
  - "dry-run 验证策略: worktree 没有 evolve_tool_reasoning.py，改为用 inline Python 模拟 ambiguous 过滤逻辑，直接加载主仓库数据集验证 ambiguous_subset_size=75"
metrics:
  duration: ~10min
  tasks_completed: 3
  tasks_total: 3
  files_modified: 2
  tests_added: 1 (test_to_dspy_examples_supports_ambiguous_filter) + 1 test strengthened
  test_suite_result: 330 passed
  ambiguous_subset_size_before: 0 (to_dspy_examples 缺 confuser_tools 字段)
  ambiguous_subset_size_after: 75 (与 test_dataset_ambiguous_size 一致)
completed: "2026-05-12"
requirements-completed:
  - TOOL-V2-03
---

# Phase 15 Plan 06: gap-closure — to_dspy_examples() confuser_tools + correct_params Summary

**修复 `to_dspy_examples()` 丢失 `confuser_tools` 和 `correct_params` 的 bug；dry-run 等效验证 `ambiguous_subset_size=75`(与观察测试一致)；330 测试全 GREEN。**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-05-12
- **Tasks:** 3/3 完成
- **Files modified:** 2

## Accomplishments

- **Task 1:** 修复 `to_dspy_examples()` — 在 `dspy.Example` 构造中追加 `correct_params=ex.correct_params` 和 `confuser_tools=ex.confuser_tools`；更新 docstring 说明 label/metadata 用途
- **Task 2:** 强化 `test_to_dspy_examples`（增 correct_params/confuser_tools 断言），新增 `test_to_dspy_examples_supports_ambiguous_filter`（D-13 回归测试：4 例中 2 例通过 `len >= 2` 过滤）
- **Task 3:** dry-run 等效验证 — worktree 修复代码 + 主仓库真实数据集 → `ambiguous_subset_size=75`，与 `test_dataset_ambiguous_size.py` 观察值 75 完全一致

## Task Commits

1. **Task 1: 修复 to_dspy_examples()** — `5e653b7` (fix)
2. **Task 2: 强化测试** — `8bbdc51` (test)
3. **Task 3: 验证** — 无文件变更，无提交（inline Python 验证，结果记录于本 SUMMARY）

## 修改前后 to_dspy_examples() 对比

**修改前（bug）:**
```python
return [
    dspy.Example(
        task_description=ex.task_description,
        correct_tool=ex.correct_tool,
    ).with_inputs("task_description")
    for ex in data
]
```
- 缺 `correct_params` → Phase 13 `joint_tool_param_metric()` 的 `param_match` 对比空 `{}`，分数虚高
- 缺 `confuser_tools` → Phase 15 D-13 过滤 `len(ex.confuser_tools) >= 2` 永远为空，`ambiguous_subset_size=0`

**修改后（fix）:**
```python
return [
    dspy.Example(
        task_description=ex.task_description,
        correct_tool=ex.correct_tool,
        correct_params=ex.correct_params,
        confuser_tools=ex.confuser_tools,
    ).with_inputs("task_description")
    for ex in data
]
```
- `correct_params` 正确传递 → Phase 13 param_match 评分使用真实参数
- `confuser_tools` 正确传递 → Phase 15 D-13 ambiguous filter 产生 `ambiguous_subset_size=75`

## dry-run 测得的 ambiguous_subset_size 实际值

| 测量来源 | 值 |
|---------|-----|
| `test_dataset_ambiguous_size.py` 直读 JSONL | 75 |
| worktree 修复代码 + 主仓库数据集 (inline 等效验证) | 75 |
| 主仓库旧代码 dry-run (修复前参考) | 0 |

两处一致：`ambiguous_subset_size=75`，验证通过。

## 全套测试结果

```
330 passed in 6.78s
```

所有 test_tool_dataset.py 测试（17/17）GREEN，全套 330 无回归。

## 与 Plan 15-05 sign-off 衔接

Plan 15-05 因以下阻塞未完成 Task 3（dry-run human-verify）和 Task 4（VALIDATION.md sign-off）：

- `to_dspy_examples()` 丢失 `confuser_tools` → dry-run 报 `ambiguous_subset_size=0`（与观察测试 75 不一致）
- 用户拒绝 in-plan 修复（commit 621e1c1 → revert b78e70b），要求独立 plan 处理

**本 plan 完成后：**
- `to_dspy_examples()` bug 已修复（worktree 分支 `5e653b7`）
- dry-run 等效验证确认 `ambiguous_subset_size=75` 与观察一致
- **15-05 的 Task 3 dry-run 一致性条件已满足**，继任 agent 可安全推进 Task 4（VALIDATION.md sign-off）

## Deviations from Plan

### Task 3: dry-run 方法调整（scope）

**背景:** Plan 要求 `python -m evolution.tools.evolve_tool_reasoning --dry-run` 在 worktree 目录执行。

**发现:** worktree 仅包含 Phase 4/Plan 2-6 相关文件（`tool_dataset.py`, `tool_loader.py` 等），`evolve_tool_reasoning.py`（Phase 15 专属）不在 worktree 文件集合中（未在此 worktree branch 上 checked out）。

**适应:** 改用 inline Python 脚本模拟 dry-run 中的 ambiguous 过滤逻辑：
- 使用 worktree 修复后的 `tool_dataset.py` (via sys.path.insert)
- 加载主仓库真实 `datasets/tools/holdout.jsonl`（临时复制至 worktree，验证后删除）
- 结果：`ambiguous_subset_size=75`，与观察测试完全一致

验证目标（"N 与 test_dataset_ambiguous_size 一致"）**完全满足**，仅执行方法有所调整。

## Known Stubs

无。两个修改文件均无 stub、hardcode 或 TODO。

## Threat Surface Scan

无新增网络端点、认证路径、文件访问模式或 schema 变更。修改是纯字段补充，不引入外部输入解析路径。

## Self-Check: PASSED

- [x] `evolution/tools/tool_dataset.py` 存在（含 confuser_tools + correct_params 字段）
- [x] `tests/tools/test_tool_dataset.py` 含 `test_to_dspy_examples_supports_ambiguous_filter`
- [x] 提交 `5e653b7` 存在（Task 1）
- [x] 提交 `8bbdc51` 存在（Task 2）
- [x] dry-run 等效验证 `ambiguous_subset_size=75 == observe=75`
- [x] 全套 330 测试 GREEN
