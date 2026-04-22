"""Evolve hermes-agent tool descriptions using DSPy + GEPA.

Usage:
    python -m evolution.tools.evolve_tool_descriptions --iterations 10
    python -m evolution.tools.evolve_tool_descriptions --eval-source load --hermes-repo /path/to/repo
    python -m evolution.tools.evolve_tool_descriptions --dry-run
"""

import json
import sys
import time
import difflib
from pathlib import Path
from datetime import datetime
from typing import Optional

import click
import dspy
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from evolution.core.config import EvolutionConfig, get_hermes_agent_path
from evolution.core.constraints import ConstraintValidator
from evolution.tools.tool_loader import discover_tool_files, extract_tool_descriptions, ToolDescription
from evolution.tools.tool_module import ToolModule
from evolution.tools.tool_dataset import ToolDatasetBuilder, ToolSelectionDataset
from evolution.tools.tool_metric import tool_selection_metric, CrossToolRegressionChecker
from evolution.tools.tool_constraints import ToolFactualChecker

console = Console()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _generate_diff(original_tools: list[ToolDescription], evolved_tools: list[ToolDescription]) -> str:
    """Generate unified diff between original and evolved tool descriptions.

    Args:
        original_tools: List of original ToolDescription objects.
        evolved_tools: List of evolved ToolDescription objects.

    Returns:
        Concatenated unified diff string for all changed tools.
    """
    original_map = {t.name: t for t in original_tools}
    diff_parts = []

    for evolved in evolved_tools:
        original = original_map.get(evolved.name)
        if original is None:
            continue
        orig_lines = original.description.splitlines(keepends=True)
        evol_lines = evolved.description.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines,
            evol_lines,
            fromfile=f"{evolved.name} (original)",
            tofile=f"{evolved.name} (evolved)",
        )
        diff_text = "".join(diff)
        if diff_text:
            diff_parts.append(diff_text)

    return "\n".join(diff_parts)


# ── Main Pipeline ────────────────────────────────────────────────────────────


def evolve(
    iterations: int = 10,
    eval_source: str = "synthetic",
    hermes_repo: Optional[str] = None,
    dry_run: bool = False,
    model: Optional[str] = None,
    api_base: Optional[str] = None,
):
    """Main evolution function -- orchestrates the full tool description optimization loop.

    Args:
        iterations: Number of GEPA optimization iterations.
        eval_source: Dataset source ('synthetic' or 'load').
        hermes_repo: Optional path to hermes-agent repo.
        dry_run: If True, validate setup without running optimization.
        model: Override model for all LLM calls.
        api_base: Override API base URL.
    """

    # ── 1. Configuration ─────────────────────────────────────────────────
    config = EvolutionConfig.load(
        iterations=iterations,
        hermes_repo=hermes_repo,
        model=model,
        api_base=api_base,
    )

    console.print(
        f"\n[bold cyan]Hermes Agent Self-Evolution[/bold cyan]"
        f" -- Tool Description Optimization\n"
    )

    # ── 2. Discover tool files + extract descriptions ────────────────────
    console.print("[bold]Discovering tool files...[/bold]")
    tool_files = discover_tool_files(config.hermes_agent_path)
    if not tool_files:
        console.print("[red]No tool files found in hermes-agent repo.[/red]")
        sys.exit(1)

    all_tools: list[ToolDescription] = []
    for f in tool_files:
        all_tools.extend(extract_tool_descriptions(f))

    if not all_tools:
        console.print("[red]No tool descriptions extracted from discovered files.[/red]")
        sys.exit(1)

    # Display discovered tools
    table = Table(title="Discovered Tools")
    table.add_column("Tool Name", style="bold")
    table.add_column("Description Length", justify="right")
    table.add_column("Parameters", justify="right")
    for tool in all_tools:
        table.add_row(tool.name, str(len(tool.description)), str(len(tool.params)))
    console.print(table)

    # ── 3. Dry-run mode ──────────────────────────────────────────────────
    if dry_run:
        console.print("[bold green]DRY RUN -- setup validated successfully.[/bold green]")
        console.print(f"  Would optimize {len(all_tools)} tool description(s)")
        console.print(f"  Dataset source: {eval_source}")
        if eval_source == "load":
            dataset_path = Path("datasets") / "tools"
            console.print(f"  Dataset path: {dataset_path} (exists: {dataset_path.exists()})")
        console.print(f"  Would run GEPA optimization ({iterations} iterations)")
        return

    # ── 4. Build ToolModule (save baseline reference) ────────────────────
    original_tools = list(all_tools)  # Copy for later diff/constraint comparison
    baseline_module = ToolModule(all_tools)

    # ── 5. Generate/load dataset ─────────────────────────────────────────
    console.print(f"\n[bold]Building evaluation dataset[/bold] (source: {eval_source})")

    if eval_source == "synthetic":
        builder = ToolDatasetBuilder(config)
        dataset = builder.generate(all_tools)
        save_path = Path("datasets") / "tools"
        dataset.save(save_path)
        console.print(f"  Generated {len(dataset.all_examples)} synthetic examples")
        console.print(f"  Saved to {save_path}/")
    elif eval_source == "load":
        dataset_path = Path("datasets") / "tools"
        if not dataset_path.exists():
            console.print(f"[red]Dataset path does not exist: {dataset_path}[/red]")
            sys.exit(1)
        dataset = ToolSelectionDataset.load(dataset_path)
        console.print(f"  Loaded {len(dataset.all_examples)} examples")
    else:
        console.print(f"[red]Unknown eval-source: {eval_source}[/red]")
        sys.exit(1)

    console.print(
        f"  Split: {len(dataset.train)} train / {len(dataset.val)} val"
        f" / {len(dataset.holdout)} holdout"
    )

    # ── 6. GEPA optimization ─────────────────────────────────────────────
    console.print(f"\n[bold]Configuring optimizer[/bold]")
    console.print(f"  Optimizer: GEPA ({iterations} iterations)")
    console.print(f"  Eval model: {config.eval_model}")

    lm = dspy.LM(config.eval_model, **config.get_lm_kwargs())
    dspy.configure(lm=lm)

    trainset = dataset.to_dspy_examples("train")
    valset = dataset.to_dspy_examples("val")

    console.print(f"\n[bold cyan]Running GEPA optimization ({iterations} iterations)...[/bold cyan]\n")

    start_time = time.time()

    try:
        optimizer = dspy.GEPA(
            metric=tool_selection_metric,
            max_steps=iterations,
        )
        optimized_module = optimizer.compile(
            baseline_module,
            trainset=trainset,
            valset=valset,
        )
    except Exception as e:
        # Fall back to MIPROv2 if GEPA isn't available
        console.print(f"[yellow]GEPA not available ({e}), falling back to MIPROv2[/yellow]")
        optimizer = dspy.MIPROv2(
            metric=tool_selection_metric,
            auto="light",
        )
        optimized_module = optimizer.compile(
            baseline_module,
            trainset=trainset,
        )

    elapsed = time.time() - start_time
    console.print(f"\n  Optimization completed in {elapsed:.1f}s")

    # ── 7. Extract evolved descriptions ──────────────────────────────────
    evolved_tools = optimized_module.get_evolved_descriptions()

    # ── 8. Constraint validation (GEPA -> constraints -> holdout) ────────
    console.print(f"\n[bold]Validating evolved descriptions[/bold]")

    original_map = {t.name: t for t in original_tools}
    all_constraint_results = []
    all_pass = True

    # 8a. Size + growth + non_empty checks per tool/param
    validator = ConstraintValidator(config)
    for evolved_tool in evolved_tools:
        # Size check on tool description
        result = validator._check_size(evolved_tool.description, "tool_description")
        all_constraint_results.append(result)
        if not result.passed:
            all_pass = False

        # Non-empty check
        result = validator._check_non_empty(evolved_tool.description)
        all_constraint_results.append(result)
        if not result.passed:
            all_pass = False

        # Growth check against original
        original_tool = original_map.get(evolved_tool.name)
        if original_tool:
            result = validator._check_growth(
                evolved_tool.description,
                original_tool.description,
                "tool_description",
            )
            all_constraint_results.append(result)
            if not result.passed:
                all_pass = False

        # Size check on each parameter description
        for param in evolved_tool.params:
            result = validator._check_size(param.description, "param_description")
            all_constraint_results.append(result)
            if not result.passed:
                all_pass = False

    # 8b. Factual accuracy check
    console.print("  Running factual accuracy check...")
    factual_checker = ToolFactualChecker(config)
    factual_results = factual_checker.check_all(original_tools, evolved_tools)
    all_constraint_results.extend(factual_results)
    for r in factual_results:
        if not r.passed:
            all_pass = False

    # 8c. Print all constraint results
    for c in all_constraint_results:
        icon = "+" if c.passed else "x"
        color = "green" if c.passed else "red"
        console.print(f"  [{color}]{icon} {c.constraint_name}[/{color}]: {c.message}")

    if not all_pass:
        # Save failed results for inspection
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("output") / "tools" / f"FAILED_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "metrics.json").write_text(json.dumps({
            "timestamp": timestamp,
            "status": "FAILED",
            "constraints_passed": False,
        }, indent=2))
        console.print(f"[red]Constraint validation FAILED -- not deploying[/red]")
        console.print(f"  Saved failed results to {output_dir}/")
        return

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

    # Compute overall accuracy
    baseline_correct = sum(1 for c, s in baseline_preds if c.strip().lower() == s.strip().lower())
    evolved_correct = sum(1 for c, s in evolved_preds if c.strip().lower() == s.strip().lower())
    n_holdout = max(1, len(holdout_examples))
    baseline_score = baseline_correct / n_holdout
    evolved_score = evolved_correct / n_holdout
    improvement = evolved_score - baseline_score

    # 8d. Cross-tool regression check (needs holdout predictions)
    console.print("\n  Running cross-tool regression check...")
    regression_checker = CrossToolRegressionChecker()
    baseline_rates = regression_checker.compute_per_tool_rates(baseline_preds)
    evolved_rates = regression_checker.compute_per_tool_rates(evolved_preds)
    regression_result = regression_checker.check_regression(baseline_rates, evolved_rates)

    if not regression_result.passed:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("output") / "tools" / f"FAILED_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "metrics.json").write_text(json.dumps({
            "timestamp": timestamp,
            "status": "REGRESSION_FAILED",
            "baseline_score": baseline_score,
            "evolved_score": evolved_score,
            "regressed_tools": regression_result.regressed_tools,
        }, indent=2))
        console.print("[red]Cross-tool regression detected -- not deploying[/red]")
        console.print(f"  Saved results to {output_dir}/")
        return

    # ── 10. Report results ───────────────────────────────────────────────
    result_table = Table(title="Evolution Results")
    result_table.add_column("Metric", style="bold")
    result_table.add_column("Baseline", justify="right")
    result_table.add_column("Evolved", justify="right")
    result_table.add_column("Change", justify="right")

    change_color = "green" if improvement > 0 else "red"
    result_table.add_row(
        "Holdout Score",
        f"{baseline_score:.3f}",
        f"{evolved_score:.3f}",
        f"[{change_color}]{improvement:+.3f}[/{change_color}]",
    )
    result_table.add_row("Tool Count", "", str(len(evolved_tools)), "")
    result_table.add_row("Time", "", f"{elapsed:.1f}s", "")
    result_table.add_row("Iterations", "", str(iterations), "")

    console.print()
    console.print(result_table)

    # ── 11. Save results ─────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("output") / "tools" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save evolved descriptions as JSON
    evolved_data = [
        {"name": t.name, "description": t.description}
        for t in evolved_tools
    ]
    (output_dir / "evolved_descriptions.json").write_text(
        json.dumps(evolved_data, indent=2)
    )

    # Save metrics
    metrics = {
        "timestamp": timestamp,
        "iterations": iterations,
        "eval_model": config.eval_model,
        "baseline_score": baseline_score,
        "evolved_score": evolved_score,
        "improvement": improvement,
        "tool_count": len(evolved_tools),
        "train_examples": len(dataset.train),
        "val_examples": len(dataset.val),
        "holdout_examples": len(dataset.holdout),
        "elapsed_seconds": elapsed,
        "constraints_passed": True,
    }
    (output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))

    # Save diff
    diff_text = _generate_diff(original_tools, evolved_tools)
    (output_dir / "diff.txt").write_text(diff_text)

    console.print(f"\n  Output saved to {output_dir}/")

    if improvement > 0:
        console.print(
            f"\n[bold green]Evolution improved tool descriptions"
            f" by {improvement:+.3f} ({improvement / max(0.001, baseline_score) * 100:+.1f}%)[/bold green]"
        )
    else:
        console.print(f"\n[yellow]Evolution did not improve tool descriptions (change: {improvement:+.3f})[/yellow]")
        console.print("  Try: more iterations, better eval dataset, or different optimizer model")


# ── Click CLI ────────────────────────────────────────────────────────────────


@click.command()
@click.option("--iterations", default=10, help="Number of GEPA iterations")
@click.option("--eval-source", default="synthetic", type=click.Choice(["synthetic", "load"]),
              help="Source for evaluation dataset")
@click.option("--hermes-repo", default=None, help="Path to hermes-agent repo")
@click.option("--dry-run", is_flag=True, help="Validate setup without running optimization")
@click.option("--model", default=None, help="Override model for all LLM calls (e.g. openai/qwen-plus)")
@click.option("--api-base", default=None, help="Override API base URL (e.g. https://dashscope.aliyuncs.com/compatible-mode/v1)")
def main(iterations, eval_source, hermes_repo, dry_run, model, api_base):
    """Evolve hermes-agent tool descriptions using DSPy + GEPA optimization."""
    evolve(
        iterations=iterations,
        eval_source=eval_source,
        hermes_repo=hermes_repo,
        dry_run=dry_run,
        model=model,
        api_base=api_base,
    )


if __name__ == "__main__":
    main()
