# Project Research Summary

**Project:** hermes-agent-self-evolution
**Domain:** DSPy/GEPA-based multi-parameter text optimization for agent tool descriptions and system prompts
**Researched:** 2026-04-15
**Confidence:** MEDIUM-HIGH

## Executive Summary

This project extends Hermes' Phase 1 single-skill optimization pipeline to Phase 2 (tool descriptions) and Phase 3 (system prompt sections). The core technical challenge is **joint multi-parameter optimization** -- tool descriptions compete with each other for selection, and prompt sections interact holistically. Phase 1's "wrap one text blob in a DSPy Module" pattern does NOT transfer directly. The research conclusively shows that treating Phase 2/3 as "Phase 1 with different text" is the project's biggest risk.

The recommended approach is to use **GEPA's standalone `gepa.optimize()` API** (not DSPy Module wrapping) for both phases. This API directly maps multiple text components as dict keys, supports joint optimization via `component_selector="all"` (Phase 2) or `"round_robin"` (Phase 3), and provides the reflective feedback mechanism that makes GEPA effective. This introduces `gepa` as a new direct dependency but is architecturally cleaner than forcing tool descriptions into DSPy's predictor abstraction.

The top risks are: (1) cross-tool interference where improving one description degrades another, (2) semantic drift where GEPA invents false tool capabilities to win selections, (3) system prompt blast radius where a small section change breaks unrelated behaviors, and (4) overfitting to small synthetic datasets. All are preventable with the mitigations documented below, but each requires deliberate implementation -- none will be caught by default.

## Key Findings

### Recommended Stack

No new frameworks needed. DSPy >=3.0 and GEPA remain the core. The key change is using `gepa.optimize()` standalone API instead of `dspy.GEPA` via Module wrapping.

**Core technologies:**
- **DSPy >=3.0**: Orchestration framework, already integrated and validated in Phase 1
- **GEPA standalone (`pip install gepa`)**: Multi-component text optimization via `seed_candidate` dict -- directly maps N text blobs as N optimizable components
- **`component_selector="all"`** (Phase 2): Joint optimization prevents cross-tool description stealing
- **`component_selector="round_robin"`** (Phase 3): Per-section optimization for lower-coupling prompt sections

**What NOT to use:**
- Do NOT use DSPy Module predictor pattern for tool descriptions (descriptions are not predictor instructions)
- Do NOT use MIPROv2 (needs 200+ examples; Phase 3 has only 60-80)
- Do NOT use `skill_fitness_metric` keyword-overlap heuristic for Phase 2/3 (it's skill-specific and wrong for these domains)

### Expected Features

**Must have (table stakes):**
- Joint tool description optimization with cross-tool regression gates
- Binary tool selection metric (correct tool yes/no, not LLM-as-judge float)
- Synthetic dataset builder producing 200-400 tool selection triples
- Factual accuracy preservation (prevent GEPA from inventing capabilities)
- Per-section behavioral evaluator for system prompt optimization
- 60-80 behavioral test scenarios across 5 evolvable prompt sections
- CLI entry points following existing Click+Rich pattern
- Size/growth constraint validation (already implemented, just wire in)

**Should have (differentiators):**
- SessionDB-mined misselection patterns as high-value training data
- Confuser task generation (ambiguous tasks where 2+ tools could work)
- Per-parameter description optimization (not just top-level)
- Personality/tone drift detection for system prompt changes
- Benchmark-gated validation (TBLite as hard regression gate)

**Defer (v2+):**
- Joint section optimization (start per-section only)
- Think-augmented tool selection (changes agent behavior, not just text)
- SessionDB behavioral pattern mining
- Production A/B testing infrastructure

### Architecture Approach

Both phases follow the existing module-per-domain pattern: `evolution/tools/` and `evolution/prompts/` each get a loader, module, and orchestrator, sharing `evolution/core/`. The critical architectural decision is that tool descriptions are optimized jointly (all descriptions as one optimization unit) while prompt sections are optimized independently then validated jointly.

**Major components (new):**
1. **`tool_loader.py`** -- Extract tool descriptions from hermes-agent via regex, write evolved versions back
2. **`tool_module.py`** -- Wrap all tool descriptions as a single GEPA-optimizable unit
3. **`evolve_tools.py`** -- Orchestration + CLI, binary tool selection metric
4. **`prompt_loader.py`** -- Extract 5 evolvable prompt sections from `prompt_builder.py`
5. **`prompt_module.py`** -- Per-section DSPy Module with frozen context passthrough
6. **`evolve_prompt.py`** -- Orchestration + CLI, per-section then joint validation

**Shared core extensions (minimal):**
- Add config fields to `EvolutionConfig` (tool_selection_weight, behavioral_score_threshold)
- Add structural constraint checks to `constraints.py` (factual accuracy, section role preservation)

### Critical Pitfalls

1. **Cross-tool interference** -- Optimizing descriptions independently causes "description stealing." Prevention: always evaluate ALL descriptions jointly; reject any candidate where a single tool's selection rate drops >2%.

2. **Semantic drift / factual hallucination** -- GEPA discovers that lying about capabilities improves selection accuracy. Prevention: freeze factual claims, only allow GEPA to optimize framing/guidance; add factual accuracy constraint check.

3. **System prompt blast radius** -- Small section changes cause unpredictable behavioral shifts elsewhere. Prevention: full behavioral fingerprinting (response length, tool call frequency, tone) before and after; mandatory benchmark gate.

4. **Overfitting to small synthetic datasets** -- 10-20 training examples produce narrow optima that don't generalize. Prevention: 200-400 examples for Phase 2, 60-80 for Phase 3; generate splits in separate LLM calls; mix synthetic with SessionDB data.

5. **GEPA degrades without execution traces** -- Returning only scalar scores makes GEPA no better than random search. Prevention: pipe chain-of-thought reasoning and tool selection rationale as structured `feedback` to GEPA's reflective analysis.

## Implications for Roadmap

### Phase 2: Tool Description Optimization

**Rationale:** Lower risk than system prompts (bounded 500-char strings, binary measurable outcome). Validates that GEPA can optimize non-skill text artifacts. Must come before Phase 3.

**Delivers:** Evolved tool descriptions that improve agent tool selection accuracy without cross-tool regression.

**Build order:**
1. `tool_loader.py` (no dependencies, testable immediately)
2. `tool_module.py` (depends on loader)
3. Tool selection metric (standalone function)
4. Synthetic dataset builder extension (200-400 triples)
5. `evolve_tools.py` orchestrator + CLI
6. Constraint extensions (factual accuracy check)

**Avoids:** Pitfalls 1 (joint eval), 2 (binary metric not LLM judge), 4 (factual accuracy gate)

**Estimated cost per optimization run:** $0.50-4.00

### Phase 3: System Prompt Section Evolution

**Rationale:** Depends on Phase 2 proving the GEPA standalone pattern works. Higher risk due to behavioral evaluation complexity and unbounded blast radius.

**Delivers:** Evolved prompt sections that improve agent behavior per-section without personality drift or benchmark regression.

**Build order:**
1. `prompt_loader.py` (independent of Phase 2)
2. `prompt_module.py` (per-section + context passthrough)
3. Behavioral metric (LLM-as-judge with binary behavioral checks)
4. Behavioral test suite (60-80 scenarios across 5 sections)
5. `evolve_prompt.py` orchestrator + CLI
6. Constraint extensions (section role preservation)

**Avoids:** Pitfalls 5 (behavioral fingerprinting), 11 (sequential section optimization), 3 (larger dataset)

**Estimated cost per optimization run:** $1.00-5.00

### Phase Ordering Rationale

- Phase 2 before Phase 3: tool selection is a classification problem (binary correct/incorrect) while behavioral evaluation is inherently fuzzy. Build confidence on the measurable problem first.
- Phases are architecturally independent (both depend only on `core/`) but sequentially gated by PLAN.md for risk management.
- The GEPA standalone pattern validated in Phase 2 directly transfers to Phase 3, reducing Phase 3's technical risk.

### Research Flags

**Needs deeper research during planning:**
- **Phase 2 dataset design:** How to generate high-quality confuser tasks and ensure sufficient diversity. The synthetic-vs-SessionDB data mix ratio needs experimentation.
- **Phase 3 behavioral metrics:** Defining "correct behavior" for fuzzy sections like AGENT_IDENTITY is harder than tool selection. The LLM-as-judge approach needs careful calibration.
- **`gepa` package compatibility:** The standalone `gepa` package vs `dspy.GEPA` compatibility is LOW confidence. Must be validated before implementation starts.

**Standard patterns (skip research):**
- **Loader modules:** Regex extraction from Python source files is well-understood.
- **CLI entry points:** Follow existing Click+Rich pattern exactly.
- **Constraint validation:** Existing `ConstraintValidator` dispatch already handles new artifact types.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | GEPA standalone API well-documented; `component_selector` modes confirmed in official docs |
| Features | HIGH | Clear table stakes derived from PLAN.md + domain research; good separation of must-have vs defer |
| Architecture | HIGH | Direct extension of working Phase 1 patterns; codebase already designed for this expansion |
| Pitfalls | MEDIUM-HIGH | Critical pitfalls well-documented across multiple sources; some prevention strategies are theoretical (no production case studies for tool description optimization via GEPA) |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **`gepa` standalone package maturity:** LOW confidence on version compatibility with `dspy>=3.0`. Must run compatibility test before committing to this approach. Fallback: use `dspy.GEPA` with creative Module wrapping.
- **Factual accuracy constraint implementation:** No existing pattern for this. Need to design the LLM-based fact-check or embedding similarity approach during Phase 2 planning.
- **Behavioral metric calibration for Phase 3:** Binary behavioral checks are more reliable than float scores, but defining the binary criteria for each section requires domain expertise and iteration.
- **Cost projections:** The $0.50-5.00/run estimates are based on Phase 1 extrapolation. Actual costs with 200-400 examples and joint evaluation could be higher. Set hard budget caps.

## Sources

### Primary (HIGH confidence)
- [DSPy GEPA Overview](https://dspy.ai/api/optimizers/GEPA/overview/) -- optimizer configuration, component_selector modes
- [GEPA Standalone API Blog](https://gepa-ai.github.io/gepa/blog/2026/02/18/introducing-optimize-anything/) -- seed_candidate dict pattern
- [GEPA Paper (ICLR 2026 Oral)](https://arxiv.org/pdf/2507.19457) -- theoretical foundation, outperforms MIPROv2 by 10%+
- [Dropbox DSPy Case Study](https://dropbox.tech/machine-learning/optimizing-dropbox-dash-relevance-judge-with-dspy) -- overfitting failure mode confirmed

### Secondary (MEDIUM confidence)
- [ACL 2025: Joint Tool Optimization](https://github.com/Bingo-W/ToolOptimization) -- cross-tool regression prevention
- [Modular Prompt Optimization (MPO)](https://arxiv.org/abs/2601.04055) -- section-local textual gradients
- [Microsoft: Tool-Space Interference](https://www.microsoft.com/en-us/research/blog/tool-space-interference-in-the-mcp-era-designing-for-agent-compatibility-at-scale/) -- cross-tool interference patterns
- [LLM-as-a-Judge Survey](https://arxiv.org/abs/2411.15594) -- scoring instability, binary vs pointwise

### Tertiary (LOW confidence)
- [Contra DSPy and GEPA -- Benjamin Anderson](https://benanderson.work/blog/contra-dspy-gepa/) -- critique of DSPy for agentic workflows (single source)
- `gepa` standalone package version compatibility with `dspy>=3.0` -- needs validation

---
*Research completed: 2026-04-15*
*Ready for roadmap: yes*
