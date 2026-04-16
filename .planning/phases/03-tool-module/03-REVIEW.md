---
phase: 03
status: issues_found
severity_max: medium
findings_count: 3
reviewed_files:
  - evolution/tools/tool_module.py
  - tests/tools/test_tool_module.py
findings:
  critical: 0
  warning: 2
  info: 1
  total: 3
---

# Phase 03: Code Review Report

**Reviewed:** 2026-04-16T12:00:00Z
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

`tool_module.py` 实现了将工具描述包装为 DSPy GEPA 可优化参数的模块，整体结构清晰，与 Phase 1 的 `SkillModule` 模式保持一致。代码遵循项目约定（snake_case、Google docstring、Rich console 等）。发现 2 个 Warning 级别问题和 1 个 Info 级别问题。

## Warnings

### WR-01: 工具名称 hyphen-to-underscore 转换可能产生键冲突

**File:** `evolution/tools/tool_module.py:52`
**Issue:** `td.name.replace("-", "_")` 将连字符替换为下划线。如果同时存在名为 `list-files` 和 `list_files` 的工具，后者会静默覆盖前者在 `self.tool_predictors` 字典中的条目，导致数据丢失且无任何警告。虽然 hermes-agent 当前不太可能出现此情况，但作为通用模块应进行防御性检查。
**Fix:**
```python
for td in tool_descriptions:
    safe_name = td.name.replace("-", "_")
    if safe_name in self.tool_predictors:
        raise ValueError(
            f"Tool name collision: '{td.name}' maps to '{safe_name}' "
            f"which already exists in tool_predictors"
        )
    desc = td.description if td.description else f"Tool: {td.name}"
    sig = dspy.Signature("tool_name -> confirmation", instructions=desc)
    self.tool_predictors[safe_name] = dspy.Predict(sig)
    self._tool_names.append(td.name)
```

### WR-02: 空工具列表时 forward() 行为不明确

**File:** `evolution/tools/tool_module.py:46-86`
**Issue:** 如果传入空的 `tool_descriptions` 列表，`ToolModule` 构造不会报错，但 `forward()` 会向 LLM 发送空的 `available_tools` 字符串，LLM 的选择结果将是不可预测的。构造时应对空列表进行校验，或至少在文档中明确说明此限制。
**Fix:**
```python
def __init__(self, tool_descriptions: list[ToolDescription]):
    super().__init__()
    if not tool_descriptions:
        raise ValueError("tool_descriptions must not be empty")
    self.tool_predictors: dict[str, dspy.Predict] = {}
    self._tool_names: list[str] = []
    # ... rest of init
```

## Info

### IN-01: 测试文件中未使用的 MagicMock 导入

**File:** `tests/tools/test_tool_module.py:4`
**Issue:** `from unittest.mock import patch, MagicMock` 中 `MagicMock` 已导入但从未使用。
**Fix:** 移除未使用的导入：
```python
from unittest.mock import patch
```

---

_Reviewed: 2026-04-16T12:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
