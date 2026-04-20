# Hermes Agent Self-Evolution: Phase 2 & 3

## What This Is

在已实现 Phase 1（技能进化）的基础上，实现 Phase 2（工具描述优化）和 Phase 3（系统提示词进化）。复用核心基础设施（dataset_builder、fitness、constraints），为每个 Phase 构建独立可用的优化管道。目标是让 GEPA 能优化 hermes-agent 的工具描述和系统提示词组件。

## Core Value

让 GEPA 优化循环能覆盖工具描述和系统提示词——不仅是技能文件——使 hermes-agent 的核心文本制品都能被系统性地自动改进。

## Requirements

### Validated

- ✓ Skill evolution pipeline — Phase 1 已实现
- ✓ DSPy module wrapper pattern (SkillModule) — existing
- ✓ Synthetic dataset builder — existing
- ✓ Session importers (Claude Code, Copilot, Hermes) — existing
- ✓ LLM-as-judge fitness scoring — existing
- ✓ Constraint validation (size, growth, structure) — existing
- ✓ CLI with Click + Rich console output — existing
- ✓ Tool loading & discovery (ToolDescription, extract_tool_descriptions) — Validated in Phase 2-3
- ✓ ToolModule (DSPy module for tool selection) — Validated in Phase 3
- ✓ Tool selection dataset (ToolSelectionExample, ToolSelectionDataset, ToolDatasetBuilder) — Validated in Phase 4
- ✓ Binary tool selection metric (tool_selection_metric) — Validated in Phase 4
- ✓ Cross-tool regression checker (CrossToolRegressionChecker) — Validated in Phase 4

### Active

- [ ] v2: Per-parameter description optimization (TOOL-V2-02)
- [ ] v2: SessionDB mining for tool/prompt training data (TOOL-V2-01, PMPT-V2-04)
- [ ] v2: Think-augmented tool selection (TOOL-V2-03)
- [ ] v2: Joint section optimization (PMPT-V2-01)
- [ ] v2: Personality drift detection (PMPT-V2-02)
- [ ] v2: Darwinian code evolution (V2-CODE-01)
- [ ] v2: Continuous evolution loop (V2-LOOP-01)

### Validated (v1 Complete)

- ✓ Skill evolution pipeline — Phase 1
- ✓ DSPy module wrapper pattern (SkillModule) — Phase 1
- ✓ Synthetic dataset builder — Phase 1
- ✓ Session importers (Claude Code, Copilot, Hermes) — Phase 1
- ✓ LLM-as-judge fitness scoring — Phase 1
- ✓ Constraint validation (size, growth, structure) — Phase 1
- ✓ CLI with Click + Rich console output — Phase 1
- ✓ Tool loading & discovery (ToolDescription, extract_tool_descriptions) — Phase 2
- ✓ ToolModule (DSPy module for tool selection) — Phase 3
- ✓ Tool selection dataset (ToolSelectionExample, ToolDatasetBuilder) — Phase 4
- ✓ Binary tool selection metric (tool_selection_metric) — Phase 4
- ✓ Cross-tool regression checker (CrossToolRegressionChecker) — Phase 4
- ✓ ToolFactualChecker (factual accuracy constraint) — Phase 5
- ✓ evolve_tool_descriptions CLI entry point — Phase 5
- ✓ Prompt loading (extract_prompt_sections, write_back_section) — Phase 7
- ✓ PromptModule (per-section DSPy optimization) — Phase 8
- ✓ Prompt behavioral dataset (PromptDatasetBuilder, 80 scenarios) — Phase 9
- ✓ Prompt behavioral metric (PromptBehavioralMetric) — Phase 9
- ✓ PromptRoleChecker (role preservation constraint) — Phase 10
- ✓ evolve_prompt_sections CLI entry point — Phase 10

### Out of Scope

- hermes-agent batch_runner integration — 做独立管道，不依赖 hermes-agent 的运行时
- TBLite/YC-Bench benchmark gating — 基准测试作为可选项，不阻塞核心功能
- Phase 4 (Code evolution via Darwinian Evolver) — 不在本次范围
- Phase 5 (Continuous improvement loop) — 不在本次范围
- Auto PR creation — 输出到 output/ 目录即可

## Context

- 项目是独立的优化管道，对 hermes-agent 只做读取操作
- Phase 1 建立的模式：Module wrapper → Dataset → GEPA optimize → Constraint validate → Holdout evaluate → Save output
- PLAN.md 中对 Phase 2 和 Phase 3 有非常详细的规划，包括具体的数据源、评估指标、约束条件
- 核心依赖：DSPy>=3.0, Click, Rich

## Constraints

- **Architecture**: 严格遵循 Phase 1 的代码模式和目录结构
- **Dependency**: 不引入新的外部依赖，复用现有 DSPy/Click/Rich 栈
- **hermes-agent**: 只读访问，通过 HERMES_AGENT_REPO 环境变量定位
- **Size**: 工具描述 ≤500 chars，参数描述 ≤200 chars，提示词段 ≤ 基线 +20%

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 独立管道优先 | 不依赖 hermes-agent 运行时，降低集成复杂度 | ✓ Validated |
| 复用 core/ 基础设施 | SyntheticDatasetBuilder、LLMJudge、ConstraintValidator 已经足够通用 | ✓ Validated |
| 遵循 PLAN.md 的 Phase 2/3 详细规划 | 规划已经非常详尽，包含具体实现方案 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-16 after Phase 4 completion*
