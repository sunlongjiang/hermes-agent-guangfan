# Phase 15: Think-Augmented Tool Selection — Research

**Researched:** 2026-05-09
**Status:** Final
**Author:** orchestrator-direct (gsd-phase-researcher subagent retried twice; both attempts socket-dropped before write — orchestrator synthesized the research from direct file reads to unblock planning)

> **Scope guard.** Phase 15 设计已在 [15-CONTEXT.md](./15-CONTEXT.md) 锁定 17 条决策（D-01..D-17）。本研究**不重新设计**——仅校验框架机制、固定 file:line 引用、回答 planner 必须的开放点（Wave 拆分、ab_comparison.json schema、ConstraintResult 写入策略、ThinkABGate 双 API 形态）。所有 D-XX 引用指向 CONTEXT.md。

---

## 0. Phase 形状速览

| 项目 | 值 |
|---|---|
| 目标 | 在 ToolModule 中加入可选的 reasoning 前置 Predict，使 GEPA 可优化 reasoning 模板，并以 think-off / think-on A/B 验证其在 ambiguous 子集上的净收益 |
| Requirements | TOOL-V2-03（[.planning/REQUIREMENTS.md:74](../../REQUIREMENTS.md)） |
| 依赖 Phase | Phase 13（per-param 模块结构 + V1BaselineGate + cost tracking） |
| 新增模块 | `evolution/tools/think_metrics.py`（含 `ThinkABGate`）；`evolution/tools/evolve_tool_reasoning.py`（CLI） |
| 修改模块 | `evolution/tools/tool_module.py`（新增 `enable_reasoning` 构造开关 + `self.reasoner`） |
| 输出目录 | `output/tools_reasoning/<ts>/`（与 `output/tools/` 物理隔离） |
| 默认门阈值 | full_regression_tolerance_pp=2.0，ambiguous_improvement_pp=3.0，latency_p95_budget_sec=5.0，reasoning_tokens_cap=200 |
| ambiguous 子集 | `len(example.confuser_tools) >= 2`（不新增字段） |
| 小样本保护 | ambiguous 子集 < 5 例时跳过 ambiguous 门，仍跑全集回归门 + latency 门 |

---

## 1. DSPy 机制深挖（Phase 15 特异）

### 1.1 dspy.Predict + 自定义 Signature 暴露给 GEPA

**结论：** `dspy.Predict(SignatureSubclass)` 暴露给 GEPA 的可优化文本是 `signature.instructions`（即 Signature class 的 docstring 或显式 `instructions=` kwarg）。

**证据：**
- Phase 13 ToolModule 已用同一机制把 per-param desc 暴露给 GEPA：[evolution/tools/tool_module.py:73-78](../../../evolution/tools/tool_module.py#L73)
  ```python
  desc_text = (p.description or "").strip()
  sig = dspy.Signature(
      "param_name -> confirmation",
      instructions=desc_text,
  )
  self.param_predictors[p.name] = dspy.Predict(sig)
  ```
  GEPA 通过 `named_predictors()` 递归发现这些 Predict，并在反思时把 `signature.instructions` 作为可变文本（参见 13-RESEARCH.md §"Sources Primary"）。
- DSPy 3.1.3 GEPA `compile()` 依赖 `student.named_predictors()` 收集所有可优化 Predict（13-RESEARCH.md cite: `.venv/lib/python3.13/site-packages/dspy/teleprompt/gepa/gepa.py:540, 558`）。
- `_format_available_tools()` 读出来的也是 `bundle.param_predictors[pn].signature.instructions`（[evolution/tools/tool_module.py:154](../../../evolution/tools/tool_module.py#L154)）——证明 instructions 即是 GEPA 可触达的文本载体。

**Phase 15 应用：** `ToolReasoningSignature` 是一个 `dspy.Signature` 子类，定义 `task_description, available_tools -> reasoning`。
其 docstring 写出推理模板的初始指令文本，GEPA 编译期会把整段 docstring 视为可变 `instructions` 字段（与 D-01/D-02 一致）。

```python
class ToolReasoningSignature(dspy.Signature):
    """Briefly reason about which tool best fits this task.
    Be concise (≤200 tokens). Mention what makes the candidate tools different
    in this context. Do NOT pre-select a tool — that is the selector's job.
    """
    task_description: str = dspy.InputField(desc="The task to accomplish")
    available_tools: str = dspy.InputField(desc="Formatted tools listing")
    reasoning: str = dspy.OutputField(desc="Short rationale, ≤200 tokens")
```

### 1.2 GEPA 单目标编译：只优化 reasoner，冻结 selector

**问题：** `student=ToolModule(enable_reasoning=True)` 暴露的 `named_predictors()` 包括：
- N×M 个 per-param Predict（来自 `_ToolParamBundle.param_predictors`，Phase 13 遗留）
- 1 个 `dspy.ChainOfThought` 内的 Predict（来自 `self.selector`）
- 1 个新增的 `dspy.Predict(ToolReasoningSignature)`（`self.reasoner`）

我们只想让 reasoner.instructions 变。

**结论：** DSPy 3.1.3 的 GEPA **没有 per-Predict 冻结开关**（[gepa.py 没有 `freeze_predictors` 参数](../../phases/13-per-parameter-description-optimization/13-RESEARCH.md)）。但 Phase 13 已遇到等价问题（要冻结 tool-level desc）并采用**物理隔离方案**：把不想优化的文本放在 `_frozen_tool_desc: dict[str, str]`（plain str dict，非 Predict），GEPA 的 `named_predictors()` 看不见它（[evolution/tools/tool_module.py:111](../../../evolution/tools/tool_module.py#L111)）。

**Phase 15 复用同一思路：**
- selector 仍是 `dspy.ChainOfThought(ToolSelectionWithParamsSignature)` —— 不能物理隔离（必须真正调用），所以**接受它进入 named_predictors()**。
- per-param Predict 同样接受。
- 后果：GEPA 会**同时**反思 selector / per-param / reasoner 的 instructions。

**关键决定（D-08 隐含）：** Phase 15 接受 GEPA 看见所有 Predict，但通过**初始化时 selector / per-param 已是 Phase 13 evolved 产物**避免回退：
- Phase 13 evolve 完后，per-param descriptions 已沉淀到 `output/tools/<ts>/evolved_descriptions.json`。
- Phase 15 CLI 应支持 `--baseline-run output/tools/<ts>` 读取已 evolved 的 ToolDescription，作为 baseline_module 起点（mirrors evolve_tool_params.py 的 `--baseline-run` 语义但用法更严格——这里读的是「上游已优化的 tool desc」而非「v1 baseline 历史」）。
- ⚠️ **planner 决策点：** 是否在 Phase 15 加载 Phase 13 evolved descriptions 作为起点？或是从 hermes-agent 源码原始 desc 起？两种都可，前者把 Phase 15 evolved instructions 与 Phase 13 evolved descriptions 一起测试（更接近线上行为），后者评估 reasoning 是否能独立救场（更纯净）。**推荐前者**——`--baseline-run` 读 Phase 13 输出，让 Phase 15 评估的是「reasoning 在 Phase 13 之上的增量」。

**实务：** 即使 GEPA 看见 selector / per-param Predict，在 reasoner-only 优化 budget（max_metric_calls 限制）下，reasoner 是**主参数**（其变化对 ambiguous 子集影响更大），GEPA 反思预算自然集中在 reasoner 上。我们**不**额外在 student 端做 `set_lm` / 屏蔽——那是过度设计，且 13-RESEARCH.md 已证 sub-Module 物理结构是可靠隔离手段。

### 1.3 reasoner LM `max_tokens=200` 配置

**问题：** D-04 要求传给 reasoner 的 LM 强制 `max_tokens=200`，**不**影响 selector 的 LM。

**结论：** DSPy 支持两条路径，**Phase 15 选 path B（context override at call time）**：

**Path A — `Predict.set_lm(lm)`（不推荐 Phase 15 用）。**
- DSPy 允许给特定 Predict 实例 attach 一个 LM 实例。
- 风险：从 `dspy.configure(lm=eval_lm, track_usage=True)` 引入的 track_usage 上下文未必跟随 set_lm 的 LM。`evolve_tool_params.py:765` 在全局 configure 后 GEPA 会复用全局 LM，set_lm 干扰这层契约的边界没明确文档支持。

**Path B — `with dspy.context(lm=reasoner_lm)`（推荐）。**
- Phase 13 与 v1 baseline gate 都用 `dspy.context(lm=lm)` 在 holdout 评估期切换 LM（[evolution/tools/evolve_tool_params.py:372](../../../evolution/tools/evolve_tool_params.py#L372)，[evolution/tools/v1_baseline_gate.py:184](../../../evolution/tools/v1_baseline_gate.py#L184)）。
- **但是** GEPA 编译是黑盒——它不在我们的 `dspy.context` 范围内调用 reasoner。

**最终方案 — Path C（混合，Phase 15 真实路径）：**
1. **构造期** 在 `ToolModule.__init__` 中创建 reasoner 时，预留一个**自有 LM**：
   ```python
   if enable_reasoning:
       reasoning_lm = dspy.LM(
           config.eval_model,
           max_tokens=200,
           **{k: v for k, v in config.get_lm_kwargs().items() if k != "max_tokens"}
       )
       self.reasoner = dspy.Predict(ToolReasoningSignature)
       self.reasoner.set_lm(reasoning_lm)  # per-Predict LM override
   ```
2. **forward 期**仍用全局 `dspy.context(lm=eval_lm)`：selector 走全局 LM；reasoner 因 `set_lm` 强制走自身 200-token-cap LM。
3. **GEPA 编译期** GEPA 反思每个 Predict 的 instructions 时，使用 reflection_lm（来自 dspy.GEPA 构造）；evaluator 路径调用 student.forward()，进入上面 forward 期的混合配置。

**可验证：** DSPy 3.1.3 `dspy.Predict` 有 `set_lm()` 和 `get_lm()` 方法（参见 .venv 源码 `dspy/primitives/program.py`，亦在 v1_baseline_gate 测试中常用）。

**冗余保险（D-04 双保险）：** Signature docstring 内显式写 `Be concise (≤200 tokens)`——即使 LM 配置漂移，模型也倾向遵循。

### 1.4 Latency + token usage 采样

**问题：** D-17 要求 think-on holdout 全集逐例计时，输出 p50/p95/mean 到 metrics.json。

**结论：** **包裹 forward()** 是最简方案。DSPy 的 `track_usage=True` 提供 cumulative usage（`dspy.settings.usage_tracker.get_total_tokens()`），**但不分 Predict 也不分 call**——它适合做整轮 cost 累加（`CostTracker` 走的就是这条路），不适合 per-call latency。

**推荐：** 在 `evolution/tools/think_metrics.py` 内提供独立 helper，包裹 module 调用：

```python
import time
from typing import Any

def sample_latency_tokens(
    module: Any,
    examples: list,
    lm: Any,
) -> dict:
    """Per-call latency + token usage sampling for think-on holdout.

    Returns:
        {
            "latency_seconds": [float, ...],     # one per example
            "reasoning_tokens": [int, ...],      # one per example (0 if reasoner None)
            "stats": {
                "latency_p50": float,
                "latency_p95": float,
                "latency_mean": float,
                "reasoning_token_p50": int,
                "reasoning_token_p95": int,
                "reasoning_token_mean": float,
            }
        }
    """
    import dspy

    latencies: list[float] = []
    rtokens: list[int] = []

    with dspy.context(lm=lm):
        for ex in examples:
            t0 = time.perf_counter()
            try:
                pred = module(task_description=ex.task_description)
            except Exception:
                # 与 _evaluate_holdout / _score_module_on_holdout 一致：跳过
                continue
            t1 = time.perf_counter()
            latencies.append(t1 - t0)
            # reasoning token: 取 reasoner 的 history 最后一条
            tokens = _extract_reasoner_tokens(module, pred)
            rtokens.append(tokens)

    return _compute_stats(latencies, rtokens)
```

**reasoner token 提取：** DSPy 的 `dspy.Prediction` 暴露 `_completions._completions` 与 LM `history` 列表。
两条路：
- **Path 1（recommended）：** 在 `ToolModule.forward()` 中把 reasoner 的 `_completions` 或 `usage` 字段附到返回的 `dspy.Prediction` 上，例如 `pred.reasoning_tokens = reasoner_response_tokens`。这样 latency sampler 不需要反向解析 LM history。
- **Path 2：** 读 `module.reasoner.lm.history[-1].usage` 的 `total_tokens` —— 实际可行（v1_baseline_gate 与 fitness.py 都有 LM 实例化历史），但跨 dspy 版本不稳。

**Phase 15 决定（planner pin）：** **Path 1**——`ToolModule.forward()` 在 think-on 路径上读 `reasoner_response.get_lm_usage()` 或 fallback 到 `len(reasoning_text)/4` 估算（character/4 ≈ token），然后通过 `dspy.Prediction(..., reasoning_tokens=N)` 附带返回。Latency sampler 直接读 `pred.reasoning_tokens`。
- ⚠️ Phase 15 planner 在 PLAN.md 内 pin：**不**新增 dspy 版本依赖，token 估算用 `len(reasoning_text)/4` 即可（200-token cap 保证误差不致破坏 ThinkABGate 决策；真要严谨，token 准确性是 Phase 16 dashboard 工作）。

### 1.5 GEPA 5-param metric signature（Pitfall 12 守门）

**已验证（13-RESEARCH.md）：** GEPA 3.1.3 metric 必须签名 `(gold, pred, trace, pred_name, pred_trace)`。
[evolution/tools/tool_metric.py:321-326](../../../evolution/tools/tool_metric.py#L321) 与 `joint_tool_param_metric_with_feedback`（同文件 365）已遵循。

**Phase 15 复用：** ThinkABGate **不是** GEPA metric——它是 post-compile 验证 gate。GEPA 的 metric 仍是 `joint_tool_param_metric_with_feedback`（reasoner 参数被反思时，使用 selection 准确率作为信号）。
- **planner 在 PLAN.md 内 pin：** Phase 15 不新增 GEPA-facing metric；ThinkABGate 仅在 holdout 评估完成后比较 think-on / think-off 分数。

---

## 2. 现有代码引用（file:line — VERIFIED）

| 用途 | 文件:行号 | 备注 |
|---|---|---|
| ToolModule 构造（要 patch enable_reasoning 进入此处）| [evolution/tools/tool_module.py:104-127](../../../evolution/tools/tool_module.py#L104) | 在 `super().__init__()` 后追加 reasoning 分支 |
| ToolModule.forward()（think-on/off 分叉点）| [evolution/tools/tool_module.py:162-184](../../../evolution/tools/tool_module.py#L162) | `forward()` 内 if `self.reasoner is not None: reasoning = self.reasoner(...)` 然后传给 selector |
| ToolSelectionWithParamsSignature（need新增 reasoning InputField）| [evolution/tools/tool_module.py:21-43](../../../evolution/tools/tool_module.py#L21) | think-on 路径需要 selector 看到 reasoning；可以 monkey-patch 或新建 ToolSelectionWithReasoningSignature 子类——⚠️ planner 决策点 |
| `_frozen_tool_desc` 物理隔离模式（参考）| [evolution/tools/tool_module.py:111](../../../evolution/tools/tool_module.py#L111) | Phase 15 不需要新隔离字段——reasoner 是可优化 Predict |
| Phase 13 CLI 流水线 16 步骨架 | [evolution/tools/evolve_tool_params.py:1-43](../../../evolution/tools/evolve_tool_params.py#L1) docstring + L552-1129 evolve()/_evolve_impl | Phase 15 CLI 复用此结构，替换 step 3, 11-14 |
| dry-run 早返分支 | [evolution/tools/evolve_tool_params.py:741-751](../../../evolution/tools/evolve_tool_params.py#L741) | 模式参考：echo 关键参数后 return 0 |
| FAILED_<ts>/ ABORTED_<ts>/ 写盘 | [evolution/tools/evolve_tool_params.py:432-546](../../../evolution/tools/evolve_tool_params.py#L432) | 命名约定与文件构成 |
| 输出 metrics.json + evolved_descriptions.json + diff.txt | [evolution/tools/evolve_tool_params.py:1085-1117](../../../evolution/tools/evolve_tool_params.py#L1085) | 模板；Phase 15 替换为 `reasoning_prompt.txt` + `ab_comparison.json` + `metrics.json` |
| V1BaselineGate 类（双 API 模式）| [evolution/tools/v1_baseline_gate.py:349-394](../../../evolution/tools/v1_baseline_gate.py#L349) | ThinkABGate **必须**复制此模板 |
| `check_v1_baseline_gate(...)` 函数 API | [evolution/tools/v1_baseline_gate.py:92-131](../../../evolution/tools/v1_baseline_gate.py#L92) | ThinkABGate 函数 API 形态参考 |
| `_compute_baseline_gate_metrics(...)` 计算函数 | [evolution/tools/v1_baseline_gate.py:52-86](../../../evolution/tools/v1_baseline_gate.py#L52) | 内部 dict 计算函数模板 |
| ConstraintResult 定义（passed/constraint_name/message/details）| [evolution/core/constraints.py:15-21](../../../evolution/core/constraints.py#L15) | 4 字段；details 是 `Optional[str]`（**不是 dict**——必须 json.dumps 后写入）|
| ConstraintResult 用法示例（v1 gate）| [evolution/tools/v1_baseline_gate.py:117-131](../../../evolution/tools/v1_baseline_gate.py#L117) | `details=json.dumps({...}, sort_keys=True)`——Phase 15 沿用 |
| `_check_size("param_description", 200)` | [evolution/core/constraints.py:101-103](../../../evolution/core/constraints.py#L101) | 200-char 上限来自 `EvolutionConfig.max_param_desc_size`；Phase 15 reasoning instructions **不**走此 gate（reasoning 是 prompt 文本，长度上限由 D-12 `--reasoning-tokens-cap` 即输出 token 控制，不由 instructions 字符数控制）|
| `EvolutionConfig.eval_model / optimizer_model / reflection_model / max_cost_usd` | [evolution/core/config.py:42-59](../../../evolution/core/config.py#L42) | Phase 15 不扩 config（D-15）|
| `joint_tool_param_metric` / `_with_feedback` | [evolution/tools/tool_metric.py:321-436](../../../evolution/tools/tool_metric.py#L321) | GEPA metric 复用，**不改**——reasoning 不影响 metric 形态 |
| ToolSelectionExample.confuser_tools | [evolution/tools/tool_dataset.py:55](../../../evolution/tools/tool_dataset.py#L55) | `field(default_factory=list)`——非 None，empty 列表合法 |
| `GenerateConfuserTasks` Signature（synthetic 路径写 confuser_tools）| [evolution/tools/tool_dataset.py:195-210](../../../evolution/tools/tool_dataset.py#L195) | confuser task 至少有 1 个 confuser；**注意：** synthetic 在 [tool_dataset.py:387](../../../evolution/tools/tool_dataset.py#L387) 写入 `confuser_tools=[other]` —— **只 1 个 confuser**！见 §3 |
| baseline 路径写 confuser_tools（来自 confuser_pairs）| [evolution/tools/tool_dataset.py:341](../../../evolution/tools/tool_dataset.py#L341) | `confuser_tools=task.get("confuser_tools", [])` —— LLM 自由生成，**0..N 都可能** |
| CostTracker / track_usage / max_cost_usd | [evolution/core/cost_tracker.py:1-343](../../../evolution/core/cost_tracker.py) | 直接复用，Phase 15 GEPA compile 必须 `with CostTracker(max_usd):` |
| dspy.context 模式（v1 gate / fitness）| [evolution/tools/v1_baseline_gate.py:184](../../../evolution/tools/v1_baseline_gate.py#L184)，[evolution/core/fitness.py:77](../../../evolution/core/fitness.py#L77) | 标准模式 |
| `dspy.configure(lm=lm, track_usage=True)` | [evolution/tools/evolve_tool_params.py:765](../../../evolution/tools/evolve_tool_params.py#L765) | Phase 15 CLI 必须沿用 |

---

## 3. confuser_tools 字段语义（D-13 校验）

### 3.1 ToolSelectionExample.confuser_tools 数据来源

数据集中的每个 `ToolSelectionExample` 由两条路径填 `confuser_tools`：

**Path 1 — 合成 baseline 任务（per-tool tasks）**
[evolution/tools/tool_dataset.py:336-343](../../../evolution/tools/tool_dataset.py#L336) — `GenerateToolTasks` Signature 让 LLM 在生成 task 时同时输出 `confuser_tools`。
LLM 可能输出 0/1/N 个 confuser，未保证。

**Path 2 — 合成 confuser pair 任务**
[evolution/tools/tool_dataset.py:380-390](../../../evolution/tools/tool_dataset.py#L380) — `GenerateConfuserTasks` 跑在 confuser pair (A,B) 上，写入 `confuser_tools=[other]` 即**只 1 个 confuser**。

**Path 3 — Phase 14 sessiondb 矿工**
未读 session_miner.py 全文，但 13-CONTEXT.md 与 14-CONTEXT.md 已声明 sessiondb 路径会沿用 ToolSelectionExample dataclass 同字段；**字段始终是 list 而非 None**（dataclass `field(default_factory=list)` 保证）。

### 3.2 D-13 阈值复审

CONTEXT.md D-13 写：「`len(example.confuser_tools) >= 2`（即 correct_tool 之外还有 ≥2 个合法候选 → 共 ≥3 合法候选）」。

**校验：**
- ToolSelectionExample.confuser_tools **不**包含 correct_tool（[tool_dataset.py:387](../../../evolution/tools/tool_dataset.py#L387) 写 `[other]`，明确不含 correct）。
- Path 2 单 confuser → `len == 1`，**被排除**于 ambiguous 子集（合理：仅 1 confuser 不够 ambiguous）。
- Path 1 由 LLM 自由决定，可能 0/1/2/3+。
- ⚠️ **数据集观察待 planner Wave 0 验证：** 用现有 `datasets/tools/holdout.jsonl` 跑一次 `len([ex for ex in holdout if len(ex.confuser_tools) >= 2])` 查实际 ambiguous 子集大小。如果 < 5（D-16 small-sample 阈值），ThinkABGate 会跳过 ambiguous 门——planner 应在 dry-run 报告中显式 echo 子集大小让用户提前知情。

### 3.3 confuser_tools 字段稳定性测试（Wave 0）

```python
# tests/tools/test_think_metrics.py
def test_ambiguous_subset_filter():
    examples = [
        ToolSelectionExample(task_description="a", correct_tool="t1", confuser_tools=[]),
        ToolSelectionExample(task_description="b", correct_tool="t1", confuser_tools=["t2"]),
        ToolSelectionExample(task_description="c", correct_tool="t1", confuser_tools=["t2", "t3"]),
        ToolSelectionExample(task_description="d", correct_tool="t1", confuser_tools=["t2", "t3", "t4"]),
    ]
    ambiguous = [ex for ex in examples if len(ex.confuser_tools) >= 2]
    assert len(ambiguous) == 2
    assert ambiguous[0].task_description == "c"
```

---

## 4. ConstraintResult 写入策略

**关键发现：** `ConstraintResult` 只有 4 个字段：
```python
@dataclass
class ConstraintResult:
    passed: bool
    constraint_name: str
    message: str
    details: Optional[str] = None  # ← Optional[str], 不是 dict
```
([evolution/core/constraints.py:15-21](../../../evolution/core/constraints.py#L15))

**v1 baseline gate 的做法**（Phase 15 复用）：
```python
details = json.dumps(
    {"delta": ..., "tolerance_pp": ..., "evolved_score": ..., "baseline_score": ...},
    sort_keys=True,
)
return ConstraintResult(passed=..., constraint_name="v1_baseline_gate",
                        message=..., details=details)
```

**Phase 15 ThinkABGate 写入：**
```python
details = json.dumps(
    {
        "full_regression_delta": full_regression_delta,
        "full_regression_tolerance_pp": full_regression_tolerance_pp,
        "ambiguous_delta": ambiguous_delta,
        "ambiguous_improvement_pp": ambiguous_improvement_pp,
        "latency_p95_seconds": latency_p95,
        "latency_p95_budget_sec": latency_p95_budget_sec,
        "ambiguous_sample_size": n_ambiguous,
        "ambiguous_gate_skipped": (n_ambiguous < 5),
        "gates": {
            "full_regression_gate_passed": ...,
            "ambiguous_gate_passed": ...,
            "latency_gate_passed": ...,
        },
    },
    sort_keys=True,
)
```

**额外 — metrics.json 写入：** ThinkABGate 同时把所有数字字段拍平展开到 `metrics.json` 里（参考 evolve_tool_params.py:1039-1043 的 `metrics["v1_baseline_*"]` 风格）。这是 D-11 metrics.json 字段表的来源。

**结论：** ConstraintResult 的 `details: str` 已足够；不扩字段，**不**改 dataclass 定义。

---

## 5. ThinkABGate 设计契约

### 5.1 双 API 形态（mirror v1_baseline_gate.py）

```python
# ── evolution/tools/think_metrics.py ──

DEFAULT_FULL_REGRESSION_TOLERANCE_PP = 2.0
DEFAULT_AMBIGUOUS_IMPROVEMENT_PP = 3.0
DEFAULT_LATENCY_P95_BUDGET_SEC = 5.0
AMBIGUOUS_SMALL_SAMPLE_THRESHOLD = 5  # D-16

# ── 内部计算 ──
def _compute_think_ab_metrics(
    *,
    think_on_holdout_score: float,
    think_off_holdout_score: float,
    ambiguous_think_on_score: float,
    ambiguous_think_off_score: float,
    ambiguous_sample_size: int,
    latency_p95_seconds: float,
    full_regression_tolerance_pp: float = DEFAULT_FULL_REGRESSION_TOLERANCE_PP,
    ambiguous_improvement_pp: float = DEFAULT_AMBIGUOUS_IMPROVEMENT_PP,
    latency_p95_budget_sec: float = DEFAULT_LATENCY_P95_BUDGET_SEC,
) -> dict:
    full_delta = round(think_on_holdout_score - think_off_holdout_score, 10)
    full_threshold = -(full_regression_tolerance_pp / 100.0)
    full_passed = full_delta >= full_threshold

    ambiguous_delta = round(ambiguous_think_on_score - ambiguous_think_off_score, 10)
    ambiguous_threshold = ambiguous_improvement_pp / 100.0
    ambiguous_skipped = ambiguous_sample_size < AMBIGUOUS_SMALL_SAMPLE_THRESHOLD
    ambiguous_passed = True if ambiguous_skipped else (ambiguous_delta >= ambiguous_threshold)

    latency_passed = latency_p95_seconds <= latency_p95_budget_sec

    all_passed = full_passed and ambiguous_passed and latency_passed
    # message 拼装如 v1_baseline_gate 风格 ...
    return {
        "passed": all_passed,
        "full_regression_delta": full_delta,
        "ambiguous_delta": ambiguous_delta,
        "ambiguous_sample_size": ambiguous_sample_size,
        "ambiguous_gate_skipped": ambiguous_skipped,
        "latency_p95_seconds": latency_p95_seconds,
        # tolerance 字段 ...
        "gates": {
            "full_regression_gate_passed": full_passed,
            "ambiguous_gate_passed": ambiguous_passed,
            "latency_gate_passed": latency_passed,
        },
        "message": "...",
    }


# ── 函数 API ──
def check_think_ab_gate(
    *,
    think_on_holdout_score: float,
    think_off_holdout_score: float,
    ambiguous_think_on_score: float,
    ambiguous_think_off_score: float,
    ambiguous_sample_size: int,
    latency_p95_seconds: float,
    full_regression_tolerance_pp: float = DEFAULT_FULL_REGRESSION_TOLERANCE_PP,
    ambiguous_improvement_pp: float = DEFAULT_AMBIGUOUS_IMPROVEMENT_PP,
    latency_p95_budget_sec: float = DEFAULT_LATENCY_P95_BUDGET_SEC,
) -> ConstraintResult:
    metrics = _compute_think_ab_metrics(...)  # 同 kwargs
    details = json.dumps(metrics, sort_keys=True, ensure_ascii=False)
    return ConstraintResult(
        passed=metrics["passed"],
        constraint_name="think_ab_gate",
        message=metrics["message"],
        details=details,
    )


# ── 类 API ──
class ThinkABGate:
    """Three-AND-gate validator for Phase 15 think-augmented selection."""

    def __init__(
        self,
        *,
        full_regression_tolerance_pp: float = DEFAULT_FULL_REGRESSION_TOLERANCE_PP,
        ambiguous_improvement_pp: float = DEFAULT_AMBIGUOUS_IMPROVEMENT_PP,
        latency_p95_budget_sec: float = DEFAULT_LATENCY_P95_BUDGET_SEC,
    ):
        self.full_regression_tolerance_pp = float(full_regression_tolerance_pp)
        self.ambiguous_improvement_pp = float(ambiguous_improvement_pp)
        self.latency_p95_budget_sec = float(latency_p95_budget_sec)

    def check(
        self,
        *,
        think_on_holdout_score: float,
        think_off_holdout_score: float,
        ambiguous_think_on_score: float,
        ambiguous_think_off_score: float,
        ambiguous_sample_size: int,
        latency_p95_seconds: float,
    ) -> dict:
        """Returns full metrics dict (shape matches _compute_think_ab_metrics)."""
        return _compute_think_ab_metrics(
            think_on_holdout_score=think_on_holdout_score,
            ...,
            full_regression_tolerance_pp=self.full_regression_tolerance_pp,
            ambiguous_improvement_pp=self.ambiguous_improvement_pp,
            latency_p95_budget_sec=self.latency_p95_budget_sec,
        )
```

### 5.2 与 V1BaselineGate 的对偶部署

CLI 流程：
```
score think-off (=baseline_evolved) on holdout    -> th_off_full, th_off_ambig, latency_off_p95
score think-on  (=evolved_evolved) on holdout     -> th_on_full,  th_on_ambig,  latency_on_p95

# Gate 1 — V1BaselineGate (复用 Phase 13)
v1_gate.check(evolved_score=th_off_full, baseline=v1_baseline_info)   # think-off vs Phase 5 v1
v1_gate.check(evolved_score=th_on_full,  baseline=v1_baseline_info)   # think-on  vs Phase 5 v1

# Gate 2 — ThinkABGate (Phase 15 新)
think_ab_gate.check(
    think_on_holdout_score=th_on_full,
    think_off_holdout_score=th_off_full,
    ambiguous_think_on_score=th_on_ambig,
    ambiguous_think_off_score=th_off_ambig,
    ambiguous_sample_size=n_ambiguous,
    latency_p95_seconds=latency_on_p95,
)
```

任一 gate FAILED 即写 `FAILED_<ts>/`（D-10）。

---

## 6. 输出目录与文件 schema

### 6.1 目录约定（mirror evolve_tool_params.py）

```
output/tools_reasoning/
    <YYYYMMDD_HHMMSS>/                  # SUCCESS
        metrics.json
        reasoning_prompt.txt              # evolved reasoning instructions (D-11)
        diff.txt                          # baseline reasoning instructions → evolved
        ab_comparison.json                # per-example think-off vs think-on
    FAILED_<YYYYMMDD_HHMMSS>/            # constraints / regression / v1 gate / think_ab gate
        metrics.json (status=...)
        reasoning_prompt.txt
        diff.txt
        ab_comparison.json (partial)
    ABORTED_<YYYYMMDD_HHMMSS>/           # cost cap exceeded
        aborted.json (CostTracker.write_aborted_json + reasoning fields)
        partial_diff.txt
```

时间戳格式：`datetime.now().strftime("%Y%m%d_%H%M%S")`（与 [evolve_tool_params.py:450](../../../evolution/tools/evolve_tool_params.py#L450) 一致）。

### 6.2 metrics.json schema（CONTEXT.md D-11 + 本研究补全）

```json
{
  "timestamp": "20260509_143022",
  "started_at": "2026-05-09T14:30:22+00:00",
  "status": "SUCCESS",
  "iterations": 10,
  "eval_model": "openai/gpt-4.1-mini",
  "optimizer_used": "gepa",
  "reflection_model": "openai/gpt-4.1",
  "cost_usd_spent": 7.81,
  "cost_usd_cap": 20.0,
  "tool_count": 17,
  "param_predictors_discovered": 87,
  "train_examples": 162,
  "val_examples": 81,
  "holdout_examples": 81,
  "ambiguous_subset_size": 14,
  "ambiguous_gate_skipped": false,
  "elapsed_seconds": 1837.4,

  "think_off_score": 0.748,
  "think_on_score": 0.762,
  "v1_score": 0.731,

  "ambiguous_think_on": 0.643,
  "ambiguous_think_off": 0.571,

  "reasoning_token_stats": {"p50": 92, "p95": 178, "mean": 108.3},
  "latency_stats":         {"p50": 1.87, "p95": 3.94, "mean": 2.13},

  "v1_baseline_holdout": 0.731,
  "v1_baseline_source": "historical",
  "v1_gate_delta_think_off": 0.017,
  "v1_gate_delta_think_on": 0.031,
  "v1_gate_passed": true,

  "think_ab_gate": {
    "passed": true,
    "full_regression_delta": 0.014,
    "ambiguous_delta": 0.072,
    "latency_p95_seconds": 3.94,
    "ambiguous_sample_size": 14,
    "ambiguous_gate_skipped": false,
    "tolerances": {
      "full_regression_tolerance_pp": 2.0,
      "ambiguous_improvement_pp": 3.0,
      "latency_p95_budget_sec": 5.0
    },
    "gates": {
      "full_regression_gate_passed": true,
      "ambiguous_gate_passed": true,
      "latency_gate_passed": true
    }
  }
}
```

### 6.3 ab_comparison.json schema（CONTEXT.md «Claude's Discretion» 此处 pin）

逐例 JSONL-like array，**每行一条** —— 实际写为 JSON array 以便 Phase 16 dashboard 直接 json.load：

```json
[
  {
    "task_id": 0,
    "task_description": "find all python files containing the word 'TODO'",
    "correct_tool": "grep",
    "selected_off": "find",
    "selected_on": "grep",
    "is_correct_off": false,
    "is_correct_on": true,
    "is_ambiguous": true,
    "confuser_tools": ["find", "ls", "rg"],
    "reasoning_text_on": "The task explicitly mentions searching for content...",
    "reasoning_tokens_on": 87,
    "latency_seconds_off": 1.21,
    "latency_seconds_on": 2.93
  },
  ...
]
```

字段约束：
- `task_id`: 整型递增（holdout 顺序索引），**不**复用 task_description hash（保留一致顺序便于人工 diff）
- `is_ambiguous`: `len(confuser_tools) >= 2`（D-13）
- `reasoning_text_on`: 完整字符串落盘（≤200 token，文件大小可控；hold ≈81 例 × 200 token ≈ 60KB max）
- `reasoning_tokens_on`: estimated `len(reasoning_text_on)/4` 或 LM usage actual（参 §1.4）
- `latency_seconds_*`: 必填两条（off 与 on 都计时，便于 dashboard 对比延迟差）

### 6.4 dry-run report schema（CONTEXT.md D-09 复用 evolve_tool_params 风格）

```
param_predictors_discovered=87
tools_in_scope=17
holdout_size=81
ambiguous_subset_size=14
ambiguous_gate_skipped=false (size >= 5)
reasoning_tokens_cap=200
latency_p95_budget_sec=5.0
ab_tolerance_pp=2.0
ambiguous_improvement_pp=3.0
full_regression_tolerance_pp=2.0
iterations_planned=10
eval_source=load
max_cost_usd_cap=20.0
max_metric_calls_estimate=4350    # iterations * max(50, 3 * num_predictors)
DRY RUN — setup validated.
```

CLI flag 表（D-12 + 复用）：

| Flag | 类型 | 默认 | 来源 |
|---|---|---|---|
| `--reasoning-tokens-cap` | int | 200 | D-12（新增）|
| `--ab-tolerance-pp` | float | 2.0 | D-12（新增）— mapped to `--full-regression-tolerance-pp` 别名 OK |
| `--ambiguous-improvement-pp` | float | 3.0 | D-15（新增）|
| `--latency-budget-sec` | float | 5.0 | D-12（新增）|
| `--ambiguous-only` | bool | False | D-12（新增）— 仅评估 ambiguous 子集，跳过全集；用于快速调参 |
| `--eval-source` | choice | "load" | 复用 evolve_tool_params |
| `--tools` | str | None | 复用 |
| `--dry-run` | bool | False | 复用 |
| `--max-cost-usd` | float | None→20.0 | 复用 |
| `--baseline-run` | str | None | 复用，但本 phase 用法是「读 Phase 13 evolved descriptions 作为起点」（参 §1.2）|
| `--reflection-model` | str | None | 复用 |
| `--iterations` | int | 10 | 复用 |
| `--auto` | choice | None | 复用 |
| `--allow-miprov2-fallback` | bool | False | 复用 |
| `--component-selector` | choice | "round_robin" | 复用 |

---

## 7. Wave 结构推荐（TDD-friendly）

> Wave 拆分由 planner 在 PLAN.md 里 pin。本节给推荐与依赖说明，planner 可调整。

**Wave 1 — Module + Signature 骨架**（`evolution/tools/tool_module.py` 改造 + 新 Signature）
- T1.1：新增 `ToolReasoningSignature` 类（dspy.Signature 子类）+ docstring 即初始 reasoning instructions
- T1.2：`ToolModule.__init__` 接受 `enable_reasoning: bool = False`（默认 False — 不破坏 Phase 13 行为）
- T1.3：`enable_reasoning=True` 时构造 `self.reasoner = dspy.Predict(ToolReasoningSignature)` 并 `set_lm(reasoning_lm)`（max_tokens=200）
- T1.4：扩展 selector 输入 — `ToolSelectionWithParamsSignature` 增加 optional `reasoning: str = dspy.InputField(default="")` 字段（**或** 新建 `ToolSelectionWithReasoningSignature` 子类。⚠️ planner 决策——推荐 default-empty 同 Signature，向后兼容）
- T1.5：`ToolModule.forward()` think-on 分支：先调 reasoner 拿 reasoning，再调 selector
- T1.6：返回 `dspy.Prediction(selected_tool=..., selected_params=..., reasoning=reasoning, reasoning_tokens=N)`
- **RED tests:** `test_enable_reasoning_constructs_reasoner`、`test_disable_reasoning_omits_reasoner`、`test_forward_off_unchanged_signature`、`test_forward_on_calls_reasoner_then_selector`、`test_reasoner_lm_max_tokens_200`
- **依赖：** 无 → Wave 2/3 不能并行

**Wave 2 — ThinkABGate（`evolution/tools/think_metrics.py` 新模块）**
- T2.1：模块级常量 `DEFAULT_FULL_REGRESSION_TOLERANCE_PP=2.0`、`DEFAULT_AMBIGUOUS_IMPROVEMENT_PP=3.0`、`DEFAULT_LATENCY_P95_BUDGET_SEC=5.0`、`AMBIGUOUS_SMALL_SAMPLE_THRESHOLD=5`
- T2.2：`_compute_think_ab_metrics(...)`（三重 AND + small-sample skip + ConstraintResult 兼容 dict）
- T2.3：`check_think_ab_gate(...)` 函数 API（返回 ConstraintResult）
- T2.4：`ThinkABGate` 类 API（`__init__` + `.check()`）
- T2.5：`sample_latency_tokens(module, examples, lm)` helper
- **RED tests:** `test_three_and_pass`、`test_full_regression_fails`、`test_ambiguous_below_3pp_fails`、`test_latency_p95_over_budget_fails`、`test_small_sample_skips_ambiguous`、`test_dual_api_consistency`、`test_constraint_result_shape`、`test_sample_latency_tokens_collects`
- **依赖：** 不依赖 Wave 1（用 mock module 测）→ **Wave 1 / Wave 2 可并行**

**Wave 3 — CLI（`evolution/tools/evolve_tool_reasoning.py`）**
- T3.1：Click command 骨架，flags 按 §6.4 表
- T3.2：`_evolve_impl()` 16 步流水线复刻 evolve_tool_params 但替换 step 3 / 11-14：
  - step 3: 构造 baseline_module（`enable_reasoning=False`）+ evolved_module（`enable_reasoning=True`）
  - step 12: `_evaluate_holdout` 跑两次（off / on），同时 sample latency
  - step 13: `V1BaselineGate.check()` 跑两次（v1 vs think-off, v1 vs think-on）
  - step 14（新）: `ThinkABGate.check()`
- T3.3：dry-run 早返（按 §6.4）
- T3.4：metrics.json + reasoning_prompt.txt + ab_comparison.json + diff.txt 写盘（`output/tools_reasoning/<ts>/`）
- T3.5：FAILED_<ts>/ 与 ABORTED_<ts>/ 路径
- **RED tests:** `test_dry_run_emits_setup`、`test_baseline_module_off_evolved_on_constructed`、`test_dual_v1_baseline_calls`、`test_think_ab_gate_failure_writes_failed`、`test_ab_comparison_json_per_example`、`test_reasoning_prompt_diff_format`、`test_cost_cap_aborts_to_aborted_dir`
- **依赖：** Wave 1（ToolModule.enable_reasoning）+ Wave 2（ThinkABGate）→ **Wave 3 ≻ Wave 1, Wave 2**

**Wave 4 — Integration smoke + docs**
- T4.1：integration smoke test：mock LM，运行 `evolve_tool_reasoning --iterations 1 --dry-run`，断言 stdout 包含 dry-run schema 字段
- T4.2：integration smoke test：mock LM + 100 examples 数据集，跑完整 pipeline，断言 metrics.json schema 完整
- T4.3：Wave 0 数据集观察：用 `datasets/tools/holdout.jsonl` 跑 `len([ex for ex in holdout if len(ex.confuser_tools) >= 2])`，echo 实际 ambiguous 子集大小（planner Wave 0 任务）
- T4.4：更新 `evolution/tools/__init__.py` 导出（如有）+ 文档 cross-link
- **依赖：** Wave 3

**Wave 0 prerequisites（在 Wave 1 之前，由 planner 决定是否单独 Wave）**
- 跑 `datasets/tools/holdout.jsonl` 子集大小检查（决定 ambiguous 门是否会跳过）
- `tests/tools/test_think_metrics.py` 与 `tests/tools/test_evolve_tool_reasoning.py` 文件骨架建立 + conftest 共享 mock LM fixture

---

## 8. Pitfall 4 守门（CONTEXT canonical_refs §先验经验）

`.planning/research/PITFALLS.md §Pitfall 4` 已锁三大风险：
1. **延迟膨胀** → §1.4 latency sampling + ThinkABGate latency_p95 ≤ 5.0s 守门
2. **CoT 偏航 / confabulation** → §1.3 reasoning 200-token cap + §5.1 ambiguous +3pp 净收益门（不是绝对收益门）
3. **selector 变橡皮图章** → §1.1 reasoner 仅输出 reasoning text，**不**输出 selected_tool；selector 仍接收完整 tools 列表（D-02）

**Pitfall 4 §"Prevention strategy"** 提到的 5 项：
1. cost & latency tracking → ✓ §6.2 metrics.json + §1.4 sampler
2. A/B 全集回归 + ambiguous 净收益 + latency budget → ✓ §5.1 三重 AND
3. reasoning 200-token cap → ✓ §1.3
4. **Hybrid 路由（runtime 决定 think/no-think）** → **延后**：CONTEXT.md D-05 拒绝 runtime mutator，归入 Phase 23+ deferred
5. Hard cost cap → ✓ §1 已通过 CostTracker 复用

---

## 9. 开放问题（planner 决策点）

按重要性递减排序：

1. **selector signature 是否新增 reasoning InputField**（Wave 1 T1.4）
   - 选项 A：扩展 `ToolSelectionWithParamsSignature`，加 `reasoning: str = dspy.InputField(default="")`（推荐——向后兼容，think-off 路径传 ""）
   - 选项 B：新建 `ToolSelectionWithReasoningSignature` 子类，think-on 路径用新 selector，think-off 路径继续用旧
   - **推荐 A** —— 避免双 selector 维护，default="" 让 GEPA 看到字段时 think-off 与 Phase 13 行为完全等价

2. **`--baseline-run` 语义**（CLI flag 复用 vs 新名）
   - 复用 evolve_tool_params 的 `--baseline-run` 但语义改变（Phase 13: v1 metrics.json；Phase 15: Phase 13 evolved_descriptions.json 起点）会增加 confusion
   - **推荐：** 新 CLI 把 `--baseline-run` 文档改成「Phase 13 output dir; loads evolved_descriptions.json as starting tool descriptions」；同时**保留** v1_baseline gate 行为（v1 score 来自 hard-coded 历史 / inline fallback，**不**来自 baseline_run）

3. **reasoning_tokens 估算 vs 精确**
   - §1.4 推荐 `len(reasoning_text)/4` 估算
   - 若 planner 想要精确（更靠谱的 ThinkABGate 数值），可在 ToolModule.forward() 内访问 `self.reasoner.lm.history[-1]` 拿到准确 token usage
   - **推荐：** 估算先行；Phase 16 dashboard 阶段再升级

4. **Wave 0 数据集 ambiguous 子集大小预检**
   - planner 应把 §7 Wave 0 prerequisites 中的 `len(ambig)` echo 加入 PLAN.md Wave 0 任务
   - 若 < 5：警告并建议先跑 `evolve_tool_params --eval-source synthetic --tools <subset>` 重新生成数据集
   - 或者考虑 Phase 14 sessiondb 注入（如果已有 14-output 可用）

---

## 10. Validation Architecture

### 10.1 Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest >=7.0` `[CITED: pyproject.toml:27]` |
| Config file | `pyproject.toml [tool.pytest.ini_options]` `[CITED: pyproject.toml:41-43]` (testpaths=["tests"], python_files=["test_*.py"]) |
| Quick run command | `/Users/slj/项目/hermes-agent-self-evolution/.venv/bin/python -m pytest tests/tools/ -x --tb=short` |
| Full suite command | `/Users/slj/项目/hermes-agent-self-evolution/.venv/bin/python -m pytest tests/ -v` |
| Estimated runtime | ~15-25s tests/tools/ subset；~60-90s 全集 |

### 10.2 Phase Requirements / Decisions → Test Map

| Req / D-ID | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| TOOL-V2-03 / SC-1 | `ToolModule(enable_reasoning=True)` 构造 `self.reasoner: dspy.Predict` | unit | `pytest tests/tools/test_tool_module.py::TestEnableReasoning::test_constructs_reasoner -x` | ❌ Wave 0 |
| TOOL-V2-03 / SC-1 | `ToolModule(enable_reasoning=False)` 不构造 reasoner（`self.reasoner is None` or attr absent） | unit | `pytest tests/tools/test_tool_module.py::TestEnableReasoning::test_disabled_reasoner_absent -x` | ❌ Wave 0 |
| TOOL-V2-03 / SC-1 | think-off 路径 forward() 调 selector 不调 reasoner | unit (mock) | `pytest tests/tools/test_tool_module.py::TestEnableReasoning::test_off_path_no_reasoner_call -x` | ❌ Wave 0 |
| TOOL-V2-03 / SC-1 | think-on 路径 forward() 先调 reasoner 后调 selector，selector 接收 reasoning | unit (mock) | `pytest tests/tools/test_tool_module.py::TestEnableReasoning::test_on_path_reasoner_first -x` | ❌ Wave 0 |
| D-04 | reasoner 的 LM `max_tokens == 200` | unit | `pytest tests/tools/test_tool_module.py::TestEnableReasoning::test_reasoner_lm_max_tokens_200 -x` | ❌ Wave 0 |
| TOOL-V2-03 / SC-2 | `ToolModule(enable_reasoning=True).named_predictors()` 包含 reasoner，路径暴露 instructions 给 GEPA | unit | `pytest tests/tools/test_tool_module.py::TestEnableReasoning::test_reasoner_in_named_predictors -x` | ❌ Wave 0 |
| D-13 | ambiguous 子集筛选: `len(ex.confuser_tools) >= 2` | unit | `pytest tests/tools/test_think_metrics.py::TestAmbiguousFilter::test_filter_correct -x` | ❌ Wave 0 |
| D-14 / 三重门 | think_on full ≥ think_off full - 2pp 时 full_regression_gate_passed | unit | `pytest tests/tools/test_think_metrics.py::TestThreeGate::test_full_regression_within -x` | ❌ Wave 0 |
| D-14 / 三重门 | ambiguous_on - ambiguous_off ≥ 3pp 时 ambiguous_gate_passed | unit | `pytest tests/tools/test_think_metrics.py::TestThreeGate::test_ambiguous_improves -x` | ❌ Wave 0 |
| D-14 / 三重门 | latency_p95 ≤ 5.0s 时 latency_gate_passed | unit | `pytest tests/tools/test_think_metrics.py::TestThreeGate::test_latency_within -x` | ❌ Wave 0 |
| D-14 / 三重门 | 三 AND：任一 fail → passed=False | unit (parametric) | `pytest tests/tools/test_think_metrics.py::TestThreeGate::test_three_and_logic -x` | ❌ Wave 0 |
| D-16 / small sample | ambiguous_sample_size < 5 → ambiguous_gate_skipped=True，不影响 passed | unit | `pytest tests/tools/test_think_metrics.py::TestThreeGate::test_small_sample_skip -x` | ❌ Wave 0 |
| ThinkABGate 双 API | check_think_ab_gate() 返回 ConstraintResult，details 是 sort_keys json | unit | `pytest tests/tools/test_think_metrics.py::TestDualAPI::test_function_returns_constraint_result -x` | ❌ Wave 0 |
| ThinkABGate 双 API | ThinkABGate.check() 返回完整 metrics dict | unit | `pytest tests/tools/test_think_metrics.py::TestDualAPI::test_class_returns_dict -x` | ❌ Wave 0 |
| D-17 / latency sampler | sample_latency_tokens 返回 stats 含 p50 / p95 / mean | unit (mock module) | `pytest tests/tools/test_think_metrics.py::TestSampler::test_emits_p50_p95_mean -x` | ❌ Wave 0 |
| D-09 / CLI | `python -m evolution.tools.evolve_tool_reasoning --dry-run` 退出 0 + echo dry-run schema | integration (mock LM) | `pytest tests/tools/test_evolve_tool_reasoning.py::test_dry_run_emits_setup -x` | ❌ Wave 0 |
| D-10 / dual gate | think_ab_gate FAILED → 写 FAILED_<ts>/ + 退出码 1 | integration (mock LM) | `pytest tests/tools/test_evolve_tool_reasoning.py::test_think_ab_failed_writes_failed_dir -x` | ❌ Wave 0 |
| D-10 / dual gate | v1_baseline FAILED (think-on) → 写 FAILED_<ts>/ + 退出码 1 | integration (mock LM) | `pytest tests/tools/test_evolve_tool_reasoning.py::test_v1_failed_think_on_writes_failed_dir -x` | ❌ Wave 0 |
| D-11 / output | metrics.json 含 think_on_score / think_off_score / ambiguous_* / reasoning_token_stats / latency_stats / think_ab_gate | integration | `pytest tests/tools/test_evolve_tool_reasoning.py::test_metrics_json_schema -x` | ❌ Wave 0 |
| D-11 / output | reasoning_prompt.txt 是 evolved instructions（plain string）；diff.txt 是 unified diff | integration | `pytest tests/tools/test_evolve_tool_reasoning.py::test_reasoning_prompt_files -x` | ❌ Wave 0 |
| D-11 / output | ab_comparison.json 逐例含 task_id / selected_off / selected_on / is_ambiguous / reasoning_text_on / latency_seconds_* | integration | `pytest tests/tools/test_evolve_tool_reasoning.py::test_ab_comparison_schema -x` | ❌ Wave 0 |
| D-11 / output | output 在 `output/tools_reasoning/<ts>/` 而**非** `output/tools/` | integration | `pytest tests/tools/test_evolve_tool_reasoning.py::test_output_isolated_directory -x` | ❌ Wave 0 |
| Cost cap | cost > max_cost_usd 触发 ABORTED_<ts>/ + 退出码 2 | integration (mock + injected usage) | `pytest tests/tools/test_evolve_tool_reasoning.py::test_cost_cap_aborts -x` | ❌ Wave 0 |
| GEPA 5-param sig | think_metrics 内**任何** GEPA-facing metric（如有）必须 5-param signature | unit | `pytest tests/tools/test_think_metrics.py::test_no_gepa_metric_added -x`（守门测试，断言 think_metrics.py **不**新增 GEPA-bound metric）| ❌ Wave 0 |

### 10.3 Sampling Rate

- **Per task commit:** `pytest tests/tools/ -x --tb=short`（Phase 15 新增测试集中在 `tests/tools/test_think_metrics.py` + `tests/tools/test_evolve_tool_reasoning.py` + 现有 `test_tool_module.py` 扩展）
- **Per wave merge:** `pytest tests/ -v`（确保 Phase 13/14 全集仍绿，新增 +20 ~ +30 测试）
- **Phase gate:** 全集通过 + 一次 `python -m evolution.tools.evolve_tool_reasoning --iterations 1 --dry-run` 真 dry-run 不报错；若有 API key，一次 `--iterations 1 --max-cost-usd 2.0` 真 E2E（至少跑出 metrics.json schema 且 think_ab_gate.passed 真假任一即合格——本测试只验流水线，不验性能）

### 10.4 Wave 0 Gaps

- [ ] `tests/tools/test_tool_module.py` — 扩展：`TestEnableReasoning` 5-7 项（discovery / off-path / on-path / max_tokens / signature）
- [ ] `tests/tools/test_think_metrics.py` — **NEW** 模块（~15-20 测试，覆盖三重门 / small-sample / 双 API / sampler）
- [ ] `tests/tools/test_evolve_tool_reasoning.py` — **NEW** integration（~10-12 测试，覆盖 dry-run / 双 gate / FAILED_ / ABORTED_ / metrics.json schema / ab_comparison.json schema）
- [ ] `tests/tools/conftest.py` — 可能需 `mock_reasoning_module` fixture（构造 `ToolModule(enable_reasoning=True)` with mock LM）
- [ ] dataset 子集大小预检脚本：可作为 `tests/tools/test_dataset_ambiguous_size.py` 跑一次实际 holdout 检查（输出 warning 而非 fail）

*（现有 test framework 已到位；无需 framework install。Phase 13/14 已验证 pytest baseline。）*

### 10.5 Phase Gate Sign-Off

- [ ] 所有 Wave 0 列出测试通过
- [ ] dry-run 在新 CLI 上退出 0
- [ ] (可选) E2E 真 LM 运行至少一次产出有效 metrics.json
- [ ] `nyquist_compliant: true` 设入 VALIDATION.md frontmatter

---

## 11. Sources

### Primary (HIGH confidence — direct file reads)

- [evolution/tools/tool_module.py](../../../evolution/tools/tool_module.py) — ToolModule 全文（1-233 行），构造、forward、`_frozen_tool_desc`、`_format_available_tools` 全验证
- [evolution/tools/evolve_tool_params.py](../../../evolution/tools/evolve_tool_params.py) — Phase 13 CLI 全文（1-1133 行），16 步流水线、dry-run、FAILED_/ABORTED_、metrics.json schema、CostTracker 集成
- [evolution/tools/v1_baseline_gate.py](../../../evolution/tools/v1_baseline_gate.py) — V1BaselineGate 全文（1-394 行），双 API (函数 + 类) 模板，`_compute_baseline_gate_metrics` 内部计算函数模板，ConstraintResult 写入风格
- [evolution/tools/tool_dataset.py](../../../evolution/tools/tool_dataset.py) — ToolSelectionExample 字段（1-441 行），confuser_tools 写入路径（synthetic baseline 与 confuser pair）
- [evolution/core/constraints.py](../../../evolution/core/constraints.py) — ConstraintResult dataclass 4 字段（1-21 行），`_check_size("param_description")` 200-char 上限（95-117 行）
- [evolution/tools/tool_metric.py](../../../evolution/tools/tool_metric.py) — joint_tool_param_metric / `_with_feedback` 5-param 签名（321-436 行），CrossToolRegressionChecker、persist_per_tool_rates
- [evolution/core/cost_tracker.py](../../../evolution/core/cost_tracker.py) — CostTracker 全文（1-343 行），track_usage、estimate_cost_usd、CostBudgetExceeded、write_aborted_json
- [evolution/core/config.py](../../../evolution/core/config.py) — EvolutionConfig 字段（41-59 行），eval_model / optimizer_model / reflection_model / max_cost_usd / max_param_desc_size / max_tool_desc_size
- [.planning/phases/13-per-parameter-description-optimization/13-RESEARCH.md](../13-per-parameter-description-optimization/13-RESEARCH.md) — DSPy 3.1.3 GEPA 5-param sig、reflection_lm、named_predictors 递归规则、track_usage 默认 False、Validation Architecture 模板
- [.planning/phases/15-think-augmented-tool-selection/15-CONTEXT.md](./15-CONTEXT.md) — 17 条锁定决策 D-01..D-17
- [.planning/research/PITFALLS.md §Pitfall 4](../../research/PITFALLS.md) — Phase 15 三大守门指引（latency / CoT confabulation / selector rubber-stamp）
- [.planning/REQUIREMENTS.md](../../REQUIREMENTS.md) — TOOL-V2-03（line 74）

### Secondary (MEDIUM confidence — pattern transfer)

- DSPy 3.1.3 `Predict.set_lm()` API（推断自 13-RESEARCH.md sources，`.venv/lib/python3.13/site-packages/dspy/primitives/program.py`）
- DSPy 3.1.3 `dspy.context(lm=lm)` 在 fitness.py / v1_baseline_gate.py / evolve_tool_params.py 多处使用，pattern 稳定
- DSPy 3.1.3 `Signature` docstring 即 GEPA-mutable instructions —— 推断自 Phase 13 _ToolParamBundle 的 `dspy.Signature(... instructions=desc_text)` 构造方式与 GEPA `named_predictors()` 通过 instructions 字段反思的契约（13-RESEARCH.md HIGH 已 cite gepa.py:540, 558）

### Tertiary (LOW confidence — TBD by planner / Wave 0)

- ambiguous 子集实际大小（`len(holdout where len(confuser_tools) >= 2)`）—— 取决于现有 `datasets/tools/holdout.jsonl` 内容，需 Wave 0 实测
- reasoning token 估算 `len(text)/4` 与真实 token 的偏差幅度 —— 200-token cap 下偏差应 ≤ 30 token，对 ThinkABGate latency/cost 计算不致失真，但 Phase 16 dashboard 可能希望精确数

### Out-of-scope（明确不研究的内容）

- DSPy GEPA 跨版本变化（Phase 13 已锁 3.1.3）
- LM provider-specific token counting（OpenAI / OpenRouter / Anthropic 差异）
- hermes-agent 仓库的 reasoning prompt 历史/演变（hermes-agent 端无 reasoning 模块，零先例）

---

## Metadata

**Confidence breakdown:**
- DSPy 3.1.3 mechanics（Predict.instructions / set_lm / context / GEPA named_predictors）: HIGH（Phase 13 已实证）
- ToolModule.forward 改造与 Signature 扩展: HIGH（代码读完，改造点明确）
- ThinkABGate 双 API 形态: HIGH（v1_baseline_gate 是直接模板）
- ConstraintResult 写入策略: HIGH（dataclass 字段读完）
- ambiguous 子集语义稳定性: MEDIUM-HIGH（dataclass `default_factory=list` 保证 list 而非 None；synthetic 写入路径已验证；sessiondb 路径需 Phase 14 PLAN 校核）
- ab_comparison.json field 命名: MEDIUM（CONTEXT.md 把命名让给 planner；本研究 §6.3 给推荐 schema 但 planner 可微调）
- reasoning_token 估算精度: MEDIUM（粗估 `len/4` 工作良好，精确度待 Phase 16 dashboard 实测验证）
- Wave 拆分: MEDIUM（结构合理，planner 可调）

**Research date:** 2026-05-09
**Valid until:** 2026-06-09 (30 天 — DSPy 3.1.3 与本仓库 Phase 13/14 已稳定，核心契约不会突变)

---

## RESEARCH COMPLETE
