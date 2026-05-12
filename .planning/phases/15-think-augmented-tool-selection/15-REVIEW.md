---
phase: 15-think-augmented-tool-selection
reviewed: 2026-05-12T00:00:00Z
depth: standard
files_reviewed: 11
files_reviewed_list:
  - evolution/core/cost_tracker.py
  - evolution/tools/evolve_tool_reasoning.py
  - evolution/tools/think_metrics.py
  - evolution/tools/tool_dataset.py
  - evolution/tools/tool_module.py
  - tests/tools/conftest.py
  - tests/tools/test_dataset_ambiguous_size.py
  - tests/tools/test_evolve_tool_reasoning.py
  - tests/tools/test_think_metrics.py
  - tests/tools/test_tool_dataset.py
  - tests/tools/test_tool_module.py
findings:
  critical: 4
  warning: 9
  info: 6
  total: 19
status: issues_found
---

# Phase 15: Code Review Report

**Reviewed:** 2026-05-12
**Depth:** standard
**Files Reviewed:** 11
**Status:** issues_found

## Summary

Phase 15 引入 think-augmented tool selection 管道(双 ToolModule、ThinkABGate 三 AND 门、latency/token 采样)。整体架构与 Phase 13 风格一致,门控逻辑与契约清晰,测试覆盖广。

但审查发现 **4 个 BLOCKER 级别缺陷**会在生产路径上产生不正确的指标或误导性的"通过":

1. **`_build_ab_comparison` 的 latency 索引错配**:`sample_latency_tokens` 跳过失败示例后,`latencies_on[i]` 不再对应 `holdout[i]`,导致 ab_comparison.json 的 `latency_seconds_on` 标签错位(并且 p95 latency 进入 ThinkABGate 时与示例不再对齐)。
2. **V1BaselineGate 在缺省 baseline_run 时假装通过**:`v1_baseline_holdout=0.0`,任何 `evolved_score >= -tolerance` 都通过,但 `v1_gate_passed=True` 会写入 metrics.json,操作员无法察觉门退化。
3. **`ambiguous_only` 模式下两个门的数学冗余**:`eval_holdout=ambiguous_subset` 时 `th_off_full == th_off_ambig`、`th_on_full == th_on_ambig`,full_regression 与 ambiguous improvement 退化为同一信号,three-AND 门事实上变成 two-AND。
4. **`cost_tracker.estimate_cost_usd` 的 NaN guard 不捕获 inf**:`lm_usd != lm_usd` 只检 NaN;`inf + 任何值 = inf`,不触发 fallback,导致 spent_usd=inf,`exceeded()` 立即返回 True 中止所有运行。

另有 9 个 WARNING(包括 dry-run 静默吞掉数据集错误、reasoning_tokens 估算用 `len/4` 不可靠、`_load_dataset` 异常路径下 `final_spent_usd=0` 等)。

---

## Critical Issues

### CR-01: `_build_ab_comparison` 的 latency 索引错配 — 全 holdout 的 latency 标签都可能错位

**File:** `evolution/tools/evolve_tool_reasoning.py:759-761`
**Issue:**
```python
latencies_on: list[float] = sampling.get("latency_seconds", [])
...
"latency_seconds_on": (
    round(latencies_on[i], 4) if i < len(latencies_on) else 0.0
),
```
`sample_latency_tokens`(`think_metrics.py:349-354`)在 `module(...)` 抛异常时 `continue`,**不追加** latency 占位。所以 `latencies_on` 的长度 ≤ `len(holdout)`,且**索引不再对应原 holdout 索引**:如果第 3 个示例失败,那么 `latencies_on[3]` 实际是 holdout[4] 的延迟。所有 i>=失败索引 的 `latency_seconds_on` 在 `ab_comparison.json` 中标签错位。

更严重的是,这个 `latencies_on` 是从同一个 `sampling["stats"]["latency_p95"]` 派生的 — `latency_p95` 在跳过失败示例后仍以"成功示例数"为分母计算 percentile,**ThinkABGate 的 latency 门用的是无效样本** (混入失败示例后 p95 系统性偏低)。这两个 bug 共生:静默丢弃异常 + 用错位的 latency 进入指标 + 写入磁盘。

**Fix:**
让 `sample_latency_tokens` 在异常路径写入哨兵值(NaN 或 None),保持索引对齐:
```python
# think_metrics.py
for ex in examples:
    ...
    t0 = time.perf_counter()
    try:
        pred = module(task_description=task)
        t1 = time.perf_counter()
        latencies.append(t1 - t0)
        tokens = int(getattr(pred, "reasoning_tokens", 0) or 0)
        rtokens.append(tokens)
    except Exception:
        # Preserve index alignment with `examples`.
        latencies.append(float("nan"))
        rtokens.append(0)
```
然后在 `evolve_tool_reasoning._build_ab_comparison` 内对 NaN 显式处理:
```python
lat_on = latencies_on[i] if i < len(latencies_on) else 0.0
if isinstance(lat_on, float) and lat_on != lat_on:  # NaN
    lat_on = 0.0
```
并在 `_percentile` 计算前过滤 NaN(否则 sort 行为依赖 Python 版本)。

---

### CR-02: V1BaselineGate 在缺省 baseline_run 时 silently no-op,但 metrics.json 报 PASS

**File:** `evolution/tools/evolve_tool_reasoning.py:482-485`
**Issue:**
```python
v1_info = compute_v1_baseline(baseline_run=baseline_run)
v1_gate = V1BaselineGate(tolerance=ab_tolerance_pp / 100.0)
v1_off_metrics = v1_gate.check(evolved_score=th_off_full, baseline=v1_info)
v1_on_metrics = v1_gate.check(evolved_score=th_on_full, baseline=v1_info)
```
当 `baseline_run=None`(CLI 默认),`compute_v1_baseline` 走 `'missing'` 分支返回 `v1_baseline_holdout=0.0`。`V1BaselineGate.check` 比较 `evolved_score >= 0.0 - tolerance`(`-0.02`),**任何 ≥ 0 的分数都通过**。但 `metrics["v1_gate_passed"]` 仍写 `True`,日志、面板、metrics.json 都显示"PASS"。

操作员看到 V1_OFF/V1_ON 都 PASS 时,理性预期是"对比历史 baseline 没退化",但实际只是"评估到了非负分数"。注释(line 476-481)说门退化是有意为之,但 metrics.json **没有任何字段标注此次 V1 gate 实际未执行**。`v1_baseline_source='missing'` 是字段表里的子项,容易被忽略。

**Fix:**
1. 在 `compute_v1_baseline` 返回 `'missing'` 时,将 `v1_gate_passed` 显式写成 `None`(或 `"SKIPPED"` 字符串),不要混入 `True/False`:
```python
v1_gate_skipped = v1_info.get("v1_baseline_source") == "missing"
metrics["v1_gate_passed"] = None if v1_gate_skipped else (
    bool(_gate_passed(v1_off_metrics)) and bool(_gate_passed(v1_on_metrics))
)
metrics["v1_gate_skipped"] = v1_gate_skipped
```
2. 在 console 面板里区分 `PASS / FAIL / SKIPPED`,避免视觉欺骗。

---

### CR-03: `--ambiguous-only` 模式下 ThinkABGate 退化为 two-AND(full_regression 与 ambiguous 重复信号)

**File:** `evolution/tools/evolve_tool_reasoning.py:464-468`
**Issue:**
```python
eval_holdout = ambiguous_subset if ambiguous_only else holdout
th_off_full = _safe_score(baseline_module, eval_holdout, lm)
th_on_full = _safe_score(optimized_module, eval_holdout, lm)
th_off_ambig = _safe_score(baseline_module, ambiguous_subset, lm)
th_on_ambig = _safe_score(optimized_module, ambiguous_subset, lm)
```
当 `ambiguous_only=True`,`eval_holdout == ambiguous_subset`,因此 `th_off_full == th_off_ambig`、`th_on_full == th_on_ambig`,送入 ThinkABGate 的 `full_regression_delta == ambiguous_delta`。

D-14.1(full regression 容差 2pp)与 D-14.2(ambiguous improvement +3pp)合成一个矛盾约束:要求 `delta >= -0.02` 且 `delta >= +0.03`,后者隐含前者。**门从 three-AND 退化为 two-AND**(只剩 ambiguous + latency 实际工作)。

更糟的是 metrics.json 的 `think_off_score` 字段会写 ambiguous_only 跑出来的分数,而 `v1_baseline_holdout` 是完整 holdout 上算出的(若 historical)——比较失去意义。

**Fix:**
要么禁止 `--ambiguous-only` 与 ThinkABGate 共用:
```python
if ambiguous_only:
    # Skip full_regression gate; warn + only enforce ambiguous + latency.
    think_gate = ThinkABGate(
        full_regression_tolerance_pp=1e9,  # effectively disable
        ambiguous_improvement_pp=ambiguous_improvement_pp,
        latency_p95_budget_sec=latency_budget_sec,
    )
    console.print("[yellow]--ambiguous-only — full_regression gate disabled.[/yellow]")
```
要么始终在完整 holdout 上算 `th_*_full`,只让 sampling/ab_comparison/eval_holdout 局限到 ambiguous_subset:
```python
th_off_full = _safe_score(baseline_module, holdout, lm)  # always full
th_on_full = _safe_score(optimized_module, holdout, lm)
```

---

### CR-04: `cost_tracker.estimate_cost_usd` 的 NaN guard 不捕获 inf,会让 spent_usd=inf

**File:** `evolution/core/cost_tracker.py:106-108`
**Issue:**
```python
lm_usd = float(prompt_cost) + float(completion_cost)
if lm_usd != lm_usd:  # NaN guard
    raise ValueError("NaN cost")
```
`lm_usd != lm_usd` 只对 NaN 为 True,对 `float('inf')` 是 False。若 `litellm.cost_per_token` 返回 inf(例如 model 名称未知导致内部除零、或新模型表里有 placeholder),`lm_usd=inf` 会通过 guard,直接累加到 `total_usd`,最终 `tracker.spent_usd=inf`,`exceeded()` 立刻 True,中止所有 GEPA 运行(即使 max_usd 设得很高)。

**Fix:**
```python
import math
...
if not math.isfinite(lm_usd):
    raise ValueError(f"non-finite cost: {lm_usd}")
```
`math.isfinite` 同时排除 NaN 与 ±inf。同时考虑增加对 `prompt_cost < 0` 的检查 —— litellm 偶尔返回负值(token 计数为 0 时的 placeholder)。

---

## Warnings

### WR-01: dry-run 静默吞掉 `_load_dataset` 异常,违反 dry-run 验证契约

**File:** `evolution/tools/evolve_tool_reasoning.py:319-325`
**Issue:**
```python
if dry_run:
    try:
        trainset, valset, holdout = _load_dataset(
            eval_source, config, all_tools, session_source=session_source
        )
    except Exception:
        trainset, valset, holdout = [], [], []
```
dry-run 的目的是"验证设置而不真正跑"。但当 `_load_dataset` 抛错(数据集文件损坏、session_source 路径错、外部 importer 失败),dry-run 会**静默继续**并 echo `ambiguous_subset_size=0`、`ambiguous_gate_skipped=true`、`holdout_size=0`,exit 0。操作员无法从 dry-run 输出察觉到他们的数据集配置坏了。

**Fix:**
```python
if dry_run:
    try:
        trainset, valset, holdout = _load_dataset(...)
    except Exception as e:
        click.echo(f"dataset_load_error={type(e).__name__}: {e}", err=True)
        click.echo("dry_run_status=DATASET_LOAD_FAILED", err=True)
        return 1
```

### WR-02: `tool_module.reasoning_tokens` 用 `len(text)/4` 估算,不是真实 token 数

**File:** `evolution/tools/tool_module.py:268-271`
**Issue:**
```python
reasoning_tokens = int(len(reasoning_text) / 4) if reasoning_text else 0
```
char/4 是英文文本的粗略经验值,中文文本可能误差 3-5 倍(每字 1 token,但 `len()` 返回字符数 ≈ token 数;除 4 会低估 75%)。reasoning_tokens 进入 `think_ab_gate.reasoning_token_p50/p95/mean`(写入 metrics.json),Phase 16 dashboard 又会消费这个字段。文档注释承认这是临时方案("Phase 16 dashboard can upgrade"),但当前已写入磁盘的 metrics 历史数据会是错的、不可比较。

**Fix:**
立刻接入 DSPy 的 usage tracker:`tracker.get_total_tokens()` 已在 CostTracker 中可用,在 forward 后查询差值。或者最低限度:**在 metrics.json 中加 `reasoning_tokens_estimate_method: "len_div_4"`** 字段,让历史数据可识别。

### WR-03: GEPA 失败但 `allow_miprov2_fallback=True` 时 `final_spent_usd=0.0`

**File:** `evolution/tools/evolve_tool_reasoning.py:380, 422-458`
**Issue:**
```python
final_spent_usd = 0.0
...
try:
    with tracker:
        ...
        optimized_module = optimizer.compile(...)
        final_spent_usd = float(tracker.poll())  # only reached on success
except CostBudgetExceeded:
    ...
except Exception as gepa_err:
    if not allow_miprov2_fallback:
        ...
    else:
        optimizer_used = "miprov2"
        optimized_module = evolved_module
        # final_spent_usd never updated!
```
fallback 路径不重新 poll,`final_spent_usd` 保持 0.0,写入 metrics.json 的 `cost_usd_spent` 是 0,但 GEPA 在崩溃前可能已经消耗了大量 token。**成本日志失真**。

**Fix:**
```python
else:
    optimizer_used = "miprov2"
    optimized_module = evolved_module
    try:
        final_spent_usd = float(tracker.poll())
    except Exception:
        pass  # fall back to 0
```
注:`tracker.poll()` 在 `__exit__` 后是否仍可用取决于 `_tracker is None` — 看 `cost_tracker.py:250-251` 的逻辑会用 `spent_usd` 作 fallback,可以接受。

### WR-04: `tool_dataset.py:431` `task_description.strip()` 对 LLM 返回 None 时崩溃

**File:** `evolution/tools/tool_dataset.py:341-348, 431`
**Issue:**
```python
task_description=task.get("task_description", ""),
...
all_examples = [ex for ex in all_examples if ex.task_description.strip()]
```
`task.get("task_description", "")` 在 LLM 返回 `{"task_description": null}` 时返回 `None`(而不是默认值),`None.strip()` 抛 AttributeError,杀死整个 `generate()`。

**Fix:**
```python
task_description=(task.get("task_description") or ""),
```
或者在 filter 处加防御:
```python
all_examples = [
    ex for ex in all_examples
    if isinstance(ex.task_description, str) and ex.task_description.strip()
]
```

### WR-05: `ToolSelectionDataset.to_dspy_examples` 不暴露 `reason` 字段

**File:** `evolution/tools/tool_dataset.py:135-158`
**Issue:** `ToolSelectionExample.reason` 字段(D-13 解释为何选某个工具)在 `to_dspy_examples()` 中没传给 `dspy.Example`。Phase 15 metric / future GEPA reflection 可能会需要这些理由作为反馈信号,目前被丢弃在 dataset 阶段。

**Fix:**
```python
return [
    dspy.Example(
        task_description=ex.task_description,
        correct_tool=ex.correct_tool,
        correct_params=ex.correct_params,
        confuser_tools=ex.confuser_tools,
        reason=ex.reason,  # add this
    ).with_inputs("task_description")
    for ex in data
]
```

### WR-06: `tool_dataset.generate` 在 `n_total=1` 时切片产生空 holdout

**File:** `evolution/tools/tool_dataset.py:436-445`
**Issue:**
```python
n_train = max(1, int(n_total * self.config.train_ratio))
n_val = max(1, int(n_total * self.config.val_ratio))
...
holdout=all_examples[n_train + n_val:],
```
若 `n_total=1`,`n_train=1`、`n_val=1`(`max(1, 0)=1`),`n_train + n_val = 2 > n_total`。train 切到 `[:1]`(整个数据),val 切到 `[1:2]`(空),holdout 切到 `[2:]`(空)。下游 ThinkABGate.holdout_examples=0 时会触发 `len(ambiguous_subset) < 5` 自动 skip ambiguous 门,但 v1 gate 仍按 0.0 比较。整体仍 "PASS",但数据上没有任何样本验证。

**Fix:**
要么在 `generate` 入口 assert `n_total >= 3`,要么显式地保证至少 1 example holdout:
```python
n_holdout = max(1, n_total - n_train - n_val)
n_train = max(1, n_total - n_holdout - n_val)
```

### WR-07: `_safe_score` 把所有失败折叠成 0.0 — 隐藏 ThinkABGate 的实际信号

**File:** `evolution/tools/evolve_tool_reasoning.py:615-633`
**Issue:**
```python
def _safe_score(module, examples, lm):
    if not examples:
        return 0.0
    try:
        return float(_score_module_on_holdout(module, examples, lm))
    except Exception:
        return 0.0
```
当 LM 在 holdout 评估时整体崩溃(API key 错、配额耗尽、网络中断),`_safe_score` 返回 0.0。然后 `th_off=0.0`、`th_on=0.0`、`full_delta=0` → full_regression PASS,`ambiguous_delta=0` < 0.03 → ambiguous FAIL,but 触发的是 "THINK_AB_FAILED" 而不是 "EVAL_FAILED"。操作员看到 ThinkABGate 失败,以为是模型质量问题,实际是基础设施失败。

**Fix:**
让 `_safe_score` 返回 `None` 或 NaN,在调用方显式处理:
```python
th_off_full = _safe_score(baseline_module, eval_holdout, lm)
th_on_full = _safe_score(optimized_module, eval_holdout, lm)
if th_off_full is None or th_on_full is None:
    failed_reason = "EVAL_FAILED"
    # write FAILED dir + return 1
```

### WR-08: `evolve_tool_reasoning._write_aborted_dir` schema 与 `CostTracker.write_aborted_json` schema 不一致

**File:** `evolution/tools/evolve_tool_reasoning.py:770-800` vs `evolution/core/cost_tracker.py:272-348`
**Issue:** Phase 15 自己写 `aborted.json`(line 787-799),用的 schema 只有 `{timestamp, started_at, status: "ABORTED", error_class, error_message, reflection_model, spent_usd}`。但 `CostTracker.write_aborted_json`(cost_tracker.py:272-348)有更完整的 schema:`final_cost_usd, max_cost_usd, evaluated_candidates, partial_diff, spent_breakdown_by_lm, status: "ABORTED_COST_CAP"`。

两个不同的 status 字符串(`"ABORTED"` vs `"ABORTED_COST_CAP"`)、不同的成本字段命名(`spent_usd` vs `final_cost_usd` + `max_cost_usd`)。下游消费者如果按 `cost_tracker.write_aborted_json` 的契约编程,Phase 15 的 aborted.json 不兼容。

**Fix:**
直接调用 `tracker.write_aborted_json`:
```python
def _write_aborted_dir(*, tracker, evolved_module, cap_exc, reflection_model_name, started_at):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = OUTPUT_ROOT / f"ABORTED_{ts}"
    tracker.write_aborted_json(
        out_dir,
        extra={
            "timestamp": ts,
            "started_at": started_at,
            "error_class": "CostBudgetExceeded",
            "error_message": str(cap_exc),
            "reflection_model": reflection_model_name,
        },
    )
    return out_dir
```

### WR-09: `ToolModule.forward` 对 reasoner Prediction 缺少 selected_tool 字段时不防御

**File:** `evolution/tools/tool_module.py:259-278`
**Issue:**
```python
result = self.selector(...)
selected_params = getattr(result, "selected_params", "") or "{}"
...
return dspy.Prediction(
    selected_tool=result.selected_tool,  # AttributeError if missing
    ...
)
```
`result.selected_tool` 没有 `getattr` 兜底,如果 LM 输出格式异常导致 DSPy ChainOfThought 解析失败、Prediction 缺少该字段,这里抛 AttributeError 中断整个 forward。`_safe_score`(WR-07)会 catch 并 → 0.0,但单点失败传染整个 holdout 评估。

**Fix:**
```python
selected_tool = getattr(result, "selected_tool", "") or ""
selected_params = getattr(result, "selected_params", "") or "{}"
return dspy.Prediction(
    selected_tool=selected_tool,
    selected_params=selected_params,
    ...
)
```

---

## Info

### IN-01: `sample_latency_tokens` 的 task 提取有冗余 try/except

**File:** `evolution/tools/think_metrics.py:344-347`
**Issue:**
```python
try:
    task = ex.task_description
except AttributeError:
    task = getattr(ex, "task_description", "")
```
两个分支等价:`ex.task_description` 抛 AttributeError 时,`getattr(ex, "task_description", "")` 一样会返回默认值 `""`(它内部也是用 `getattr` 的逻辑)。代码冗余,且对 MagicMock 来说 try 永远成功(MagicMock 不抛 AttributeError)。

**Fix:** `task = getattr(ex, "task_description", "")`(直接,无 try)。

### IN-02: `CostBudgetExceeded.__init__` 双形参形式是反模式

**File:** `evolution/core/cost_tracker.py:62-73`
**Issue:** 一个异常类同时支持 `CostBudgetExceeded("msg string")` 和 `CostBudgetExceeded(spent, max)` 两种调用约定,通过 `isinstance(arg, str)` 分流。这是测试驱动的妥协,使得任何 `int` 调用(如 `CostBudgetExceeded(0)`)会走 "spent_usd=0, max=0" 路径,消息变成 `"Cost budget exceeded: spent $0.0000 > cap $0.0000"`,与调用者意图相反。

**Fix:** 把字符串版本改成 classmethod:
```python
@classmethod
def from_message(cls, msg: str) -> "CostBudgetExceeded":
    exc = cls.__new__(cls)
    exc.spent_usd = 0.0
    exc.max_usd = 0.0
    Exception.__init__(exc, msg)
    return exc
```
测试可改为 `CostBudgetExceeded.from_message("cost exceeded $5.00")`。

### IN-03: `_inject_usage_for_test` 与 `poll` 中重复了相同的合并逻辑

**File:** `evolution/core/cost_tracker.py:202-211, 236-246`
**Issue:** 两处都在合并 `prompt_tokens/completion_tokens/total_tokens`(累加)+ 其他字段(覆盖)。是经典的 DRY 违反,如果合并语义改变(例如允许 `model` 字段冲突报错),要改两处。

**Fix:** 抽出 `_merge_usage(dest, src)` 私有静态方法。

### IN-04: `evolve_tool_reasoning._gate_passed` 对 MagicMock 处理过于宽松

**File:** `evolution/tools/evolve_tool_reasoning.py:636-649`
**Issue:**
```python
def _gate_passed(gate_result: Any) -> bool:
    if isinstance(gate_result, dict):
        return bool(gate_result.get("passed", True))
    return bool(gate_result)
```
非 dict 情形(包括 MagicMock)直接 `bool(...)`。MagicMock 的 `__bool__` 默认是 True,等于把所有 mock 视为 PASS。生产代码不应该有这个分支(只为测试服务),且测试本身可以构造 `MagicMock(passed=True)` + return dict。

**Fix:** 删除非 dict 分支,assert dict:
```python
def _gate_passed(gate_result: Any) -> bool:
    if not isinstance(gate_result, dict):
        raise TypeError(f"gate result must be dict, got {type(gate_result)}")
    return bool(gate_result.get("passed", False))  # default False, not True
```

### IN-05: `tool_module.py:178` "immutable after __init__" 注释与 Python 语言能力不符

**File:** `evolution/tools/tool_module.py:175-180`
**Issue:** 注释声称 `enable_reasoning is immutable after __init__ — never set self.reasoner outside this block`。Python 没有 final/frozen 属性。任何外部代码 `module.enable_reasoning = True; module.reasoner = some_predict` 都能改变行为。注释是社区契约,但同名字段又作为行为开关使用,容易被绕过。

**Fix:** 改用 `_enable_reasoning`(下划线表 "private 约定")+ 注释 + 不在 forward 中读 `self.enable_reasoning`(只读 `self.reasoner is not None`),消除字段-行为耦合的歧义。

### IN-06: `tool_module._format_available_tools` 不防御 `param_predictors[pn].signature.instructions=None`

**File:** `evolution/tools/tool_module.py:217-219`
**Issue:**
```python
p_desc = bundle.param_predictors[pn].signature.instructions
param_lines.append(f"    - {pn}: {p_desc}")
```
若 GEPA mutate 后 instructions 是 None(理论上 DSPy 不允许,但 with_instructions(None) 不被禁止),f-string 会显示字面 `"None"`,污染选择器的 prompt。

**Fix:**
```python
p_desc = bundle.param_predictors[pn].signature.instructions or ""
```

---

_Reviewed: 2026-05-12_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
