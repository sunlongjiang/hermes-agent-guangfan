# Phase 2: Tool Loading - Research

**Researched:** 2026-04-16
**Domain:** Python source code parsing (regex-based extraction/rewriting of tool schema dicts in hermes-agent)
**Confidence:** HIGH

## Summary

Phase 2 的核心任务是从 hermes-agent 的 `tools/*.py` 文件中提取工具描述（top-level description 和 per-parameter description），以及将进化后的描述写回原文件而不破坏 schema 结构。

通过对 hermes-agent 53 个工具文件的系统化审计，已确认：所有工具通过 `registry.register()` 注册，schema 均存储在命名常量中（如 `MEMORY_SCHEMA`、`READ_FILE_SCHEMA`）。描述文本有 4 种格式模式，写回时必须按原格式保持一致。MCP 动态注册的工具（f-string 模板）不在静态解析范围内。

**Primary recommendation:** 使用正则表达式解析 Python 源文件中的 schema dict 字面量，按 `*_SCHEMA = {` 命名常量定位，提取 `"description"` 字段值；写回时定位原描述位置做精确字符串替换，保持原始格式（单行/多行/三引号）。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** 使用正则表达式从 `tools/*.py` 文件提取描述，和 Phase 1 的 skill frontmatter 解析模式一致
- **D-02:** 同时提取 top-level description 和每个参数的 description，两者都是可进化目标
- **D-03:** 需要处理多种描述格式：内联 dict 字面量、字符串隐式拼接（括号内多行）、命名常量引用
- **D-04:** 使用正则定位 + 字符串替换写回进化后的描述，和 Phase 1 的 `reassemble_skill()` 模式一致
- **D-05:** 保留原文件的格式——如果原始描述是多行字符串拼接，写回时也保持多行拼接格式；如果是单行则保持单行。目标是最小化 diff 噪音
- **D-06:** 写回只修改 description 文本，param names/types/required/enum 等 schema 结构完全不碰
- **D-07:** 使用 `@dataclass` 定义 `ToolDescription` 和 `ToolParam`。`ToolDescription` 包含 name、file_path、description (evolvable)、params: list[ToolParam]。`ToolParam` 区分 frozen 字段（name, type, required, enum）和 evolvable 字段（description）
- **D-08:** 提供 `to_dict()` / `from_dict()` 序列化方法，和 Phase 1 的 `EvalExample`、`FitnessScore` 等保持一致

### Claude's Discretion
- 正则表达式的具体模式设计，包括处理字符串拼接、命名常量等边界情况的策略
- `ToolDescription` dataclass 的具体字段设计细节（例如是否包含 raw_source、line_number 等辅助字段）
- 文件发现逻辑（哪些 `*.py` 文件包含工具定义，哪些是辅助模块如 `registry.py`、`__init__.py`）

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOOL-01 | Pipeline can extract tool descriptions from hermes-agent's tools/*.py files via regex parsing | 已完成对 53 个工具文件的格式审计，识别出 4 种描述格式模式，22 个包含 `registry.register()` 的文件，以及可靠的 schema 常量命名模式 |
| TOOL-02 | Pipeline can write evolved descriptions back to files preserving schema structure (param names, types, required fields frozen) | 基于格式模式分析，设计了 format-preserving 写回策略：记录原始格式类型，写回时按原格式重建描述字符串 |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Architecture**: 严格遵循 Phase 1 的代码模式和目录结构
- **Dependency**: 不引入新的外部依赖，复用现有 DSPy/Click/Rich 栈
- **hermes-agent**: 只读访问，通过 HERMES_AGENT_REPO 环境变量定位
- **Size**: 工具描述 <= 500 chars，参数描述 <= 200 chars
- **Code location**: `evolution/tools/` 包（已有占位 `__init__.py`）
- **Test location**: `tests/` 目录，文件名 `test_*.py`
- **Conventions**: snake_case 函数/变量，PascalCase 类名，@dataclass + to_dict/from_dict，Rich Console 输出

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python `re` | stdlib | 正则表达式解析工具描述 | Phase 1 已用于 skill frontmatter 解析，零依赖 [VERIFIED: codebase grep] |
| Python `pathlib` | stdlib | 文件路径操作 | Phase 1 统一使用 Path 对象 [VERIFIED: codebase grep] |
| Python `dataclasses` | stdlib | ToolDescription/ToolParam 数据结构 | Phase 1 统一模式 (ConstraintResult, EvalExample, FitnessScore) [VERIFIED: codebase grep] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `evolution.core.config` | local | `get_hermes_agent_path()` 定位 hermes-agent | 发现 tools/ 目录时 [VERIFIED: codebase] |
| `rich` | >=13.0 | Console 输出（如发现摘要、解析警告） | 用于 CLI 输出和调试信息 [VERIFIED: codebase] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| 正则解析 | Python AST (`ast` module) | AST 能可靠解析 Python 语法但无法保持原始格式（写回时会重格式化）；正则虽脆弱但保留原始格式，且与 D-05 最小化 diff 噪音的决策一致 |
| 正则解析 | `lib2to3` / `libcst` | 保留格式的 AST，但这是外部依赖（libcst）或不稳定 API（lib2to3），违反不引入新依赖的约束 |

**Installation:**
```bash
# 无需安装额外依赖 — 全部使用 stdlib + 已有项目依赖
```

## Architecture Patterns

### Recommended Project Structure
```
evolution/
├── tools/
│   ├── __init__.py           # 已存在的占位包
│   ├── tool_loader.py        # 提取 + 写回逻辑（本 Phase 主文件）
│   └── ...                   # Phase 3+ 的文件
tests/
├── tools/                    # 新建测试目录
│   ├── __init__.py
│   └── test_tool_loader.py   # 提取和写回的测试
```

### Pattern 1: Schema Discovery (文件发现)
**What:** 扫描 hermes-agent `tools/` 目录，识别包含工具定义的 Python 文件
**When to use:** 作为提取管道的第一步
**Example:**
```python
# Source: hermes-agent/tools/ 审计结果 [VERIFIED: codebase grep]
def discover_tool_files(hermes_agent_path: Path) -> list[Path]:
    """Find *.py files containing tool schemas in hermes-agent/tools/."""
    tools_dir = hermes_agent_path / "tools"
    # 排除已知的辅助模块
    EXCLUDE = {"__init__.py", "registry.py", "debug_helpers.py",
               "ansi_strip.py", "binary_extensions.py", "approval.py",
               "budget_config.py", "credential_files.py", "env_passthrough.py",
               "fuzzy_match.py", "interrupt.py", "patch_parser.py",
               "url_safety.py", "website_policy.py", "tool_backend_helpers.py",
               "tool_result_storage.py", "voice_mode.py",
               "browser_camofox.py", "browser_camofox_state.py",
               "managed_tool_gateway.py", "mcp_oauth.py",
               "skills_guard.py", "skills_hub.py", "skills_sync.py",
               "checkpoint_manager.py", "openrouter_client.py",
               "osv_check.py", "tirith_security.py", "neutts_synth.py",
               "file_operations.py"}
    # 更可靠的方式：grep 有 registry.register() 的文件
    result = []
    for py_file in sorted(tools_dir.glob("*.py")):
        if py_file.name in EXCLUDE:
            continue
        content = py_file.read_text()
        if "registry.register(" in content:
            result.append(py_file)
    return result
```

### Pattern 2: Description Format Detection & Extraction
**What:** 识别描述字段的 4 种格式并提取纯文本值
**When to use:** 解析每个 schema dict 中的 description 字段
**Formats found:** [VERIFIED: hermes-agent codebase audit]

| Format | Count | Example Files |
|--------|-------|---------------|
| 单行字符串 `"desc": "text"` | 大多数 param descriptions | file_tools.py, web_tools.py |
| 括号内字符串拼接 `"desc": ("a " "b ")` | 10 个文件的 top-level descriptions | memory_tool.py, clarify_tool.py |
| 三引号字符串 `"desc": """text"""` | 1 个文件 | cronjob_tools.py |
| 变量引用 `"desc": VAR_NAME` | 1 个文件 | terminal_tool.py |

**Example:**
```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class DescFormat(Enum):
    """Description field format in source code."""
    SINGLE_LINE = "single_line"       # "description": "text"
    PAREN_CONCAT = "paren_concat"     # "description": ("a " "b ")
    TRIPLE_QUOTE = "triple_quote"     # "description": """text"""
    VARIABLE_REF = "variable_ref"     # "description": VAR_NAME

@dataclass
class ToolParam:
    """A tool parameter — frozen schema fields + evolvable description."""
    # Frozen fields (never modified)
    name: str
    type: str
    required: bool = False
    enum: Optional[list[str]] = None
    # Evolvable field
    description: str = ""
    # Source tracking for write-back
    desc_format: DescFormat = DescFormat.SINGLE_LINE
    desc_line_offset: int = 0  # line number within file

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "required": self.required,
            "enum": self.enum,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ToolParam":
        return cls(
            name=d["name"],
            type=d["type"],
            required=d.get("required", False),
            enum=d.get("enum"),
            description=d.get("description", ""),
        )

@dataclass
class ToolDescription:
    """A tool's full description — top-level + parameters."""
    name: str
    file_path: Path
    description: str  # evolvable top-level description
    params: list[ToolParam] = field(default_factory=list)
    # Source tracking for write-back
    desc_format: DescFormat = DescFormat.SINGLE_LINE
    schema_var_name: str = ""  # e.g. "MEMORY_SCHEMA"
    raw_source: str = ""  # original file content for write-back

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "file_path": str(self.file_path),
            "description": self.description,
            "params": [p.to_dict() for p in self.params],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ToolDescription":
        return cls(
            name=d["name"],
            file_path=Path(d["file_path"]),
            description=d["description"],
            params=[ToolParam.from_dict(p) for p in d.get("params", [])],
        )
```

### Pattern 3: Format-Preserving Write-Back
**What:** 将进化后的描述写回文件，保持原始格式
**When to use:** 将优化后的描述替换原文件中的描述文本
**Key insight:** 写回核心是 "定位原始描述字符串在源代码中的位置 -> 替换为同格式的新描述"

```python
def write_back_description(
    file_path: Path,
    tool: ToolDescription,
    new_description: str,
    param_name: Optional[str] = None,
) -> str:
    """Replace a description in the source file, preserving format."""
    source = file_path.read_text()
    if param_name:
        # 替换参数描述 — 定位到具体参数的 "description" 字段
        target_param = next(p for p in tool.params if p.name == param_name)
        old_desc = target_param.description
        fmt = target_param.desc_format
    else:
        # 替换 top-level 描述
        old_desc = tool.description
        fmt = tool.desc_format

    # 根据格式类型构建替换字符串
    # ... format-specific replacement logic ...
    return new_source
```

### Anti-Patterns to Avoid
- **exec/eval 解析:** 不要用 `exec()` 或 `eval()` 来解析 schema dict -- 工具文件有大量 import 和副作用，不能安全执行
- **AST 写回:** 不要用 `ast.parse()` 再 `ast.unparse()` -- 会丢失原始格式，产生大量 diff 噪音
- **全文件 regex:** 不要用单个 regex 匹配整个 schema dict -- 嵌套结构太复杂，用分层解析更可靠
- **硬编码 schema 名:** 不要硬编码 `MEMORY_SCHEMA` 等常量名 -- 通过 `registry.register(schema=XXX)` 的引用来动态发现

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Python 字符串拼接求值 | 手写 concat parser | `ast.literal_eval()` on the parenthesized expression | 安全可靠地将 `("a " "b " "c")` 求值为 `"a b c"` |
| 三引号字符串解析 | 手写 triple-quote parser | `ast.literal_eval()` | 正确处理转义字符、换行 |
| 文件路径发现 | 硬编码文件列表 | `Path.glob("*.py")` + grep "registry.register" | 新增工具文件时自动发现 |
| JSON 序列化 | 手写 serializer | `json.dumps()` / `json.loads()` | 项目统一 JSONL 序列化模式 |

**Key insight:** `ast.literal_eval()` 可以安全求值 Python 字符串字面量（包括拼接、三引号），但不能求值变量引用。对于 `"description": TERMINAL_TOOL_DESCRIPTION` 这种情况，需要先找到变量定义再求值。

## Common Pitfalls

### Pitfall 1: 字符串拼接格式多样性
**What goes wrong:** 假设所有 description 都是简单的单行字符串，遗漏括号内隐式拼接和三引号格式
**Why it happens:** 53 个工具文件中格式不统一
**How to avoid:** 解析 `"description":` 后面的值时，检测 `(` 开头（拼接）、`"""` 开头（三引号）、大写字母开头（变量引用）三种特殊情况
**Warning signs:** 提取到的描述被截断或包含语法字符如 `("`

### Pitfall 2: 嵌套 dict 中的 description 定位
**What goes wrong:** top-level description 和 param description 共用 `"description"` key，正则匹配到错误位置
**Why it happens:** `"description"` 在一个 schema dict 中出现多次（top-level + 每个 param）
**How to avoid:** 用分层策略：先定位 schema 变量 -> 找 top-level description -> 进入 `"properties"` -> 找每个 param 的 description。利用缩进层级或 brace 计数区分层级
**Warning signs:** 写回时替换了错误的 description 字段

### Pitfall 3: browser_tool.py 的 list-of-schemas 模式
**What goes wrong:** 预期每个文件有独立的 `XXX_SCHEMA = {` 命名常量，但 browser_tool.py 使用 `BROWSER_TOOL_SCHEMAS = [...]` 列表
**Why it happens:** 10 个 browser 工具共享一个 list 常量
**How to avoid:** 处理两种 schema 定义模式：单个 dict 常量（如 `MEMORY_SCHEMA = {`）和 list 常量（如 `BROWSER_TOOL_SCHEMAS = [`）
**Warning signs:** browser 相关工具完全没有被提取

### Pitfall 4: MCP 动态注册工具
**What goes wrong:** 试图解析 `mcp_tool.py` 的动态注册（f-string schema, runtime 构建）
**Why it happens:** MCP 工具的 schema 是运行时从 MCP 服务器动态获取的，不是静态定义
**How to avoid:** 明确排除 `mcp_tool.py` -- MCP 工具的描述来自外部服务器，不在进化范围内
**Warning signs:** 解析 mcp_tool.py 时遇到 f-string 或动态构建的 schema

### Pitfall 5: 写回时破坏 Python 语法
**What goes wrong:** 新描述包含未转义的引号或特殊字符，写回后文件无法 `python -c "import ..."`
**Why it happens:** 进化后的描述可能包含单引号、双引号、反斜杠、换行等
**How to avoid:** 写回前对新描述做字符转义（按原格式类型转义），写回后做 `py_compile.compile()` 验证
**Warning signs:** 写回后文件的 `python -c "compile(...)"` 失败

### Pitfall 6: registry.py 中的 fallback description
**What goes wrong:** `registry.register()` 的 `description` 参数 和 schema dict 中的 `description` 可能不同
**Why it happens:** `registry.py` line 88: `description=description or schema.get("description", "")` -- 如果 register() 传了 description 参数，它会覆盖 schema 中的
**How to avoid:** 提取和进化 schema dict 中的 description（这是发送给 LLM API 的实际值），register() 的 description 参数主要用于 UI 显示
**Warning signs:** 进化了 schema description 但实际运行时使用的是 register() 的 description

## Code Examples

### Schema 常量发现 [VERIFIED: hermes-agent codebase]
```python
import re

# 匹配 XXX_SCHEMA = { 模式的命名常量
SCHEMA_VAR_PATTERN = re.compile(
    r'^([A-Z][A-Z0-9_]*_SCHEMA(?:S)?)\s*=\s*[\[{]',
    re.MULTILINE,
)

def find_schema_variables(source: str) -> list[tuple[str, int]]:
    """Find schema variable definitions and their line positions."""
    results = []
    for match in SCHEMA_VAR_PATTERN.finditer(source):
        var_name = match.group(1)
        line_num = source[:match.start()].count('\n') + 1
        results.append((var_name, line_num))
    return results
```

### Description 值提取 [ASSUMED -- regex 设计是 discretion 范围]
```python
def extract_description_value(source: str, start_pos: int) -> tuple[str, DescFormat, int, int]:
    """Extract description value starting after '"description":'.

    Returns: (text, format, start_offset, end_offset)
    """
    # Skip whitespace after colon
    pos = start_pos
    while pos < len(source) and source[pos] in ' \t':
        pos += 1

    char = source[pos]

    if char == '(':
        # Parenthesized string concatenation
        # Find matching close paren, then ast.literal_eval the content
        ...
        return text, DescFormat.PAREN_CONCAT, pos, end_pos

    elif source[pos:pos+3] == '"""':
        # Triple-quoted string
        end = source.index('"""', pos + 3)
        raw = source[pos:end + 3]
        text = ast.literal_eval(raw)
        return text, DescFormat.TRIPLE_QUOTE, pos, end + 3

    elif char == '"':
        # Single-line string
        # Find closing quote (handling escapes)
        raw = ...  # extract quoted string
        text = ast.literal_eval(raw)
        return text, DescFormat.SINGLE_LINE, pos, end_pos

    elif char.isupper():
        # Variable reference — resolve it
        var_name = re.match(r'[A-Z_]+', source[pos:]).group()
        # Find variable definition elsewhere in file
        ...
        return text, DescFormat.VARIABLE_REF, pos, pos + len(var_name)
```

### Round-Trip 测试模式 [VERIFIED: Phase 1 test_skill_module.py 模式]
```python
def test_roundtrip(self, tmp_path):
    """Extract -> modify -> write back -> extract again = modification persists."""
    # 1. 创建一个包含工具 schema 的模拟 .py 文件
    tool_file = tmp_path / "test_tool.py"
    tool_file.write_text(SAMPLE_TOOL_SOURCE)

    # 2. 提取
    tools = extract_tool_descriptions(tool_file)
    original_desc = tools[0].description

    # 3. 修改描述
    new_desc = "EVOLVED: " + original_desc

    # 4. 写回
    write_back_description(tool_file, tools[0], new_desc)

    # 5. 再次提取，验证修改持久化
    tools_after = extract_tool_descriptions(tool_file)
    assert tools_after[0].description == new_desc

    # 6. 验证 schema 结构不变
    assert tools_after[0].params == tools[0].params  # frozen fields identical
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Phase 1: YAML frontmatter 解析 | Phase 2: Python dict 字面量解析 | 本次 | 更复杂，需要处理 Python 语法的多种字符串格式 |
| 简单 split("---") | 正则 + ast.literal_eval | 本次 | 需要分层解析策略，但更健壮 |

## hermes-agent 工具文件格式审计

通过对 hermes-agent 仓库的实际审计得出以下结论 [VERIFIED: codebase grep + file reading]:

### 文件统计
- **总文件数:** 53 个 `tools/*.py` 文件
- **包含 `registry.register()` 的文件:** 22 个
- **总 register() 调用数:** ~50 个（含 browser_tool.py 的 10 个和 rl_training_tool.py 的 10 个）
- **MCP 动态注册（排除）:** mcp_tool.py 的 3 个动态注册

### Schema 定义模式
| 模式 | 文件数 | 示例 |
|------|--------|------|
| 单个 `XXX_SCHEMA = {` 常量 | 20 | `MEMORY_SCHEMA`, `TODO_SCHEMA`, `CLARIFY_SCHEMA` |
| List `XXX_SCHEMAS = [...]` | 1 | `BROWSER_TOOL_SCHEMAS`（browser_tool.py，包含 10 个 schema） |
| 多个独立常量在同一文件 | 3 | file_tools.py (4 个), web_tools.py (2 个), skills_tool.py (2 个) |

### Description 格式统计
| 格式 | Top-level | Param-level | 示例 |
|------|-----------|-------------|------|
| 单行字符串 `"text"` | 大多数短描述 | 绝大多数 | `"The search query to look up on the web"` |
| 括号内拼接 `("a " "b ")` | 10 个文件 | 少量 | memory_tool.py, clarify_tool.py, delegate_tool.py |
| 三引号 `"""text"""` | 1 个文件 | 0 | cronjob_tools.py |
| 变量引用 `VAR_NAME` | 1 个文件 | 0 | terminal_tool.py -> `TERMINAL_TOOL_DESCRIPTION` |

### 需要排除的文件
以下文件不包含工具定义，但在 `tools/` 目录中：
`__init__.py`, `registry.py`, `debug_helpers.py`, `ansi_strip.py`, `binary_extensions.py`, `approval.py`, `budget_config.py`, `credential_files.py`, `env_passthrough.py`, `fuzzy_match.py`, `interrupt.py`, `patch_parser.py`, `url_safety.py`, `website_policy.py`, `tool_backend_helpers.py`, `tool_result_storage.py`, `voice_mode.py`, `browser_camofox.py`, `browser_camofox_state.py`, `managed_tool_gateway.py`, `mcp_oauth.py`, `skills_guard.py`, `skills_hub.py`, `skills_sync.py`, `checkpoint_manager.py`, `openrouter_client.py`, `osv_check.py`, `tirith_security.py`, `neutts_synth.py`, `file_operations.py`

**推荐发现策略:** 不用排除列表，而是检测文件内容中是否有 `registry.register(` 调用 + `_SCHEMA` 常量定义来判断。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `ast.literal_eval()` 可以安全求值所有遇到的 description 字符串格式（括号拼接、三引号） | Don't Hand-Roll | 如果有边界情况（如包含表达式而非纯字面量），需要 fallback 到纯正则解析 -- 低风险 |
| A2 | 所有实际发送给 OpenAI API 的工具描述都来自 schema dict 的 `"description"` 字段而非 `registry.register()` 的 `description` 参数 | Pitfall 6 | 如果 API 使用 register 参数的 description，则进化效果不会生效 -- 中风险，需验证 `get_definitions()` 方法 |
| A3 | 进化管道只需要处理静态定义的工具（不含 MCP 动态工具） | Pitfall 4 | 低风险 -- MCP 工具描述来自外部服务器，不在本项目控制范围 |

**A2 验证:** 检查 `registry.py` line 141: `schema_with_name = {**entry.schema, "name": entry.name}` -- `get_definitions()` 返回的是 `entry.schema`，即传入 register 的 schema dict 原始内容。schema dict 中的 `"description"` 就是发送给 API 的值。但 `ToolEntry` 也有一个 `description` 属性（line 88: `description=description or schema.get("description", "")`），仅用于 UI 显示。**结论：进化 schema dict 中的 description 是正确的。** [VERIFIED: registry.py source code]

## Open Questions

1. **browser_tool.py 的 list 模式解析策略**
   - What we know: `BROWSER_TOOL_SCHEMAS = [...]` 包含 10 个 schema dict 的列表
   - What's unclear: 是否值得用 `ast.literal_eval()` 解析整个列表（可能太大），还是逐个用正则提取
   - Recommendation: 用正则先分割 list 为单个 dict 块，再逐个解析。或者跳过 list 解析，按 `"name":` 和 `"description":` 在 list 内定位

2. **rl_training_tool.py 的 10 个 schema 变量**
   - What we know: 每个 RL 工具有独立的 `RL_XXX_SCHEMA = {` 常量
   - What's unclear: 这些工具是否活跃使用（RL 工具可能是实验性的）
   - Recommendation: 一视同仁，全部提取 -- 让下游 Phase 决定哪些值得优化

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=7.0 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/python -m pytest tests/tools/ -x -q` |
| Full suite command | `.venv/bin/python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TOOL-01 | 从 tools/*.py 提取 top-level description | unit | `.venv/bin/python -m pytest tests/tools/test_tool_loader.py::TestExtract -x` | Wave 0 |
| TOOL-01 | 从 tools/*.py 提取 per-param description | unit | `.venv/bin/python -m pytest tests/tools/test_tool_loader.py::TestExtractParams -x` | Wave 0 |
| TOOL-01 | 处理 4 种描述格式（单行/拼接/三引号/变量引用） | unit | `.venv/bin/python -m pytest tests/tools/test_tool_loader.py::TestDescFormats -x` | Wave 0 |
| TOOL-02 | 写回 top-level description 保持格式 | unit | `.venv/bin/python -m pytest tests/tools/test_tool_loader.py::TestWriteBack -x` | Wave 0 |
| TOOL-02 | 写回 param description 保持格式 | unit | `.venv/bin/python -m pytest tests/tools/test_tool_loader.py::TestWriteBackParam -x` | Wave 0 |
| TOOL-02 | Round-trip: extract -> modify -> write -> extract = modification | integration | `.venv/bin/python -m pytest tests/tools/test_tool_loader.py::TestRoundTrip -x` | Wave 0 |
| TOOL-02 | 写回后 schema 结构不变（param names/types/required 冻结） | unit | `.venv/bin/python -m pytest tests/tools/test_tool_loader.py::TestSchemaPreservation -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest tests/tools/ -x -q`
- **Per wave merge:** `.venv/bin/python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/tools/__init__.py` -- 新建测试包
- [ ] `tests/tools/test_tool_loader.py` -- 覆盖 TOOL-01 和 TOOL-02 的所有测试
- [ ] pytest 安装: `.venv/bin/pip install pytest` -- venv 中未安装 pytest

## Security Domain

本 Phase 不涉及安全关键操作：
- hermes-agent 仓库只读访问
- 不执行外部代码
- 不处理用户输入或网络请求
- 唯一风险：进化后的描述可能包含注入文本，但这属于 Phase 5 (TOOL-09 约束检查) 的范围

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A |
| V3 Session Management | no | N/A |
| V4 Access Control | no | N/A |
| V5 Input Validation | minimal | `py_compile.compile()` 验证写回后文件语法正确 |
| V6 Cryptography | no | N/A |

## Sources

### Primary (HIGH confidence)
- hermes-agent `tools/` 目录 (~/.hermes/hermes-agent/tools/) -- 53 个文件全部审计
- hermes-agent `tools/registry.py` -- ToolRegistry.register() 和 get_definitions() 完整阅读
- hermes-agent `tools/memory_tool.py`, `clarify_tool.py`, `file_tools.py`, `web_tools.py`, `terminal_tool.py`, `browser_tool.py`, `cronjob_tools.py`, `todo_tool.py` -- schema 格式样本
- `evolution/skills/skill_module.py` -- Phase 1 loader 模式参考
- `evolution/core/config.py` -- hermes-agent 路径发现逻辑
- `tests/skills/test_skill_module.py` -- Phase 1 测试模式参考

### Secondary (MEDIUM confidence)
- Python `ast.literal_eval()` 文档 -- 用于安全求值字符串字面量 [ASSUMED: 基于 Python 标准库知识]

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- 全部使用 stdlib，零外部依赖
- Architecture: HIGH -- 基于 Phase 1 已验证模式，加上对 hermes-agent 工具文件的完整审计
- Pitfalls: HIGH -- 基于实际代码审计发现的真实格式多样性

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (hermes-agent 工具格式稳定，除非有重大重构)
