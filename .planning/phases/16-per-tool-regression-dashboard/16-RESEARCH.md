# Phase 16: Per-Tool Regression Dashboard - Research

**Researched:** 2026-05-12
**Domain:** Standalone Rich console + JSON regression dashboard for tool-evolution pipelines (D-01..D-17 from 16-CONTEXT.md)
**Confidence:** HIGH (all assertions verified against running code, real metrics.json fixtures, Rich 15.0.0 / Click 8.1.8 / DSPy 3.1.3 in `.venv/`)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

D-01..D-17 from `16-CONTEXT.md`. Pinned highlights the planner MUST honor verbatim:

- **D-01:** Standalone CLI `python -m evolution.tools.regression_dashboard`. **不动** evolve_tool_* 三 CLI 入口。
- **D-02:** `--runs <path>` 可重复（multiple=True 累加）；默认根 `output/tools/` + `output/tools_reasoning/`；都为空且无 `--runs` → exit 2。
- **D-03:** stdout Rich Table（LATEST + DIFF + TREND + ABStudy）+ `dashboard.json` 双产物。
- **D-04:** `dashboard.json` 落 CWD，文件名 `dashboard_<YYYYMMDD_HHMMSS>.json`，可 `--output <path>` 覆盖。
- **D-05:** 三区视图：LATEST（mtime 最新单 run）、DIFF（仅在传 `--baseline-run` + `--evolved-run` 时启用）、TREND（按 D-06 窗口）。
- **D-06:** TREND 窗口互斥两 flag：`--trend-window N`（默认 10）与 `--trend-days D`（同时传 → exit 2）。
- **D-07:** 跨 CLI 全合并；`source ∈ {desc, params, reasoning}` 自动判定；表头脚注说明 baseline 含义差异。
- **D-08:** schema 兼容：缺 `per_tool_baseline_rates` / `per_tool_evolved_rates` → 整 run 跳过 + `dropped_runs`；缺 `raw_predictions` → distribution 列退化为 n/a；缺 `ab_comparison.json` → ABStudy 不渲染。
- **D-09:** LATEST 字段：`source / tool / baseline_rate / evolved_rate / delta_pp / sample_count / min / p25 / median / p75 / max / status`；`status ∈ {OK / WARN(≤-2pp) / FAIL(≤-5pp) / GAIN(≥+5pp)}`。
- **D-10:** distribution 双层语义都做（语义 A 单 run 内分桶；语义 B 跨 run 序列）。
- **D-11:** `--segment difficulty|pool_size|none`，pool_size 分桶 1-3 / 4-7 / 8+。
- **D-12:** **本 phase 范围内：扩展三 CLI metrics.json schema** 增 `raw_predictions`，新建共用 helper `evolution.tools.tool_metric.persist_raw_predictions()`，模式对齐 `persist_per_tool_rates`。
- **D-13:** 默认 -2pp warning，`--warning-threshold-pp` 可调，**不返 exit code**。Phase 13 现有 `CrossToolRegressionChecker` 硬门继续单独跑。
- **D-14:** **不**实现 p25-based hard gate（deferred）。
- **D-15:** ABStudy 区（仅在扫到 reasoning source 时）展示 `think_on_saved / think_on_regressed / both_wrong` 三类计数 + top-3 例子。
- **D-16:** LATEST 表底渲染频次柱图（按 `sample_count` 降序，limit 12 行 + 「others (N tools)」聚合）。
- **D-17:** 五 Wave 切分：Wave 0 schema + helper + 三 CLI 接线；Wave 1 dashboard 骨架 + LATEST；Wave 2 DIFF + TREND；Wave 3 ABStudy + source 标注 + fallback；Wave 4 dashboard.json schema 收口 + 集成测试。

### Claude's Discretion

- `dashboard.json` 顶层字段名（建议 `latest / diff / trend / ab_study / source_legend / dropped_runs / summary / warnings`，可微调）
- Rich Table 颜色编码具体 hex / Rich style 名（基调 OK 默认 / WARN 黄 / FAIL 红 / GAIN 绿已锁）
- TREND sparkline 字符集合（`▁▂▃▄▅▆▇█` 推荐）
- 老 run 自动检测启发顺序（field set + 目录名 fallback）
- ABStudy top-3 排序键
- `persist_raw_predictions` 字段精确名（`correct_tool / selected_tool / difficulty / num_available_tools` 推荐）
- segment `pool_size` 分桶边界

### Deferred Ideas (OUT OF SCOPE)

- p25-based hard gate（→ Phase 19 / 20 / 22 数据扩量后评估）
- SQLite history DB / 90-day / 1000-run cap retention（→ Phase 22）
- evolve_* CLI 末尾 inline summary（→ Phase 16.5 / 23）
- `--strict` flag 让 dashboard 返 exit 1（→ Phase 22）
- skill / prompt 管道 dashboard 化（→ Phase 17 / 18 后再议）
- Reasoning 错例自动 issue / repair（→ Phase 22+）
- 给 evolve_tool_descriptions 历史 run 回填 `per_tool_*_rates`
- pool_size 分桶自适应 / quantile-based 分桶
- Rich Live / 交互式 dashboard
- 跨 source baseline normalization

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TOOL-V2-04 | Per-tool regression guard with individual selection rate tracking dashboard | Wave 0 schema 扩展 (`raw_predictions` + `persist_raw_predictions`) 提供 distribution 数据；Wave 1-4 dashboard 渲染 LATEST/DIFF/TREND/ABStudy 四区 + warning 阈值 + dashboard.json 持久化 |

ROADMAP §Phase 16 的 3 条成功标准本研究全部覆盖：
1. metrics 文件记录 per-tool accuracy before/after — 由 D-12 schema 扩展 + 既有 `per_tool_*_rates`（Phase 13 落地的 evolve_tool_params）共同满足；evolve_tool_descriptions 老 run 走 dropped_runs fallback。
2. Rich console dashboard 显示 per-tool 选择率变化 — D-09 LATEST + D-15 ABStudy + D-16 频次柱图。
3. Regression 阈值可配（默认 2pp） — D-13 `--warning-threshold-pp`。

</phase_requirements>

## Summary

Phase 16 是一个**只读的观察工具**——不调用 LLM、不写回 hermes-agent、不参与 GEPA 决策路径，只把三条 evolve_tool_* 管道沉淀在 `output/tools/` 和 `output/tools_reasoning/` 下的 `metrics.json` + `ab_comparison.json` 数据聚合成可读的 Rich 表格 + JSON 报表。所有「怎么算」的逻辑（per-tool rate 计算、ambiguous 子集判定、cost / latency 跟踪）都在 Phase 13 / 15 已经落地；Phase 16 只做读取、切片、对比、渲染。

研究确认了三个关键事实：（1）现存的 17 个 reasoning runs + 1 个 desc FAILED run 都**没有** `raw_predictions` 字段——Wave 0 helper 是新代码而非接到既有调用点；（2）`persist_per_tool_rates` 当前**仅** `evolve_tool_params.py:1017` 调用，`evolve_tool_descriptions.py` 与 `evolve_tool_reasoning.py` 完全没接——这意味着所有 desc 老 run、所有现存 reasoning run 在 Phase 16 启动时都会落入 `dropped_runs[]`（只有 Phase 13 之后跑过的 params runs 能正常进入 LATEST/DIFF/TREND），CONTEXT D-08 fallback 路径是真实主路径不是边角；（3）Rich 15.0.0 没有 sparkline 原语，必须手工拼 `▁▂▃▄▅▆▇█`，而 `rich.bar.Bar` 嵌入 Table 列时会被列宽自适应挤死，**频次柱图必须放在表底单独的 Panel/Group 里而不是当 Table 列**。

**Primary recommendation:** Wave 0 helper 接线必须**同时**在三个 CLI 上一次性补齐：evolve_tool_descriptions / evolve_tool_reasoning 同步加 `persist_per_tool_rates(...)` + `persist_raw_predictions(...)` 两行（不是只加 raw_predictions），否则 Phase 16 dashboard 启动时 90% 的 run 仍然 dropped。这与 16-CONTEXT.md 「Out of scope」的「不补 `per_tool_*_rates` 到 evolve_tool_descriptions」**有冲突**——Open Question 1 提请讨论。

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 三 CLI 写入 `raw_predictions` 到 metrics.json | Pipeline-side (evolve_tool_*.py) | Helper module (tool_metric.py) | 数据生产者就近持久化；helper 提供不可变 merge 模式，CLI 只调一行 |
| 跨 run 扫描 + mtime 排序 | Dashboard CLI (regression_dashboard.py) | — | pathlib.Path.glob + stat().st_mtime 即可，无需独立服务 |
| Per-run distribution 切片（语义 A） | Dashboard CLI | Helper functions in dashboard module | 纯内存 dict + collections.Counter；不引 pandas |
| Cross-run sparkline 序列（语义 B） | Dashboard CLI | — | 同上，无新依赖 |
| Source 启发判定（desc/params/reasoning） | Dashboard CLI | metrics.json field schema | 字段集判定 (think_ab_gate / param_predictors_discovered) → 目录名 fallback |
| Warning 渲染 + 颜色编码 | Dashboard CLI | Rich style system | 复用 Rich 内置 logging.level.warning (yellow) / error (bold red) 语义 |
| Secret redaction（ABStudy task_description / reasoning_text_on 截断前） | Dashboard CLI | `_contains_secret` (external_importers.py) | 已有函数复用；二次 re-render 谨慎 |
| dashboard.json 持久化 | Dashboard CLI | — | json.dumps with sort_keys=True；落 CWD |

## Existing Code Survey

### `evolution/tools/tool_metric.py` — Helper 模板（必读，Wave 0 镜像）

- **Lines 442-477**：`persist_per_tool_rates(metrics, baseline_rates, evolved_rates) -> dict` 是 Phase 16 `persist_raw_predictions` 的精确模板。模式细节：
  - `out = dict(metrics)` —— **shallow copy**，调用方可继续复用入参（Wave 0 测试必须 assert 入参未被 mutate）
  - `{k: float(v) for k, v in sorted((rates or {}).items())}` —— 每个值 `float()` 强转 + 按 key 字典序排序，跨 run diff 稳定
  - `(rates or {})` —— None 容错
  - 返回新 dict，包含**所有原有 keys + 两新 key**
- **Lines 80-195**：`CrossToolRegressionChecker.compute_per_tool_rates(predictions: list[tuple[str, str]]) -> dict[str, float]` —— Phase 16 dashboard 端**不重新实现**，从 metrics.json 直接读 `per_tool_baseline_rates` / `per_tool_evolved_rates`。
- **Lines 26-53**：`tool_selection_metric()` 5-param signature，dashboard 不调；仅作为「dashboard 不使用 metric / fitness 模块」的边界证明。

### `evolution/tools/evolve_tool_params.py` — 唯一已接 persist_per_tool_rates 的 CLI

- **Line 75 import**：`from evolution.tools.tool_metric import persist_per_tool_rates, ...`
- **Lines 343-433** `_evaluate_holdout(module, holdout, lm)`：循环结构是 Wave 0 在三 CLI 都需要的接线参考。返回 `(score, tool_pairs, param_pairs)`，其中 `tool_pairs: list[tuple[str, str]]` 即 `(correct_tool, selected_tool)`。
- **Lines 1012-1017** Wave 0 接线点：
  ```python
  regression_checker = CrossToolRegressionChecker()
  baseline_rates = regression_checker.compute_per_tool_rates(baseline_tool_pairs)
  evolved_rates = regression_checker.compute_per_tool_rates(evolved_tool_pairs)
  regression_result = regression_checker.check_regression(baseline_rates, evolved_rates)
  metrics = persist_per_tool_rates(metrics, baseline_rates, evolved_rates)
  ```
  Phase 16 在此**之后**插入：`metrics = persist_raw_predictions(metrics, raw_predictions_list)`。

  **Per-prediction 数据可得性**：line 343-432 的循环里 `ex` 是 `dspy.Example`（含 `correct_tool`、`correct_params`、`confuser_tools`），`pred` 是 `dspy.Prediction`（含 `selected_tool`、`selected_params`），都在同一作用域。需要补的是 `difficulty` 与 `num_available_tools`：
  - `difficulty` —— `to_dspy_examples()` 在 `tool_dataset.py:135-158` 中**没有把 `difficulty` 装进 `dspy.Example`**！只装了 `task_description / correct_tool / correct_params / confuser_tools`。Wave 0 必须**先扩 `to_dspy_examples`** 把 `difficulty` + `pool_size`（或 raw `available_tools`）加进 dspy.Example，再接线。
  - `num_available_tools` —— ToolModule.forward 时拼 available_tools 字符串使用所有 tools，所以严格意义上 dataset example 自带的 `confuser_tools + [correct_tool]` 是「设计期合法候选数」而不是「运行时可见 tool 数」。CONTEXT D-11 「`num_available_tools` = `len(example.available_tools)`」的描述与现有 `ToolSelectionExample` 字段不匹配——dataset 没有 `available_tools` 字段，只有 `confuser_tools`。**planner 必须 pin 死 num_available_tools 的真实数据来源** —— 见 Open Question 2。

### `evolution/tools/evolve_tool_descriptions.py` — 老 CLI（Wave 0 接线缺口最大）

- **Lines 326-369** holdout 评估：手写 `for ex in holdout_examples: bp = baseline_module(...); ep = optimized_module(...)`，**不调** `persist_per_tool_rates`。Wave 0 接线必须把 line 352-354 的 rates 计算结果传给 `persist_per_tool_rates(metrics, ...)` 并 merge 进 line 407 的 metrics dict。
- **Lines 407-422** metrics dict 写入：当前字段集 = `{timestamp, iterations, eval_model, baseline_score, evolved_score, improvement, tool_count, train_examples, val_examples, holdout_examples, elapsed_seconds, constraints_passed, session_source}`。**无 `optimizer_used`**——D-07 的 source 启发不能依赖此字段。
- **判定**：所有现存 desc runs（output/tools/FAILED_20260422_201215 + 任何未来未接线的）都缺 `per_tool_*_rates` → 必入 `dropped_runs[]`。

### `evolution/tools/evolve_tool_reasoning.py` — Phase 15 CLI（Wave 0 接线缺口）

- **Lines 463-471** holdout 评估：`th_off_full = _safe_score(baseline_module, eval_holdout, lm)` 等四次评分**只算 mean float**，没有暴露 per-prediction 列表给后续 persist。Wave 0 必须重构 `_safe_score` 或新加一个 `_score_with_predictions` 返回 `(score, predictions_list)`。
- **Lines 514-555** metrics dict assembly：字段集**有** `think_ab_gate`、`param_predictors_discovered`、`optimizer_used` —— D-07 source 启发可用 `think_ab_gate ∈ keys` → reasoning。
- **Lines 697-764** `_build_ab_comparison`：已经在每个 holdout 例上计算 `pred_off / pred_on / sel_off / sel_on / is_correct_off / is_correct_on / confuser_tools / reasoning_text_on / reasoning_tokens_on / latency_seconds_*`。这是 **Wave 0 的金矿**——`raw_predictions` 字段 80% 数据已经在内存里，只是没被持久化到 metrics.json。Wave 0 应该把 ab_comparison 的 `pred_on` 路径也复用到 `raw_predictions`（避免双跑）。
- **Lines 75 + 568-571**：`OUTPUT_ROOT = Path("output") / "tools_reasoning"`；FAILED 走 `FAILED_<ts>/`，正常 `<ts>/` —— 与 Phase 5 的 `output/tools/<ts>/` 格式一致，Phase 16 glob 模式 `<root>/*/metrics.json` 可同时命中（FAILED_ 前缀的 run 也会被 dashboard 扫到，需在 dropped_runs 里说明跳过原因——见 Failure Modes）。

### `evolution/tools/tool_dataset.py:33-77` — ToolSelectionExample

- **现有字段**（实测）：`task_description / correct_tool / correct_params / difficulty / confuser_tools / reason / source / misselection_signals`
- **关键缺失**：**没有 `available_tools` 字段**——D-11 的 `num_available_tools = len(example.available_tools)` 不能直接对应到字段读取。
- `difficulty: str = "medium"` —— 实测 holdout 81 例分布 `Counter({'medium': 34, 'easy': 29, 'hard': 18})`，三桶都有但 hard 偏少（18 例）。
- `confuser_tools: list[str]` —— 实测 holdout 分布 `Counter({3: 38, 4: 33, 1: 6, 5: 3, 2: 1})`，几乎全部例子的 confuser_tools 长度在 3-5 之间。如果 D-11 的 `pool_size = len(confuser_tools) + 1`（含 correct），实际值域是 2 / 4-6 / 7（大致全部落 4-7 桶），Phase 16 默认分桶 `1-3 / 4-7 / 8+` 会让 holdout 几乎所有例子集中到 4-7 桶 —— sample size 警告（见 Sample Size 节）。
- **Lines 135-158** `to_dspy_examples()`：当前**只**把 `task_description / correct_tool / correct_params / confuser_tools` 装进 dspy.Example —— Wave 0 必须扩这里加 `difficulty`，否则 dashboard 内分桶切片拿不到 difficulty 数据。

### `evolution/core/external_importers.py:108-121` — `_contains_secret`

- 签名：`_contains_secret(text: str) -> bool`
- 实现：（1）`SECRET_PATTERNS.search(text)` 模式匹配（2）Shannon entropy heuristic（24+ 字符 base64-like token，阈值见 `_SECRET_ENTROPY_THRESHOLD`）。
- **Phase 16 ABStudy 渲染 task_description / reasoning_text_on 截断前应过这一道**：
  ```python
  if _contains_secret(text):
      text = "[REDACTED — secret-like content]"
  else:
      text = text[:80] + "..." if len(text) > 80 else text
  ```
- 注意：`_contains_secret` 是模块级函数；从 `evolution.core.external_importers import _contains_secret` 即可，不需要新公开 API。下划线前缀只是惯例不是强约束。

### `output/tools_reasoning/<ts>/metrics.json` 实际样例（Phase 15 mock test runs）

字段集（实测自 `output/tools_reasoning/20260512_150748/metrics.json`，**全部 17 个 reasoning runs 字段集相同**）：
```
ambiguous_gate_skipped, ambiguous_subset_size, ambiguous_think_off, ambiguous_think_on,
cost_usd_cap, cost_usd_spent, elapsed_seconds, eval_model, holdout_examples, iterations,
latency_stats {mean, p50, p95}, optimizer_used, param_predictors_discovered,
reasoning_token_stats {mean, p50, p95}, reflection_model, started_at, status,
think_ab_gate {ambiguous_*, evolved_scores, gates, latency_p95_seconds, message,
               passed, tolerances, full_regression_delta},
think_off_score, think_on_score, timestamp, tool_count, train_examples,
v1_baseline_holdout, v1_baseline_source, v1_gate_delta_think_off,
v1_gate_delta_think_on, v1_gate_passed, v1_score, val_examples
```
**关键确认**：
- 含 `think_ab_gate` ✓ → D-07 reasoning 启发可用
- 含 `param_predictors_discovered` ✓ → 但与 reasoning 共享，所以判定顺序必须是 **先 think_ab_gate，再 param_predictors_discovered**
- 含 `optimizer_used` ✓ → 但 desc 没有，不能作为 desc 的正向标识
- **不含 `per_tool_baseline_rates` / `per_tool_evolved_rates`** —— 现存 17 reasoning runs **全部** dropped
- **不含 `raw_predictions`** —— Wave 0 之后才有

### `output/tools_reasoning/<ts>/ab_comparison.json` 实际样例

字段（实测）：
```json
{
  "task_id": int,
  "task_description": str,
  "correct_tool": str,
  "selected_off": str,
  "selected_on": str,
  "is_correct_off": bool,
  "is_correct_on": bool,
  "is_ambiguous": bool,
  "confuser_tools": list[str],
  "reasoning_text_on": str,
  "reasoning_tokens_on": int,
  "latency_seconds_off": float,
  "latency_seconds_on": float
}
```
**完整覆盖** D-15 ABStudy 所需字段。三类计数推导：
- `think_on_saved` = `is_correct_off == False AND is_correct_on == True`
- `think_on_regressed` = `is_correct_off == True AND is_correct_on == False`
- `both_wrong` = `is_correct_off == False AND is_correct_on == False`

### `output/tools/FAILED_20260422_201215/metrics.json` —— 唯一现存 desc run

字段集（实测）：`{timestamp, status: "FAILED", constraints_passed: false}` —— **完全无法用**。dropped_runs 必中。这进一步确认 Wave 0 接线缺口的紧迫性。

### `tests/tools/test_cross_tool_regression.py` —— Phase 13 helper test 模板

实测在 `tests/tools/test_cross_tool_regression.py` 而**不是** `test_persist_per_tool_rates.py`（CONTEXT 的「test_persist_per_tool_rates.py 文件结构对称」表述与实际不符）。文件结构（80 行单测 1 个）：
- `pytest.importorskip("dspy")` 防御
- `from evolution.tools.tool_metric import persist_per_tool_rates`
- 准备 `metrics`、`baseline_rates`、`evolved_rates` 三个 dict
- 调用 helper，断言：（1）两新 keys 存在（2）值类型 `dict[str, float]`（3）原始 metrics keys 保留

Phase 16 Wave 0 测试**应放同一文件**（`test_cross_tool_regression.py` 追加测试函数）或新建 `test_persist_raw_predictions.py`（与 helper 模式对称），planner 决定。建议新建以保持单一职责。

### `tests/tools/conftest.py` —— Phase 15 fixture 模板

- `fake_tools` fixture 提供两个最小 ToolDescription
- `mock_reasoning_module` fixture 用 MagicMock 包 LM
- 文件位置：`tests/tools/conftest.py` —— Phase 16 dashboard 测试 fixture（fixture 文件 vs inline string）继承此模式

### `tests/fixtures/sessions/*.json` —— 仓库 fixture 数据放置惯例

- 实测路径：`tests/fixtures/sessions/{malformed_msg, secret_in_user_msg, multi_signal, ...}.json`
- **结论**：仓库**有** fixture 文件夹惯例（`tests/fixtures/<domain>/*.json`），Phase 16 测试用的 fixture metrics.json / ab_comparison.json **应放** `tests/fixtures/dashboard_runs/<scenario>/metrics.json` 而非 inline string，便于复用 + diff。

### `evolution/tools/mine_tool_sessions.py:347` `--signals`

CONTEXT 的「`--runs` 多次出现累加（`multiple=True`）的风格与 Phase 14 的 `--signals` 类似」与实际不符 —— `--signals` 是**单值 CSV** + 自定义 `_parse_signals` 解析，不是 `multiple=True`。Phase 16 的 `--runs` 应**直接用** `multiple=True`（已用 `Bash` 实测 Click 8.1.8 行为：`--runs a --runs b --runs c` → `('a', 'b', 'c')`，空时 `()`），语义更顺。

## Library API

### Rich 15.0.0 (`.venv/lib/python3.13/site-packages/rich/`)

- **`rich.console.Console`** —— 主 sink。已被 `tool_metric.py / evolve_tool_*.py / tool_dataset.py` 等多处用 module-level `console = Console()` —— Phase 16 沿用同模式。
- **`rich.table.Table`** —— LATEST/DIFF/TREND 三区主体。`add_column(header, justify, style, no_wrap)` + `add_row(*cells)`。
- **`rich.panel.Panel`** —— ABStudy 区 + source legend + dashboard summary header 适用。
- **`rich.bar.Bar`**（实测 `from rich.bar import Bar`）：
  ```
  Bar(size: float, begin: float, end: float, *, width: Optional[int]=None,
      color='default', bgcolor='default')
  ```
  渲染单一实心横向块。**实测踩坑**：嵌入 `Table` 单元格时，Bar 的 `width=None` 行为是「列宽自适应」，但当 Table 还有其他 fixed-width 列时（tool name + count），Bar 列会被挤到 0 宽显示空白——见 demo 中 `┃┃┃ bar` 的奇怪表头与压扁块。**结论：D-16 频次柱图必须放在 LATEST Table 之外的独立 Group / Panel 中**，不能当 Table 列。推荐结构：
  ```
  ┌─ LATEST [params] @ output/tools/20260512_103000 ─┐
  │ Tool         | rate  | delta_pp | sample | ...   │  ← Rich Table
  └──────────────────────────────────────────────────┘
  ┌─ Sample frequency ───────────────────────────────┐
  │ search_files       ████████████████ 437          │  ← rendered as text
  │ read_file          ███████████ 312               │     (each line: name + Bar via Console.print(Group(Text, Bar)))
  │ ... (top 12)                                      │
  │ others (38 tools)  █████ 234                     │
  └──────────────────────────────────────────────────┘
  ```
- **Sparkline**：**Rich 没有内置 sparkline**（实测 `from rich import sparkline` → ImportError）。手工拼 Unicode block elements `▁▂▃▄▅▆▇█` (U+2581..U+2588)。25 行实现：
  ```python
  _SPARK_CHARS = "▁▂▃▄▅▆▇█"
  def sparkline(values: list[float]) -> str:
      if not values:
          return ""
      lo, hi = min(values), max(values)
      span = (hi - lo) or 1.0
      return "".join(_SPARK_CHARS[min(7, int((v - lo) / span * 8))] for v in values)
  ```
- **语义 styles**（实测 `rich.default_styles.DEFAULT_STYLES`）：
  - `logging.level.warning` → `yellow`
  - `logging.level.error` → `bold red`
  - `logging.level.info` → `blue`
  - `logging.level.debug` → `green`

  Phase 16 颜色映射建议：
  | Status | Style key (推荐) | 等效 Rich style |
  |--------|------------------|-----------------|
  | OK     | (默认)           | none |
  | WARN (delta ≤ -2pp) | `yellow` | `yellow` |
  | FAIL (delta ≤ -5pp) | `bold red` | 复用 `logging.level.error` |
  | GAIN (delta ≥ +5pp) | `bold green` | `bold green` |

  使用 inline markup（`f"[{style}]{text}[/{style}]"`）即可，无需注册自定义 theme。

### Click 8.1.8 (`.venv/lib/python3.13/site-packages/click/`)

- **`@click.option('--runs', multiple=True, type=click.Path())`** —— 实测 `--runs a --runs b --runs c` → 闭包内 `runs = ('a', 'b', 'c')`；空时 `runs = ()`。**Phase 16 推荐写法**。
- **`type=click.Path(exists=False, file_okay=False, dir_okay=True)`** —— 不强制存在（dashboard 启动时再 expand glob，未存在 → 走 dropped_runs）。
- **`raise click.UsageError("...")`** —— 输出红色错误 + exit 2。CONTEXT 多处「stdout 报错并 exit 2」用此。
- **`click.testing.CliRunner`** —— 与 `unittest.mock.patch` 搭配是仓库内 `test_evolve_tool_params_cli.py:64` 的 fixture 模式：
  ```python
  runner = CliRunner()
  with patch('evolution.tools.regression_dashboard._scan_runs', return_value=[fake_run]):
      result = runner.invoke(main, ['--runs', '/fake/run1'], catch_exceptions=True)
  assert result.exit_code == 0
  assert 'LATEST' in result.output
  ```

### DSPy 3.1.3

**Phase 16 完全不调 LLM** —— 不引 dspy，import 不必要。dashboard 既不用 dspy.Module 也不用 dspy.LM。Wave 0 helper `persist_raw_predictions` 也是纯 dict 操作（不 import dspy）。Wave 0 三 CLI 接线点的 dspy 依赖来自既有代码不受 Phase 16 影响。

## Schema & Data Flow

### `metrics.json` 现状对照表（Wave 0 之前 / 之后）

| 字段 | desc CLI（evolve_tool_descriptions） | params CLI（evolve_tool_params） | reasoning CLI（evolve_tool_reasoning） |
|------|------|------|------|
| `timestamp` | ✓ | ✓ | ✓ |
| `baseline_score` / `evolved_score` | ✓ | ✓ | （`think_off_score` / `think_on_score` 替代） |
| `optimizer_used` | ✗ | ✓ | ✓ |
| `param_predictors_discovered` | ✗ | ✓ | ✓ |
| `think_ab_gate` | ✗ | ✗ | ✓ |
| `per_tool_baseline_rates` / `per_tool_evolved_rates` | **✗ (Wave 0 必补)** | ✓ (Phase 13) | **✗ (Wave 0 必补)** |
| `raw_predictions`（**Phase 16 新字段**） | **✗ (Wave 0 必补)** | **✗ (Wave 0 必补)** | **✗ (Wave 0 必补)** |

### D-07 source 启发判定决策树（基于实测字段集）

```
def detect_source(metrics_dict, run_path: Path) -> Optional[str]:
    if "think_ab_gate" in metrics_dict:
        return "reasoning"
    if "param_predictors_discovered" in metrics_dict:
        return "params"
    # desc CLI 没有可靠 positive marker — 走目录名 fallback
    parent_root = run_path.parent.parent.name  # output/tools | output/tools_reasoning
    if parent_root == "tools_reasoning":
        return "reasoning"  # 防御：即使 metrics 字段不全也按目录归类
    if parent_root == "tools":
        # 同时确认 metrics 至少有 baseline_score（防误命中其他子目录）
        if "baseline_score" in metrics_dict:
            return "desc"
    return None  # 未知 source → dropped_runs[reason="unknown source"]
```

### `raw_predictions` 字段精确 schema（D-12 Claude's Discretion，建议 planner pin 死）

```json
{
  "raw_predictions": [
    {
      "correct_tool": "search_files",
      "selected_tool": "search_files",
      "difficulty": "medium",
      "num_available_tools": 4
    },
    ...
  ]
}
```

**字段语义**：
- `correct_tool: str` —— 来自 `example.correct_tool`，从未为 None / "" （现有数据集所有 81 holdout 例都填了 correct_tool）。
- `selected_tool: str` —— 来自 `prediction.selected_tool`，**可能为空字符串**（LM 失败 / 解析失败时）但**不应为 None**（CLI 接线时用 `getattr(pred, 'selected_tool', '') or ''` 兜底，与 evolve_tool_params.py:415 一致风格）。
- `difficulty: str` —— 必为 `"easy" | "medium" | "hard"`（来自 `ToolSelectionExample.difficulty` enum，VALID_DIFFICULTIES = `{'easy', 'medium', 'hard'}`）。Wave 0 必须**先扩 `to_dspy_examples`**（`tool_dataset.py:135-158`）把 `difficulty` 装进 dspy.Example，否则 holdout 循环里拿不到。
- `num_available_tools: int` —— 见 Open Question 2，planner 必须在 Wave 0 测试前 pin 死定义。

### `persist_raw_predictions` 函数签名草稿（Wave 0 helper）

```python
def persist_raw_predictions(
    metrics: dict,
    raw_predictions: list[dict],
) -> dict:
    """Merge raw_predictions list into a metrics dict.

    Pattern matches persist_per_tool_rates (D-12 symmetry):
    - Does NOT mutate inputs (returns shallow copy of metrics)
    - Coerces every record to a clean {correct_tool, selected_tool, difficulty,
      num_available_tools} dict (no extra keys leak through, schema stable)
    - Preserves prediction order (do NOT sort — temporal order matters for debug)
    """
    out = dict(metrics)
    cleaned: list[dict] = []
    for rec in (raw_predictions or []):
        cleaned.append({
            "correct_tool": str(rec.get("correct_tool", "") or ""),
            "selected_tool": str(rec.get("selected_tool", "") or ""),
            "difficulty": str(rec.get("difficulty", "medium") or "medium"),
            "num_available_tools": int(rec.get("num_available_tools", 0) or 0),
        })
    out["raw_predictions"] = cleaned
    if len(cleaned) > 2000:
        # Pitfall 10 retention placeholder — print to stderr-equivalent Rich
        # console (warning style). DO NOT raise / truncate (data integrity > size).
        from rich.console import Console
        Console().print(
            f"[yellow]raw_predictions large ({len(cleaned)} records); "
            f"metrics.json may exceed 1MB[/yellow]"
        )
    return out
```

**与 `persist_per_tool_rates` 模式差异**：
- 不 sort（per_tool_rates 按 key 排是为了跨 run diff 稳定；raw_predictions 是顺序敏感的时间序列）
- 不全部 float 强转（每字段类型不同——str / str / str / int）
- 加了 size warning（D-15 specifics 提到的「list 长度 >2000 时 stdout warning」）

### `dashboard.json` 顶层 schema 草案（Claude's Discretion，CONTEXT specifics 已给出，planner 微调）

```json
{
  "generated_at": "ISO 8601 UTC",
  "scanned_runs": int,
  "dropped_runs": [{"path": str, "reason": str}],
  "source_legend": {"desc": str, "params": str, "reasoning": str},
  "latest": {"run_path": str, "source": "desc|params|reasoning", "per_tool": [...]},
  "diff": {"baseline_run": str, "evolved_run": str, "per_tool": [...]} | null,
  "trend": {"window_kind": "n|days", "window_value": int, "tools": [...]},
  "ab_study": {"detected_runs": int, "by_run": [...]} | null,
  "warnings": [{"tool": str, "delta_pp": float, "run_path": str}],
  "summary": {"warning_threshold_pp": float, "segment_kind": str}
}
```

## Failure Modes

### 老 run fallback 路径（D-08 三类）

| Scenario | 行为 | dashboard.json 体现 |
|----------|------|---------------------|
| 缺 `per_tool_baseline_rates` / `per_tool_evolved_rates` | **整 run 跳过**，stdout `[yellow]` warning | `dropped_runs[]` 含 `{path, reason: "missing per_tool_*_rates"}` |
| 缺 `raw_predictions`（老 params run，所有 desc/reasoning run 在 Wave 0 之前的） | **distribution 列退化为 `n/a`**，stdout 一行 yellow 提示 | `latest.per_tool[].distribution = null`；warning 不计入 regression |
| 缺 `ab_comparison.json`（仅 reasoning source 必须） | ABStudy 区**该 run 不渲染**，stdout 不抱怨 | `ab_study.by_run` 不含此 run；`ab_study.detected_runs` 计数不增 |
| FAILED_<ts>/ 前缀目录被 glob 命中 | dashboard 的 glob `<root>/*/metrics.json` 会扫到 `FAILED_*/metrics.json`；`status="FAILED"` → 整 run 跳过 | dropped_runs 含 `{path, reason: "run status=FAILED"}` |
| `metrics.json` 解析失败（坏 JSON / 文件被截断） | try/except → 跳过 | dropped_runs `{path, reason: "json parse error: <msg>"}` |
| 同时传 `--trend-window` + `--trend-days` | `click.UsageError` → exit 2 | 不生成 dashboard.json |
| 默认根 + `--runs` 都为空 | stdout 错误 + exit 2 | 不生成 dashboard.json |
| `--baseline-run` / `--evolved-run` 仅传一个 | DIFF 区不渲染（视为「未启用 DIFF」），stdout 黄色 hint；不 abort | dashboard.json `diff: null` |

### CLI 错误码约定

| 退出码 | 触发场景 |
|--------|----------|
| 0 | 正常完成（即使有 warnings） |
| 2 | usage error: 默认根空且无 --runs；--trend-window 与 --trend-days 同时传；--segment 值非法 |
| **不返 1** | D-13 明确：dashboard 不参与 CI 决策，warnings 不影响 exit code |

### Rich 渲染异常

- 终端宽度过窄时 Rich 自动 truncate；Phase 16 测试中应用 `Console(record=True, width=120)` 强制宽度，断言 stdout 含关键 text。
- ABStudy 区 task_description / reasoning_text_on 长文本：先过 `_contains_secret`，再 `text[:80] + "..."` 截断；Rich Table 的 `no_wrap=False`（默认）允许换行展示。
- CJK 字符宽度：CONTEXT pitfall（L1）已注。Rich 的 `cells.cell_len()` 处理东亚字符宽，无需额外代码。

### `output/` 与 dashboard.json 落点（CONCERNS §H4 重核）

实测 `.gitignore` 第 26-27 行：
```
# Per-run evolution outputs (may contain mined data / evolved artifacts)
output/
```
`output/` 已在 .gitignore（CONCERNS §H4 已被 Phase 12 commit 7500abc 修复）。

**Phase 16 dashboard.json 落点**：D-04 锁定「CWD」`dashboard_<YYYYMMDD_HHMMSS>.json`。Repo root 是常见 CWD —— **dashboard.json 会被 git status 看到**。建议 plan 中加一行 `.gitignore` 规则 `dashboard_*.json`（一句话改动，纳入 Wave 4）。

## Implementation Recipes

### Wave 0 — Schema + helper + 三 CLI 接线

**Files touched (4):**
- `evolution/tools/tool_metric.py` (+1 helper, ~40 LoC)
- `evolution/tools/tool_dataset.py` (extend `to_dspy_examples` to include `difficulty`, ~3 LoC change)
- `evolution/tools/evolve_tool_descriptions.py` (+`persist_per_tool_rates` + `persist_raw_predictions` calls, ~10 LoC)
- `evolution/tools/evolve_tool_params.py` (+`persist_raw_predictions` call after line 1017, ~5 LoC)
- `evolution/tools/evolve_tool_reasoning.py` (+`persist_per_tool_rates` + `persist_raw_predictions`, refactor `_safe_score` or add prediction collector, ~15 LoC)

**Tests:**
- `tests/tools/test_persist_raw_predictions.py` (新；4-6 测试函数：immutability / 空 list / 超长 list warning / 字段强转 / 缺键 fallback)
- `tests/tools/test_evolve_tool_*.py` 三 CLI 已有 test 加入 `assert "raw_predictions" in metrics`（小补丁）
- `tests/tools/test_to_dspy_examples_includes_difficulty.py`（新或追加到现有 `test_tool_dataset.py`）

**Helper signature**:
```python
# evolution/tools/tool_metric.py
def persist_raw_predictions(metrics: dict, raw_predictions: list[dict]) -> dict:
    ...  # 见 Schema 节
```

**Wave 0 接线模板**（适用于三 CLI）:
```python
# 在 holdout 循环内或之后构建 raw_predictions list:
raw_preds = []
for ex, pred in zip(holdout_examples, predictions):
    raw_preds.append({
        "correct_tool": getattr(ex, "correct_tool", "") or "",
        "selected_tool": getattr(pred, "selected_tool", "") or "",
        "difficulty": getattr(ex, "difficulty", "medium") or "medium",
        "num_available_tools": len(getattr(ex, "confuser_tools", []) or []) + 1,  # +1 for correct
    })
metrics = persist_raw_predictions(metrics, raw_preds)
```

### Wave 1 — Dashboard CLI 骨架 + LATEST 区

**File:** `evolution/tools/regression_dashboard.py`（新，~250 LoC 估算）

```python
# evolution/tools/regression_dashboard.py
import json
from datetime import datetime
from pathlib import Path
from typing import Optional
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.bar import Bar
from rich.text import Text

console = Console()

DEFAULT_ROOTS = (Path("output") / "tools", Path("output") / "tools_reasoning")
_SPARK_CHARS = "▁▂▃▄▅▆▇█"

def _scan_runs(roots: tuple[Path, ...]) -> list[Path]:
    """Glob <root>/*/metrics.json, sorted by mtime ascending."""
    found: list[Path] = []
    for root in roots:
        if root.exists():
            found.extend(root.glob("*/metrics.json"))
    return sorted(found, key=lambda p: p.stat().st_mtime)

def _load_run(metrics_path: Path) -> Optional[dict]:
    """Return dict of {path, source, metrics, ab_comparison?} or None on parse error."""
    ...

def _detect_source(metrics: dict, run_path: Path) -> Optional[str]:
    """D-07 启发判定 — 见 Schema 节."""
    ...

def _segment_distribution(raw_preds: list[dict], segment: str) -> dict[str, dict]:
    """Per-tool, per-segment evolved_rate quintiles. Returns {tool: {min, p25, ...}}."""
    ...

def _render_latest(run: dict, segment: str, console: Console) -> dict:
    """Render LATEST Rich Table + frequency bar Panel; return latest dict for JSON."""
    ...

def _render_frequency_bars(per_tool_counts: dict[str, int], console: Console) -> None:
    """D-16: top-12 + 'others (N tools)' aggregate; rendered as Console.print rows."""
    ...

@click.command()
@click.option("--runs", "runs", multiple=True, type=click.Path(),
              help="Run directory (repeatable; appends to default roots)")
@click.option("--baseline-run", default=None, type=click.Path(),
              help="DIFF baseline run (must be paired with --evolved-run)")
@click.option("--evolved-run", default=None, type=click.Path(),
              help="DIFF evolved run")
@click.option("--trend-window", default=None, type=int,
              help="TREND: most recent N runs (default 10; mutex with --trend-days)")
@click.option("--trend-days", default=None, type=int,
              help="TREND: runs from past D days (mutex with --trend-window)")
@click.option("--segment", default="difficulty",
              type=click.Choice(["difficulty", "pool_size", "none"]),
              help="Distribution segment dimension (D-11)")
@click.option("--warning-threshold-pp", default=2.0, type=float,
              help="Per-tool delta threshold for yellow warning (D-13)")
@click.option("--output", default=None, type=click.Path(),
              help="dashboard.json path (default: ./dashboard_<ts>.json)")
def main(runs, baseline_run, evolved_run, trend_window, trend_days, segment,
         warning_threshold_pp, output):
    """Per-tool regression dashboard for evolve_tool_* pipelines."""
    if trend_window is not None and trend_days is not None:
        raise click.UsageError("--trend-window and --trend-days are mutually exclusive")
    # ... (orchestration: scan → load → render LATEST → render DIFF? → render TREND
    #      → render ABStudy? → emit warnings → write JSON)
```

### Wave 2 — DIFF + TREND + sparkline

- DIFF: 复用 `_render_latest` 的 per-tool 行结构，加 `delta_baseline → delta_evolved` 两侧列。
- TREND: 按工具聚合时间序列 → 生成 sparkline + min/p25/median/p75/max 摘要列。
- 关键函数：
  ```python
  def _quintiles(values: list[float]) -> dict[str, float]:
      """Return {min, p25, median, p75, max}; uses statistics.quantiles."""
      ...
  def _sparkline(values: list[float]) -> str:
      """8-char Unicode block sparkline."""
      ...
  ```

### Wave 3 — ABStudy + source 标注 + 老 run fallback

- 扫描 reasoning runs 同目录下 `ab_comparison.json`：`run_dir / "ab_comparison.json"`
- 三类计数 + top-3 例子（按 D-15 ABStudy 排序键）
- ABStudy 渲染前每条 task_description / reasoning_text_on 调 `_contains_secret`
- source legend Panel: 表头脚注「desc/params source 的 baseline = v1 frozen；reasoning source 的 baseline = think-off」
- dropped_runs 累加到 dashboard.json + stdout summary 一行

### Wave 4 — dashboard.json schema 收口 + 集成测试

- 完整 dashboard.json 序列化（顶层字段见 Schema 节）
- E2E 测试：fixture 5 个 run（2 desc 老 dropped / 1 params 完整 / 2 reasoning 完整含 ab_comparison）→ 跑完整 CLI → 断言 stdout 含「LATEST / DIFF / TREND / ABStudy / dropped_runs」+ dashboard.json 含全部 8 个顶层字段
- `.gitignore` 加 `dashboard_*.json`

## Open Questions

1. **Wave 0 是否同时给 evolve_tool_descriptions / evolve_tool_reasoning 补 `persist_per_tool_rates`？**
   - **What we know**：CONTEXT D-12 「dashboard 仅读 + Phase 16 新增 raw_predictions」+ Out of scope「不补 `per_tool_*_rates` 到 evolve_tool_descriptions」。
   - **What's unclear**：但 D-08 fallback「缺 `per_tool_*_rates` → 整 run 跳过」叠加现实「desc + reasoning 老 CLI 完全没接 `persist_per_tool_rates`」 → Phase 16 启动时 90% 的 run 直接落入 dropped_runs[]，dashboard 几乎只能看到 Phase 13 落地后的 params runs。这违背 D-17 Wave 0 「数据基础」的设计意图。
   - **Recommendation**：planner 在 Wave 0 决策时确认「`persist_per_tool_rates` 接线」与 `persist_raw_predictions` 接线**绑定一起做**（成本几乎为零——同一处 holdout 循环之后多调一行）。如果用户坚持 Out of scope 严格「只加 raw_predictions」，dashboard 在前 1-2 周生产期内会几乎只显示 dropped_runs 列表，体验受损。**建议在 discuss-phase 阶段提出 amend D-08 / Out of scope 第 6 条**。

2. **`num_available_tools` 的真实数据来源是什么？**
   - **What we know**：CONTEXT D-11「`num_available_tools` = `len(example.available_tools)`」，但实测 `ToolSelectionExample` 字段集是 `{task_description, correct_tool, correct_params, difficulty, confuser_tools, reason, source, misselection_signals}` —— **没有 `available_tools` 字段**。
   - **What's unclear**：D-11 的 `num_available_tools` 实际指：
     - (a) `len(confuser_tools) + 1`（设计期合法候选数，含 correct） —— 实测 holdout 81 例分布在 2-6 之间，**绝大多数落 4-7 桶**。
     - (b) ToolModule.forward 时 selector 实际看到的 tool count（runtime 全部 tools 数，~50） —— 这个值在 dataset example 上不存在，需要从 ToolModule 上读；且每条 example 都是同样数字（无区分度）。
     - (c) 新加 `available_tools` 字段到 `ToolSelectionExample` —— 与 Out of scope「只补 raw_predictions」冲突。
   - **Recommendation**：planner pin 死定义 (a) `num_available_tools = len(confuser_tools) + 1`。这是唯一不需扩字段的解。但必须警告用户：默认分桶 `1-3 / 4-7 / 8+` 在当前 holdout 上是「全集中 4-7 桶」（Sample size 警告），dashboard 默认 segment=difficulty 比 segment=pool_size 更有信息量。建议**默认 segment 改 `difficulty`**（CONTEXT 已默认 difficulty —— 一致）。

3. **Wave 0 加 `persist_raw_predictions` 时是否需要在 `_evaluate_holdout` 返回签名上加第 4 元素？**
   - **What we know**：`evolve_tool_params.py:343-432 _evaluate_holdout` 当前返回 `(score, tool_pairs, param_pairs)`。
   - **What's unclear**：planner 选择两条路：(a) 在原签名上加 `raw_predictions_records: list[dict]` 第 4 元素 —— 涉及调用点改动 + 测试改 mock；(b) 在 holdout 循环外**重新跑一次**只为收集 raw_predictions —— 简单但 cost 翻倍。
   - **Recommendation**：(a) 加第 4 元素返回值。Wave 0 测试现在 patch 了 `_evaluate_holdout` 的话只要 update mock。或者更干净：(c) **保留 `_evaluate_holdout` 签名不变**，让 helper 层从 `tool_pairs` + holdout examples zip 出 raw_predictions（需要把 holdout list 也传给 helper）。

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All | ✓ | 3.13.3 (`.venv/`) | — |
| Rich | dashboard rendering | ✓ | 15.0.0 | — |
| Click | CLI | ✓ | 8.1.8 | — |
| pytest | tests | ✓ | (declared >=7.0) | — |
| DSPy | Wave 0 CLI 接线（既有 import） | ✓ | 3.1.3 | — |
| `output/tools/` 实数据 | Source 启发判定测试 | partial | 1 个 FAILED run | 用 fixture metrics.json 模拟 |
| `output/tools_reasoning/` 实数据 | ABStudy + source 启发 | ✓ | 17 mock test runs | 现有 runs 缺 per_tool_rates / raw_predictions → dropped 路径测试可直接用现存数据 |
| `datasets/tools/holdout.jsonl` | Wave 0 接线 difficulty 字段验证 | ✓ | 81 例 | — |

**所有依赖已就绪 — 无 blocking 缺失。**

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=7.0 + pytest-asyncio >=0.21 (declared in `pyproject.toml`) |
| Config file | `pyproject.toml [tool.pytest.ini_options]` |
| Quick run command | `.venv/bin/pytest tests/tools/test_persist_raw_predictions.py tests/tools/test_regression_dashboard.py -x` |
| Full suite command | `.venv/bin/pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TOOL-V2-04 / D-12 | `persist_raw_predictions` immutability + shape | unit | `pytest tests/tools/test_persist_raw_predictions.py::test_immutability_and_shape -x` | ❌ Wave 0 |
| TOOL-V2-04 / D-12 | `persist_raw_predictions` empty list / large list warning | unit | `pytest tests/tools/test_persist_raw_predictions.py::test_empty_and_large -x` | ❌ Wave 0 |
| TOOL-V2-04 / D-12 | `to_dspy_examples` includes `difficulty` | unit | `pytest tests/tools/test_tool_dataset.py::test_dspy_example_has_difficulty -x` | ❌ Wave 0 |
| TOOL-V2-04 / D-12 | evolve_tool_params holdout writes `raw_predictions` to metrics.json | integration | `pytest tests/tools/test_evolve_tool_params_cli.py::test_metrics_includes_raw_predictions -x` | ⚠ extend existing |
| TOOL-V2-04 / D-12 | evolve_tool_descriptions holdout writes `per_tool_*_rates` + `raw_predictions` | integration | `pytest tests/tools/test_evolve_tool_descriptions.py::test_metrics_includes_per_tool_and_raw -x` | ⚠ extend existing |
| TOOL-V2-04 / D-12 | evolve_tool_reasoning holdout writes `per_tool_*_rates` + `raw_predictions` | integration | `pytest tests/tools/test_evolve_tool_reasoning.py::test_metrics_includes_per_tool_and_raw -x` | ⚠ extend existing |
| TOOL-V2-04 / D-05+D-09 | dashboard LATEST renders per-tool rates + distribution | functional | `pytest tests/tools/test_regression_dashboard.py::test_latest_renders_per_tool_table -x` | ❌ Wave 1 |
| TOOL-V2-04 / D-16 | LATEST 频次柱图 top-12 + others 聚合 | functional | `pytest tests/tools/test_regression_dashboard.py::test_frequency_bars_aggregate_long_tail -x` | ❌ Wave 1 |
| TOOL-V2-04 / D-05+D-06 | DIFF 仅在 baseline+evolved-run 都传时启用 | functional | `pytest tests/tools/test_regression_dashboard.py::test_diff_requires_both_runs -x` | ❌ Wave 2 |
| TOOL-V2-04 / D-06 | TREND 同时传 --trend-window + --trend-days → exit 2 | functional | `pytest tests/tools/test_regression_dashboard.py::test_trend_window_days_mutex -x` | ❌ Wave 2 |
| TOOL-V2-04 / D-10 | TREND sparkline 字符序列 + 摘要列 | functional | `pytest tests/tools/test_regression_dashboard.py::test_trend_sparkline -x` | ❌ Wave 2 |
| TOOL-V2-04 / D-15 | ABStudy 三类计数 + top-3 排序 + secret redaction | functional | `pytest tests/tools/test_regression_dashboard.py::test_ab_study_categories_and_redaction -x` | ❌ Wave 3 |
| TOOL-V2-04 / D-07 | source 启发: think_ab_gate → reasoning, param_predictors → params, fallback → desc | functional | `pytest tests/tools/test_regression_dashboard.py::test_source_detection -x` | ❌ Wave 3 |
| TOOL-V2-04 / D-08 | 缺 per_tool_*_rates → dropped_runs / 缺 raw_predictions → distribution n/a / 缺 ab_comparison.json → ABStudy skip | functional | `pytest tests/tools/test_regression_dashboard.py::test_fallback_paths -x` | ❌ Wave 3 |
| TOOL-V2-04 / D-13 | warning threshold 触发 + 不影响 exit code | functional | `pytest tests/tools/test_regression_dashboard.py::test_warning_threshold_no_exit -x` | ❌ Wave 3 |
| TOOL-V2-04 / D-04+D-17 | E2E：5 fixture run → dashboard.json 8 顶层字段完整 | system | `pytest tests/tools/test_regression_dashboard.py::test_e2e_dashboard_json_schema -x` | ❌ Wave 4 |

### Sampling Rate
- **Per task commit:** `pytest tests/tools/test_persist_raw_predictions.py tests/tools/test_regression_dashboard.py -x`
- **Per wave merge:** `pytest tests/tools/ -v`
- **Phase gate:** `pytest tests/ -v` 全套通过 + 手动跑 `python -m evolution.tools.regression_dashboard` against 实数据观察 stdout

### Wave 0 Gaps
- [ ] `tests/tools/test_persist_raw_predictions.py` — 覆盖 D-12 helper（4-6 测试）
- [ ] `tests/tools/test_regression_dashboard.py` — 覆盖 Wave 1-4 dashboard 全部行为（15-20 测试）
- [ ] `tests/fixtures/dashboard_runs/` — fixture 数据：5 个模拟 run（`desc_old/metrics.json`、`params_complete/metrics.json` + `params_complete/raw_predictions`、`reasoning_complete/{metrics.json, ab_comparison.json}`、`reasoning_old/metrics.json`、`json_corrupt/metrics.json`）
- [ ] 现有 `tests/tools/test_evolve_tool_*.py` 三 CLI 测试加 Wave 0 字段断言（小补丁）

### Distribution Semantics 显式标注（Pitfall 10 收口）

dashboard 的 distribution 列必须**在表头脚注或 Panel legend 中显式说明**：
- **语义 A（LATEST/DIFF）**：「`min/p25/median/p75/max` 来自单 run 内按 `--segment` 切片后的 per-segment evolved_rate」
- **语义 B（TREND）**：「`min/p25/median/p75/max` 来自跨 N run 的同一工具 evolved_rate 时间序列」
- 不混用——两区不能用同一列标题不加说明。

## Sample Size 警告（Pitfall 10 + holdout 实数据）

**实测 holdout 81 例，按 correct_tool 分桶后 sample 分布**：
- top tool `browser_navigate` = 5 例
- 中段 tools 多为 3 例
- 长尾 tools 仅 1-2 例

**结论**：
- per-tool sample size 普遍 <10 → distribution 列（min/p25/median/p75/max）**估计方差极大**
- 默认 segment=difficulty 后再分 3 桶 → per-tool-per-segment sample 通常 1-2 例 → **min/p25/median/p75/max 退化为单点**
- planner 在 LATEST distribution 列中应**显示 `sample_count` per segment**（不只 per tool 总数），并且当 per-segment sample < 3 时**渲染为 `n/a`**（避免误导）—— 这是 D-13 Pitfall 10 「avoid misleading averages」的延伸。
- D-14 拒绝 p25-based hard gate 是基于此事实的正确决策。

## Sources

### Primary (HIGH confidence)
- `evolution/tools/tool_metric.py:442-477` (Bash read) — `persist_per_tool_rates` 实现，Wave 0 镜像模板
- `evolution/tools/evolve_tool_params.py:75 / 343-432 / 1012-1017` (Bash grep + Read) — Phase 13 唯一已接 helper 的 CLI
- `evolution/tools/evolve_tool_descriptions.py:326-422` (Read) — 老 CLI metrics 字段集 + 缺 helper 接线证据
- `evolution/tools/evolve_tool_reasoning.py:463-555 / 697-764` (Read) — Phase 15 CLI metrics 字段集 + ab_comparison 已有数据
- `evolution/tools/tool_dataset.py:33-77 / 135-158` (Read) — ToolSelectionExample 字段集 + to_dspy_examples 缺 difficulty
- `evolution/core/external_importers.py:108-121` (Read) — `_contains_secret` 签名
- `output/tools_reasoning/20260512_150748/metrics.json` (Read) — 实测 reasoning metrics 字段集
- `output/tools_reasoning/20260512_150748/ab_comparison.json` (Read) — 实测 ab_comparison 字段
- `output/tools/FAILED_20260422_201215/metrics.json` (Read) — 唯一现存 desc run，字段贫乏证据
- `datasets/tools/holdout.jsonl` (Bash python script) — 81 例实测 difficulty / confuser_tools / correct_tool 分布
- `.venv` Python 3.13.3 + Rich 15.0.0 + Click 8.1.8 + DSPy 3.1.3 (Bash importlib.metadata) — 实际版本
- Rich `Bar` / `default_styles` 行为 (Bash python live demo) — 验证 Bar 嵌 Table 列被压扁、styles 名称
- `.gitignore:26-27` (Bash cat) — `output/` 已 ignore 确认

### Secondary (MEDIUM confidence)
- `tests/tools/test_cross_tool_regression.py` (Read) — Phase 13 helper test 模板
- `tests/tools/conftest.py / tests/fixtures/sessions/*.json` (Bash ls) — fixture 文件夹惯例

### Tertiary (LOW confidence)
- 无 LOW 项；本研究全部基于 in-repo 实测代码与文件，无 web search / 训练知识猜测。

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| (no entries) | — | — | All claims verified against in-repo code, real metrics.json fixtures, or live `.venv` library probes. |

## Metadata

**Confidence breakdown:**
- Standard stack (Rich/Click/pytest/DSPy versions + APIs): HIGH — all probed live in `.venv`
- Architecture (helper pattern, holdout接线, source detection): HIGH — code paths read end-to-end
- Pitfalls (Sample size, distribution semantics, Bar limits): HIGH — empirically verified
- Open Questions: 3 真未决项，均要求 planner 在 Wave 0 设计前 pin 死

**Research date:** 2026-05-12
**Valid until:** 2026-06-12 (30 days; Rich/Click/DSPy 都是稳定栈)

## RESEARCH COMPLETE
