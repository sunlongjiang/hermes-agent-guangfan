# Phase 8: Prompt Module - Research

**Researched:** 2026-04-16
**Domain:** DSPy Module wrapping prompt sections for GEPA optimization
**Confidence:** HIGH

## Summary

Phase 8 将 Phase 7 提取的 PromptSection 包装为 DSPy 可优化模块。核心模式直接复用 Phase 3 的 ToolModule：每个 section 的 text 作为一个 `dspy.Predict` 实例的 Signature instructions，GEPA 通过 `named_parameters()` 发现并优化这些参数。与 ToolModule 的关键区别在于：(1) PromptModule 需要支持 per-section 优化而非全部联合优化，(2) 非活跃段落作为 frozen context 拼接传入 InputField，(3) 提供 `set_active_section()` 方法支持 round-robin 迭代。

ToolModule 模式已在 Phase 3 验证可行，DSPy 3.1.3 的 `Signature.with_instructions()` 和 `named_parameters()` 发现机制均已确认工作正常。PromptModule 的实现复杂度适中，核心挑战在于 frozen context 的组装和 active section 切换的正确性。

**Primary recommendation:** 严格复制 ToolModule 的 dict-of-Predict 模式，增加 `_active_section` 状态控制和 frozen context 拼接逻辑。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D1: 模块结构 -- 复用 ToolModule 模式，创建 `PromptModule(dspy.Module)`，每个 PromptSection 的 text 作为一个 `dspy.Predict` 实例的 Signature instructions
- D2: Frozen context 传递 -- 优化某一段落时，其余段落的文本作为 frozen context 拼接传入 `dspy.InputField`，不暴露给优化器
- D3: Round-robin 支持 -- 提供 `set_active_section(section_id)` 方法控制当前优化的段落
- D4: 进化结果提取 -- `get_evolved_sections()` 返回 `list[PromptSection]`

### Claude's Discretion
None specified -- all decisions locked.

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PMPT-03 | Each prompt section wrapped as DSPy-optimizable module with section text as the parameter | ToolModule dict-of-Predict pattern verified: DSPy 3.1.3 discovers Predict instances in dicts via named_parameters() |
| PMPT-04 | Per-section optimization with frozen context from other sections passed through | Frozen context as InputField verified: underscore-prefixed attrs hidden from named_parameters(); InputField passes context without optimization |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dspy | 3.1.3 | DSPy Module, Predict, Signature, InputField | Already installed, core optimization framework [VERIFIED: .venv/bin/python import] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pytest | >=7.0 | Test runner | Unit tests for PromptModule |

No new dependencies needed. All imports come from existing codebase (`dspy`, `evolution.prompts.prompt_loader`).

## Architecture Patterns

### Recommended File Structure
```
evolution/prompts/
    __init__.py          # Add PromptModule export
    prompt_loader.py     # Phase 7 (existing)
    prompt_module.py     # NEW: PromptModule class
tests/prompts/
    test_prompt_loader.py  # Phase 7 (existing)
    test_prompt_module.py  # NEW: PromptModule tests
```

### Pattern 1: Dict-of-Predict for Section Parameters (from ToolModule)

**What:** 每个 PromptSection 的 text 存储为一个 `dspy.Predict` 实例的 Signature instructions。DSPy 通过 `named_parameters()` 自动发现 dict 中的 Predict 实例。[VERIFIED: DSPy 3.1.3 测试确认 dict 属性中的 Predict 被 named_parameters() 发现]

**When to use:** 所有需要将文本制品暴露为 GEPA 可优化参数的场景。

**Example:**
```python
# Source: evolution/tools/tool_module.py (verified pattern)
class PromptModule(dspy.Module):
    def __init__(self, sections: list[PromptSection]):
        super().__init__()
        self.section_predictors: dict[str, dspy.Predict] = {}
        self._section_ids: list[str] = []
        self._active_section: str | None = None

        for section in sections:
            sig = dspy.Signature(
                "section_text -> confirmation",
                instructions=section.text,
            )
            self.section_predictors[section.section_id] = dspy.Predict(sig)
            self._section_ids.append(section.section_id)

        # Frozen metadata -- not discoverable by named_parameters()
        self._frozen_sections: dict[str, PromptSection] = {
            s.section_id: s for s in sections
        }
```

### Pattern 2: Frozen Context via Underscore-Prefix

**What:** 以下划线前缀的属性（如 `_frozen_sections`, `_active_section`）不会被 DSPy `named_parameters()` 发现，因此不会被优化器修改。[VERIFIED: DSPy 3.1.3 测试确认]

**When to use:** 存储不应被 GEPA 修改的元数据和状态。

### Pattern 3: Active Section Control for Round-Robin

**What:** `set_active_section(section_id)` 设置当前优化目标。`forward()` 构建 frozen context（非活跃段落拼接）并仅用活跃段落的 Predict 进行推理。

**Example:**
```python
def set_active_section(self, section_id: str) -> None:
    """Set the section to optimize. Others become frozen context."""
    if section_id not in self.section_predictors:
        raise ValueError(f"Unknown section: {section_id}. Available: {self._section_ids}")
    self._active_section = section_id

def _build_frozen_context(self) -> str:
    """Concatenate non-active sections as frozen context string."""
    parts = []
    for sid in self._section_ids:
        if sid != self._active_section:
            pred = self.section_predictors[sid]
            parts.append(f"[{sid}]: {pred.signature.instructions}")
    return "\n\n".join(parts)
```

### Pattern 4: Evolved Result Extraction (from ToolModule.get_evolved_descriptions)

**What:** `get_evolved_sections()` 从 Predict 实例读取当前（可能已被 GEPA 修改的）instructions，与冻结的元数据合并，返回 `list[PromptSection]`。

**Example:**
```python
def get_evolved_sections(self) -> list[PromptSection]:
    """Extract current (possibly evolved) sections merged with frozen metadata."""
    evolved = []
    for sid in self._section_ids:
        pred = self.section_predictors[sid]
        current_text = pred.signature.instructions
        original = self._frozen_sections[sid]
        evolved.append(PromptSection(
            section_id=original.section_id,
            text=current_text,
            char_count=len(current_text),
            line_range=original.line_range,
            source_path=original.source_path,
        ))
    return evolved
```

### Anti-Patterns to Avoid

- **将 section_ids 列表存为非下划线属性**: DSPy 可能尝试将其作为参数处理。所有非 Predict 的状态必须以 `_` 前缀。[VERIFIED: DSPy 3.1.3 行为]
- **在 forward() 中硬编码段落数量**: 段落数量取决于 hermes-agent 的 prompt_builder.py（当前 4 个 str + 9 个 platform hints = 13 个），不应假设固定数量。
- **忘记更新 char_count**: `get_evolved_sections()` 中必须用 `len(current_text)` 而非原始 char_count。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DSPy 参数发现 | 自定义参数注册 | `dspy.Predict` + dict 属性 | DSPy 内置的 named_parameters() 自动发现 [VERIFIED] |
| Signature 修改 | 直接修改 instructions 字符串 | `sig.with_instructions(new_text)` | DSPy immutable Signature 模式 [VERIFIED] |
| 冻结属性 | 自定义冻结机制 | `_underscore` 前缀 | DSPy named_parameters() 跳过下划线属性 [VERIFIED] |

## Common Pitfalls

### Pitfall 1: Platform Hints Section ID 包含点号
**What goes wrong:** `section_id` 如 `platform_hints.whatsapp` 包含点号，可能与 Python 属性访问冲突。
**Why it happens:** Phase 7 的命名约定用点号分隔 dict key。
**How to avoid:** 使用 dict 存储（`self.section_predictors[section_id]`），不使用 `setattr()`。ToolModule 已采用此模式。
**Warning signs:** `AttributeError` 或 `named_parameters()` 无法发现。

### Pitfall 2: Forward Signature 需要匹配评估管道
**What goes wrong:** Phase 9 的行为评估器需要特定的输入/输出格式，如果 forward() 的 Signature 不兼容会导致对接失败。
**Why it happens:** Phase 8 和 Phase 9 独立开发。
**How to avoid:** forward() 应接受 `task_input: str` 并返回 `dspy.Prediction(output=...)` -- 与 SkillModule 和 ToolModule 的模式一致。frozen context 作为内部构建的 InputField 传入。
**Warning signs:** Phase 9 集成时需要修改 forward() 签名。

### Pitfall 3: set_active_section 未调用时的行为
**What goes wrong:** 如果创建 PromptModule 后直接调用 forward() 而未设置 active section，会产生 None 相关错误。
**Why it happens:** `_active_section` 初始化为 None。
**How to avoid:** forward() 中检查 `_active_section is None` 时 raise 明确错误，或默认使用第一个 section。
**Warning signs:** `TypeError: NoneType` 在 forward() 中。

### Pitfall 4: GEPA 优化时会修改所有 Predict 实例
**What goes wrong:** GEPA 可能同时修改所有 section 的 instructions，而非仅修改 active section。
**Why it happens:** `named_parameters()` 返回所有 dict 中的 Predict，GEPA 无法区分哪个是 "active"。
**How to avoid:** 这是一个关键设计问题。两种策略：
  1. **动态重建**: `set_active_section()` 时将非活跃段落的 Predict 移到 `_frozen_predictors`（下划线前缀 dict），仅保留活跃段落在 `section_predictors` 中。
  2. **冻结标记**: 利用 Predict 的某种机制标记为不可优化（但 DSPy 3.1.3 可能不支持）。

  **推荐策略 1**: 动态移动 Predict 实例。这确保 `named_parameters()` 仅返回活跃段落。
**Warning signs:** 非活跃段落的文本在优化后被修改。

## Code Examples

### PromptModule 完整骨架（推荐实现）

```python
# Source: 基于 evolution/tools/tool_module.py 模式 + Phase 8 CONTEXT.md 决策
"""Wraps prompt sections as GEPA-optimizable DSPy module.

Each prompt section's text is stored as a dspy.Predict instance's Signature
instructions. Only the active section is discoverable by named_parameters();
other sections are held as frozen context in an underscore-prefixed dict.
"""

import dspy

from evolution.prompts.prompt_loader import PromptSection


class PromptSectionSignature(dspy.Signature):
    """Given a task and system prompt context, respond following the active section's guidance.

    Use the frozen context (other prompt sections) as background, and follow
    the active section's instructions to generate an appropriate response.
    """
    frozen_context: str = dspy.InputField(
        desc="Concatenated text from non-active prompt sections (read-only context)",
    )
    task_input: str = dspy.InputField(
        desc="The task or user message to respond to",
    )
    output: str = dspy.OutputField(
        desc="Response following the active section's guidance",
    )


class PromptModule(dspy.Module):
    """Wraps prompt sections as GEPA-optimizable parameters.

    Only one section is active (optimizable) at a time. The others
    are frozen and passed as context input. Use set_active_section()
    to switch which section is being optimized.

    Args:
        sections: List of PromptSection from prompt_loader.extract_prompt_sections()
    """

    def __init__(self, sections: list[PromptSection]):
        super().__init__()
        # Active section predictor -- discoverable by named_parameters()
        self.section_predictors: dict[str, dspy.Predict] = {}
        # Frozen section predictors -- NOT discoverable
        self._frozen_predictors: dict[str, dspy.Predict] = {}
        self._section_ids: list[str] = []
        self._active_section: str | None = None

        for section in sections:
            sig = dspy.Signature(
                "section_text -> confirmation",
                instructions=section.text,
            )
            # Initially all in frozen; set_active_section moves one out
            self._frozen_predictors[section.section_id] = dspy.Predict(sig)
            self._section_ids.append(section.section_id)

        # Frozen metadata
        self._frozen_sections: dict[str, PromptSection] = {
            s.section_id: s for s in sections
        }

        # Selector for forward pass
        self.selector = dspy.ChainOfThought(PromptSectionSignature)

    def set_active_section(self, section_id: str) -> None:
        """Set which section is optimizable. Others become frozen context."""
        if section_id not in self._frozen_sections:
            raise ValueError(
                f"Unknown section: {section_id}. "
                f"Available: {self._section_ids}"
            )
        # Move current active back to frozen
        if self._active_section is not None:
            pred = self.section_predictors.pop(self._active_section)
            self._frozen_predictors[self._active_section] = pred

        # Move new active out of frozen
        pred = self._frozen_predictors.pop(section_id)
        self.section_predictors[section_id] = pred
        self._active_section = section_id

    def forward(self, task_input: str) -> dspy.Prediction:
        """Respond to task using active section + frozen context."""
        if self._active_section is None:
            raise RuntimeError(
                "No active section set. Call set_active_section() first."
            )
        frozen_context = self._build_frozen_context()
        result = self.selector(
            frozen_context=frozen_context,
            task_input=task_input,
        )
        return dspy.Prediction(output=result.output)

    def _build_frozen_context(self) -> str:
        """Concatenate non-active sections as context string."""
        parts = []
        for sid in self._section_ids:
            if sid != self._active_section:
                pred = self._frozen_predictors[sid]
                parts.append(f"[{sid}]: {pred.signature.instructions}")
        return "\n\n".join(parts)

    def get_evolved_sections(self) -> list[PromptSection]:
        """Extract current (possibly evolved) sections merged with frozen metadata."""
        evolved = []
        for sid in self._section_ids:
            # Check both dicts
            if sid in self.section_predictors:
                pred = self.section_predictors[sid]
            else:
                pred = self._frozen_predictors[sid]
            current_text = pred.signature.instructions
            original = self._frozen_sections[sid]
            evolved.append(PromptSection(
                section_id=original.section_id,
                text=current_text,
                char_count=len(current_text),
                line_range=original.line_range,
                source_path=original.source_path,
            ))
        return evolved
```

### 关键验证：动态 Predict 移动确保隔离

```python
# Source: DSPy 3.1.3 行为验证 [VERIFIED: 本次会话测试]
import dspy

class TestMod(dspy.Module):
    def __init__(self):
        super().__init__()
        self.active = {}                    # discoverable
        self._frozen = {                    # NOT discoverable
            'a': dspy.Predict(dspy.Signature('x -> y', instructions='A')),
            'b': dspy.Predict(dspy.Signature('x -> y', instructions='B')),
        }

m = TestMod()
assert len(list(m.named_parameters())) == 0  # nothing in active

# Move 'a' to active
m.active['a'] = m._frozen.pop('a')
params = list(m.named_parameters())
assert len(params) == 1                     # only 'a' discoverable
assert params[0][0] == "active['a']"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| DSPy SkillModule: 单个文本参数 | ToolModule: dict-of-Predict + frozen schema | Phase 3 (本项目) | 支持多参数独立优化 |
| 全参数同时优化 | Per-section + frozen context | Phase 8 (本 Phase) | 避免 GEPA 同时修改所有段落 |

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=7.0 (installed in .venv) |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `.venv/bin/pytest tests/prompts/test_prompt_module.py -x` |
| Full suite command | `.venv/bin/pytest tests/prompts/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PMPT-03 | Each section exposed as optimizable parameter | unit | `.venv/bin/pytest tests/prompts/test_prompt_module.py::TestPromptModule -x` | Wave 0 |
| PMPT-03 | Signature instructions match section text | unit | `.venv/bin/pytest tests/prompts/test_prompt_module.py::TestPromptModule::test_section_predictor_instructions -x` | Wave 0 |
| PMPT-04 | Frozen context excludes active section | unit | `.venv/bin/pytest tests/prompts/test_prompt_module.py::TestFrozenContext -x` | Wave 0 |
| PMPT-04 | Only active section in named_parameters | unit | `.venv/bin/pytest tests/prompts/test_prompt_module.py::TestFrozenContext::test_only_active_in_named_parameters -x` | Wave 0 |
| D3 | set_active_section switches correctly | unit | `.venv/bin/pytest tests/prompts/test_prompt_module.py::TestActiveSection -x` | Wave 0 |
| D4 | get_evolved_sections returns list[PromptSection] | unit | `.venv/bin/pytest tests/prompts/test_prompt_module.py::TestGetEvolvedSections -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/pytest tests/prompts/test_prompt_module.py -x`
- **Per wave merge:** `.venv/bin/pytest tests/prompts/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/prompts/test_prompt_module.py` -- covers PMPT-03, PMPT-04, D3, D4
- Framework install: not needed (pytest already available)
- Shared fixtures: test_prompt_loader.py 的 `SAMPLE_PROMPT_BUILDER` 可复用

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | GEPA 优化时会修改 named_parameters() 返回的所有 Predict 实例 | Common Pitfalls #4 | 如果 GEPA 有内置的冻结机制，动态移动方案可简化 |
| A2 | forward() 的 Signature 需要 frozen_context + task_input 格式 | Code Examples | Phase 9 评估器可能需要不同格式，但遵循 SkillModule 模式降低风险 |

## Open Questions

1. **GEPA 是否支持 per-parameter 冻结？**
   - What we know: DSPy 3.1.3 的 `named_parameters()` 返回所有非下划线 Predict 实例 [VERIFIED]
   - What's unclear: GEPA 是否有 `freeze()` 或类似 API 可以标记特定参数为不可优化
   - Recommendation: 使用动态移动方案（将非活跃 Predict 移到 `_frozen_predictors`），这是最可靠的隔离方式，不依赖 GEPA 内部机制

## Sources

### Primary (HIGH confidence)
- `evolution/tools/tool_module.py` -- ToolModule 参考实现，直接阅读源码
- `evolution/prompts/prompt_loader.py` -- PromptSection 数据类，直接阅读源码
- DSPy 3.1.3 runtime -- `named_parameters()`, `Signature.with_instructions()` 行为通过实际 Python 执行验证
- `tests/tools/test_tool_module.py` -- 测试模式参考

### Secondary (MEDIUM confidence)
None.

### Tertiary (LOW confidence)
None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - 无新依赖，全部使用已验证的 DSPy API
- Architecture: HIGH - 直接复用 ToolModule 模式，关键行为已通过运行时验证
- Pitfalls: HIGH - Pitfall #4（GEPA 修改所有 Predict）通过 named_parameters() 测试确认，动态移动方案已验证

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (stable domain, DSPy API unlikely to break)
