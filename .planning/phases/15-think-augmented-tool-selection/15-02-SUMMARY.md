---
phase: 15
plan: "02"
subsystem: tools
tags: [tdd, wave-1, think-augmented, tool-module, enable-reasoning, gepa]
dependency_graph:
  requires:
    - 15-01 (conftest.py mock_reasoning_module fixture + Wave 0 RED scaffolding)
  provides:
    - evolution/tools/tool_module.py (ToolReasoningSignature + enable_reasoning ctor + forward dual-path)
    - tests/tools/test_tool_module.py (TestEnableReasoning 7 tests)
  affects:
    - Wave 2: think_metrics.py 可使用 ToolModule(enable_reasoning=True)
    - Wave 3: evolve_tool_reasoning.py CLI 可构造 think-on/think-off 双模块对比
    - conftest.py mock_reasoning_module fixture 从 RED 转为 GREEN
tech_stack:
  added: []
  patterns:
    - DSPy per-Predict LM override via predict.set_lm() (RESEARCH §1.3 Path C)
    - Optional think-on path with static branching at constructor (D-05/D-07)
    - reasoning InputField default="" for backward compatibility (RESEARCH §9 选项 A)
key_files:
  created: []
  modified:
    - evolution/tools/tool_module.py
    - tests/tools/test_tool_module.py
decisions:
  - "ToolReasoningSignature 定义为模块顶层类（而非 ToolModule 内嵌类），使其可被直接 import 用于测试断言 sig is ToolReasoningSignature"
  - "reasoning InputField 插入 ToolSelectionWithParamsSignature 的 available_tools 与 selected_tool 之间（不是末尾），保持输入字段与输出字段的自然分隔"
  - "forward() 在 think-off 路径中显式传递 reasoning='' 给 selector，保持一致调用签名"
metrics:
  duration_seconds: 455
  completed_date: "2026-05-11"
  tasks_completed: 2
  files_created: 0
  files_modified: 2
---

# Phase 15 Plan 02: Wave 1 ToolModule Core Refactor Summary

Wave 1 核心实现完成：ToolModule 新增 `enable_reasoning` 构造器 kwarg，引入独立 `ToolReasoningSignature` 类，`forward()` 实现 think-on/think-off 双路径，GEPA 通过 `named_predictors()` 可触达 reasoner.signature.instructions。

## What Was Built

### tool_module.py 改造（232 行 → 326 行，+94 行）

| 改造段 | 内容 |
|--------|------|
| 模块 docstring | 追加 Phase 15 一行说明 |
| `ToolReasoningSignature` | 新增类：2 InputField + 1 OutputField；docstring 含 D-04 "Be concise (≤200 tokens)" + D-02 "Do NOT pre-select a tool" |
| `ToolSelectionWithParamsSignature` | 新增 `reasoning: str = dspy.InputField(default="")` 字段 |
| `ToolModule.__init__` | 新签名：`enable_reasoning: bool = False, eval_model: str, lm_kwargs: Optional[dict]`；enable_reasoning=True 时构造 `dspy.Predict(ToolReasoningSignature)` 并 `set_lm(max_tokens=200)` |
| `ToolModule.forward` | 双路径：think-on 先调 reasoner，reasoning 文本传入 selector；所有路径返回 `reasoning` + `reasoning_tokens` 字段 |

### TestEnableReasoning 测试类（7 个测试，全部 GREEN）

| 测试 | 覆盖决策 | 结果 |
|------|---------|------|
| `test_constructs_reasoner` | D-01 dspy.Predict 而非 CoT | PASS |
| `test_disabled_reasoner_absent` | D-05 opt-in | PASS |
| `test_default_enable_reasoning_is_false` | D-06 向后兼容 | PASS |
| `test_off_path_no_reasoner_call` | D-06 think-off = Phase 13 | PASS |
| `test_on_path_reasoner_first` | D-01/D-02 调用顺序 | PASS |
| `test_reasoner_lm_max_tokens_200` | D-04 LM 双保险其一 | PASS |
| `test_reasoner_in_named_predictors` | TOOL-V2-03 SC-2 GEPA 可达 | PASS |

## 关键验证结果

### TestEnableReasoning 7/7 GREEN
```
tests/tools/test_tool_module.py::TestEnableReasoning::test_constructs_reasoner PASSED
tests/tools/test_tool_module.py::TestEnableReasoning::test_disabled_reasoner_absent PASSED
tests/tools/test_tool_module.py::TestEnableReasoning::test_default_enable_reasoning_is_false PASSED
tests/tools/test_tool_module.py::TestEnableReasoning::test_off_path_no_reasoner_call PASSED
tests/tools/test_tool_module.py::TestEnableReasoning::test_on_path_reasoner_first PASSED
tests/tools/test_tool_module.py::TestEnableReasoning::test_reasoner_lm_max_tokens_200 PASSED
tests/tools/test_tool_module.py::TestEnableReasoning::test_reasoner_in_named_predictors PASSED
7 passed in 6.73s
```

### Phase 13/14 现有测试不退化
```
tests/tools/（--ignore test_think_metrics + test_evolve_tool_reasoning）
174 passed, 1 skipped in 10.26s
```

### D-04 双保险实测
- `max_tokens=200` kwarg：3 处命中（LM 构造、注释、其他）
- docstring 提示文字：3 处命中（"Be concise"、"≤200 tokens"、"Do NOT pre-select"）

### named_predictors() reasoner 路径实测
```
Plan check 4 PASS: reasoner key='reasoner',
instructions starts: 'Briefly reason about which tool best fits this task.\n\nBe con'
```

### mock_reasoning_module fixture 转 GREEN
Wave 0 conftest.py 中 `mock_reasoning_module` fixture 在 Wave 0 时会 `TypeError`（`enable_reasoning` kwarg 不存在），Wave 1 完成后已转 GREEN，Wave 2/3 测试可直接使用该 fixture。

## D-01..D-07 + D-17 覆盖确认

| 决策 | 实现位置 | 验证 |
|------|---------|------|
| D-01: Predict 而非 CoT | `dspy.Predict(ToolReasoningSignature)` | test_constructs_reasoner |
| D-02: reasoner 不输出 selected_tool | Signature 仅 OutputField=reasoning | test_on_path_reasoner_first (selector 仍收完整 tools) |
| D-03: 全局单实例 reasoner | `self.reasoner` 单实例 | test_constructs_reasoner |
| D-04: 200-token cap 双保险 | `max_tokens=200` + docstring "≤200 tokens" | test_reasoner_lm_max_tokens_200 |
| D-05: opt-in flag | `enable_reasoning: bool = False` kwarg | test_default_enable_reasoning_is_false |
| D-06: think-off = Phase 13 | `reasoning=""` 默认透传 | test_off_path_no_reasoner_call |
| D-07: ctor 后不可变 | `*` 强制 keyword-only，文档说明 immutable | code review |
| D-17: reasoning_tokens 字段 | `int(len(reasoning_text) / 4)` | test_off_path_no_reasoner_call (=0) + test_on_path_reasoner_first (>0) |

## Deviations from Plan

无 — 计划按原样执行。代码中的注释结构和测试方法均与计划中的 pseudocode 一致。

## Known Stubs

无 stubs — 所有实现路径均已完整（reasoning 计算通过 `len/4` 估算，非空占位符）。

## Threat Flags

无新增安全相关 surface — 改造限于 DSPy 模块内部，所有 LM 调用在测试中通过 MagicMock 屏蔽（满足 T-15-02-02 mitigate 要求）。

## Self-Check: PASSED

Files exist:
- evolution/tools/tool_module.py: FOUND (326 lines)
- tests/tools/test_tool_module.py: FOUND (380 lines)

Commits exist:
- 82dcc27: feat(15-02): add ToolReasoningSignature + enable_reasoning ctor + forward dual-path
- 63732a6: test(15-02): add TestEnableReasoning class — 7 tests for Wave 1 ToolModule changes
