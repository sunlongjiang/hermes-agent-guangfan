# Phase 4: Tool Dataset & Evaluation - Context

**Gathered:** 2026-04-16
**Status:** Ready for planning

<domain>
## Phase Boundary

构建工具选择的合成数据集和二值评估指标，用于衡量进化后的工具描述是否改善了 agent 的工具选择。包含 confuser 任务（功能重叠的工具对）和跨工具回归检测机制。

覆盖 TOOL-05（二值工具选择指标）、TOOL-06（合成数据集 200-400 条）、TOOL-07（confuser 任务）、TOOL-08（跨工具联合评估，回归 >2% 则拒绝）四个需求。

</domain>

<decisions>
## Implementation Decisions

### 数据集格式
- **D-01:** 新建 `ToolSelectionExample` 专用数据类，包含 task_description, correct_tool, correct_params, difficulty, confuser_tools 等字段。不扩展现有 `EvalExample`，两者并存
- **D-02:** 配套新建 `ToolSelectionDataset` 数据类，提供 train/val/holdout 分割和 JSONL 序列化，和 `EvalDataset` 模式一致

### 数据集生成策略
- **D-03:** 新建 `ToolDatasetBuilder` 专用类，参考 `SyntheticDatasetBuilder` 的模式（DSPy Signature + ChainOfThought + JSONL 分割保存），但用专用 Signature 生成 (task, correct_tool, correct_params) 三元组
- **D-04:** 数据集来源仅用 LLM 合成生成。不需要 SessionDB 或 golden set
- **D-05:** 保存到 `datasets/tools/selection/`，标准 JSONL 分割（train.jsonl / val.jsonl / holdout.jsonl），50/25/25 比例

### Confuser 生成
- **D-06:** confuser 采用工具相似度分析驱动——先用 LLM 分析所有工具描述找出功能重叠的工具对/组，再针对每对生成 5-10 个 confuser 任务，明确标注正确工具和原因
- **D-07:** hard 难度的任务主要由 confuser 组成

### 难度分布与覆盖率
- **D-08:** 难度分布 easy 30% / medium 40% / hard 30%
- **D-09:** 每个工具至少 3 条任务（1 easy + 1 medium + 1 hard/confuser），确保跨工具回归检测有足够样本。50 工具 × 3 = 150 条起步，加上额外 confuser 达到 200-400 总量

### 二值指标
- **D-10:** 精确匹配判断工具选择正确性：`selected_tool.strip().lower() == correct_tool.strip().lower()` → 1 或 0
- **D-11:** correct_params 不纳入 Phase 4 的二值评分，只关注工具选择正确率。数据集中仍记录 correct_params 供未来使用
- **D-12:** 独立 `tool_selection_metric(example, prediction)` 函数，返回 0 或 1，直接作为 GEPA `compile()` 的 metric 参数。和 Phase 1 的 `skill_fitness_metric` 并列

### 跨工具回归检测
- **D-13:** baseline 通过优化前用原始描述在整个评估数据集上跑一遍，记录 per-tool 正确选中率
- **D-14:** 回归阈值为绝对值 2 个百分点（如 baseline 80% → 跌至 78% 以下即触发拒绝）
- **D-15:** 跨工具回归检测作为最终门禁（post-optimization gate），在 holdout 集上执行一次。和 Phase 1 的 constraint validation 模式一致

### Claude's Discretion
- `ToolSelectionExample` 和 `ToolSelectionDataset` 的具体字段命名和辅助方法
- `ToolDatasetBuilder` 内部的 DSPy Signature 设计（字段名、desc 文本）
- 工具相似度分析的具体实现（LLM prompt 设计、相似度阈值）
- 跨工具回归检测函数的具体接口设计和返回格式

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 参考实现
- `evolution/core/dataset_builder.py` — `EvalExample`、`EvalDataset`、`SyntheticDatasetBuilder` 的模式参考。Phase 4 的 `ToolSelectionExample` 和 `ToolDatasetBuilder` 应遵循相同的数据类 + builder 模式
- `evolution/core/fitness.py` — `skill_fitness_metric()` 的 DSPy metric 接口模式。Phase 4 的 `tool_selection_metric()` 应遵循相同的函数签名

### Phase 2/3 产出
- `evolution/tools/tool_loader.py` — `ToolDescription`、`ToolParam` 数据类，`extract_tool_descriptions()` 提取所有工具描述
- `evolution/tools/tool_module.py` — `ToolModule` 类，`forward(task_description)` 返回 `selected_tool`，`get_evolved_descriptions()` 提取进化后描述

### 项目规划文档
- `.planning/REQUIREMENTS.md` — TOOL-05 到 TOOL-08 的需求定义
- `.planning/ROADMAP.md` §Phase 4 — 成功标准

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `evolution/core/dataset_builder.py` — `SyntheticDatasetBuilder` 的 DSPy Signature + ChainOfThought 模式直接参考
- `evolution/core/dataset_builder.py` — `EvalDataset` 的 JSONL 保存/加载和分割逻辑可参考
- `evolution/tools/tool_loader.py` — `extract_tool_descriptions()` 提供所有工具描述数据，直接供 confuser 分析和数据集生成使用
- `evolution/tools/tool_module.py` — `ToolModule.forward()` 是二值指标的评估目标

### Established Patterns
- Dataclass + `to_dict()` / `from_dict()` 序列化（`EvalExample`, `ToolDescription`, `FitnessScore`）
- DSPy Signature 内部类 + ChainOfThought 生成
- Module-level `Console()` + Rich 输出
- JSONL 格式的 train/val/holdout 分割保存

### Integration Points
- `evolution/tools/` 包——新文件 `tool_dataset.py`（数据类 + builder）和 `tool_metric.py`（二值指标 + 回归检测）
- `datasets/tools/selection/` 目录——生成的数据集保存位置
- Phase 5 的 CLI 将调用 Phase 4 的 metric 和数据集构建功能

</code_context>

<specifics>
## Specific Ideas

- `ToolDatasetBuilder` 分两步生成：Step 1 工具相似度分析（输出工具对列表），Step 2 针对每对/每工具生成任务
- confuser_tools 字段记录在 `ToolSelectionExample` 中，标记哪些工具是该任务的"混淆项"
- 跨工具回归检测返回 per-tool 详情（每个工具的 baseline rate vs evolved rate），方便定位哪个工具的描述退化了
- 数据集生成应保证每个工具至少 3 条覆盖，不足的工具要补充生成

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-tool-dataset-evaluation*
*Context gathered: 2026-04-16*
