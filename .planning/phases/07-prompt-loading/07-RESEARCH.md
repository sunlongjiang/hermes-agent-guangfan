# Phase 7: Prompt Loading - Research

**Researched:** 2026-04-16
**Domain:** Python AST parsing, prompt section extraction and format-preserving write-back
**Confidence:** HIGH

## Summary

Phase 7 从 hermes-agent 的 `agent/prompt_builder.py` 中提取 5 个可进化的提示词段落，并支持格式保持的写回。核心技术是 Python `ast` 模块解析源文件，定位目标变量的 `ast.Assign` 节点，提取文本值和行号范围，然后通过行级替换实现写回。

实际验证发现 `prompt_builder.py` 中的 4 个 str 常量全部使用括号拼接格式 `("a " "b ")`，AST 自动合并为单一 `ast.Constant` 节点。`PLATFORM_HINTS` 是 `ast.Dict`，包含 9 个 key（whatsapp, telegram, discord, slack, signal, email, cron, cli, sms）。AST 提供精确的 `lineno`/`end_lineno` 和 `col_offset`/`end_col_offset`，足够支持位置级写回。

本 Phase 与 Phase 2 的 tool_loader 共享 "AST 提取 + 位置替换写回" 模式，但实现更简单：只有一个源文件、两种格式（paren_concat str 和 dict value），且所有目标变量都是模块顶层赋值。

**Primary recommendation:** 使用 `ast.parse()` + `ast.walk()` 找到 5 个目标 `ast.Assign` 节点，提取文本和行号范围；写回时用行号范围做源文件行级替换，重新格式化为括号拼接格式。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D1: PLATFORM_HINTS 按 key 展开为独立段落 (platform_hints.whatsapp etc)
- D2: 使用 AST 解析提取/写回
- D3: 四项元数据: section_id, char_count, line_range, source_path

### Claude's Discretion
None specified.

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PMPT-01 | Pipeline can extract 5 evolvable sections from prompt_builder.py | AST 解析验证通过：4 个 str 常量为 `ast.Constant`，PLATFORM_HINTS 为 `ast.Dict`，均含精确行号范围 |
| PMPT-02 | Pipeline can write evolved sections back preserving surrounding code structure | 行级替换策略：用 AST 行号范围定位，替换后重新格式化为括号拼接格式，保留文件其余部分不变 |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `ast` | stdlib | Python AST 解析，定位目标变量和行号范围 | Python 标准库，无需安装，Phase 2 已验证模式 [VERIFIED: Python 3.14.3 stdlib] |
| `dataclasses` | stdlib | `PromptSection` 数据类定义 | 项目统一使用 dataclass 模式 [VERIFIED: codebase pattern] |
| `pathlib` | stdlib | 文件路径处理 | 项目统一使用 Path [VERIFIED: codebase pattern] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `rich` | >=13.0 | Console 输出和警告信息 | 所有用户可见输出 [VERIFIED: codebase convention] |
| `pytest` | >=7.0 | round-trip 测试 | 验证 extract -> modify -> write-back -> extract 循环 [VERIFIED: pyproject.toml] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `ast` 模块 | 正则表达式 | 正则更脆弱，无法可靠处理嵌套括号和多行字符串；AST 是 D2 锁定决策 |
| 行级替换 | `ast.unparse()` 重建 | `ast.unparse()` 会丢失注释和格式；行级替换保留文件其余部分 |

## Architecture Patterns

### Recommended Project Structure

```
evolution/
├── prompts/
│   ├── __init__.py          # 已存在 (placeholder)
│   └── prompt_loader.py     # 新文件：提取和写回
tests/
└── prompts/
    ├── __init__.py
    └── test_prompt_loader.py # round-trip 测试
```

### Pattern 1: AST 变量定位

**What:** 用 `ast.parse()` 解析 `prompt_builder.py`，`ast.walk()` 遍历找到目标变量名的 `ast.Assign` 节点。
**When to use:** 提取阶段。

**关键发现** [VERIFIED: 实际 AST 解析 prompt_builder.py]:
- 4 个 str 常量（DEFAULT_AGENT_IDENTITY, MEMORY_GUIDANCE, SESSION_SEARCH_GUIDANCE, SKILLS_GUIDANCE）AST 类型为 `ast.Constant`，括号拼接被自动合并
- PLATFORM_HINTS AST 类型为 `ast.Dict`，9 个 key 的每个 value 也是 `ast.Constant`
- `ast.Assign` 节点提供 `lineno`/`end_lineno`（1-based）和 `col_offset`/`end_col_offset`

**Example:**
```python
# Source: 实际验证 prompt_builder.py AST 解析结果
import ast

EVOLVABLE_STR_VARS = [
    "DEFAULT_AGENT_IDENTITY",
    "MEMORY_GUIDANCE",
    "SESSION_SEARCH_GUIDANCE",
    "SKILLS_GUIDANCE",
]
EVOLVABLE_DICT_VAR = "PLATFORM_HINTS"

def _find_assignments(source: str) -> dict[str, ast.Assign]:
    """Parse source and find target variable assignments."""
    tree = ast.parse(source)
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                name = target.id
                if name in EVOLVABLE_STR_VARS or name == EVOLVABLE_DICT_VAR:
                    found[name] = node
    return found
```

### Pattern 2: 行级替换写回

**What:** 读取源文件为行列表，用 AST 提供的行号范围定位目标区域，替换为重新格式化的文本，然后重新组装写回。
**When to use:** 写回阶段。

**关键发现** [VERIFIED: 实际 AST 行号测试]:
- `ast.Assign.lineno` 指向 `VAR_NAME = (` 那一行（1-based）
- `ast.Assign.end_lineno` 指向 `)` 那一行
- 对于 PLATFORM_HINTS dict，每个 value 的 `ast.Constant` 节点也有独立的 `lineno`/`end_lineno`
- 写回策略：替换 `lines[lineno-1 : end_lineno]` 为新格式化的文本

**Example:**
```python
def _replace_lines(
    source: str,
    start_line: int,  # 1-based, from AST lineno
    end_line: int,     # 1-based, from AST end_lineno
    replacement: str,
) -> str:
    """Replace lines [start_line, end_line] inclusive with replacement text."""
    lines = source.splitlines(keepends=True)
    # AST lines are 1-based
    before = lines[:start_line - 1]
    after = lines[end_line:]
    # Ensure replacement ends with newline
    if not replacement.endswith("\n"):
        replacement += "\n"
    return "".join(before) + replacement + "".join(after)
```

### Pattern 3: PromptSection 数据类

**What:** 遵循 D3 决策，每个提取的段落携带四项元数据。
**When to use:** 数据传递。

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class PromptSection:
    """An extracted prompt section with metadata for write-back."""
    section_id: str          # e.g. "default_agent_identity" or "platform_hints.whatsapp"
    text: str                # 提取的纯文本内容
    char_count: int          # len(text)
    line_range: tuple[int, int]  # (start_line, end_line), 1-based
    source_path: Path        # prompt_builder.py 的路径

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id,
            "text": self.text,
            "char_count": self.char_count,
            "line_range": list(self.line_range),
            "source_path": str(self.source_path),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PromptSection":
        return cls(
            section_id=d["section_id"],
            text=d["text"],
            char_count=d["char_count"],
            line_range=tuple(d["line_range"]),
            source_path=Path(d["source_path"]),
        )
```

### Pattern 4: PLATFORM_HINTS 展开

**What:** D1 决策要求将 PLATFORM_HINTS dict 的每个 key 展开为独立 `PromptSection`。
**When to use:** PLATFORM_HINTS 提取。

**实际数据** [VERIFIED: AST 解析 prompt_builder.py]:

| key | 行范围 | 字符数 |
|-----|--------|--------|
| whatsapp | 287-294 | 512 |
| telegram | 297-303 | 448 |
| discord | 306-310 | 347 |
| slack | 313-317 | 342 |
| signal | 320-326 | 443 |
| email | 329-334 | 372 |
| cron | 337-341 | 358 |
| cli | 344-345 | 93 |
| sms | 348-350 | 177 |

写回 dict value 时需要特殊处理：不能替换整个 dict，只替换特定 key 的 value 部分。

### Anti-Patterns to Avoid

- **整体 ast.unparse()**: 会丢失所有注释、空行和格式，不可接受
- **正则定位变量**: prompt_builder.py 中有大量类似格式的非目标变量（TOOL_USE_ENFORCEMENT_GUIDANCE 等），正则容易误匹配
- **修改 AST 再 unparse**: 同上，丢失格式信息
- **只用 Constant 节点的行号**: 对于 str 常量，Constant 的行号不包含括号行；必须用 Assign 节点的行号才能覆盖完整赋值语句

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Python 源码解析 | 自写 tokenizer/正则 | `ast.parse()` | AST 是 Python 标准库，正确处理所有语法 |
| 字符串字面量求值 | 手动拼接 | `ast.literal_eval()` 或 AST Constant.value | 自动处理转义和隐式拼接 |
| 括号拼接格式化 | 简单 split | 复用 tool_loader 的 `_format_paren_concat()` 逻辑 | 已验证的格式化逻辑 |

## Common Pitfalls

### Pitfall 1: AST 行号是 1-based

**What goes wrong:** 用 AST 的 lineno 直接索引 `lines[lineno]` 会偏移一行。
**Why it happens:** AST 行号从 1 开始，Python list 从 0 开始。
**How to avoid:** 始终使用 `lines[lineno - 1]`。
**Warning signs:** 写回后的内容偏移了一行。

### Pitfall 2: Assign 节点 vs Constant 节点的行号范围不同

**What goes wrong:** 用 `ast.Constant` 的 `lineno`/`end_lineno` 做写回，遗漏了括号行。
**Why it happens:** 对于 `X = (\n    "hello "\n    "world"\n)`，Constant 节点的 lineno 指向 "hello" 那行，end_lineno 指向 "world" 那行，不包含 `(` 和 `)` 所在的行。
**How to avoid:** str 常量写回用 Assign 节点的行号范围；dict value 写回用 Constant 节点的行号范围（因为只替换 value 部分）。
**Warning signs:** 写回后残留了括号或变量名。

**验证数据** [VERIFIED]:
```
DEFAULT_AGENT_IDENTITY: assign line 134-142, value(Constant) line 135-141
```
- Assign 范围 134-142 包含 `DEFAULT_AGENT_IDENTITY = (` 和 `)`
- Constant 范围 135-141 只包含字符串内容

### Pitfall 3: PLATFORM_HINTS dict value 写回需要精确定位

**What goes wrong:** 替换整个 PLATFORM_HINTS dict 时，如果只修改了一个 platform 的文本，其他 platform 的格式可能被破坏。
**Why it happens:** 重新格式化整个 dict 会改变所有 value 的格式。
**How to avoid:** 只替换特定 key 的 value 行范围，不动 dict 的其他部分。用 `ast.Dict` 的 key/value 对的 Constant 节点的行号精确定位。
**Warning signs:** round-trip 测试中未修改的 platform hint 文本或格式发生变化。

### Pitfall 4: 写回后 line_range 失效

**What goes wrong:** 写回一个 section 后，后续 section 的 line_range 可能偏移。
**Why it happens:** 替换文本的行数可能与原文不同。
**How to avoid:** 如果需要批量写回，从文件末尾的 section 开始向前替换；或者每次写回后重新解析 AST。
**Warning signs:** 第二次写回时内容替换到了错误位置。

### Pitfall 5: 格式化后 py_compile 失败

**What goes wrong:** 写回的文本包含未转义的引号或换行符，导致 Python 语法错误。
**Why it happens:** 进化后的文本可能包含引号字符。
**How to avoid:** 写回前用 `_format_paren_concat()` 正确转义；写回后用 `py_compile.compile()` 验证语法。
**Warning signs:** round-trip 测试的 `py_compile` 检查失败。

## Code Examples

### Extract all sections

```python
# Source: 基于实际 AST 解析结果设计
import ast
from pathlib import Path

TARGET_STR_VARS = {
    "DEFAULT_AGENT_IDENTITY": "default_agent_identity",
    "MEMORY_GUIDANCE": "memory_guidance",
    "SESSION_SEARCH_GUIDANCE": "session_search_guidance",
    "SKILLS_GUIDANCE": "skills_guidance",
}
TARGET_DICT_VAR = "PLATFORM_HINTS"

def extract_prompt_sections(prompt_builder_path: Path) -> list[PromptSection]:
    """Extract all evolvable prompt sections from prompt_builder.py."""
    source = prompt_builder_path.read_text()
    tree = ast.parse(source)
    sections = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue

        var_name = target.id

        if var_name in TARGET_STR_VARS:
            # Paren-concat str constant -> single PromptSection
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                sections.append(PromptSection(
                    section_id=TARGET_STR_VARS[var_name],
                    text=node.value.value,
                    char_count=len(node.value.value),
                    line_range=(node.lineno, node.end_lineno),
                    source_path=prompt_builder_path,
                ))

        elif var_name == TARGET_DICT_VAR:
            # Dict -> expand each key to independent PromptSection
            if isinstance(node.value, ast.Dict):
                for key_node, val_node in zip(node.value.keys, node.value.values):
                    if (isinstance(key_node, ast.Constant)
                            and isinstance(val_node, ast.Constant)
                            and isinstance(val_node.value, str)):
                        key = key_node.value
                        sections.append(PromptSection(
                            section_id=f"platform_hints.{key}",
                            text=val_node.value,
                            char_count=len(val_node.value),
                            line_range=(val_node.lineno, val_node.end_lineno),
                            source_path=prompt_builder_path,
                        ))

    return sections
```

### Write back a str section

```python
# Source: 基于 AST 行号范围和 tool_loader 写回模式设计
def write_back_section(
    prompt_builder_path: Path,
    section: PromptSection,
    new_text: str,
) -> None:
    """Write evolved text back to prompt_builder.py, preserving format."""
    source = prompt_builder_path.read_text()
    lines = source.splitlines(keepends=True)

    start_line, end_line = section.line_range  # 1-based

    if section.section_id.startswith("platform_hints."):
        # Dict value: replace only the value's line range
        replacement = _format_paren_concat_value(new_text, indent=4)
    else:
        # Top-level str assignment: replace entire assignment
        var_name = section.section_id.upper()
        replacement = _format_str_assignment(var_name, new_text)

    # Line-level replacement
    new_lines = lines[:start_line - 1] + [replacement + "\n"] + lines[end_line:]
    prompt_builder_path.write_text("".join(new_lines))
```

### Round-trip test pattern

```python
# Source: 基于 test_tool_loader.py 的 round-trip 测试模式
def test_round_trip(tmp_path):
    """Extract -> modify -> write back -> extract again yields modification."""
    # Copy prompt_builder.py to tmp
    src = tmp_path / "prompt_builder.py"
    src.write_text(SAMPLE_PROMPT_BUILDER_SOURCE)

    # Extract
    sections = extract_prompt_sections(src)
    original = {s.section_id: s.text for s in sections}

    # Modify one section
    target = next(s for s in sections if s.section_id == "memory_guidance")
    new_text = "EVOLVED: " + target.text

    # Write back
    write_back_section(src, target, new_text)

    # Verify syntax
    import py_compile
    py_compile.compile(str(src), doraise=True)

    # Re-extract
    sections2 = extract_prompt_sections(src)
    result = {s.section_id: s.text for s in sections2}

    # Modified section has new text
    assert result["memory_guidance"] == new_text

    # Unmodified sections unchanged
    for sid in original:
        if sid != "memory_guidance":
            assert result[sid] == original[sid]
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `ast.Str` 节点 | `ast.Constant` 节点 | Python 3.8+ | 所有字符串字面量统一为 `ast.Constant`，`ast.Str` 已废弃 |
| 无 `end_lineno` | `end_lineno`/`end_col_offset` | Python 3.8+ | AST 节点现在提供精确的结束位置，使行级替换成为可能 |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | prompt_builder.py 的 5 个目标变量不会频繁新增/删除 key | Architecture Patterns | 如果 PLATFORM_HINTS 新增 key，loader 需要重新提取但不影响已有逻辑 |

所有其他主要声明均已通过实际 AST 解析验证。

## Open Questions

1. **str 常量写回时的缩进约定**
   - What we know: 原文使用 4 空格缩进的括号拼接格式
   - What's unclear: 是否所有 str 常量的缩进都一致（已验证是的）
   - Recommendation: 硬编码 4 空格缩进，与原文一致

2. **PLATFORM_HINTS dict value 写回时的 key 行处理**
   - What we know: AST 给出的是 value 的行号范围（如 whatsapp: 287-294），不包含 key 行（如 `"whatsapp": (`）
   - What's unclear: value 的 lineno 是否包含左括号
   - Recommendation: 实际验证 value Constant 的 lineno 指向第一个字符串行（如 287 = `"You are on..."`），不包含 key 行。写回时只替换 value 的字符串内容行，保留 key 行和缩进。需要在实现时仔细处理 `("` 和 `)` 的边界。

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >=7.0 |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/prompts/ -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PMPT-01 | 提取 4 个 str 段落 + 9 个 platform hint 段落 | unit | `python -m pytest tests/prompts/test_prompt_loader.py::test_extract_all_sections -x` | Wave 0 |
| PMPT-01 | 每个段落有正确的 section_id, char_count, line_range, source_path | unit | `python -m pytest tests/prompts/test_prompt_loader.py::test_section_metadata -x` | Wave 0 |
| PMPT-02 | str 段落 round-trip: extract -> modify -> write back -> extract | unit | `python -m pytest tests/prompts/test_prompt_loader.py::test_round_trip_str -x` | Wave 0 |
| PMPT-02 | platform hint round-trip | unit | `python -m pytest tests/prompts/test_prompt_loader.py::test_round_trip_platform_hint -x` | Wave 0 |
| PMPT-02 | 写回后 py_compile 通过 | unit | `python -m pytest tests/prompts/test_prompt_loader.py::test_write_back_syntax_valid -x` | Wave 0 |
| PMPT-02 | 写回一个段落不影响其他段落 | unit | `python -m pytest tests/prompts/test_prompt_loader.py::test_write_back_isolation -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `python -m pytest tests/prompts/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/prompts/__init__.py` -- package init
- [ ] `tests/prompts/test_prompt_loader.py` -- covers PMPT-01, PMPT-02

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A |
| V3 Session Management | no | N/A |
| V4 Access Control | no | N/A |
| V5 Input Validation | yes | AST 解析只接受有效 Python；写回后用 py_compile 验证 |
| V6 Cryptography | no | N/A |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| 恶意文本注入到 prompt_builder.py | Tampering | 写回后 py_compile 验证；进化文本仅替换字符串值，不能改变 Python 代码结构 |

## Sources

### Primary (HIGH confidence)
- Python `ast` 模块 - 实际解析 `~/.hermes/hermes-agent/agent/prompt_builder.py` 验证 [VERIFIED: 实际运行 ast.parse()]
- `evolution/tools/tool_loader.py` - Phase 2 的 AST + 位置替换写回模式 [VERIFIED: 代码阅读]
- `evolution/core/config.py` - `EvolutionConfig.max_prompt_growth = 0.2` [VERIFIED: 代码阅读]
- `evolution/core/constraints.py` - `ConstraintResult` 数据类和 `_check_growth()` 方法 [VERIFIED: 代码阅读]

### Secondary (MEDIUM confidence)
- None needed -- all claims verified through direct source inspection.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - 全部使用 Python stdlib，无外部依赖
- Architecture: HIGH - 实际 AST 解析验证了所有数据结构和行号
- Pitfalls: HIGH - 通过实际测试发现并验证了 AST 行号差异

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (stable -- stdlib-only, prompt_builder.py 结构不会频繁变化)
