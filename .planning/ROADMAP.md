# Roadmap: Hermes Agent Self-Evolution Phase 2 & 3

## Overview

Extend GEPA optimization from skill evolution (Phase 1, complete) to tool descriptions (Phases 2-6) and system prompts (Phases 7-11). Tool descriptions come first because they have binary measurable outcomes and validate the GEPA standalone pattern. System prompts follow, leveraging the proven pattern for fuzzier behavioral evaluation. Each phase delivers a testable, independent component that builds toward the full optimization pipeline.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Skill Evolution** - Already implemented (baseline pipeline)
- [ ] **Phase 2: Tool Loading** - Extract and write tool descriptions from hermes-agent
- [ ] **Phase 3: Tool Module** - DSPy-optimizable module wrapping all tool descriptions
- [ ] **Phase 4: Tool Dataset & Evaluation** - Synthetic dataset and binary tool selection metric
- [ ] **Phase 5: Tool Constraints & CLI** - Factual accuracy checks, size limits, and CLI entry point
- [ ] **Phase 6: Tool Pipeline Tests** - Unit tests for all tool description components
- [ ] **Phase 7: Prompt Loading** - Extract and write prompt sections from prompt_builder.py
- [ ] **Phase 8: Prompt Module** - Per-section DSPy-optimizable module with context passthrough
- [ ] **Phase 9: Prompt Evaluation** - Behavioral evaluator and 60-80 scenario test suite
- [ ] **Phase 10: Prompt Constraints & CLI** - Growth limits, role preservation, and CLI entry point
- [ ] **Phase 11: Prompt Pipeline Tests** - Unit tests for all prompt section components

## Phase Details

### Phase 1: Skill Evolution
**Goal**: Baseline GEPA optimization pipeline for skill files (already complete)
**Depends on**: Nothing
**Requirements**: (Phase 1 requirements already validated)
**Success Criteria** (what must be TRUE):
  1. Skill files can be optimized through GEPA pipeline
  2. Core infrastructure (dataset_builder, fitness, constraints) works end-to-end
**Plans**: Complete

### Phase 2: Tool Loading
**Goal**: Pipeline can reliably extract tool descriptions from hermes-agent and write evolved versions back without breaking schema structure
**Depends on**: Phase 1 (reuses core infrastructure)
**Requirements**: TOOL-01, TOOL-02
**Success Criteria** (what must be TRUE):
  1. Running the loader extracts all tool descriptions from hermes-agent's tools/*.py files
  2. Writing evolved descriptions back preserves param names, types, and required fields exactly
  3. Round-trip test passes: extract -> modify description text -> write back -> extract again yields the modification
**Plans:** 2 plans

Plans:
- [x] 02-01-PLAN.md — 数据类定义和工具描述提取（4 种格式 + 集成测试）
- [x] 02-02-PLAN.md — Format-preserving 写回和 round-trip 验证

### Phase 3: Tool Module
**Goal**: All tool descriptions are wrapped as a single GEPA-optimizable unit where only description text evolves
**Depends on**: Phase 2
**Requirements**: TOOL-03, TOOL-04
**Success Criteria** (what must be TRUE):
  1. All tool descriptions are exposed as optimizable parameters in one DSPy/GEPA module
  2. Schema structure (param names, types, required) is frozen and cannot be modified by optimization
  3. Module can receive updated description text and produce valid tool definitions
**Plans:** 1 plan

Plans:
- [x] 03-01-PLAN.md — TDD: ToolModule DSPy 模块（per-tool Predict + selector + schema 冻结 + 测试）

### Phase 4: Tool Dataset & Evaluation
**Goal**: Binary tool selection metric and synthetic dataset enable measuring whether evolved descriptions improve agent tool selection
**Depends on**: Phase 3
**Requirements**: TOOL-05, TOOL-06, TOOL-07, TOOL-08
**Success Criteria** (what must be TRUE):
  1. Given a task and available tools, the metric returns 0 or 1 for correct/incorrect tool selection
  2. Synthetic dataset contains 200-400 (task, correct_tool, correct_params) triples with difficulty levels
  3. Dataset includes confuser tasks where 2+ tools overlap but one is clearly better
  4. Cross-tool evaluation rejects candidates where any single tool's selection rate drops >2%
**Plans:** 2 plans

Plans:
- [x] 04-01-PLAN.md — ToolSelectionExample/Dataset 数据类 + ToolDatasetBuilder 两步合成生成
- [x] 04-02-PLAN.md — tool_selection_metric 二值指标 + CrossToolRegressionChecker 回归检测

### Phase 5: Tool Constraints & CLI
**Goal**: Evolved tool descriptions are validated for factual accuracy and size limits, and the full pipeline is runnable via CLI
**Depends on**: Phase 4
**Requirements**: TOOL-09, TOOL-10, TOOL-11
**Success Criteria** (what must be TRUE):
  1. LLM-based factual accuracy check catches descriptions that claim false capabilities
  2. Size constraints reject descriptions >500 chars and parameter descriptions >200 chars
  3. `python -m evolution.tools.evolve_tool_descriptions` runs end-to-end with --iterations, --eval-source, --hermes-repo, --dry-run options
  4. Dry-run mode shows proposed changes without writing files
**Plans:** 2 plans

Plans:
- [ ] 05-01-PLAN.md — ToolFactualChecker 事实准确性检查器 + size constraint 复用验证
- [ ] 05-02-PLAN.md — evolve_tool_descriptions CLI 端到端管道

### Phase 6: Tool Pipeline Tests
**Goal**: Unit tests verify each tool pipeline component works correctly in isolation and together
**Depends on**: Phase 5
**Requirements**: TEST-01
**Success Criteria** (what must be TRUE):
  1. Tests cover tool loader (extraction and write-back)
  2. Tests cover tool module (parameter freezing, description exposure)
  3. Tests cover tool selection metric (correct scoring for known cases)
  4. Tests cover cross-tool evaluation (regression detection)
  5. All tests pass in CI
**Plans**: TBD

### Phase 7: Prompt Loading
**Goal**: Pipeline can extract the 5 evolvable prompt sections from prompt_builder.py and write evolved versions back
**Depends on**: Phase 2 (parallel development possible, shares loader pattern)
**Requirements**: PMPT-01, PMPT-02
**Success Criteria** (what must be TRUE):
  1. Loader extracts all 5 sections: DEFAULT_AGENT_IDENTITY, MEMORY_GUIDANCE, SESSION_SEARCH_GUIDANCE, SKILLS_GUIDANCE, PLATFORM_HINTS
  2. Writing evolved sections back preserves surrounding Python code structure
  3. Round-trip test passes: extract -> modify section text -> write back -> extract again yields the modification
**Plans:** 1 plan

Plans:
- [ ] 07-01-PLAN.md — PromptSection dataclass, AST extraction, format-preserving write-back, round-trip tests

### Phase 8: Prompt Module
**Goal**: Each prompt section is wrapped as a DSPy-optimizable module with frozen context from other sections
**Depends on**: Phase 7
**Requirements**: PMPT-03, PMPT-04
**Success Criteria** (what must be TRUE):
  1. Each of the 5 prompt sections is exposed as an independently optimizable parameter
  2. When optimizing one section, the other 4 sections are passed through as frozen context
  3. Module supports round-robin optimization (optimize one section at a time across iterations)
**Plans:** 1 plan

Plans:
- [ ] 08-01-PLAN.md — TDD: PromptModule DSPy 模块（per-section Predict + frozen context + round-robin + 测试）

### Phase 9: Prompt Evaluation
**Goal**: Behavioral evaluator with scenario-based tests measures whether evolved prompt sections produce correct agent behavior
**Depends on**: Phase 8
**Requirements**: PMPT-05, PMPT-06, PMPT-07
**Success Criteria** (what must be TRUE):
  1. Behavioral evaluator checks whether agent exhibits expected behavior for each scenario
  2. Test suite contains 60-80 scenarios across 5 sections (10-20 per section, scaled by importance)
  3. Per-section scoring produces structured actionable feedback that GEPA's reflective analysis can consume
**Plans:** 2 plans

Plans:
- [ ] 09-01-PLAN.md — TDD: PromptBehavioralExample/Dataset 数据类 + PromptDatasetBuilder 按重要性加权场景生成
- [ ] 09-02-PLAN.md — TDD: PromptBehavioralMetric callable class（LLMJudge 评分 + 快速启发式 + feedback 传播）

### Phase 10: Prompt Constraints & CLI
**Goal**: Evolved prompt sections are validated for growth limits and role preservation, and the full pipeline is runnable via CLI
**Depends on**: Phase 9
**Requirements**: PMPT-08, PMPT-09, PMPT-10
**Success Criteria** (what must be TRUE):
  1. Growth constraint rejects evolved sections that exceed baseline by >20%
  2. LLM-based role preservation check confirms evolved text maintains its functional role
  3. `python -m evolution.prompts.evolve_prompt_sections` runs end-to-end with --section, --iterations, --hermes-repo, --dry-run options
  4. Dry-run mode shows proposed changes without writing files
**Plans:** 2 plans

Plans:
- [ ] 10-01-PLAN.md — PromptRoleChecker 角色保持检查器 + growth constraint 复用验证
- [ ] 10-02-PLAN.md — evolve_prompt_sections CLI 端到端管道

### Phase 11: Prompt Pipeline Tests
**Goal**: Unit tests verify each prompt pipeline component works correctly in isolation and together
**Depends on**: Phase 10
**Requirements**: TEST-02
**Success Criteria** (what must be TRUE):
  1. Tests cover prompt loader (extraction of all 5 sections and write-back)
  2. Tests cover prompt module (frozen context passthrough, per-section optimization)
  3. Tests cover behavioral evaluator (scoring known-good and known-bad scenarios)
  4. All tests pass in CI
**Plans**: Skipped (TDD satisfied)

---

## Milestone v2.0 — Stabilization, Enhancement & Expansion

**Priority order:** Stabilize v1 → Enhance tools/prompts → New capabilities

### Phase 12: v1 Stabilization
**Goal**: Fix bugs, update traceability, ensure both pipelines run end-to-end reliably
**Depends on**: Phase 10
**Requirements**: V2-STAB-01, V2-STAB-02
**Success Criteria** (what must be TRUE):
  1. REQUIREMENTS.md traceability table reflects all v1 phases as Complete
  2. PROJECT.md validated requirements section updated to match actual state
  3. Both `--dry-run` pipelines succeed on a fresh clone
  4. `python -m pytest tests/ -v` passes 329+ tests with zero failures
**Plans**: TBD

### Phase 13: Per-Parameter Description Optimization
**Goal**: Extend tool description optimization to individual parameter descriptions, not just top-level
**Depends on**: Phase 12
**Requirements**: TOOL-V2-02
**Success Criteria** (what must be TRUE):
  1. ToolModule exposes per-parameter descriptions as independently optimizable parameters
  2. GEPA can mutate individual param descriptions while tool-level description stays frozen
  3. Constraint checks enforce max_param_desc_size (200 chars) per parameter
**Plans**: TBD

### Phase 14: SessionDB Mining for Tools
**Goal**: Mine hermes-agent session transcripts for tool misselection patterns as high-value training data
**Depends on**: Phase 12
**Requirements**: TOOL-V2-01
**Success Criteria** (what must be TRUE):
  1. Importer extracts tool selection ground truth from session transcripts
  2. Misselection patterns weighted higher in training dataset
  3. Integration with existing ToolDatasetBuilder as additional data source
**Plans**: TBD

### Phase 15: Think-Augmented Tool Selection
**Goal**: Add reasoning step before tool selection to improve accuracy on ambiguous tasks
**Depends on**: Phase 13
**Requirements**: TOOL-V2-03
**Success Criteria** (what must be TRUE):
  1. ToolModule supports optional ChainOfThought reasoning before selection
  2. Reasoning step is optimizable by GEPA (prompt text is a parameter)
  3. A/B comparison shows improvement on ambiguous selection scenarios
**Plans**: TBD

### Phase 16: Per-Tool Regression Dashboard
**Goal**: Track individual tool selection rates across optimization runs
**Depends on**: Phase 14
**Requirements**: TOOL-V2-04
**Success Criteria** (what must be TRUE):
  1. Metrics file records per-tool accuracy before and after optimization
  2. Rich console dashboard shows selection rate changes per tool
  3. Regression threshold configurable (default: 2pp drop triggers warning)
**Plans**: TBD

### Phase 17: Joint Section Optimization
**Goal**: Optimize all 5 prompt sections simultaneously instead of round-robin
**Depends on**: Phase 12
**Requirements**: PMPT-V2-01
**Success Criteria** (what must be TRUE):
  1. PromptModule supports all-sections-active mode (all Predicts discoverable)
  2. GEPA can mutate multiple sections in one pass
  3. Joint optimization produces equal or better scores than round-robin on holdout
**Plans**: TBD

### Phase 18: Personality Drift Detection
**Goal**: Detect tone/personality changes between original and evolved prompt sections
**Depends on**: Phase 17
**Requirements**: PMPT-V2-02
**Success Criteria** (what must be TRUE):
  1. DriftDetector compares original vs evolved text on tone, formality, personality dimensions
  2. Constraint gate rejects evolved sections with drift score exceeding threshold
  3. Drift report included in optimization output
**Plans**: TBD

### Phase 19: SessionDB Behavioral Mining for Prompts
**Goal**: Mine session transcripts for behavioral patterns to generate targeted test scenarios
**Depends on**: Phase 12
**Requirements**: PMPT-V2-04
**Success Criteria** (what must be TRUE):
  1. Importer extracts behavioral examples from real sessions (what section guided which behavior)
  2. Mined examples augment synthetic dataset with real-world scenarios
  3. Integration with PromptDatasetBuilder as additional data source
**Plans**: TBD

### Phase 20: Benchmark-Gated Validation
**Goal**: Use TBLite as optional hard regression gate after optimization
**Depends on**: Phase 18
**Requirements**: PMPT-V2-03
**Success Criteria** (what must be TRUE):
  1. Optional `--benchmark` flag triggers TBLite evaluation before accepting evolved sections
  2. Configurable pass threshold (default: no regression on core capabilities)
  3. Benchmark results saved to output metrics
**Plans**: TBD

### Phase 21: Darwinian Code Evolution
**Goal**: Integrate darwinian-evolver for code-level evolution of hermes-agent components
**Depends on**: Phase 16, Phase 20
**Requirements**: V2-CODE-01
**Success Criteria** (what must be TRUE):
  1. darwinian-evolver package integrated and tested
  2. At least one code component (e.g., tool registry) evolvable
  3. Fitness function combines functional tests + code quality metrics
**Plans**: TBD

### Phase 22: Continuous Evolution Loop
**Goal**: Automated pipeline that periodically runs optimization, validates, and creates PRs
**Depends on**: Phase 21
**Requirements**: V2-LOOP-01
**Success Criteria** (what must be TRUE):
  1. Scheduler runs optimization on configurable interval
  2. Results validated against regression gates before PR creation
  3. Human review required before merge (no auto-merge)
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 2 -> 3 -> 4 -> 5 -> 6 -> 7 -> 8 -> 9 -> 10 -> 11

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Skill Evolution | - | Complete | Pre-existing |
| 2. Tool Loading | 2/2 | Complete | - |
| 3. Tool Module | 0/1 | Planned | - |
| 4. Tool Dataset & Evaluation | 0/2 | Planned | - |
| 5. Tool Constraints & CLI | 0/2 | Planned | - |
| 6. Tool Pipeline Tests | 0/TBD | Not started | - |
| 7. Prompt Loading | 0/1 | Planned | - |
| 8. Prompt Module | 0/1 | Planned | - |
| 9. Prompt Evaluation | 0/2 | Planned | - |
| 10. Prompt Constraints & CLI | 0/2 | Planned | - |
| 11. Prompt Pipeline Tests | 0/TBD | Not started | - |
