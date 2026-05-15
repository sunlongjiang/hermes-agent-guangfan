---
phase: 16-per-tool-regression-dashboard
reviewed: 2026-05-15T00:00:00Z
depth: standard
files_reviewed: 24
files_reviewed_list:
  - .gitignore
  - evolution/tools/evolve_tool_descriptions.py
  - evolution/tools/evolve_tool_params.py
  - evolution/tools/evolve_tool_reasoning.py
  - evolution/tools/regression_dashboard.py
  - evolution/tools/tool_dataset.py
  - evolution/tools/tool_metric.py
  - tests/fixtures/dashboard_runs/desc_old/metrics.json
  - tests/fixtures/dashboard_runs/json_corrupt/metrics.json
  - tests/fixtures/dashboard_runs/params_complete/metrics.json
  - tests/fixtures/dashboard_runs/params_complete_v2/metrics.json
  - tests/fixtures/dashboard_runs/params_multi_regress/metrics.json
  - tests/fixtures/dashboard_runs/params_no_raw/metrics.json
  - tests/fixtures/dashboard_runs/reasoning_complete/ab_comparison.json
  - tests/fixtures/dashboard_runs/reasoning_complete/metrics.json
  - tests/fixtures/dashboard_runs/reasoning_old/metrics.json
  - tests/fixtures/dashboard_runs/reasoning_with_secret/ab_comparison.json
  - tests/fixtures/dashboard_runs/reasoning_with_secret/metrics.json
  - tests/tools/test_evolve_tool_descriptions.py
  - tests/tools/test_evolve_tool_params_cli.py
  - tests/tools/test_evolve_tool_reasoning.py
  - tests/tools/test_persist_raw_predictions.py
  - tests/tools/test_regression_dashboard.py
  - tests/tools/test_tool_dataset.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 16: Code Review Report (Post-Gap-Closure Re-Review)

**Reviewed:** 2026-05-15T00:00:00Z
**Depth:** standard
**Files Reviewed:** 24
**Status:** issues_found

## Summary

本次为 Phase 16 在 16-05 gap closure 之后的复审。先前 REVIEW（2026-05-14）登记
3 BLOCKER + 7 WARNING + 6 INFO，本轮逐一回放并补查新引入风险：

**先前 BLOCKER 全部已闭合（3/3）：**

- **CR-01（`--runs` 语义破裂）** — 已修复。`_scan_runs(roots, explicit_runs)`
  现在接受第二个 tuple 参数；`--runs` 进入 `explicit_runs` 渠道并以
  `Path(run_dir)/"metrics.json"` 直接解析（regression_dashboard.py:54-83、
  663-665）。新增 `test_scan_runs_resolves_explicit_path` 与
  `test_scan_runs_glob_and_explicit_combined` 不再 patch `_scan_runs`，端到端
  覆盖真实 glob + 显式两路径。
- **CR-02（`--runs` vs `--baseline-run` 语义不一致）** — 已修复。`--baseline-run`
  仍走 `Path(...)/"metrics.json"`（line 713-714），`--runs` 通过 `explicit_runs`
  渠道走相同语义；同一份 fixture 既可作 `--runs` 也可作 `--baseline-run`。
- **CR-03（reasoning A/B 双 metric 混用）** — 已修复。`_score_with_predictions`
  在 evolve_tool_reasoning.py:687-690 现在使用 `joint_tool_param_metric` 计算
  `sample_score`，与 `_safe_score → _score_module_on_holdout` 同源。
  `test_score_with_predictions_uses_joint_metric` 用大小写不一致的
  `correct_tool="Read_File"` 与 `selected_tool="read_file"` 验证归一化生效。

**先前 WARNING 处理情况（7 条中 6 闭合、1 延期）：**

| 编号 | 状态 | 备注 |
|------|------|------|
| WR-01 `datetime.utcnow()` 弃用 | 已闭合 | `datetime.now(timezone.utc).strftime(...)`；`test_dashboard_json_no_datetime_deprecation_warning` 主动断言 |
| WR-02 TREND cutoff 时区混用 | 已闭合 | line 741 改 `datetime.now(timezone.utc).timestamp()`，与 `generated_at` 一致 |
| WR-03 `_load_run` 2-3× 重复 I/O | **延期**（17-XX 性能 phase） | line 679 + 713-714 + 730 三处仍各自加载 |
| WR-04 FAILED-dir 漏 per_tool/raw | 已闭合 | evolve_tool_descriptions.py:374-375 在 `regression_result` 分支前就调用 `persist_*`；新增 `test_regression_failed_metrics_carry_per_tool_rates` 端到端验证 |
| WR-05 DIFF source=None 渲染 `None` | 已闭合 | `_render_diff` line 363-364 用 `baseline_run["source"] or "?"` 兜底 |
| WR-06 空 `correct_tool` 产生鬼影 bar | 已闭合 | line 242-244 用 `if tool` 过滤空字符串 |
| WR-07 `_score_with_predictions` 静默吞异常 | 已闭合 | 内部 except 加 yellow log（line 667-670），外层 except 加 batch 级日志并返回部分结果（line 695-701）；`test_score_with_predictions_logs_per_example_error` 断言 stdout |

**先前 INFO 处理情况（6 条中 3 闭合、3 延期）：**

| 编号 | 状态 | 备注 |
|------|------|------|
| IN-01 `_load_run` `is None` 死代码 | 已闭合 | line 680 改为 `loaded.get("metrics") is None`，与新 `_drop_reason` 契约一致；docstring 同步更新 |
| IN-02 `json_corrupt` fixture 未被引用 | 已闭合 | 新增 `test_json_corrupt_fixture_drops_with_reason` 端到端覆盖 |
| IN-03 测试注释 `-5pp` 与 fixture `-10pp` 矛盾 | **延期** | test_regression_dashboard.py:50/73/85/363/368/385 仍写 `-5pp` |
| IN-04 LATEST `_quintiles` 列名误导 | **延期** | 未触动 `_render_latest` 列头 |
| IN-05 `_detect_source` 顺序依赖注释 | **延期** | 未触动 step 2 注释 |
| IN-06 `evolve_tool_descriptions` 仍用 `sys.exit(1)` | **延期** | line 152/160/200/205 未改 `_evolve_impl` 模式 |

**本轮新发现：**

- **WR-A1**（新）：`_score_with_predictions` docstring 与实际语义不符——
  docstring 写 "exact-match accuracy over successful predictions"，代码实际
  累加 `joint_tool_param_metric` (0.5 tool + 0.5 param composite)。这是 CR-03
  修复的副作用，必须更新文档以避免误导。
- **WR-A2**（新）：`evolve_tool_descriptions._union_session_into_dataset` 与
  `evolve_tool_params._union_session_into_dataset` 是逐字重复实现（55-72 vs
  223-252），任一处修复必须 manual 同步另一处。
- **IN-A1**（新）：`regression_dashboard.py` import 了 `sys` 但模块体内零引用。
- **IN-A2**（新）：`evolve_tool_descriptions.py` / `evolve_tool_params.py` /
  `evolve_tool_reasoning.py` 三处均 import `Panel`、`get_hermes_agent_path` 但
  完全未使用——属于 phase 间遗留 import，gap closure 触动过 descriptions 文件
  但未顺手清理。
- **IN-A3**（新）：`test_evolve_tool_reasoning.test_e2e_mock_pipeline` 注释
  写 "5 ambiguous examples in fake_holdout (i < 5)"，但 fixture 实际上
  `i < 5` 的 confuser_tools 是 `["read_file", "ls"]`（len=2 → ambiguous），
  `i >= 5` 是 `["ls"]`（len=1 → not ambiguous），所以注释正确；但断言
  `metrics["ambiguous_subset_size"] == 5` 是硬编码 magic number，
  若 fixture 调整将沉默失败。

整体而言，gap closure 落地干净，3 个 BLOCKER 全部修复且配有未 mock `_scan_runs`
的端到端测试，符合 16-05-PLAN 验收契约。剩余 5 项发现均为 WARNING/INFO 级，
不阻塞 Phase 16 收口。

## Warnings

### WR-A1: `_score_with_predictions` docstring 与 CR-03 修复后的语义不匹配

**File:** `evolution/tools/evolve_tool_reasoning.py:646-654`
**Issue:** CR-03 修复将 `sample_score` 从 `correct == selected` 改为
`joint_tool_param_metric(ex, pred)`（line 687-690），但 docstring 仍写：

```
Returns:
    (mean_score, tool_pairs, raw_preds)
    - mean_score: exact-match accuracy over successful predictions
```

实际上 `mean_score = total / n`，而 `total` 累加的是 0.5 * tool_match +
0.5 * param_match。对于一个只答对工具名但 param 错的样本，sample_score=0.5
而非 1.0。这与 docstring 的 "exact-match accuracy" 直接冲突，未来读者会被
误导（特别是 ThinkABGate 调试者）。
**Fix:** 把 docstring 换成准确描述：

```python
- mean_score: mean joint_tool_param_metric over successful predictions
  (0.5 tool_match + 0.5 param_match, normalized via strip+lower / strip+coerce)
```

或反向：若希望保留 "exact-match accuracy" 语义，则把 `joint_tool_param_metric`
换成 `tool_selection_metric`（仅看 selected_tool == correct_tool 归一化后是
否相等）——但这又违背 CR-03 "与 `_safe_score` 同源" 的初衷。强烈建议改文档
而非改逻辑。

### WR-A2: `_union_session_into_dataset` 在 descriptions/params 两处逐字重复

**File:** `evolution/tools/evolve_tool_descriptions.py:43-72` ←→
`evolution/tools/evolve_tool_params.py:223-252`
**Issue:** 这两个函数从 import 列表（`from pathlib import Path as _SessPath`）、
循环结构、注释（"Pitfall 10 ordering"、"Pitfall 5"）到 console.print 文案均
完全相同。任何一处 bug fix（例如 D-09 / D-14 合并语义升级）必须人工同步两处，
否则会出现 desc 与 params 行为漂移。属于 Phase 14 引入、Phase 16 触动过
descriptions 文件但未顺手提取的债务。
**Fix:** 抽取到 `evolution/tools/_session_union.py` 或在
`tool_dataset.py` 上方新增 `union_session_into_dataset(...)` 公共函数，两个
CLI 同 import。Phase 16 之外的改动建议合并到 Phase 17 cleanup。

## Info

### IN-A1: `regression_dashboard.py` import `sys` 但模块内零引用

**File:** `evolution/tools/regression_dashboard.py:25`
**Issue:** `import sys` 在第 25 行，但整个模块体内没有任何 `sys.*` 调用——
退出走 `click.UsageError`（line 670），所有 I/O 走 `Path` + `console.print`。
该 import 应是早期手写 sys.exit 时遗留。
**Fix:** 删除 `import sys`。

### IN-A2: 三个 evolve_tool_* CLI 均 import 但未使用 `Panel` 与 `get_hermes_agent_path`

**File:** `evolution/tools/evolve_tool_descriptions.py:20, 23` /
`evolution/tools/evolve_tool_params.py:58, 61` /
`evolution/tools/evolve_tool_reasoning.py:43`
**Issue:** `from rich.panel import Panel` 与 `from evolution.core.config import
EvolutionConfig, get_hermes_agent_path` 在所有三个 evolve_tool_* CLI 中均
存在，但 `Panel` 仅 evolve_tool_params 与 evolve_tool_reasoning 在 import 时
保留（params 文件内同样无 Panel(...) 调用），`get_hermes_agent_path` 在三处
都仅占用 import 行——所有路径都通过 `config.hermes_agent_path` 访问。
**Fix:** Phase 17 清理时一次性删除：

```python
# evolve_tool_descriptions.py / evolve_tool_params.py / evolve_tool_reasoning.py
from evolution.core.config import EvolutionConfig  # 删 get_hermes_agent_path
# 删 from rich.panel import Panel（descriptions 与 params；reasoning 中 Panel 实际被用）
```

注意：reasoning.py 的 `Panel` 在第 598 行被使用，仅 descriptions/params 的
Panel import 是死代码。

### IN-A3: `test_e2e_mock_pipeline` 硬编码 `ambiguous_subset_size == 5`

**File:** `tests/tools/test_evolve_tool_reasoning.py:567-569`
**Issue:** 断言 `metrics["ambiguous_subset_size"] == 5` 直接绑定 fixture 内
"前 5 个 example 的 confuser_tools 长度 >= 2" 的实现细节。若 `_mock_example`
（line 478-484）的 `i < 5` 条件被调整（例如改 holdout 大小），断言会失败但
错误信息只会显示 size mismatch、不指明 fixture 与断言耦合。
**Fix:** 用动态计算替换硬编码：

```python
expected_ambig = sum(1 for ex in fake_holdout if len(ex.confuser_tools) >= 2)
assert metrics["ambiguous_subset_size"] == expected_ambig
```

---

_Reviewed: 2026-05-15T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
