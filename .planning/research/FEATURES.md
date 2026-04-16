# Feature Landscape

**Domain:** Tool description optimization & system prompt evolution for DSPy+GEPA agent self-improvement pipeline
**Researched:** 2026-04-15

## Table Stakes

Features users expect. Missing = pipeline is useless or untrustworthy.

### Phase 2: Tool Description Optimization

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **ToolDescriptionModule** (DSPy module wrapper) | Without it, GEPA cannot optimize tool descriptions -- this is the core abstraction. Must wrap tool description text as a DSPy Signature parameter, analogous to SkillModule. | Low | Follow SkillModule pattern exactly. Each tool description string becomes an optimizable parameter. Schema structure (param names, types, required) stays frozen -- only text evolves. |
| **Tool selection evaluator** | The fundamental fitness signal. Given (task, available_tools) -> did the agent pick the correct tool? Without this, there's no way to measure improvement. | Medium | Metric = tool_selection_accuracy (binary: right tool or not). Must also check parameter correctness as secondary signal. Use dspy.Predict with all tool schemas injected, score against ground truth tool name. |
| **Synthetic tool selection dataset builder** | GEPA needs training data. Generate (task_description, correct_tool, correct_params) triples. Without it, no optimization can run. | Medium | Extend existing SyntheticDatasetBuilder. Generate 10-20 tasks per tool (clear cases) + 10-20 "confuser" tasks (ambiguous cases where two tools overlap). Total ~200-400 triples, split 60/20/20. |
| **Cross-tool joint evaluation** | The critical differentiator from naive per-tool optimization. Optimizing one description in isolation can "steal" selections from other tools. Must evaluate ALL descriptions together. | High | This is the hardest part. Fitness function must penalize regressions on any individual tool's selection rate, not just optimize global accuracy. See ACL 2025 joint optimization paper (Bingo-W/ToolOptimization). |
| **Size constraint validation** | Tool descriptions are sent with every API call. Bloated descriptions waste tokens across every conversation turn. Existing ConstraintValidator already handles 500-char tool desc and 200-char param desc limits. | Low | Already implemented in constraints.py. Just wire it into the Phase 2 pipeline. Add length_penalty to fitness (already in fitness.py pattern). |
| **Factual accuracy preservation** | An evolved description that claims a tool does something it doesn't is worse than the original. Semantic drift detection is non-negotiable. | Medium | LLM-as-judge check: "Does this description accurately describe a tool that [original_functionality]?" Score 0-1. Reject if < 0.7. Could also use embedding similarity as fast proxy. |
| **CLI entry point: evolve_tool_descriptions** | Users need a way to run it. Follow existing Click+Rich pattern from evolve_skill. | Low | `python -m evolution.tools.evolve_tool_descriptions --iterations N`. Mirror evolve_skill.py structure. |

### Phase 3: System Prompt Section Evolution

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **PromptSectionModule** (DSPy module wrapper) | Each of the 5 evolvable prompt sections becomes a DSPy Signature field. Without this, GEPA cannot touch system prompt sections. | Low | Follow SkillModule/ToolDescriptionModule pattern. Read sections from prompt_builder.py (read-only). Sections: DEFAULT_AGENT_IDENTITY, MEMORY_GUIDANCE, SESSION_SEARCH_GUIDANCE, SKILLS_GUIDANCE, PLATFORM_HINTS. |
| **Behavioral evaluator** | System prompt quality is measured by behavior, not content. "Does the agent save memories when it should?" not "Does the prompt mention memories?" | High | Build per-section behavioral test scenarios. Each scenario = (user_input, expected_agent_behavior). Score via LLM-as-judge on whether the behavior occurred. This is harder than tool selection because behaviors are fuzzy. |
| **Per-section behavioral test suite** | Each section controls different agent behaviors. Tests must be targeted, not generic. | Medium | MEMORY_GUIDANCE: "Does agent save preferences?" (10 scenarios). SESSION_SEARCH: "Does agent search when user says 'like last time'?" (10 scenarios). SKILLS_GUIDANCE: "Does agent load relevant skills?" (10 scenarios). IDENTITY: "Is response direct, helpful, not verbose?" (20 scenarios). PLATFORM_HINTS: "Does CLI avoid markdown?" (10/platform). Total ~60-80. |
| **Growth constraint** (max +20% over baseline) | System prompt bloat degrades model attention and increases cost. Existing ConstraintValidator already implements growth checking. | Low | Already implemented. Wire into Phase 3 pipeline. |
| **Prompt caching compatibility check** | Hermes relies on prompt caching. Evolved prompts must not break cache boundaries. Changes deploy on next session only, never mid-conversation. | Low | Enforce as a deployment rule, not a code check. Document in pipeline output: "Apply to new sessions only." |
| **CLI entry point: evolve_prompt_section** | `python -m evolution.prompts.evolve_prompt_section --section MEMORY_GUIDANCE --iterations N` | Low | Follow existing Click+Rich CLI pattern. |

## Differentiators

Features that set this pipeline apart from generic prompt optimization. Not expected, but high value.

### Phase 2: Tool Description Optimization

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **SessionDB-mined misselection patterns** | Real user data beats synthetic data. Find conversations where agent used terminal(grep) when search_files was better, or vice versa. These become the highest-value training examples. | Medium | Query SessionDB for tool_call entries. Use LLM-as-judge to score whether the tool choice was optimal for the task context. Misselections become hard negatives in the dataset. Requires HERMES_AGENT_REPO SessionDB access. |
| **Confuser task generation** | Most tool selection failures happen on ambiguous tasks, not obvious ones. Deliberately generating tasks where 2+ tools could work but one is clearly better creates a harder, more discriminating eval set. | Medium | "Search for a specific error message in logs" -> search_files or terminal(grep)? The confuser set forces descriptions to be precise about when-to-use guidance, not just what-it-does. |
| **Per-parameter description optimization** | Tool descriptions include parameter-level descriptions (max 200 chars each). Optimizing these alongside the top-level description improves parameter correctness, not just tool selection. | Medium | Extend ToolDescriptionModule to include parameter descriptions as additional optimizable fields. Evaluate parameter_correctness alongside tool_selection_accuracy. |
| **Regression guard with per-tool selection rates** | Beyond global accuracy, track each tool's individual selection rate. Flag if any single tool's rate drops >5%, even if overall accuracy improves. | Low | Simple bookkeeping during evaluation. Report per-tool metrics alongside composite score. Critical for catching "description stealing" where one tool's improvement comes at another's expense. |
| **Think-augmented tool selection** | Add a "reasoning" step before tool selection to improve accuracy on complex multi-step tasks. Based on TAFC (Think-Augmented Function Calling, 2025). | Medium | Could be a future enhancement. For now, focus on description text quality. Note: this changes agent behavior, not just descriptions -- may be out of scope for Phase 2 if we're only evolving text. |

### Phase 3: System Prompt Section Evolution

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Section-local textual gradients** (MPO pattern) | Modular Prompt Optimization (MPO, arxiv 2601.04055) shows that optimizing structured prompts section-by-section with local gradients outperforms global updates. Maps perfectly to Hermes' sectioned prompt_builder.py. | Medium | GEPA already supports targeted module selection. Use GEPA's reflective analysis on per-section failures to generate section-specific improvement suggestions. Optimize independently first, then jointly. |
| **Personality/tone drift detection** | System prompt changes can subtly shift the agent's personality. Detect when the agent becomes more verbose, less direct, or loses core traits (helpful, admits uncertainty). | Medium | Automated tone comparison: run 10 generic tasks with baseline vs evolved prompt, use LLM-as-judge to score tone consistency on dimensions (directness, helpfulness, verbosity, honesty). Flag if any dimension shifts >15%. |
| **Joint section optimization** | After optimizing sections independently, run a joint optimization pass that evolves all sections together. Captures cross-section interactions that per-section optimization misses. | High | Run per-section first (cheaper, faster signal), then joint pass with all 5 sections as parameters. Joint pass is expensive (GEPA has more parameters to explore) but catches interactions like MEMORY_GUIDANCE conflicting with SESSION_SEARCH_GUIDANCE. |
| **Benchmark-gated validation** | Use TBLite score as a hard regression gate. An evolved prompt that scores higher on behavioral tests but lower on TBLite is REJECTED. Zero tolerance for benchmark regression on system prompt changes. | Medium | Already partially implemented (config has run_tblite flag). Wire benchmark_gate.py into Phase 3 pipeline. Run TBLite fast subset (20 tasks, ~20 min) as gate before full evaluation. |
| **SessionDB behavioral pattern mining** | Mine real sessions for behavioral failures: agent didn't search memory when it should have, was too verbose, used wrong formatting for the platform. These become targeted test cases. | Medium | Query SessionDB for patterns like user corrections ("no, I meant...", "you already know this"), format complaints, skill loading failures. Each pattern becomes a behavioral test scenario. |

## Anti-Features

Features to explicitly NOT build. These are tempting but wrong for this project.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| **Batch_runner integration / hermes-agent runtime dependency** | PLAN.md explicitly scopes this out. The pipeline must be standalone, reading from hermes-agent but never importing its runtime. Adding runtime dependency makes the pipeline fragile and couples release cycles. | Use DSPy's own dspy.Predict/ChainOfThought for evaluation. Simulate agent behavior through DSPy modules, not by running actual hermes-agent sessions. |
| **Real-time hot-swapping of descriptions/prompts** | Mid-conversation changes break prompt caching and create unpredictable behavior. Every constraint in the plan says "changes apply on next session only." | Output evolved artifacts to output/ directory. Changes deploy via PR merge, taking effect on next fresh session. |
| **Auto-merge without human review** | Evolved text is LLM-generated. Even with constraints and benchmarks, human review catches subtle issues (factual inaccuracy, tone drift, unintended implications) that automated checks miss. | Always output a PR (or output/ files). Include before/after diff, scores on train/val/holdout, constraint validation results. Human decides whether to merge. |
| **Individual tool description optimization** (without joint eval) | Optimizing tool descriptions one at a time WILL cause regressions in other tools. This is the most common pitfall in the domain (ACL 2025 joint optimization paper confirms it). | Always evaluate all tool descriptions together. Fitness function must penalize any individual tool's selection rate regression. |
| **Full TerminalBench2/YC-Bench as per-iteration gate** | These benchmarks take 2-6 hours and cost $50-200 each. Running them on every candidate is prohibitively expensive. | Use task-specific eval datasets for per-iteration fitness. Reserve full benchmarks for final candidate validation only (top 1-3 candidates). |
| **Evolving tool schema structure** (parameter names, types, required fields) | Schema changes break callers and tool discovery. The plan explicitly freezes schema structure. | Only evolve description TEXT fields. Parameter names, types, required flags are immutable. |
| **Prompt-level A/B testing infrastructure** | Building production A/B testing is a Phase 5 concern (continuous improvement loop). Premature for Phase 2/3. | Output comparison reports (baseline vs evolved scores). Let human reviewer decide based on metrics. A/B testing can be added later if needed. |
| **GPU-based fine-tuning or weight updates** | The entire plan operates via API calls only. DSPy+GEPA mutates TEXT, not weights. BootstrapFinetune is explicitly excluded. | Keep everything as text evolution through GEPA's reflective prompt mutation. No model training required. |

## Feature Dependencies

```
Phase 2 dependencies:
  SyntheticDatasetBuilder (existing) --> Tool Selection Dataset Builder
  ConstraintValidator (existing) --> Tool Description Constraints (wiring only)
  LLMJudge (existing) --> Tool Selection Evaluator (extends scoring dimensions)
  SkillModule pattern (existing) --> ToolDescriptionModule (follows same pattern)
  ToolDescriptionModule --> Cross-tool Joint Evaluation (needs all modules together)
  Tool Selection Dataset Builder --> Cross-tool Joint Evaluation (needs data)

Phase 3 dependencies:
  Phase 2 validated --> Phase 3 starts (plan requires sequential gating)
  ToolDescriptionModule pattern --> PromptSectionModule (follows same pattern)
  LLMJudge (existing) --> Behavioral Evaluator (extends with behavior dimensions)
  SyntheticDatasetBuilder (existing) --> Behavioral Test Suite Generator
  PromptSectionModule --> Per-section optimization
  Per-section optimization --> Joint section optimization (do independent first)
  Behavioral Evaluator --> Tone drift detection (uses same scoring infrastructure)
```

## MVP Recommendation

### Phase 2 MVP (Tool Description Optimization)

Prioritize:
1. **ToolDescriptionModule** -- core abstraction, low complexity, follow existing pattern
2. **Tool selection evaluator** -- the fitness function, medium complexity, essential
3. **Synthetic tool selection dataset builder** -- extend existing builder, medium complexity
4. **Cross-tool joint evaluation** -- the hard part but non-negotiable for correctness
5. **CLI entry point** -- low complexity, needed to actually run it

Defer:
- SessionDB mining: valuable but not needed for first run; synthetic data is sufficient to prove the pipeline works
- Per-parameter optimization: adds complexity; start with top-level descriptions only
- Think-augmented selection: changes agent behavior, not just descriptions; belongs in a future iteration

### Phase 3 MVP (System Prompt Evolution)

Prioritize:
1. **PromptSectionModule** -- core abstraction, low complexity
2. **Behavioral evaluator** -- the fitness function, high complexity, essential
3. **Per-section behavioral test suite** -- medium complexity, defines what "better" means
4. **Growth constraint wiring** -- low complexity, safety net
5. **CLI entry point** -- low complexity

Defer:
- Joint section optimization: start with per-section only; joint pass adds complexity and cost
- Personality drift detection: important but can be a manual check in v1; automate later
- Benchmark gating: valuable but expensive; defer to final validation step, not per-iteration
- SessionDB mining: same rationale as Phase 2 -- synthetic first, real data later

## Phase Ordering Rationale

Phase 2 MUST come before Phase 3 because:
1. Tool descriptions are a simpler optimization target (classification-like problem with clear right/wrong answers)
2. Phase 2 validates that GEPA can optimize non-skill text artifacts
3. System prompt changes have wider blast radius -- you want proven infrastructure before attempting them
4. Behavioral evaluation (Phase 3) is inherently fuzzier than tool selection accuracy (Phase 2) -- build confidence on the easier problem first

## Sources

- [ACL 2025: A Joint Optimization Framework for Tool Utilization](https://github.com/Bingo-W/ToolOptimization) -- joint tool description optimization, cross-tool regression prevention
- [Modular Prompt Optimization (MPO)](https://arxiv.org/abs/2601.04055) -- section-local textual gradients for structured prompts
- [GEPA: Reflective Prompt Evolution](https://dspy.ai/api/optimizers/GEPA/overview/) -- GEPA optimizer docs, Pareto frontier strategy
- [GEPA Paper (ICLR 2026 Oral)](https://arxiv.org/abs/2507.19457) -- outperforms GRPO by 6%, MIPROv2 by 10%+
- [DSPy Advanced Tool Use](https://dspy.ai/tutorials/tool_use/) -- DSPy tool integration patterns
- [ToolACE (ICLR 2025)](https://arxiv.org/html/2409.00920v2) -- tool calling data synthesis pipeline
- [Think-Augmented Function Calling](https://arxiv.org/html/2601.18282) -- reasoning before tool selection
- [Confident AI: LLM Agent Evaluation Guide](https://www.confident-ai.com/blog/llm-agent-evaluation-complete-guide) -- tool selection accuracy metrics
- [Statsig: Tool Calling Optimization](https://www.statsig.com/perspectives/tool-calling-optimization) -- practical tool selection improvement techniques
- [promptolution](https://arxiv.org/abs/2512.02840) -- modular prompt optimization framework
- [PromptBench](https://www.emergentmind.com/topics/promptbench) -- prompt robustness evaluation
