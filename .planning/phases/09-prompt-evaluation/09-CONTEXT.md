# Phase 9: Prompt Evaluation — Context

## Domain Boundary

行为评估器 + 场景测试集，用于衡量进化后的提示词段落是否让 agent 产生正确行为。为 GEPA 优化循环提供 metric 函数和反馈。

## Decisions

### D1: 场景生成 → LLM 合成

**选择**: 用 LLM 根据段落内容合成场景，复用 Phase 1 的 `SyntheticDatasetBuilder` 模式。

每个场景包含:
- `section_id`: 所属段落
- `user_message`: 模拟用户输入
- `expected_behavior`: 期望 agent 行为描述
- `difficulty`: easy/medium/hard

### D2: 场景分配 → 按重要性加权

**选择**: 按段落重要性和复杂度分配场景数量:

| 段落 | 场景数 | 理由 |
|------|--------|------|
| default_agent_identity | 20 | 核心身份，影响所有交互 |
| memory_guidance | 15 | 记忆策略，判断什么该存什么不该存 |
| skills_guidance | 15 | 技能保存/修补时机判断 |
| platform_hints.* | 20 | 9 个平台，每平台 2-3 个场景 |
| session_search_guidance | 10 | 相对简单，触发条件明确 |

总计: 80 场景，50/25/25 train/val/holdout 拆分。

### D3: 评分维度 → 复用 FitnessScore

**选择**: 复用现有 `FitnessScore` 的三个维度:
- `correctness` (0.5): 行为是否符合场景预期
- `procedure_following` (0.3): 是否遵守段落指导原则
- `conciseness` (0.2): 是否简洁不冗余

复用 `LLMJudge` 的 judge prompt 模式，仅需调整 rubric 描述为行为检测场景。

### D4: GEPA 集成 → 复用 tool_selection_metric 模式

**选择**: 创建 `prompt_behavioral_metric(example, prediction, trace=None) -> float` 函数:
- 返回 0.0-1.0 的 float 分数（DSPy metric 兼容）
- 内部调用 LLMJudge 获取 FitnessScore
- feedback 字段传递给 GEPA 的反思分析

与 `tool_selection_metric` 对称，仅评估维度的 rubric 不同。

## Carrying Forward

- **Phase 1**: SyntheticDatasetBuilder 场景生成模式
- **Phase 1**: FitnessScore + LLMJudge 评分基础设施
- **Phase 4**: tool_selection_metric + ToolSelectionDataset 模式
- **Phase 8**: PromptModule.set_active_section() 支持 per-section 评估

## Canonical Refs

- `evolution/core/fitness.py` — FitnessScore, LLMJudge
- `evolution/core/dataset_builder.py` — SyntheticDatasetBuilder, EvalExample, EvalDataset
- `evolution/tools/tool_metric.py` — tool_selection_metric 模式参考
- `evolution/tools/tool_dataset.py` — ToolSelectionDataset 模式参考
- `evolution/prompts/prompt_module.py` — PromptModule (Phase 8)
- `evolution/prompts/prompt_loader.py` — PromptSection (Phase 7)

## Deferred Ideas

None.
