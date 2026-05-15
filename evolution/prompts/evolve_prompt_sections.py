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


# ── Module constants ────────────────────────────────────────────────────────

# Unit convention for `_pp`-suffixed values in this module:
#   1.0 == 1 percentage point (pp) == 0.01 score units.
# All metrics fields with the `_pp` suffix (`epsilon_pp`,
# `joint_vs_roundrobin_delta_pp`) are stored as percentage points, so
# downstream consumers can compare them directly without 100x rescaling.
# Internal score-space comparisons must divide pp values by 100.
#
# Phase 17 / D-AB-03: Soft-gate threshold — joint mode warns (no exit) when
# joint_score regresses by more than EPSILON_PP percentage points vs the
# round-robin baseline. CR-02 fix: value is now 1.0 (pp), not 0.01 (score
# space), so the field name's `_pp` suffix matches its unit.
EPSILON_PP = 1.0  # percentage points


# ── Mode resolution helper (W1: single source of truth) ────────────────────

def _resolve_effective_mode(section: Optional[str], mode: str) -> str:
    """Return the effective optimization mode after applying D-RR-03 routing.

    D-RR-03 implicit routing: when a single `section` is targeted, the
    round-robin single-section path is forced regardless of `mode`. This
    helper is the ONLY place this conditional lives — both the dry-run
    gate and the main optimization path call it (W1 revision: prevents
    drift between two code locations).

    Args:
        section: Optional section_id from CLI --section flag.
        mode: Raw mode string from CLI --mode flag, already validated by
            click.Choice to be "joint" or "round-robin".

    Returns:
        "round-robin" when section is non-empty; otherwise mode unchanged.
    """
    return "round-robin" if section else mode


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
    model: Optional[str] = None,
    api_base: Optional[str] = None,
    mode: str = "joint",
):
    """Main evolution function -- orchestrates the full prompt section optimization loop.

    Args:
        section: Optional section_id to optimize (default: all sections).
        iterations: Number of GEPA optimization iterations per section.
        eval_source: Dataset source ('synthetic' or 'load').
        hermes_repo: Optional path to hermes-agent repo.
        dry_run: If True, validate setup without running optimization.
        model: Override model for all LLM calls.
        api_base: Override API base URL.
        mode: Optimization mode — 'joint' (default, Phase 17 — all sections
            optimized simultaneously via GEPA with component_selector='all')
            or 'round-robin' (legacy, section-by-section). When section is
            also specified, round-robin single-section path is forced
            regardless of mode (D-RR-03 implicit routing). Effective mode
            is computed via _resolve_effective_mode(section, mode).
    """

    # ── 0. Mode resolution (D-RR-03 via single helper, W1 revision) ──────
    effective_mode = _resolve_effective_mode(section, mode)
    # Click.Choice already validated the input mode is "joint" or
    # "round-robin"; the helper applies the --section implicit routing.

    # ── 1. Configuration ─────────────────────────────────────────────────
    config = EvolutionConfig.load(
        iterations=iterations,
        hermes_repo=hermes_repo,
        model=model,
        api_base=api_base,
    )

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

    # ── 3. Dry-run gate (D-IT-03: budget preview always printed) ─────────
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
        # W1 invariant: same helper as main path — single source of truth.
        effective_mode_dry = _resolve_effective_mode(section, mode)
        # In dry-run we don't have module yet — use section count as proxy
        # (Phase 17 selector is frozen in joint mode so num_predictors == N sections).
        num_predictors_dry = len(original_sections)
        joint_budget_dry = (
            max(iterations * 50, 3 * num_predictors_dry) * num_predictors_dry
        )
        rr_per_section_dry = iterations * 50
        rr_total_dry = rr_per_section_dry * len(original_sections)
        console.print(f"  Mode: {effective_mode_dry}")
        if effective_mode_dry == "joint":
            console.print(
                f"  Joint optimization:        "
                f"iterations={iterations}, max_metric_calls={joint_budget_dry}"
            )
            console.print(
                f"  Round-robin A/B baseline:  "
                f"iterations={iterations}/section × {len(original_sections)} sections, "
                f"max_metric_calls={rr_per_section_dry}/section"
            )
            console.print(
                f"  Total est. LM calls:       ~{joint_budget_dry} (joint) + "
                f"~{rr_total_dry} (baseline) = ~{joint_budget_dry + rr_total_dry}"
            )
        else:
            console.print(
                f"  Round-robin: iterations={iterations}/section × "
                f"{len(original_sections)} section(s), "
                f"max_metric_calls={rr_per_section_dry}/section"
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

    # ── 6. Optimization (joint vs round-robin fork) ──────────────────────
    sections_to_optimize = [section] if section else module._section_ids

    metric = PromptBehavioralMetric(config)
    section_texts = {s.section_id: s.text for s in original_sections}

    # ── 6a. Compute budget preview (D-IT-03) ─────────────────────────────
    # For budget purposes, simulate joint mode to capture num_predictors
    # without permanently mutating module state when we're going round-robin.
    if effective_mode == "joint":
        module.set_joint_mode(True)
        num_predictors = len(list(module.named_predictors()))
        joint_budget = max(iterations * 50, 3 * num_predictors) * num_predictors
    else:
        num_predictors = len(module._section_ids)
        joint_budget = 0  # not running joint
    rr_per_section_budget = iterations * 50
    rr_total_budget = rr_per_section_budget * len(module._section_ids)

    console.print(f"\n[bold]Configuring optimizer[/bold]")
    console.print(f"  Mode: {effective_mode}")
    console.print(f"  Eval model: {config.eval_model}")
    console.print(f"  Reflection model: {config.optimizer_model}")
    if effective_mode == "joint":
        console.print(
            f"  Joint optimization:        "
            f"iterations={iterations}, max_metric_calls={joint_budget}"
        )
        console.print(
            f"  Round-robin A/B baseline:  "
            f"iterations={iterations}/section × {len(module._section_ids)} sections, "
            f"max_metric_calls={rr_per_section_budget}/section"
        )
        console.print(
            f"  Total est. LM calls:       ~{joint_budget} (joint) + "
            f"~{rr_total_budget} (baseline) = ~{joint_budget + rr_total_budget}"
        )
    else:
        console.print(
            f"  Round-robin: iterations={iterations}/section × "
            f"{len(sections_to_optimize)} section(s), "
            f"max_metric_calls={rr_per_section_budget}/section"
        )

    lm = dspy.LM(config.eval_model, **config.get_lm_kwargs())
    dspy.configure(lm=lm)

    start_time = time.time()

    if effective_mode == "joint":
        # ── 6b. JOINT branch: single GEPA.compile with component_selector="all" ──
        # W2 invariant: NO try/except wrapping GEPA.compile here. Joint mode
        # follows Phase 13 D-15a "loud GEPA failure" pattern — any exception
        # propagates uncaught to Click main and exits non-zero. This is the
        # deliberate behavioral DIFFERENCE from the round-robin branch below
        # (which retains its GEPA → MIPROv2 fallback for legacy parity).
        # Future PRs MUST NOT silently introduce try/except here without a
        # CONTEXT decision revision.
        console.print(
            f"\n[bold cyan]Joint optimization across "
            f"{len(module._section_ids)} sections[/bold cyan]"
        )

        trainset = dataset.to_dspy_examples(
            "train", section_texts=section_texts
        )
        valset = dataset.to_dspy_examples(
            "val", section_texts=section_texts
        )

        if not trainset:
            console.print(
                "  [yellow]Warning: No training data, "
                "skipping joint optimization[/yellow]"
            )
        else:
            console.print(
                f"  Training examples: {len(trainset)}, "
                f"Validation examples: {len(valset)}"
            )
            reflection_lm = dspy.LM(
                config.optimizer_model, **config.get_lm_kwargs()
            )
            optimizer = dspy.GEPA(
                metric=metric,
                max_metric_calls=joint_budget,
                reflection_lm=reflection_lm,
                component_selector="all",
                track_stats=True,
                seed=0,
            )
            # NO try/except: loud-fail per W2 invariant / D-15a parity
            module = optimizer.compile(
                module,
                trainset=trainset,
                valset=valset,
            )
    else:
        # ── 6c. ROUND-ROBIN branch: per-section for-loop (legacy preserved) ──
        # NOTE: This branch INTENTIONALLY retains the GEPA → MIPROv2 fallback
        # chain (try/except below) — that is the long-standing round-robin
        # behavior. Joint branch above does NOT have this fallback (W2 invariant).
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
                reflection_lm = dspy.LM(
                    config.optimizer_model, **config.get_lm_kwargs()
                )
                optimizer = dspy.GEPA(
                    metric=metric,
                    max_metric_calls=rr_per_section_budget,
                    reflection_lm=reflection_lm,
                )
                module = optimizer.compile(
                    module,
                    trainset=trainset,
                    valset=valset,
                )
            except Exception as e:
                # Round-robin legacy: fall back to MIPROv2 if GEPA isn't available
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

    # WR-01 fix: hoist set_active_section out of the per-example loop.
    # Previously the body did `for sid in _section_ids: set_active(sid); break`
    # on EVERY holdout example, which pop/recreates the active Predict on
    # iteration 2+ (no-op semantically after the first call, but wastes work
    # and obscures intent). Pitfall 1 fix guarantees _build_frozen_context
    # already includes all section text regardless of which section is
    # "active", so a one-time activation pre-loop is sufficient. Guarded
    # by `holdout_examples` so empty-holdout test paths don't accrue an
    # extra set_active_section call.
    if holdout_examples and baseline_module._section_ids:
        baseline_module.set_active_section(baseline_module._section_ids[0])

    baseline_scores = []
    evolved_scores = []

    for ex in holdout_examples:
        with dspy.context(lm=lm):
            # Score baseline
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

    # ── 9.5. Joint mode inline A/B baseline (D-AB-01/02/03/04) ───────────
    roundrobin_baseline_score: Optional[float] = None
    ab_elapsed: float = 0.0
    ab_baseline_evolved_sections: list[PromptSection] = []
    joint_vs_roundrobin_delta_pp: Optional[float] = None

    if effective_mode == "joint":
        # D-AB-04 (W6 revision): per-section baseline budget = iterations*50,
        # 与 round-robin legacy 路径单参数公式 1:1 对齐(NO 压缩),保证 A/B 严格可比
        ab_per_section_budget = iterations * 50

        console.print(
            f"\n[bold]Inline A/B baseline: round-robin on same dataset[/bold]"
        )
        console.print(
            f"  (fresh PromptModule, {len(original_sections)} sections × "
            f"{iterations} iter, max_metric_calls={ab_per_section_budget}/section)"
        )

        ab_baseline_module = PromptModule(original_sections)  # fresh (Pitfall 4)
        ab_start = time.time()

        for ab_sid in ab_baseline_module._section_ids:
            ab_baseline_module.set_active_section(ab_sid)
            ab_section_train = [
                ex for ex in dataset.train if ex.section_id == ab_sid
            ]
            ab_section_val = [
                ex for ex in dataset.val if ex.section_id == ab_sid
            ]
            if not ab_section_train:
                console.print(
                    f"  [dim]No training data for {ab_sid}, skipping[/dim]"
                )
                continue

            ab_temp_ds = PromptBehavioralDataset(
                train=ab_section_train,
                val=ab_section_val,
                holdout=[],
            )
            ab_trainset = ab_temp_ds.to_dspy_examples(
                "train", section_texts=section_texts
            )
            ab_valset = ab_temp_ds.to_dspy_examples(
                "val", section_texts=section_texts
            )

            # CR-01 fix: mirror main round-robin branch's GEPA -> MIPROv2
            # fallback chain to preserve D-AB-04 "1:1 strict comparability".
            # If the main RR branch (line ~405-438) falls back to MIPROv2 when
            # GEPA is unavailable but the A/B baseline does NOT, then a
            # GEPA-only failure would skew the holdout comparison into
            # "joint optimization vs UNoptimized" and the soft gate would
            # mis-trigger.
            try:
                ab_reflection_lm = dspy.LM(
                    config.optimizer_model, **config.get_lm_kwargs()
                )
                ab_optimizer = dspy.GEPA(
                    metric=metric,
                    max_metric_calls=ab_per_section_budget,  # D-AB-04 full budget
                    reflection_lm=ab_reflection_lm,
                    component_selector="round_robin",
                )
                ab_baseline_module = ab_optimizer.compile(
                    ab_baseline_module,
                    trainset=ab_trainset,
                    valset=ab_valset,
                )
            except Exception as e:
                # A/B baseline parity with main RR branch: GEPA -> MIPROv2 fallback
                console.print(
                    f"  [yellow]A/B baseline GEPA not available for {ab_sid} "
                    f"({e}), falling back to MIPROv2[/yellow]"
                )
                try:
                    ab_optimizer = dspy.MIPROv2(
                        metric=metric,
                        auto="light",
                    )
                    ab_baseline_module = ab_optimizer.compile(
                        ab_baseline_module,
                        trainset=ab_trainset,
                    )
                except Exception as e2:
                    console.print(
                        f"  [red]A/B baseline MIPROv2 also failed for {ab_sid} "
                        f"({e2}), skipping this section[/red]"
                    )

        # Score A/B baseline on SAME holdout
        ab_scores: list[float] = []
        # Ensure forward() does not raise RuntimeError — set any single active
        if ab_baseline_module._section_ids:
            ab_baseline_module.set_active_section(
                ab_baseline_module._section_ids[0]
            )
        for ex in holdout_examples:
            with dspy.context(lm=lm):
                ab_pred = ab_baseline_module(task_input=ex.task_input)
                ab_scores.append(metric(ex, ab_pred, trace=None))
        roundrobin_baseline_score = (
            sum(ab_scores) / max(1, len(ab_scores)) if ab_scores else 0.0
        )
        ab_elapsed = time.time() - ab_start
        ab_baseline_evolved_sections = ab_baseline_module.get_evolved_sections()

        console.print(
            f"  A/B baseline completed in {ab_elapsed:.1f}s "
            f"(score: {roundrobin_baseline_score:.3f})"
        )

        # ── 9.6. Soft gate (D-AB-02 — warning only, no exit code) ────────
        # W3 revision: explicit two-direction deltas to disambiguate semantics
        # delta_pp: rr_baseline view (positive = rr beats joint, used in warning text)
        # joint_vs_roundrobin_delta_pp: A/B delta (positive = joint wins),
        # persisted to metrics.json as a distinct field from `improvement`
        # (which is evolved_score - baseline_score vs UNOPTIMIZED baseline).
        delta_pp = (roundrobin_baseline_score - evolved_score) * 100
        joint_vs_roundrobin_delta_pp = (evolved_score - roundrobin_baseline_score) * 100
        # CR-02 fix: EPSILON_PP is in percentage points; convert to score
        # space for direct comparison with raw scores. (Strictly less-than:
        # an exactly-epsilon regression is treated as acceptable per WR-06
        # documented semantics.)
        if evolved_score < roundrobin_baseline_score - (EPSILON_PP / 100):
            console.print(
                f"[yellow]Joint score ({evolved_score:.3f}) below "
                f"round-robin baseline ({roundrobin_baseline_score:.3f}) "
                f"by {delta_pp:.1f}pp — review before deploying[/yellow]"
            )
        else:
            console.print(
                f"[green]Joint score ({evolved_score:.3f}) ≥ "
                f"round-robin baseline ({roundrobin_baseline_score:.3f}) "
                f"within epsilon ({EPSILON_PP:.0f}pp)[/green]"
            )

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
    # NOTE (W3 revision): `improvement` = evolved_score - baseline_score
    # (vs unoptimized prompt baseline_score). This is DISTINCT from
    # `joint_vs_roundrobin_delta_pp` (added below in joint mode) which is
    # the A/B delta: joint_score - roundrobin_baseline_score. Downstream
    # dashboards MUST NOT conflate the two — improvement gauges absolute
    # quality gain; joint_vs_roundrobin_delta_pp gauges joint mode's edge
    # over the round-robin legacy path on the same holdout.
    metrics = {
        "timestamp": timestamp,
        "mode": effective_mode,
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
    # Joint-mode-only A/B baseline fields (D-OUT-02 + W3 explicit A/B delta)
    if effective_mode == "joint" and roundrobin_baseline_score is not None:
        metrics["joint_score"] = evolved_score
        metrics["roundrobin_baseline_score"] = roundrobin_baseline_score
        metrics["epsilon_pp"] = EPSILON_PP
        metrics["joint_vs_roundrobin_delta_pp"] = joint_vs_roundrobin_delta_pp
        metrics["ab_elapsed_seconds"] = ab_elapsed
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2)
    )

    # Save diff
    diff_text = _generate_diff(original_sections, evolved_sections)
    (output_dir / "diff.txt").write_text(diff_text)

    # ── 11.5. Joint mode: persist A/B baseline副本文件(shared-prefix layout, D-OUT-01)
    if effective_mode == "joint" and ab_baseline_evolved_sections:
        ab_data = [
            {"section_id": s.section_id, "text": s.text}
            for s in ab_baseline_evolved_sections
        ]
        (output_dir / "roundrobin_baseline_evolved_sections.json").write_text(
            json.dumps(ab_data, indent=2)
        )
        ab_diff_text = _generate_diff(
            original_sections, ab_baseline_evolved_sections
        )
        (output_dir / "roundrobin_baseline_diff.txt").write_text(ab_diff_text)

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
@click.option("--model", default=None, help="Override model for all LLM calls (e.g. openai/qwen-plus)")
@click.option("--api-base", default=None, help="Override API base URL")
@click.option(
    "--mode",
    default="joint",
    type=click.Choice(["joint", "round-robin"]),
    help="Optimization mode: 'joint' (default, optimizes all sections "
         "simultaneously via GEPA) or 'round-robin' (legacy, optimizes "
         "section-by-section). --section <id> implicitly forces round-robin "
         "single-section even with --mode joint.",
)
def main(section, iterations, eval_source, hermes_repo, dry_run, model, api_base, mode):
    """Evolve hermes-agent prompt sections using DSPy + GEPA optimization."""
    evolve(
        section=section,
        iterations=iterations,
        eval_source=eval_source,
        hermes_repo=hermes_repo,
        dry_run=dry_run,
        model=model,
        api_base=api_base,
        mode=mode,
    )


if __name__ == "__main__":
    main()
