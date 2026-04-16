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

- [ ] Phase 2: Tool description optimization pipeline
- [ ] Phase 2: ToolDescriptionModule (DSPy module wrapping tool descriptions)
- [ ] Phase 2: Tool selection evaluator (task → correct tool scoring)
- [ ] Phase 2: Cross-tool evaluation (optimize all descriptions jointly)
- [ ] Phase 2: Tool description constraint validation (500 char limit, factual accuracy)
- [ ] Phase 2: evolve_tool_descriptions CLI entry point
- [ ] Phase 3: System prompt section optimization pipeline
- [ ] Phase 3: PromptSectionModule (DSPy module wrapping prompt sections)
- [ ] Phase 3: Behavioral evaluator (test prompt section effectiveness)
- [ ] Phase 3: Per-section and joint optimization
- [ ] Phase 3: evolve_prompt_section CLI entry point
- [ ] Tests for Phase 2 and Phase 3 modules

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
| 独立管道优先 | 不依赖 hermes-agent 运行时，降低集成复杂度 | — Pending |
| 复用 core/ 基础设施 | SyntheticDatasetBuilder、LLMJudge、ConstraintValidator 已经足够通用 | — Pending |
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
