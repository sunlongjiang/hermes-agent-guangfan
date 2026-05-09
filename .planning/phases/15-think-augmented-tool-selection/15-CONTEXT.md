# Phase 15: Think-Augmented Tool Selection - Context

**Gathered:** 2026-05-09
**Status:** Ready for planning

<domain>
## Phase Boundary

在 `evolution.tools.ToolModule` 中加入可选的「推理前置」Predict（ChainOfThought-like），让 GEPA 能优化 reasoning 模板文本，并通过独立 CLI 以 think-off / think-on A/B 方式评估该步骤在 **ambiguous（多合法候选）** 任务上的净收益——不回归全集、不击穿延迟。

**In scope:**
- `ToolModule` 新增可切换的 reasoner Predict（`enable_reasoning=True` 时构造），并将 `ToolReasoningSignature` 产出的 `reasoning` 作为 selector 的附加 InputField。
- 新 CLI `evolution/tools/evolve_tool_reasoning.py` 与新门控 `evolution/tools/think_metrics.py`（含 `ThinkABGate`）。
- 复用 Phase 13 的 `V1BaselineGate` 做全集不回归检查，叠加 ThinkABGate 做 ambiguous +3pp 提升与 p95 延迟预算检查。
- `ToolSelectionExample.confuser_tools` 字段已有——以 `len(confuser_tools) >= 2`（即含 correct 本身 ≥ 3 合法候选）派生 ambiguous 子集。

**Out of scope:**
- 修改 tool 参数描述或顶层工具描述文本（Phase 5/13/17 负责）。
- 训练/运行时 hybrid 路由（用运行时信号决定是否 think）。
- 写回 hermes-agent 仓库（Phase 22）。
- 多 reasoner/per-tool reasoner 结构（本阶段仅单全局 reasoner）。

</domain>

<decisions>
## Implementation Decisions

### Reasoning 模块结构
- **D-01:** Reasoning 通过独立 `dspy.Predict(ToolReasoningSignature)` 暴露给 GEPA，其 `instructions` 即优化参数；selector Predict 独立保留，接收原始 `tools` + 新增 `reasoning` InputField。拒绝把 reasoning 塞进 selector 的 CoT。
- **D-02:** `ToolReasoningSignature`: 输入 `(task_description, available_tools)` → 输出 `reasoning`。selector 仍然保留完整 tools 列表，不走「reasoner 输出 candidates」捷径（避免把筛选责任错位到 reasoner，见 Pitfall 4）。
- **D-03:** Reasoning Predict 是**全局单实例**（所有 tool 共用一条 reasoning 模板）。不做 per-tool reasoner；per-tool 粒度成本/收益不明确，deferred。
- **D-04:** 200-token cap 双保险：传给 reasoner 的 `dspy.LM` 实例使用 `max_tokens=200` 硬截；同时在 signature docstring / instructions 里明确提示简短。不引入 post-eval Checker。

### A/B 路由策略
- **D-05:** 采用 **opt-in flag**：`ToolModule(enable_reasoning=bool)` constructor 二选一、静态分叉（`self.reasoner = None if not enable_reasoning else dspy.Predict(...)`）。不做 runtime mutator，不做 always-think。
- **D-06:** A/B 双边固定为 **think-off (no reasoning) baseline vs think-on evolved**——对照必须是「不加 reasoning 的原 selector」而非「think-on default」，这样才能归因于 reasoning 本身是否有贡献。
- **D-07:** enable_reasoning 参数在 `__init__` 决定，构造后**不可变**；两条 pipeline 分别构建两个 ToolModule 实例（`baseline_module=ToolModule(..., enable_reasoning=False)` 与 `evolved_module=ToolModule(..., enable_reasoning=True)`）。
- **D-08:** latency / reasoning-token 采样 + 三重门判决放在独立模块 `evolution/tools/think_metrics.py` 内的 `ThinkABGate` 类，**不污染** `fitness.py` / `tool_metric.py`；metric 继续做准确率打分，gate 做 PASS/FAIL 决策。

### CLI 入口形态
- **D-09:** 新建独立 CLI `evolution/tools/evolve_tool_reasoning.py`，命令 `python -m evolution.tools.evolve_tool_reasoning`。继承 `evolve_tool_params.py` 的流水线骨架（config/LM/GEPA/CostTracker），但独立拥有 A/B 逻辑与输出目录。不在 P13 CLI 上加 `--enable-reasoning` flag（避免双门交叉污染）。
- **D-10:** 双基线门并行跑：
  - `V1BaselineGate`：think-off evolved vs Phase 5 v1 baseline（全集 holdout 不回归 -2pp）；
  - `ThinkABGate`：think-on evolved vs think-off evolved（ambiguous +3pp + 全集 -2pp + latency p95 ≤ budget）。
  - 任一门 FAILED 即 run 失败并落到 `FAILED_<ts>/`。
- **D-11:** 输出到独立目录 `output/tools_reasoning/<ts>/`，包含：
  - `metrics.json`（含 `think_on_score`, `think_off_score`, `v1_score`, `ambiguous_think_on`, `ambiguous_think_off`, `reasoning_token_stats` {p50,p95,mean}, `latency_stats` {p50,p95,mean}, 两道门的 pass/delta/tolerance）
  - `reasoning_prompt.txt`（进化后的 reasoning instructions）
  - `diff.txt`（baseline reasoning instructions → evolved instructions）
  - `ab_comparison.json`（逐例 think_off/think_on 预测 + 正确答案，方便错例分析）
- **D-12:** CLI flags — 新增 4 个：`--reasoning-tokens-cap`（默认 200）、`--ab-tolerance-pp`（默认 2.0）、`--latency-budget-sec`（默认 5.0）、`--ambiguous-only`（bool，限定只评估 ambiguous 子集）；复用 Phase 13 通用 flags：`--eval-source`、`--tools`、`--dry-run`、`--max-cost-usd`、`--baseline-run`、`--reflection-model`。

### A/B 验收门 + ambiguous 子集定义
- **D-13:** ambiguous 子集定义 = `len(example.confuser_tools) >= 2`（即 correct_tool 之外还有 ≥2 个合法候选 → 共 ≥3 合法候选）。该字段在 `ToolSelectionExample` 中已存在，由 `SyntheticToolDatasetBuilder` 的 confuser-pair 生成步骤与 Phase 14 sessiondb 矿工填入——不引入新的 `ambiguous: bool` 字段，不跑额外 LLM judge pass。
- **D-14:** `ThinkABGate.check()` 三重 AND（全部满足才 PASS）：
  1. **全集不回归**：think-on holdout_score ≥ think-off holdout_score - `full_regression_tolerance_pp/100`（默认 tolerance 2pp）；
  2. **ambiguous 净提升**：ambiguous_subset_score(think-on) - ambiguous_subset_score(think-off) ≥ `ambiguous_improvement_pp/100`（默认 +3pp 绝对提升）；
  3. **延迟预算**：think-on 单次调用 latency_p95 ≤ `latency_p95_budget_sec`（默认 5.0s）。
- **D-15:** 三重门默认阈值硬编码在 `think_metrics.py` 模块级常量：`DEFAULT_FULL_REGRESSION_TOLERANCE_PP=2.0`、`DEFAULT_AMBIGUOUS_IMPROVEMENT_PP=3.0`、`DEFAULT_LATENCY_P95_BUDGET_SEC=5.0`。CLI flag 可覆盖这三个。EvolutionConfig 不扩。
- **D-16:** 小样本保护：ambiguous 子集在 holdout 中 `< 5` 例时，`ThinkABGate` **skip 第 2 重门**（ambiguous +3pp 不检查），metrics.json 写入 `ambiguous_gate_skipped: true` + `ambiguous_sample_size: N`；日志输出「样本过小跳过 ambiguous 门」。只要全集回归门和 latency 门过，run 仍 PASS。
- **D-17:** latency & reasoning-token 采样：在 ToolModule.forward 或封装的 benchmark harness 中，对 think-on holdout 全集逐例计时与 token usage 记录，统计 p50/p95/mean 写入 `metrics.json`（Pitfall 4 对齐——reasoning 不允许偷偷地把 p95 延迟炸到可用性以下）。

### Claude's Discretion
- Wave 结构与具体测试分片（RED→GREEN、哪个 wave 先写 ThinkABGate 单测 vs `ToolReasoningSignature` 骨架）由 planner 决定。
- `ab_comparison.json` 具体字段名（如使用 `task_id` / `selected_off` / `selected_on` / `correct_tool`）细化由 planner 在 PLAN 里 pin 死。
- 是否在 `think_metrics.py` 里同时暴露函数式 API (`check_think_ab_gate(...)`) 与类式 API（`ThinkABGate.check(...)`）——参考 `v1_baseline_gate.py` 的双模式惯例。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase goal & roadmap
- `.planning/ROADMAP.md` §Phase 15 — 目标、依赖（Phase 13）、Requirements（TOOL-V2-03）、3 条 Success Criteria。

### 先验经验 / 风险文档
- `.planning/research/PITFALLS.md` §Pitfall 4 — 推理步骤会 **增加延迟 / 偏航 / 把 selector 变成橡皮图章**；A/B 门必须抓 latency p95 和 ambiguous 子集净收益。
- `.planning/codebase/CONCERNS.md` — 现有 constraint 与结构性关切，planner 须核对与本 phase 的冲突项。

### 上游 Phase 决策
- `.planning/phases/13-per-parameter-description-optimization/13-CONTEXT.md` — ToolModule per-param sub-Module 结构，`_frozen_tool_desc` 隔离；Phase 15 的 reasoner 必须兼容此结构（不重写 selector 输出字段）。
- `.planning/phases/14-sessiondb-mining-for-tools/14-CONTEXT.md` — sessiondb 产出的真实 ambiguous 样本如何流入 `ToolSelectionExample.confuser_tools`。

### 代码基座
- `evolution/tools/tool_module.py` — ToolModule 现有构造函数与 `forward()`；本 phase 在此引入 `enable_reasoning` 构造开关与 `self.reasoner`。
- `evolution/tools/evolve_tool_params.py` — Phase 13 CLI 流水线模板，新 CLI 复用其 config/LM/GEPA/CostTracker 骨架。
- `evolution/tools/v1_baseline_gate.py` — `V1BaselineGate` 结构；`ThinkABGate` 参考其 `_compute_baseline_gate_metrics` / `.check()` 返回 `ConstraintResult` 的形态惯例。
- `evolution/tools/tool_metric.py` — `joint_tool_param_metric` / `CrossToolRegressionChecker` / `persist_per_tool_rates`，本 phase 的新 metric（think-on 与 think-off 并行评估）基于此封装。
- `evolution/tools/tool_dataset.py` — `ToolSelectionExample.confuser_tools` 字段与 `GenerateConfuserTasks` signature；ambiguous 子集完全基于 confuser_tools 长度派生，**不新增字段**。
- `evolution/core/constraints.py` — `ConstraintResult` dataclass；`ThinkABGate.check()` 必须返回该类型以保持 constraint chain 接口一致。
- `evolution/core/cost_tracker.py` — `CostTracker` / `CostBudgetExceeded`；新 CLI 必须在 CostTracker 内做 GEPA compile，可能因 reasoning token 叠加触发 cost 截断。

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ToolModule.__init__(tool_descriptions, ...)`：已有 per-param sub-Module 结构；添加 `enable_reasoning: bool = False` 构造参数，在 True 时构造 `self.reasoner = dspy.Predict(ToolReasoningSignature)`，`max_tokens=200` 限定在 reasoner 使用的 LM config 上。
- `evolve_tool_params.py` 16 步流水线骨架（config load → tool discover → baseline module → dry-run → dataset → LM configure → GEPA setup → GEPA compile → 抽取 → constraint chain → holdout eval → regression → V1 gate → 写盘）——新 CLI 结构等价，只替换第 3/7/10/12-14 步以加入 think-on/think-off 并行 + ThinkABGate。
- `V1BaselineGate` + `_compute_baseline_gate_metrics`：返回 dict + `ConstraintResult` 的双 API 模式，`ThinkABGate` 直接套用。
- `SyntheticToolDatasetBuilder.GenerateConfuserTasks`（`tool_dataset.py:195`）已为每条 confuser task 记录 `confuser_tools`——ambiguous 子集筛选 = `[ex for ex in holdout if len(ex.confuser_tools) >= 2]`，零新代码。
- `CostTracker` + `CostBudgetExceeded` → reasoning 多跑一个 Predict 会推高 API cost，`--max-cost-usd` 必须复用。

### Established Patterns
- **Sub-Module 物理隔离**：Phase 13 把 freeze 的 tool 级 description 放到 `_frozen_tool_desc` 避免被 GEPA 触达——Phase 15 反向利用：reasoner 是新增可优化对象，selector 的 per-param Predict 不因 reasoning 存在而改变；GEPA 只应「看见」reasoner instructions 作为新 parameter。
- **Constraint chain fail-closed**：size check → non-empty → factual → Checker → fail-closed；本 phase 的 ThinkABGate 是 constraint chain 的新一环（排在 V1BaselineGate 旁）。
- **FAILED_<ts>/ vs ABORTED_<ts>/**：constraint/regression fail → FAILED_，cost 超限 → ABORTED_；新 CLI 沿用。
- **CLI flag 风格**：Phase 13 用 `@click.option` + 默认值 + 帮助文本；`--dry-run` 早 return 报告；遵循此惯例。
- **Rich console + Table / Panel 输出结果**：新 CLI 沿用 `rich.console` 的高亮 PASS/FAIL 面板。

### Integration Points
- `ToolModule.forward()` 入口：think-off 分支保持现有行为；think-on 分支先调 `self.reasoner(task, tools)` → 得到 `reasoning` → 作为额外 InputField 传给 selector。
- `think_metrics.py` 新模块：导出 `ThinkABGate` 类、`check_think_ab_gate(...)` 函数、`sample_latency_tokens(module, holdout)` 辅助函数。
- 新 CLI → 仍 import `from evolution.tools.v1_baseline_gate import V1BaselineGate`（复用），不做 re-export 污染。
- 输出目录 `output/tools_reasoning/` 是新根目录，与 `output/tools/` 物理隔离避免 Phase 13 结果被混淆。

</code_context>

<specifics>
## Specific Ideas

- 参考 `v1_baseline_gate.py` 的设计：`ThinkABGate` 应同时提供类 API（`.check()`）和函数 API（`check_think_ab_gate(...)`），类 API 封装状态（样本数、子集切分），函数 API 用于轻量调用/测试。
- `ab_comparison.json` 应以逐例形式落盘，便于后续做错例 diff（例如 sessiondb 中哪些 ambiguous task think-on 救回来、哪些 think-on 反而答错）；该数据是 Phase 16 dashboard 的输入。
- reasoning_prompt.txt 是 GEPA 产物的唯一可读快照——命名沿用 `reasoning_prompt.txt` 而非 `evolved_descriptions.json`，因为 Phase 15 不进化 description。

</specifics>

<deferred>
## Deferred Ideas

- **Hybrid 运行时路由**：根据任务复杂度 runtime 决定是否走 think-on（D-05 拒绝 B），留到后续 phase（可能是 Phase 23+）。
- **Per-tool reasoner**（每工具一个独立 reasoner Predict） — D-03 拒绝，等 Phase 16 dashboard 跑起来后看 per-tool 表现再评估。
- **Reasoning 错误分析 skill / CLI**（从 ab_comparison.json 生成错例报告）：归入 Phase 16 regression dashboard 的延展。
- **sessiondb 新增 ambiguous 人工标签** — 不做；D-13 已用 `confuser_tools` 派生足够。
- **ThinkABGate 加 Bayesian 显著性检验** — 当前固定 pp 阈值；样本量大、方差稳定之前不引入统计推断。

### Reviewed Todos (not folded)
None — todo backlog 为空（`cross_reference_todos` 无匹配）。

</deferred>

---

*Phase: 15-think-augmented-tool-selection*
*Context gathered: 2026-05-09*
