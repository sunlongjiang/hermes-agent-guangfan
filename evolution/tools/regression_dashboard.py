"""Per-tool regression dashboard for evolve_tool_* pipelines — Phase 16 (TOOL-V2-04).

Standalone read-only CLI: aggregates per-tool selection rates from
output/tools/<ts>/metrics.json and output/tools_reasoning/<ts>/metrics.json
(plus ab_comparison.json for reasoning runs), renders a Rich console
dashboard (LATEST + DIFF + TREND + ABStudy regions), and emits a JSON
report to ./dashboard_<ts>.json.

Usage:
    python -m evolution.tools.regression_dashboard
    python -m evolution.tools.regression_dashboard --runs path/to/run1 --runs path/to/run2
    python -m evolution.tools.regression_dashboard --baseline-run <path> --evolved-run <path>
    python -m evolution.tools.regression_dashboard --trend-window 5 --segment difficulty

Failure paths:
    exit 2 — usage error (default roots empty + no --runs; mutex --trend-window/--trend-days)

READ-ONLY guarantee: this CLI never writes to hermes-agent, never calls LLMs,
never imports dspy. It only reads metrics.json / ab_comparison.json and emits
stdout + dashboard.json.
"""

import json
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from evolution.core.external_importers import _contains_secret


# WARNING 5: keep default Console() — no force_terminal, no_color, file overrides.
# This ensures CliRunner can capture stdout cleanly.
console = Console()

DEFAULT_ROOTS: tuple[Path, ...] = (
    Path("output") / "tools",
    Path("output") / "tools_reasoning",
)
_SPARK_CHARS = "▁▂▃▄▅▆▇█"
_MIN_SEGMENT_SAMPLE = 3  # below this, render distribution column as n/a (D-11 / Pitfall 10)


# ── Run discovery & loading ────────────────────────────────────────────────


def _scan_runs(roots: tuple[Path, ...]) -> list[Path]:
    """Glob <root>/*/metrics.json, sorted by mtime ascending (oldest first)."""
    found: list[Path] = []
    for root in roots:
        if root.exists():
            found.extend(root.glob("*/metrics.json"))
    return sorted(found, key=lambda p: p.stat().st_mtime)


def _load_run(metrics_path: Path) -> Optional[dict]:
    """Return {path, source, metrics, ab_comparison?} or None on parse error.

    Also returns None for runs that are unrecoverable (status=FAILED, missing
    per_tool_*_rates) — those appear in dropped_runs[] via the caller.
    """
    try:
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"path": str(metrics_path), "metrics": None, "source": None, "_drop_reason": f"json parse error: {e}"}
    run_dir = metrics_path.parent
    source = _detect_source(metrics, metrics_path)
    record: dict = {"path": str(run_dir), "metrics": metrics, "source": source, "ab_comparison": None}
    # Optional ab_comparison.json (reasoning source only)
    ab_path = run_dir / "ab_comparison.json"
    if ab_path.exists():
        try:
            record["ab_comparison"] = json.loads(ab_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            record["ab_comparison"] = None
    return record


def _detect_source(metrics: dict, run_path: Path) -> Optional[str]:
    """D-07 启发判定 — 字段集 + 目录名 fallback.

    Order matters:
    1. think_ab_gate present → reasoning (Phase 15 unique)
    2. param_predictors_discovered present → params (Phase 13 unique;
       NOT used for reasoning even though reasoning shares — step 1 catches first)
    3. parent dir name == 'tools_reasoning' → reasoning (defensive fallback)
    4. parent dir name == 'tools' AND has baseline_score → desc
    5. otherwise → None (run goes to dropped_runs)
    """
    if metrics is None:
        return None
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


# ── Status colour coding (D-09) ────────────────────────────────────────────


def _status_style(delta_pp: float, warning_threshold_pp: float = 2.0) -> tuple[str, str]:
    """Return (status_label, rich_style) per D-09."""
    if delta_pp <= -5.0:
        return ("FAIL ❌", "bold red")
    if delta_pp <= -warning_threshold_pp:
        return ("WARN ⚠️", "yellow")
    if delta_pp >= 5.0:
        return ("GAIN ✨", "bold green")
    return ("OK ✅", "")


# ── Distribution segmentation (D-11) ───────────────────────────────────────


def _quintiles(values: list[float]) -> dict[str, float]:
    """Return {min, p25, median, p75, max}; uses statistics.quantiles for p25/p75."""
    if not values:
        return {"min": 0.0, "p25": 0.0, "median": 0.0, "p75": 0.0, "max": 0.0}
    sorted_v = sorted(values)
    if len(sorted_v) == 1:
        v = float(sorted_v[0])
        return {"min": v, "p25": v, "median": v, "p75": v, "max": v}
    qs = statistics.quantiles(sorted_v, n=4)
    return {
        "min": float(min(sorted_v)),
        "p25": float(qs[0]),
        "median": float(statistics.median(sorted_v)),
        "p75": float(qs[2]),
        "max": float(max(sorted_v)),
    }


def _segment_distribution(
    raw_preds: list[dict],
    segment: str,
) -> dict[str, dict]:
    """Per-tool, per-segment evolved_rate quintiles.

    Returns {tool_name: {min,p25,median,p75,max, sample_count, n_segments}}.
    If sample_count for a tool is < _MIN_SEGMENT_SAMPLE, returns
    {tool_name: {"_n_a": True, "sample_count": int}} so caller can render
    n/a in distribution columns (D-11 / Pitfall 10).
    """
    if segment == "none" or not raw_preds:
        return {}
    out: dict[str, dict] = {}
    by_tool: dict[str, list[dict]] = {}
    for rec in raw_preds:
        by_tool.setdefault(rec["correct_tool"], []).append(rec)
    for tool, recs in by_tool.items():
        # Group recs by segment key
        by_seg: dict[str, list[dict]] = {}
        for rec in recs:
            if segment == "difficulty":
                key = rec.get("difficulty", "medium") or "medium"
            elif segment == "pool_size":
                n = int(rec.get("num_available_tools", 0) or 0)
                key = "1-3" if n <= 3 else ("4-7" if n <= 7 else "8+")
            else:
                key = "all"
            by_seg.setdefault(key, []).append(rec)
        # Per-segment evolved_rate
        seg_rates: list[float] = []
        for seg_key, seg_recs in by_seg.items():
            if len(seg_recs) < _MIN_SEGMENT_SAMPLE:
                continue
            n_correct = sum(1 for r in seg_recs if r["correct_tool"] == r["selected_tool"])
            seg_rates.append(n_correct / len(seg_recs))
        if not seg_rates:
            out[tool] = {"_n_a": True, "sample_count": len(recs)}
        else:
            out[tool] = {**_quintiles(seg_rates), "sample_count": len(recs), "n_segments": len(seg_rates)}
    return out


# ── LATEST region rendering (D-09 + D-16) ──────────────────────────────────


def _render_latest(
    run: dict,
    segment: str,
    warning_threshold_pp: float,
) -> dict:
    """Render LATEST Rich Table + frequency bar Panel; return latest dict for JSON.

    LATEST table columns (D-09): source / tool / baseline_rate / evolved_rate /
    delta_pp / sample_count / min / p25 / median / p75 / max / status.
    """
    metrics = run["metrics"]
    source = run["source"]
    baseline_rates = metrics.get("per_tool_baseline_rates", {}) or {}
    evolved_rates = metrics.get("per_tool_evolved_rates", {}) or {}
    raw_preds = metrics.get("raw_predictions", []) or []
    distribution = _segment_distribution(raw_preds, segment)

    # Per-tool sample counts from raw_predictions (correct_tool occurrences)
    sample_counts: Counter = Counter(rec.get("correct_tool", "") for rec in raw_preds)

    table = Table(title=f"LATEST [{source}] @ {run['path']}", show_lines=False)
    table.add_column("source", justify="left")
    table.add_column("tool", justify="left", style="cyan")
    table.add_column("baseline", justify="right")
    table.add_column("evolved", justify="right")
    table.add_column("delta_pp", justify="right")
    table.add_column("sample", justify="right")
    table.add_column("min", justify="right")
    table.add_column("p25", justify="right")
    table.add_column("median", justify="right")
    table.add_column("p75", justify="right")
    table.add_column("max", justify="right")
    table.add_column("status", justify="left", min_width=8, no_wrap=True)

    per_tool_records: list[dict] = []
    all_tools = sorted(set(baseline_rates.keys()) | set(evolved_rates.keys()))

    for tool in all_tools:
        b = float(baseline_rates.get(tool, 0.0))
        e = float(evolved_rates.get(tool, 0.0))
        delta = (e - b) * 100.0
        label, style = _status_style(delta, warning_threshold_pp)
        sc = int(sample_counts.get(tool, 0))
        dist = distribution.get(tool, {})
        if dist.get("_n_a") or not dist:
            cells_dist = ("n/a", "n/a", "n/a", "n/a", "n/a")
            dist_record: Optional[dict] = None
        else:
            cells_dist = (
                f"{dist['min']:.2f}", f"{dist['p25']:.2f}", f"{dist['median']:.2f}",
                f"{dist['p75']:.2f}", f"{dist['max']:.2f}",
            )
            dist_record = {k: dist[k] for k in ("min", "p25", "median", "p75", "max")}
        table.add_row(
            source or "?", tool, f"{b:.3f}", f"{e:.3f}",
            f"[{style}]{delta:+.2f}[/{style}]" if style else f"{delta:+.2f}",
            str(sc), *cells_dist,
            f"[{style}]{label}[/{style}]" if style else label,
        )
        per_tool_records.append({
            "tool": tool,
            "baseline_rate": b,
            "evolved_rate": e,
            "delta_pp": delta,
            "sample_count": sc,
            "distribution": dist_record,
            "status": label.split()[0],  # OK/WARN/FAIL/GAIN without emoji
        })

    console.print(Panel(
        "[dim]baseline meaning: desc/params=v1 frozen; reasoning=think-off (D-07 legend)[/dim]",
        title="source legend",
    ))
    console.print(table)

    # D-16 frequency bars (top-12 + others aggregate)
    _render_frequency_bars(sample_counts)

    return {
        "run_path": run["path"],
        "source": source,
        "per_tool": per_tool_records,
    }


def _render_frequency_bars(sample_counts: Counter) -> None:
    """D-16: top-12 + 'others (N tools)' aggregate; rendered as text rows in a Panel."""
    if not sample_counts:
        return
    sorted_tools = sample_counts.most_common()
    top = sorted_tools[:12]
    rest = sorted_tools[12:]
    max_count = top[0][1] if top else 1
    bar_width = 30
    lines: list[str] = []
    for name, count in top:
        bar_len = int((count / max_count) * bar_width) if max_count else 0
        lines.append(f"{name:<25} {'█' * bar_len} {count}")
    if rest:
        rest_total = sum(c for _, c in rest)
        bar_len = int((rest_total / max_count) * bar_width) if max_count else 0
        lines.append(f"{'others (' + str(len(rest)) + ' tools)':<25} {'█' * bar_len} {rest_total}")
    console.print(Panel("\n".join(lines), title="Sample frequency"))


def _sparkline(values: list[float]) -> str:
    """8-char Unicode block sparkline (▁▂▃▄▅▆▇█).

    Maps each value linearly to one of 8 block characters based on
    (v - min) / (max - min) span. Empty list → "". Single value (zero
    span) → all min-band characters (▁ × n).
    """
    if not values:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    return "".join(
        _SPARK_CHARS[min(7, int((v - lo) / span * 8))]
        for v in values
    )


def _render_diff(
    baseline_run: dict,
    evolved_run: dict,
    warning_threshold_pp: float,
) -> dict:
    """Render DIFF region: per-tool comparison between two specific runs (D-05).

    Returns dict consumed by Wave 4 dashboard.json schema.
    """
    b_metrics = baseline_run["metrics"]
    e_metrics = evolved_run["metrics"]
    b_rates = b_metrics.get("per_tool_evolved_rates", {}) or {}
    e_rates = e_metrics.get("per_tool_evolved_rates", {}) or {}
    all_tools = sorted(set(b_rates.keys()) | set(e_rates.keys()))

    table = Table(
        title=(
            f"DIFF region [{baseline_run['source']} vs {evolved_run['source']}]: "
            f"{baseline_run['path']} → {evolved_run['path']}"
        ),
        show_lines=False,
    )
    table.add_column("tool", justify="left", style="cyan")
    table.add_column("baseline_run rate", justify="right")
    table.add_column("evolved_run rate", justify="right")
    table.add_column("delta_pp", justify="right")
    table.add_column("status", justify="left", min_width=8, no_wrap=True)

    per_tool: list[dict] = []
    for tool in all_tools:
        b = float(b_rates.get(tool, 0.0))
        e = float(e_rates.get(tool, 0.0))
        delta = (e - b) * 100.0
        label, style = _status_style(delta, warning_threshold_pp)
        delta_cell = f"[{style}]{delta:+.2f}[/{style}]" if style else f"{delta:+.2f}"
        status_cell = f"[{style}]{label}[/{style}]" if style else label
        table.add_row(tool, f"{b:.3f}", f"{e:.3f}", delta_cell, status_cell)
        per_tool.append({
            "tool": tool,
            "baseline_rate": b,
            "evolved_rate": e,
            "delta_pp": delta,
            "status": label.split()[0] if label else "",
        })

    console.print(table)
    return {
        "baseline_run": baseline_run["path"],
        "evolved_run": evolved_run["path"],
        "per_tool": per_tool,
    }


def _render_trend(
    runs: list[dict],
    window_kind: str,
    window_value: int,
) -> dict:
    """Render TREND region: cross-run sparkline + quintile summary per tool (D-10 语义 B).

    `runs` is the windowed list (caller already filtered). For each tool,
    gather evolved_rate time-series across runs (oldest → newest).
    """
    if not runs:
        console.print("[dim]No runs for TREND region[/dim]")
        return {"window_kind": window_kind, "window_value": window_value, "tools": []}

    series: dict[str, list[tuple[str, float]]] = {}
    for run in runs:
        rates = run["metrics"].get("per_tool_evolved_rates", {}) or {}
        for tool, rate in rates.items():
            series.setdefault(tool, []).append((run["path"], float(rate)))

    table = Table(
        title=f"TREND region ({window_kind}={window_value}, {len(runs)} runs)",
        show_lines=False,
    )
    table.add_column("tool", justify="left", style="cyan")
    table.add_column("sparkline", justify="left", no_wrap=True)
    table.add_column("min", justify="right")
    table.add_column("p25", justify="right")
    table.add_column("median", justify="right")
    table.add_column("p75", justify="right")
    table.add_column("max", justify="right")
    table.add_column("n_runs", justify="right")

    tools_records: list[dict] = []
    for tool in sorted(series.keys()):
        ts = series[tool]
        rates = [r for _, r in ts]
        spark = _sparkline(rates)
        q = _quintiles(rates)
        table.add_row(
            tool, spark,
            f"{q['min']:.2f}", f"{q['p25']:.2f}", f"{q['median']:.2f}",
            f"{q['p75']:.2f}", f"{q['max']:.2f}",
            str(len(rates)),
        )
        tools_records.append({
            "tool": tool,
            "sparkline": spark,
            "series": [{"run_path": p, "rate": r} for p, r in ts],
            "summary": q,
        })

    console.print(Panel(
        "[dim]Distribution semantics (D-10 B): min/p25/median/p75/max are computed "
        "across N runs' evolved_rate time-series for each tool "
        "(cross-run, not within-run segment).[/dim]",
        title="TREND legend",
    ))
    console.print(table)

    return {
        "window_kind": window_kind,
        "window_value": window_value,
        "tools": tools_records,
    }


def _safe_truncate(text: str, max_len: int = 80) -> str:
    """D-15: redact-then-truncate ABStudy strings.

    Defensive: hermes-agent session importers already filter secrets upstream,
    but ab_comparison.json is downstream-rendered to stdout. Re-check before
    display to avoid second-order leak.
    """
    if not text:
        return ""
    if _contains_secret(text):
        return "[REDACTED — secret-like content]"
    return text[:max_len] + "..." if len(text) > max_len else text


def _count_ab_categories(ab_records: list[dict]) -> dict:
    """D-15: three-category counts + top-3 examples per category.

    Categories (mutually exclusive over the off×on truth grid):
    - think_on_saved = is_correct_off==False AND is_correct_on==True
    - think_on_regressed = is_correct_off==True AND is_correct_on==False
    - both_wrong = is_correct_off==False AND is_correct_on==False
    (is_correct_off==True AND is_correct_on==True is the boring "both right",
    not surfaced as a category — Phase 16 only highlights deltas.)

    Top-3 sorting:
    - saved: reasoning_text_on length DESC (longest reasoning = most explanatory win)
    - regressed: task_description length DESC (longest task = most likely a hard case)
    - both_wrong: unsorted (no narrative ordering)
    """
    saved = [r for r in ab_records if not r.get("is_correct_off") and r.get("is_correct_on")]
    regressed = [r for r in ab_records if r.get("is_correct_off") and not r.get("is_correct_on")]
    both_wrong = [r for r in ab_records if not r.get("is_correct_off") and not r.get("is_correct_on")]
    saved_sorted = sorted(saved, key=lambda r: len(r.get("reasoning_text_on", "") or ""), reverse=True)
    regressed_sorted = sorted(regressed, key=lambda r: len(r.get("task_description", "") or ""), reverse=True)

    def _top(recs: list[dict], k: int = 3) -> list[dict]:
        out = []
        for r in recs[:k]:
            out.append({
                "task_id": r.get("task_id"),
                "task_description": _safe_truncate(r.get("task_description", "") or ""),
                "correct_tool": r.get("correct_tool"),
                "selected_off": r.get("selected_off"),
                "selected_on": r.get("selected_on"),
                "reasoning_text_on": _safe_truncate(r.get("reasoning_text_on", "") or "", max_len=200),
            })
        return out

    return {
        "think_on_saved": {"count": len(saved), "top": _top(saved_sorted)},
        "think_on_regressed": {"count": len(regressed), "top": _top(regressed_sorted)},
        "both_wrong": {"count": len(both_wrong), "top": _top(both_wrong)},
    }


def _render_ab_study(reasoning_runs: list[dict]) -> dict:
    """D-15: ABStudy region — renders for reasoning runs with ab_comparison.json present."""
    if not reasoning_runs:
        return {"detected_runs": 0, "by_run": []}
    by_run: list[dict] = []
    for run in reasoning_runs:
        ab = run.get("ab_comparison") or []
        cats = _count_ab_categories(ab)
        by_run.append({
            "run_path": run["path"],
            "think_on_saved": cats["think_on_saved"]["count"],
            "think_on_regressed": cats["think_on_regressed"]["count"],
            "both_wrong": cats["both_wrong"]["count"],
            "top_examples": {
                "saved": cats["think_on_saved"]["top"],
                "regressed": cats["think_on_regressed"]["top"],
                "both_wrong": cats["both_wrong"]["top"],
            },
        })

    table = Table(title="ABStudy (Phase 15 reasoning runs)", show_lines=False)
    table.add_column("run_path", justify="left", style="cyan")
    table.add_column("think_on_saved", justify="right", style="bold green")
    table.add_column("think_on_regressed", justify="right", style="bold red")
    table.add_column("both_wrong", justify="right", style="yellow")
    for entry in by_run:
        table.add_row(
            entry["run_path"],
            str(entry["think_on_saved"]),
            str(entry["think_on_regressed"]),
            str(entry["both_wrong"]),
        )
    console.print(table)

    for entry in by_run:
        top = entry["top_examples"]
        lines: list[str] = [f"[bold]Run:[/bold] {entry['run_path']}"]
        for cat_name, recs in [
            ("saved", top["saved"]),
            ("regressed", top["regressed"]),
            ("both_wrong", top["both_wrong"]),
        ]:
            if recs:
                lines.append(f"\n[bold]{cat_name}[/bold]")
                for r in recs:
                    lines.append(
                        f"  task#{r['task_id']}: {r['task_description']}"
                        f" | correct={r['correct_tool']} | off={r['selected_off']} on={r['selected_on']}"
                    )
                    if r.get("reasoning_text_on"):
                        lines.append(f"    reasoning: {r['reasoning_text_on']}")
        console.print(Panel("\n".join(lines), title="ABStudy top-3"))

    return {"detected_runs": len(reasoning_runs), "by_run": by_run}


def _write_dashboard_json(
    output_path: Path,
    *,
    scanned_runs: int,
    dropped_runs: list[dict],
    latest_data: Optional[dict],
    diff_data: Optional[dict],
    trend_data: dict,
    ab_study_data: dict,
    warnings_list: list[dict],
    summary: dict,
) -> None:
    """Serialize 8 top-level fields to dashboard.json (D-04 schema).

    Top-level keys: latest, diff, trend, ab_study, source_legend, dropped_runs,
    summary, warnings + auxiliary generated_at and scanned_runs.
    """
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "scanned_runs": scanned_runs,
        "dropped_runs": dropped_runs,
        "source_legend": {
            "desc": "evolve_tool_descriptions, baseline=v1 frozen",
            "params": "evolve_tool_params, baseline=v1 frozen",
            "reasoning": "evolve_tool_reasoning, baseline=think-off",
        },
        "latest": latest_data,
        "diff": diff_data,
        "trend": trend_data,
        "ab_study": ab_study_data,
        "warnings": warnings_list,
        "summary": summary,
    }
    output_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    console.print(f"[green]Wrote dashboard.json: {output_path}[/green]")


# ── Click CLI ──────────────────────────────────────────────────────────────


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
    # D-06 mutex check
    if trend_window is not None and trend_days is not None:
        raise click.UsageError("--trend-window and --trend-days are mutually exclusive")

    # Wave 4: collectors for dashboard.json 8-field schema (D-04)
    latest_data: Optional[dict] = None
    diff_data: Optional[dict] = None
    trend_data: dict = {
        "window_kind": "n",
        "window_value": trend_window if trend_window is not None else 10,
        "tools": [],
    }
    ab_study_data: dict = {"detected_runs": 0, "by_run": []}
    warnings_list: list[dict] = []

    # Build root list: defaults + --runs additions
    roots = list(DEFAULT_ROOTS)
    for r in runs:
        roots.append(Path(r))
    runs_paths = _scan_runs(tuple(roots))

    # D-02: empty default roots + no --runs → exit 2
    if not runs_paths:
        console.print("[red]No runs found in default roots or --runs paths[/red]")
        raise click.UsageError("no runs found; pass --runs <path> or populate output/tools[_reasoning]/")

    # Full classification pass: every scanned run is either usable or dropped.
    # Latest is the newest usable; all unusable runs (regardless of position)
    # surface in dropped_runs[] so dashboard.json gives a complete picture.
    latest_run = None
    dropped: list[dict] = []
    usable_runs: list[dict] = []  # ordered as scanned (newest first via reversed below)
    for p in reversed(runs_paths):  # newest first
        loaded = _load_run(p)
        if loaded is None or loaded.get("metrics") is None:
            dropped.append({
                "path": str(p),
                "reason": loaded.get("_drop_reason", "load failed") if loaded else "load failed",
            })
            continue
        m = loaded["metrics"]
        if loaded["source"] is None:
            dropped.append({"path": str(p), "reason": "unknown source"})
            continue
        if "per_tool_baseline_rates" not in m or "per_tool_evolved_rates" not in m:
            dropped.append({"path": str(p), "reason": "missing per_tool_*_rates"})
            continue
        if m.get("status") == "FAILED":
            dropped.append({"path": str(p), "reason": "run status=FAILED"})
            continue
        usable_runs.append(loaded)
    if usable_runs:
        latest_run = usable_runs[0]

    if latest_run is None:
        console.print("[yellow]No usable runs for LATEST region[/yellow]")
    else:
        latest_data = _render_latest(latest_run, segment, warning_threshold_pp)

    # ── DIFF region (D-05) ────────────────────────────────────────────────
    if baseline_run is not None or evolved_run is not None:
        if baseline_run is None or evolved_run is None:
            console.print(
                "[yellow]DIFF region requires both --baseline-run AND --evolved-run; "
                "got only one — skipping DIFF[/yellow]"
            )
        else:
            b_loaded = _load_run(Path(baseline_run) / "metrics.json")
            e_loaded = _load_run(Path(evolved_run) / "metrics.json")
            if (
                b_loaded and b_loaded.get("metrics")
                and "per_tool_evolved_rates" in b_loaded["metrics"]
                and e_loaded and e_loaded.get("metrics")
                and "per_tool_evolved_rates" in e_loaded["metrics"]
            ):
                diff_data = _render_diff(b_loaded, e_loaded, warning_threshold_pp)
            else:
                console.print(
                    "[yellow]DIFF region: one or both runs missing per_tool_evolved_rates — skipped[/yellow]"
                )

    # ── TREND region (D-06) ───────────────────────────────────────────────
    valid_runs: list[dict] = []
    for p in runs_paths:
        loaded = _load_run(p)
        if (
            loaded and loaded.get("metrics") and loaded.get("source")
            and "per_tool_evolved_rates" in loaded["metrics"]
            and loaded["metrics"].get("status") != "FAILED"
        ):
            valid_runs.append(loaded)

    if trend_days is not None:
        window_kind = "days"
        window_value = trend_days
        cutoff = datetime.now().timestamp() - (trend_days * 86400.0)
        windowed = [
            r for r in valid_runs
            if Path(r["path"]).stat().st_mtime >= cutoff
        ]
    else:
        window_kind = "n"
        window_value = trend_window if trend_window is not None else 10
        windowed = (
            valid_runs[-window_value:]
            if len(valid_runs) > window_value
            else valid_runs
        )

    if windowed:
        trend_data = _render_trend(windowed, window_kind, window_value)
    else:
        trend_data = {
            "window_kind": window_kind,
            "window_value": window_value,
            "tools": [],
        }

    # ── ABStudy region (D-15) ────────────────────────────────────────────
    reasoning_with_ab = [
        r for r in valid_runs
        if r.get("source") == "reasoning" and r.get("ab_comparison")
    ]
    if reasoning_with_ab:
        ab_study_data = _render_ab_study(reasoning_with_ab)

    # ── D-13 warnings + D-08 fallback messages (latest run only) ─────────
    if latest_run is not None:
        b_rates = latest_run["metrics"].get("per_tool_baseline_rates", {}) or {}
        e_rates = latest_run["metrics"].get("per_tool_evolved_rates", {}) or {}
        for tool in sorted(set(b_rates) | set(e_rates)):
            delta = (float(e_rates.get(tool, 0.0)) - float(b_rates.get(tool, 0.0))) * 100.0
            if delta <= -warning_threshold_pp:
                warnings_list.append({
                    "tool": tool,
                    "delta_pp": delta,
                    "run_path": latest_run["path"],
                })
                console.print(
                    f"[yellow]WARNING: {tool} regressed by {delta:+.2f}pp in "
                    f"{latest_run['path']} (threshold: -{warning_threshold_pp:.1f}pp)[/yellow]"
                )
        if "raw_predictions" not in latest_run["metrics"]:
            console.print(
                f"[yellow]raw_predictions absent in {latest_run['path']}; "
                f"distribution disabled for this run[/yellow]"
            )

    if dropped:
        console.print(f"\n[yellow]Dropped {len(dropped)} run(s):[/yellow]")
        for d in dropped:
            console.print(f"[yellow]  - {d['path']}: {d['reason']}[/yellow]")

    # ── Wave 4: emit dashboard.json (D-04) ────────────────────────────────
    if output is not None:
        out_path = Path(output)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = Path.cwd() / f"dashboard_{ts}.json"

    _write_dashboard_json(
        out_path,
        scanned_runs=len(runs_paths),
        dropped_runs=dropped,
        latest_data=latest_data,
        diff_data=diff_data,
        trend_data=trend_data,
        ab_study_data=ab_study_data,
        warnings_list=warnings_list,
        summary={
            "warning_threshold_pp": warning_threshold_pp,
            "segment_kind": segment,
        },
    )

    # D-13: warnings DO NOT affect exit code.
    return 0


if __name__ == "__main__":
    main()
