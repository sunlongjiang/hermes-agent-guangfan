---
phase: 15-think-augmented-tool-selection
verified: 2026-05-12T07:09:32Z
status: human_needed
score: 3/3 must-haves verified
overrides_applied: 0
human_verification:
  - test: "在真实 hermes-agent repo + LM API 下执行 --iterations 1 --max-cost-usd 2.0 --eval-source load，检查输出目录 output/tools_reasoning/<ts>/ 包含全部 4 个文件（metrics.json / reasoning_prompt.txt / diff.txt / ab_comparison.json），且 think_ab_gate 块存在、无崩溃"
    expected: "exit code 0 或 1（THINK_AB_FAILED 为合理失败），metrics.json 含 think_on_score / think_off_score / ambiguous_think_on / ambiguous_think_off / latency_stats / think_ab_gate 全字段"
    why_human: "需要真实 LM API key 与 $2 预算；CI 不具备此条件。代码审查 CR-01~CR-04 中的 4 个 BLOCKER 在真实运行下可能导致 ab_comparison.json latency 标签错位、V1Gate 静默 PASS、--ambiguous-only three-AND 退化、cost tracker inf 中止——需要人工核验这些场景在实际运行中是否触发"
  - test: "以 --ambiguous-only 标志运行，确认 ThinkABGate 实际有效区分 full_regression 与 ambiguous 两个信号（CR-03 场景）"
    expected: "full_regression_delta 与 ambiguous_delta 有数值差异，或 CLI 打印警告说明 full_regression gate 已失效"
    why_human: "当前代码中 --ambiguous-only 时 eval_holdout==ambiguous_subset，导致两个 delta 完全相同，three-AND 退化为 two-AND；需要人工决策是否接受此限制或要求修复"
  - test: "注入一个触发 litellm 返回 inf 成本的场景（或 mock float('inf') 进入 CostTracker），确认 cost tracker 不将 spent_usd=inf 写入 metrics.json（CR-04 场景）"
    expected: "CostTracker 抛出 ValueError 或返回 fallback 而非累加 inf"
    why_human: "自动测试已 mock 了 cost path，inf 路径未被测试覆盖；需要人工决定是否补测或视为可接受风险"
---

# Phase 15: Think-Augmented Tool Selection — Verification Report

**Phase Goal:** Add optional reasoning-before-selection Predict to ToolModule (enable_reasoning opt-in), make it GEPA-optimizable, and validate via three-AND gate (full-regression 2pp + ambiguous +3pp + latency p95 ≤ 5s) in a new CLI with isolated output directory.
**Verified:** 2026-05-12T07:09:32Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | ToolModule supports optional ChainOfThought reasoning before selection (enable_reasoning opt-in) | VERIFIED | `tool_module.py:178-191`: `enable_reasoning` 参数控制 `self.reasoner` 构造；`forward()` 第 247 行 `if self.reasoner is not None` 双路径分支；7/7 TestEnableReasoning 测试全绿 |
| 2 | Reasoning step is optimizable by GEPA (prompt text is a parameter — reachable via named_predictors()) | VERIFIED | `tool_module.py:189` `self.reasoner = dspy.Predict(ToolReasoningSignature)` 作为 `dspy.Module` 属性被 DSPy 自动注册；运行时验证 `named_predictors()` 输出包含 key `'reasoner'`，instructions 非空且含 `'Be concise'` |
| 3 | A/B comparison shows improvement on ambiguous selection scenarios (CLI executes the comparison and writes ab_comparison.json + metrics.json) | VERIFIED (with caveats) | `evolve_tool_reasoning.py:558-580` 写出 4 个文件；11/11 integration tests 全绿；但存在 4 个代码审查 BLOCKER（CR-01~CR-04）影响 ab_comparison.json 的可信度，见 "Risks Against SC-3" 节 |

**Score:** 3/3 truths verified

---

### Risks Against Success Criterion 3 (Review BLOCKERs)

代码审查（15-REVIEW.md）标记了 4 个 BLOCKER，不阻止代码执行但**影响输出可信度**：

#### CR-01 — latency 索引错配（BLOCKER — 数据可信度）

`think_metrics.py:352-354`：`sample_latency_tokens` 在 module 调用抛异常时执行 `continue`，不追加哨兵值，导致 `latencies_on` 长度 < `len(holdout)`。`_build_ab_comparison`（line 759-760）用 `latencies_on[i]` 按 holdout 索引取延迟，当有失败示例时，index i 对应的延迟实为 holdout[i+N]（N = 已跳过的失败示例数）。**ab_comparison.json 中 latency_seconds_on 字段在有 LM 错误时系统性错位**。ThinkABGate 消费的 latency_p95 来自同一 `sampling["stats"]`，其百分位计算基于"成功示例数"，**当失败率非零时 p95 系统性偏低**。

- 影响范围：仅当有 LM 调用失败时触发；全成功路径（测试环境）不触发
- 严重程度：静默数据污染，操作员无法从输出发现

#### CR-02 — V1BaselineGate silent no-op（BLOCKER — 误导性 PASS）

`evolve_tool_reasoning.py:482-485`：`baseline_run=None`（CLI 默认）时，`compute_v1_baseline` 返回 `v1_baseline_holdout=0.0`。`v1_gate.check(evolved_score=th_off_full, baseline=v1_info)` 等效于"是否 score >= -0.02"，任何非负分数都通过。`metrics["v1_gate_passed"]` 仍写 `True`，日志显示 "PASS"，但门实际未执行。**v1_baseline_source='missing' 字段可标识此情形，但操作员易忽视**。

- 影响范围：所有未提供 `--baseline-run` 的运行（即默认路径）
- 注：代码注释（line 476-481）明确说明这是有意为之的降级，但 metrics.json schema 未区分 PASS vs SKIPPED

#### CR-03 — `--ambiguous-only` 使 ThinkABGate 退化为 two-AND（BLOCKER — 逻辑缺陷）

`evolve_tool_reasoning.py:464-468`：当 `ambiguous_only=True`，`eval_holdout = ambiguous_subset`，导致 `th_off_full == th_off_ambig`、`th_on_full == th_on_ambig`。送入 ThinkABGate 的 `full_regression_delta == ambiguous_delta`。three-AND 门实质退化为 two-AND（full_regression 门被 ambiguous 门冗余覆盖）。

- 影响范围：仅 `--ambiguous-only` 标志时
- 注：默认路径（不加此标志）不受影响

#### CR-04 — `cost_tracker.estimate_cost_usd` inf guard 缺失（BLOCKER — 潜在运行中止）

`cost_tracker.py:107`：`lm_usd != lm_usd` 仅检测 NaN，`float('inf')` 不触发检测。若 litellm 返回 inf cost，`spent_usd=inf`，`exceeded()` 立即返回 True，中止所有 GEPA 运行。

- 影响范围：litellm 返回 inf（较罕见但已知在未知 model 名时发生）

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `evolution/tools/tool_module.py` | ToolModule.enable_reasoning + ToolReasoningSignature | VERIFIED | `enable_reasoning` 构造器参数、`self.reasoner` Predict、双路径 forward；Phase 15 相关代码 line 56-75 + 174-278 |
| `evolution/tools/think_metrics.py` | ThinkABGate 三 AND 门 + sample_latency_tokens | VERIFIED | 实体文件 386 行；ThinkABGate class + check_think_ab_gate function + sample_latency_tokens；21/21 tests 全绿 |
| `evolution/tools/evolve_tool_reasoning.py` | CLI 16 步流水线 + 4 输出文件 + tools_reasoning/ 物理隔离 | VERIFIED | 811 行；OUTPUT_ROOT = Path("output")/"tools_reasoning"（line 75）；_write_metrics/_write_ab_comparison/_write_reasoning_prompt/_write_diff 全实现；11/11 integration tests 全绿 |
| `evolution/tools/tool_dataset.py` | to_dspy_examples 携带 confuser_tools（15-06 修复） | VERIFIED | line 150-157：`confuser_tools=ex.confuser_tools` 包含在 dspy.Example；test_tool_dataset.py 验证 |
| `tests/tools/test_think_metrics.py` | ThinkABGate / sampler / dual-API 测试 | VERIFIED | 21 个测试全绿 |
| `tests/tools/test_evolve_tool_reasoning.py` | CLI integration tests | VERIFIED | 11 个测试全绿 |
| `tests/tools/test_dataset_ambiguous_size.py` | 观察真实 ambiguous 子集大小 | VERIFIED | 1 test 绿；ambiguous_subset_size=75 |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| ToolModule.forward | self.reasoner | `if self.reasoner is not None` (line 247) | WIRED | think-on 路径先调 reasoner，reasoning_text 传入 selector |
| self.reasoner | ToolReasoningSignature | `dspy.Predict(ToolReasoningSignature)` (line 189) | WIRED | reasoner 使用 Phase 15 专属签名 |
| GEPA | ToolModule.reasoner | `named_predictors()` 输出含 'reasoner' key | WIRED | 运行时验证通过 |
| evolve_tool_reasoning | ThinkABGate | line 488-500 | WIRED | `think_gate.check(...)` 接收 th_on_full / th_off_full / ambiguous scores / latency_p95 |
| evolve_tool_reasoning | sample_latency_tokens | line 471 | WIRED | sampling 结果用于 ab_comparison 和 latency_p95 |
| CLI output | tools_reasoning/ | OUTPUT_ROOT = Path("output")/"tools_reasoning" (line 75) | WIRED | 所有写出路径均基于此常量；integration tests 验证物理隔离 |
| to_dspy_examples | confuser_tools | line 155 `confuser_tools=ex.confuser_tools` | WIRED | 15-06 修复，ambiguous filter（confuser_tools 长度 >= 2）可正确工作 |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| evolve_tool_reasoning._evolve_impl | th_on_full / th_off_full | `_safe_score(module, holdout, lm)` | 是（LM 评分，测试中 mock） | FLOWING |
| evolve_tool_reasoning._evolve_impl | think_ab_metrics | `think_gate.check(...)` with real delta values | 是 | FLOWING |
| evolve_tool_reasoning._build_ab_comparison | latency_seconds_on | `sampling["latency_seconds"][i]` | 有条件：失败示例 skip 导致索引错位（CR-01） | CONDITIONALLY HOLLOW |
| think_metrics.sample_latency_tokens | latencies | `time.perf_counter()` before/after module() | 是（成功路径），失败时 skip 不追加哨兵 | CONDITIONALLY FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| CLI 入口可调用 | `python -m evolution.tools.evolve_tool_reasoning --dry-run --hermes-repo /tmp/noexist` | 程序启动、发现 tools（使用 env 默认 repo）| PASS |
| named_predictors() 包含 reasoner | Python 脚本：`ToolModule(tools, enable_reasoning=True).named_predictors()` | keys 含 'reasoner' | PASS |
| ThinkABGate 三 AND 逻辑正确 | Python 脚本：各组合输入验证 passed 字段 | 全 pass 时 True，ambiguous 不足 3pp 时 False | PASS |
| to_dspy_examples 携带 confuser_tools | grep + code read | line 155 已包含 confuser_tools | PASS |
| 完整测试套件 | `pytest tests/ -q` | 466 passed, 1 xfailed, 0 failures | PASS |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| TOOL-V2-03 | Phase 15 (6 plans) | Think-augmented tool selection (reasoning step before selection) | SATISFIED | ToolModule.enable_reasoning 实现 SC-1；named_predictors() 暴露 reasoner 满足 SC-2；CLI + ThinkABGate 三 AND 门实现 SC-3 |

**备注：** REQUIREMENTS.md 中 TOOL-V2-03 状态仍标注为 "Pending"——这是追踪表未更新，与代码实现现状不符。建议更新为 "Complete"。

---

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `evolution/tools/think_metrics.py` | 352-354 | `continue` 在异常路径不追加哨兵，破坏索引对齐 | BLOCKER (CR-01) | ab_comparison.json latency 字段在 LM 失败时错位 |
| `evolution/tools/evolve_tool_reasoning.py` | 464-468 | `--ambiguous-only` 时 `eval_holdout==ambiguous_subset` 造成双信号冗余 | BLOCKER (CR-03) | ThinkABGate three-AND 退化为 two-AND，full_regression gate 失效 |
| `evolution/tools/evolve_tool_reasoning.py` | 482-485, 551-553 | `v1_baseline_source=missing` 时 v1_gate_passed 写 True | BLOCKER (CR-02) | metrics.json 显示 V1 gate PASS 但门未实际执行 |
| `evolution/core/cost_tracker.py` | 107 | `lm_usd != lm_usd` 不捕获 `float('inf')` | BLOCKER (CR-04) | litellm 返回 inf cost 时 spent_usd=inf，GEPA 立即中止 |
| `evolution/tools/tool_module.py` | 271 | `reasoning_tokens = int(len(reasoning_text) / 4)` — char/4 估算 | WARNING (WR-02) | metrics.json 中 reasoning_token_stats 对中文文本误差 3-5 倍 |
| `evolution/tools/evolve_tool_reasoning.py` | 319-325 | dry-run 静默吞掉 `_load_dataset` 异常 | WARNING (WR-01) | 数据集配置损坏时 dry-run 仍 exit 0 |

---

### Human Verification Required

#### 1. 真实 LLM A/B 运行端到端验证

**Test:** 配置 API key，运行 `python -m evolution.tools.evolve_tool_reasoning --iterations 1 --max-cost-usd 2.0 --eval-source load`
**Expected:** exit 0 或 exit 1（ThinkABGate FAILED），输出目录含 4 个文件，metrics.json 无崩溃字段，think_ab_gate 块完整
**Why human:** 需要真实 LM API；CR-01/CR-02/CR-04 在生产路径下是否实际触发需要真实运行确认

#### 2. `--ambiguous-only` 退化验证与决策

**Test:** 运行 `python -m evolution.tools.evolve_tool_reasoning --dry-run --ambiguous-only`，然后查看真实运行下 metrics.json 中 `think_off_score == ambiguous_think_off` 是否成立
**Expected:** 操作员决定是接受此限制（--ambiguous-only 仅用作调试模式）还是要求修复 CR-03
**Why human:** 这是一个设计决策——CR-03 是 BLOCKER 还是可接受的 known limitation 取决于 --ambiguous-only 的使用意图

#### 3. V1BaselineGate SKIPPED vs PASS 语义确认

**Test:** 在 metrics.json 中检查 `v1_baseline_source` 字段，确认操作员能否从现有输出判断 V1 gate 是否真正执行
**Expected:** 若接受"v1_baseline_source='missing' 即 SKIPPED"的约定，则 CR-02 为可接受风险；否则需要修复
**Why human:** 代码注释明确说明降级是有意为之，但 metrics.json schema 未区分 PASS vs SKIPPED

---

### Gaps Summary

所有 3 个 Success Criteria 在代码结构层面均已实现并通过测试验证（466 passed, 1 xfailed）。**Phase 15 的管道骨架存在且正确连通。**

但代码审查标记的 4 个 BLOCKER（CR-01~CR-04）影响**输出可信度**而非代码正确性：

- **CR-01**（latency 索引错位）和 **CR-03**（`--ambiguous-only` 退化）直接影响 SC-3 中 A/B comparison 的数学可信度
- **CR-02**（V1Gate 静默 no-op）和 **CR-04**（inf guard 缺失）属于潜在误导性输出和稳定性风险

这些 BLOCKER 不触发 `gaps_found`（实现结构完整），但需要人工决策：(a) 在推进到 Phase 16 前修复，或 (b) 记录为已知限制并接受。因此状态为 `human_needed`。

---

_Verified: 2026-05-12T07:09:32Z_
_Verifier: Claude (gsd-verifier)_
