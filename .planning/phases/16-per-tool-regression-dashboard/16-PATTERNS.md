# Phase 16: Per-Tool Regression Dashboard — Pattern Map

**Mapped:** 2026-05-12
**Files analyzed:** 13 (5 new files + 5 fixture dirs + 6 modified source files + 4 modified test files)
**Analogs found:** 13/13 (every file has a strong in-repo match — Phase 16 is 100% pattern-following work)

---

## File Map

| # | New / Modified File | Role | Data Flow | Closest Analog | Reuse Strategy | 关键 LoC |
|---|---------------------|------|-----------|----------------|----------------|---------|
| 1 | **NEW** `evolution/tools/regression_dashboard.py` | CLI / view-renderer | file-I/O → transform → stdout + JSON | `evolution/tools/mine_tool_sessions.py` (Click+Rich骨架) + `evolution/skills/evolve_skill.py` (Click 完整骨架) | 复用 `multiple=True` flag 风格、`Console()` module-level、`@click.command()` 末尾 `if __name__ == "__main__": main()` 收尾；新增 `_scan_runs / _detect_source / _segment_distribution / _render_*` helpers 自成体系 | mine_tool_sessions.py:329-413（CLI block），evolve_skill.py:317-323 |
| 2 | **MODIFIED** `evolution/tools/tool_metric.py`（+`persist_raw_predictions`） | helper | dict-transform | `tool_metric.py:442-477` `persist_per_tool_rates` | **直接镜像**：shallow copy + 字段强转 + None 容错；差异：不 sort（保留时间序）、type 多元（str/str/str/int）、加 size warning | tool_metric.py:442-477 |
| 3 | **MODIFIED** `evolution/tools/tool_dataset.py:135-158`（`to_dspy_examples` 加 `difficulty`） | data adapter | transform | 同函数自身现有结构 | 在 `dspy.Example(...)` 字典里追加一行 `difficulty=ex.difficulty,` 即可；不动 `with_inputs("task_description")` | tool_dataset.py:135-158 |
| 4 | **MODIFIED** `evolution/tools/evolve_tool_params.py:1012-1017`（接 `persist_raw_predictions`） | CLI / persistence | file-I/O | `evolve_tool_params.py:1012-1017` 自身 `persist_per_tool_rates` 接线 | **同位贴一行**：`metrics = persist_raw_predictions(metrics, raw_preds)`；上游构 raw_preds 用 `_evaluate_holdout` 已返回的 `evolved_tool_pairs` + zip(holdout_examples) | evolve_tool_params.py:1012-1017 |
| 5 | **MODIFIED** `evolution/tools/evolve_tool_descriptions.py:326-422`（接两 helper） | CLI / persistence | file-I/O | `evolve_tool_params.py:1012-1017` | **照搬两行**：`baseline_rates = checker.compute_per_tool_rates(...)` + `persist_per_tool_rates(...)` 已存在(line 351-353)，仅缺将其结果**注入** `metrics` dict（line 407-422 dict literal）。新增 `persist_raw_predictions(...)` + 在 holdout 循环里收 `raw_preds` | evolve_tool_descriptions.py:326-422 |
| 6 | **MODIFIED** `evolution/tools/evolve_tool_reasoning.py:463-555`（重构 `_safe_score` + 接两 helper） | CLI / persistence | file-I/O | `evolve_tool_reasoning.py:697-764` `_build_ab_comparison`（per-prediction 列表已在内存） | **复用 `_build_ab_comparison` 的预测路径**：在 `_safe_score` 旁新增 `_score_with_predictions(module, examples, lm) -> tuple[float, list[tuple[str,str]], list[dict]]`，返回 (score, tool_pairs, raw_preds)；不动 `_build_ab_comparison`（已为 ABStudy 服务） | evolve_tool_reasoning.py:463-555, 697-764 |
| 7 | **NEW** `tests/tools/test_persist_raw_predictions.py` | unit test | request-response | `tests/tools/test_cross_tool_regression.py` | **直接镜像 test_per_tool_persistence**：4-6 个测试函数，断言 immutability / 空 list / 大 list warning / 字段强转 / 缺键 fallback | test_cross_tool_regression.py:全文 |
| 8 | **NEW** `tests/tools/test_regression_dashboard.py` | functional + e2e test | request-response | `tests/tools/test_evolve_tool_params_cli.py` (Click CliRunner + patch 模式) + `test_cross_tool_regression.py`（最小测试 shape） | 用 `CliRunner.invoke(main, [...], catch_exceptions=True)` + `patch("evolution.tools.regression_dashboard._scan_runs")` 注入 fixture runs；15-20 个测试覆盖 LATEST/DIFF/TREND/ABStudy/fallback/exit-codes | test_evolve_tool_params_cli.py:64-99 |
| 9 | **NEW/EXTEND** `tests/tools/test_tool_dataset.py`（加 `test_dspy_example_has_difficulty`） | unit test | request-response | `test_tool_dataset.py` 已存在的 round_trip / from_dict ignores 模式 | 追加单测函数；mirror `TestToolSelectionExample` 类风格 | test_tool_dataset.py:21-77 |
| 10 | **EXTEND** `tests/tools/test_evolve_tool_params_cli.py`（断言 `raw_predictions` in metrics） | integration test | request-response | 同文件现有 patch 模式 | 加 1 个测试函数 `test_metrics_includes_raw_predictions` | test_evolve_tool_params_cli.py:64-99 |
| 11 | **EXTEND** `tests/tools/test_evolve_tool_descriptions.py`（断言 `per_tool_*_rates` + `raw_predictions`） | integration test | request-response | 同上 | 加 1 个测试函数 `test_metrics_includes_per_tool_and_raw` | test_evolve_tool_params_cli.py:64-99 |
| 12 | **EXTEND** `tests/tools/test_evolve_tool_reasoning.py`（断言 `per_tool_*_rates` + `raw_predictions`） | integration test | request-response | 同上 | 加 1 个测试函数 `test_metrics_includes_per_tool_and_raw` | test_evolve_tool_params_cli.py:64-99 |
| 13 | **NEW** `tests/fixtures/dashboard_runs/{desc_old,params_complete,reasoning_complete,reasoning_old,params_no_raw}/{metrics.json, ab_comparison.json?, raw_predictions?}` | test fixture data | file-I/O | `tests/fixtures/sessions/*.json`（每场景一文件 / 一目录） | 仿造 `tests/fixtures/sessions/` 目录约定，每个 scenario 一个子目录，符合 dashboard `_scan_runs` glob `<root>/*/metrics.json` | tests/fixtures/sessions/*.json |

---

## Code Excerpts

### Wave 0 — Schema Helper + 三 CLI 接线

#### Excerpt A — `persist_raw_predictions` 镜像模板

**Source analog:** `evolution/tools/tool_metric.py:439-477`

```python
# ── Per-Tool Rate Persistence (Phase 13: D-12) ───────────────────────────────


def persist_per_tool_rates(
    metrics: dict,
    baseline_rates: dict[str, float],
    evolved_rates: dict[str, float],
) -> dict:
    """Merge per-tool rate dicts into a metrics dict (for metrics.json).

    The function:
    - Does NOT mutate its inputs (returns a shallow copy of metrics).
    - Coerces every rate value to float for safe json.dumps serialization.
    - Sorts keys in both rate dicts alphabetically for stable diffs across runs.
    """
    out = dict(metrics)  # shallow copy — callers may reuse `metrics` afterwards
    out["per_tool_baseline_rates"] = {
        k: float(v) for k, v in sorted((baseline_rates or {}).items())
    }
    out["per_tool_evolved_rates"] = {
        k: float(v) for k, v in sorted((evolved_rates or {}).items())
    }
    return out
```

**按这个写**：紧贴 `persist_per_tool_rates` 之下追加 `persist_raw_predictions(metrics, raw_predictions: list[dict]) -> dict`：
- 同样 `out = dict(metrics)` 不可变模式
- 同样 `(raw_predictions or [])` None 容错
- **不 sort**（raw_predictions 是顺序敏感时间序列）
- **不全部 float**（每字段类型 str/str/str/int，逐字段强转）
- **加** `if len(cleaned) > 2000:` size warning（Pitfall 10 retention 占位），`Console().print(f"[yellow]raw_predictions large ({len(cleaned)} records)...[/yellow]")`
- 返回新 dict 含 `out["raw_predictions"] = cleaned`

#### Excerpt B — `to_dspy_examples` 加 `difficulty` 字段

**Source analog（即将修改本身）：** `evolution/tools/tool_dataset.py:135-158`

```python
def to_dspy_examples(self, split: str = "train") -> list[dspy.Example]:
    """Convert a split to DSPy Example objects.

    Only task_description is marked as input; correct_tool, correct_params,
    and confuser_tools are labels/metadata consumed by downstream metrics
    (joint_tool_param_metric in Phase 13) and filters (D-13 ambiguous subset
    in Phase 15).
    """
    data = getattr(self, split)
    return [
        dspy.Example(
            task_description=ex.task_description,
            correct_tool=ex.correct_tool,
            correct_params=ex.correct_params,
            confuser_tools=ex.confuser_tools,
        ).with_inputs("task_description")
        for ex in data
    ]
```

**按这个写**：在 `confuser_tools=ex.confuser_tools,` 之后追加 `difficulty=ex.difficulty,` 一行；不动 `.with_inputs("task_description")`（difficulty 是 metadata 不是 input）。同步更新 docstring 第二段「filters... + segmentation (D-11 in Phase 16)」一行。

#### Excerpt C — Phase 13 唯一已接 helper 接线点（params CLI 的同位插入）

**Source analog:** `evolution/tools/evolve_tool_params.py:1012-1017`

```python
# ── 13. CrossToolRegressionChecker + persist_per_tool_rates ────────
regression_checker = CrossToolRegressionChecker()
baseline_rates = regression_checker.compute_per_tool_rates(baseline_tool_pairs)
evolved_rates = regression_checker.compute_per_tool_rates(evolved_tool_pairs)
regression_result = regression_checker.check_regression(baseline_rates, evolved_rates)
metrics = persist_per_tool_rates(metrics, baseline_rates, evolved_rates)
```

**按这个写**（params CLI）：在 line 1017 之后插入：

```python
# ── 13b. Persist raw_predictions for Phase 16 dashboard distribution ──
raw_preds = []
for ex, (correct, selected) in zip(holdout, evolved_tool_pairs):
    raw_preds.append({
        "correct_tool": correct,
        "selected_tool": selected,
        "difficulty": getattr(ex, "difficulty", "medium") or "medium",
        "num_available_tools": len(getattr(ex, "confuser_tools", []) or []) + 1,
    })
metrics = persist_raw_predictions(metrics, raw_preds)
```

注意 import 同步加 `persist_raw_predictions` 到 line 71-76 的 import block。

#### Excerpt D — `_evaluate_holdout` 已暴露 tool_pairs（params CLI 数据可得性证明）

**Source analog:** `evolution/tools/evolve_tool_params.py:343-426`

```python
def _evaluate_holdout(
    module: Any,
    holdout: list[dspy.Example],
    lm: Any,
) -> tuple[
    float,
    list[tuple[str, str]],
    list[tuple[str, str]],
]:
    """Score `module` over `holdout` using bare joint_tool_param_metric.

    Returns:
        (mean_score, tool_pairs, param_pairs) where tool_pairs is the
        (correct_tool, selected_tool) sequence consumable by
        CrossToolRegressionChecker, ...
    """
    if not holdout:
        return 0.0, [], []
    total = 0.0
    n = 0
    tool_pairs: list[tuple[str, str]] = []
    # ...
    with dspy.context(lm=lm):
        for ex in holdout:
            try:
                pred = module(task_description=task)
            except Exception as e:
                console.print(f"[yellow]holdout example skipped...[/yellow]")
                continue
            # ...
            tool_pairs.append(
                (
                    getattr(ex, "correct_tool", "") or "",
                    getattr(pred, "selected_tool", "") or "",
                )
            )
```

**按这个写**：保持 `_evaluate_holdout` 签名不变；构 `raw_preds` 不在循环里改返回，而是**在外部**用已有 `evolved_tool_pairs` zip(`holdout`)（Open Question 3 推荐路径 c：保持签名）。注意 `getattr(pred, "selected_tool", "") or ""` 的兜底风格（永不 None）。

#### Excerpt E — `evolve_tool_descriptions` 当前 holdout 接线（Wave 0 缺口最大点）

**Source analog（即将修改本身）：** `evolution/tools/evolve_tool_descriptions.py:326-422`

```python
# ── 9. Holdout evaluation (baseline vs evolved) ──────────────────────
console.print(f"\n[bold]Evaluating on holdout set ({len(dataset.holdout)} examples)[/bold]")

holdout_examples = dataset.to_dspy_examples("holdout")

baseline_preds: list[tuple[str, str]] = []
evolved_preds: list[tuple[str, str]] = []

for ex in holdout_examples:
    with dspy.context(lm=lm):
        bp = baseline_module(task_description=ex.task_description)
        baseline_preds.append((ex.correct_tool, bp.selected_tool))
        ep = optimized_module(task_description=ex.task_description)
        evolved_preds.append((ex.correct_tool, ep.selected_tool))

# ...
regression_checker = CrossToolRegressionChecker()
baseline_rates = regression_checker.compute_per_tool_rates(baseline_preds)
evolved_rates = regression_checker.compute_per_tool_rates(evolved_preds)
regression_result = regression_checker.check_regression(baseline_rates, evolved_rates)

# ── Save metrics ──
metrics = {
    "timestamp": timestamp,
    # ... NO per_tool_baseline_rates / per_tool_evolved_rates / raw_predictions
    "constraints_passed": True,
}
```

**按这个写**：
1. 在 `holdout_examples` 循环里同步收 `raw_preds = []` 列表（追加 `{correct_tool, selected_tool, difficulty=ex.difficulty, num_available_tools=len(ex.confuser_tools)+1}`）—— **依赖 Excerpt B 已扩 `to_dspy_examples` 含 difficulty**。
2. 在 line 354 `regression_result = ...` 之后、line 407 metrics dict 字面量之前新加：`metrics_extra = persist_per_tool_rates({}, baseline_rates, evolved_rates); metrics_extra = persist_raw_predictions(metrics_extra, raw_preds)`。
3. 在 line 422 之后（写盘前）合并：`metrics = {**metrics, **metrics_extra}`。
4. import 加 `from evolution.tools.tool_metric import persist_per_tool_rates, persist_raw_predictions`。

**注意：根据 RESEARCH §Open Questions Q1，CONTEXT D-08 fallback 与 Out of scope「不补 per_tool_*_rates」叠加现实「desc/reasoning 完全没接 helper」会让 dashboard 启动时 90% run dropped。Wave 0 这一步是 D-08 一致性收口的合理延伸，planner 在 plan 阶段必须确认。**

#### Excerpt F — `evolve_tool_reasoning._safe_score` 重构点

**Source analog（即将修改本身）：** `evolution/tools/evolve_tool_reasoning.py:463-468 + 615-633`

```python
# Line 463-468
th_off_full = _safe_score(baseline_module, eval_holdout, lm)
th_on_full = _safe_score(optimized_module, eval_holdout, lm)
# ...

# Line 615-633
def _safe_score(module: Any, examples: list, lm: Any) -> float:
    """Score module on examples, returning 0.0 on any failure (including empty set)."""
    if not examples:
        return 0.0
    try:
        return float(_score_module_on_holdout(module, examples, lm))
    except Exception:
        return 0.0
```

**按这个写**：
1. 在 `_safe_score` 旁新加 `_score_with_predictions(module, examples, lm) -> tuple[float, list[tuple[str,str]], list[dict]]`：返回 `(score, tool_pairs, raw_preds)`；逻辑里循环逐例调 `module(task_description=...)`，收 `(correct, selected_tool)` 与 `{correct_tool, selected_tool, difficulty, num_available_tools}`。复用 `evolve_tool_params._evaluate_holdout` 的 try/except 风格（line 381-411）。
2. 在 line 463-468 之后用 `_, tool_pairs_off, _ = _score_with_predictions(...)` 与 `_, tool_pairs_on, raw_preds_on = _score_with_predictions(...)`（two-pass，think-off 与 think-on 各跑一次；不复用 `_safe_score` 因为它已经丢了 predictions）。
3. 在 line 514 metrics dict literal 后加：`metrics = persist_per_tool_rates(metrics, baseline_rates, evolved_rates); metrics = persist_raw_predictions(metrics, raw_preds_on)`（baseline_rates/evolved_rates 由 `CrossToolRegressionChecker.compute_per_tool_rates(tool_pairs_off/on)` 算出）。
4. 不动 `_build_ab_comparison`（line 697-764）—— 它已经为 ABStudy 服务，与 raw_predictions 数据流并行。

---

### Wave 1 — Dashboard CLI 骨架 + LATEST 区

#### Excerpt G — Click + Rich CLI 模块头骨架

**Source analog:** `evolution/tools/mine_tool_sessions.py:1-40`

```python
"""SessionDB tool-misselection mining CLI — Phase 14 (TOOL-V2-01).

Reads ~/.hermes/sessions/*.json transcripts and produces ToolSelectionExample
JSONL files suitable for unioning with synthetic Phase 4 datasets.

Usage:
    python -m evolution.tools.mine_tool_sessions \\
        --i-have-consent \\
        --sessions-dir ~/.hermes/sessions \\
        --signals error_retry,user_correction,oracle_disagreement \\
        --baseline-module output/tools/<latest> \\
        --output datasets/tools/sessions/<ts>

Failure paths:
    FAILED_<ts>/   — sessions empty / consent missing / 0 candidate after filter

READ-ONLY guarantee: this CLI never calls tool_loader.write_back_description
or any hermes-agent mutation path. ...
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from evolution.core.config import EvolutionConfig
```

**按这个写**：
- 模块 docstring：「Per-tool regression dashboard for evolve_tool_* pipelines (TOOL-V2-04 / Phase 16). Standalone read-only CLI; emits Rich console + dashboard.json. Never touches LLM / hermes-agent.」+ Usage block + Failure paths + READ-ONLY guarantee 段（与 mine_tool_sessions 平行）。
- imports：完全相同的顺序 `json / sys / datetime / pathlib.Path / typing.Optional` → 空行 → `click` → `rich.console.Console / rich.panel.Panel / rich.table.Table`。**不 import dspy**（dashboard 零 LLM）。
- 增 `from evolution.core.external_importers import _contains_secret`（ABStudy 渲染前 redact）。

#### Excerpt H — Click multiple=True flag + 末尾 `if __name__`

**Source analog:** `evolution/skills/evolve_skill.py:317-323` + `evolution/tools/mine_tool_sessions.py:329-413`

```python
# evolve_skill.py:317-323
@click.command()
@click.option("--skill", required=True, help="Name of the skill to evolve")
@click.option("--iterations", default=10, help="Number of GEPA iterations")
@click.option("--eval-source", default="synthetic", type=click.Choice(["synthetic", "golden", "sessiondb"]),
              help="Source for evaluation dataset")
@click.option("--dataset-path", default=None, help="Path to existing eval dataset (JSONL)")
```

```python
# mine_tool_sessions.py:412-413
if __name__ == "__main__":
    main()
```

**按这个写**（regression_dashboard.py 末尾）：

```python
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
    # ... orchestration ...


if __name__ == "__main__":
    main()
```

**关键风格点**（实测对照）：
- `multiple=True` → 闭包内是 `tuple`（不是 list），空时 `()`；判定空用 `if not runs and not <default-root-glob-result>`。
- `type=click.Path()` 不传 `exists=True`（dashboard 启动时再 expand glob，未存在的 path 走 dropped_runs）。
- `raise click.UsageError("...")` 输出红色错误自动 exit 2（CONTEXT 多处「stdout 报错并 exit 2」用此）。

#### Excerpt I — module-level Console + glob + sort by mtime

**Source analog:** `evolution/tools/evolve_tool_reasoning.py:72,75` + `mine_tool_sessions.py:1-40` 风格

```python
# evolve_tool_reasoning.py
console = Console()
OUTPUT_ROOT = Path("output") / "tools_reasoning"
```

**按这个写**（regression_dashboard.py 模块级）：

```python
console = Console()

DEFAULT_ROOTS: tuple[Path, ...] = (
    Path("output") / "tools",
    Path("output") / "tools_reasoning",
)
_SPARK_CHARS = "▁▂▃▄▅▆▇█"


def _scan_runs(roots: tuple[Path, ...]) -> list[Path]:
    """Glob <root>/*/metrics.json, sorted by mtime ascending (oldest first)."""
    found: list[Path] = []
    for root in roots:
        if root.exists():
            found.extend(root.glob("*/metrics.json"))
    return sorted(found, key=lambda p: p.stat().st_mtime)
```

#### Excerpt J — D-07 source 启发判定决策树

**Source analog:** RESEARCH §Schema & Data Flow + `evolve_tool_reasoning.py` 字段集证据

```python
def _detect_source(metrics: dict, run_path: Path) -> Optional[str]:
    """D-07 启发判定 — 字段集 + 目录名 fallback.

    Order matters:
    1. think_ab_gate present → reasoning (Phase 15 unique)
    2. param_predictors_discovered present → params (Phase 13 unique;
       NOT used for reasoning even though reasoning shares this field —
       step 1 catches reasoning first)
    3. parent dir == 'tools_reasoning' → reasoning (defensive fallback)
    4. parent dir == 'tools' AND has baseline_score → desc
    5. otherwise → None (run goes to dropped_runs)
    """
    if "think_ab_gate" in metrics:
        return "reasoning"
    if "param_predictors_discovered" in metrics:
        return "params"
    parent_root = run_path.parent.parent.name
    if parent_root == "tools_reasoning":
        return "reasoning"
    if parent_root == "tools" and "baseline_score" in metrics:
        return "desc"
    return None
```

#### Excerpt K — Rich Style 颜色编码 + sparkline

**Source analog:** `evolve_tool_descriptions.py:378-383`（Phase 5 改动颜色 inline markup 风格）

```python
change_color = "green" if improvement > 0 else "red"
result_table.add_row(
    "Holdout Score",
    f"{baseline_score:.3f}",
    f"{evolved_score:.3f}",
    f"[{change_color}]{improvement:+.3f}[/{change_color}]",
)
```

**按这个写**（dashboard.py 状态着色 helper）：

```python
def _status_style(delta_pp: float, warning_threshold_pp: float = 2.0) -> tuple[str, str]:
    """Return (status_label, rich_style) per D-09."""
    if delta_pp <= -5.0:
        return ("FAIL❌", "bold red")
    if delta_pp <= -warning_threshold_pp:
        return ("WARN⚠️", "yellow")
    if delta_pp >= 5.0:
        return ("GAIN✨", "bold green")
    return ("OK✅", "")  # default — no markup


def _sparkline(values: list[float]) -> str:
    """8-char Unicode block sparkline (▁▂▃▄▅▆▇█)."""
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    return "".join(
        _SPARK_CHARS[min(7, int((v - lo) / span * 8))] for v in values
    )
```

inline markup 用 `f"[{style}]{text}[/{style}]"` 即可（与 evolve_tool_descriptions:378-383 完全一致风格），不需注册自定义 theme。

---

### Wave 3 — ABStudy + Secret Redaction

#### Excerpt L — `_contains_secret` 复用模式

**Source analog:** `evolution/core/external_importers.py:108-121`

```python
def _contains_secret(text: str) -> bool:
    """Check if text contains potential API keys or tokens.

    Layer 1: pattern match against known secret prefixes/formats.
    Layer 2 (D-15): Shannon entropy heuristic over ≥24-char base64-like
    tokens — flag if entropy > _SECRET_ENTROPY_THRESHOLD.
    """
    if SECRET_PATTERNS.search(text):
        return True
    for tok in re.findall(r'[A-Za-z0-9_/+=-]{24,}', text):
        if _shannon_entropy(tok) > _SECRET_ENTROPY_THRESHOLD:
            return True
    return False
```

**按这个写**（dashboard.py ABStudy 渲染前）：

```python
from evolution.core.external_importers import _contains_secret


def _safe_truncate(text: str, max_len: int = 80) -> str:
    """Redact-then-truncate for ABStudy display (D-15)."""
    if not text:
        return ""
    if _contains_secret(text):
        return "[REDACTED — secret-like content]"
    return text[:max_len] + ("..." if len(text) > max_len else "")
```

下划线前缀只是惯例不是强约束；从 `evolution.core.external_importers` 直接 import `_contains_secret` 即可（与现有 import 风格一致）。

---

## Import Path Convention

### `regression_dashboard.py` 应该 import 哪些既有 helper

```python
# Standard library — alphabetical, top group
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Third-party — alphabetical, second group
import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Local — alphabetical by full module path, third group
from evolution.core.external_importers import _contains_secret
# NOTE: dashboard 不 import tool_metric / CrossToolRegressionChecker —
# 直接从 metrics.json 读 per_tool_*_rates，不重新计算（RESEARCH §Existing
# Code Survey 明确「dashboard 端不重新实现」）
```

### `tool_metric.py` 新增 helper（无新依赖）

```python
# 既有 imports 已包含所需：
# import json
# from rich.console import Console
# console = Console()
# 在 line 477 之后追加 persist_raw_predictions —— 零新 import
```

### 三 evolve_tool_*.py CLI 接线 import

```python
# evolve_tool_params.py:71-76 已有 persist_per_tool_rates；只需扩为：
from evolution.tools.tool_metric import (
    joint_tool_param_metric,
    joint_tool_param_metric_with_feedback,
    CrossToolRegressionChecker,
    persist_per_tool_rates,
    persist_raw_predictions,  # ← 新增
)

# evolve_tool_descriptions.py 当前 import 仅有 CrossToolRegressionChecker —
# 须扩 persist_per_tool_rates + persist_raw_predictions 两个新 import.

# evolve_tool_reasoning.py 同 evolve_tool_descriptions —
# 当前同样仅 import CrossToolRegressionChecker.
```

---

## Test Pattern Map

| Test File | Closest Analog | Fixture Path | 模式要点 |
|-----------|---------------|--------------|---------|
| **NEW** `tests/tools/test_persist_raw_predictions.py` | `tests/tools/test_cross_tool_regression.py`（80 LoC，单测 1 个） | inline dict（无外部 fixture，与 analog 一致） | `pytest.importorskip("dspy")`（虽然 helper 不 import dspy，但保持 tests/tools/ 一致防御） + `from evolution.tools.tool_metric import persist_raw_predictions` + 4-6 个测试函数：immutability / empty list / large list warning / 字段强转 / 缺键 fallback |
| **NEW** `tests/tools/test_regression_dashboard.py` | `tests/tools/test_evolve_tool_params_cli.py:64-99`（CliRunner + patch 模式） | `tests/fixtures/dashboard_runs/<scenario>/`（5 个子目录） | `runner = CliRunner()` + `with patch("evolution.tools.regression_dashboard._scan_runs", return_value=[<fixture path>])` + `result = runner.invoke(main, [...], catch_exceptions=True)` + `assert result.exit_code == 0` + `assert "LATEST" in result.output` |
| **EXTEND** `tests/tools/test_tool_dataset.py` | 同文件已有的 `TestToolSelectionExample` 类 | inline `ToolSelectionExample` 实例 | 加 `def test_dspy_example_has_difficulty(self)`：构 builder → `to_dspy_examples("holdout")` → `assert getattr(ex_dspy, "difficulty", None) == "hard"` |
| **EXTEND** `tests/tools/test_evolve_tool_params_cli.py` | 同文件 `test_loud_gepa_failure_and_opt_in:64-99` | `tmp_path` 临时输出目录（pytest 内置） | 在现有 GEPA mock 模式之上加 `result = runner.invoke(...)` 之后 `metrics = json.loads((tmp_path / "metrics.json").read_text()); assert "raw_predictions" in metrics; assert metrics["raw_predictions"][0].keys() == {"correct_tool","selected_tool","difficulty","num_available_tools"}` |
| **EXTEND** `tests/tools/test_evolve_tool_descriptions.py` | 同上风格 + 文件自身现有 patch 模式 | `tmp_path` | 加 `test_metrics_includes_per_tool_and_raw`：mock 让 holdout 走通 → `assert "per_tool_baseline_rates" in metrics` + `assert "raw_predictions" in metrics` |
| **EXTEND** `tests/tools/test_evolve_tool_reasoning.py` | `tests/tools/conftest.py:mock_reasoning_module` fixture + 同文件现有 patch 模式 | `mock_reasoning_module` fixture（已有） | 加 `test_metrics_includes_per_tool_and_raw`：用 `mock_reasoning_module` + 走通 think-on/think-off 评估 → `assert "per_tool_*_rates" in metrics` + `assert "raw_predictions" in metrics` |

### Fixture Layout（仿 `tests/fixtures/sessions/` 惯例）

```
tests/fixtures/dashboard_runs/
├── desc_old/                          # D-08 缺 per_tool_*_rates → dropped_runs
│   └── metrics.json                   # 仅 {timestamp, status, baseline_score}
├── params_complete/                   # 完整字段（含 raw_predictions）
│   └── metrics.json                   # 含 per_tool_*_rates + raw_predictions + param_predictors_discovered
├── params_no_raw/                     # D-08 老 params run：缺 raw_predictions
│   └── metrics.json                   # 含 per_tool_*_rates 但无 raw_predictions
├── reasoning_complete/                # 完整 reasoning + ABStudy
│   ├── metrics.json                   # 含 think_ab_gate + per_tool_*_rates + raw_predictions
│   └── ab_comparison.json             # 含 task_description / reasoning_text_on / is_correct_off/on
└── reasoning_old/                     # D-08 老 reasoning run：缺 per_tool_*_rates
    └── metrics.json                   # 仅 think_ab_gate（17 个现存 reasoning runs 的实情）
```

每个 metrics.json 用 inline `json.dumps(..., indent=2)` 写入（不复杂，单文件 < 50 行）。test_regression_dashboard.py 用 `Path("tests/fixtures/dashboard_runs/<scenario>")` 直接引用。

---

## Style Cheatsheet

### Naming（实测自 evolution/tools/）

| 类别 | 规则 | 示例 |
|------|------|------|
| 模块文件 | `snake_case.py` | `regression_dashboard.py` ✓ / `tool_metric.py` ✓ |
| 函数 | `snake_case` | `persist_raw_predictions`, `_scan_runs`, `_detect_source` |
| 私有 helper | `_underscore_prefix` | `_safe_score`, `_evaluate_holdout`, `_status_style` |
| 类 | `PascalCase` | `CrossToolRegressionChecker`, `EvolutionConfig` |
| 常量 | `UPPER_SNAKE_CASE` | `DEFAULT_ROOTS`, `_SPARK_CHARS`, `OUTPUT_ROOT` |
| Test 文件 | `test_<module>.py` | `test_persist_raw_predictions.py`, `test_regression_dashboard.py` |
| Test 函数 | `test_<behavior>` | `test_immutability_and_shape`, `test_diff_requires_both_runs` |

### Type Hints（PEP 585，Python 3.10+）

| 用法 | 实测示例（来源） |
|------|-----------------|
| `list[ConstraintResult]` | `evolve_tool_params.py:347-350` |
| `dict[str, float]` | `tool_metric.py:444-445` |
| `tuple[Path, ...]` | dashboard 推荐 |
| `Optional[str]` | `evolve_tool_descriptions.py / evolve_skill.py` 多处 |
| `tuple[float, list[tuple[str,str]], list[dict]]` | `_evaluate_holdout` 返回签名风格 |

### Dataclass + from_dict 模式

`evolution/tools/tool_dataset.py:33-77` `ToolSelectionExample` 的 `to_dict() / from_dict()` 模式 —— **dashboard 不需新建 dataclass**（纯 dict 操作），但若 planner 决定加 `DashboardSummary` dataclass 用于 dashboard.json 序列化，**必须**镜像此 `to_dict / @classmethod from_dict` 模式。

### Click @click.option 风格（实测自 mine_tool_sessions.py:329-378 + evolve_skill.py:317-323）

| 风格 | 实测示例 |
|------|---------|
| 一律 `--snake-case-flag` | `--baseline-run`, `--trend-window`, `--warning-threshold-pp` |
| `default=None` 表示「不强制」 | `--output default=None` |
| `multiple=True` 累加传值 | `--runs` (Phase 16 推荐) |
| `type=click.Choice(["a","b","c"])` 限定枚举 | `--segment difficulty\|pool_size\|none` |
| 帮助文本以大写起句不带句号 | `"Per-tool delta threshold for yellow warning (D-13)"` |
| `is_flag=True` 表示 boolean | （Phase 16 暂无） |
| 短语「(default ...)」括号内说明默认值 | `"--output ... (default: ./dashboard_<ts>.json)"` |

### Rich Style 名（实测自 `.venv/lib/python3.13/site-packages/rich/default_styles.py`）

| Phase 16 status | 推荐 Rich style 字符串 | 等效内置语义 |
|-----------------|----------------------|-------------|
| OK ✅ | `""`（空 = 默认） | none |
| WARN ⚠️ (delta ≤ -2pp) | `"yellow"` | 等效 `logging.level.warning` |
| FAIL ❌ (delta ≤ -5pp) | `"bold red"` | 等效 `logging.level.error` |
| GAIN ✨ (delta ≥ +5pp) | `"bold green"` | （无内置等效，常用模式） |

inline markup 用法：`f"[{style}]{cell}[/{style}]"`（实测自 `evolve_tool_descriptions.py:382-383` `f"[{change_color}]{improvement:+.3f}[/{change_color}]"`）。

### 错误处理风格

| 场景 | 模式 |
|------|------|
| CLI usage error | `raise click.UsageError("...")` → 自动 exit 2（实测 Click 8.1.8 行为） |
| 运行时 unrecoverable | `console.print("[red]...[/red]")` + `return 1` 或 `sys.exit(1)`（`evolve_tool_descriptions.py:322-324`） |
| 解析失败 / 单条 example 失败 | try/except + `console.print("[yellow]...[/yellow]")` + continue（`evolve_tool_params.py:387-397`） |
| 不可变 helper 失败容错 | None 容错 `(rates or {})`、`getattr(obj, "field", "") or ""`（`tool_metric.py:471-475 / evolve_tool_params.py:415`） |

### Console.print vs print

仓库内**全部** evolution/tools/ 模块用 `console = Console()` module-level + `console.print(...)`（**禁** bare `print()`，只有 `generate_report.py` 是例外）。Phase 16 dashboard.py 必须遵循。

### JSON 序列化

| 用途 | 模式 |
|------|------|
| metrics.json / dashboard.json | `json.dumps(metrics, indent=2)`（人读） |
| 数据集 train/val/holdout.jsonl | `json.dumps(obj) + "\n"` 一行一对象 |
| 跨 run diff 稳定 | `sort_keys=True`（dashboard.json 推荐） |
| 字段类型保留 | helper 内逐字段强转 `float() / int() / str()`（`persist_per_tool_rates` 模板） |

---

## No Analog Found

无。Phase 16 全部 13 个 new/modified 文件都有 in-repo 强 analog——这是 Phase 13/14/15 已经踩通的同一类型工作（CLI + helper + tests），Phase 16 是其自然延展。

---

## Metadata

**Analog search scope:**
- `evolution/tools/` （所有 12 个模块）
- `evolution/skills/evolve_skill.py`（CLI 全模板）
- `evolution/core/external_importers.py`（_contains_secret）
- `tests/tools/`（28 个 test 文件，挑 4 个相关）
- `tests/fixtures/sessions/`（fixture layout）
- `output/tools_reasoning/`（实测 metrics.json 字段集）

**Files scanned:** 约 25 个 Python 源文件 + 2 个 metrics.json 实数据样例
**Pattern extraction date:** 2026-05-12
**Confidence:** HIGH — 全部 excerpts 引用真实行号，code excerpt 来自 in-repo 现有代码 verbatim copy。

---

## PATTERN MAPPING COMPLETE

**Phase:** 16 - Per-Tool Regression Dashboard
**Files classified:** 13
**Analogs found:** 13/13

### Coverage
- Files with exact analog: 7（直接镜像 `persist_per_tool_rates` / `_evaluate_holdout` / `mine_tool_sessions` CLI 骨架 / `test_cross_tool_regression` 单测）
- Files with role-match analog: 6（test extensions、fixture layout、source-detection 决策树）
- Files with no analog: 0

### Key Patterns Identified
- **`persist_*` 不可变 helper 模式** —— `tool_metric.py:442-477` 是黄金模板；Wave 0 `persist_raw_predictions` 直接镜像（差异：不 sort、字段类型多元、加 size warning）。
- **Click + Rich + module-level Console** —— `evolution/tools/` 一律 `console = Console()` 顶级声明 + `console.print(...)`；`@click.option` 风格统一 kebab-case + `default=None` + 帮助文本无句号。
- **Holdout 接线统一在 `_evaluate_holdout` 之后插入两行 helper 调用** —— `evolve_tool_params.py:1012-1017` 已示范 `persist_per_tool_rates`；Phase 16 Wave 0 同位贴 `persist_raw_predictions` 一行（params CLI），desc/reasoning 两 CLI 同时补 `persist_per_tool_rates` + `persist_raw_predictions` 两行（这违背 D-08 Out of scope 表述但与 D-12 一致性收口对齐——Open Question 1 已记录）。
- **Test fixture：每场景一目录 + inline `json.dumps`** —— `tests/fixtures/sessions/` 惯例；Phase 16 `tests/fixtures/dashboard_runs/<scenario>/` 直接复用。
- **Click testing：`CliRunner` + `patch("module._helper")`** —— `test_evolve_tool_params_cli.py:64-99` 是金标模板；Phase 16 dashboard 测试用 `patch("evolution.tools.regression_dashboard._scan_runs")` 注入 fixture。
- **Source 启发判定优先字段集，目录名兜底** —— Phase 15 `think_ab_gate` 是 reasoning 唯一正向标识，Phase 13 `param_predictors_discovered` 是 params 唯一标识，desc 无正向标识必须走目录名 fallback；判定顺序 reasoning → params → desc 不可逆。

### File Created
`/Users/slj/项目/hermes-agent-self-evolution/.planning/phases/16-per-tool-regression-dashboard/16-PATTERNS.md`

### Ready for Planning
Pattern mapping 完成。planner 可以直接在 plan 的 action 段落里 reference 上述 excerpt + 行号，三 Wave 的代码模式都已锁定（Wave 0 helper 镜像 / Wave 1 CLI 骨架 / Wave 3 secret redaction）。Open Question 1（Wave 0 是否同时给 desc/reasoning 补 `persist_per_tool_rates`）需要 planner 在 Wave 0 plan 中明确决策——pattern 上是「绑定一起做」更一致，但 CONTEXT D-08 Out of scope 第 6 条与之冲突；以用户后续确认为准。
