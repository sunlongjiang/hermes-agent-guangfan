# Phase 13: Per-Parameter Description Optimization — Research

**Researched:** 2026-05-07
**Domain:** DSPy 3.x GEPA optimization scaled to ~150 per-parameter Predict units
**Confidence:** HIGH（核心 API 行为通过本地 DSPy 3.1.3 源码 + 运行时 smoke test 直接验证；litellm.cost_per_token 对项目实际使用的模型全部覆盖已实测；LLM 输出 / 写回脆弱性部分为 CITED）

## Summary

本研究验证 Phase 13 的 18 个锁定决策（D-01~D-18）对应到 DSPy 3.1.3 的实际 API 行为时的可行性。**最重要的一个发现将影响 D-01 实现细节**：`dspy.Module.named_parameters()` 对嵌套 `dict[str, dict[str, Predict]]` 结构**只递归一层**，直接导致 D-01 原提议的两维字典对 GEPA 完全不可见（实测 `named_parameters` 返回 0 条目）。本研究给出两个可行替代（扁平化 key 或每 tool 一个 sub-Module），并强烈推荐 **sub-Module per tool** 方案，因为它同时满足 D-04「命名保留层次」与 GEPA 参数发现。

其余决策都有清晰的实现路径：`litellm.cost_per_token()` 对 `openai/gpt-4.1-mini`、`openrouter/google/gemini-2.5-flash`、`dashscope/qwen-plus` 全部返回有效（prompt_cost, completion_cost）元组；`dspy.settings.configure(track_usage=True)` + `dspy.utils.usage_tracker.track_usage()` 是唯一干净的 LM usage 拦截钩子；GEPA 构造器强制 5-param metric signature 与 `reflection_lm` 存在（未 OK 时 raise TypeError / AssertionError）；DSPy 已内置 `component_selector='round_robin'` / `'all'`，可选择让 ~150 Predict 逐一或并行优化。

**Primary recommendation:** Planner 应将 D-01 修订为 **"每 tool 一个 sub-Module，sub-Module 内部持有 flat `dict[param_name, dspy.Predict]`"**。名称空间变为 `tools['tool_a'].param_predictors['param_x']`，既被 GEPA 发现又保留层次。所有其他决策（cost cap、v1 baseline gate、ParamConsistencyChecker、joint metric）按 CONTEXT.md 原样执行。新的 cost_tracker 模块通过 `track_usage()` 包住整个 GEPA `compile()` 调用 + 评估循环，使用 `litellm.cost_per_token` 做 tokens→USD 换算（带 OpenRouter fallback）。

## User Constraints (from CONTEXT.md)

### Locked Decisions

**D1 模块结构**
- **D-01:** ToolModule 扩展两维字典 `self.param_predictors: dict[str, dict[str, dspy.Predict]]`，键为 `tool_name → param_name → Predict`，Predict.signature.instructions 存 param 描述。GEPA 通过 `named_parameters()` 自动发现每个 param 作为独立可优化单元。
  - **⚠️ 实现修订建议（本研究新增）：** 此字面上的两维字典在 DSPy 3.1.3 下 `named_parameters()` 返回 0 条目（验证见 `## Code Examples` § "Nested Dict Discovery Trap"）。Planner 必须把 D-01 的 **意图**（per-tool × per-param 独立可优化单元 + 层次保留命名）与**数据结构**解耦。推荐实现：每 tool 用一个轻量 sub-`dspy.Module` 包装 flat `dict[str, dspy.Predict]`。此调整**不改变 D-01 的语义承诺**，只换表达容器。
- **D-02:** tool-level description 采用**物理隔离**——不作为 Predict 暴露，仅以字符串存于 `_frozen_tool_desc: dict[str, str]`。forward() 拼装 available_tools 字符串时仍读取此冻结文本，保证 GEPA 无法触碰。成功标准 2 的机制实现。
- **D-03:** 注册**全部** params（含 description 为空的）为 Predict。空描述由 GEPA 从零生成；无 growth baseline 时跳过 growth 检查但仍跑 size/非空/factual/consistency。
- **D-04:** Predict 对象存储走二维字典，命名保留层次（不扁平化为 `param_{tool}_{name}_desc`），避免 tool/param 名冲突，也便于 get_evolved_descriptions() 回溯。
- **D-05:** forward() 新增 `selected_params` 输出字段——selector 一次同时输出 `selected_tool` 和 `selected_params`（JSON 编码），喂 joint metric。现有 ToolSelectionSignature 升级为 `ToolSelectionWithParamsSignature`，保留 task_description/available_tools 输入，新增 selected_params OutputField。

**D2 CLI 形态**
- **D-06:** 新建独立入口 `evolution/tools/evolve_tool_params.py`（Click CLI）。evolve_tool_descriptions 保持原貌不变——top-level 与 param-level 完全分管。Joint 优化留给 Phase 17。
- **D-07:** 新入口复用 Phase 5 共用机制：`--iterations` / `--eval-source` / `--hermes-repo` / `--dry-run` / `--model` / `--api-base`。
- **D-08:** 新入口新增四个 flag：`--tools`、`--max-cost-usd`（默认 20.0）、`--reflection-model`、`--param-group-size`。
- **D-09:** 不向 evolve_tool_descriptions 添加 `--with-params` 级联。

**D3 Phase 13 Scope 切分**
- **D-10:** joint tool fitness：`0.5 * tool_match + 0.5 * param_match`，exact-match。
- **D-11:** ParamConsistencyChecker 在 `evolution/tools/tool_constraints.py`，每 tool 一次批检。
- **D-12:** per_tool_baseline_rates / per_tool_evolved_rates 持久化到 metrics.json。
- **D-13:** `EvolutionConfig.max_cost_usd=20.0` + `reflection_model` + 新 `evolution/core/cost_tracker.py`。
- **D-14:** v1 baseline 回归硬门（2pp 容差）。
- **D-15:** 无默认 param-group cap；依赖 D-13 成本门 + GEPA `max_metric_calls`。
- **D-15a:** GEPA 失败默认 loud raise；`--allow-miprov2-fallback` opt-in；metrics.json `optimizer_used` 字段。

**D4 评估数据与指标**
- **D-16:** 完全复用 `datasets/tools/{train,val,holdout}.jsonl`（162/81/81 = 324 examples，含 correct_params 字段，已实测）。
- **D-17:** 新 `joint_tool_param_metric` 放 `evolution/tools/tool_metric.py`，5-param 签名。
- **D-18:** ToolModule.forward() 升级后 holdout 循环同时记录 `(correct_tool, selected_tool)` 和 `(correct_params_json, selected_params_json)`。

### Claude's Discretion

- `ToolSelectionWithParamsSignature` 的字段名与 desc 文本、JSON 编码约定
- cost_tracker 的 token→USD 换算实现细节
- ParamConsistencyChecker 的 Signature / system prompt 具体文本
- ABORTED / FAILED 目录结构细节
- evolve_tool_params 的 Rich table 展示细节

### Deferred Ideas (OUT OF SCOPE)

- Joint top-level + param 同轮优化（留给 Phase 17）
- Per-tool distribution dashboard（留给 Phase 16）
- SessionDB-driven param 场景增强（Phase 14）
- Think-augmented param 推理（Phase 15）
- write_back dry-run / git clean 校验 / deploy_mode（Phase 22）
- JSONL 单行鲁棒加载（v2-STAB hygiene）
- LLM 输出解析强化（独立清理）
- `_format_paren_concat` Unicode 鲁棒性（见下文 §5 研究建议）

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOOL-V2-02 | Per-parameter description optimization (not just top-level) | 本研究验证 DSPy 3.1.3 下 `named_parameters()` 对每 tool sub-Module 内 flat dict of Predict 能正确发现（~150 路径），GEPA compile() 接受；joint metric 5-param 签名通过构造器断言；max_cost_usd 可通过 `track_usage()` + `litellm.cost_per_token` 实现 abort；v1 baseline 读 `output/tools/<timestamp>/metrics.json.evolved_score`。 |

## Project Constraints (from CLAUDE.md)

| 约束类型 | 内容 | 影响 |
|---------|------|------|
| 响应语言 | Simplified Chinese 叙述 + English 代码标识符 | 本 RESEARCH.md 格式 |
| Python | >=3.10 | `dspy>=3.0.0`（已安装 3.1.3）兼容 |
| 依赖 | 不引入新外部依赖 | cost_tracker 只用 `litellm`（DSPy 传递依赖，已在 venv）、标准库 |
| hermes-agent | READ-ONLY via `HERMES_AGENT_REPO` | Phase 13 不触发 write_back，输出仅入 `output/` |
| 尺寸门 | tool desc ≤500 / **param desc ≤200** / prompt growth ≤20% | `ConstraintValidator._check_size("param_description")` 已存在（`constraints.py:101-102`），直接复用 |
| GSD workflow | 所有文件改动走 /gsd-execute-phase | planner 需生成 PLAN.md，task 列表按 waves 组织 |

## Standard Stack

### Core（全部已存在于 venv，零新增依赖）

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `dspy` | 3.1.3 `[VERIFIED: /Users/slj/项目/hermes-agent-self-evolution/.venv/lib/python3.13/site-packages/dspy]` | 参数发现、GEPA 优化、ChainOfThought | Phase 3/5/12 既有栈；GEPA 的 `reflection_lm`、`max_metric_calls`、`component_selector` 都来自此版 |
| `litellm` | 1.83.8 `[VERIFIED: 实测 import 成功]` | tokens→USD 换算 | DSPy 的 LM 后端传递依赖；`completion_cost` / `cost_per_token` / `model_cost` 内建，对 gpt-4.1-mini、openrouter、dashscope 均有价目 |
| `click` | ≥8.0 `[CITED: pyproject.toml:21]` | CLI | Phase 5 evolve_tool_descriptions 既有模式 |
| `rich` | ≥13.0 `[CITED: pyproject.toml:22]` | 表格 / 进度 | 既有模式，per-tool rate 表格、ABORT 状态展示 |

### Supporting（均已存在）

| 文件路径 | 复用方式 |
|---------|---------|
| `evolution/tools/tool_loader.py:523-578` `write_back_description(param_name=...)` `[VERIFIED: grep 行号确认]` | Phase 13 的 param 写回直接调用（虽然按 Deferred，实际 Phase 13 只写入 `output/`，不调用此函数；但 dry-run 展示 diff 时可复用 `_format_description`）|
| `evolution/tools/tool_constraints.py` `ToolFactualChecker` `[VERIFIED]` | ParamConsistencyChecker 按相同类结构模板（inner Signature + ChainOfThought + `check` + `check_all`）|
| `evolution/tools/tool_metric.py` `CrossToolRegressionChecker.compute_per_tool_rates` `[VERIFIED: lines 83-110]` | D-12 per-tool rate 持久化的计算源头 |
| `evolution/tools/tool_dataset.py` `ToolSelectionExample.correct_params: dict` `[VERIFIED: lines 33-71, holdout.jsonl 实测]` | D-16 直接复用 |
| `evolution/core/constraints.py` `_check_size("param_description")` `[VERIFIED: lines 95-117]` | 200-char 硬门直接复用，无需新增 |
| `evolution/core/config.py` `EvolutionConfig.load()` `[VERIFIED: lines 79-152]` | D-13 新字段按相同模式加入 + yaml/env/CLI 三层 override |

### Alternatives Considered & Why Not

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `litellm.cost_per_token` | 手写 token→USD 查找表 | 每次模型更新都要维护；`litellm.model_cost` 已覆盖 1000+ 模型 `[VERIFIED: keys listing 返回 >5 匹配]` |
| 两维 `dict[str,dict[str,Predict]]` (D-01 字面) | Sub-Module per tool (推荐) / 扁平化 key `tool::param` | 两维 dict 对 `named_parameters()` 不可见（实测）；扁平化丢失层次；sub-Module 两全 |
| 定制 `instruction_proposer` | 默认 proposer | DSPy docstring `[CITED: gepa.py:216-247]` 明确说明 default 已覆盖"绝大多数 use cases"；自定义只在多模态/强约束/provider-specific 下需要 |
| `component_selector="all"`（一次性优化全部 ~150 Predict） | `"round_robin"`（默认，循环逐个优化） | CONTEXT.md D-15 已选择不做 group cap；"all" 会把 5-section joint credit-assignment 问题放大到 150-unit 级别（PITFALLS #5 同理），`round_robin` 是默认且安全 |

**Installation:** 无新增依赖。验证命令：
```bash
/Users/slj/项目/hermes-agent-self-evolution/.venv/bin/python -c "import dspy, litellm; print(dspy.__version__)"
# Expected: 3.1.3
```

**Version verification:**
- DSPy 3.1.3: `.venv/lib/python3.13/site-packages/dspy/__init__.py` 含 GEPA；`Teleprompter` 要求 5-param metric（实测 `inspect.signature(metric).bind(None,None,None,None,None)` 必须通过） `[VERIFIED: gepa.py:368-373]`
- litellm 1.83.8: `importlib.metadata.version('litellm')` `[VERIFIED: 运行时实测]`

## Architecture Patterns

### Recommended Project Structure (deltas from current tree)

```
evolution/
├── core/
│   ├── config.py             # D-13: add max_cost_usd, reflection_model fields + CLI overrides
│   └── cost_tracker.py       # NEW: CostTracker class, Budget tracker, USD estimation
├── tools/
│   ├── tool_module.py        # D-01/D-02: add sub-Module per tool + _frozen_tool_desc
│   ├── tool_metric.py        # D-17: add joint_tool_param_metric (5-param sig)
│   ├── tool_constraints.py   # D-11: add ParamConsistencyChecker
│   └── evolve_tool_params.py # D-06: new Click CLI, mirrors evolve_tool_descriptions structure
output/
└── tools/
    ├── <timestamp>/           # Success — metrics.json with D-12/D-13/D-14 fields
    ├── FAILED_<timestamp>/    # Constraint / regression failure
    └── ABORTED_<timestamp>/   # NEW: max_cost_usd exhausted mid-run, aborted.json present
```

### Pattern 1: Sub-Module-per-Tool with Flat Per-Param Predict Dict

**What:** 每 tool 一个轻量 `dspy.Module`，内部持有单层 `dict[param_name, dspy.Predict]`。`ToolModule` 作为顶层持 `tools: dict[tool_name, _ToolParamBundle]`。

**When to use:** 需要 GEPA 发现 per-(tool, param) 独立可优化单元，且要保留 tool 与 param 层次命名以便 `get_evolved_descriptions()` 回溯。

**Why it solves D-01:** `named_parameters()` 对 Module-valued dict 子项会递归（`if isinstance(value, dspy.Module): for sub_name, param in value.named_parameters(): ...` `[VERIFIED: base_module.py:53-57]`）；对直接的 dict 值调用 `add_parameter` 时，只有 `Parameter` 实例被收录，嵌套的 dict 值被静默丢弃 `[VERIFIED: base_module.py:59-65 + smoke test 返回 0]`。把内部容器升格为 `dspy.Module` 绕过此 bug。

**Example:**
```python
# evolution/tools/tool_module.py (Phase 13 sketch)
import dspy

class _ToolParamBundle(dspy.Module):
    """Per-tool container holding flat dict[param_name, dspy.Predict].

    Wrapping in a dspy.Module makes the inner dict discoverable by
    ToolModule.named_parameters() — raw dict[str, dict[str, Predict]]
    at ToolModule level is NOT discovered by DSPy 3.1.3 (verified).
    """
    def __init__(self, tool_name: str, param_names: list[str], param_descs: dict[str, str]):
        super().__init__()
        self.tool_name = tool_name
        self.param_predictors: dict[str, dspy.Predict] = {}
        for pn in param_names:
            desc = param_descs.get(pn, "") or f"Parameter: {pn}"
            sig = dspy.Signature("param_name -> confirmation", instructions=desc)
            self.param_predictors[pn] = dspy.Predict(sig)

    def forward(self, param_name: str):
        # Not called during GEPA — param_predictors are pure instruction carriers.
        # forward defined only to satisfy dspy.Module contract.
        return dspy.Prediction(confirmation="")

class ToolModule(dspy.Module):
    def __init__(self, tool_descriptions: list):
        super().__init__()
        self.tools: dict[str, _ToolParamBundle] = {}
        self._frozen_tool_desc: dict[str, str] = {}   # D-02: physically isolated
        self._tool_names: list[str] = []
        for td in tool_descriptions:
            safe = td.name.replace("-", "_")
            param_descs = {p.name: p.description for p in td.params}
            self.tools[safe] = _ToolParamBundle(
                tool_name=td.name,
                param_names=[p.name for p in td.params],
                param_descs=param_descs,
            )
            self._frozen_tool_desc[td.name] = td.description or f"Tool: {td.name}"
            self._tool_names.append(td.name)
        self.selector = dspy.ChainOfThought(ToolSelectionWithParamsSignature)
    # ... forward() reads _frozen_tool_desc + self.tools[safe].param_predictors[pn].signature.instructions ...
```

After construction, `list(named_predictors())` yields entries like `tools['search_files'].param_predictors['pattern']` `[VERIFIED: smoke test ran V2 with 3 params and got 3 entries]`.

### Pattern 2: 5-param Metric Contract for GEPA (Strict Compile-Time Check)

**What:** 新 `joint_tool_param_metric` 与既有 `tool_selection_metric` 一致使用 `(example, prediction, trace=None, pred_name=None, pred_trace=None) -> float` 签名。GEPA 构造器在 `__init__` 就执行 `inspect.signature(metric).bind(None, None, None, None, None)` 并在失败时 raise TypeError `[VERIFIED: gepa.py:368-373]`。因此不加签名 test 也会在运行时立即失败——但 PITFALLS #12 + CONCERNS M2 要求加 unit test 做 TDD。

**When to use:** 任何新 GEPA metric。

**Code template:**
```python
# evolution/tools/tool_metric.py (extend existing module)
def joint_tool_param_metric(
    example: dspy.Example,
    prediction: dspy.Prediction,
    trace=None,
    pred_name=None,
    pred_trace=None,
) -> float:
    """Joint 0.5 * tool_match + 0.5 * param_match.
    tool_match: strip+lower exact; param_match: dict exact-match on parsed JSON.
    Returns: float in [0.0, 1.0]."""
    selected_tool = (getattr(prediction, "selected_tool", "") or "").strip().lower()
    correct_tool = (getattr(example, "correct_tool", "") or "").strip().lower()
    tool_match = 1.0 if selected_tool == correct_tool else 0.0

    correct_params = getattr(example, "correct_params", {}) or {}
    raw_params = getattr(prediction, "selected_params", "") or ""
    try:
        predicted_params = json.loads(raw_params) if isinstance(raw_params, str) else dict(raw_params)
        if not isinstance(predicted_params, dict):
            predicted_params = {}
    except (json.JSONDecodeError, TypeError):
        predicted_params = None  # ← marks "invalid output" — see §7 joint metric pitfall

    if predicted_params is None:
        param_match = 0.0
    else:
        param_match = 1.0 if predicted_params == correct_params else 0.0

    return 0.5 * tool_match + 0.5 * param_match
```

### Pattern 3: GEPA Compile Invocation (mirror of Phase 5 evolve_tool_descriptions)

```python
import dspy
from dspy.utils.usage_tracker import track_usage  # [VERIFIED: usage_tracker.py:69]

dspy.configure(lm=lm, track_usage=True)  # ← track_usage=False by default [VERIFIED: settings.py:25]

reflection_model_name = config.reflection_model or config.optimizer_model
reflection_lm = dspy.LM(reflection_model_name, **config.get_lm_kwargs())

optimizer = dspy.GEPA(
    metric=joint_tool_param_metric,          # D-17: 5-param sig
    max_metric_calls=iterations * 50,        # baseline multiplier; cost cap supersedes
    reflection_lm=reflection_lm,             # [VERIFIED: required — gepa.py:392-396]
    component_selector="round_robin",        # default, safe at 150-param scale
    seed=0,                                  # reproducibility
    track_stats=True,                        # enables detailed_results for debugging
)

with track_usage() as tracker:
    optimized_module = optimizer.compile(baseline_module, trainset=trainset, valset=valset)
# tracker.get_total_tokens() -> {lm_name: {prompt_tokens, completion_tokens, ...}} [VERIFIED: usage_tracker.py:57-65]
```

### Anti-Patterns to Avoid

- **Two-dimensional bare dict as parameter container:** `self.param_predictors: dict[str, dict[str, dspy.Predict]]` — Predict 完全对 GEPA 不可见（see §Pitfalls). Use sub-Module.
- **Calling `dspy.GEPA(...)` without `reflection_lm`:** AssertionError at construction `[VERIFIED: gepa.py:392-396]`。
- **Omitting `dspy.configure(track_usage=True)`:** `Prediction.get_lm_usage()` 返回 None，cost_tracker 永远看不到 token 数。
- **Silently catching GEPA exceptions and falling back to MIPROv2 without user opt-in:** CONCERNS §M2, D-15a 已明令禁止。
- **Passing 4-arg metric (e.g. `tool_selection_metric(example, prediction, trace=None, pred_name=None)`)：** GEPA 立即 raise TypeError `[VERIFIED: gepa.py:368-373]`，但要按 PITFALLS #12 加单测做前置保护。

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| tokens → USD | 手写模型价目表 | `litellm.cost_per_token(model=..., prompt_tokens=..., completion_tokens=...)` `[VERIFIED: 对 gpt-4.1-mini / openrouter/google/gemini-2.5-flash / dashscope/qwen-plus 全部返回有效 tuple]` | 模型定价每月变动；litellm 维护 1000+ 模型价目，升级是包升级 |
| LM usage 拦截 | 包装 dspy.LM.__call__ 或 monkeypatch litellm | `dspy.settings.configure(track_usage=True)` + `dspy.utils.usage_tracker.track_usage()` | 已内建 context manager，cache hit 自动忽略 `[VERIFIED: clients/lm.py:167]` |
| GEPA 参数发现 | 手写扁平化 key + reflection_lm adapter | `dspy.Module` + flat dict + `named_parameters()` | DSPy 内建递归逻辑 `[VERIFIED: base_module.py:23-67]` |
| per-tool rate | 手写 defaultdict 统计 | 现有 `CrossToolRegressionChecker.compute_per_tool_rates` `[VERIFIED: tool_metric.py:83-110]` | D-12 只是把既有返回值写进 metrics.json |
| 5-param metric contract 校验 | 自建接口断言 | `inspect.signature(fn).bind(None, None, None, None, None)` | GEPA 构造时就做 `[VERIFIED: gepa.py:368]` — TDD test 可复用 |
| GEPA 预算公式 | 推导 `iterations * N` 直觉值 | `auto="light"/"medium"/"heavy"` 或调用 `GEPA.auto_budget(num_preds=..., num_candidates=..., valset_size=...)` | auto_budget 公式 `max(2*(num_preds*2)*log2(num_candidates), 1.5*num_candidates) * M + full_evals * V` `[CITED: gepa.py:436-462]` — 可用来在 dry-run 里预估成本 |
| 嵌套 JSON 解析 | 手写 `find_brace_matching()` | 既有 `_parse_json_array` in `tool_dataset.py:213-240` / DSPy 3.x typed OutputField | dataset_builder 已有模式，ParamConsistencyChecker 直接复用 |

**Key insight:** Phase 13 在工具链上**一行 pip install 都不需要**。所有 "看起来新颖" 的基础设施（cost tracking、cost→USD、参数发现、metric 签名校验）都已经在 venv 里，只是从未被串联起来。Planner 的任务是**组装**，不是**发明**。

## Runtime State Inventory

> Phase 13 为**新建管道**，不做重命名/迁移。此 section 只做一遍巡查确认。

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | 无 — Phase 13 从 `datasets/tools/{train,val,holdout}.jsonl` 读取（已存在 324 examples，含 correct_params），不新建 store | None |
| Live service config | 无 — Phase 13 不触碰 hermes-agent 运行时；不修改 evolution.yaml schema | None |
| OS-registered state | 无 — Phase 13 是 CLI 一次性运行 | None |
| Secrets/env vars | `EVOLUTION_API_BASE`, `EVOLUTION_API_KEY`, `EVOLUTION_MODEL` 已存在（Phase 12），`HERMES_AGENT_REPO` 已存在 — Phase 13 的新 `reflection_model` 字段**不**引入新 env var（复用 evolution.yaml + CLI） | None |
| Build artifacts | 无 — 纯 Python 源码；`.venv` 已装 DSPy 3.1.3 | None |

**Nothing found in category:** 已验证 — Phase 13 是纯新增管道，所有外部状态都由既有 Phase 5/12 基础设施提供。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.10+ | 所有 | ✓ | 3.13.3 `[VERIFIED: .venv/lib/python3.13]` | — |
| `dspy>=3.0.0` | 全部 module / metric / GEPA | ✓ | 3.1.3 `[VERIFIED: importlib.metadata]` | — |
| `litellm` (DSPy transitive) | cost_tracker tokens→USD | ✓ | 1.83.8 `[VERIFIED: importlib.metadata]` | 若未来升级导致 `cost_per_token` 移除，fallback 到手写 gpt-4.1-mini/openrouter gemini 二模型价目表 |
| `click`, `rich`, `pyyaml`, `openai` | CLI/config | ✓ | `[CITED: pyproject.toml:17-23]` | — |
| `HERMES_AGENT_REPO` 可达 | Phase 5 baseline 比较（若通过文件 re-extract） | 取决于调用环境 `[VERIFIED: config.py:155-180 会 raise FileNotFoundError]` | `--baseline-run <output-dir>` flag 从既往 Phase 5 metrics.json 读 evolved_score（CONTEXT D-14 已指定） |
| 既往 Phase 5 `output/tools/<ts>/metrics.json` | D-14 v1 baseline 回归门的 "history" 来源 | 环境相关；当前仓库只有 `FAILED_20260422_201215` 无 evolved_score `[VERIFIED: ls 确认]` | 若无任何成功 Phase 5 记录：**fallback 到即时构造** baseline_module (原始 ToolDescription list) 跑 holdout 得到 baseline_score；实现上 `--baseline-run` optional，default 为 inline baseline |
| 外部 LLM API key | GEPA reflection + eval + factual + param_consistency | 环境相关 | 无 fallback — 缺 key 应 early fail |

**Missing dependencies with no fallback:** 无（纯开发依赖全部到位）

**Missing dependencies with fallback:**
- Phase 5 历史 metrics.json 的 evolved_score：若 `--baseline-run` 未传且无历史记录 → inline 计算 baseline (原始 ToolDescription 构造 ToolModule → holdout 评估)。Planner 必须让 fallback 默认生效，不强制 `--baseline-run`。

## Common Pitfalls

### Pitfall 1: 嵌套 dict Predict 对 GEPA 不可见（D-01 字面实现陷阱）
**What goes wrong:** `ToolModule.param_predictors: dict[str, dict[str, dspy.Predict]]`（D-01 字面）直接落地，`named_parameters()` 返回 0 条目，GEPA 的 `seed_candidate = {name: pred.signature.instructions for name, pred in student.named_predictors()}` 为空字典，优化变成 no-op，但 `optimizer.compile()` 不报错——成功标准 1 "ToolModule exposes per-parameter descriptions as independently optimizable parameters" 在**测试不到位时**会假阳性通过。
**Why it happens:** `BaseModule.named_parameters()` 在遇到 `dict` 值时只对每个 value 调用 `add_parameter(name, value)` 一次 `[VERIFIED: base_module.py:59-65]`；`add_parameter` 只识别 `Parameter` 实例和 `dspy.Module`——嵌套 dict 都不是，被静默忽略。
**How to avoid:**
1. 结构修订（首选）：每 tool 一个 sub-Module，内部持 flat `dict[str, dspy.Predict]`。`[VERIFIED: smoke test 返回 3 entries，命名 `tools['tool_a'].param_predictors['param_x']`]`
2. 备选：扁平化 key（`tool_a::param_x`）。丢失层次，与 D-04 冲突。
3. 断言测试（必须）：Wave 0 加 `test_tool_module_per_param_discovery` — 构造 3 tools × 3 params，`assert len(tm.named_predictors()) == 9` 且 key 模式正确。
**Warning signs:** `optimizer.compile()` 在几秒内返回、`detailed_results.candidates[0]` 为空 dict、metrics.json 的 `evolved_score == baseline_score`（精确相等，0 浮动）。
**Confidence:** HIGH — 直接运行时验证。

### Pitfall 2: `track_usage=False` 默认值让 cost_tracker 失效
**What goes wrong:** `EvolutionConfig` 里加了 `max_cost_usd`，cost_tracker 实现了 `track_usage()` context manager，但**忘记**调 `dspy.settings.configure(track_usage=True)`——`clients/lm.py:167` 的条件 `if ... and dspy.settings.usage_tracker ...` 永远 False，tracker 收到 0 tokens，"abort at threshold" 永远不触发。成本爆表不受控。
**Why it happens:** DSPy 默认 `track_usage=False` `[VERIFIED: settings.py:25]`；Phase 5 既有 CLI 没打开过。
**How to avoid:** evolve_tool_params 的入口 `configure` 调用改为 `dspy.configure(lm=lm, track_usage=True)`。加 unit test：mock LM 调用 2 次，`tracker.get_total_tokens()` 非空 dict。
**Warning signs:** Dry-run 里打印 "tracked tokens: {}" 为空。
**Confidence:** HIGH — 源码直接验证。

### Pitfall 3: reflection_lm 并非 "更小更快" 的同义词
**What goes wrong:** `--reflection-model openai/gpt-4.1-mini`（便宜的）替代默认 `optimizer_model=openai/gpt-4.1`，期望大幅降成本，结果 GEPA 反思质量骤降，候选 mutation 堆积低质量文本，被 param_consistency 或 v1 baseline gate 拒绝；iterations 更多消耗、总成本反升。
**Why it happens:** DSPy docstring `[CITED: gepa.py:215-217 / 313-315]`：`"GEPA benefits from a strong reflection model. Consider using dspy.LM(model='gpt-5', temperature=1.0, max_tokens=32000) for optimal performance"`。Reflection 是**理解失败 trace 并提出新 instruction** 的 LLM 工作，不是简单分类。
**How to avoid:** planner 在 Phase 13 的 plan 里写明 "`--reflection-model` 是 **成本** knob，降档前应先 10-example dry-run 验证质量没崩；推荐默认仍指向 `optimizer_model`"。
**Warning signs:** candidates Pareto front 在前 20 iterations 基本无改进；`detailed_results.val_aggregate_scores` 方差很大、趋势平坦。
**Confidence:** MEDIUM-HIGH — DSPy 官方 docstring 建议 + CONCERNS M8 原文。

### Pitfall 4: `correct_params` 归一化漏洞（D-10/D-17 exact-match 的隐形脆弱）
**What goes wrong:** LLM 返回 `selected_params = '{"pattern":"foo","file_pattern":"*.py"}'`，holdout 记录 `correct_params = {"file_pattern":"*.py","pattern":"foo"}`——key 顺序不同但语义相等，`dict1 == dict2` 在 Python 里**是 True**（✓）。但 value 层面：`"*.py"` vs `"*.py "`（尾空格）、`"(?i)foo"` vs `"(?i)FOO"`（正则语义相等但字符串不等）、`123` vs `"123"`（int vs str）——都是 0.0 param_match。
**Why it happens:** exact-match `dict == dict` 对 value 按 `__eq__` 比较；LLM 输出类型飘移（尤其 numeric）常见。
**How to avoid:**
1. joint_tool_param_metric 里对 `predicted_params` 做轻量归一化：所有 value strip() + 数字类型 coerce（尝试 `int(v) == correct_v` 若两边都能转）。
2. Unit test 覆盖：尾空格、key 顺序、int/str 混杂三个具体 case。
3. 归一化细节**留为 Claude 自由度**（CONTEXT.md 已标），planner 需在 PLAN 里写归一化规则清单。
**Warning signs:** val/holdout 分布上 param_match=0 的占比远高于 Phase 4 "correct_params 应当正确" 的主观预估。
**Confidence:** MEDIUM — 基于 JSON 序列化惯例；需实测 LLM 输出风格。

### Pitfall 5: param_consistency 的 LLM JSON 输出脆弱（CONCERNS §M4 放大）
**What goes wrong:** `ParamConsistencyChecker` 用 `dspy.ChainOfThought` + OutputField `has_conflicts: bool` + `conflicts: list[...]`。LLM 对 `bool` 的输出常为 `"True"` / `"yes"` / `"no conflicts found."`——`_parse_bool` (tool_constraints.py:15-29) 对 `"no conflicts found."` 返回 False 是正确的，但对 `"there are conflicts: ..."` 返回 False 是**危险的假阴性**。
**Why it happens:** `_parse_bool` conservative strategy 只认 `"true"/"yes"/"1"` 为 True。Phase 13 新增的 `ParamConsistencyChecker` 语义恰好相反（"has_conflicts" 的 True 是"坏"）——conservative 往"无冲突"偏，会漏报。
**How to avoid:**
1. 设计 Signature 时把问题反转：输出 `is_consistent: bool`（复用 `_parse_bool` 的保守性——"不确定 → False → 拒绝"）。
2. 加 typed OutputField `dspy.OutputField(desc=..., type=bool)` DSPy 3.x 支持（CONCERNS §M4 建议）。
3. parser 失败时 default=False（即 "failed check → reject"，比 default=True 安全）。
**Warning signs:** dry-run 里所有 tool 都 passed=True；构造 intentionally-inconsistent 测试数据却不拒。
**Confidence:** HIGH — `_parse_bool` 源码已读，Signature 反转是机械修订。

### Pitfall 6: GEPA `auto_budget` vs 手工 `max_metric_calls` 误用
**What goes wrong:** Phase 5 用 `max_metric_calls=iterations*50`（固定 50 倍），`iterations` 默认 10 → 500 metric calls。Phase 13 把可优化单元从 ~50 增到 ~150，50 倍没变，**每个 Predict 分到的预算** 从 10 骤降到 3.3。GEPA reflection 收敛要求每 predictor ≥3-5 mutation rounds `[CITED: gepa.py:436-437 公式暗示]`；欠预算 → candidates 全在 baseline 附近、无收敛。
**Why it happens:** 公式错位——`iterations*50` 是 "per-tool" 假设，不是 "per-predictor"。CONCERNS §M8 已预警成本、未预警预算不足。
**How to avoid:**
1. Phase 13 把默认改为 `max_metric_calls = iterations * max(50, 3 * num_predictors)`（单数小时保底 50×iterations，大 fan-out 保底 3 次 per-predictor）。
2. 推荐用 GEPA.auto_budget：`GEPA(auto="medium")` 对应 `n=12` `[CITED: gepa.py:19-23]`，`auto_budget(num_preds=150, num_candidates=12, valset_size=81)` 会给出一个由 `num_preds` 驱动的合理预算。
3. Planner 在 CLI 加 `--auto {light|medium|heavy}` 与 `--max-metric-calls` 互斥选项。
**Warning signs:** `detailed_results.total_metric_calls` 远小于 `total_metric_calls / num_predictors` = 个位数；candidate 数量 < 10。
**Confidence:** MEDIUM — 公式推导 + auto_budget 源码 + PITFALLS #11 cost 分析。

### Pitfall 7: joint metric exact-match 抹杀 partial credit（D-10 语义）
**What goes wrong:** 5 个参数，4 个正确 1 个错 → param_match=0.0；tool 选对 → tool_match=1.0；joint=0.5。另一候选 tool 错 param 全对 → joint 也 0.5。GEPA reflection 无法区分两者，credit-assignment 失败。GEPA paper 与 gepa.py docstring `[CITED: gepa.py:163-192]` 均建议 metric 返回 `ScoreWithFeedback` 对象（dict `{score: float, feedback: str}`），让 reflection LM 拿到"哪里错了"的文字。
**Why it happens:** exact-match 把连续信号压成阶梯；GEPA 的优势在"reflection from traces"，失去 partial credit 等于只给 MIPROv2 的信号量。
**How to avoid:**
1. **保持 D-10 exact-match 作为 acceptance metric**（公平、可复现）。
2. **额外实现 `joint_tool_param_metric_with_feedback`** 返回 `{"score": exact_match_score, "feedback": f"tool={selected_tool}/expected={correct_tool}; param_diff_keys={set(predicted)-set(correct)} ..."}`，仅在 GEPA `metric=` 里使用；holdout 评估仍用 bare exact-match。
3. Feedback 字符串**不含** PII / training-data verbatim（Pitfall 2 of v2 PITFALLS）。
4. Planner 需在 PLAN 里明确两版 metric 的使用边界。
**Warning signs:** `detailed_results` 里候选全部 aggregate 在 0.0 / 0.5 / 1.0 三个值；Pareto front 退化为阶梯函数。
**Confidence:** HIGH — GEPA docstring 明言支持 ScoreWithFeedback 且建议使用。

### Pitfall 8: v1 baseline 硬门的"历史文件缺席"阻塞
**What goes wrong:** D-14 规定 "Phase 13 evolved < v1 baseline − 0.02" → FAIL。但新 repo / 首次运行没有 Phase 5 历史 metrics.json；用户 `--baseline-run` 忘传；evolve_tool_params 立即报错退出——阻塞 onboarding。
**Why it happens:** D-14 未定义 fallback 行为。
**How to avoid:**
1. `--baseline-run` **非必填**。若传了：读 `output/tools/<timestamp>/metrics.json` 的 `evolved_score` 作为 v1_baseline_holdout。
2. 若未传：现场构造原始 `ToolModule`（无 param optimization）跑 holdout 得到 inline baseline；记录到 metrics.json 为 `v1_baseline_source: "inline"` vs `"historical"`。
3. 当 inline baseline 与即将要跑的 Phase 13 baseline_module 实际上是同一个（都是"未优化"）时，比较变成 `evolved_score >= inline_baseline_score - 0.02`，退化成 "Phase 13 evolved 不比自己原状差 2pp"——仍是有用的稳定性守卫。
4. Planner 必须在 PLAN 里写清此 fallback 语义，并将 `v1_baseline_source` 写入 metrics.json。
**Warning signs:** 用户首次运行报 "cannot find baseline"，弃用。
**Confidence:** HIGH — 基于 filesystem 现状实测（output/tools 只有 FAILED_ 目录）。

### Pitfall 9: `_format_paren_concat` 在 150 次 param 写回中的脆弱（CONCERNS §L1 放大）
**What goes wrong:** Phase 13 CONTEXT 已把 `_format_paren_concat` 修订放到 Deferred，但 Phase 13 的 dry-run 会调用 `_generate_diff()`（借道 Phase 5 的 diff 生成逻辑），若涉及 paren-concat 格式的 param，diff 本身可能已经显示变形字符（triple-escaped quotes）。**生产上** Phase 13 不写回，此问题为 dry-run UX 瑕疵。
**Why it happens:** CONCERNS §L1 已列明：`text.replace('\\', '\\\\').replace('"', '\\"')` 对已经转义的内容二次转义出错；paren-concat 的 70-char word-split 对中文（L1 作者都称"UX nit"）按 codepoint 截行，可能生成丑陋但语法有效的输出。
**How to avoid:**
- Phase 13 **不**修订 `_format_paren_concat`（CONTEXT deferred）。
- Plan 加一条集成测试：用 10 条含中文 / 单双引号 / URL 的 param 描述跑 `_format_description` round-trip，`ast.parse()` 解析通过即可。
- 若测试 fail：在 Phase 13 PLAN 里作为 "new subtask" 修订；否则记录 "Phase 13 sidecar verified format integrity on N=10 samples" 继续。
**Warning signs:** dry-run diff 里出现 `\\\"\"\"` 四重转义或截断的中文词。
**Confidence:** MEDIUM — CONCERNS §L1 本身标 LOW severity，Phase 13 没有代码路径触发写回。

### Pitfall 10: GEPA track_stats 内存开销在 150 Predict × N candidates 下
**What goes wrong:** `track_stats=True`（我们需要）+ `track_best_outputs=True`（不需要）会保留 `best_outputs_valset: list[list[tuple[int, list[Prediction]]]]` `[CITED: gepa.py:89-90]`——N_candidates × M_val_examples × K_predictions 的矩阵。50 candidates × 81 val × 5 preds ≈ 20000 Prediction 对象驻留内存。
**Why it happens:** 默认 GEPA save/track 逻辑没为 fan-out 场景做内存优化。
**How to avoid:** `track_best_outputs=False`（默认），`track_stats=True` 足矣（我们需要 `detailed_results.candidates[i]` 做写入 metrics.json 的 debug dump）。planner 无需额外代码，但 PLAN 里需显式不传 `track_best_outputs=True`。
**Confidence:** MEDIUM — 基于源码 dataclass field 分析，未实测内存。

## Code Examples

### Nested Dict Discovery Trap（D-01 陷阱的直接证据）

```python
# verified 2026-05-07 on dspy 3.1.3, python 3.13.3
import dspy
sig = dspy.Signature('x -> y', instructions='p1')

class NestedDict(dspy.Module):
    def __init__(self):
        super().__init__()
        self.nested = {
            'tool_a': {'param_x': dspy.Predict(sig), 'param_y': dspy.Predict(sig)},
            'tool_b': {'param_z': dspy.Predict(sig)},
        }
    def forward(self, x): return dspy.Prediction(y=x)

print(len(NestedDict().named_parameters()))
# Output: 0         ← GEPA sees nothing

class FlatDict(dspy.Module):
    def __init__(self):
        super().__init__()
        self.tool_predictors = {'a': dspy.Predict(sig), 'b': dspy.Predict(sig)}
    def forward(self, x): return dspy.Prediction(y=x)

print(len(FlatDict().named_parameters()))
# Output: 2         ← works

class _Bundle(dspy.Module):
    def __init__(self, names):
        super().__init__()
        self.param_predictors = {n: dspy.Predict(sig) for n in names}
    def forward(self, x): return dspy.Prediction(y=x)

class SubModulePerTool(dspy.Module):
    def __init__(self):
        super().__init__()
        self.tools = {'tool_a': _Bundle(['param_x','param_y']), 'tool_b': _Bundle(['param_z'])}
    def forward(self, x): return dspy.Prediction(y=x)

print([name for name, _ in SubModulePerTool().named_parameters()])
# Output: ["tools['tool_a'].param_predictors['param_x']",
#          "tools['tool_a'].param_predictors['param_y']",
#          "tools['tool_b'].param_predictors['param_z']"]
# ← hierarchical names preserved (D-04 compliant)
```

### tokens → USD via litellm（cost_tracker 内部模式）

```python
# verified: litellm 1.83.8 returns finite (prompt_usd, completion_usd) for all three models in use
import litellm

def estimate_cost_usd(usage_by_lm: dict) -> float:
    """usage_by_lm comes from dspy.utils.usage_tracker.UsageTracker.get_total_tokens()
    Shape: {lm_name: {prompt_tokens: int, completion_tokens: int, ...}}"""
    total_usd = 0.0
    for lm_name, usage in usage_by_lm.items():
        pt = usage.get("prompt_tokens", 0) or 0
        ct = usage.get("completion_tokens", 0) or 0
        try:
            prompt_cost, completion_cost = litellm.cost_per_token(
                model=lm_name, prompt_tokens=pt, completion_tokens=ct,
            )
            total_usd += prompt_cost + completion_cost
        except Exception:
            # Fallback: assume $0.001 per 1K prompt + $0.003 per 1K completion
            total_usd += (pt / 1000.0) * 0.001 + (ct / 1000.0) * 0.003
    return total_usd

# Verified outputs:
# openai/gpt-4.1-mini (1000 pt, 500 ct)  -> (0.0004, 0.0008) = $0.0012
# openrouter/google/gemini-2.5-flash     -> (0.0003, 0.00125) = $0.00155
# dashscope/qwen-plus                    -> (0.0004, 0.0006) = $0.0010
```

### GEPA cost cap loop（cost_tracker 核心逻辑）

```python
# evolution/core/cost_tracker.py (sketch)
from dspy.utils.usage_tracker import track_usage
import litellm

class CostTracker:
    def __init__(self, max_usd: float):
        self.max_usd = max_usd
        self.spent_usd = 0.0
        self._tracker = None
    def __enter__(self):
        self._ctx = track_usage()
        self._tracker = self._ctx.__enter__()
        return self
    def __exit__(self, *a):
        return self._ctx.__exit__(*a)
    def poll(self) -> float:
        """Call between GEPA iterations or eval batches."""
        usage = self._tracker.get_total_tokens()
        self.spent_usd = estimate_cost_usd(usage)
        return self.spent_usd
    def exceeded(self) -> bool:
        return self.poll() > self.max_usd

# Usage: GEPA doesn't expose a per-iteration callback; best hook is (1) check before/after
# optimizer.compile(), and (2) use gepa_kwargs['stop_callbacks'] with custom StopperProtocol.
# [CITED: gepa.py:288-295] — gepa_kwargs.stop_callbacks is documented passthrough.
```

### Joint metric with feedback（Pitfall 7 缓解）

```python
# evolution/tools/tool_metric.py (new)
import json
import dspy

def joint_tool_param_metric(example, prediction, trace=None, pred_name=None, pred_trace=None):
    """Pure exact-match score used for acceptance gate and holdout scoring."""
    selected_tool = (getattr(prediction, "selected_tool", "") or "").strip().lower()
    correct_tool = (getattr(example, "correct_tool", "") or "").strip().lower()
    tool_match = 1.0 if selected_tool == correct_tool else 0.0
    correct_params = getattr(example, "correct_params", {}) or {}
    raw = getattr(prediction, "selected_params", "") or ""
    try:
        predicted = json.loads(raw) if isinstance(raw, str) else (dict(raw) if raw else {})
    except (json.JSONDecodeError, TypeError):
        predicted = None
    if not isinstance(predicted, dict):
        param_match = 0.0
    else:
        # TODO: light normalization (strip, int/str coerce) — recorded as Claude discretion
        param_match = 1.0 if predicted == correct_params else 0.0
    return 0.5 * tool_match + 0.5 * param_match

def joint_tool_param_metric_with_feedback(example, prediction, trace=None, pred_name=None, pred_trace=None):
    """GEPA-facing metric returning {"score": float, "feedback": str}.
    Used ONLY in the GEPA(metric=) slot; holdout evaluation uses the bare function above."""
    score = joint_tool_param_metric(example, prediction, trace, pred_name, pred_trace)
    correct_tool = getattr(example, "correct_tool", "")
    selected_tool = getattr(prediction, "selected_tool", "")
    correct_params = getattr(example, "correct_params", {}) or {}
    raw = getattr(prediction, "selected_params", "")
    fb_parts = []
    if selected_tool.strip().lower() != correct_tool.strip().lower():
        fb_parts.append(f"Wrong tool: picked '{selected_tool}', expected '{correct_tool}'.")
    try:
        predicted = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    except Exception:
        predicted = None
    if predicted is None:
        fb_parts.append("selected_params was not valid JSON.")
    elif predicted != correct_params:
        missing = set(correct_params) - set(predicted)
        extra = set(predicted) - set(correct_params)
        bad_val = [k for k in set(correct_params) & set(predicted) if correct_params[k] != predicted[k]]
        fb_parts.append(f"Param mismatch — missing keys: {sorted(missing)}; extra: {sorted(extra)}; wrong value: {sorted(bad_val)}.")
    if not fb_parts:
        fb_parts.append("Perfect match.")
    return {"score": score, "feedback": " ".join(fb_parts)}
```

### ParamConsistencyChecker Signature（D-11 具体）

```python
# evolution/tools/tool_constraints.py (append)
import dspy
from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintResult
from evolution.tools.tool_constraints import _parse_bool  # reuse existing

class ParamConsistencyChecker:
    """Per-tool batch LLM consistency check.

    Inverts the question from 'has_conflicts' to 'is_consistent' so that
    _parse_bool's conservative strategy (defaults to False) fails CLOSED —
    i.e., parse ambiguity rejects the candidate, matching D-11 semantics.
    """
    class ConsistencySignature(dspy.Signature):
        """Verify that a tool's frozen top-level description and all of its evolved
        parameter descriptions are mutually consistent. Inconsistency includes:
        1) Contradictory constraints (e.g. path param says 'absolute only' while
           tool-level says 'supports relative').
        2) Abbreviation / terminology drift (e.g. 'URL' vs 'url' vs 'link' across params).
        3) Required-field mismatch (a description implying a param is required when
           the schema lists it optional, or vice versa).
        Respond strictly with the boolean and brief explanation.
        """
        tool_name: str = dspy.InputField()
        frozen_tool_description: str = dspy.InputField()
        evolved_param_descriptions: str = dspy.InputField(
            desc="JSON object: {param_name: evolved_description_text}"
        )
        is_consistent: bool = dspy.OutputField(
            desc="True ONLY if all param descriptions are coherent with each other "
                 "and with the frozen tool description; False on any contradiction."
        )
        explanation: str = dspy.OutputField(
            desc="If False, name the conflicting params and the nature of the conflict. "
                 "If True, one-line confirmation."
        )

    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.checker = dspy.ChainOfThought(self.ConsistencySignature)

    def check(self, tool_name: str, frozen_desc: str, param_descs: dict[str, str]) -> ConstraintResult:
        import json
        lm = dspy.LM(self.config.eval_model, **self.config.get_lm_kwargs())
        with dspy.context(lm=lm):
            result = self.checker(
                tool_name=tool_name,
                frozen_tool_description=frozen_desc,
                evolved_param_descriptions=json.dumps(param_descs, ensure_ascii=False),
            )
        is_consistent = _parse_bool(result.is_consistent)  # conservative: unknown -> False
        explanation = str(getattr(result, "explanation", ""))
        return ConstraintResult(
            passed=is_consistent,
            constraint_name="param_consistency",
            message=f"{'Consistent' if is_consistent else 'Inconsistent'} param descriptions for '{tool_name}'",
            details=explanation,
        )

    def check_all(self, evolved_tools: list, frozen_tool_descs: dict[str, str]) -> list[ConstraintResult]:
        results = []
        for tool in evolved_tools:
            param_descs = {p.name: p.description for p in tool.params}
            results.append(self.check(tool.name, frozen_tool_descs.get(tool.name, ""), param_descs))
        return results
```

### ABORTED/FAILED directory minimal schema

```json
// output/tools/ABORTED_20260507_HHMMSS/aborted.json
{
  "timestamp": "20260507_HHMMSS",
  "status": "ABORTED_COST_CAP",
  "max_cost_usd": 20.0,
  "final_cost_usd": 20.34,
  "spent_breakdown_by_lm": {
    "openai/gpt-4.1":       {"prompt_tokens": 450000, "completion_tokens": 50000, "usd": 6.8},
    "openai/gpt-4.1-mini":  {"prompt_tokens": 3200000,"completion_tokens": 180000, "usd": 13.54}
  },
  "evaluated_candidates": 47,
  "num_predictors": 142,
  "last_best_val_score": 0.612,
  "partial_evolved_descriptions": [
    {"tool": "search_files", "param": "pattern", "original": "...", "evolved": "..."},
    ...
  ]
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| GEPA metric with 2-param `(gold, pred)` | 5-param `(gold, pred, trace, pred_name, pred_trace)` | DSPy 3.0.0 release | Phase 13 metric must follow; 构造时 raise TypeError 否则 `[VERIFIED: gepa.py:368-373]` |
| GEPA `max_steps=iterations` | `max_metric_calls=N` or `auto={"light","medium","heavy"}` or `max_full_evals=M` — 必须**恰好一个** | DSPy 3.0 | 三选一的 assertion `[VERIFIED: gepa.py:378-383]` |
| Silent MIPROv2 fallback on GEPA error | Loud raise + `--allow-miprov2-fallback` opt-in | 项目内决定（D-15a, Phase 12 follow-up） | evolve_tool_params 从 day 1 loud；evolve_skill / evolve_tool_descriptions 留给后续 hygiene PR |
| Custom instruction_proposer | Default GEPA proposer (via `gepa` package) | DSPy 3.0 | 除非多模态 / 强约束，别折腾 `[CITED: gepa.py:219-247]` |
| Manual cost tracking | `dspy.settings.configure(track_usage=True)` + `track_usage()` + `litellm.cost_per_token` | DSPy 3.x + litellm | Phase 13 首次启用；track_usage 默认 False `[VERIFIED: settings.py:25]` |

**Deprecated/outdated:**
- `dspy.GEPA(max_steps=...)` — 3.x 不识别（`max_metric_calls`/`max_full_evals`/`auto` 三选一 `[VERIFIED: gepa.py:378-383]`）。
- `dspy.LM(model="...", retries=...)` 的 `retries` kwarg — litellm 用 `num_retries`（CONCERNS §M9 背景，Phase 13 不需要改）。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | 项目偏好用 `openai/gpt-4.1-mini` 作 eval、`openai/gpt-4.1` 作 reflection — 同 Phase 5。Phase 13 延续 | Standard Stack | 如 Phase 13 应换用更便宜 eval，cost_tracker 预测会偏 |
| A2 | 现有 Phase 4 dataset 的 correct_params value 类型主要是 str；少数 bool/int。joint metric normalization 规则以 str 为主 | Pitfall 4 | 若 dataset 中大量 int / bool / list value，归一化规则不足，param_match 假阴高发 |
| A3 | LiteLLM 1.83.8 `cost_per_token` 对 OpenRouter / DashScope 的价格来源是上游 provider pricing API；定期更新 | Don't Hand-Roll | 若某模型下游价格与 litellm 快照差异大，cost_tracker 预估偏差；不会阻塞 Phase 13 功能 |
| A4 | GEPA 在 ~150 predictor 的实测行为与 5 predictor 行为定性一致（round_robin 循环每 predictor 分得 budget/N）—— 未找到 DSPy 官方针对大 fan-out 的性能 benchmark | Pitfall 6 | 若 GEPA 在 150 fan-out 下有未知行为（内存爆炸、reflection_lm 崩溃），Phase 13 可能需要回退 param-group cap |
| A5 | 用户会运行 Phase 5 至少一次以获得 v1 baseline 历史文件；缺失时 inline fallback 不会产生误导 | Pitfall 8 | 如果用户直接跳到 Phase 13（跳过 Phase 5），inline baseline 就是"原始 ToolModule"——此时 "Phase 13 baseline" 与 "v1 baseline" 是同一个，gate 退化为 "Phase 13 不比自身更差 2pp"，语义仍正确 |

**If this table is empty:** N/A — 5 条假设需要 discuss-phase 或 planner 确认。A1/A2/A5 影响较小；A3/A4 是 Phase 13 运行时才能完全验证。

## Open Questions

1. **`component_selector="round_robin"` 是否对 D-15 的 "no group cap" 决策最优？**
   - What we know: round_robin 逐个优化 `[CITED: gepa.py:251-253]`；all 同时优化；150 unit × round_robin 意味着 ≥150 次 reflection 才能触及每个 predictor 一次。
   - What's unclear: DSPy 有无 "weighted" selector 让 GEPA 按 feedback 信号重点优化高影响 predictor。
   - Recommendation: Phase 13 默认 round_robin；PLAN 预留 `--component-selector {round_robin,all}` CLI flag，默认 round_robin。未实测 `all` 的 fan-out 稳定性，归为 Phase 后续 knob。

2. **joint metric 的 param normalization 规则严格度**
   - What we know: exact-match 对尾空格 / 大小写 / int-vs-str 敏感。
   - What's unclear: dataset 里 correct_params 的实际分布（多为 str，还是 mixed type？）。
   - Recommendation: PLAN 的第一个 subtask 是跑一个 `inspect_dataset.py` 脚本，统计 correct_params value 类型分布；据此决定 normalization 规则是 "strip only" 还是 "strip + numeric coerce"。

3. **ABORTED 状态下是否要写回部分 evolved（dry-run 等价）？**
   - What we know: CONTEXT 明示 Phase 13 "不触发 write_back"，输出仅入 `output/`。
   - What's unclear: ABORTED_ 的 `partial_evolved_descriptions` 是否要按 diff 格式写一份方便用户手工 cherry-pick？
   - Recommendation: 写一份 `partial_diff.txt`（借 Phase 5 的 `_generate_diff`），保留手工审阅入口；不做 write_back。

## Security Domain

> `security_enforcement` 在 `.planning/config.json` 中未显式 false，按缺省"启用"处理。Phase 13 对安全敏感面较窄（不做 mining、不写 hermes-agent、不调 external service），但仍需覆盖。

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Phase 13 不新增认证 —— 复用 evolution.yaml 里的 API key |
| V3 Session Management | No | 无会话状态 |
| V4 Access Control | No | 单用户 CLI |
| V5 Input Validation | yes | correct_params 类型校验（见 joint metric）；ParamConsistencyChecker 对 LLM 输出 JSON 解析使用 `_parse_json_array` 的 try/regex 两段式；`_parse_bool` 保守策略 |
| V6 Cryptography | No | 不处理密钥（复用 Phase 12 的 env-var 引用） |
| V7 Error Handling & Logging | yes | aborted.json + FAILED/ABORTED 目录；metrics.json 不能含 LLM 的 PII echo（v2 PITFALLS #2 间接相关，但 Phase 13 不做 mining，风险低） |
| V14 Configuration | yes | `max_cost_usd` 默认 20.0 是开发者预算护栏；literal API key warning 已在 Phase 12 实现 |

### Known Threat Patterns for {DSPy + LiteLLM + CLI}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| API key 泄漏到 `output/*/metrics.json` | Information Disclosure | 不把 `config.api_key` 写入 metrics.json；模型名（`optimizer_model`, `reflection_model`）OK 入 metrics（Phase 5 既有） |
| `subprocess` 路径遍历（inherited from M6） | Tampering | Phase 13 不调 subprocess；hermes_repo 只读 |
| 恶意 param 描述里含 prompt injection（针对 reflection_lm） | Tampering | baseline descriptions 来自 hermes-agent 源码，信任等级与项目相同；evolved descriptions 由 GEPA 生成后走 ParamConsistencyChecker + factual checker 门控 |
| 用户在 `--baseline-run` 指向任意路径加载 metrics.json | Tampering | 对解析结果做字段类型校验：`evolved_score: float in [0,1]`；路径不进 subprocess |
| Cost DoS（训练到预算耗光） | Denial of Service | `max_cost_usd` cap + CLI 启动时 dry-run 估算 + `--dry-run` 必须打印预估（planner 设计 UX） |

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest >=7.0` `[CITED: pyproject.toml:27]` + `pytest-asyncio >=0.21`（仅需时） |
| Config file | `pyproject.toml [tool.pytest.ini_options]` `[VERIFIED: pyproject.toml:41-43]` (testpaths=["tests"], python_files=["test_*.py"]) |
| Quick run command | `/Users/slj/项目/hermes-agent-self-evolution/.venv/bin/python -m pytest tests/tools/ -x --tb=short` |
| Full suite command | `/Users/slj/项目/hermes-agent-self-evolution/.venv/bin/python -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TOOL-V2-02 (SC-1) | `ToolModule.named_predictors()` 发现 sum(params_per_tool) 个条目 | unit | `pytest tests/tools/test_tool_module.py::TestToolModulePerParam::test_per_param_discovery -x` | ❌ Wave 0 |
| TOOL-V2-02 (SC-1) | Predict keys 保留层次命名 `tools[<tool>].param_predictors[<param>]` | unit | `pytest tests/tools/test_tool_module.py::TestToolModulePerParam::test_key_hierarchy_preserved -x` | ❌ Wave 0 |
| TOOL-V2-02 (SC-2) | tool-level description 对 `named_parameters()` 不可见（`_frozen_tool_desc` 为纯 str dict） | unit | `pytest tests/tools/test_tool_module.py::TestToolModulePerParam::test_tool_desc_frozen_not_discoverable -x` | ❌ Wave 0 |
| TOOL-V2-02 (SC-3) | `_check_size("param_description")` 对 201-char 文本返回 passed=False | unit | `pytest tests/test_constraints.py::TestCheckSize::test_param_desc_200_limit -x` | 部分（既有 `_check_size` 测试，可能需补 201-char edge） |
| D-10 | joint metric 4 组输入返回正确分数（tool+param 全对=1.0；tool 对 param 错=0.5；tool 错 param 对=0.5；两错=0.0） | unit | `pytest tests/tools/test_tool_metric.py::TestJointToolParamMetric -x` | ❌ Wave 0 |
| D-10 | joint metric 签名通过 5-param bind（GEPA 契约） | unit | `pytest tests/tools/test_tool_metric.py::TestJointToolParamMetric::test_5_param_signature -x` | ❌ Wave 0 |
| D-11 | ParamConsistencyChecker 对 intentionally contradictory params 返回 passed=False | unit+mocked LLM | `pytest tests/tools/test_tool_constraints.py::TestParamConsistencyChecker::test_rejects_contradiction -x` | ❌ Wave 0 |
| D-11 | ParamConsistencyChecker parse failure → passed=False（保守） | unit | `pytest tests/tools/test_tool_constraints.py::TestParamConsistencyChecker::test_parse_failure_rejects -x` | ❌ Wave 0 |
| D-12 | evolve_tool_params CLI 写出 `per_tool_baseline_rates` 与 `per_tool_evolved_rates` 到 metrics.json | integration (mock LM) | `pytest tests/tools/test_evolve_tool_params.py::test_metrics_includes_per_tool_rates -x` | ❌ Wave 0 |
| D-13 | cost_tracker 对 mock LM 的 2 次调用返回非空 usage dict 与 >0 USD | unit | `pytest tests/test_cost_tracker.py::TestCostTracker::test_tracks_after_lm_call -x` | ❌ Wave 0 |
| D-13 | cost_tracker.exceeded() 在超阈值后返回 True | unit | `pytest tests/test_cost_tracker.py::TestCostTracker::test_exceeded_above_threshold -x` | ❌ Wave 0 |
| D-14 | v1 baseline fallback：无 `--baseline-run` 时 `metrics.json.v1_baseline_source == "inline"` | integration (mock LM) | `pytest tests/tools/test_evolve_tool_params.py::test_v1_baseline_inline_fallback -x` | ❌ Wave 0 |
| D-14 | evolved 比 v1 baseline 低 > 2pp → FAILED_ 目录（不 deploy） | integration (mock LM) | `pytest tests/tools/test_evolve_tool_params.py::test_v1_regression_hard_gate -x` | ❌ Wave 0 |
| D-15a | 默认 GEPA 失败直接 raise（无 fallback） | unit (mock GEPA raise) | `pytest tests/tools/test_evolve_tool_params.py::test_gepa_failure_loud -x` | ❌ Wave 0 |
| D-15a | `--allow-miprov2-fallback` 启用时 fallback 且 `optimizer_used == "miprov2"` | unit (mock) | `pytest tests/tools/test_evolve_tool_params.py::test_gepa_fallback_opt_in -x` | ❌ Wave 0 |
| D-17 | joint_tool_param_metric JSON 解析失败 → 0.0 param_match（非 0.5） | unit | `pytest tests/tools/test_tool_metric.py::TestJointToolParamMetric::test_invalid_json_scores_zero -x` | ❌ Wave 0 |
| D-18 | holdout 循环 debug dump 含 `(correct_params_json, selected_params_json)` 对 | integration (mock LM) | `pytest tests/tools/test_evolve_tool_params.py::test_debug_dump_contains_param_pairs -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `/Users/slj/项目/hermes-agent-self-evolution/.venv/bin/python -m pytest tests/tools/ -x --tb=short`（Phase 13 新增测试全集中在 tests/tools/ + tests/test_cost_tracker.py）
- **Per wave merge:** `/Users/slj/项目/hermes-agent-self-evolution/.venv/bin/python -m pytest tests/ -v`（全部 353+ 测试；允许 Phase 13 新增 +15 左右）
- **Phase gate:** 全部通过 + 一次 evolve_tool_params 实 dry-run（`--iterations 1 --dry-run`）不报错；若有 API key，一次 `--iterations 1 --max-cost-usd 2.0` 实 E2E。

### Wave 0 Gaps

- [ ] `tests/tools/test_tool_module.py` — 扩展：`TestToolModulePerParam` 覆盖 discovery / key hierarchy / frozen desc 三项（3 new tests）
- [ ] `tests/tools/test_tool_metric.py` — 扩展：`TestJointToolParamMetric`，4 match cases + 5-param sig + invalid-json（~6 new tests）
- [ ] `tests/tools/test_tool_constraints.py` — 扩展：`TestParamConsistencyChecker`（至少 4 tests，含 mock LM Signature）
- [ ] `tests/test_cost_tracker.py` — NEW 模块，覆盖 tracks_after_lm_call / exceeded / token_to_usd_openrouter_fallback（~5 tests）
- [ ] `tests/tools/test_evolve_tool_params.py` — NEW 集成测试文件，mock LM + mock GEPA / 覆盖 D-12/D-14/D-15a/D-18（~8 tests）
- [ ] `tests/test_constraints.py` — 可能需补 `test_param_desc_200_limit`（如 Phase 5 未覆盖 201-char 边界）
- [ ] shared fixtures：`tests/tools/conftest.py` 可能需 `mock_lm_that_returns(response_factory)` helper（若现有 mock 风格不够）

*（现有 test framework 已到位；无需 framework install。Phase 12 已验证 pytest + 353 tests 绿。）*

## Sources

### Primary (HIGH confidence)

- `/Users/slj/项目/hermes-agent-self-evolution/.venv/lib/python3.13/site-packages/dspy/teleprompt/gepa/gepa.py` (DSPy 3.1.3 GEPA 源码) — 5-param metric 契约 (lines 368-373)；reflection_lm required (392-396)；component_selector 默认 / 选项 (251-253)；max_metric_calls / auto_budget 公式 (431-462)；compile() 使用 named_predictors (540, 558)
- `/Users/slj/项目/hermes-agent-self-evolution/.venv/lib/python3.13/site-packages/dspy/primitives/base_module.py` lines 23-67 — `named_parameters()` 对 dict 只递归一层
- `/Users/slj/项目/hermes-agent-self-evolution/.venv/lib/python3.13/site-packages/dspy/primitives/module.py` lines 103-106 — `named_predictors()` filter
- `/Users/slj/项目/hermes-agent-self-evolution/.venv/lib/python3.13/site-packages/dspy/utils/usage_tracker.py` — `UsageTracker.get_total_tokens()` 输出 shape；track_usage context manager
- `/Users/slj/项目/hermes-agent-self-evolution/.venv/lib/python3.13/site-packages/dspy/clients/lm.py` lines 167-168, 205-206, 321 — `track_usage` 触发条件
- `/Users/slj/项目/hermes-agent-self-evolution/.venv/lib/python3.13/site-packages/dspy/dsp/utils/settings.py:25` — `track_usage=False` 默认
- 运行时 smoke test（本研究新产）：2D dict 不可发现、sub-Module 可发现；litellm.cost_per_token 对 3 类模型全部 return 有效 tuple
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/tools/tool_loader.py` lines 520-578, 706-771 — write-back + format helpers
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/tools/tool_constraints.py` — ToolFactualChecker 模板
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/core/constraints.py:95-117` — `_check_size("param_description")` 200 char limit
- `/Users/slj/项目/hermes-agent-self-evolution/datasets/tools/{train,val,holdout}.jsonl` (324 lines total; correct_params 字段实测)
- `/Users/slj/项目/hermes-agent-self-evolution/.planning/phases/13-per-parameter-description-optimization/13-CONTEXT.md` (D-01~D-18)
- `/Users/slj/项目/hermes-agent-self-evolution/.planning/research/PITFALLS.md` §Pitfall 1, 11, 12
- `/Users/slj/项目/hermes-agent-self-evolution/.planning/codebase/CONCERNS.md` §M2, M3, M4, M8, L1

### Secondary (MEDIUM confidence)

- DSPy 3.1.3 gepa.py docstring (lines 215-247) — reflection_lm 模型强度建议、instruction_proposer 何时自定义
- DSPy 3.1.3 gepa.py docstring (lines 248-256) — component_selector 策略说明
- `litellm.model_cost` 字典（运行时查询）— 覆盖 openrouter/google/gemini-2.5-flash、dashscope/qwen-plus、openai/gpt-4.1-mini

### Tertiary (LOW confidence)

- 无 — 本研究 HIGH/MEDIUM source 对所有断言已足够。WebSearch 在 2026-05-07 对 Bedrock 侧 400 未返回结果（单次工具错误，不影响结论）。

## Metadata

**Confidence breakdown:**
- Standard stack (DSPy/litellm API surface): HIGH — 本地源码 + 运行时 smoke test 双重验证
- Architecture (sub-Module-per-tool pattern)：HIGH — 实际 smoke test 证实 named_parameters 发现正确
- Cost tracker plumbing: HIGH — track_usage + litellm.cost_per_token 实测 OK 对 3 个项目实际模型
- Joint metric correctness: MEDIUM-HIGH — 代码模板按 D-10/D-17 字面设计，但 LLM JSON 输出稳定性需 integration test 实测
- ParamConsistencyChecker 设计：MEDIUM-HIGH — Signature 反转策略基于既有 `_parse_bool` 源码，但 LLM 对 `is_consistent` 的回答风格尚未实测
- v1 baseline fallback 语义：HIGH — filesystem 现状 + D-14 决策文字对齐
- Pitfall 6 (GEPA budget shape at fan-out)：MEDIUM — 公式推导 + DSPy 官方 auto_budget 源码，但 150-predictor 实测未做

**Research date:** 2026-05-07
**Valid until:** 2026-06-07 (30 天 — DSPy 3.x 已进入稳定期，核心 API 契约变更概率低；但 `max_metric_calls` / `auto_budget` 在次版本升级时可能微调)
