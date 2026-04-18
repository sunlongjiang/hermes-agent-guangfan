# Requirements: Hermes Agent Self-Evolution Phase 2 & 3

**Defined:** 2026-04-16
**Core Value:** 让 GEPA 优化循环能覆盖工具描述和系统提示词，使 hermes-agent 的核心文本制品都能被系统性地自动改进

## v1 Requirements

Requirements for Phase 2 (tool description optimization) and Phase 3 (system prompt evolution). Each maps to roadmap phases.

### Tool Loading

- [x] **TOOL-01**: Pipeline can extract tool descriptions from hermes-agent's tools/*.py files via regex parsing
- [x] **TOOL-02**: Pipeline can write evolved descriptions back to files preserving schema structure (param names, types, required fields frozen)

### Tool Module

- [ ] **TOOL-03**: All tool descriptions wrapped as a single DSPy-optimizable module for joint optimization
- [ ] **TOOL-04**: Schema structure (param names, types, required) stays frozen — only description text evolves

### Tool Evaluation

- [ ] **TOOL-05**: Binary tool selection metric — given (task, available_tools), score whether agent picks the correct tool (0 or 1)
- [ ] **TOOL-06**: Synthetic dataset builder generates 200-400 (task_description, correct_tool, correct_params) triples with difficulty levels
- [ ] **TOOL-07**: Dataset includes "confuser" tasks where 2+ tools overlap but one is clearly better
- [ ] **TOOL-08**: Cross-tool joint evaluation — fitness function penalizes any individual tool's selection rate regression >2%

### Tool Constraints

- [ ] **TOOL-09**: Factual accuracy preservation — LLM-based check that evolved descriptions don't claim false capabilities
- [ ] **TOOL-10**: Size constraint enforced (≤500 chars per tool description, ≤200 chars per parameter description)

### Tool CLI

- [ ] **TOOL-11**: CLI entry point `python -m evolution.tools.evolve_tool_descriptions` with --iterations, --eval-source, --hermes-repo, --dry-run options

### Prompt Loading

- [ ] **PMPT-01**: Pipeline can extract 5 evolvable sections (DEFAULT_AGENT_IDENTITY, MEMORY_GUIDANCE, SESSION_SEARCH_GUIDANCE, SKILLS_GUIDANCE, PLATFORM_HINTS) from prompt_builder.py via regex
- [ ] **PMPT-02**: Pipeline can write evolved sections back preserving surrounding code structure

### Prompt Module

- [ ] **PMPT-03**: Each prompt section wrapped as DSPy-optimizable module with section text as the parameter
- [ ] **PMPT-04**: Per-section optimization with frozen context from other sections passed through

### Prompt Evaluation

- [ ] **PMPT-05**: Behavioral evaluator — per-section scenario-based testing that checks whether agent exhibits expected behavior
- [ ] **PMPT-06**: Behavioral test suite with 60-80 scenarios across 5 sections (10-20 per section, scaled by section importance)
- [ ] **PMPT-07**: Per-section scoring with structured actionable feedback piped to GEPA's reflective analysis

### Prompt Constraints

- [ ] **PMPT-08**: Growth constraint enforced — evolved section must not exceed baseline by >20%
- [ ] **PMPT-09**: Section role preservation — LLM-based check that evolved text maintains its functional role (memory guidance still guides memory usage, etc.)

### Prompt CLI

- [ ] **PMPT-10**: CLI entry point `python -m evolution.prompts.evolve_prompt_section` with --section, --iterations, --hermes-repo, --dry-run options

### Testing

- [ ] **TEST-01**: Unit tests for tool loader, tool module, tool selection metric, cross-tool evaluation
- [ ] **TEST-02**: Unit tests for prompt loader, prompt module, behavioral evaluator

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Tool Optimization Enhancements

- **TOOL-V2-01**: SessionDB-mined misselection patterns as high-value training data
- **TOOL-V2-02**: Per-parameter description optimization (not just top-level)
- **TOOL-V2-03**: Think-augmented tool selection (reasoning step before selection)
- **TOOL-V2-04**: Per-tool regression guard with individual selection rate tracking dashboard

### Prompt Evolution Enhancements

- **PMPT-V2-01**: Joint section optimization (all 5 sections simultaneously)
- **PMPT-V2-02**: Personality/tone drift detection (automated comparison before/after)
- **PMPT-V2-03**: Benchmark-gated validation (TBLite as hard regression gate)
- **PMPT-V2-04**: SessionDB behavioral pattern mining for targeted test cases

### v2 Stabilization

- [ ] **V2-STAB-01**: Traceability table updated — all v1 phases marked Complete
- [ ] **V2-STAB-02**: Both pipelines pass end-to-end dry-run on fresh clone

### v2 New Capabilities

- [ ] **V2-CODE-01**: Darwinian code evolution — at least one hermes-agent code component evolvable
- [ ] **V2-LOOP-01**: Continuous evolution loop — scheduled optimization with regression gates and PR creation

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| hermes-agent batch_runner integration | 做独立管道，不依赖 hermes-agent 运行时 |
| TBLite/YC-Bench per-iteration gating | 每次 2-6 小时 + $50-200，作为可选最终验证 |
| Real-time hot-swapping | 会破坏 prompt caching，所有改动仅在新会话生效 |
| Auto-merge without human review | 进化的文本是 LLM 生成的，始终需要人工审核 |
| Tool schema structure changes | 冻结 param names/types/required，只进化描述文本 |
| GPU-based fine-tuning | 整个管道仅通过 API 调用运作，不训练模型权重 |
| Phase 4 (Code evolution) | 不在本次范围 |
| Phase 5 (Continuous loop) | 不在本次范围 |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| TOOL-01 | Phase 2 | Complete |
| TOOL-02 | Phase 2 | Complete |
| TOOL-03 | Phase 3 | Pending |
| TOOL-04 | Phase 3 | Pending |
| TOOL-05 | Phase 4 | Pending |
| TOOL-06 | Phase 4 | Pending |
| TOOL-07 | Phase 4 | Pending |
| TOOL-08 | Phase 4 | Pending |
| TOOL-09 | Phase 5 | Pending |
| TOOL-10 | Phase 5 | Pending |
| TOOL-11 | Phase 5 | Pending |
| PMPT-01 | Phase 7 | Pending |
| PMPT-02 | Phase 7 | Pending |
| PMPT-03 | Phase 8 | Pending |
| PMPT-04 | Phase 8 | Pending |
| PMPT-05 | Phase 9 | Pending |
| PMPT-06 | Phase 9 | Pending |
| PMPT-07 | Phase 9 | Pending |
| PMPT-08 | Phase 10 | Pending |
| PMPT-09 | Phase 10 | Pending |
| PMPT-10 | Phase 10 | Pending |
| TEST-01 | Phase 6 | Complete (skipped) |
| TEST-02 | Phase 11 | Complete (skipped) |
| TOOL-V2-01 | Phase 14 | Pending |
| TOOL-V2-02 | Phase 13 | Pending |
| TOOL-V2-03 | Phase 15 | Pending |
| TOOL-V2-04 | Phase 16 | Pending |
| PMPT-V2-01 | Phase 17 | Pending |
| PMPT-V2-02 | Phase 18 | Pending |
| PMPT-V2-03 | Phase 20 | Pending |
| PMPT-V2-04 | Phase 19 | Pending |
| V2-STAB-01 | Phase 12 | Pending |
| V2-STAB-02 | Phase 12 | Pending |
| V2-CODE-01 | Phase 21 | Pending |
| V2-LOOP-01 | Phase 22 | Pending |

**Coverage:**
- v1 requirements: 23 total (all complete)
- v2 requirements: 14 total
- Mapped to phases: 37
- Unmapped: 0

---
*Requirements defined: 2026-04-16*
*Last updated: 2026-04-18 after v2 roadmap creation*
