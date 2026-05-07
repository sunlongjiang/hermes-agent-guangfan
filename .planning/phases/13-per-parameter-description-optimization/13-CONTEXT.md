# Phase 13: Per-Parameter Description Optimization - Context

**Gathered:** 2026-05-07
**Status:** Ready for planning

<domain>
## Phase Boundary

将 hermes-agent 工具的 **参数级 description 文本** 纳入 GEPA 优化面。~50 个工具 × ~3 avg params ≈ ~150 个独立可优化单元，每个 ≤200 chars。**tool-level description 全程冻结**，只进化 param 描述。沿用 Phase 3 的 `dspy.Predict.signature.instructions` 作参数暴露机制，Phase 2 的 `ToolDescription.params` 作数据载体，Phase 5 的 `_check_size(param_description)` 作尺寸门；新增 joint tool fitness、param_consistency LLM 约束、per-tool 持久化、cost cap、v1 baseline 回归硬门。

覆盖 TOOL-V2-02 需求；不引入新依赖。

</domain>

<decisions>
## Implementation Decisions

### D1 模块结构

- **D-01:** ToolModule 扩展两维字典 `self.param_predictors: dict[str, dict[str, dspy.Predict]]`，键为 `tool_name → param_name → Predict`，Predict.signature.instructions 存 param 描述。GEPA 通过 `named_parameters()` 自动发现每个 param 作为独立可优化单元。
- **D-02:** tool-level description 采用**物理隔离**——不作为 Predict 暴露，仅以字符串存于 `_frozen_tool_desc: dict[str, str]`。forward() 拼装 available_tools 字符串时仍读取此冻结文本，保证 GEPA 无法触碰。成功标准 2 的机制实现。
- **D-03:** 注册**全部** params（含 description 为空的）为 Predict。空描述由 GEPA 从零生成；无 growth baseline 时跳过 growth 检查但仍跑 size/非空/factual/consistency。
- **D-04:** Predict 对象存储走二维字典，命名保留层次（不扁平化为 `param_{tool}_{name}_desc`），避免 tool/param 名冲突，也便于 get_evolved_descriptions() 回溯。
- **D-05:** forward() 新增 `selected_params` 输出字段——selector 一次同时输出 `selected_tool` 和 `selected_params`（JSON 编码），喂 joint metric。现有 ToolSelectionSignature 升级为 `ToolSelectionWithParamsSignature`，保留 task_description/available_tools 输入，新增 selected_params OutputField。

### D2 CLI 形态

- **D-06:** 新建独立入口 `evolution/tools/evolve_tool_params.py`（Click CLI）。evolve_tool_descriptions 保持原貌不变——top-level 与 param-level 完全分管。Joint 优化留给 Phase 17。
- **D-07:** 新入口复用 Phase 5 共用机制：`--iterations` / `--eval-source` / `--hermes-repo` / `--dry-run` / `--model` / `--api-base`。
- **D-08:** 新入口新增四个 flag：`--tools`（逗号分隔工具名子集，默认空=全部）、`--max-cost-usd`（默认 20.0，超 abort 并持久化中间状态）、`--reflection-model`（可覆盖 GEPA reflection_lm，CONCERNS M8）、`--param-group-size`（默认无 cap；设置后当 tool param 数超 --param-group-threshold 时按组分批冻结，留作手动实验）。
- **D-09:** 不向 evolve_tool_descriptions 添加 `--with-params` 级联。两条 pipeline 独立调试。

### D3 Phase 13 Scope 切分

- **D-10:** joint tool fitness 在 Phase 13 落地：metric 按 `0.5 * tool_match + 0.5 * param_match` 计算，两者都为 exact-match（strip+lower 归一化后整体比对）。tool 错 → 整体 0.5\*0=0 + 0.5\*param\_score；param 比较用 dict exact-match（所有 key+value 一致才算 1.0，允许一个 LLM judge 模式 flag 备用但默认关闭）。
- **D-11:** param_consistency LLM 约束在 Phase 13 落地（Pitfall 1 #2）。粒度：**每 tool 一次批检**——把 top-level（frozen）+ 全部 evolved param 描述传给 LLM，要求返回是否存在「缩写不一致 / 必填矛盾 / 语义冲突」，任一冲突 → 整 tool 变体被拒。实现放 `evolution/tools/tool_constraints.py`，新增 `ParamConsistencyChecker` 类，与 `ToolFactualChecker` 结构对齐。
- **D-12:** per-tool rate 持久化在 Phase 13 落地（CONCERNS M3）。metrics.json 新增 `per_tool_baseline_rates: dict[str, float]` 与 `per_tool_evolved_rates: dict[str, float]` 字段；CrossToolRegressionChecker 继续做 pass/fail gate（沿用 2pp 阈值），但计算后把两份 dict 写进 metrics。Phase 16 再做 dashboard 聚合。
- **D-13:** cost cap 在 Phase 13 落地（CONCERNS M8）。EvolutionConfig 新增字段 `max_cost_usd: float = 20.0` 和 `reflection_model: Optional[str] = None`。新建 `evolution/core/cost_tracker.py` 累计 `dspy` 调用返回的 token/usage，每次 GEPA 候选评估后检查；超阈值则 abort 并把已评估候选写入 `output/tools/ABORTED_<timestamp>/`。
- **D-14:** v1 baseline 回归**硬门**在 Phase 13 落地（Pitfall 1 #5）。evolve_tool_params 在进化前强制要求 baseline 分数：默认读取 hermes-agent 原始文件构造的 `ToolModule` + 现有 holdout；可选 `--baseline-run <output-dir>` 指向历史 Phase 5 output，读取 metrics.json 的 evolved_score 作为 v1 基线。判定：per-param evolved holdout < baseline holdout − 0.02（2pp 容差）则 FAIL，写 FAILED_<timestamp>/ 不部署。
- **D-15:** **不**强制 param-group cap 默认行为——D-08 的 --param-group-size 仅作可选 knob。主要靠 D-13 的 cost cap + GEPA 内置 max_metric_calls 双重约束。Rationale：cap 的 Pitfall 1 #3 主要针对无成本上限场景；有 D-13 时过度 cap 会压缩探索空间。

### D4 评估数据与指标

- **D-16:** 数据集**完全复用** Phase 4 产物 `datasets/tools/{train,val,holdout}.jsonl`（含 correct_params 字段），不新建 ToolParamDatasetBuilder 也不追加 param-focused 场景。Rationale：Phase 4 数据集已含 correct_params，新建会引入数据分布偏差。若后续发现 param-focused signal 弱，再到 Phase 14（SessionDB mining）补 param 场景。
- **D-17:** 新 fitness 函数 `joint_tool_param_metric(example, prediction, trace=None, pred_name=None, pred_trace=None) -> float` 放 `evolution/tools/tool_metric.py`。返回 `0.5 * tool_match + 0.5 * param_match` ∈ [0.0, 1.0]。tool_match 复用现有 strip+lower 比较；param_match = 1.0 iff `dict(predicted_params) == dict(correct_params)`（key 与 value 逐对比）否则 0.0。原 tool_selection_metric 不动。
- **D-18:** ToolModule.forward() 升级签名后 holdout 循环同时记录两组 prediction pair：`(correct_tool, selected_tool)`（给 CrossToolRegressionChecker 不变）和 `(correct_params_json, selected_params_json)`（可写入 metrics.json debug）。

### Claude's Discretion

- `ToolSelectionWithParamsSignature` 的字段名与 desc 文本、JSON 编码约定（建议 Python dict 序列化、允许 `{}` 空字典）
- cost_tracker 的 token-per-USD 换算表（从 DSPy/LiteLLM usage 字段取，按默认模型估算）
- ParamConsistencyChecker 的 Signature / system prompt 具体文本
- ABORTED / FAILED 目录结构细节（可参考 Phase 5 FAILED_ 布局）
- evolve_tool_params 的 Rich table 展示细节

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 研究与约束（必读）
- `.planning/research/PITFALLS.md` §Pitfall 1 — Per-Parameter Optimization Destroys Coherence；joint fitness、param_consistency、param-count cap、v1 baseline 硬门的原始论证（Phase 13 scope 切分的决策依据）
- `.planning/codebase/CONCERNS.md` §M3 — Cross-Tool Regression Gate Is Pass/Fail Only；per-tool rate 持久化缺口
- `.planning/codebase/CONCERNS.md` §M8 — Phase 13 Per-Param Fan-Out Multiplies Optimization Cost；max_cost_usd、reflection_model 的原始建议
- `.planning/codebase/CONCERNS.md` §L1 — `_format_paren_concat` Unicode / 内嵌引号边缘用例；Phase 13 param 写回量 3-5× 放大需关注
- `.planning/codebase/CONCERNS.md` §M4 — LLM 输出解析脆弱；param_consistency / joint metric 新增 LLM 调用需考虑

### Phase 13 实现参考
- `evolution/tools/tool_module.py` — 当前 ToolModule 结构（D-01/D-02 在其上扩展）
- `evolution/tools/tool_loader.py` lines 523-578 — `write_back_description(file_path, tool, new_description, param_name=...)` 已支持 param-level 写回；Phase 13 直接调用即可
- `evolution/tools/evolve_tool_descriptions.py` — Phase 5 完整管线，evolve_tool_params 的结构模板（D-06/D-07）
- `evolution/tools/tool_constraints.py` — ToolFactualChecker 类结构；ParamConsistencyChecker 对齐此模式（D-11）
- `evolution/tools/tool_metric.py` lines 18-45 — tool_selection_metric 签名约定；joint_tool_param_metric 沿用（D-17）
- `evolution/tools/tool_metric.py` lines 72-187 — CrossToolRegressionChecker；D-12 对其扩展
- `evolution/tools/tool_dataset.py` lines 40-90 — ToolSelectionExample 含 correct_params（D-16 复用）
- `evolution/core/constraints.py` lines 95-110 — `_check_size("param_description")` 已存在，sizing gate 重复使用
- `evolution/core/config.py` lines 11-65 — EvolutionConfig 扩展点（D-13 新增 max_cost_usd、reflection_model）

### 项目规划文档
- `.planning/REQUIREMENTS.md` §TOOL-V2-02 — 需求定义
- `.planning/ROADMAP.md` §Phase 13 — 成功标准（3 条）
- `.planning/phases/03-tool-module/03-CONTEXT.md` — Phase 3 D-04/D-06 奠定的 param 暴露机制与 schema 冻结设计
- `.planning/phases/05-tool-constraints-cli/05-CONTEXT.md`（如存在）— Phase 5 约束与 CLI 结构参考
- `.planning/PROJECT.md` §Constraints — 尺寸 / 依赖 / 只读约束

### 外部框架
- DSPy 3.x `dspy.GEPA` — reflection_lm 参数、max_metric_calls 语义；per-tool cost 特性（D-13）
- DSPy `dspy.Predict.signature.instructions` — GEPA 可变参数机制（Phase 3 已验证）
- DSPy `Prediction` 对象 usage 字段 — cost_tracker 读数来源

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ToolDescription.params: list[ToolParam]` 与 `ToolParam.description` 字段（`tool_loader.py`）——D-01 的数据源
- `write_back_description(..., param_name="foo")`（`tool_loader.py` lines 523-578）——param-level 写回已 ready
- `ConstraintValidator._check_size(text, "param_description")`（`constraints.py` lines 95-110）——尺寸门复用
- `ToolFactualChecker`（`tool_constraints.py`）——ParamConsistencyChecker 类结构模板
- `CrossToolRegressionChecker.compute_per_tool_rates`（`tool_metric.py` lines 83-110）——D-12 基础

### Established Patterns
- DSPy Module 结构：inner Signature + Predict/ChainOfThought + forward() with dspy.Prediction 输出（Phase 1/3 统一）
- GEPA→MIPROv2 回退模式（`evolve_tool_descriptions.py` lines 184-206）——evolve_tool_params 沿用
- FAILED_ / ABORTED_ 输出目录约定（Phase 5 FAILED_<timestamp>/）——D-13 扩展
- Click CLI + Rich console + metrics.json 三件套——D-06 沿用
- Config 层 layered merge（evolution.yaml < env < CLI override）——D-13 新字段落地

### Integration Points
- evolve_tool_params → ToolModule（扩展后）→ GEPA → joint metric → param_consistency + size + factual → CrossToolRegressionChecker（扩展）→ v1 baseline 硬门 → write_back per param
- param_consistency 插在 size/factual 之后、CrossToolRegressionChecker 之前
- cost_tracker 贯穿 dspy 调用链路；GEPA 候选评估完成后逐次 check
- v1 baseline 硬门放在 holdout 评估之后、result save 之前

</code_context>

<specifics>
## Specific Ideas

- `ToolSelectionWithParamsSignature` 示例字段：`selected_tool: str` + `selected_params: str`（LLM 返回 JSON 字符串，orchestrator 解析为 dict）
- `joint_tool_param_metric` 实现：`tool_match = 1.0 if selected_tool == correct_tool else 0.0`；解析 `selected_params` 为 dict（try/except JSON），`param_match = 1.0 if parsed == example.correct_params else 0.0`
- `ParamConsistencyChecker` 返回 `list[ConstraintResult]`（每 tool 一条），passed=False 时 message 含冲突描述
- cost_tracker 支持在 CLI 启动时打印当前已累计；abort 时写 `aborted.json` 含 final_cost_usd、evaluated_candidates 数等
- metrics.json 追加字段：`per_tool_baseline_rates`、`per_tool_evolved_rates`、`cost_usd_spent`、`v1_baseline_holdout`（来自 --baseline-run 或即时计算）、`param_consistency_failures: int`
- evolve_tool_params 的 dry-run 应列出：发现的 param 总数、分组计划（若启用 cap）、预估 max cost

</specifics>

<deferred>
## Deferred Ideas

- **Joint optimization (top-level + param 同轮进化)** — 推到 Phase 17（Joint Section Optimization 的 tool 等价），Phase 13 仅 param-only
- **Per-tool distribution dashboard (min/p25/median/p75/max)** — CONCERNS M3 + Pitfall 10 的 p25 gate；Phase 16 落地。Phase 13 只持久化 rates
- **SessionDB-driven param scenario augmentation** — Phase 14 补充 param-focused 数据
- **Think-augmented param selection（reasoning step 输出 params）** — Phase 15
- **写回 dry-run flag / git 干净校验 / deploy_mode 门** — CONCERNS M6；Phase 22 持续进化循环前必须做，Phase 13 不触发 write_back（写 output/ 为主），保持现状
- **JSONL 单行鲁棒加载 / 跳过破损行** — CONCERNS M7；v2-STAB 级别独立 hygiene fix
- **LLM 输出解析强化（typed OutputField / error threshold）** — CONCERNS M4；D-11/D-17 内隐式依赖，但强化留待独立清理
- **`_format_paren_concat` Unicode / nested quote 鲁棒性** — CONCERNS L1；Phase 13 写回量放大时补上

</deferred>

---

*Phase: 13-per-parameter-description-optimization*
*Context gathered: 2026-05-07*
