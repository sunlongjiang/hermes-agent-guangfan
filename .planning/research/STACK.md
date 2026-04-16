# Technology Stack: Phase 2 (Tool Description) & Phase 3 (System Prompt) Optimization

**Project:** hermes-agent-self-evolution
**Researched:** 2026-04-15
**Focus:** DSPy patterns for multi-parameter joint optimization of tool descriptions and system prompt sections

## Executive Summary

Phase 2 和 Phase 3 的核心技术挑战不是"能不能用 GEPA 优化文本"（Phase 1 已经证明可以），而是**如何将多个耦合的文本参数作为一个整体进行联合优化**。工具描述之间相互竞争（优化 search_files 可能让 terminal(grep) 的选择率下降），系统提示词的各个段落共同影响行为。

研究发现两条可行路径：
1. **DSPy 集成路径**：将多个文本包装为一个 `dspy.Module` 中的多个 predictor，用 `dspy.GEPA(component_selector="all")` 联合优化
2. **GEPA standalone 路径**：用 `gepa.optimize()` 的 `seed_candidate` dict 直接定义多个文本组件，绕过 DSPy Module 抽象

**推荐路径 1（DSPy 集成）**，因为现有 Phase 1 基础设施全部基于 DSPy Module 模式，复用成本最低。

---

## Recommended Stack

### Core Framework (No Changes)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| DSPy | >=3.0.0 | Module wrapping, optimization orchestration | Already integrated, Phase 1 validated |
| GEPA (via DSPy) | dspy.GEPA | Primary optimizer | Reflective evolution, reads traces, works with few examples |
| MIPROv2 (via DSPy) | dspy.MIPROv2 | Fallback optimizer | Bayesian optimization, useful when few-shot demos matter |

### New Patterns for Phase 2 & 3

| Pattern | Purpose | Confidence |
|---------|---------|------------|
| Multi-predictor `dspy.Module` | Wrap N tool descriptions as N predictors in one module | HIGH |
| `component_selector="all"` | Force GEPA to optimize all descriptions jointly per iteration | HIGH |
| `component_selector="round_robin"` | Per-section optimization for system prompt (less coupling) | HIGH |
| Custom `ReflectionComponentSelector` | Dependency-aware optimization for coupled sections | MEDIUM |
| Standalone `gepa.optimize()` | Alternative: dict-based multi-component optimization | MEDIUM |

### Supporting Libraries (No Changes)

| Library | Version | Purpose |
|---------|---------|---------|
| Click | >=8.0 | CLI entry points |
| Rich | >=13.0 | Console output |
| PyYAML | >=6.0 | Config parsing |

---

## Key DSPy Patterns for Phase 2 & 3

### Pattern 1: ToolDescriptionModule -- Multi-Predictor Wrapping

**Confidence: HIGH** (based on DSPy's documented multi-module optimization + GEPA component_selector)

Phase 1 的 `SkillModule` 包装单个文本参数。Phase 2 需要包装 N 个工具描述并联合评估。关键洞察：DSPy 的 `dspy.Module` 天然支持多个 predictor，GEPA 天然支持多组件优化。

```python
class ToolDescriptionModule(dspy.Module):
    """Wraps ALL tool descriptions as a single optimizable module.

    Each tool description becomes a separate predictor (= separate GEPA component).
    GEPA optimizes them jointly via component_selector="all".
    """

    class ToolSelectionSignature(dspy.Signature):
        """Given a task, select the best tool and parameters."""
        available_tools: str = dspy.InputField(desc="JSON of all tool schemas with descriptions")
        task_description: str = dspy.InputField(desc="What the user wants to do")
        selected_tool: str = dspy.OutputField(desc="Name of the best tool for this task")
        parameters: str = dspy.OutputField(desc="JSON of parameters to pass")
        reasoning: str = dspy.OutputField(desc="Why this tool was selected")

    def __init__(self, tool_descriptions: dict[str, str]):
        super().__init__()
        self.tool_descriptions = tool_descriptions  # {tool_name: description_text}
        self.selector = dspy.ChainOfThought(self.ToolSelectionSignature)

    def forward(self, task_description: str) -> dspy.Prediction:
        tools_json = self._build_tool_schema()
        result = self.selector(
            available_tools=tools_json,
            task_description=task_description,
        )
        return dspy.Prediction(
            selected_tool=result.selected_tool,
            parameters=result.parameters,
        )
```

**关键问题：这种方式只有一个 predictor，GEPA 只能优化 selector 的 instructions，不能直接优化工具描述文本。**

### Pattern 2 (RECOMMENDED): 用 GEPA standalone API 优化工具描述

**Confidence: HIGH** (gepa.optimize 的 seed_candidate dict 直接支持多文本组件)

```python
import gepa

# seed_candidate 的每个 key 就是一个可优化的文本组件
seed_candidate = {
    "search_files_desc": "Search for files matching a pattern...",
    "read_file_desc": "Read the contents of a file...",
    "terminal_desc": "Execute a terminal command...",
    # ... 每个工具描述作为一个 component
}

def evaluate_tool_selection(candidate: dict, example: dict) -> dict:
    """Metric function: does the agent pick the right tool?"""
    # 1. 用 candidate 中的描述组装 tool schema
    # 2. 让 LLM 根据 task 选择工具
    # 3. 比较选择结果与 ground truth
    score = compute_tool_selection_accuracy(candidate, example)
    feedback = f"Selected {predicted_tool}, expected {expected_tool}."
    return {"score": score, "feedback": feedback}

result = gepa.optimize(
    seed_candidate=seed_candidate,
    evaluate_fn=evaluate_tool_selection,
    dataset=trainset,
    valset=valset,
    task_lm="openai/gpt-4.1-mini",
    reflection_lm="openai/gpt-4.1",
    max_metric_calls=150,
    component_selector="all",  # 所有描述联合优化
)
```

**为什么推荐这个而不是 Pattern 1：**
- 工具描述不是 "predictor instructions"，而是注入到 tool schema 的文本
- DSPy Module 的 predictor 优化的是 prompt instructions，不是任意文本参数
- `gepa.optimize()` 直接将每个 dict key 视为一个可优化的文本组件，完美匹配需求
- `component_selector="all"` 确保所有描述联合优化，不会出现跷跷板效应

**但有一个权衡：** 这会引入 `gepa` 作为新的直接依赖（`pip install gepa`），而非只通过 DSPy 间接使用。

### Pattern 3: PromptSectionModule -- System Prompt Section 优化

**Confidence: HIGH**

系统提示词的各段落也适合用 `gepa.optimize()` 的多组件模式：

```python
seed_candidate = {
    "agent_identity": current_identity_text,
    "memory_guidance": current_memory_guidance_text,
    "session_search_guidance": current_session_search_text,
    "skills_guidance": current_skills_guidance_text,
    "platform_hints": current_platform_hints_text,
}

def evaluate_behavior(candidate: dict, example: dict) -> dict:
    """Assemble full prompt from sections, run behavioral test."""
    full_prompt = assemble_prompt(candidate)
    response = run_agent_with_prompt(full_prompt, example["task"])
    score = judge_behavior(response, example["expected_behavior"])
    return {"score": score, "feedback": feedback}

result = gepa.optimize(
    seed_candidate=seed_candidate,
    evaluate_fn=evaluate_behavior,
    dataset=trainset,
    valset=valset,
    component_selector="round_robin",  # 段落耦合度低于工具描述，逐个优化更高效
)
```

**为什么 round_robin：** 系统提示词段落相对独立（memory_guidance 和 platform_hints 几乎不耦合），逐个优化减少搜索空间，更高效。但 agent_identity 可能需要和其他段落联合优化。

### Pattern 4: 混合策略 -- DSPy Module + GEPA Standalone

**Confidence: MEDIUM**

如果想保持与 Phase 1 完全一致的代码模式（用 DSPy Module），可以这样做：

```python
class ToolDescriptionModule(dspy.Module):
    """Each tool description is stored as module attribute,
    injected into predictor call as input."""

    def __init__(self, tool_descs: dict[str, str]):
        super().__init__()
        # 将每个描述存为 module 属性
        for name, desc in tool_descs.items():
            setattr(self, f"desc_{name}", desc)
        self.selector = dspy.ChainOfThought(ToolSelection)

    def forward(self, task_description: str):
        # 动态组装 tool schema
        schema = {name: getattr(self, f"desc_{name}") for name in self.tool_names}
        return self.selector(tools=json.dumps(schema), task=task_description)
```

**问题：** DSPy GEPA 优化的是 Module 中的 predictor（即 `self.selector`），不是普通的字符串属性。你需要让每个 tool description 成为一个 predictor 的 instructions，但这会非常别扭 -- 工具描述不是 "instructions"。

---

## Recommended Approach (Decision Matrix)

| Dimension | DSPy Module Only | GEPA Standalone | Hybrid |
|-----------|-----------------|-----------------|--------|
| Phase 1 代码模式一致性 | HIGH | LOW | MEDIUM |
| 多参数联合优化自然度 | LOW | HIGH | MEDIUM |
| 工具描述优化匹配度 | LOW | HIGH | MEDIUM |
| 系统提示词优化匹配度 | MEDIUM | HIGH | MEDIUM |
| 新依赖引入 | 无 | gepa package | gepa package |
| 实现复杂度 | HIGH (需要 hack) | LOW (直接映射) | MEDIUM |

### 最终推荐

**Phase 2 (工具描述): 用 `gepa.optimize()` standalone API**

理由：
1. 工具描述是注入 tool schema 的文本，不是 predictor instructions
2. `seed_candidate` dict 直接将 N 个工具描述映射为 N 个可优化组件
3. `component_selector="all"` 天然支持联合优化防止跷跷板效应
4. `evaluate_fn` 可以返回 textual feedback，GEPA 用它做 reflective mutation
5. 现有 `SyntheticDatasetBuilder` 和 `ConstraintValidator` 可以直接复用

**Phase 3 (系统提示词): 也用 `gepa.optimize()` standalone API**

理由：
1. 与 Phase 2 保持一致的模式
2. 每个 prompt section 作为一个 component，`round_robin` 逐个优化
3. 对于强耦合的段落（identity + skills_guidance），可用自定义 `ReflectionComponentSelector` 联合优化

**共同的 wrapper 层：** 在 `evolution/core/` 中创建 `gepa_runner.py`，封装 `gepa.optimize()` 调用，提供与现有 `evolve_skill.py` 一致的 CLI 体验。Phase 1 的 DSPy Module 模式保持不动。

---

## GEPA API 关键参数

| Parameter | Phase 2 Value | Phase 3 Value | Rationale |
|-----------|--------------|---------------|-----------|
| `seed_candidate` | `{tool_name: desc_text, ...}` | `{section_name: section_text, ...}` | Dict keys = optimizable components |
| `evaluate_fn` | tool_selection_accuracy + feedback | behavioral_test_score + feedback | Must return `{"score": float, "feedback": str}` |
| `dataset` | Train split of tool selection triples | Train split of behavioral scenarios | |
| `valset` | Val split | Val split | Prevents overfitting |
| `task_lm` | `"openai/gpt-4.1-mini"` | `"openai/gpt-4.1-mini"` | Cheap model for evaluation runs |
| `reflection_lm` | `"openai/gpt-4.1"` | `"openai/gpt-4.1"` | Strong model for reflective mutation |
| `max_metric_calls` | 150 | 100 | Phase 2 has more components |
| `component_selector` | `"all"` | `"round_robin"` | Tools are coupled; prompt sections are more independent |

---

## Fitness/Metric Function Design

### Phase 2: Tool Selection Metric

```python
def tool_selection_metric(candidate: dict, example: dict) -> dict:
    """
    candidate: {"search_files_desc": "...", "read_file_desc": "...", ...}
    example: {"task": "find Python files with import os",
              "correct_tool": "search_files",
              "correct_params": {"pattern": "import os", "glob": "*.py"}}
    """
    # 1. Assemble tool schemas with candidate descriptions
    tool_schemas = build_schemas_from_candidate(candidate)

    # 2. Ask LLM to select tool
    predicted = llm_select_tool(tool_schemas, example["task"])

    # 3. Score
    tool_correct = float(predicted["tool"] == example["correct_tool"])
    param_correct = compute_param_overlap(predicted["params"], example["correct_params"])
    score = 0.7 * tool_correct + 0.3 * param_correct

    # 4. Feedback for GEPA reflection (CRITICAL for quality)
    if not tool_correct:
        feedback = (f"Agent selected '{predicted['tool']}' but correct tool is "
                   f"'{example['correct_tool']}'. The {predicted['tool']} description "
                   f"may be too broad or {example['correct_tool']} description too narrow.")
    else:
        feedback = f"Correct tool selected. Param accuracy: {param_correct:.0%}"

    return {"score": score, "feedback": feedback}
```

**关键设计决策：feedback 字段是 GEPA 优于 MIPROv2 的核心原因。** MIPROv2 只看 scalar score；GEPA 读 feedback 理解 *why* 选错了，然后提出有针对性的文本修改。

### Phase 3: Behavioral Test Metric

```python
def behavioral_metric(candidate: dict, example: dict) -> dict:
    """
    candidate: {"agent_identity": "...", "memory_guidance": "...", ...}
    example: {"task": "Remember that I prefer Python 3.12",
              "section_tested": "memory_guidance",
              "expected_behavior": "Agent should save this as a memory entry"}
    """
    full_prompt = assemble_system_prompt(candidate)
    response = simulate_agent(full_prompt, example["task"])

    # LLM-as-judge scoring
    judge_result = judge_behavior(response, example["expected_behavior"])

    return {
        "score": judge_result.score,
        "feedback": judge_result.feedback,
    }
```

---

## Constraint Integration

现有 `ConstraintValidator` 已经支持 `tool_description` 和 `param_description` 类型。需要扩展的地方：

| Constraint | Phase 2 | Phase 3 | Already Exists |
|------------|---------|---------|----------------|
| Size limit (chars) | 500/tool, 200/param | Baseline +20% | YES |
| Growth limit | N/A (absolute limit) | +20% over baseline | YES |
| Non-empty | YES | YES | YES |
| Factual accuracy | NEW: descriptions must match actual tool behavior | N/A | NO |
| Cross-tool regression | NEW: no individual tool selection rate drops | N/A | NO |
| Semantic preservation | NEW: core meaning preserved | NEW | NO |

新增约束可以在 `evaluate_fn` 中实现（返回 score=0 + feedback 解释为什么被拒绝），不需要修改 `ConstraintValidator`。但建议也在 `ConstraintValidator` 中添加 post-optimization validation。

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Optimizer for Phase 2 | GEPA standalone (`gepa.optimize`) | dspy.GEPA via Module | Tool descriptions are not predictor instructions; DSPy Module wrapping is awkward |
| Optimizer for Phase 3 | GEPA standalone (`gepa.optimize`) | dspy.MIPROv2 | MIPROv2 needs more data (200+), Phase 3 targets ~60-80 examples |
| Component selection (Phase 2) | `"all"` (joint) | `"round_robin"` (sequential) | Tools compete for selection; must optimize jointly to prevent stealing |
| Component selection (Phase 3) | `"round_robin"` | `"all"` | Prompt sections are relatively independent; round_robin is more efficient |
| Tool descriptions as DSPy Signature fields | NO | YES (one field per tool) | Signature fields are input/output declarations, not optimizable text |
| Darwinian Evolver for text | NO | YES | Overkill for text optimization; AGPL license; GEPA is purpose-built |

---

## Installation

```bash
# Core (already installed)
pip install "dspy>=3.0.0"

# New dependency for Phase 2 & 3
pip install gepa

# No other new dependencies needed
```

**pyproject.toml 变更：**
```toml
dependencies = [
    "dspy>=3.0.0",
    "gepa>=0.1.0",    # NEW: standalone GEPA API for multi-component optimization
    "openai>=1.0.0",
    "pyyaml>=6.0",
    "click>=8.0",
    "rich>=13.0",
]
```

---

## What NOT To Do

### 1. DO NOT wrap each tool description as a separate DSPy Module predictor
**Why:** DSPy predictors are meant to be LLM call sites. Tool descriptions are passive text injected into tool schemas. Forcing them into the predictor pattern creates unnatural abstractions that GEPA can't effectively optimize.

### 2. DO NOT optimize tool descriptions in isolation (one at a time)
**Why:** Tool selection is a zero-sum game. Improving search_files description might make terminal(grep) look worse by comparison. Must evaluate ALL descriptions together against the FULL tool selection dataset.

### 3. DO NOT use MIPROv2 for Phase 2/3
**Why:** MIPROv2 needs 200+ examples to avoid overfitting (Bayesian optimization samples many combinations). Phase 2 targets ~200-400 triples (borderline), Phase 3 targets ~60-80 (too few). GEPA is specifically designed for low-data regimes.

### 4. DO NOT optimize system prompt sections with `component_selector="all"`
**Why:** 5 sections x all-at-once = enormous search space. Sections are sufficiently independent that round_robin is more efficient. Exception: identity + skills_guidance may need coupled optimization.

### 5. DO NOT mix Phase 1's DSPy Module pattern with Phase 2/3's GEPA standalone pattern
**Why:** They solve different problems. Phase 1 optimizes a single text blob (skill body) as predictor instructions. Phase 2/3 optimize multiple text blobs that are injected into external contexts (tool schemas, system prompts). Keep them separate, share only the eval infrastructure.

### 6. DO NOT skip textual feedback in evaluate_fn
**Why:** Returning only a scalar score reduces GEPA to a dumb genetic algorithm. The textual feedback ("Agent confused search_files with terminal because the description mentions 'pattern matching'") is what enables targeted, intelligent mutations.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| GEPA `component_selector` 支持 "all" 和 "round_robin" | HIGH | 官方文档明确记录，多个来源确认 |
| `gepa.optimize()` standalone API 的 seed_candidate dict | HIGH | 官方 API 文档 + blog post (2026-02) 确认 |
| 工具描述不适合用 DSPy Module predictor 模式 | MEDIUM | 基于 DSPy Module 的设计意图推断，未找到反例 |
| MIPROv2 需要 200+ examples | MEDIUM | 官方文档建议 200+，但可能在更少数据上也能工作 |
| GEPA feedback 机制提升工具描述优化质量 | MEDIUM | 理论上成立（GEPA 的核心优势就是读 trace/feedback），但缺少工具描述优化的具体案例 |
| `gepa` 包与 `dspy>=3.0` 的兼容性 | LOW | 需要验证：GEPA 同时存在于 DSPy 内部 (dspy.GEPA) 和独立包 (gepa)，版本兼容需要测试 |

---

## Sources

- [DSPy GEPA Overview](https://dspy.ai/api/optimizers/GEPA/overview/) -- 官方文档
- [DSPy GEPA Advanced](https://dspy.ai/api/optimizers/GEPA/GEPA_Advanced/) -- component_selector 详细说明
- [GEPA GitHub](https://github.com/gepa-ai/gepa) -- standalone API 源码
- [gepa.optimize_anything Blog Post](https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/) -- seed_candidate dict 模式
- [DSPy Optimizers Overview](https://dspy.ai/learn/optimization/optimizers/) -- MIPROv2 vs GEPA 对比
- [GEPA Paper (ICLR 2026 Oral)](https://arxiv.org/pdf/2507.19457) -- 理论基础
- [DSPy Modules Documentation](https://dspy.ai/learn/programming/modules/) -- Module/predictor 设计意图
