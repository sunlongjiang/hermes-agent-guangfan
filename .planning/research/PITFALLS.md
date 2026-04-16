# Domain Pitfalls: DSPy-based Tool Description & System Prompt Optimization

**Domain:** LLM prompt/tool description optimization via DSPy+GEPA
**Researched:** 2026-04-15
**Confidence:** MEDIUM-HIGH (verified against DSPy docs, published case studies, and practitioner critiques)

---

## Critical Pitfalls

Mistakes that cause rewrites, wasted optimization budget, or produce artifacts that look improved on metrics but degrade real-world performance.

---

### Pitfall 1: Modular Decomposition Mismatch for Agentic Workflows

**What goes wrong:** GEPA assumes modules have discrete steps with clear inputs/outputs that can be improved in isolation. Tool descriptions and system prompt sections do NOT work this way -- they interact holistically during agent execution. Optimizing a tool description in isolation from other tool descriptions (or from the system prompt) produces locally-optimal but globally-incoherent results.

**Why it happens:** Phase 1 (skills) wraps a single text artifact as a DSPy module, which fits GEPA's model well. Naively applying the same pattern to Phase 2 (tool descriptions) fails because tool selection is a *comparative* decision across ALL available tools, not an evaluation of one tool in isolation.

**Consequences:**
- Evolved tool descriptions that score well individually but cause cross-tool interference
- Tool A's description "steals" selection from Tool B (e.g., `search_files` description becomes so broad it gets selected over `read_file`)
- System prompt sections that conflict with each other after independent optimization

**Warning signs:**
- Individual tool selection accuracy goes up but overall task completion goes down
- One tool's selection rate spikes while a related tool's rate drops
- Evolved descriptions contain overlapping or contradictory guidance

**Prevention:**
- **Phase 2:** Always evaluate ALL tool descriptions jointly, never in isolation. The fitness function must penalize regressions on ANY individual tool's selection rate, not just the one being optimized. PLAN.md already specifies "cross-tool evaluation" -- this is the single most important Phase 2 design decision.
- **Phase 3:** Evaluate the full assembled system prompt, not individual sections. Optimize sections independently first (for efficiency), but validate jointly before accepting.
- Implement a "no-regression gate": any candidate that improves target metric but regresses any other tool/section by >2% is rejected.

**Detection:** Track per-tool selection accuracy as a vector, not a scalar. Alert on any single-tool regression even if the aggregate improves.

**Phase:** Phase 2 (primary), Phase 3 (secondary)

**Confidence:** HIGH -- this is explicitly called out in the PLAN.md cross-tool evaluation requirement, corroborated by Microsoft research on tool-space interference and Anderson's critique of DSPy for agentic workflows.

---

### Pitfall 2: LLM-as-Judge Scoring Instability Corrupts the Optimization Signal

**What goes wrong:** The current `skill_fitness_metric` in `fitness.py` uses a keyword-overlap heuristic for speed, and the `LLMJudge` uses pointwise 0-1 scoring on three dimensions. Both approaches produce noisy, unreliable fitness signals that GEPA then optimizes against -- amplifying noise rather than real quality.

**Why it happens:**
- The keyword-overlap heuristic (`skill_fitness_metric`) is a terrible proxy for tool selection accuracy or prompt effectiveness. A response containing the right words in the wrong order scores well.
- Pointwise LLM-as-judge scoring (0.0-1.0 float) has documented instability: the same response can score 0.6 on one evaluation and 0.8 on another. Research shows absolute scores are "much more likely to fluctuate compared to pairwise comparisons."
- LLM judges exhibit position bias, length bias, and score clustering around training-data-common values.
- With only 20 eval examples (current `eval_dataset_size`), noise dominates signal.

**Consequences:**
- GEPA optimizes toward artifacts that game the judge's biases rather than genuinely improving
- "Improvements" that don't replicate on holdout or in production
- Evolutionary drift toward verbose descriptions (length bias in LLM judges)
- Wasted API budget on optimization runs that produce noise

**Warning signs:**
- High variance in scores across optimization runs with identical inputs
- Evolved artifacts score higher but human reviewers see no improvement
- Scores on holdout set don't track training set improvements (classic overfitting-to-judge)

**Prevention:**
- **Phase 2 (tool descriptions):** Replace the generic LLM judge with a *binary classification metric*: did the agent select the correct tool? YES=1, NO=0. This is deterministic and unambiguous. No LLM judge needed for the core metric.
- **Phase 3 (system prompt):** Use pairwise comparison (A vs B) instead of pointwise scoring where possible. Binary evaluations ("did the agent search memory when it should have?" YES/NO) are more reliable than float scores.
- Add score calibration: run the judge 3x on the same input, reject examples where variance > threshold.
- Increase `eval_dataset_size` from 20 to at least 50 for Phase 2, 80+ for Phase 3.
- The existing `skill_fitness_metric` heuristic MUST NOT be reused for Phase 2/3 -- it's a skill-specific shortcut that doesn't generalize.

**Detection:** Track judge inter-run agreement (score the same example 3 times, compute variance). If mean variance > 0.15, the judge is too noisy to drive optimization.

**Phase:** Phase 2 and Phase 3 (both require new fitness functions; reusing Phase 1's will fail)

**Confidence:** HIGH -- LLM-as-judge instability is well-documented in multiple 2025 surveys. The current `fitness.py` keyword-overlap heuristic is clearly unsuitable for tool selection or behavioral evaluation.

---

### Pitfall 3: Overfitting to Small Synthetic Evaluation Datasets

**What goes wrong:** GEPA optimizes the evolved text to perform well on 10 training examples, producing artifacts that are overfit to the specific phrasing and scenarios in those examples. The improvement doesn't generalize.

**Why it happens:**
- Current config: `eval_dataset_size=20`, `train_ratio=0.5` = 10 training examples. DSPy's own docs recommend "at least 300 examples" for robust optimization.
- Synthetic datasets generated by a single LLM call share systematic biases (similar phrasing patterns, similar difficulty distribution, limited scenario diversity).
- GEPA is sample-efficient (works with as few as 3 examples) but "works" means "converges," not "generalizes." Small datasets converge to narrow optima.
- Dropbox found their optimizer would "copy specific keywords, usernames, or verbatim document phrases directly into prompts" when training on small sets.

**Consequences:**
- Tool descriptions optimized for 10 synthetic scenarios that don't represent real-world tool use distribution
- System prompt sections that handle test scenarios perfectly but break on edge cases
- Holdout scores plateau or degrade while training scores keep climbing (classic overfitting)

**Warning signs:**
- Training score >> holdout score (gap > 15%)
- Evolved text contains very specific phrasing that mirrors the training examples
- Performance degrades on manually-constructed test cases not in the synthetic set

**Prevention:**
- **Phase 2:** Build tool selection datasets from MULTIPLE sources: synthetic generation (diverse prompts), SessionDB mining (real usage patterns), and benchmark-derived examples (TBLite failures). Target 200-400 examples as PLAN.md specifies.
- **Phase 3:** Build behavioral test suites from 60-80 examples across all sections as PLAN.md specifies. Include adversarial cases.
- Use DSPy's recommended 20/80 train/val split (not the current 50/25/25). GEPA uses valset for Pareto tracking -- a large valset is more important than a large trainset.
- Generate synthetic data in multiple independent LLM calls with different system prompts to increase diversity.
- Add an explicit "no-verbatim-copying" constraint: reject candidates where the evolved text contains verbatim phrases from training examples.

**Detection:** Monitor training-holdout score gap. If gap exceeds 15% during optimization, stop and diversify the dataset.

**Phase:** Phase 2 (critical -- tool selection needs diverse scenarios), Phase 3 (critical -- behavioral tests need broad coverage)

**Confidence:** HIGH -- Dropbox's production DSPy case study confirmed this exact failure mode. DSPy docs explicitly recommend larger datasets than our current config provides.

---

### Pitfall 4: Semantic Drift in Evolved Tool Descriptions (Factual Inaccuracy)

**What goes wrong:** GEPA evolves tool descriptions that improve selection accuracy by making claims the tool can't actually deliver. The optimizer discovers that *lying about capabilities* is an effective optimization strategy.

**Why it happens:**
- The fitness function measures "did the agent select the right tool?" but not "is the description factually accurate?"
- GEPA has no grounding in the actual tool implementation. It only sees inputs/outputs of the selection task.
- A description that says "search_files can search across all file types including binary, archives, and databases" will get selected more often -- even if search_files can only search text files.
- The PLAN.md constraint "must remain factually accurate" is stated but not enforced in `constraints.py`.

**Consequences:**
- Agent selects tools for tasks they can't actually perform, leading to runtime failures
- Users lose trust when tool selection seems right but execution fails
- Downstream code (parameter construction, result parsing) breaks because the description implied capabilities that don't exist

**Warning signs:**
- Tool selection accuracy improves but task completion rate drops
- Evolved descriptions contain capability claims not in the original
- Agent starts attempting operations the tool doesn't support

**Prevention:**
- Add a `factual_accuracy` constraint to `ConstraintValidator`: cross-reference evolved descriptions against the tool's actual parameter schema and implementation.
- Include "negative selection" examples in the dataset: tasks where the tool should NOT be selected. If the evolved description causes false-positive selection, penalize heavily.
- Freeze factual claims (what the tool does, what file types it supports, what parameters it accepts) and only allow GEPA to optimize the *framing* (when to use it, how it compares to alternatives, behavioral guidance).
- Implement a two-part description structure: frozen factual section + evolvable guidance section.

**Detection:** After each optimization round, run the evolved description through an LLM check: "Does this description claim capabilities not present in the tool's parameter schema?" Also monitor task completion rate alongside selection accuracy.

**Phase:** Phase 2 (this is Phase 2's most dangerous failure mode)

**Confidence:** HIGH -- this is a well-known failure mode in any text optimization where the objective function doesn't penalize hallucination. The current `constraints.py` checks size and growth but NOT factual accuracy.

---

### Pitfall 5: System Prompt Changes Have Unbounded Blast Radius

**What goes wrong:** A small change to one system prompt section (e.g., MEMORY_GUIDANCE) causes unexpected behavioral shifts in unrelated areas (e.g., tool selection, response verbosity, personality drift). The optimization loop can't detect these second-order effects because they aren't measured.

**Why it happens:**
- System prompt sections are read holistically by the LLM. There are no "boundaries" between sections at the model's attention level.
- The optimizer's behavioral tests only cover the section being optimized. A change to MEMORY_GUIDANCE that says "always check your memory before responding" can cause the agent to delay tool calls while it searches memory first.
- Unlike tool descriptions (which have a narrow, measurable effect on tool selection), system prompt changes affect *everything*.
- PLAN.md acknowledges this: "system prompt changes have the widest blast radius" and recommends "multiple human reviewers."

**Consequences:**
- Agent personality drifts (becomes more verbose, less direct, changes tone)
- Latency increases from behavioral changes (e.g., agent adds extra memory checks)
- Benchmark regression on tasks unrelated to the optimized section
- Hard to debug because the cause-effect chain is indirect

**Warning signs:**
- Benchmark scores shift in areas unrelated to the optimized section
- Agent response length changes significantly
- Users report "something feels different" without being able to pinpoint what

**Prevention:**
- **Mandatory full benchmark gate** after every system prompt optimization round (not just final validation). PLAN.md's "zero tolerance for regression" is correct -- enforce it.
- Measure a broad behavioral fingerprint before and after optimization: average response length, tool call frequency, memory access frequency, first-response latency. Any significant shift (even "improvements") should trigger human review.
- Optimize one section at a time, with full behavioral regression suite between sections.
- Set a strict growth limit (the 20% max in `constraints.py` is already there -- good).
- Add a "personality preservation" check: run 10 open-ended conversational prompts and compare tone/style before and after.

**Detection:** Automated behavioral fingerprinting. Compute statistics (response length distribution, tool call distribution, memory access frequency) on a fixed test set before and after optimization. Flag any statistically significant shift.

**Phase:** Phase 3 (this is Phase 3's defining challenge)

**Confidence:** HIGH -- this is well-understood in prompt engineering literature. The PLAN.md explicitly acknowledges it.

---

## Moderate Pitfalls

---

### Pitfall 6: Prompt Caching Breakage From Evolved Content

**What goes wrong:** Evolved tool descriptions or system prompt sections change frequently enough (or at wrong boundaries) to defeat prompt caching, dramatically increasing API costs.

**Why it happens:** Prompt caching works by detecting identical prefix content across API calls. If tool descriptions change, the cached prefix becomes invalid. Even a single character change to a tool description that's sent every turn invalidates the entire cache.

**Prevention:**
- Never deploy evolved content mid-session (PLAN.md already enforces this).
- Batch tool description changes: deploy all evolved descriptions together as a single version bump, not incrementally.
- Test cache hit rates before and after deploying evolved content.
- For system prompt sections, ensure evolved sections maintain the same position and structure in the assembled prompt.

**Phase:** Phase 2 (tool descriptions sent every turn), Phase 3 (system prompt cached at session start)

**Confidence:** MEDIUM -- PLAN.md covers this well, but implementation must enforce it strictly.

---

### Pitfall 7: Optimization Budget Explosion from Expensive Evaluation

**What goes wrong:** Each GEPA iteration requires running the full agent on multiple test cases. For tool selection, this means N test cases x M tools x K iterations of full LLM inference. Costs spiral to hundreds of dollars per optimization run.

**Why it happens:**
- Phase 1 (skills) evaluates one skill at a time with ~20 examples. Phase 2 needs to evaluate ALL tools jointly on 200-400 examples. Phase 3 needs full agent runs for behavioral testing.
- The PLAN.md estimates "$2-10 per run" for GEPA, but this assumed Phase 1's scope. Phase 2/3 evaluation is 10-50x more expensive per iteration.
- GEPA's "20-100 evaluations" requirement means 20-100 full evaluation rounds, each running 200+ test cases.

**Prevention:**
- Use a tiered evaluation strategy: cheap proxy metric (e.g., tool selection without full execution) for GEPA's inner loop, expensive full evaluation only for top candidates.
- For Phase 2, tool selection can be evaluated without actually running the tools -- just check which tool the LLM picks given a task description and the tool schema. This is a single LLM call per test case, not a full agent run.
- For Phase 3, use GEPA's `sample_fraction` to evaluate on subsets during exploration, full set for final validation.
- Set hard budget caps per optimization run ($20 for Phase 2, $50 for Phase 3). Kill the run if budget exceeded.
- Use `eval_model` (gpt-4.1-mini) not `optimizer_model` (gpt-4.1) for evaluation calls.

**Phase:** Phase 2 and Phase 3

**Confidence:** MEDIUM -- cost depends on implementation choices. The cheap-proxy strategy is well-established in DSPy's documentation.

---

### Pitfall 8: Train/Val/Holdout Data Leakage Through Synthetic Generation

**What goes wrong:** When the same LLM generates all synthetic training, validation, and holdout examples in a single call (as the current `SyntheticDatasetBuilder.generate()` does), the splits share systematic biases. The holdout set doesn't truly test generalization because it was generated by the same process with the same biases.

**Why it happens:** `dataset_builder.py` generates all examples in one LLM call, shuffles, and splits. The LLM produces examples with correlated difficulty, phrasing patterns, and scenario types. Shuffling doesn't remove correlation.

**Prevention:**
- Generate train, val, and holdout sets in SEPARATE LLM calls with different system prompts or temperature settings.
- Mix synthetic data with real SessionDB data -- use synthetic for training but real data for holdout where possible.
- For Phase 2, derive holdout examples from actual benchmark failures (TBLite misselections) which have fundamentally different distribution from synthetic examples.
- Consider having a human-curated "golden" holdout set for the most critical evaluations (PLAN.md mentions this as Source C).

**Phase:** Phase 2 and Phase 3

**Confidence:** MEDIUM -- this is a standard ML pitfall, not specific to DSPy, but the current code structure makes it likely.

---

### Pitfall 9: GEPA Reflective Feedback Quality Degrades Without Execution Traces

**What goes wrong:** GEPA's key advantage over other optimizers is its ability to analyze WHY failures happened (reflective analysis of execution traces). If the evaluation pipeline only returns a score without a trace of the agent's decision process, GEPA degenerates into blind mutation -- no better than random search.

**Why it happens:**
- Phase 1's `SkillModule.forward()` returns only `output` text. There's no trace of the agent's reasoning, tool selection process, or intermediate decisions.
- For Phase 2, the critical information is "why did the agent pick tool A instead of tool B?" Without this trace, GEPA can't reason about description quality.
- For Phase 3, the critical information is "how did the system prompt influence the agent's behavior?" Without trace data, GEPA is blind.

**Prevention:**
- Return chain-of-thought reasoning alongside the output from evaluation runs. DSPy's `ChainOfThought` already captures this -- pipe it to GEPA as feedback.
- For Phase 2, capture the LLM's tool selection reasoning (many models expose this in their response). Feed it to GEPA as context.
- Use the `feedback` field in `FitnessScore` (already in `fitness.py`) to provide rich, structured feedback to GEPA, not just a score.
- PLAN.md mentions "captures execution traces for GEPA's reflective analysis" in Phase 1 -- make sure Phase 2/3 implementations don't skip this.

**Phase:** Phase 2 (tool selection reasoning traces), Phase 3 (behavioral reasoning traces)

**Confidence:** MEDIUM -- GEPA's documentation emphasizes feedback as critical, and the current code structure supports it via `FitnessScore.feedback`, but it's easy to overlook during Phase 2/3 module design.

---

## Minor Pitfalls

---

### Pitfall 10: Tool Description Size Budget is Too Tight for Meaningful Optimization

**What goes wrong:** The 500-char limit for tool descriptions (`max_tool_desc_size`) leaves very little room for GEPA to add guidance about when to use vs. not use a tool. The optimizer converges to trivially different variants because the design space is too constrained.

**Prevention:**
- Accept that 500 chars is a hard constraint (it's sent every API call). Optimize within it, but don't expect dramatic changes.
- Focus GEPA's optimization on the high-signal parts: the "when to use" and "when NOT to use" framing, not the factual description.
- Consider splitting the budget: 200 chars for factual description (frozen), 300 chars for evolvable guidance.

**Phase:** Phase 2

**Confidence:** LOW -- may not be a real problem. The 500-char limit is tight but GEPA might find efficient phrasings.

---

### Pitfall 11: Parallel Optimization of Correlated Sections Causes Oscillation

**What goes wrong:** If Phase 3 optimizes multiple system prompt sections in parallel (or in quick succession), changes to section A can invalidate the optimization of section B. The system oscillates between configurations without converging.

**Prevention:**
- Optimize one section at a time, sequentially. Run full validation between sections.
- If joint optimization is attempted, freeze all other sections while optimizing one.
- After all sections are individually optimized, do one joint validation pass and accept only if the combined result is better than baseline.

**Phase:** Phase 3

**Confidence:** MEDIUM -- standard optimization problem. PLAN.md mentions "per-section and joint optimization" which suggests awareness, but the ordering matters.

---

### Pitfall 12: Parameter Description Optimization Neglected in Favor of Top-Level Description

**What goes wrong:** Phase 2 focuses on the top-level tool `description` field but ignores per-parameter descriptions (capped at 200 chars each). In practice, parameter descriptions often cause more confusion than tool-level descriptions -- agents select the right tool but pass wrong parameters.

**Prevention:**
- Include parameter correctness in the Phase 2 fitness function (PLAN.md mentions `parameter_correctness` as part of the score).
- Evolve parameter descriptions alongside top-level descriptions.
- Build test cases that specifically test parameter usage, not just tool selection.

**Phase:** Phase 2

**Confidence:** MEDIUM -- the PLAN.md mentions this but it could easily be deprioritized during implementation.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation | Severity |
|-------------|---------------|------------|----------|
| Phase 2: Tool description module design | Treating tool descriptions independently (Pitfall 1) | Always evaluate all descriptions jointly with cross-tool regression gates | Critical |
| Phase 2: Tool selection fitness function | Reusing Phase 1's keyword-overlap heuristic (Pitfall 2) | Build a binary tool-selection metric (correct tool: yes/no) | Critical |
| Phase 2: Factual accuracy | GEPA invents tool capabilities (Pitfall 4) | Freeze factual claims, only optimize framing/guidance | Critical |
| Phase 2: Evaluation dataset | 20 synthetic examples insufficient (Pitfall 3) | Target 200-400 examples from multiple sources | High |
| Phase 3: System prompt blast radius | Optimizing one section breaks unrelated behavior (Pitfall 5) | Full behavioral fingerprinting + benchmark gate after every round | Critical |
| Phase 3: Section interaction | Parallel section optimization oscillates (Pitfall 11) | Sequential optimization, one section at a time, validate between each | Moderate |
| Phase 3: Personality drift | Evolved prompt changes agent tone/character (Pitfall 5) | Personality preservation check on open-ended test prompts | High |
| Both: Budget management | Full agent runs per evaluation are too expensive (Pitfall 7) | Tiered evaluation: cheap proxy inner loop, expensive full eval for top candidates only | High |
| Both: GEPA effectiveness | No execution traces = blind mutation (Pitfall 9) | Pipe chain-of-thought and tool selection reasoning to GEPA feedback | High |
| Both: Data quality | Single-call synthetic generation biases all splits (Pitfall 8) | Separate generation calls per split, mix with real SessionDB data | Moderate |

---

## Key Insight: Phase 2 and Phase 3 Are Fundamentally Different From Phase 1

The most dangerous meta-pitfall is assuming that Phase 1's patterns transfer directly. They do NOT:

| Aspect | Phase 1 (Skills) | Phase 2 (Tool Descriptions) | Phase 3 (System Prompt) |
|--------|-------------------|----------------------------|------------------------|
| **Optimization unit** | Single text file | All tool descriptions jointly | All prompt sections jointly |
| **Evaluation** | Output quality (subjective) | Tool selection (binary, measurable) | Behavioral patterns (complex, multi-dimensional) |
| **Fitness function** | LLM-as-judge works OK | LLM-as-judge is wrong approach; use binary selection accuracy | Needs mixed metrics: binary behavioral checks + benchmark gates |
| **Blast radius** | Limited to one skill | Cross-tool interference | Everything the agent does |
| **Data needs** | 20 examples sufficient | 200-400 examples needed | 60-80 behavioral scenarios needed |
| **Cost per eval** | Low (single LLM call) | Medium (tool selection across all tools) | High (full agent behavioral test) |

Treating Phase 2/3 as "Phase 1 but with different text" is the single biggest mistake this project can make.

---

## Sources

- [DSPy GEPA Overview](https://dspy.ai/api/optimizers/GEPA/overview/) -- GEPA train/val split best practices, feedback mechanism
- [DSPy Optimization Overview](https://dspy.ai/learn/optimization/overview/) -- 20/80 train/val split recommendation, dataset sizing
- [Contra DSPy and GEPA -- Benjamin Anderson](https://benanderson.work/blog/contra-dspy-gepa/) -- Critique of DSPy/GEPA for agentic workflows (LOW confidence, single source)
- [Dropbox DSPy Optimization Case Study](https://dropbox.tech/machine-learning/optimizing-dropbox-dash-relevance-judge-with-dspy) -- Overfitting to training examples, verbatim copying
- [Tool-Space Interference in the MCP Era -- Microsoft Research](https://www.microsoft.com/en-us/research/blog/tool-space-interference-in-the-mcp-era-designing-for-agent-compatibility-at-scale/) -- Cross-tool interference
- [LLM-as-a-Judge Survey](https://arxiv.org/abs/2411.15594) -- Scoring instability, position/length bias, binary vs pointwise
- [Learning to Rewrite Tool Descriptions for Reliable LLM-Agent Tool Use](https://arxiv.org/html/2602.20426v1) -- Tool description rewriting research
- [Evidently AI: LLM-as-a-Judge Guide](https://www.evidentlyai.com/llm-guide/llm-as-a-judge) -- Reliability mitigation strategies
- [Building Effective AI Agents -- Anthropic](https://www.anthropic.com/research/building-effective-agents) -- Tool design best practices
- [Optimizing Tool Calling -- Paragon](https://www.useparagon.com/learn/rag-best-practices-optimizing-tool-calling/) -- Tool calling optimization patterns
