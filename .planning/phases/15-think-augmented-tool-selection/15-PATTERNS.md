# Phase 15 — Patterns Map

**Generated:** 2026-05-09
**Source references:** [15-RESEARCH.md §2](./15-RESEARCH.md) (code refs table)、[15-CONTEXT.md](./15-CONTEXT.md) (D-01..D-17)

> 对每个新建或修改的文件，给出**最近的现有代码模板**与简短 pattern excerpt。Planner 应让新文件严格沿用引用文件的结构惯例。本文件不重新设计——只把 RESEARCH.md 已验证的 file:line 与片段固化到「per-target-file」视角。

| # | 路径 | 角色 | 最近模板 |
|---|---|---|---|
| 1 | `evolution/tools/tool_module.py` | MODIFIED | 自身（局部扩展）|
| 2 | `evolution/tools/think_metrics.py` | NEW | `evolution/tools/v1_baseline_gate.py` |
| 3 | `evolution/tools/evolve_tool_reasoning.py` | NEW | `evolution/tools/evolve_tool_params.py` |
| 4 | `tests/tools/test_think_metrics.py` | NEW | `tests/tools/test_v1_baseline_gate.py` |
| 5 | `tests/tools/test_evolve_tool_reasoning.py` | NEW | `tests/tools/test_evolve_tool_params_cli.py` |
| 6 | `tests/tools/test_dataset_ambiguous_size.py` | NEW | `tests/tools/test_tool_dataset.py`（observation-only）|
| 7 | `tests/tools/test_tool_module.py` | MODIFIED | 自身 + `test_tool_module_per_param.py` 风格 |
| 8 | `tests/tools/conftest.py` | NEW（项目当前无）| `tests/conftest.py` |

---

## 1. `evolution/tools/tool_module.py` (MODIFIED)

**Role:** 引入 `enable_reasoning: bool = False` 构造开关；构造期分支 `self.reasoner: dspy.Predict | None`；`forward()` 增加 think-on 路径；新增 `ToolReasoningSignature`；扩展 `ToolSelectionWithParamsSignature` 增 `reasoning: str = dspy.InputField(default="")`。

**Closest analog:** 自身——在现有构造函数 + forward + Signature 段内做局部扩展，**不**新建 sub-Module。

**Pattern excerpt — 构造期 `__init__`（[tool_module.py:104-127](../../../evolution/tools/tool_module.py#L104)）：**

```python
def __init__(self, tool_descriptions: list[ToolDescription]):
    super().__init__()
    self.tools: dict[str, _ToolParamBundle] = {}
    self._frozen_tool_desc: dict[str, str] = {}
    self._frozen_tools: dict[str, ToolDescription] = {}
    self._tool_names: list[str] = []
    for td in tool_descriptions:
        safe_name = self._safe_key(td.name)
        self.tools[safe_name] = _ToolParamBundle(td.name, list(td.params))
        self._frozen_tool_desc[td.name] = (td.description or f"Tool: {td.name}")
        self._frozen_tools[td.name] = td
        self._tool_names.append(td.name)
    # Selector: ChainOfThought with upgraded signature (D-05).
    self.selector = dspy.ChainOfThought(ToolSelectionWithParamsSignature)
```

**Pattern excerpt — forward 现状（[tool_module.py:162-184](../../../evolution/tools/tool_module.py#L162)）：**

```python
def forward(self, task_description: str) -> dspy.Prediction:
    available_tools = self._format_available_tools()
    result = self.selector(
        task_description=task_description,
        available_tools=available_tools,
    )
    selected_params = getattr(result, "selected_params", "") or "{}"
    return dspy.Prediction(
        selected_tool=result.selected_tool,
        selected_params=selected_params,
    )
```

**Pattern excerpt — Signature 风格（[tool_module.py:21-43](../../../evolution/tools/tool_module.py#L21)）：** 顶层 docstring 即 GEPA-mutable instructions，字段用 `dspy.InputField/OutputField(desc=...)`。`ToolReasoningSignature` 与新 `reasoning` InputField 必须严格沿用此格式。

**Deviations from analog:**
- 构造函数签名增 `enable_reasoning: bool = False`（D-05/D-07，构造后**不可变**）。
- `super().__init__()` 后追加分支：`self.reasoner = None`；当 `enable_reasoning=True`：构造 reasoning-专用 `dspy.LM(eval_model, max_tokens=200, ...)` → `self.reasoner = dspy.Predict(ToolReasoningSignature)` → `self.reasoner.set_lm(reasoning_lm)`（D-04，参 RESEARCH §1.3 Path C）。
- 新增 `class ToolReasoningSignature(dspy.Signature)`：`task_description, available_tools -> reasoning`，docstring 内显式写 "Be concise (≤200 tokens). Do NOT pre-select a tool"（200-token 双保险，RESEARCH §1.1）。
- 扩展 `ToolSelectionWithParamsSignature` 增 `reasoning: str = dspy.InputField(default="", desc="Optional pre-reasoning from think-on path; '' on think-off path")`（RESEARCH §9 开放问题 1 推荐选项 A——向后兼容）。
- `forward()` 在 think-on 分支：先 `reasoning_pred = self.reasoner(task_description=..., available_tools=...)` → `reasoning_text = reasoning_pred.reasoning` → 把 `reasoning=reasoning_text` 作为额外 kwarg 传给 `self.selector(...)`；think-off 分支传 `reasoning=""`。
- 返回 `dspy.Prediction(..., reasoning=reasoning_text, reasoning_tokens=int(len(reasoning_text)/4))`（RESEARCH §1.4 Path 1，token 估算 `len/4`）。
- 物理隔离原则不变：`_frozen_tool_desc` 不动；reasoner 是新的 **可优化** Predict，故**应当**进入 `named_predictors()` —— 与 Phase 13 物理隔离思路相反（D-08 / RESEARCH §1.2）。

---

## 2. `evolution/tools/think_metrics.py` (NEW)

**Role:** 模块级常量 + `_compute_think_ab_metrics` 内部计算 + `check_think_ab_gate` 函数 API（返回 `ConstraintResult`）+ `ThinkABGate` 类 API（返回 dict）+ `sample_latency_tokens(module, examples, lm)` helper。**不**新增 GEPA-facing metric（RESEARCH §1.5 / §10.2 守门测试）。

**Closest analog:** `evolution/tools/v1_baseline_gate.py`——双 API（函数式 + 类式）模板。

**Pattern excerpt — 内部计算函数（[v1_baseline_gate.py:52-86](../../../evolution/tools/v1_baseline_gate.py#L52)）：**

```python
def _compute_baseline_gate_metrics(evolved_score, baseline_score, tolerance=0.02) -> dict:
    delta = round(float(evolved_score) - float(baseline_score), 10)
    threshold = -float(tolerance)
    passed = delta >= threshold
    if passed:
        message = f"v1 baseline gate OK: evolved={evolved_score:.4f} ..."
    else:
        message = f"v1 baseline gate FAILED: evolved={evolved_score:.4f} regressed by {abs(delta):.4f} ..."
    return {
        "passed": passed, "delta": delta, "tolerance_pp": float(tolerance),
        "evolved_score": float(evolved_score), "baseline_score": float(baseline_score),
        "message": message,
    }
```

**Pattern excerpt — 函数 API + ConstraintResult 写入（[v1_baseline_gate.py:92-131](../../../evolution/tools/v1_baseline_gate.py#L92)）：**

```python
def check_v1_baseline_gate(evolved_score, baseline_score, tolerance=0.02) -> ConstraintResult:
    metrics = _compute_baseline_gate_metrics(evolved_score=..., baseline_score=..., tolerance=...)
    details = json.dumps({
        "delta": metrics["delta"], "tolerance_pp": metrics["tolerance_pp"],
        "evolved_score": metrics["evolved_score"], "baseline_score": metrics["baseline_score"],
    }, sort_keys=True)
    return ConstraintResult(
        passed=metrics["passed"],
        constraint_name="v1_baseline_gate",
        message=metrics["message"],
        details=details,
    )
```

**Pattern excerpt — 类 API（[v1_baseline_gate.py:349-394](../../../evolution/tools/v1_baseline_gate.py#L349)）：**

```python
class V1BaselineGate:
    def __init__(self, tolerance: float = 0.02):
        self.tolerance = float(tolerance)
    def check(self, *, evolved_score: float, baseline: dict) -> dict:
        metrics = _compute_baseline_gate_metrics(
            evolved_score=evolved_score,
            baseline_score=float(baseline["v1_baseline_holdout"]),
            tolerance=self.tolerance,
        )
        return {**baseline, **metrics}
```

**Deviations from analog:**
- **三重 AND 门** 取代单 delta gate：full_regression / ambiguous_improvement / latency_p95 三条件全 PASS 才 `passed=True`（D-14、RESEARCH §5.1）。
- 模块级常量：`DEFAULT_FULL_REGRESSION_TOLERANCE_PP=2.0`、`DEFAULT_AMBIGUOUS_IMPROVEMENT_PP=3.0`、`DEFAULT_LATENCY_P95_BUDGET_SEC=5.0`、`AMBIGUOUS_SMALL_SAMPLE_THRESHOLD=5`（D-15、D-16）。
- `_compute_think_ab_metrics(...)` 的 kwargs：`think_on_holdout_score`、`think_off_holdout_score`、`ambiguous_think_on_score`、`ambiguous_think_off_score`、`ambiguous_sample_size`、`latency_p95_seconds`、三个 tolerance kwargs（参 RESEARCH §5.1 详细签名）。
- ambiguous_sample_size < 5 时 `ambiguous_gate_skipped=True`，门 2 视为 PASS；全集 + latency 仍正常判（D-16）。
- `details` json 字段含 `gates: {full_regression_gate_passed, ambiguous_gate_passed, latency_gate_passed}` 子对象（RESEARCH §4）；`constraint_name="think_ab_gate"`。
- 类签名：`ThinkABGate(*, full_regression_tolerance_pp, ambiguous_improvement_pp, latency_p95_budget_sec)`；`.check(...)` 返回**完整 metrics dict**（保持与 V1BaselineGate.check 语义对称）。
- 新增 `sample_latency_tokens(module, examples, lm) -> dict` helper（RESEARCH §1.4），用 `time.perf_counter()` 包裹 `module(task_description=ex.task_description)`，统计 `latency_p50/p95/mean` + `reasoning_token_p50/p95/mean`；在 `dspy.context(lm=lm)` 内调用；逐例 try/except 跳过失败（与 `_score_module_on_holdout` 一致，参 [v1_baseline_gate.py:184](../../../evolution/tools/v1_baseline_gate.py#L184)）。
- **不** import `evolution.tools.tool_metric.joint_tool_param_metric` 到此模块（gate 是后置验证，不是 GEPA metric）。

---

## 3. `evolution/tools/evolve_tool_reasoning.py` (NEW)

**Role:** 新 CLI `python -m evolution.tools.evolve_tool_reasoning`，16 步流水线复刻 Phase 13 CLI，替换 step 3 / 11-14：构造 think-off baseline + think-on evolved 两个 ToolModule；holdout 双跑；同时跑 `V1BaselineGate` 与 `ThinkABGate`；输出到 `output/tools_reasoning/<ts>/`。

**Closest analog:** `evolution/tools/evolve_tool_params.py`（1133 行，THE template）。

**Pattern excerpt — dry-run 早返（[evolve_tool_params.py:741-751](../../../evolution/tools/evolve_tool_params.py#L741)）：**

```python
if dry_run:
    click.echo(f"param_predictors_discovered={num_predictors}")
    click.echo(f"tools_in_scope={len(all_tools)}")
    click.echo(f"iterations_planned={iterations}")
    click.echo(f"eval_source={eval_source}")
    click.echo(f"max_cost_usd_cap={config.max_cost_usd}")
    budget_estimate = iterations * max(50, 3 * num_predictors)
    click.echo(f"max_metric_calls_estimate={budget_estimate}")
    console.print("[bold green]DRY RUN — setup validated.[/bold green]")
    return 0
```

**Pattern excerpt — FAILED_ 目录写盘（[evolve_tool_params.py:432-463](../../../evolution/tools/evolve_tool_params.py#L432)）：**

```python
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
out_dir = Path("output") / "tools" / f"FAILED_{ts}"
out_dir.mkdir(parents=True, exist_ok=True)
metrics.setdefault("status", reason)
(out_dir / "metrics.json").write_text(
    json.dumps(metrics, indent=2, ensure_ascii=False),
    encoding="utf-8",
)
```

**Pattern excerpt — SUCCESS 目录写盘（[evolve_tool_params.py:1085-1117](../../../evolution/tools/evolve_tool_params.py#L1085)）：**

```python
ts = metrics["timestamp"]
out_dir = Path("output") / "tools" / ts
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / "evolved_descriptions.json").write_text(json.dumps(payload, indent=2, ...))
(out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2, ...))
(out_dir / "diff.txt").write_text(_generate_param_diff(original_tools, evolved_tools))
```

**Pattern excerpt — LM 配置（[evolve_tool_params.py:764-765](../../../evolution/tools/evolve_tool_params.py#L764)）：**

```python
lm = dspy.LM(config.eval_model, **config.get_lm_kwargs())
dspy.configure(lm=lm, track_usage=True)
```

**Deviations from analog:**
- **替换 step 3：** 构造**两个** ToolModule：`baseline_module = ToolModule(all_tools, enable_reasoning=False)`、`evolved_module = ToolModule(all_tools, enable_reasoning=True)`（D-07）。GEPA `compile(student=evolved_module, ...)`——只 evolve think-on 实例。
- **替换 step 11-12：** holdout 评估**跑两次**：（1）think-off baseline 用 `_score_module_on_holdout(baseline_module, holdout, lm)` 拿 `th_off_full`；（2）think-on evolved 用同函数拿 `th_on_full`；同时调 `sample_latency_tokens(evolved_module, holdout, lm)` 得 `latency_stats` + `reasoning_token_stats`。Ambiguous 子集 = `[ex for ex in holdout if len(ex.confuser_tools) >= 2]`（D-13），对子集再调一次拿 `th_off_ambig` / `th_on_ambig`。
- **替换 step 13-14：** 跑**两道门**：`V1BaselineGate.check(evolved_score=th_off_full, baseline=v1_info)` + `V1BaselineGate.check(evolved_score=th_on_full, baseline=v1_info)`；然后 `ThinkABGate.check(...)`。**任一** gate FAILED 即 `_write_failed_dir(...)` 并 `return 1`（D-10）。
- **输出目录变更：** 所有 `Path("output") / "tools"` 替换为 `Path("output") / "tools_reasoning"`（D-11）。
- **输出文件变更：** `evolved_descriptions.json` 不写（不进化 description）；改写 `reasoning_prompt.txt`（含 evolved reasoner `signature.instructions`）+ `ab_comparison.json`（逐例 think_off/on，schema 见 RESEARCH §6.3）+ `diff.txt`（baseline→evolved reasoning instructions 的 unified diff）+ `metrics.json`（schema 见 RESEARCH §6.2）。
- **新增 4 个 CLI flag**（RESEARCH §6.4 表）：`--reasoning-tokens-cap`（int, 默认 200）、`--ab-tolerance-pp`（float, 默认 2.0，又名 `--full-regression-tolerance-pp`）、`--ambiguous-improvement-pp`（float, 默认 3.0）、`--latency-budget-sec`（float, 默认 5.0）、`--ambiguous-only`（bool, 默认 False，限定只评估 ambiguous 子集）。
- **复用 Phase 13 flag：** `--eval-source`、`--tools`、`--dry-run`、`--max-cost-usd`、`--baseline-run`（**语义变更：** 读 Phase 13 evolved_descriptions.json 作为 tool desc 起点，参 RESEARCH §9 开放问题 2）、`--reflection-model`、`--iterations`、`--auto`、`--allow-miprov2-fallback`、`--component-selector`。
- **dry-run 输出补充字段**（参 RESEARCH §6.4）：`ambiguous_subset_size`、`ambiguous_gate_skipped`、`reasoning_tokens_cap`、`latency_p95_budget_sec`、`ab_tolerance_pp`、`ambiguous_improvement_pp`、`full_regression_tolerance_pp`、`max_metric_calls_estimate`。
- **CostTracker 流程不变：** `with CostTracker(max_usd=config.max_cost_usd):` 包裹 GEPA compile；`CostBudgetExceeded` → `ABORTED_<ts>/`（D-10、参 `evolve_tool_params._write_aborted_dir`）。
- **复用而非重写：** `from evolution.tools.v1_baseline_gate import V1BaselineGate, compute_v1_baseline`、`from evolution.tools.tool_metric import joint_tool_param_metric_with_feedback as gepa_metric`、`from evolution.core.cost_tracker import CostTracker, CostBudgetExceeded`、`from evolution.tools.think_metrics import ThinkABGate, sample_latency_tokens`。
- Rich console 用法不变：`console = Console()`、`Panel`、`Table` 沿用 `evolve_tool_params.py` 风格。

---

## 4. `tests/tools/test_think_metrics.py` (NEW)

**Role:** ~15-20 单元测试覆盖三重门、small-sample 跳过、双 API 一致性、latency sampler。

**Closest analog:** `tests/tools/test_v1_baseline_gate.py`（Wave 0 RED 风格、`ConstraintResult` 断言模式、`MagicMock` 用法）。

**Pattern excerpt（[test_v1_baseline_gate.py:10-37](../../../tests/tools/test_v1_baseline_gate.py#L10)）：**

```python
def test_regression_fails_run():
    pytest.importorskip("dspy")
    from evolution.tools.evolve_tool_params import check_v1_baseline_gate
    from evolution.core.constraints import ConstraintResult

    result = check_v1_baseline_gate(evolved_score=0.70, baseline_score=0.75, tolerance=0.02)

    assert isinstance(result, ConstraintResult), f"Expected ConstraintResult, got {type(result)}"
    assert result.passed is False, f"Expected passed=False ..., got passed={result.passed}"
    msg_lower = result.message.lower()
    assert "2pp" in msg_lower or "regression" in msg_lower, f"...got: {result.message!r}"
```

**Deviations from analog:**
- 测试类按 RESEARCH §10.2 测试映射表分组：
  - `TestAmbiguousFilter`：1 项——`len(confuser_tools) >= 2` 过滤（参 RESEARCH §3.3 示例代码已给出）
  - `TestThreeGate`：4-6 项——`test_full_regression_within` / `test_ambiguous_improves` / `test_latency_within` / `test_three_and_logic`（parametrize 8 个 truth-table 行）/ `test_small_sample_skip`
  - `TestDualAPI`：2 项——`test_function_returns_constraint_result`（断 `isinstance(..., ConstraintResult)`、`details` 是合法 sort_keys json）+ `test_class_returns_dict`（断 dict 含全部 metrics 字段）
  - `TestSampler`：2-3 项——`test_emits_p50_p95_mean`（mock module 返回带 `reasoning_tokens` 的 Prediction，断 stats 字段齐全）+ `test_sampler_skips_failed_calls`（一例 raise，sampler 不中断）
  - `TestGuard`：1 项——`test_no_gepa_metric_added`（断 think_metrics 模块**不**导出 GEPA 5-param 签名函数，RESEARCH §10.2）。
- 全部用 `pytest.importorskip("dspy")` 守头（参 v1_baseline_gate 测试）。
- mock 模式：`from unittest.mock import MagicMock`，构造 `ToolSelectionExample` 与 mock `module(task_description=...)` 返回 `dspy.Prediction(selected_tool="t1", reasoning="...", reasoning_tokens=42)`。
- 浮点比较：`abs(a - b) < 1e-9` 或直接用 `pytest.approx(..., abs=1e-9)`（与 v1 gate 测试一致）。

---

## 5. `tests/tools/test_evolve_tool_reasoning.py` (NEW)

**Role:** ~10-12 集成测试，mock LM + mock GEPA，覆盖 dry-run、双门失败路径、metrics.json / ab_comparison.json schema 断言、输出目录隔离、cost cap 流转。

**Closest analog:** `tests/tools/test_evolve_tool_params_cli.py`（Click CliRunner 模式、`patch("...dspy.GEPA")` mock GEPA、`mock_gepa.return_value.compile.side_effect=...` 触发失败路径）。

**Pattern excerpt — Click CLI test scaffold（[test_evolve_tool_params_cli.py:29-78](../../../tests/tools/test_evolve_tool_params_cli.py#L29)）：**

```python
pytest.importorskip("dspy")
import dspy
from click.testing import CliRunner
from unittest.mock import patch
evolve_mod = pytest.importorskip("evolution.tools.evolve_tool_params")
evolve = getattr(evolve_mod, "evolve", None)
...
with patch("evolution.tools.evolve_tool_params._load_tool_descriptions", return_value=[fake_tool]), \
     patch("evolution.tools.evolve_tool_params._load_dataset", return_value=(fake_ds, fake_ds, fake_ds)), \
     patch("evolution.tools.evolve_tool_params.dspy.GEPA") as mock_gepa, \
     patch("evolution.tools.evolve_tool_params.dspy.LM"):
    mock_gepa.return_value.compile.side_effect = RuntimeError("gepa blew up")
    runner = CliRunner()
    result = runner.invoke(evolve, [...flags...], catch_exceptions=True)
```

**Deviations from analog:**
- 测试目标 import 全部指向 `evolution.tools.evolve_tool_reasoning`（不是 `evolve_tool_params`）。
- 测试集（RESEARCH §10.2 后半部 + §10.4 Wave 0 Gaps）：
  - `test_dry_run_emits_setup`：`--dry-run` 退出 0；stdout 含 `ambiguous_subset_size=`、`ambiguous_gate_skipped=`、`reasoning_tokens_cap=200`、`latency_p95_budget_sec=5.0`、`max_metric_calls_estimate=`。
  - `test_baseline_module_off_evolved_on_constructed`：patch `ToolModule.__init__` 计数器，断 CLI 构造 2 次 ToolModule，且 `enable_reasoning` kwargs 一次 False 一次 True。
  - `test_dual_v1_baseline_calls`：patch `V1BaselineGate.check`，断被调 2 次（一次 think-off, 一次 think-on）。
  - `test_think_ab_gate_failure_writes_failed`：patch `ThinkABGate.check` 返回 `{"passed": False, ...}` → 断输出目录是 `output/tools_reasoning/FAILED_<ts>/`、退出码 `1`、`metrics.json["status"] == "THINK_AB_FAILED"`。
  - `test_v1_failed_think_on_writes_failed_dir`：think-on v1 gate fail → FAILED dir。
  - `test_metrics_json_schema`：成功路径下，`metrics.json` 含 `think_on_score` / `think_off_score` / `ambiguous_think_on` / `ambiguous_think_off` / `reasoning_token_stats` / `latency_stats` / `think_ab_gate` / `v1_gate_passed` 全部字段（RESEARCH §6.2 schema 严格断言）。
  - `test_ab_comparison_schema`：`ab_comparison.json` 是 JSON array，每条含 `task_id` / `task_description` / `correct_tool` / `selected_off` / `selected_on` / `is_correct_off` / `is_correct_on` / `is_ambiguous` / `reasoning_text_on` / `reasoning_tokens_on` / `latency_seconds_off` / `latency_seconds_on`（RESEARCH §6.3）。
  - `test_reasoning_prompt_files`：`reasoning_prompt.txt` 是 evolved `ToolReasoningSignature.instructions` 字符串；`diff.txt` 是 unified diff 格式（baseline instructions → evolved instructions）。
  - `test_output_isolated_directory`：所有写盘路径必须以 `output/tools_reasoning/` 起头，**绝不**触达 `output/tools/`。
  - `test_cost_cap_aborts`：通过 `_injected_usage` 或 patch `CostTracker.poll` 模拟 cost > cap → 断 `output/tools_reasoning/ABORTED_<ts>/aborted.json` 存在且退出码 `2`。

---

## 6. `tests/tools/test_dataset_ambiguous_size.py` (NEW, observation-only)

**Role:** Wave 0 non-gating observation test：echo 真实 `datasets/tools/holdout.jsonl` 中 `len([ex for ex in holdout if len(ex.confuser_tools) >= 2])`；输出 warning 而非 fail（RESEARCH §10.4）。

**Closest analog:** `tests/tools/test_tool_dataset.py`（项目中现有最接近的数据集观察测试）。无完美对应，定位为 **observation script + assert size >= 0**。

**Pattern excerpt — 推荐实现：**

```python
"""Wave 0 observation: ambiguous subset size in current holdout.

Not a strict gate. Logs a warning if size < AMBIGUOUS_SMALL_SAMPLE_THRESHOLD (5)
so the planner knows ThinkABGate's ambiguous gate will be skipped at runtime.
"""
import json
import warnings
from pathlib import Path

import pytest


def test_holdout_ambiguous_subset_size():
    holdout_path = Path("datasets/tools/holdout.jsonl")
    if not holdout_path.exists():
        pytest.skip(f"holdout dataset not present: {holdout_path}")

    examples = [json.loads(line) for line in holdout_path.read_text().splitlines() if line.strip()]
    ambiguous = [ex for ex in examples if len(ex.get("confuser_tools", [])) >= 2]
    n = len(ambiguous)
    print(f"holdout_total={len(examples)} ambiguous_subset_size={n}")
    if n < 5:
        warnings.warn(
            f"Ambiguous subset has only {n} examples (< 5 small-sample threshold). "
            f"ThinkABGate will skip the ambiguous-improvement gate at runtime (D-16).",
            UserWarning,
        )
    assert n >= 0  # always passes — observation only
```

**Deviations:** 非 gating；本质是「数据集探针」。日志输出（`print()` 或 `warnings.warn(...)`）供 planner 在 Wave 0 决定是否需要重新生成数据集（参 RESEARCH §9 开放问题 4）。文件存在则跳过；故 CI 上若无 holdout 数据也不报错。

---

## 7. `tests/tools/test_tool_module.py` (MODIFIED)

**Role:** 在现有文件**追加** `TestEnableReasoning` 测试类，6-7 项覆盖：构造分支、forward 双路径、reasoner LM max_tokens=200、`named_predictors()` 包含 reasoner（D-04/D-05/D-07，RESEARCH §10.2 上半部）。

**Closest analog:** 自身现有 `test_tool_module.py` + `test_tool_module_per_param.py`（同样 Wave 0 RED 风格）。

**Pattern excerpt — 现有 fixture 模式（[test_tool_module_per_param.py:19-52](../../../tests/tools/test_tool_module_per_param.py#L19)）：**

```python
def _make_3x3_tools() -> list[ToolDescription]:
    return [
        ToolDescription(
            name="search_files",
            file_path=Path("/fake/search.py"),
            description="Search files by pattern",
            params=[
                ToolParam(name="pattern", type="string", required=True, description="Search regex pattern"),
                ...
            ],
        ),
        ...
    ]
```

**Deviations from analog:**
- 新增测试类 `TestEnableReasoning`，全部使用 `_make_tool_descriptions()` 现有 fixture。
- 7 个推荐测试（RESEARCH §10.2）：
  - `test_constructs_reasoner`：`ToolModule(tools, enable_reasoning=True).reasoner` 是 `dspy.Predict` 实例；其 `signature` 是 `ToolReasoningSignature`。
  - `test_disabled_reasoner_absent`：`ToolModule(tools, enable_reasoning=False).reasoner is None`（或 `hasattr` 检查）。
  - `test_off_path_no_reasoner_call`：mock LM；`enable_reasoning=False`，调 `forward(task_description="t")`，断 reasoner 未被调用、`Prediction.reasoning == ""`。
  - `test_on_path_reasoner_first`：mock LM；`enable_reasoning=True`，调 `forward(...)`；断 reasoner 在 selector 之前被调用，且 selector 入参 `reasoning != ""`。
  - `test_reasoner_lm_max_tokens_200`：断 `module.reasoner.get_lm().kwargs.get("max_tokens") == 200`（或等价 attr）。
  - `test_reasoner_in_named_predictors`：断 `dict(module.named_predictors()).get("reasoner")` 非 None；`signature.instructions` 与 `ToolReasoningSignature.__doc__` 等价。
  - `test_default_enable_reasoning_is_false`：构造不传 kwarg 时 `reasoner is None`——保持 Phase 13 行为完全等价（向后兼容守门）。
- 所有 mock：`with patch("evolution.tools.tool_module.dspy.LM")` + `patch.object(module.selector, "__call__")`；返回 `dspy.Prediction(selected_tool="t1", selected_params="{}")` / `dspy.Prediction(reasoning="...")`。

---

## 8. `tests/tools/conftest.py` (NEW)

**Role:** 提供 `mock_reasoning_module` fixture——构造 `ToolModule(enable_reasoning=True)` with mock LM，供 `test_think_metrics.py` / `test_evolve_tool_reasoning.py` 共用。

**Closest analog:** `tests/conftest.py`（项目 conftest 仅在 `tests/` 根目录存在；`tests/tools/conftest.py` 当前**不存在** —— Wave 0 需要新建）。

**Pattern excerpt — 推荐 fixture：**

```python
"""Phase 15 shared fixtures for tests/tools/.

Created Wave 0 to support test_think_metrics.py and test_evolve_tool_reasoning.py.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import dspy
import pytest

from evolution.tools.tool_loader import ToolDescription, ToolParam


@pytest.fixture
def fake_tools() -> list[ToolDescription]:
    return [
        ToolDescription(
            name="search",
            file_path=Path("/fake/search.py"),
            description="Search for stuff",
            params=[ToolParam(name="q", type="string", required=True, description="query")],
        ),
    ]


@pytest.fixture
def mock_reasoning_module(fake_tools):
    """ToolModule(enable_reasoning=True) with mocked LMs (zero real API calls)."""
    from evolution.tools.tool_module import ToolModule
    with patch("evolution.tools.tool_module.dspy.LM") as mock_lm_cls:
        mock_lm_cls.return_value = MagicMock()
        module = ToolModule(fake_tools, enable_reasoning=True)
    # Optionally inject a mock selector / reasoner call
    module.selector = MagicMock(return_value=dspy.Prediction(
        selected_tool="search", selected_params="{}", reasoning="(mock)",
    ))
    module.reasoner = MagicMock(return_value=dspy.Prediction(reasoning="(mock reasoning)"))
    return module
```

**Deviations:** 项目当前无 `tests/tools/conftest.py`——本文件**全新建立**。fixture 命名 `mock_reasoning_module`（与 RESEARCH §10.4 一致），使用 `unittest.mock.patch` + `MagicMock` 屏蔽真实 LM；`pytest.fixture` 装饰；与 `tests/conftest.py` 风格保持一致（snake_case、显式 import dspy with `pytest.importorskip` 兼容性）。如担心 `dspy.LM` patch 副作用，可加 `pytest.importorskip("dspy")` 在模块顶部。

---

## PATTERN MAPPING COMPLETE

**Files classified:** 8 (3 new module files + 4 new test files + 1 modified module + 1 modified test，与 RESEARCH §0 / §7 一致)
**Analogs found:** 8 / 8 (全部命中现有最近模板)

### Key Patterns Identified
- **双 API 形态 (函数 + 类)**：所有 gate 模块（`v1_baseline_gate` → `think_metrics`）沿用 `_compute_*_metrics()` 内部函数 + `check_*(...)` 函数 API（返回 `ConstraintResult`）+ `*Gate` 类 API（返回 dict）的三层结构。
- **物理隔离 vs 显式暴露**：Phase 13 `_frozen_tool_desc` 把不想优化的文本物理隔离（不入 named_predictors）；Phase 15 反向利用——reasoner **应当**进入 named_predictors 让 GEPA 可优化其 instructions。两个机制并存不冲突。
- **CLI 流水线骨架可拷贝**：`evolve_tool_params.py` 16 步流水线 + dry-run 早返 + FAILED_/ABORTED_/SUCCESS 三种输出目录 + CostTracker 包裹 GEPA compile —— Phase 15 CLI 只换 step 3/11-14 与输出根目录。
- **测试 RED-first 风格**：所有新测试用 `pytest.importorskip("dspy")` 守头、`patch("module.path.dspy.LM")` 屏蔽真实 API、`from click.testing import CliRunner` 跑 CLI、`ConstraintResult` 与字段 schema 直接断言；无需 framework 安装。

### File Created
`/Users/slj/项目/hermes-agent-self-evolution/.planning/phases/15-think-augmented-tool-selection/15-PATTERNS.md`

### Ready for Planning
Pattern mapping 完成。Planner 在 PLAN.md 中针对每个目标文件 cite 此文档对应小节，并将 pattern excerpt 直接复制到 Wave action 的 "实现指引" 段。
