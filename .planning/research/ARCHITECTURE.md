# Architecture Patterns

**Domain:** DSPy-based tool description and system prompt optimization modules
**Researched:** 2026-04-15

## Recommended Architecture

### High-Level View

Phase 2 (tools) and Phase 3 (prompts) follow the exact same pipeline pattern as Phase 1 (skills). The key structural difference: skills are single files, tool descriptions are many small strings optimized jointly, and prompt sections are medium-sized text blocks within a larger assembled prompt.

```
                     Shared Core (existing)
                 +--------------------------+
                 | config.py                |
                 | dataset_builder.py       |
                 | fitness.py               |
                 | constraints.py           |
                 +--------------------------+
                    |          |          |
          +---------+    +----+----+    +----------+
          |              |              |
   evolution/skills/  evolution/tools/  evolution/prompts/
   (Phase 1 - done)  (Phase 2 - new)  (Phase 3 - new)
   - skill_module.py  - tool_module.py  - prompt_module.py
   - evolve_skill.py  - evolve_tools.py - evolve_prompt.py
                      - tool_loader.py  - prompt_loader.py
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `evolution/core/config.py` | Configuration (existing, extend) | All components read config |
| `evolution/core/dataset_builder.py` | Build eval datasets (existing, reuse as-is) | Orchestrators call it |
| `evolution/core/fitness.py` | LLM-as-judge scoring (existing, extend with new metrics) | Orchestrators call it |
| `evolution/core/constraints.py` | Hard-gate validation (existing, already handles tool_description type) | Orchestrators call it |
| `evolution/tools/tool_loader.py` | **NEW** - Find and parse tool descriptions from hermes-agent | tool_module.py |
| `evolution/tools/tool_module.py` | **NEW** - DSPy Module wrapping tool descriptions | evolve_tools.py |
| `evolution/tools/evolve_tools.py` | **NEW** - Orchestration + CLI for tool description evolution | All core modules |
| `evolution/prompts/prompt_loader.py` | **NEW** - Find and parse prompt sections from hermes-agent | prompt_module.py |
| `evolution/prompts/prompt_module.py` | **NEW** - DSPy Module wrapping prompt sections | evolve_prompt.py |
| `evolution/prompts/evolve_prompt.py` | **NEW** - Orchestration + CLI for prompt section evolution | All core modules |

---

## Phase 2: Tool Description Architecture

### Why a Separate Loader

Unlike skills (single SKILL.md files), tool descriptions are embedded in Python source files as string constants passed to `registry.register()`. Extracting them requires AST parsing or regex, and writing them back requires preserving the surrounding code. This justifies `tool_loader.py` as a distinct component.

### tool_loader.py - Data Access Layer

**Responsibility:** Read tool descriptions from hermes-agent, write evolved descriptions back.

**Key abstractions:**

```python
@dataclass
class ToolDescription:
    """A single tool's description extracted from hermes-agent."""
    tool_name: str           # e.g., "search_files"
    description: str         # The main description text
    param_descriptions: dict[str, str]  # param_name -> description
    source_file: Path        # Which .py file it came from
    # Metadata for reassembly
    raw_source: str          # Full file content (for writing back)

@dataclass
class ToolDescriptionSet:
    """All tool descriptions from hermes-agent, loaded together."""
    tools: list[ToolDescription]

    def get(self, name: str) -> ToolDescription: ...
    def all_descriptions_text(self) -> str: ...  # For dataset generation context
```

**Discovery strategy:** Scan `hermes-agent/tools/*.py` for `registry.register()` calls or known description constants (like `TERMINAL_TOOL_DESCRIPTION`). Use regex extraction, not AST parsing -- tool description strings are simple enough that regex is reliable and avoids import-side-effect issues.

**Write-back strategy:** Use string replacement on the `raw_source` to swap old description text with evolved text. The surrounding Python code stays untouched. Schema structure (parameter names, types, required fields) is frozen -- only `description` text fields change.

### tool_module.py - DSPy Module Layer

**Responsibility:** Wrap tool descriptions as DSPy-optimizable parameters.

**Critical design choice: Joint optimization.** Tool descriptions must be optimized together, not in isolation. Improving `search_files`'s description could cause the agent to stop selecting `read_file` when it should. The module wraps ALL tool descriptions as a single optimizable unit.

```python
class ToolDescriptionModule(dspy.Module):
    """Wraps all tool descriptions as a joint DSPy module.

    forward() simulates tool selection: given a task, which tool
    would the agent pick based on these descriptions?
    """

    class ToolSelection(dspy.Signature):
        """Given a task and available tools, select the best tool."""
        available_tools: str = dspy.InputField(desc="Tool descriptions")
        task_input: str = dspy.InputField(desc="The task to complete")
        selected_tool: str = dspy.OutputField(desc="Name of the best tool")
        reasoning: str = dspy.OutputField(desc="Why this tool")

    def __init__(self, tool_descriptions: str):
        super().__init__()
        self.tool_descriptions = tool_descriptions  # Optimizable parameter
        self.predictor = dspy.ChainOfThought(self.ToolSelection)

    def forward(self, task_input: str) -> dspy.Prediction:
        result = self.predictor(
            available_tools=self.tool_descriptions,
            task_input=task_input,
        )
        return dspy.Prediction(
            selected_tool=result.selected_tool,
            reasoning=result.reasoning,
        )
```

**Why joint, not per-tool:** GEPA optimizes the `tool_descriptions` string as a single parameter. This string contains all tool descriptions concatenated with clear delimiters. When GEPA mutates one description, it sees the full context of all other descriptions, preventing "description stealing" where one tool's improvement comes at another's expense.

**Alternative considered and rejected:** One DSPy module per tool, optimized sequentially. Rejected because tool selection is inherently comparative -- the agent picks tool A *over* tool B. Optimizing in isolation misses this.

### tool_fitness.py - Fitness Function (extend core/fitness.py)

**Responsibility:** Score tool selection accuracy.

Place this as a function in `evolution/tools/evolve_tools.py` (or a small `tool_fitness.py` helper), not in `core/fitness.py`. Reason: `core/fitness.py` provides the generic LLM-as-judge; tool selection accuracy is domain-specific.

```python
def tool_selection_metric(example: dspy.Example, prediction: dspy.Prediction, trace=None) -> float:
    """DSPy-compatible metric for tool selection optimization.

    Scores:
    - 1.0 if correct tool selected
    - 0.5 if acceptable alternative selected
    - 0.0 if wrong tool selected
    """
    expected = getattr(example, "correct_tool", "")
    selected = getattr(prediction, "selected_tool", "")
    alternatives = getattr(example, "acceptable_alternatives", "").split(",")

    if selected.strip().lower() == expected.strip().lower():
        return 1.0
    elif selected.strip().lower() in [a.strip().lower() for a in alternatives]:
        return 0.5
    return 0.0
```

### evolve_tools.py - Orchestration Layer

Follows the exact same 10-step pattern as `evolve_skill.py`:

1. Load all tool descriptions from hermes-agent
2. Build/load eval dataset (tool selection triples)
3. Validate baseline constraints
4. Set up DSPy + GEPA
5. Run optimization (joint, all descriptions at once)
6. Extract evolved descriptions
7. Validate constraints (500 char limit per tool, 200 per param)
8. Holdout evaluation
9. Report results
10. Save output (evolved descriptions + metrics)

**CLI entry point:** `python -m evolution.tools.evolve_tools --iterations 5`

**Dataset format for tool selection:**

```python
# EvalExample extended usage:
# task_input: "find all Python files containing 'import os'"
# expected_behavior: "correct_tool=search_files;alternatives=terminal"
# category: "tool_selection"
```

Reuse `EvalExample` and `EvalDataset` from `core/dataset_builder.py`. The `expected_behavior` field encodes the correct tool and acceptable alternatives as a structured string. The `SyntheticDatasetBuilder` already accepts `artifact_type="tool_description"` -- just pass the concatenated tool descriptions as `artifact_text`.

---

## Phase 3: System Prompt Architecture

### Why a Separate Loader

Prompt sections live inside `hermes-agent/agent/prompt_builder.py` as Python string constants (e.g., `DEFAULT_AGENT_IDENTITY`, `MEMORY_GUIDANCE`). Like tool descriptions, extracting and writing back requires awareness of the source file structure.

### prompt_loader.py - Data Access Layer

```python
@dataclass
class PromptSection:
    """A single section of the system prompt."""
    section_name: str        # e.g., "DEFAULT_AGENT_IDENTITY"
    content: str             # The section text
    source_file: Path        # prompt_builder.py
    is_evolvable: bool       # True for the 5 evolvable sections

EVOLVABLE_SECTIONS = [
    "DEFAULT_AGENT_IDENTITY",
    "MEMORY_GUIDANCE",
    "SESSION_SEARCH_GUIDANCE",
    "SKILLS_GUIDANCE",
    "PLATFORM_HINTS",
]

@dataclass
class PromptSectionSet:
    """All prompt sections from hermes-agent."""
    sections: list[PromptSection]

    def get(self, name: str) -> PromptSection: ...
    def evolvable(self) -> list[PromptSection]: ...
    def assemble_full_prompt(self) -> str: ...  # Reconstruct full prompt for context
```

**Discovery strategy:** Parse `prompt_builder.py` for known constant names. These are well-defined in PLAN.md (5 evolvable sections). Use regex to extract multi-line string constants.

### prompt_module.py - DSPy Module Layer

**Two-mode optimization:** Per-section (targeted) and joint (holistic).

```python
class PromptSectionModule(dspy.Module):
    """Wraps a single prompt section as a DSPy module.

    forward() simulates agent behavior with this prompt section,
    testing whether the section guides the agent correctly.
    """

    class BehavioralTest(dspy.Signature):
        """Test if the agent behaves correctly given a system prompt section."""
        system_prompt_section: str = dspy.InputField(desc="The prompt section being tested")
        full_system_context: str = dspy.InputField(desc="Other sections for context")
        task_input: str = dspy.InputField(desc="A scenario testing this section's behavior")
        agent_response: str = dspy.OutputField(desc="How the agent responds")
        behavioral_notes: str = dspy.OutputField(desc="What behaviors the agent exhibited")

    def __init__(self, section_text: str, context_text: str):
        super().__init__()
        self.section_text = section_text    # Optimizable parameter
        self.context_text = context_text    # Frozen context (other sections)
        self.predictor = dspy.ChainOfThought(self.BehavioralTest)

    def forward(self, task_input: str) -> dspy.Prediction:
        result = self.predictor(
            system_prompt_section=self.section_text,
            full_system_context=self.context_text,
            task_input=task_input,
        )
        return dspy.Prediction(
            agent_response=result.agent_response,
            behavioral_notes=result.behavioral_notes,
        )
```

**Why per-section first, joint second:** System prompt sections serve distinct purposes (memory guidance vs identity vs platform hints). Optimizing per-section first allows targeted improvement. Joint optimization as a second pass catches cross-section interactions (e.g., identity section contradicting memory guidance).

**Recommended optimization flow:**
1. Optimize each evolvable section independently (5 separate GEPA runs)
2. Validate each section's improvement on its targeted behavioral tests
3. Assemble all evolved sections into a full prompt
4. Run joint holdout evaluation on the full assembled prompt
5. If joint score regresses, roll back the section that caused regression

### evolve_prompt.py - Orchestration Layer

Same 10-step pattern, with one addition: the per-section / joint split.

**CLI entry points:**
```bash
# Evolve a single section
python -m evolution.prompts.evolve_prompt --section MEMORY_GUIDANCE --iterations 5

# Evolve all sections (runs per-section, then joint validation)
python -m evolution.prompts.evolve_prompt --all --iterations 5
```

---

## Data Flow

### Phase 2: Tool Description Evolution

```
hermes-agent/tools/*.py
       |
       v
  tool_loader.py (extract descriptions)
       |
       v
  ToolDescriptionSet
       |
       +---> SyntheticDatasetBuilder(artifact_type="tool_description")
       |            |
       |            v
       |     EvalDataset (tool selection triples)
       |            |
       v            v
  ToolDescriptionModule(all_descriptions)
       |
       v
  GEPA optimizer (metric=tool_selection_metric)
       |
       v
  Evolved ToolDescriptionModule
       |
       v
  ConstraintValidator.validate_all(desc, "tool_description")
       |
       v
  Holdout evaluation (tool selection accuracy)
       |
       v
  output/tools/<timestamp>/ (evolved descriptions + metrics)
```

### Phase 3: System Prompt Evolution

```
hermes-agent/agent/prompt_builder.py
       |
       v
  prompt_loader.py (extract sections)
       |
       v
  PromptSectionSet
       |
       +---> SyntheticDatasetBuilder(artifact_type="prompt_section")
       |            |
       |            v
       |     EvalDataset (behavioral scenarios)
       |            |
       v            v
  PromptSectionModule(section, context)   <-- per section
       |
       v
  GEPA optimizer (metric=behavioral_metric)
       |
       v
  Evolved sections
       |
       v
  ConstraintValidator.validate_all(section, "prompt_section", baseline)
       |
       v
  Joint holdout evaluation (all sections assembled)
       |
       v
  output/prompts/<section>/<timestamp>/ (evolved section + metrics)
```

---

## Patterns to Follow

### Pattern 1: Module-per-domain with Shared Core

**What:** Each domain (skills, tools, prompts) gets its own package under `evolution/` with the same three-file structure: loader, module, orchestrator. All share `evolution/core/`.

**Why:** Phase 1 established this pattern and it works. Predictable structure makes the codebase navigable. New domains (Phase 4: code) can follow the same pattern.

**Structure per domain:**
```
evolution/<domain>/
    __init__.py
    <domain>_loader.py    # Read/write artifacts from hermes-agent
    <domain>_module.py    # DSPy Module wrapping the artifact
    evolve_<domain>.py    # Orchestration + CLI (Click entry point)
```

### Pattern 2: Extend Config, Don't Fork It

**What:** Add new config fields to `EvolutionConfig` for Phase 2/3 needs. Do not create separate config classes.

**Why:** `EvolutionConfig` already has `max_tool_desc_size` and `max_param_desc_size`. The config is a flat dataclass -- adding fields is non-breaking. All orchestrators already receive config as their first setup step.

**Fields to add:**
```python
# Phase 2
tool_selection_weight: float = 1.0      # Weight for correct tool selection
param_accuracy_weight: float = 0.3      # Weight for correct param usage

# Phase 3
max_prompt_section_size: int = 5_000    # Per-section size limit
behavioral_score_threshold: float = 0.6  # Minimum behavioral score to accept
```

### Pattern 3: Domain-Specific Metric, Generic Judge

**What:** The `core/fitness.py` LLMJudge stays generic. Each domain defines its own DSPy-compatible metric function in its orchestrator file.

**Why:** `skill_fitness_metric()` in `evolve_skill.py` is a fast heuristic proxy. Tool selection needs a different heuristic (exact match on tool name). Prompt evolution needs behavioral scoring. These are fundamentally different metrics that should not be crammed into one function.

```
core/fitness.py         -> LLMJudge (generic, for detailed scoring)
                        -> FitnessScore (generic data class)

skills/evolve_skill.py  -> skill_fitness_metric() (keyword overlap proxy)
tools/evolve_tools.py   -> tool_selection_metric() (exact match + alternatives)
prompts/evolve_prompt.py -> behavioral_metric() (behavior checklist scoring)
```

### Pattern 4: Constraint Type Dispatch (Already Exists)

**What:** `ConstraintValidator.validate_all()` already dispatches on `artifact_type`. The `_check_size()` method already handles `"tool_description"` and `"param_description"` types.

**What to add:** Structural checks for new artifact types.

```python
# In constraints.py _check_structure dispatch:
if artifact_type == "skill":
    results.append(self._check_skill_structure(artifact_text))
elif artifact_type == "tool_description":
    results.append(self._check_tool_desc_structure(artifact_text))
elif artifact_type == "prompt_section":
    results.append(self._check_prompt_section_structure(artifact_text))
```

New structural checks:
- `_check_tool_desc_structure`: Verify description is factual (no claims about capabilities the tool doesn't have). This is a lightweight heuristic, not a full fact-check.
- `_check_prompt_section_structure`: Verify section maintains its functional role (e.g., MEMORY_GUIDANCE still talks about memory).

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Per-Tool Isolation

**What:** Optimizing each tool description independently.
**Why bad:** Tool selection is comparative. Improving search_files in isolation could make it steal selections from read_file. You can't evaluate tool descriptions without seeing them all together.
**Instead:** Always optimize all tool descriptions jointly via a single ToolDescriptionModule.

### Anti-Pattern 2: Full LLM Judge During Optimization

**What:** Calling `LLMJudge.score()` for every candidate during GEPA iterations.
**Why bad:** Each GEPA iteration evaluates multiple candidates on the full training set. LLM-as-judge calls are expensive ($0.01-0.10 each). 10 iterations x 5 candidates x 20 examples = 1000 LLM calls just for scoring.
**Instead:** Use fast heuristic metrics during optimization (like `skill_fitness_metric`). Reserve full LLM-as-judge for holdout evaluation only.

### Anti-Pattern 3: Modifying hermes-agent Source In-Place

**What:** Writing evolved descriptions directly into hermes-agent files.
**Why bad:** Breaks the read-only contract. Makes rollback difficult. Could corrupt working state.
**Instead:** Write evolved artifacts to `output/` directory. The output includes the full file content ready to be copied or PR'd.

### Anti-Pattern 4: Shared Mutable State Between Phases

**What:** Phase 3 depending on Phase 2's evolved output as its baseline.
**Why bad:** Creates cascading dependencies. If Phase 2 regresses, Phase 3 inherits the regression.
**Instead:** Each phase reads the current state of hermes-agent independently. Phases are independent optimization targets.

---

## What to Extend in Core vs Create New

| Need | Approach | Rationale |
|------|----------|-----------|
| Config fields for tool/prompt limits | **Extend** `core/config.py` | Already has tool desc fields, just add prompt fields |
| Size/growth constraint checking | **Reuse** `core/constraints.py` as-is | Already dispatches on artifact_type |
| Structural constraint checking | **Extend** `core/constraints.py` | Add `_check_tool_desc_structure`, `_check_prompt_section_structure` |
| Synthetic dataset generation | **Reuse** `core/dataset_builder.py` as-is | Already accepts `artifact_type` parameter |
| Tool selection fitness metric | **Create** in `tools/evolve_tools.py` | Domain-specific, not generic |
| Behavioral fitness metric | **Create** in `prompts/evolve_prompt.py` | Domain-specific, not generic |
| Tool description loading | **Create** `tools/tool_loader.py` | New data access pattern (Python source -> string extraction) |
| Prompt section loading | **Create** `prompts/prompt_loader.py` | New data access pattern (Python constants -> section extraction) |
| ToolDescriptionModule | **Create** `tools/tool_module.py` | Follows SkillModule pattern but joint optimization |
| PromptSectionModule | **Create** `prompts/prompt_module.py` | Follows SkillModule pattern but with context passthrough |

---

## Suggested Build Order

Build order is driven by two factors: (1) dependency chains, and (2) risk ordering (tool descriptions are lower risk than system prompts).

### Phase 2 Build Order (Tool Descriptions)

```
Step 1: tool_loader.py
    No dependencies on new code. Just reads hermes-agent files.
    Can be tested immediately against a real hermes-agent repo.

Step 2: tool_module.py
    Depends on: tool_loader.py (for ToolDescription dataclass)
    DSPy Module wrapping. Can be tested with a mock tool set.

Step 3: tool_selection_metric (in evolve_tools.py)
    Depends on: nothing new (just dspy.Example/Prediction)
    Small function, easy to unit test.

Step 4: evolve_tools.py (full orchestrator)
    Depends on: Steps 1-3 + all core/ modules
    Wire everything together. CLI entry point.

Step 5: Extend constraints.py
    Add _check_tool_desc_structure.
    Low risk, existing pattern.
```

### Phase 3 Build Order (System Prompts)

```
Step 1: prompt_loader.py
    No dependencies on Phase 2. Reads prompt_builder.py.

Step 2: prompt_module.py
    Depends on: prompt_loader.py
    Two-mode design (per-section + context passthrough).

Step 3: behavioral_metric (in evolve_prompt.py)
    Depends on: nothing new.

Step 4: evolve_prompt.py (full orchestrator)
    Depends on: Steps 1-3 + core/
    Both --section and --all modes.

Step 5: Extend constraints.py
    Add _check_prompt_section_structure.
```

### Cross-Phase Dependencies

```
Phase 2 and Phase 3 are INDEPENDENT of each other.
Both depend on Phase 1's core/ infrastructure.

core/config.py -------> tools/ (Phase 2)
core/dataset_builder.py --/
core/fitness.py --------/
core/constraints.py ---/
                        \---> prompts/ (Phase 3)

Phase 2 does NOT depend on Phase 3.
Phase 3 does NOT depend on Phase 2.
They CAN be built in parallel if desired.
```

However, PLAN.md specifies Phase 2 before Phase 3 because tool descriptions are lower risk (bounded 500-char strings vs unbounded behavioral impact of system prompt changes). Build Phase 2 first to validate the pattern extension works, then apply the same pattern to Phase 3.

---

## Scalability Considerations

| Concern | Current (Phase 1) | Phase 2 (Tools) | Phase 3 (Prompts) |
|---------|-------------------|-----------------|-------------------|
| Optimization units | 1 skill at a time | All tools jointly (~20-30 tools) | 1-5 sections per run |
| Parameter size | ~1-15KB skill body | ~10-15KB total (all descriptions) | ~1-5KB per section |
| Eval dataset size | 20 examples | 200-400 tool selection triples | 60-80 behavioral scenarios |
| GEPA iteration cost | ~$0.20-1.00 | ~$0.50-2.00 (larger dataset) | ~$0.30-1.50 |
| Constraint checking | Fast (string length) | Fast (per-tool char count) | Fast + growth check |
| Holdout eval cost | ~$0.50-2.00 | ~$1.00-4.00 | ~$1.00-3.00 |

The joint optimization of tool descriptions is the most expensive operation because the full descriptions string (~10-15KB) is evaluated against a larger dataset. If this becomes too slow, consider: (1) reducing dataset size during optimization, using full dataset only for holdout; (2) batching tool descriptions into functional groups (file tools, search tools, system tools) and optimizing groups sequentially.

---

## Sources

- Existing codebase: `evolution/skills/skill_module.py`, `evolution/skills/evolve_skill.py`, `evolution/core/constraints.py`, `evolution/core/fitness.py`, `evolution/core/dataset_builder.py`, `evolution/core/config.py`
- Project plan: `PLAN.md` (Phase 2 and Phase 3 specifications)
- Architecture analysis: `.planning/codebase/ARCHITECTURE.md`

**Confidence: HIGH** -- This architecture is a direct extension of working Phase 1 patterns, informed by reading every line of the existing implementation. The core infrastructure was explicitly designed to be generic (artifact_type dispatch, configurable size limits). The main architectural decisions (joint tool optimization, per-section-then-joint prompt optimization) are driven by the problem structure documented in PLAN.md.
