"""Evolve hermes-agent TOOL PARAMETER descriptions using DSPy + GEPA.

Phase 13 — evolves PARAMETER descriptions only; top-level tool descriptions
are frozen (physically isolated in ToolModule._frozen_tool_desc, see 13-02).
For top-level evolution use evolve_tool_descriptions.py (Phase 5).
Joint top-level + per-param optimization is deferred to Phase 17.

Pipeline (numbered to match comments in evolve()):
    1.  Config load + CLI overrides (max_cost_usd, reflection_model)
    1a. W2 --param-group-size NO-OP warning (CONTEXT D-15)
    2.  Discover + extract tools via Phase 2 loader; --tools subset filter
    3.  Build baseline ToolModule (per-param sub-Module structure, 13-02)
    4.  Dry-run early-return — print param_predictors_discovered + plan
    5.  Load dataset (default --eval-source load; 13-04 D-16)
    6.  Configure LM with track_usage=True (RESEARCH Pitfall 2 guard)
    7.  Resolve reflection_model (config.reflection_model or optimizer_model)
    8.  GEPA setup with joint_tool_param_metric_with_feedback (Pitfall 7)
    9.  GEPA compile inside CostTracker — gepa_kwargs.stop_callbacks for
        mid-run abort; loud raise on GEPA failure unless --allow-miprov2-fallback
    10. Extract evolved descriptions
    11. Constraint chain: param size (200-char) → non-empty → factual →
        ParamConsistencyChecker → fail-closed
    12. Holdout evaluation with bare joint_tool_param_metric (D-18 dual-pair)
    13. CrossToolRegressionChecker + persist_per_tool_rates (13-06)
    14. V1BaselineGate (13-07): historical or inline fallback
    15. Success: write metrics.json + evolved_descriptions.json + diff.txt
    16. Return 0

Failure branching:
    - Constraint fail        → output/tools/FAILED_<ts>/
    - Regression fail        → output/tools/FAILED_<ts>/
    - V1 baseline fail       → output/tools/FAILED_<ts>/
    - Cost cap exceeded      → output/tools/ABORTED_<ts>/
    - GEPA loud raise        → propagates (default; non-zero exit)

Phase 13 scope guard (CONTEXT.md): this module MUST NOT import or invoke
the writeback path from evolution.tools.tool_loader. Phase 13 only writes
to output/tools/; that capability is deferred to Phase 22.

Wave 0 contract preservation: re-exports V1BaselineGate / check_v1_baseline_gate /
compute_v1_baseline so tests/tools/test_v1_baseline_gate.py continues to pass
(originally introduced by the 13-07 shell module that this CLI replaces).
"""

from __future__ import annotations

import difflib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import click
import dspy
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from evolution.core.config import EvolutionConfig, get_hermes_agent_path
from evolution.core.constraints import ConstraintValidator
from evolution.core.cost_tracker import CostTracker, CostBudgetExceeded
from evolution.tools.tool_loader import (
    discover_tool_files,
    extract_tool_descriptions,
    ToolDescription,
)
from evolution.tools.tool_module import ToolModule
from evolution.tools.tool_dataset import ToolDatasetBuilder, ToolSelectionDataset
from evolution.tools.tool_metric import (
    joint_tool_param_metric,
    joint_tool_param_metric_with_feedback,
    CrossToolRegressionChecker,
    persist_per_tool_rates,
)
from evolution.tools.tool_constraints import ToolFactualChecker, ParamConsistencyChecker
from evolution.tools.v1_baseline_gate import (
    V1BaselineGate,
    check_v1_baseline_gate,
    compute_v1_baseline,
)


__all__ = [
    "evolve",
    "main",
    # Wave 0 / 13-07 re-exports — DO NOT REMOVE without verifying
    # tests/tools/test_v1_baseline_gate.py still passes.
    "V1BaselineGate",
    "check_v1_baseline_gate",
    "compute_v1_baseline",
    # Test seams (Wave 0 RED test patches reach for these names directly).
    "_load_tool_descriptions",
    "_load_dataset",
]


console = Console()


# ── Helpers ────────────────────────────────────────────────────────────────


def _generate_param_diff(
    original_tools: list[ToolDescription],
    evolved_tools: list[ToolDescription],
) -> str:
    """Generate unified diff for per-parameter description changes.

    Mirrors Phase 5 _generate_diff but diffs each `params[i].description`
    rather than the top-level `description` (which is frozen in Phase 13).

    Args:
        original_tools: List of original ToolDescription objects.
        evolved_tools: List of evolved ToolDescription objects.

    Returns:
        Concatenated unified diff string for all changed param descriptions.
        Tools with no per-param changes are skipped.
    """
    original_map = {t.name: t for t in original_tools}
    diff_parts: list[str] = []

    for evolved in evolved_tools:
        original = original_map.get(evolved.name)
        if original is None:
            continue
        orig_param_map = {p.name: (p.description or "") for p in original.params}
        evol_param_map = {p.name: (p.description or "") for p in evolved.params}
        tool_diff_pieces: list[str] = []
        for pname, evol_desc in evol_param_map.items():
            orig_desc = orig_param_map.get(pname, "")
            if orig_desc == evol_desc:
                continue
            orig_lines = orig_desc.splitlines(keepends=True) or [""]
            evol_lines = evol_desc.splitlines(keepends=True) or [""]
            piece = "".join(
                difflib.unified_diff(
                    orig_lines,
                    evol_lines,
                    fromfile=f"{evolved.name}.{pname} (original)",
                    tofile=f"{evolved.name}.{pname} (evolved)",
                )
            )
            if piece:
                tool_diff_pieces.append(piece)
        if tool_diff_pieces:
            diff_parts.append("\n".join(tool_diff_pieces))

    return "\n".join(diff_parts)


def _filter_tools(
    all_tools: list[ToolDescription],
    tools_filter: Optional[str],
) -> list[ToolDescription]:
    """Filter tool list against a comma-separated --tools subset.

    Args:
        all_tools: Output of extract_tool_descriptions().
        tools_filter: Comma-separated tool names; None or empty → no filter.

    Returns:
        Filtered list. Unknown names emit a warning and are dropped.

    Raises:
        click.UsageError: When tools_filter is non-empty but no tools match
            (avoids burning LLM budget on a misconfigured run).
    """
    if not tools_filter:
        return list(all_tools)
    requested = [name.strip() for name in tools_filter.split(",") if name.strip()]
    if not requested:
        return list(all_tools)
    by_name = {t.name: t for t in all_tools}
    matched: list[ToolDescription] = []
    unknown: list[str] = []
    for name in requested:
        if name in by_name:
            matched.append(by_name[name])
        else:
            unknown.append(name)
    if unknown:
        console.print(
            f"[yellow]⚠ --tools includes unknown name(s): "
            f"{', '.join(unknown)} — dropped[/yellow]"
        )
    if not matched:
        raise click.UsageError(
            f"--tools filter matched 0 tools (requested: {requested}; "
            f"available: {sorted(by_name.keys())[:8]}...). Aborting before LLM spend."
        )
    return matched


# ── Test seams (overridable via monkeypatch) ──────────────────────────────


def _load_tool_descriptions(hermes_agent_path: Path) -> list[ToolDescription]:
    """Discover + extract all ToolDescription instances from the hermes-agent repo.

    Wrapper exists so Wave 0 tests can monkeypatch a small fixture
    (test fixture: returns []). Production wires through to Phase 2 loader.

    Args:
        hermes_agent_path: Path to a hermes-agent checkout.

    Returns:
        Flat list of ToolDescription. Empty list when nothing discovered.
    """
    tool_files = discover_tool_files(hermes_agent_path)
    if not tool_files:
        return []
    out: list[ToolDescription] = []
    for f in tool_files:
        out.extend(extract_tool_descriptions(f))
    return out


def _load_dataset(
    eval_source: str,
    config: EvolutionConfig,
    all_tools: list[ToolDescription],
) -> tuple[list[dspy.Example], list[dspy.Example], list[dspy.Example]]:
    """Build trainset/valset/holdout dspy.Example lists.

    Wrapper exists so Wave 0 tests can monkeypatch a tiny dataset
    (test fixture: returns ([], [], [])). Production goes through
    ToolSelectionDataset.load() (D-16 default) or the synthetic builder.

    Args:
        eval_source: Either 'load' (read datasets/tools/) or 'synthetic'
            (regenerate via ToolDatasetBuilder).
        config: EvolutionConfig for synthetic generation kwargs.
        all_tools: Discovered ToolDescription list.

    Returns:
        (train, val, holdout) tuple of dspy.Example lists.
    """
    dataset_path = Path("datasets") / "tools"
    if eval_source == "synthetic":
        builder = ToolDatasetBuilder(config)
        dataset = builder.generate(all_tools)
        dataset.save(dataset_path)
    elif eval_source == "load":
        if not dataset_path.exists():
            raise click.UsageError(
                f"--eval-source load requires {dataset_path}/ to exist. "
                f"Run --eval-source synthetic first or copy a Phase 4 dataset there."
            )
        dataset = ToolSelectionDataset.load(dataset_path)
    else:
        raise click.UsageError(f"Unknown eval-source: {eval_source!r}")
    return (
        dataset.to_dspy_examples("train"),
        dataset.to_dspy_examples("val"),
        dataset.to_dspy_examples("holdout"),
    )


# ── Cost stopper adapter (W6 read_first contract) ────────────────────────


class _CostStopper:
    """Adapter satisfying gepa.utils.stop_condition.StopperProtocol.

    W6: GEPA 3.1.3's stop_callbacks expects `__call__(gepa_state) -> bool`
    rather than a bare lambda; wrapping ensures both `runtime_checkable`
    isinstance checks and direct invocation work.

    Args:
        tracker: A CostTracker whose .exceeded() returns True when the
            spent USD has crossed max_usd.
    """

    def __init__(self, tracker: CostTracker):
        self._tracker = tracker

    def __call__(self, gepa_state: Any) -> bool:  # noqa: D401
        try:
            return bool(self._tracker.exceeded())
        except Exception:
            # Never raise inside a stop callback — that aborts GEPA loudly
            # without giving us a chance to write ABORTED_<ts>/.
            return False


# ── Holdout pair scorer ───────────────────────────────────────────────────


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

    Args:
        module: ToolModule (or compatible) callable producing
            dspy.Prediction(selected_tool, selected_params).
        holdout: List of dspy.Example with correct_tool / correct_params.
        lm: dspy.LM for scoring context.

    Returns:
        (mean_score, tool_pairs, param_pairs) where tool_pairs is the
        (correct_tool, selected_tool) sequence consumable by
        CrossToolRegressionChecker, and param_pairs is the
        (correct_params_json, selected_params_json) sequence for D-18 dump.
    """
    if not holdout:
        return 0.0, [], []
    total = 0.0
    n = 0
    tool_pairs: list[tuple[str, str]] = []
    param_pairs: list[tuple[str, str]] = []
    with dspy.context(lm=lm):
        for ex in holdout:
            # BL-04: only catch the actual concern (MagicMock holdout
            # examples in unit tests may lack a real .task_description).
            # Production LM errors (timeout / rate limit / malformed
            # completion / network) raise the SAME exception on the retry
            # because ex.task_description is unchanged — so the retry
            # doubles cost on failure, masks the first error, and
            # eventually re-raises uncaught, tearing down the pipeline.
            try:
                task = ex.task_description
            except AttributeError:
                task = getattr(ex, "task_description", "")
            try:
                pred = module(task_description=task)
            except Exception as e:
                console.print(
                    f"[yellow]holdout example skipped due to LM error: "
                    f"{type(e).__name__}: {e}[/yellow]"
                )
                # Skip this example entirely: do NOT count toward denominator
                # (n) and do NOT append to tool_pairs / param_pairs. This
                # way one bad example does not silently dilute the average,
                # but a single transient failure also does not abort the
                # whole holdout loop.
                continue
            score = joint_tool_param_metric(ex, pred)
            try:
                total += float(score)
            except (TypeError, ValueError):
                pass
            n += 1
            tool_pairs.append(
                (
                    getattr(ex, "correct_tool", "") or "",
                    getattr(pred, "selected_tool", "") or "",
                )
            )
            correct_params_json = json.dumps(
                getattr(ex, "correct_params", {}) or {},
                ensure_ascii=False,
                sort_keys=True,
            )
            selected_params_raw = getattr(pred, "selected_params", "") or ""
            param_pairs.append((correct_params_json, str(selected_params_raw)))
    return total / max(1, n), tool_pairs, param_pairs


# ── Output dir writers ────────────────────────────────────────────────────


def _write_failed_dir(
    reason: str,
    metrics: dict,
    original_tools: list[ToolDescription],
    evolved_tools: Optional[list[ToolDescription]],
) -> Path:
    """Persist a FAILED_<ts>/ directory with metrics.json + partial diff.

    Args:
        reason: Short status string (e.g. 'CONSTRAINTS_FAILED', 'REGRESSION_FAILED',
            'V1_BASELINE_FAILED').
        metrics: Dict to dump as metrics.json (mutated to include status).
        original_tools: Pre-evolution list for diff base.
        evolved_tools: Post-evolution list (may be None on early-stage failures).

    Returns:
        Path to the FAILED_<ts>/ directory.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("output") / "tools" / f"FAILED_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics = dict(metrics)
    metrics.setdefault("status", reason)
    metrics["constraints_passed"] = metrics.get("constraints_passed", False)
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    if evolved_tools is not None:
        diff_text = _generate_param_diff(original_tools, evolved_tools)
        (out_dir / "diff.txt").write_text(diff_text, encoding="utf-8")
    return out_dir


def _write_aborted_dir(
    tracker: CostTracker,
    optimizer: Any,
    optimized_module: Any,
    baseline_module: ToolModule,
    original_tools: list[ToolDescription],
    reflection_model_name: str,
) -> Path:
    """Persist an ABORTED_<ts>/ directory after CostBudgetExceeded.

    Calls `tracker.write_aborted_json(...)` for the structured payload and
    additionally writes `partial_diff.txt` (param-level diff between original
    tools and best-so-far evolved tools) to give users a manual cherry-pick path.

    Args:
        tracker: The CostTracker that just exceeded its budget.
        optimizer: GEPA-or-equivalent compile target (may expose
            `_evaluated_candidates`).
        optimized_module: Best-so-far module returned by compile (or None if
            the abort fired before any candidate was returned).
        baseline_module: The original ToolModule used as fallback when no
            optimized state is available.
        original_tools: Pre-evolution list for diff base.
        reflection_model_name: Resolved reflection model string (for record).

    Returns:
        Path to the ABORTED_<ts>/ directory.
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    abort_dir = Path("output") / "tools" / f"ABORTED_{ts}"

    # Build best-so-far evolved tools — fall back to baseline when nothing usable.
    if optimized_module is not None and hasattr(optimized_module, "get_evolved_descriptions"):
        try:
            partial_evolved = optimized_module.get_evolved_descriptions()
        except Exception:
            partial_evolved = baseline_module.get_evolved_descriptions()
    else:
        partial_evolved = baseline_module.get_evolved_descriptions()

    # Structured per-(tool, param) summary for aborted.json.
    orig_map = {t.name: t for t in original_tools}
    partial_diff_payload: list[dict] = []
    for ev in partial_evolved:
        orig = orig_map.get(ev.name)
        orig_params = {p.name: (p.description or "") for p in (orig.params if orig else [])}
        params_summary: list[dict] = []
        for p in ev.params:
            params_summary.append(
                {
                    "name": p.name,
                    "original": orig_params.get(p.name, ""),
                    "evolved": p.description or "",
                }
            )
        partial_diff_payload.append({"tool": ev.name, "params": params_summary})

    evaluated_candidates = int(getattr(optimizer, "_evaluated_candidates", 0) or 0)

    tracker.write_aborted_json(
        abort_dir,
        evaluated_candidates=evaluated_candidates,
        partial_diff=partial_diff_payload,
        num_predictors=len(list(baseline_module.named_predictors())),
        reflection_model=reflection_model_name,
        optimizer_used="gepa",
    )

    abort_dir.mkdir(parents=True, exist_ok=True)
    (abort_dir / "partial_diff.txt").write_text(
        _generate_param_diff(original_tools, partial_evolved),
        encoding="utf-8",
    )
    return abort_dir


# ── Main pipeline (Click command) ─────────────────────────────────────────


@click.command()
@click.option("--iterations", default=10, type=int,
              help="GEPA iterations (affects max_metric_calls; overridden by --auto)")
@click.option("--eval-source", default="load",
              type=click.Choice(["synthetic", "load"]),
              help="Default load — reuse Phase 4 dataset (D-16)")
@click.option("--hermes-repo", default=None,
              help="Path to hermes-agent repo (overrides HERMES_AGENT_REPO env var)")
@click.option("--dry-run", is_flag=True,
              help="Show setup + discovered param count, no optimization")
@click.option("--model", default=None, help="Override all LLM model names")
@click.option("--api-base", default=None, help="Override API base URL")
@click.option("--tools", "tools", default=None,
              help="Comma-separated subset of tool names; empty = all")
@click.option("--max-cost-usd", default=None, type=float,
              help="USD cost cap (overrides EVOLUTION_MAX_COST_USD); default 20.0")
@click.option("--reflection-model", default=None,
              help="Separate model for GEPA reflection_lm; defaults to optimizer_model")
@click.option("--param-group-size", default=None, type=int,
              help="(NO-OP in Phase 13 — emits warning when set; cost cap is the "
                   "primary constraint; grouping deferred to Phase 14 per D-15)")
@click.option("--baseline-run", default=None,
              help="Path to a Phase 5 output dir with metrics.json; omit → inline baseline fallback")
@click.option("--allow-miprov2-fallback", is_flag=True,
              help="Opt-in silent fallback to MIPROv2 on GEPA failure "
                   "(folded todo 2026-05-07-loud-gepa-fallback.md)")
@click.option("--component-selector", default="round_robin",
              type=click.Choice(["round_robin", "all"]),
              help="GEPA component selection strategy")
@click.option("--auto", default=None,
              type=click.Choice(["light", "medium", "heavy"]),
              help="GEPA auto-budget; mutex with iterations→max_metric_calls fallback")
def evolve(
    iterations: int,
    eval_source: str,
    hermes_repo: Optional[str],
    dry_run: bool,
    model: Optional[str],
    api_base: Optional[str],
    tools: Optional[str],
    max_cost_usd: Optional[float],
    reflection_model: Optional[str],
    param_group_size: Optional[int],
    baseline_run: Optional[str],
    allow_miprov2_fallback: bool,
    component_selector: str,
    auto: Optional[str],
) -> None:
    """Evolve hermes-agent TOOL PARAMETER descriptions using DSPy + GEPA.

    Phase 13: top-level tool descriptions are frozen; only per-parameter
    descriptions are optimized. For top-level evolution see
    evolve_tool_descriptions (Phase 5).
    """
    exit_code = _evolve_impl(
        iterations=iterations,
        eval_source=eval_source,
        hermes_repo=hermes_repo,
        dry_run=dry_run,
        model=model,
        api_base=api_base,
        tools_filter=tools,
        max_cost_usd=max_cost_usd,
        reflection_model=reflection_model,
        param_group_size=param_group_size,
        baseline_run=baseline_run,
        allow_miprov2_fallback=allow_miprov2_fallback,
        component_selector=component_selector,
        auto=auto,
    )
    if exit_code:
        # Click's runner.invoke captures sys.exit; production callers also
        # see the documented exit-code matrix (0 success / 1 gate fail /
        # 2 cost abort / GEPA loud raise propagates with exit_code 1).
        sys.exit(int(exit_code))


# Alias matching the historical Phase 5 entrypoint convention. `main` and
# `evolve` are the same Click command — both names are documented exports
# so external orchestration (or a future `python -m evolution.tools.evolve_tool_params`)
# can invoke either.
main = evolve


def _evolve_impl(
    *,
    iterations: int,
    eval_source: str,
    hermes_repo: Optional[str],
    dry_run: bool,
    model: Optional[str],
    api_base: Optional[str],
    tools_filter: Optional[str],
    max_cost_usd: Optional[float],
    reflection_model: Optional[str],
    param_group_size: Optional[int],
    baseline_run: Optional[str],
    allow_miprov2_fallback: bool,
    component_selector: str,
    auto: Optional[str],
) -> int:
    """Phase 13 evolution pipeline — returns OS exit code.

    Exit codes:
        0 — success
        1 — constraint / regression / v1 baseline gate failure
        2 — cost cap exceeded mid-run (CostBudgetExceeded)
        (uncaught GEPA failure propagates via raise → Python default exit 1)
    """
    started_at_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    start_time = time.time()

    # ── 1. Configuration ────────────────────────────────────────────────
    overrides: dict[str, Any] = {}
    if hermes_repo:
        overrides["hermes_repo"] = hermes_repo
    if model:
        overrides["model"] = model
    if api_base:
        overrides["api_base"] = api_base
    if iterations:
        overrides["iterations"] = iterations
    if max_cost_usd is not None:
        overrides["max_cost_usd"] = max_cost_usd
    if reflection_model is not None:
        overrides["reflection_model"] = reflection_model
    config = EvolutionConfig.load(**overrides)

    console.print(
        "\n[bold cyan]Hermes Agent Self-Evolution[/bold cyan]"
        " — Per-Parameter Description Optimization (Phase 13)\n"
    )

    # ── 1a. W2 --param-group-size NO-OP warning (CONTEXT D-15) ─────────
    if param_group_size is not None:
        _warning_msg = (
            f"⚠ --param-group-size={param_group_size} accepted but NO-OP in Phase 13 "
            f"(grouping/batch-freeze deferred to Phase 14 per CONTEXT D-15); "
            f"cost cap (--max-cost-usd) is the primary constraint."
        )
        click.echo(_warning_msg, err=True)

    # ── 2. Discover + extract + filter ─────────────────────────────────
    console.print("[bold]Discovering tool files...[/bold]")
    try:
        all_tools = _load_tool_descriptions(config.hermes_agent_path)
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        return 1
    if not all_tools:
        # No tools discovered is a hard configuration error in BOTH dry-run
        # and full-run modes. Returning 0 on dry-run with empty input would
        # mask misconfigured HERMES_AGENT_REPO (Wave 0 test contract:
        # test_loud_gepa_failure_and_opt_in expects exit_code != 0 when the
        # discovery seam is patched to return []).
        _empty_msg = (
            "param_predictors_discovered=0 (no tools available; "
            "set HERMES_AGENT_REPO or pass --hermes-repo to a real repo)"
        )
        click.echo(_empty_msg, err=True)
        console.print(
            "[red]No tool descriptions discovered — aborting (configuration error).[/red]"
        )
        return 1
    all_tools = _filter_tools(all_tools, tools_filter)

    # ── 3. Build baseline ToolModule ───────────────────────────────────
    original_tools = list(all_tools)
    baseline_module = ToolModule(all_tools)
    num_predictors = len(list(baseline_module.named_predictors()))

    # Display discovered tools (skipped during dry-run for deterministic stdout).
    if not dry_run:
        table = Table(title="Discovered Tools (param-only optimization scope)")
        table.add_column("Tool Name", style="bold")
        table.add_column("Description Length", justify="right")
        table.add_column("Parameters", justify="right")
        for tool in all_tools:
            table.add_row(tool.name, str(len(tool.description)), str(len(tool.params)))
        console.print(table)

    # ── 4. Dry-run early return ────────────────────────────────────────
    if dry_run:
        click.echo(f"param_predictors_discovered={num_predictors}")
        click.echo(f"tools_in_scope={len(all_tools)}")
        click.echo(f"iterations_planned={iterations}")
        click.echo(f"eval_source={eval_source}")
        click.echo(f"max_cost_usd_cap={config.max_cost_usd}")
        # Heuristic budget estimate (RESEARCH Pitfall 6 formula).
        budget_estimate = iterations * max(50, 3 * num_predictors)
        click.echo(f"max_metric_calls_estimate={budget_estimate}")
        console.print("[bold green]DRY RUN — setup validated.[/bold green]")
        return 0

    # ── 5. Load dataset ─────────────────────────────────────────────────
    console.print(f"\n[bold]Building evaluation dataset[/bold] (source: {eval_source})")
    trainset, valset, holdout = _load_dataset(eval_source, config, all_tools)
    if not trainset and not valset and not holdout:
        console.print("[red]Empty dataset — cannot run optimization.[/red]")
        return 1
    console.print(
        f"  Split: {len(trainset)} train / {len(valset)} val / {len(holdout)} holdout"
    )

    # ── 6. Configure LM (Pitfall 2 guard: track_usage=True) ────────────
    lm = dspy.LM(config.eval_model, **config.get_lm_kwargs())
    dspy.configure(lm=lm, track_usage=True)

    # ── 7. Resolve reflection model ────────────────────────────────────
    reflection_model_name = config.reflection_model or config.optimizer_model
    console.print(
        f"  [dim]reflection_lm:[/dim] {reflection_model_name} "
        f"(eval_model={config.eval_model})"
    )

    # ── 8/9. GEPA setup + compile inside CostTracker ───────────────────
    tracker = CostTracker(max_usd=config.max_cost_usd)
    optimizer = None
    optimized_module = None
    optimizer_used = "gepa"
    # BL-01 fix: capture spent USD inside the `with tracker:` block. After
    # __exit__ runs, tracker._tracker is None and poll() falls back to
    # self._injected_usage (empty in production) → returns 0.0 silently.
    # We snapshot the live value before the context exits and use that as
    # the canonical cost for metrics.json on every success-path code path.
    final_spent_usd = 0.0

    try:
        with tracker:
            stopper = _CostStopper(tracker)
            gepa_kwargs: dict[str, Any] = {"stop_callbacks": [stopper]}
            reflection_lm = dspy.LM(reflection_model_name, **config.get_lm_kwargs())

            # Budget — exactly one of auto / max_metric_calls (Pitfall 6).
            optimizer_init_kwargs: dict[str, Any] = {
                "metric": joint_tool_param_metric_with_feedback,
                "reflection_lm": reflection_lm,
                "component_selector": component_selector,
                "track_stats": True,
                "seed": 0,
                "gepa_kwargs": gepa_kwargs,
            }
            if auto is not None:
                optimizer_init_kwargs["auto"] = auto
            else:
                optimizer_init_kwargs["max_metric_calls"] = max(
                    iterations * 50, 3 * num_predictors
                )
            optimizer = dspy.GEPA(**optimizer_init_kwargs)
            optimized_module = optimizer.compile(
                baseline_module,
                trainset=trainset,
                valset=valset,
            )
            # BL-01: poll BEFORE __exit__ disposes the live UsageTracker.
            final_spent_usd = float(tracker.poll())
    except CostBudgetExceeded as cap_exc:
        abort_dir = _write_aborted_dir(
            tracker=tracker,
            optimizer=optimizer,
            optimized_module=optimized_module,
            baseline_module=baseline_module,
            original_tools=original_tools,
            reflection_model_name=reflection_model_name,
        )
        console.print(
            f"[red]Cost budget exceeded — aborted.[/red] {cap_exc} "
            f"\n  Wrote {abort_dir}/"
        )
        return 2
    except Exception as gepa_err:
        if not allow_miprov2_fallback:
            console.print(
                f"[red]GEPA failed: {gepa_err}[/red] "
                f"(default loud raise per D-15a — pass --allow-miprov2-fallback to opt in to MIPROv2)"
            )
            raise
        console.print(
            f"[yellow]GEPA failed ({gepa_err}); falling back to MIPROv2 per --allow-miprov2-fallback[/yellow]"
        )
        optimizer_used = "miprov2"
        try:
            mipro = dspy.MIPROv2(metric=joint_tool_param_metric, auto="light")
            optimized_module = mipro.compile(baseline_module, trainset=trainset)
            # BL-01 (fallback path): tracker has already __exit__-ed, so its
            # live UsageTracker is gone; MIPROv2 spend is NOT captured here.
            # final_spent_usd remains whatever GEPA accumulated before raising.
            # Document the gap rather than reporting 0.0 silently.
        except Exception as mipro_err:
            console.print(f"[red]MIPROv2 fallback also failed: {mipro_err}[/red]")
            raise

    # Mid-loop abort path: stop_callbacks fired, compile returned partial state.
    if tracker.exceeded():
        abort_dir = _write_aborted_dir(
            tracker=tracker,
            optimizer=optimizer,
            optimized_module=optimized_module,
            baseline_module=baseline_module,
            original_tools=original_tools,
            reflection_model_name=reflection_model_name,
        )
        console.print(
            f"[red]Cost budget exceeded mid-run (stop_callback)[/red] — wrote {abort_dir}/"
        )
        return 2

    elapsed = time.time() - start_time
    console.print(f"\n  Optimization completed in {elapsed:.1f}s")

    # ── 10. Extract evolved tool descriptions ──────────────────────────
    evolved_tools = optimized_module.get_evolved_descriptions()

    # Skeleton metrics — populated as the pipeline progresses; written at end.
    metrics: dict[str, Any] = {
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "started_at": started_at_iso,
        "iterations": iterations,
        "eval_model": config.eval_model,
        "optimizer_used": optimizer_used,
        "reflection_model": reflection_model_name,
        "cost_usd_spent": float(round(final_spent_usd, 6)),
        "cost_usd_cap": float(config.max_cost_usd),
        "tool_count": len(evolved_tools),
        "param_predictors_discovered": num_predictors,
        "train_examples": len(trainset),
        "val_examples": len(valset),
        "holdout_examples": len(holdout),
        "elapsed_seconds": round(elapsed, 3),
        # WR-03: persist the actually-applied filter (tool names that
        # survived _filter_tools — empties stripped, unknowns dropped, in
        # the order discovered) rather than re-parsing the raw CLI string.
        # The original re-parse `tools_filter.split(",")` produced
        # entries like ["memory", "", "terminal"] that disagreed with the
        # filter actually applied, breaking downstream metrics.json
        # consumers (e.g. Phase 16 dashboard).
        "tools_filter": (
            [t.name for t in all_tools] if tools_filter else None
        ),
        "constraint_failures": 0,
        "param_consistency_failures": 0,
    }

    # ── 11. Constraint chain ───────────────────────────────────────────
    console.print("\n[bold]Validating evolved descriptions[/bold]")
    validator = ConstraintValidator(config)

    constraint_failures: list[dict] = []

    # 11a. SC3 param-size gate (B3) + non-empty per param.
    for evolved_tool in evolved_tools:
        for param in evolved_tool.params:
            ptext = param.description or ""
            size_result = validator._check_size(ptext, "param_description")
            if not size_result.passed:
                constraint_failures.append(
                    {
                        "tool": evolved_tool.name,
                        "param": param.name,
                        "constraint": "size_limit",
                        "message": size_result.message,
                    }
                )
            non_empty_result = validator._check_non_empty(ptext)
            # Non-empty is informational unless baseline had non-empty too (D-03).
            # We skip auto-failing on empty params to honor D-03 (empty → GEPA from-zero).
            _ = non_empty_result

    # 11b. Factual checker (defense in depth — top-level frozen, but cheap).
    factual_checker = ToolFactualChecker(config)
    # BL-02 fix: ToolFactualChecker.check_all() skips evolved tools whose
    # name has no match in original_tools (see tool_constraints.py:135-138),
    # so we cannot positionally zip(evolved_tools, factual_results). Instead
    # mirror that filter here so we can attach the correct tool name to each
    # failure. ConstraintResult.constraint_name is the constraint TYPE
    # ('factual_accuracy'), never the tool name — using it as `tool` (as the
    # original code did) labelled every failure as 'factual_accuracy', losing
    # all per-tool triage information.
    original_name_set = {t.name for t in original_tools}
    matched_evolved_for_factual = [
        ev for ev in evolved_tools if ev.name in original_name_set
    ]
    factual_results = factual_checker.check_all(original_tools, evolved_tools)
    for evolved, r in zip(matched_evolved_for_factual, factual_results):
        if not r.passed:
            constraint_failures.append(
                {
                    "tool": evolved.name,
                    "param": None,
                    "constraint": "factual_accuracy",
                    "message": r.message,
                }
            )

    # 11c. ParamConsistencyChecker — per-tool batch.
    consistency_checker = ParamConsistencyChecker(config)
    consistency_results = consistency_checker.check_all(
        evolved_tools=evolved_tools,
        frozen_tool_descs=baseline_module._frozen_tool_desc,
    )
    # BL-02 fix: ParamConsistencyChecker.check_all() iterates evolved_tools
    # in order with no skip (tool_constraints.py:300-307), so positional zip
    # is safe here. Previous code wrote `tool: None` for every consistency
    # failure even though the tool name was available — losing triage info.
    metrics["param_consistency_failures"] = sum(
        1 for r in consistency_results if not r.passed
    )
    for evolved, r in zip(evolved_tools, consistency_results):
        if r.passed:
            continue
        constraint_failures.append(
            {
                "tool": evolved.name,
                "param": None,
                "constraint": "param_consistency",
                "message": r.message,
                "details": r.details,
            }
        )

    metrics["constraint_failures"] = len(constraint_failures)
    if constraint_failures:
        metrics["constraint_failure_details"] = constraint_failures
        out_dir = _write_failed_dir(
            "CONSTRAINTS_FAILED", metrics, original_tools, evolved_tools
        )
        console.print(
            f"[red]Constraint validation FAILED[/red] — wrote {out_dir}/"
        )
        return 1

    # ── 12. Holdout evaluation (D-18 dual pairs) ───────────────────────
    console.print(f"\n[bold]Evaluating on holdout[/bold] ({len(holdout)} examples)")
    baseline_score, baseline_tool_pairs, baseline_param_pairs = _evaluate_holdout(
        baseline_module, holdout, lm
    )
    evolved_score, evolved_tool_pairs, evolved_param_pairs = _evaluate_holdout(
        optimized_module, holdout, lm
    )
    improvement = evolved_score - baseline_score
    metrics["baseline_score"] = float(round(baseline_score, 6))
    metrics["evolved_score"] = float(round(evolved_score, 6))
    metrics["improvement"] = float(round(improvement, 6))
    # D-18 debug dump — small sample (capped at 50) to bound metrics.json size.
    metrics["holdout_param_pairs"] = evolved_param_pairs[:50]

    # ── 13. CrossToolRegressionChecker + persist_per_tool_rates ────────
    regression_checker = CrossToolRegressionChecker()
    baseline_rates = regression_checker.compute_per_tool_rates(baseline_tool_pairs)
    evolved_rates = regression_checker.compute_per_tool_rates(evolved_tool_pairs)
    regression_result = regression_checker.check_regression(baseline_rates, evolved_rates)
    metrics = persist_per_tool_rates(metrics, baseline_rates, evolved_rates)

    if not regression_result.passed:
        metrics["status"] = "REGRESSION_FAILED"
        metrics["regressed_tools"] = list(regression_result.regressed_tools)
        out_dir = _write_failed_dir(
            "REGRESSION_FAILED", metrics, original_tools, evolved_tools
        )
        console.print(
            f"[red]Cross-tool regression detected[/red] — wrote {out_dir}/"
        )
        return 1

    # ── 14. V1 baseline hard-gate ──────────────────────────────────────
    gate = V1BaselineGate(tolerance=0.02)
    baseline_info = gate.resolve(
        baseline_run=baseline_run,
        baseline_module=baseline_module,
        holdout=holdout,
        lm=lm,
    )
    gate_result = gate.check(evolved_score=evolved_score, baseline=baseline_info)
    metrics["v1_baseline_holdout"] = float(baseline_info["v1_baseline_holdout"])
    metrics["v1_baseline_source"] = str(baseline_info["v1_baseline_source"])
    metrics["v1_gate_delta"] = float(gate_result["delta"])
    metrics["v1_gate_tolerance_pp"] = float(gate_result["tolerance_pp"])
    metrics["v1_gate_passed"] = bool(gate_result["passed"])

    if not gate_result["passed"]:
        metrics["status"] = "V1_BASELINE_FAILED"
        out_dir = _write_failed_dir(
            "V1_BASELINE_FAILED", metrics, original_tools, evolved_tools
        )
        console.print(
            f"[red]V1 baseline regression rejected[/red] — wrote {out_dir}/"
        )
        return 1

    # ── 15. Success — write evolved + metrics + diff ───────────────────
    metrics["status"] = "SUCCESS"
    metrics["constraints_passed"] = True
    # BL-01: do NOT call tracker.poll() here — the context has long since
    # exited and tracker._tracker is None, so poll() would return 0.0 from
    # _injected_usage (empty in production). Reuse the in-block snapshot.
    metrics["cost_usd_spent"] = float(round(final_spent_usd, 6))

    # Result table (Rich) for human review.
    result_table = Table(title="Phase 13 Evolution Results")
    result_table.add_column("Metric", style="bold")
    result_table.add_column("Baseline", justify="right")
    result_table.add_column("Evolved", justify="right")
    result_table.add_column("Change", justify="right")
    change_color = "green" if improvement > 0 else "yellow"
    result_table.add_row(
        "Holdout Score (joint tool+param)",
        f"{baseline_score:.3f}",
        f"{evolved_score:.3f}",
        f"[{change_color}]{improvement:+.3f}[/{change_color}]",
    )
    result_table.add_row("Tools in scope", "", str(len(evolved_tools)), "")
    result_table.add_row("Param predictors", "", str(num_predictors), "")
    result_table.add_row("Cost spent (USD)", "", f"${metrics['cost_usd_spent']:.4f}", "")
    result_table.add_row("v1 baseline source", "", str(metrics["v1_baseline_source"]), "")
    result_table.add_row("Time", "", f"{elapsed:.1f}s", "")
    result_table.add_row("Optimizer", "", optimizer_used, "")
    console.print()
    console.print(result_table)

    ts = metrics["timestamp"]
    out_dir = Path("output") / "tools" / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    evolved_payload = [
        {
            "name": t.name,
            "description": t.description,  # frozen — for cross-check
            "params": [
                {
                    "name": p.name,
                    "type": p.type,
                    "required": p.required,
                    "description": p.description,
                }
                for p in t.params
            ],
        }
        for t in evolved_tools
    ]
    (out_dir / "evolved_descriptions.json").write_text(
        json.dumps(evolved_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "diff.txt").write_text(
        _generate_param_diff(original_tools, evolved_tools),
        encoding="utf-8",
    )

    console.print(f"\n  Output saved to {out_dir}/")
    if improvement > 0:
        console.print(
            f"\n[bold green]Per-param evolution improved holdout score by "
            f"{improvement:+.3f}[/bold green]"
        )
    else:
        console.print(
            f"\n[yellow]Per-param evolution did not improve holdout "
            f"(change: {improvement:+.3f})[/yellow]"
        )
    return 0


if __name__ == "__main__":
    main()
