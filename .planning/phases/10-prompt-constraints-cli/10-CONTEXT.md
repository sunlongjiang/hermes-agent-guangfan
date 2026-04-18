# Phase 10: Prompt Constraints & CLI — Context

## Domain Boundary

约束检查（增长限制 + 角色保持）+ CLI 入口点，串联 Phase 7-9 所有组件为端到端提示词段落优化管道。与 Phase 5 (Tool Constraints & CLI) 完全对称。

## Decisions

### D1: 增长约束 → 复用 ConstraintValidator._check_growth()

**选择**: 复用现有 `ConstraintValidator._check_growth()` 方法，传入 `artifact_type="prompt_section"`。`max_prompt_growth` 已在 `EvolutionConfig` 中定义为 `0.2`（20%）。

### D2: 角色保持检查 → LLM-based PromptRoleChecker

**选择**: 创建 `PromptRoleChecker` 类，用 DSPy ChainOfThought 对比原始段落和进化后段落，判断功能角色是否保持（如 memory_guidance 仍在指导记忆使用）。与 Phase 5 的 `ToolFactualChecker` 对称。

### D3: CLI 入口 → 复用 evolve_tool_descriptions.py 模式

**选择**: 创建 `evolve_prompt_sections.py`，Click CLI，选项包含 `--section`（指定段落）、`--iterations`、`--hermes-repo`、`--dry-run`。编排流程：extract → module → dataset → GEPA → constraints → evaluate → save。

### D4: 约束门禁顺序 → growth + role 在 GEPA 之后、holdout 之前

**选择**: 与 Phase 5 一致，约束检查在 GEPA 优化之后、holdout 评估之前执行。

## Carrying Forward

- **Phase 5**: ToolFactualChecker + evolve_tool_descriptions.py CLI 模式
- **Phase 7**: extract_prompt_sections() + write_back_section()
- **Phase 8**: PromptModule.set_active_section() + get_evolved_sections()
- **Phase 9**: PromptBehavioralMetric + PromptDatasetBuilder

## Canonical Refs

- `evolution/tools/tool_constraints.py` — Phase 5 的 ToolFactualChecker 模式参考
- `evolution/tools/evolve_tool_descriptions.py` — Phase 5 的 CLI 模式参考
- `evolution/core/constraints.py` — ConstraintValidator, ConstraintResult
- `evolution/core/config.py` — EvolutionConfig.max_prompt_growth
- `evolution/prompts/prompt_loader.py` — extract/write-back
- `evolution/prompts/prompt_module.py` — PromptModule
- `evolution/prompts/prompt_metric.py` — PromptBehavioralMetric
- `evolution/prompts/prompt_dataset.py` — PromptDatasetBuilder

## Deferred Ideas

None.
