# Phase 3: Tool Module - Research

**Researched:** 2026-04-16
**Domain:** DSPy Module design / GEPA optimizer parameter system
**Confidence:** HIGH

## Summary

Phase 3 的核心任务是将 Phase 2 提取的所有工具描述（~50 个工具）包装为一个 GEPA 可优化的 DSPy 模块 `ToolModule`。研究的关键发现是 **DSPy 的参数系统基于 `Predict` 实例**——GEPA 通过 `named_predictors()` 发现可优化参数，每个 `Predict` 实例的 Signature instructions（即 docstring）是 GEPA 实际修改的文本。

这意味着 CONTEXT.md 中 D-04 决定的"每个工具描述作为独立可优化参数"需要通过 **per-tool `dspy.Predict` 实例** 来实现，而不是简单的字符串属性。每个 Predict 实例的 Signature instructions 存储对应工具的 description 文本，GEPA 通过 `round_robin` 组件选择器循环优化各个工具的描述。`forward()` 从所有 Predict 实例中提取当前描述文本，组装工具列表后传给一个专门的 tool-selection ChainOfThought predictor。

**Primary recommendation:** 使用 dict 存储 per-tool Predict 实例（`self.tool_predictors = {"memory": Predict(...), ...}`），加一个 `self.selector = ChainOfThought(ToolSelectionSignature)` 做工具选择推理。GEPA 的 `named_parameters()` 会自动发现 dict 中的所有 Predict 实例。

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** 所有工具描述打包进一个 `ToolModule(dspy.Module)` 类，GEPA 一次优化所有描述。和需求 TOOL-03「单一 DSPy 可优化模块」直接对应。不做 per-tool 或 per-group 拆分。
- **D-02:** `forward(task_input, tool_descriptions)` 模拟工具选择场景——给定任务描述和所有可用工具描述列表，输出选择的工具名称。这直接和 Phase 4 的 binary tool selection metric 对接。
- **D-03:** 和 Phase 1 的 `SkillModule` 模式类似，使用 `dspy.ChainOfThought` 做推理，但 Signature 是工具选择专用的（不是通用任务完成）。
- **D-04:** 每个工具的 top-level description 是一个独立的可优化参数（如 `self.tool_memory_desc = "..."`），GEPA 可以细粒度地独立修改每个工具的描述文本。参数数量 = 工具数量（~50 个）。
- **D-05:** 参数暴露只包含 description 文本，不包含 param descriptions（per-parameter 描述优化推迟到 v2, TOOL-V2-02）。
- **D-06:** 设计级隔离——GEPA 只能看到和修改 description 文本参数。param names, types, required, enum 等 frozen 字段根本不作为参数暴露，优化器物理上无法触碰。写回时使用 `ToolDescription` 的 frozen 字段原值重建 schema，保证结构不变。

### Claude's Discretion
- `ToolModule` 的 DSPy Signature 内部类设计（字段名、desc 文本）
- 工具描述参数的命名约定（如 `tool_{name}_desc` 或其他方式）
- 从 `ToolDescription` 列表构建模块参数的具体实现方式
- forward() 输出格式的具体 Signature 设计

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOOL-03 | All tool descriptions wrapped as a single DSPy-optimizable module for joint optimization | DSPy `named_parameters()` 自动发现 dict 中的 Predict 实例；GEPA `compile()` 一次处理整个模块的所有 predictors |
| TOOL-04 | Schema structure (param names, types, required) stays frozen — only description text evolves | per-tool Predict 实例的 Signature instructions 只包含 description 文本；frozen 字段存储在 `ToolDescription` dataclass 中，不进入 DSPy 参数系统 |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dspy | >=3.0.0 (latest 3.1.3) | DSPy Module/Predict/Signature/GEPA 框架 | 项目核心依赖 [VERIFIED: pip index] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| rich | >=13.0 | Console 输出格式化 | 日志和调试输出 [VERIFIED: existing codebase pattern] |

No new dependencies needed. Phase 3 only uses existing dspy and rich.

## Architecture Patterns

### Recommended Project Structure
```
evolution/
├── tools/
│   ├── __init__.py
│   ├── tool_loader.py        # Phase 2: 提取/写回 (已完成)
│   └── tool_module.py        # Phase 3: DSPy 模块包装 (NEW)
tests/
└── tools/
    ├── test_tool_loader.py    # Phase 2 测试 (已有)
    └── test_tool_module.py    # Phase 3 测试 (NEW)
```

### Pattern 1: Per-Tool Predict Dict + Selector Predictor

**What:** 每个工具的 description 存储在一个独立的 `dspy.Predict` 实例的 Signature instructions 中。一个额外的 `ChainOfThought` predictor 负责实际的 tool selection 推理。

**When to use:** 需要 GEPA 独立优化每个工具描述时（D-04）。

**Why this works with GEPA:** [VERIFIED: DSPy source code]
1. `BaseModule.named_parameters()` 遍历 `self.__dict__`，对 dict 类型递归检查每个值
2. `Predict` 继承自 `Parameter`，所以会被 `named_parameters()` 发现
3. GEPA 的 `compile()` 调用 `student.named_predictors()` 获取所有 Predict 实例
4. 种子候选构建: `seed_candidate = {name: pred.signature.instructions for name, pred in student.named_predictors()}`
5. GEPA 使用 `component_selector`（默认 round_robin）选择每步优化哪些组件
6. 优化后通过 `pred.signature = pred.signature.with_instructions(candidate[name])` 写回

**Example:**
```python
# Source: Verified from DSPy source code analysis
import dspy
from evolution.tools.tool_loader import ToolDescription, discover_tool_files, extract_tool_descriptions


class ToolSelectionSignature(dspy.Signature):
    """Given a task and available tools, select the most appropriate tool.

    Analyze the task requirements and match them to the tool whose
    description best fits the task.
    """
    task_description: str = dspy.InputField(
        desc="The task that needs to be accomplished"
    )
    available_tools: str = dspy.InputField(
        desc="Formatted list of available tools with descriptions"
    )
    selected_tool: str = dspy.OutputField(
        desc="The name of the selected tool"
    )


class ToolModule(dspy.Module):
    """Wraps all tool descriptions as GEPA-optimizable parameters.

    Each tool's description is stored as a Predict instance's Signature
    instructions. GEPA can independently optimize each tool's description
    text while schema structure remains frozen.
    """

    def __init__(self, tool_descriptions: list[ToolDescription]):
        super().__init__()

        # Per-tool Predict instances — descriptions stored as instructions
        # GEPA discovers these via named_parameters() -> dict traversal
        self.tool_predictors = {}
        self._tool_names = []  # preserve ordering
        for td in tool_descriptions:
            safe_name = td.name.replace("-", "_")
            # Create a minimal Predict with the description as instructions
            sig = dspy.Signature(
                "tool_name -> confirmation",
                instructions=td.description,
            )
            self.tool_predictors[safe_name] = dspy.Predict(sig)
            self._tool_names.append(td.name)

        # Store frozen schema data (NOT optimizable)
        self._frozen_tools = {td.name: td for td in tool_descriptions}

        # Tool selection predictor
        self.selector = dspy.ChainOfThought(ToolSelectionSignature)

    def forward(self, task_description: str) -> dspy.Prediction:
        # Assemble current descriptions from all tool predictors
        tool_list_parts = []
        for name in self._tool_names:
            safe_name = name.replace("-", "_")
            pred = self.tool_predictors[safe_name]
            desc = pred.signature.instructions
            tool_list_parts.append(f"- {name}: {desc}")
        available_tools = "\n".join(tool_list_parts)

        # Run tool selection
        result = self.selector(
            task_description=task_description,
            available_tools=available_tools,
        )
        return dspy.Prediction(selected_tool=result.selected_tool)

    def get_evolved_descriptions(self) -> dict[str, str]:
        """Extract current (possibly evolved) descriptions from predictors."""
        evolved = {}
        for name in self._tool_names:
            safe_name = name.replace("-", "_")
            pred = self.tool_predictors[safe_name]
            evolved[name] = pred.signature.instructions
        return evolved
```

### Pattern 2: SkillModule Consistency Pattern (from Phase 1)

**What:** 遵循 `SkillModule` 的结构模式：inner Signature class + ChainOfThought + forward()。

**Reference:** `evolution/skills/skill_module.py` lines 84-114 [VERIFIED: codebase]

**Key differences from SkillModule:**
- SkillModule: 1 个 string parameter（skill_text），1 个 predictor
- ToolModule: N 个 Predict 实例（per-tool descriptions），1 个 selector predictor
- SkillModule: forward() 做任务完成
- ToolModule: forward() 做工具选择（输出工具名称）

### Pattern 3: Schema Freeze by Design Isolation

**What:** Frozen schema 字段（param names, types, required, enum）存储在 `self._frozen_tools` dict 中（以 `_` 开头的私有属性），不参与 DSPy 参数系统。只有 `self.tool_predictors` dict 中的 Predict 实例被 GEPA 发现和优化。

**Why it works:** [VERIFIED: DSPy source code]
- `named_parameters()` 只寻找 `Parameter` 实例
- `ToolDescription` 是 dataclass，不继承 `Parameter`
- 以 `_` 开头的属性虽然会被遍历，但其值（dict of ToolDescription）不是 Parameter 类型，会被跳过

### Anti-Patterns to Avoid
- **Plain string attributes as optimizable params:** `self.tool_memory_desc = "..."` 不会被 GEPA 发现，因为 str 不是 `Parameter` 子类。必须用 `Predict` 实例包装。[VERIFIED: DSPy source code — BaseModule.named_parameters() 只检查 Parameter 实例]
- **One huge Predict with all descriptions:** 将 50 个工具描述放在一个 Signature instructions 里，GEPA 会作为整体优化，无法独立调整单个工具。违反 D-04。
- **Calling per-tool predictors in forward():** 如果在 forward() 中调用 50 个 Predict 实例，会产生 50 次 LLM 调用。per-tool Predict 仅作为参数容器使用，不参与 forward() 调用。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DSPy 参数发现 | 自定义参数注册机制 | `dspy.Predict` + dict 存储 | `named_parameters()` 已支持 dict 遍历 [VERIFIED: source code] |
| Signature instructions 更新 | 手动修改 `__doc__` | `sig.with_instructions(text)` | DSPy API 保证正确创建新 Signature 类 [VERIFIED: source code] |
| 工具描述提取/写回 | 新的文件 I/O | Phase 2 的 `tool_loader.py` | 已有完整的提取/写回管道 [VERIFIED: codebase] |

## Common Pitfalls

### Pitfall 1: Predict 实例命名冲突
**What goes wrong:** 工具名称包含连字符（如 `list-files`），dict key 中的连字符可能导致 `magicattr` 属性解析问题。
**Why it happens:** DSPy 使用 `magicattr` 来解析嵌套属性路径（如 `tool_predictors['list-files'].predict`）。
**How to avoid:** 在 dict key 中将连字符替换为下划线：`safe_name = td.name.replace("-", "_")`。保留原始名称在 `_tool_names` 列表中。
**Warning signs:** GEPA 无法定位特定 predictor；`named_predictors()` 返回不完整列表。

### Pitfall 2: 空 Signature instructions
**What goes wrong:** 某些工具可能有空的 description 文本，导致 Predict 实例的 Signature instructions 为空字符串。
**Why it happens:** Phase 2 提取时某些工具确实没有 top-level description。
**How to avoid:** 在 `__init__` 中为空描述提供默认值，如 `f"Tool: {td.name}"`。确保 GEPA 有文本可以优化。
**Warning signs:** GEPA 反射时无法为某些组件生成有意义的改进。

### Pitfall 3: Selector Predictor 也被 GEPA 优化
**What goes wrong:** GEPA 的 round_robin 会优化 `self.selector`（ToolSelectionSignature 的 instructions），这不是我们想优化的。
**Why it happens:** `named_predictors()` 发现所有 Predict 实例，包括 selector。
**How to avoid:** 两种策略：
1. 接受 selector 也被优化（可能有益，instructions 变得更好）
2. 用 `self.selector._compiled = True` 标记为已编译，`named_parameters()` 会跳过已编译的子模块
**Warning signs:** GEPA 日志显示正在优化 selector 而不是工具描述。

### Pitfall 4: ~50 个 Predict 实例的 round_robin 效率
**What goes wrong:** 默认 round_robin 策略每步只优化一个组件。50 个工具需要 50 步才能遍历一轮。
**Why it happens:** GEPA 的 `component_selector='round_robin'` 按顺序选择组件。
**How to avoid:** 考虑使用 `component_selector='all'`（同时优化所有组件）或增加 `max_steps`。
**Warning signs:** 大部分工具描述在优化后没有变化。

### Pitfall 5: get_evolved_descriptions 和 ToolDescription 重建
**What goes wrong:** 提取进化后的描述后忘记合并回 frozen schema 数据，导致写回时丢失 param names/types。
**Why it happens:** 进化后的文本只是字符串，需要和原始 `ToolDescription` 的 frozen 字段重新组合。
**How to avoid:** `get_evolved_descriptions()` 返回 `list[ToolDescription]`，复用原始 frozen 字段并替换 description。
**Warning signs:** 写回后的工具文件缺少 parameters 块。

## Code Examples

### 从 ToolDescription 列表创建 ToolModule
```python
# Source: Verified DSPy parameter system from source code
from pathlib import Path
from evolution.core.config import get_hermes_agent_path
from evolution.tools.tool_loader import discover_tool_files, extract_tool_descriptions

# Load all tool descriptions
hermes_path = get_hermes_agent_path()
tool_files = discover_tool_files(hermes_path)
all_tools = []
for f in tool_files:
    all_tools.extend(extract_tool_descriptions(f))

# Create module
module = ToolModule(all_tools)

# Check GEPA can see all parameters
predictors = module.named_predictors()
print(f"Optimizable predictors: {len(predictors)}")
# Expected: len(all_tools) + 1 (selector)
```

### 提取进化后的描述并写回
```python
# Source: Codebase pattern from evolve_skill.py
from evolution.tools.tool_loader import write_back_description

# After GEPA optimization
evolved_module = optimizer.compile(module, trainset=trainset, valset=valset)

# Extract evolved descriptions
evolved_descs = evolved_module.get_evolved_descriptions()

# Build ToolDescription objects with frozen fields + evolved text
for tool_name, evolved_text in evolved_descs.items():
    original_td = evolved_module._frozen_tools[tool_name]
    write_back_description(
        original_td.file_path,
        original_td,
        evolved_text,
    )
```

### 冻结 Selector Predictor（可选）
```python
# Source: Verified from DSPy BaseModule.named_parameters() source
class ToolModule(dspy.Module):
    def __init__(self, tool_descriptions):
        super().__init__()
        # ... setup tool_predictors ...
        self.selector = dspy.ChainOfThought(ToolSelectionSignature)
        # Mark selector as compiled so GEPA skips it
        self.selector._compiled = True
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| dspy 2.x optimize_module | dspy 3.x GEPA with `compile()` | DSPy 3.0 (2025) | GEPA 替代 MIPROv2 成为首选优化器 |
| `gepa` 独立包 | `dspy.GEPA` 集成 + `gepa` 包依赖 | DSPy 3.0 | 不需要单独安装 gepa，dspy 自动拉取 |
| Signature 作为类 + docstring | `Signature()` 构造器 + `with_instructions()` | DSPy 3.0+ | 动态创建 Signature 更灵活 [VERIFIED: DSPy source] |

**Deprecated/outdated:**
- DSPy 2.x 的 `BootstrapFewShot` 仍可用但不推荐用于 instruction optimization
- `dspy.Module` 的参数系统没有变化，`Predict` + `Parameter` 模式从 2.x 延续至 3.x

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | ~50 个 Predict 实例在 round_robin 模式下效率可接受 | Common Pitfalls | 如果 GEPA 每步开销大，50步一轮可能太慢；可切换 component_selector='all' |
| A2 | `self._compiled = True` 标记可可靠冻结 selector predictor | Code Examples | 如果 GEPA 实现变化，可能仍然优化 selector；影响不大（selector 优化可能有益） |
| A3 | 工具名称不包含 Python dict key 不兼容的特殊字符（除连字符外） | Pitfalls | 如果工具名包含引号或方括号，可能导致 named_parameters() 路径解析错误 |

## Open Questions

1. **component_selector 策略选择**
   - What we know: GEPA 支持 `round_robin`（默认）和 `all` 两种内置策略 [VERIFIED: source code]
   - What's unclear: 对于 50 个工具描述，哪种策略在有限步数内效果更好
   - Recommendation: 默认使用 `round_robin`，在 Phase 4 的 metric 实现后通过实验决定

2. **Selector predictor 是否应被冻结**
   - What we know: 不冻结 = GEPA 也优化 selector 的 instructions；冻结 = 只优化工具描述
   - What's unclear: 优化 selector instructions 对整体效果的影响
   - Recommendation: 不冻结（保持简单），Phase 4 评估时再决定

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/tools/test_tool_module.py -x` |
| Full suite command | `python -m pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TOOL-03 | ToolModule wraps all descriptions as named_predictors | unit | `python -m pytest tests/tools/test_tool_module.py::TestToolModule::test_named_predictors_count -x` | Wave 0 |
| TOOL-03 | forward() returns tool selection Prediction | unit | `python -m pytest tests/tools/test_tool_module.py::TestToolModule::test_forward_returns_prediction -x` | Wave 0 |
| TOOL-04 | Schema frozen fields not in named_parameters | unit | `python -m pytest tests/tools/test_tool_module.py::TestSchemaFreeze::test_frozen_fields_not_optimizable -x` | Wave 0 |
| TOOL-04 | get_evolved_descriptions preserves frozen schema | unit | `python -m pytest tests/tools/test_tool_module.py::TestSchemaFreeze::test_evolved_descriptions_preserve_schema -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/tools/test_tool_module.py -x`
- **Per wave merge:** `python -m pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/tools/test_tool_module.py` -- covers TOOL-03, TOOL-04
- [ ] DSPy mock/stub strategy -- tests should NOT require LLM API calls; mock `dspy.Predict` and `dspy.ChainOfThought`

## Security Domain

本 Phase 仅涉及 DSPy 模块定义，无外部输入、无网络调用、无文件写入（仅模块构造）。安全风险极低。

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | -- |
| V3 Session Management | no | -- |
| V4 Access Control | no | -- |
| V5 Input Validation | yes (minimal) | ToolDescription 数据来自 Phase 2 的已验证提取管道 |
| V6 Cryptography | no | -- |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| 工具名称注入导致 dict key 异常 | Tampering | sanitize tool names (replace special chars) |

## Sources

### Primary (HIGH confidence)
- DSPy source code (`/tmp/dspy_check/dspy/primitives/base_module.py`) -- `named_parameters()` 实现，确认 dict 遍历和 Parameter 类型检查
- DSPy source code (`/tmp/dspy_check/dspy/predict/parameter.py`) -- `Parameter` 是空基类
- DSPy source code (`/tmp/dspy_check/dspy/predict/predict.py`) -- `Predict(Module, Parameter)` 双继承
- DSPy source code (`/tmp/dspy_check/dspy/predict/chain_of_thought.py`) -- `ChainOfThought` 内部创建 `self.predict = dspy.Predict(...)`
- DSPy source code (`/tmp/dspy_check/dspy/teleprompt/gepa/gepa.py` line 558) -- `seed_candidate = {name: pred.signature.instructions for name, pred in student.named_predictors()}`
- DSPy source code (`/tmp/dspy_check/dspy/teleprompt/gepa/gepa_utils.py` line 141) -- `pred.signature = pred.signature.with_instructions(candidate[name])`
- Existing codebase (`evolution/skills/skill_module.py`) -- Phase 1 SkillModule 参考实现
- Existing codebase (`evolution/tools/tool_loader.py`) -- Phase 2 ToolDescription/ToolParam 数据类

### Secondary (MEDIUM confidence)
- [DSPy GEPA Overview](https://dspy.ai/api/optimizers/GEPA/overview/) -- GEPA API 和 component_selector 文档
- [GEPA Advanced](https://dspy.ai/api/optimizers/GEPA/GEPA_Advanced/) -- custom instruction proposer 和 component selector 文档
- [DSPy Modules](https://dspy.ai/learn/programming/modules/) -- Module 编程模型
- [pip index: dspy 3.1.3](https://pypi.org/project/dspy/) -- 当前最新版本 [VERIFIED: pip index]

### Tertiary (LOW confidence)
- [gepa optimize_anything](https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/) -- standalone gepa API（本项目使用 dspy.GEPA 而非独立 gepa 包）

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - 无新依赖，全部使用现有 DSPy
- Architecture: HIGH - 基于 DSPy 源代码验证的参数系统实现
- Pitfalls: HIGH - 基于源代码分析的具体风险点

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (DSPy 3.x API stable)
