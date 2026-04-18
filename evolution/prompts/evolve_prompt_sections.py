"""Evolve hermes-agent prompt sections using DSPy + GEPA.

Usage:
    python -m evolution.prompts.evolve_prompt_sections --dry-run --hermes-repo /path/to/repo
    python -m evolution.prompts.evolve_prompt_sections --section memory_guidance --iterations 10
    python -m evolution.prompts.evolve_prompt_sections --eval-source load
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
from evolution.prompts.prompt_loader import extract_prompt_sections, PromptSection
from evolution.prompts.prompt_module import PromptModule
from evolution.prompts.prompt_dataset import (
    PromptDatasetBuilder,
    PromptBehavioralDataset,
)
from evolution.prompts.prompt_metric import PromptBehavioralMetric
from evolution.prompts.prompt_constraints import PromptRoleChecker

console = Console()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _generate_diff(
    original_sections: list[PromptSection],
    evolved_sections: list[PromptSection],
) -> str:
    """Generate unified diff between original and evolved prompt sections.

    Args:
        original_sections: List of original PromptSection objects.
        evolved_sections: List of evolved PromptSection objects.

    Returns:
        Concatenated unified diff string for all changed sections.
    """
    original_map = {s.section_id: s for s in original_sections}
    diff_parts = []

    for evolved in evolved_sections:
        original = original_map.get(evolved.section_id)
        if original is None:
            continue
        orig_lines = original.text.splitlines(keepends=True)
        evol_lines = evolved.text.splitlines(keepends=True)
        diff = difflib.unified_diff(
            orig_lines,
            evol_lines,
            fromfile=f"{evolved.section_id} (original)",
            tofile=f"{evolved.section_id} (evolved)",
        )
        diff_text = "".join(diff)
        if diff_text:
            diff_parts.append(diff_text)

    return "\n".join(diff_parts)


# ── Main Pipeline ────────────────────────────────────────────────────────────


def evolve(
    section: Optional[str] = None,
    iterations: int = 10,
    eval_source: str = "synthetic",
    hermes_repo: Optional[str] = None,
    dry_run: bool = False,
):
    """Main evolution function -- orchestrates the full prompt section optimization loop.

    Args:
        section: Optional section_id to optimize (default: all sections).
        iterations: Number of GEPA optimization iterations per section.
        eval_source: Dataset source ('synthetic' or 'load').
        hermes_repo: Optional path to hermes-agent repo.
        dry_run: If True, validate setup without running optimization.
    """

    # ── 1. Configuration ─────────────────────────────────────────────────
    config = EvolutionConfig(iterations=iterations)
    if hermes_repo:
        config.hermes_agent_path = Path(hermes_repo)

    console.print(
        f"\n[bold cyan]Hermes Agent Self-Evolution[/bold cyan]"
        f" -- Prompt Section Optimization\n"
    )

    # ── 2. Extract sections ──────────────────────────────────────────────
    console.print("[bold]Extracting prompt sections...[/bold]")
    prompt_builder_path = (
        config.hermes_agent_path / "agent" / "prompt_builder.py"
    )
    original_sections = extract_prompt_sections(prompt_builder_path)

    if not original_sections:
        console.print("[red]No prompt sections found in prompt_builder.py.[/red]")
        sys.exit(1)

    # Display discovered sections
    table = Table(title="Discovered Prompt Sections")
    table.add_column("Section ID", style="bold")
    table.add_column("Char Count", justify="right")
    for s in original_sections:
        table.add_row(s.section_id, str(s.char_count))
    console.print(table)

    # ── 3. Dry-run gate ──────────────────────────────────────────────────
    if dry_run:
        console.print(
            "[bold green]DRY RUN -- setup validated successfully.[/bold green]"
        )
        console.print(f"  Found {len(original_sections)} prompt section(s)")
        console.print(f"  Dataset source: {eval_source}")
        if eval_source == "load":
            dataset_path = Path("datasets") / "prompts"
            console.print(
                f"  Dataset path: {dataset_path} (exists: {dataset_path.exists()})"
            )
        console.print(
            f"  Would run GEPA optimization ({iterations} iterations per section)"
        )
        if section:
            console.print(f"  Target section: {section}")
        else:
            console.print(f"  Target: all {len(original_sections)} sections")
        return

    # ── 4. Build PromptModule ────────────────────────────────────────────
    module = PromptModule(original_sections)

    # Validate --section if specified
    if section and section not in module._section_ids:
        console.print(
            f"[red]Unknown section: {section}. "
            f"Available: {module._section_ids}[/red]"
        )
        sys.exit(1)

    # ── 5. Generate/load dataset ─────────────────────────────────────────
    console.print(
        f"\n[bold]Building evaluation dataset[/bold] (source: {eval_source})"
    )

    if eval_source == "synthetic":
        builder = PromptDatasetBuilder(config)
        dataset = builder.generate(original_sections)
        save_path = Path("datasets") / "prompts"
        dataset.save(save_path)
        console.print(
            f"  Generated {len(dataset.all_examples)} synthetic examples"
        )
        console.print(f"  Saved to {save_path}/")
    elif eval_source == "load":
        dataset_path = Path("datasets") / "prompts"
        if not dataset_path.exists():
            console.print(
                f"[red]Dataset path does not exist: {dataset_path}[/red]"
            )
            sys.exit(1)
        dataset = PromptBehavioralDataset.load(dataset_path)
        console.print(f"  Loaded {len(dataset.all_examples)} examples")
    else:
        console.print(f"[red]Unknown eval-source: {eval_source}[/red]")
        sys.exit(1)

    console.print(
        f"  Split: {len(dataset.train)} train / {len(dataset.val)} val"
        f" / {len(dataset.holdout)} holdout"
    )

    # ── 6. Per-section GEPA optimization ─────────────────────────────────
    sections_to_optimize = [section] if section else module._section_ids

    metric = PromptBehavioralMetric(config)
    section_texts = {s.section_id: s.text for s in original_sections}

    console.print(f"\n[bold]Configuring optimizer[/bold]")
    console.print(f"  Optimizer: GEPA ({iterations} iterations per section)")
    console.print(f"  Eval model: {config.eval_model}")
    console.print(
        f"  Sections to optimize: {len(sections_to_optimize)}"
    )

    lm = dspy.LM(config.eval_model)
    dspy.configure(lm=lm)

    start_time = time.time()

    for active_sid in sections_to_optimize:
        console.print(
            f"\n[bold cyan]Optimizing section: {active_sid}[/bold cyan]"
        )
        module.set_active_section(active_sid)

        # Filter dataset for this section
        section_train = [
            ex for ex in dataset.train if ex.section_id == active_sid
        ]
        section_val = [
            ex for ex in dataset.val if ex.section_id == active_sid
        ]

        # Build DSPy examples from filtered data
        temp_dataset = PromptBehavioralDataset(
            train=section_train,
            val=section_val,
            holdout=[],
        )
        trainset = temp_dataset.to_dspy_examples(
            "train", section_texts=section_texts
        )
        valset = temp_dataset.to_dspy_examples(
            "val", section_texts=section_texts
        )

        if not trainset:
            console.print(
                f"  [yellow]Warning: No training data for {active_sid}, "
                f"skipping[/yellow]"
            )
            continue

        console.print(
            f"  Training examples: {len(trainset)}, "
            f"Validation examples: {len(valset)}"
        )

        try:
            optimizer = dspy.GEPA(
                metric=metric,
                max_steps=iterations,
            )
            module = optimizer.compile(
                module,
                trainset=trainset,
                valset=valset,
            )
        except Exception as e:
            # Fall back to MIPROv2 if GEPA isn't available
            console.print(
                f"  [yellow]GEPA not available ({e}), "
                f"falling back to MIPROv2[/yellow]"
            )
            try:
                optimizer = dspy.MIPROv2(
                    metric=metric,
                    auto="light",
                )
                module = optimizer.compile(
                    module,
                    trainset=trainset,
                )
            except Exception as e2:
                console.print(
                    f"  [red]MIPROv2 also failed ({e2}), "
                    f"skipping section {active_sid}[/red]"
                )

    elapsed = time.time() - start_time
    console.print(f"\n  Optimization completed in {elapsed:.1f}s")

    # ── 7. Extract evolved sections ──────────────────────────────────────
    evolved_sections = module.get_evolved_sections()

    # ── 8. Constraint validation (GEPA -> constraints -> holdout) ────────
    console.print(f"\n[bold]Validating evolved sections[/bold]")

    original_map = {s.section_id: s for s in original_sections}
    all_constraint_results = []
    all_pass = True

    # 8a. Growth + non_empty checks per section
    validator = ConstraintValidator(config)
    for evolved in evolved_sections:
        original = original_map.get(evolved.section_id)

        # Growth check
        if original:
            result = validator._check_growth(
                evolved.text, original.text, "prompt_section"
            )
            all_constraint_results.append(result)
            if not result.passed:
                all_pass = False

        # Non-empty check
        result = validator._check_non_empty(evolved.text)
        all_constraint_results.append(result)
        if not result.passed:
            all_pass = False

    # 8b. Role preservation check
    console.print("  Running role preservation check...")
    role_checker = PromptRoleChecker(config)
    role_results = role_checker.check_all(original_sections, evolved_sections)
    all_constraint_results.extend(role_results)
    for r in role_results:
        if not r.passed:
            all_pass = False

    # 8c. Print all constraint results
    for c in all_constraint_results:
        icon = "+" if c.passed else "x"
        color = "green" if c.passed else "red"
        console.print(
            f"  [{color}]{icon} {c.constraint_name}[/{color}]: {c.message}"
        )

    if not all_pass:
        # Save failed results for inspection
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("output") / "prompts" / f"FAILED_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "metrics.json").write_text(
            json.dumps(
                {
                    "timestamp": timestamp,
                    "status": "FAILED",
                    "constraints_passed": False,
                },
                indent=2,
            )
        )
        console.print(
            "[red]Constraint validation FAILED -- not deploying[/red]"
        )
        console.print(f"  Saved failed results to {output_dir}/")
        return

    # ── 9. Holdout evaluation (baseline vs evolved) ──────────────────────
    console.print(
        f"\n[bold]Evaluating on holdout set "
        f"({len(dataset.holdout)} examples)[/bold]"
    )

    baseline_module = PromptModule(original_sections)
    holdout_examples = dataset.to_dspy_examples(
        "holdout", section_texts=section_texts
    )

    baseline_scores = []
    evolved_scores = []

    for ex in holdout_examples:
        with dspy.context(lm=lm):
            # Score baseline
            # Need to set active section for baseline to work
            for sid in baseline_module._section_ids:
                baseline_module.set_active_section(sid)
                break
            bp = baseline_module(task_input=ex.task_input)
            b_score = metric(ex, bp, trace=None)
            baseline_scores.append(b_score)

            # Score evolved
            ep = module(task_input=ex.task_input)
            e_score = metric(ex, ep, trace=None)
            evolved_scores.append(e_score)

    n_holdout = max(1, len(holdout_examples))
    baseline_score = sum(baseline_scores) / n_holdout if baseline_scores else 0.0
    evolved_score = sum(evolved_scores) / n_holdout if evolved_scores else 0.0
    improvement = evolved_score - baseline_score

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
    result_table.add_row(
        "Section Count", "", str(len(evolved_sections)), ""
    )
    result_table.add_row("Time", "", f"{elapsed:.1f}s", "")
    result_table.add_row("Iterations", "", str(iterations), "")

    console.print()
    console.print(result_table)

    # ── 11. Save results ─────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = Path("output") / "prompts" / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save evolved sections as JSON
    evolved_data = [
        {"section_id": s.section_id, "text": s.text}
        for s in evolved_sections
    ]
    (output_dir / "evolved_sections.json").write_text(
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
        "section_count": len(evolved_sections),
        "train_examples": len(dataset.train),
        "val_examples": len(dataset.val),
        "holdout_examples": len(dataset.holdout),
        "elapsed_seconds": elapsed,
        "constraints_passed": True,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2)
    )

    # Save diff
    diff_text = _generate_diff(original_sections, evolved_sections)
    (output_dir / "diff.txt").write_text(diff_text)

    console.print(f"\n  Output saved to {output_dir}/")

    if improvement > 0:
        console.print(
            f"\n[bold green]Evolution improved prompt sections"
            f" by {improvement:+.3f}"
            f" ({improvement / max(0.001, baseline_score) * 100:+.1f}%)"
            f"[/bold green]"
        )
    else:
        console.print(
            f"\n[yellow]Evolution did not improve prompt sections"
            f" (change: {improvement:+.3f})[/yellow]"
        )
        console.print(
            "  Try: more iterations, better eval dataset, "
            "or different optimizer model"
        )


# ── Click CLI ────────────────────────────────────────────────────────────────


@click.command()
@click.option(
    "--section",
    default=None,
    help="Section ID to optimize (default: all sections)",
)
@click.option(
    "--iterations",
    default=10,
    help="Number of GEPA iterations per section",
)
@click.option(
    "--eval-source",
    default="synthetic",
    type=click.Choice(["synthetic", "load"]),
    help="Source for evaluation dataset",
)
@click.option(
    "--hermes-repo",
    default=None,
    help="Path to hermes-agent repo",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate setup without running optimization",
)
def main(section, iterations, eval_source, hermes_repo, dry_run):
    """Evolve hermes-agent prompt sections using DSPy + GEPA optimization."""
    evolve(
        section=section,
        iterations=iterations,
        eval_source=eval_source,
        hermes_repo=hermes_repo,
        dry_run=dry_run,
    )


if __name__ == "__main__":
    main()
