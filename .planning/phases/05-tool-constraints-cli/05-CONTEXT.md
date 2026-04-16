# Phase 5: Tool Constraints & CLI - Context

**Gathered:** 2026-04-16
**Status:** Ready for planning

<domain>
## Phase Boundary

为进化后的工具描述添加事实准确性验证和大小约束门禁，并构建完整的 `evolve_tool_descriptions` CLI 入口点，串联 Phase 2-4 的所有组件为端到端可运行的优化管道。

覆盖 TOOL-09（事实准确性检查）、TOOL-10（大小约束强制执行）、TOOL-11（CLI 入口点）三个需求。

</domain>

<decisions>
## Implementation Decisions

### 事实准确性检查（TOOL-09）
- **D-01:** 验证策略为"原始 vs 进化对比"——将原始描述和进化后描述一起传给 LLM，判断进化后的描述是否声称了原始描述中不存在的能力。不对照工具源代码。
- **D-02:** 输出为 Pass/Fail 二值——声称了虚假能力则 fail，否则 pass。返回 `ConstraintResult` 数据类，和现有约束模式一致。
- **D-03:** 检查器放在独立文件 `evolution/tools/tool_constraints.py`，新建 `ToolFactualChecker` 类。和 `tool_loader.py`、`tool_module.py` 并列。

### CLI 编排流程（TOOL-11）
- **D-04:** 单文件组织——`evolution/tools/evolve_tool_descriptions.py` 包含 Click CLI 入口 `main()` 和业务逻辑 `evolve()` 函数，和 `evolve_skill.py` 模式完全一致。
- **D-05:** 端到端管道复制 `evolve_skill.py` 的流程：loader → module → dataset(synthetic/load) → GEPA optimize → constraint validate → holdout evaluate → save。
- **D-06:** CLI 参数为标准四参数：`--iterations`, `--eval-source`(synthetic/load), `--hermes-repo`, `--dry-run`。保持简洁，不引入额外参数。
- **D-07:** 可通过 `python -m evolution.tools.evolve_tool_descriptions` 运行。

### 约束集成策略（TOOL-10 + TOOL-09 集成）
- **D-08:** 组合复用——现有 `ConstraintValidator` 的 `_check_size`（已支持 `tool_description`/`param_description` 类型）+ `_check_growth` + `_check_non_empty` 直接复用，加上新建的 `ToolFactualChecker`。CLI 中顺序调用两者。
- **D-09:** 执行时机为优化后门禁——GEPA 优化完成后、holdout 评估之前执行约束验证。和 Phase 1 的 post-optimization constraint gate 一致。
- **D-10:** 跨工具回归检测（Phase 4 的 `CrossToolRegressionChecker`）也在此阶段作为门禁执行。

### 输出与保存格式
- **D-11:** 进化结果保存到 `output/tools/` 目录，不直接修改 hermes-agent 文件。和 PROJECT.md "输出到 output/ 目录即可" 一致。
- **D-12:** 输出内容包含三部分：进化后的描述文本、评估指标 JSON（baseline vs evolved scores）、before/after diff 文本。
- **D-13:** dry-run 模式行为为设置验证 + 预览——验证能找到 hermes-agent、能加载工具、能生成/加载数据集，展示将要优化的工具列表，不运行 GEPA。

### Claude's Discretion
- `ToolFactualChecker` 内部的 DSPy Signature 设计（字段名、判断 prompt 措辞）
- LLM 输出的 JSON 解析策略（复用 fitness.py 的 `_parse_scoring_json` 模式）
- diff 输出的具体格式（unified diff 或自定义文本对比）
- 输出目录的子结构（按时间戳、按运行 ID 等组织方式）

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase 1 参考实现
- `evolution/skills/evolve_skill.py` — evolve() 函数和 Click CLI 入口点的完整参考。Phase 5 的 `evolve_tool_descriptions.py` 应遵循相同的编排流程和 CLI 模式
- `evolution/core/constraints.py` — `ConstraintValidator` 类，已有 `_check_size`（支持 `tool_description`/`param_description`）、`_check_growth`、`_check_non_empty`、`_check_skill_structure`、`run_test_suite` 方法
- `evolution/core/fitness.py` — `LLMJudge` 类的 DSPy Signature + JSON 解析模式，作为 `ToolFactualChecker` 的参考
- `evolution/core/config.py` — `EvolutionConfig` 数据类，已包含 `max_tool_desc_size=500`、`max_param_desc_size=200`

### Phase 2-4 产出
- `evolution/tools/tool_loader.py` — `ToolDescription`、`ToolParam`、`extract_tool_descriptions()`、`discover_tool_files()`、`write_back_description()`
- `evolution/tools/tool_module.py` — `ToolModule(dspy.Module)`，`forward()` 方法，`get_evolved_descriptions()` 方法
- `evolution/tools/tool_dataset.py` — `ToolSelectionExample`、`ToolSelectionDataset`、`ToolDatasetBuilder`
- `evolution/tools/tool_metric.py` — `tool_selection_metric()`、`CrossToolRegressionChecker`

### 项目规划文档
- `.planning/REQUIREMENTS.md` — TOOL-09、TOOL-10、TOOL-11 的需求定义
- `.planning/ROADMAP.md` §Phase 5 — 成功标准

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ConstraintValidator._check_size()` — 已支持 `artifact_type="tool_description"` 和 `"param_description"`，size limit 从 `EvolutionConfig` 读取，直接复用
- `ConstraintValidator._check_growth()` — 通用增长率检查，适用于任何文本制品
- `evolve_skill.py` — 完整的 CLI + evolve() 编排流程，Phase 5 的 CLI 可直接参照结构
- `evolution/core/fitness.py` `LLMJudge` — DSPy Signature + ChainOfThought + JSON 解析的模式，factual checker 参照此设计
- Phase 4 的 `CrossToolRegressionChecker` — 跨工具回归检测，作为 CLI 管道中的额外门禁

### Established Patterns
- Click CLI: `@click.command()` + `@click.option()` + `main()` / `evolve()` 分离
- DSPy Signature 内部类 + ChainOfThought 做 LLM 调用
- `ConstraintResult` dataclass 表示 pass/fail 结果
- Module-level `Console()` + Rich 输出（Panel, Table, Progress）

### Integration Points
- `evolution/tools/` 包——新文件 `tool_constraints.py`（factual checker）和 `evolve_tool_descriptions.py`（CLI）
- `output/tools/` 目录——进化结果的输出位置
- 所有 Phase 2-4 组件在 CLI 中被串联调用

</code_context>

<specifics>
## Specific Ideas

- `ToolFactualChecker` 接收 (original_description, evolved_description)，使用 DSPy ChainOfThought 判断是否新增了虚假能力声明
- CLI 的 evolve() 函数编排顺序：1) 发现工具文件 2) 提取描述 3) 构建 ToolModule 4) 生成/加载数据集 5) GEPA 优化 6) 约束验证（size + factual + regression） 7) holdout 评估 8) 保存结果
- dry-run 在步骤 4 之后停止，打印工具列表和数据集统计信息
- TOOL-10 的 size constraint 已在 `ConstraintValidator._check_size()` 中实现，Phase 5 只需在 CLI 中正确调用即可

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-tool-constraints-cli*
*Context gathered: 2026-04-16*
