# Phase 9: Prompt Evaluation - Research

**Researched:** 2026-04-16
**Domain:** Behavioral evaluation for prompt section optimization (LLM-as-judge + scenario dataset)
**Confidence:** HIGH

## Summary

Phase 9 builds the behavioral evaluation pipeline for prompt sections: a scenario dataset builder and a DSPy-compatible metric function. The core pattern is already proven in two prior implementations -- Phase 1's `SyntheticDatasetBuilder` + `skill_fitness_metric` and Phase 4's `ToolDatasetBuilder` + `tool_selection_metric`. Phase 9 adapts these patterns for prompt section evaluation with two key differences: (1) scenarios are per-section rather than per-tool, with weighted allocation across 5 section categories, and (2) scoring uses the continuous `FitnessScore` rubric (correctness/procedure/conciseness) rather than binary match.

The implementation requires two new files: `prompt_dataset.py` (dataclass + builder) and `prompt_metric.py` (metric function). Both follow established project conventions exactly -- nested DSPy Signatures, ChainOfThought generators, JSONL persistence, and `to_dspy_examples()` conversion. The metric function `prompt_behavioral_metric()` returns a float 0.0-1.0, making it directly compatible with `dspy.GEPA(metric=...)`.

**Primary recommendation:** Mirror the ToolDatasetBuilder/tool_selection_metric architecture, substituting per-section scenario generation for per-tool task generation, and LLMJudge-based composite scoring for binary match scoring.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- D1: LLM 合成场景（复用 SyntheticDatasetBuilder 模式）-- 用 LLM 根据段落内容合成场景，每场景包含 section_id, user_message, expected_behavior, difficulty
- D2: 按重要性加权分配 -- identity 20, memory 15, skills 15, platform 20, session 10 = 80 场景，50/25/25 拆分
- D3: 复用 FitnessScore (correctness 0.5 / procedure_following 0.3 / conciseness 0.2)
- D4: prompt_behavioral_metric() 返回 float，与 tool_selection_metric 对称

### Claude's Discretion
None specified -- all key decisions are locked.

### Deferred Ideas (OUT OF SCOPE)
None.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PMPT-05 | Behavioral evaluator -- per-section scenario-based testing that checks whether agent exhibits expected behavior | `prompt_behavioral_metric()` function using LLMJudge internally, returning FitnessScore.composite as float |
| PMPT-06 | Behavioral test suite with 60-80 scenarios across 5 sections (10-20 per section, scaled by section importance) | `PromptBehavioralDataset` + `PromptDatasetBuilder` with weighted per-section generation |
| PMPT-07 | Per-section scoring with structured actionable feedback piped to GEPA's reflective analysis | FitnessScore.feedback field carries textual feedback; metric function stores it on prediction for GEPA consumption |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| dspy | >=3.0.0 | DSPy Signature/ChainOfThought for scenario generation + judge | Already in project deps [VERIFIED: pyproject.toml] |
| evolution.core.fitness | - | FitnessScore, LLMJudge, _parse_score | Reused per D3 [VERIFIED: codebase] |
| evolution.core.dataset_builder | - | EvalExample, EvalDataset patterns | Template for dataset class [VERIFIED: codebase] |
| evolution.core.config | - | EvolutionConfig (model names, ratios, paths) | Shared config [VERIFIED: codebase] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| rich | >=13.0 | Console output, progress bars, tables | All user-facing output [VERIFIED: pyproject.toml] |
| json | stdlib | JSONL persistence | Dataset save/load |
| random | stdlib | Shuffle before split | Dataset splitting |
| re | stdlib | JSON extraction fallback | LLM output parsing |

No new external dependencies needed. [VERIFIED: all imports already available]

## Architecture Patterns

### Recommended Project Structure
```
evolution/prompts/
    __init__.py          # Add new exports
    prompt_loader.py     # Phase 7 (existing)
    prompt_module.py     # Phase 8 (existing)
    prompt_dataset.py    # NEW: PromptBehavioralExample, PromptBehavioralDataset, PromptDatasetBuilder
    prompt_metric.py     # NEW: prompt_behavioral_metric(), PromptBehavioralJudge
```

### Pattern 1: Per-Section Weighted Scenario Generation
**What:** PromptDatasetBuilder generates scenarios per-section with weighted counts, mirroring ToolDatasetBuilder's per-tool generation.
**When to use:** Dataset generation for prompt evaluation.
**Example:**
```python
# Source: Adapted from evolution/tools/tool_dataset.py ToolDatasetBuilder.generate()
SECTION_WEIGHTS = {
    "default_agent_identity": 20,
    "memory_guidance": 15,
    "skills_guidance": 15,
    "platform_hints.*": 20,  # Spread across ~9 platform keys
    "session_search_guidance": 10,
}
# Total: 80 scenarios
```
[VERIFIED: D2 from CONTEXT.md specifies exact allocation]

### Pattern 2: Continuous Metric with LLMJudge (not binary)
**What:** Unlike tool_selection_metric (binary 0/1), prompt_behavioral_metric uses LLMJudge to produce a continuous 0.0-1.0 score via FitnessScore.composite.
**When to use:** As DSPy metric function passed to GEPA.
**Example:**
```python
# Source: Adapted from evolution/core/fitness.py LLMJudge + skill_fitness_metric
def prompt_behavioral_metric(example: dspy.Example, prediction: dspy.Prediction, trace=None) -> float:
    """DSPy-compatible metric for prompt section optimization."""
    agent_output = getattr(prediction, "output", "") or ""
    expected = getattr(example, "expected_behavior", "") or ""
    task = getattr(example, "task_input", "") or ""
    section_text = getattr(example, "section_text", "") or ""

    if not agent_output.strip():
        return 0.0

    judge = LLMJudge(config)
    score = judge.score(
        task_input=task,
        expected_behavior=expected,
        agent_output=agent_output,
        skill_text=section_text,  # Reuses skill_text parameter for section text
    )
    # Attach feedback for GEPA's reflective analysis
    if hasattr(prediction, '_completions'):
        prediction.feedback = score.feedback
    return score.composite
```
[VERIFIED: LLMJudge.score() signature in fitness.py, D3/D4 from CONTEXT.md]

### Pattern 3: Dataclass with JSONL Persistence
**What:** PromptBehavioralExample/Dataset follows EvalExample/EvalDataset and ToolSelectionExample/Dataset patterns exactly.
**When to use:** All data persistence and DSPy integration.
**Example:**
```python
# Source: Mirrors evolution/tools/tool_dataset.py ToolSelectionExample
@dataclass
class PromptBehavioralExample:
    section_id: str           # e.g. "memory_guidance"
    user_message: str         # Simulated user input
    expected_behavior: str    # Rubric for judging agent response
    difficulty: str = "medium"
    source: str = "synthetic"

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, d: dict) -> "PromptBehavioralExample": ...
```
[VERIFIED: consistent with EvalExample and ToolSelectionExample patterns]

### Anti-Patterns to Avoid
- **Hardcoding platform_hints keys:** The platform_hints section has ~9 sub-keys. Discover them dynamically from PromptSection list, don't hardcode platform names. [VERIFIED: prompt_loader.py creates `platform_hints.{key}` dynamically]
- **Running LLMJudge on every optimization step:** The full judge is expensive. The metric function should use a fast heuristic for `trace is not None` (optimization loop) and full LLMJudge for final eval. Existing `skill_fitness_metric` already demonstrates this pattern. [VERIFIED: fitness.py lines 107-136]
- **Generating all 80 scenarios in one LLM call:** Break into per-section calls (like ToolDatasetBuilder does per-tool). One call per section with its target count.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| LLM-as-judge scoring | Custom scoring prompt | `LLMJudge` from fitness.py | Already handles score parsing, clamping, length penalty |
| JSON parsing from LLM | Manual regex extraction | Two-stage pattern from dataset_builder.py | Proven fallback strategy |
| Dataset splitting | Custom split logic | Follow EvolutionConfig.train_ratio/val_ratio pattern | Consistent 50/25/25 splits |
| Score clamping | Manual min/max | `_parse_score()` from fitness.py | Handles all edge cases |

## Common Pitfalls

### Pitfall 1: Platform Hints Scenario Distribution
**What goes wrong:** 20 scenarios for platform_hints spread across ~9 keys means only 2-3 per platform. If generation fails for some platforms, coverage gaps.
**Why it happens:** LLM may generate uneven distributions or fail on less common platforms.
**How to avoid:** Generate per-platform with explicit counts (2-3 each), not 20 in one batch. Check coverage after generation.
**Warning signs:** Any platform with 0 scenarios after generation.

### Pitfall 2: LLMJudge Config Access in Metric Function
**What goes wrong:** `prompt_behavioral_metric()` is a module-level function (DSPy metric signature) but needs EvolutionConfig to instantiate LLMJudge.
**Why it happens:** DSPy metric functions have a fixed signature `(example, prediction, trace=None) -> float`.
**How to avoid:** Use a class-based approach (like a closure or callable class) that captures config at construction time, or use a module-level config. The tool_selection_metric avoids this because it's binary (no LLM call needed). Look at how `skill_fitness_metric` handles it -- it uses a heuristic, not LLMJudge. For prompt_behavioral_metric, use a factory function or callable class.
**Warning signs:** Import errors or missing config at metric call time.

### Pitfall 3: Feedback Propagation to GEPA
**What goes wrong:** FitnessScore.feedback exists but GEPA needs it accessible from the metric return path.
**Why it happens:** DSPy metric functions return float, but GEPA's reflective analysis needs textual feedback.
**How to avoid:** Per D4 and D7 patterns -- store feedback on the prediction object or use DSPy's trace mechanism. Research indicates attaching feedback as an attribute on the prediction or using a side-channel (module-level accumulator) that GEPA can read.
**Warning signs:** GEPA optimization runs without section-specific feedback in its reflective analysis.

### Pitfall 4: section_text Field Naming in LLMJudge
**What goes wrong:** LLMJudge.score() takes `skill_text` parameter. Passing prompt section text through this parameter is semantically confusing.
**Why it happens:** LLMJudge was designed for skill evaluation in Phase 1.
**How to avoid:** Reuse `skill_text` parameter as-is (it's just a string). The JudgeSignature's InputField desc says "The skill/instructions the agent was following" which is semantically compatible. No need to modify LLMJudge. Document the mapping: `skill_text` = active section text.
**Warning signs:** None -- this is a naming concern, not a functional issue.

## Code Examples

### PromptBehavioralExample Dataclass
```python
# Source: Adapted from evolution/tools/tool_dataset.py lines 33-72
@dataclass
class PromptBehavioralExample:
    """A single prompt behavioral evaluation example.

    Args:
        section_id: Which section this scenario tests (e.g. "memory_guidance").
        user_message: Simulated user input.
        expected_behavior: Rubric describing correct agent behavior.
        difficulty: One of 'easy', 'medium', 'hard'.
        source: Provenance: 'synthetic', 'golden'.
    """
    section_id: str
    user_message: str
    expected_behavior: str
    difficulty: str = "medium"
    source: str = "synthetic"

    def to_dict(self) -> dict:
        return {
            "section_id": self.section_id,
            "user_message": self.user_message,
            "expected_behavior": self.expected_behavior,
            "difficulty": self.difficulty,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PromptBehavioralExample":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
```

### PromptDatasetBuilder Signature
```python
# Source: Adapted from evolution/core/dataset_builder.py lines 96-109
class GenerateSectionScenarios(dspy.Signature):
    """Generate behavioral test scenarios for a prompt section.

    Given a prompt section's text, generate realistic scenarios that test
    whether an agent following this guidance exhibits correct behavior.
    """
    section_text: str = dspy.InputField(desc="The prompt section text being tested")
    section_id: str = dspy.InputField(desc="Section identifier (e.g. 'memory_guidance')")
    num_scenarios: int = dspy.InputField(desc="Number of scenarios to generate")
    difficulty_mix: str = dspy.InputField(desc="Target difficulty distribution, e.g. 'easy:30%,medium:50%,hard:20%'")
    scenarios: str = dspy.OutputField(desc="JSON array of {user_message, expected_behavior, difficulty}")
```

### prompt_behavioral_metric with Config Capture
```python
# Source: Adapted from fitness.py skill_fitness_metric + tool_metric.py tool_selection_metric
class PromptBehavioralMetric:
    """Callable class implementing DSPy metric interface with config capture.

    Usage:
        metric = PromptBehavioralMetric(config)
        # Pass metric to GEPA:
        optimizer = dspy.GEPA(metric=metric, ...)
    """

    def __init__(self, config: EvolutionConfig):
        self.judge = LLMJudge(config)

    def __call__(self, example: dspy.Example, prediction: dspy.Prediction, trace=None) -> float:
        agent_output = getattr(prediction, "output", "") or ""
        expected = getattr(example, "expected_behavior", "") or ""
        task = getattr(example, "task_input", "") or ""
        section_text = getattr(example, "section_text", "") or ""

        if not agent_output.strip():
            return 0.0

        # Fast heuristic during optimization (when trace is not None)
        if trace is not None:
            return _quick_heuristic(agent_output, expected)

        # Full LLM-as-judge for final evaluation
        score = self.judge.score(
            task_input=task,
            expected_behavior=expected,
            agent_output=agent_output,
            skill_text=section_text,
        )
        return score.composite
```

### DSPy Example Conversion with section_text
```python
# Source: Adapted from tool_dataset.py lines 130-148
def to_dspy_examples(self, split: str = "train", section_texts: dict[str, str] | None = None) -> list[dspy.Example]:
    """Convert split to DSPy Examples, optionally injecting section text."""
    data = getattr(self, split)
    examples = []
    for ex in data:
        fields = {
            "task_input": ex.user_message,
            "expected_behavior": ex.expected_behavior,
        }
        if section_texts and ex.section_id in section_texts:
            fields["section_text"] = section_texts[ex.section_id]
        examples.append(dspy.Example(**fields).with_inputs("task_input"))
    return examples
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single metric for all sections | Per-section weighted metric | Phase 9 (new) | Enables section-specific feedback for GEPA |
| Binary tool metric | Continuous behavioral metric | Phase 9 (new) | Richer signal for prompt optimization |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | DSPy GEPA can consume a callable class (with `__call__`) as metric, not just a plain function | Code Examples | If wrong, need wrapper function with module-level config; low risk -- Python callables are standard |
| A2 | Attaching feedback to prediction object is sufficient for GEPA reflective analysis | Pitfall 3 | If wrong, need alternative feedback channel; may need to check GEPA source code |
| A3 | LLMJudge.JudgeSignature's `skill_text` field works semantically for prompt section text | Pitfall 4 | If wrong, need custom JudgeSignature subclass; very low risk since it's just a string input |

## Open Questions

1. **GEPA feedback propagation mechanism**
   - What we know: FitnessScore has a `feedback` field, and GEPA uses "reflective analysis"
   - What's unclear: Exact mechanism by which GEPA consumes per-example feedback from the metric function
   - Recommendation: Implement the callable class pattern with feedback on prediction; if GEPA doesn't read it, add a side-channel. Test empirically during Phase 10 integration.

2. **Fast heuristic vs full LLM judge during optimization**
   - What we know: `skill_fitness_metric` uses keyword overlap as fast heuristic; tool_selection_metric is inherently fast (binary)
   - What's unclear: Whether keyword overlap is meaningful for behavioral evaluation of prompt sections
   - Recommendation: Use keyword overlap as Phase 1 does; if quality is poor, switch to lightweight LLM call with cheaper model. The heuristic is only for optimization speed -- final eval always uses full LLMJudge.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=7.0 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/prompts/ -x -q` |
| Full suite command | `python -m pytest tests/ -x -q` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PMPT-05 | prompt_behavioral_metric returns float 0.0-1.0 | unit | `python -m pytest tests/prompts/test_prompt_metric.py -x` | Wave 0 |
| PMPT-05 | metric returns 0.0 for empty output | unit | same | Wave 0 |
| PMPT-05 | metric callable class accepts config | unit | same | Wave 0 |
| PMPT-06 | PromptBehavioralExample to_dict/from_dict round-trip | unit | `python -m pytest tests/prompts/test_prompt_dataset.py -x` | Wave 0 |
| PMPT-06 | PromptBehavioralDataset save/load JSONL | unit | same | Wave 0 |
| PMPT-06 | PromptDatasetBuilder generates correct count per section | unit (mocked LLM) | same | Wave 0 |
| PMPT-06 | Dataset has 50/25/25 split | unit | same | Wave 0 |
| PMPT-07 | FitnessScore.feedback is non-empty string after scoring | unit (mocked LLM) | `python -m pytest tests/prompts/test_prompt_metric.py -x` | Wave 0 |
| PMPT-07 | Per-section scores are structured | unit | same | Wave 0 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/prompts/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/prompts/test_prompt_dataset.py` -- covers PMPT-06
- [ ] `tests/prompts/test_prompt_metric.py` -- covers PMPT-05, PMPT-07

## Security Domain

No security-sensitive operations in this phase. The phase generates synthetic test data and scores LLM outputs. No authentication, cryptography, user input validation, or access control is involved.

Applicable ASVS categories: None.

## Sources

### Primary (HIGH confidence)
- `evolution/core/fitness.py` -- FitnessScore, LLMJudge, skill_fitness_metric, _parse_score patterns [VERIFIED: codebase]
- `evolution/core/dataset_builder.py` -- EvalExample, EvalDataset, SyntheticDatasetBuilder patterns [VERIFIED: codebase]
- `evolution/tools/tool_metric.py` -- tool_selection_metric, CrossToolRegressionChecker patterns [VERIFIED: codebase]
- `evolution/tools/tool_dataset.py` -- ToolSelectionExample, ToolSelectionDataset, ToolDatasetBuilder patterns [VERIFIED: codebase]
- `evolution/prompts/prompt_module.py` -- PromptModule.set_active_section(), forward(), get_evolved_sections() [VERIFIED: codebase]
- `evolution/prompts/prompt_loader.py` -- PromptSection dataclass, section_id naming [VERIFIED: codebase]
- `evolution/core/config.py` -- EvolutionConfig fields (eval_model, judge_model, train_ratio, etc.) [VERIFIED: codebase]
- `09-CONTEXT.md` -- All 4 locked decisions (D1-D4) [VERIFIED: codebase]

### Secondary (MEDIUM confidence)
- None needed -- all patterns are internal to the codebase.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in project, no new deps
- Architecture: HIGH -- direct adaptation of proven Phase 1/4 patterns
- Pitfalls: HIGH -- identified from code inspection of existing implementations

**Research date:** 2026-04-16
**Valid until:** 2026-05-16 (stable -- internal codebase patterns, no external API changes)
