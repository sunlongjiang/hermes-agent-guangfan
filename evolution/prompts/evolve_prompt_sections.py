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
from rich.table import Table

from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintValidator
from evolution.core.cost_tracker import CostTracker, CostBudgetExceeded
from evolution.prompts.prompt_loader import extract_prompt_sections, PromptSection
from evolution.prompts.prompt_module import PromptModule
from evolution.prompts.prompt_dataset import (
    PromptDatasetBuilder,
    PromptBehavioralDataset,
    PromptBehavioralExample,   # NEW: Phase 19 D-16 union helper 使用
    _normalize_task_hash,      # NEW: Phase 19 D-15/D-16 hash dedup
)
from evolution.prompts.prompt_metric import PromptBehavioralMetric
from evolution.prompts.prompt_constraints import PromptRoleChecker
from evolution.prompts.drift_detector import DRIFT_DIMENSIONS, DriftDetector

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


# ── Phase 19 D-24: JSONL bad-line tolerance ──────────────────────────
_SESSION_SOURCE_BAD_LINE_WARN: float = 0.05


def _load_session_dataset_resilient(
    session_dir: Path,
    metrics: Optional[dict] = None,
) -> tuple["PromptBehavioralDataset", dict]:
    """Load PromptBehavioralDataset from <dir>/{train,val,holdout}.jsonl
    with per-line try/except. Phase 19 D-24 mirror of Phase 14's
    _load_jsonl_skip_bad — we do NOT modify PromptBehavioralDataset.load
    (CONTEXT explicit v2-STAB-01 boundary).

    Args:
        session_dir: Directory produced by mine_prompt_sessions.
        metrics: WR-01 fix: optional dict — when provided, the total
            JSONL bad-line skip count (sum across all 3 splits) is
            written to metrics["jsonl_skipped_lines"], satisfying the
            session_prompt_miner._fresh_metrics docstring contract that
            this helper "maintains" the line-level counter (B3 fix's
            second channel). Without this argument the field remains
            permanently 0 even when bad lines were skipped — the bug
            this fix addresses.

    Returns:
        (dataset, skipped_counts) where skipped_counts is
        {"train": int, "val": int, "holdout": int}. Missing files yield
        an empty split with skip=0.

    Side effects:
        Prints yellow Rich warning when any split's skip rate > 5%.
        When `metrics` is provided, mutates metrics["jsonl_skipped_lines"]
        (accumulator: prior value + this run's skip count).
    """
    dataset = PromptBehavioralDataset()
    skipped = {"train": 0, "val": 0, "holdout": 0}
    for split_name in ("train", "val", "holdout"):
        jp = session_dir / f"{split_name}.jsonl"
        if not jp.exists():
            continue
        kept: list = []
        sk = 0
        with open(jp) as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                    kept.append(PromptBehavioralExample.from_dict(d))
                except (json.JSONDecodeError, TypeError, ValueError):
                    sk += 1
        setattr(dataset, split_name, kept)
        skipped[split_name] = sk
        total = len(kept) + sk
        if total > 0 and sk / total > _SESSION_SOURCE_BAD_LINE_WARN:
            console.print(
                f"[yellow]⚠ session-source {split_name}: skipped {sk}/{total} "
                f"bad JSONL lines ({sk / total * 100:.1f}%) > 5% threshold[/yellow]"
            )
    # WR-01 fix: write through to the shared metrics dict so the
    # `jsonl_skipped_lines` field in _fresh_metrics actually reflects
    # bad lines skipped (previously the second return value was the
    # only signal, and callers ignored it — leaving the metric at 0).
    if metrics is not None:
        metrics["jsonl_skipped_lines"] = (
            metrics.get("jsonl_skipped_lines", 0) + sum(skipped.values())
        )
    return dataset, skipped


# ── Helpers ──────────────────────────────────────────────────────────────────


def _cost_breakdown(opt_spent: float, bench_spent: float) -> dict[str, float]:
    """WR-09: produce the Phase 20 D-16 dual-track cost breakdown.

    Extracted to a single source of truth so the FAILED and success
    paths cannot drift when a third cost source is added.
    """
    return {
        "optimization": float(opt_spent),
        "benchmark": float(bench_spent),
    }


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
    drift_thresholds_path: Path = Path("datasets/prompts/drift_thresholds.json"),
    session_source: Optional[Path] = None,
    # Phase 20 D-12 + D-15 + D-16
    benchmark: str = "none",
    benchmark_tier: Optional[str] = None,
    benchmark_cache: bool = True,
    benchmark_max_cost: float = 50.0,
    wait_mode: str = "wait",
    async_full_verify: bool = True,
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
        drift_thresholds_path: Path to drift_thresholds.json with per-dim
            F1-optimized thresholds (Phase 18 D-BYPASS-02). There is no
            bypass flag (D-BYPASS-01) -- to disable drift gate, re-calibrate
            thresholds via `python -m evolution.prompts.build_drift_calibration`.
        session_source: Optional Path to a directory produced by
            `python -m evolution.prompts.mine_prompt_sessions`. When given,
            the session-mined dataset (train/val/holdout JSONL) is unioned
            with the synthetic dataset via hash dedup (Phase 19 decisions
            D-21 and D-16). None = pre-Phase-19 behavior (synthetic only).
            Works in both joint and round-robin modes.
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

    # ── 5b. Phase 19 D-21 / D-16: Union session-mined dataset ───────────
    if session_source is not None:
        console.print(
            f"\n[bold]Loading session-mined dataset[/bold] from {session_source}"
        )
        session_dataset, session_skipped = _load_session_dataset_resilient(
            Path(session_source)
        )
        console.print(
            f"  Session split: {len(session_dataset.train)} train / "
            f"{len(session_dataset.val)} val / {len(session_dataset.holdout)} holdout"
        )
        if any(session_skipped.values()):
            console.print(
                f"  (skipped lines: train={session_skipped['train']} "
                f"val={session_skipped['val']} holdout={session_skipped['holdout']})"
            )

        # D-16: per-split hash dedup. Session example wins on collision.
        # Cross-split hash dedup: an example's split is fully determined by
        # _hash_to_split — so if session example lands in 'holdout' and synthetic
        # example with the same hash sits in 'train', the synthetic one is
        # dropped from train (session wins; session sits in its computed split).
        # We achieve this via a two-pass union:
        #   1) Per split: dedup synthetic vs session, session wins.
        #   2) Drop synthetic examples whose hash exists in any session split.
        session_hashes_by_split: dict[str, dict[str, "PromptBehavioralExample"]] = {
            split_name: {
                _normalize_task_hash(ex.user_message): ex
                for ex in getattr(session_dataset, split_name)
            }
            for split_name in ("train", "val", "holdout")
        }
        all_session_hashes: set[str] = set()
        for split_name in ("train", "val", "holdout"):
            all_session_hashes |= set(session_hashes_by_split[split_name].keys())

        for split_name in ("train", "val", "holdout"):
            synth_split = getattr(dataset, split_name)
            synth_kept: list = []
            for ex in synth_split:
                h = _normalize_task_hash(ex.user_message)
                if h in all_session_hashes:
                    continue  # session wins (D-16); drop synthetic across splits
                synth_kept.append(ex)
            # Merge: kept synthetic + this split's session entries
            merged = synth_kept + list(session_hashes_by_split[split_name].values())
            setattr(dataset, split_name, merged)

        console.print(
            f"  After union: {len(dataset.train)} train / "
            f"{len(dataset.val)} val / {len(dataset.holdout)} holdout"
        )

    # ── 6. Optimization (joint vs round-robin fork) ──────────────────────
    # WR-05 fix: snapshot _section_ids via list(...) so the round-robin
    # for-loop (which rebinds `module = optimizer.compile(...)` per
    # iteration) does not implicitly rely on whether dspy.GEPA.compile
    # returns the same module instance or a deep-copy with its own
    # _section_ids attribute. The IDs themselves are stable across the
    # call by design, but capturing them up front makes the invariant
    # explicit and survives any future dspy refactor that changes the
    # compile() return semantics.
    sections_to_optimize = (
        [section] if section else list(module._section_ids)
    )

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
        # WR-03 fix: removed unused `num_predictors = len(module._section_ids)`.
        # The round-robin branch does NOT consume num_predictors anywhere —
        # only joint_budget (set to 0 here) and rr_per_section_budget (below)
        # are read on this path.
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

    # W-2/W-3 (2026-05-19): Phase 13 declared max_cost_usd but
    # evolve_prompt_sections.py never instantiated a tracker. Plan 06 wires
    # the missing optimization-side CostTracker so total_cost_breakdown's
    # 'optimization' field reports the real LM spend across GEPA + MIPROv2
    # + A/B baseline runs. Without this wrap the field is permanently 0.0.
    optimization_tracker = CostTracker(max_usd=config.max_cost_usd)
    optimization_tracker_spent: float = 0.0
    try:
        with optimization_tracker:
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

            optimization_tracker_spent = optimization_tracker.spent_usd
    except CostBudgetExceeded as e:
        console.print(f"[red]Optimization cost budget exceeded: {e}[/red]")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        aborted_dir = Path("output") / "prompts" / f"ABORTED_{timestamp}"
        aborted_dir.mkdir(parents=True, exist_ok=True)
        (aborted_dir / "metrics.json").write_text(
            json.dumps({
                "timestamp": timestamp,
                "status": "ABORTED",
                "reason": "optimization_cost_budget_exceeded",
                "max_cost_usd": config.max_cost_usd,
                "spent_usd": getattr(e, "spent_usd", 0.0),
            }, indent=2)
        )
        console.print(f"  Saved aborted-cost state to {aborted_dir}/")
        return

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

    # 8c. Personality drift detection (Phase 18, 3-run averaging per D-ROB-01/04)
    console.print("  Running personality drift detection (3-run averaging)...")
    drift_thresholds_raw = json.loads(drift_thresholds_path.read_text())
    # Strip _meta if present; DriftDetector only needs the per-dim threshold floats.
    drift_thresholds = {
        d: drift_thresholds_raw[d] for d in DRIFT_DIMENSIONS
    }
    drift_detector = DriftDetector(config, drift_thresholds)
    drift_results = drift_detector.check_all(
        original_sections, evolved_sections,
    )

    drift_exceeded_dims: list = []
    drift_per_dim_metrics: dict = {}
    drift_report_lines: list = []

    for dr in drift_results:
        all_constraint_results.append(dr["constraint_result"])
        if not dr["constraint_result"].passed:
            all_pass = False
        # D-OUT-02 aggregation for metrics.json
        drift_per_dim_metrics[dr["section_id"]] = {
            dim: {
                "mean": v["mean"],
                "stdev": v["stdev"],
                "exceeded": v["exceeded"],
            }
            for dim, v in dr["per_dim"].items()
        }
        for dim, v in dr["per_dim"].items():
            if v["exceeded"]:
                drift_exceeded_dims.append(
                    {"section": dr["section_id"], "dim": dim}
                )

        # D-GATE-03 soft warn / D-GATE-04 hard reject stdout
        if dr["severity"] == "warn":
            exceeded_dim = next(
                d for d, v in dr["per_dim"].items() if v["exceeded"]
            )
            t_val = drift_thresholds[exceeded_dim]
            mean_val = dr["per_dim"][exceeded_dim]["mean"]
            console.print(
                f"  [yellow]Drift warning: section '{dr['section_id']}' "
                f"dim '{exceeded_dim}' = {mean_val:.2f} "
                f"(threshold {t_val:.2f}) -- review evolved text "
                f"before deploying[/yellow]"
            )
        elif dr["severity"] == "reject":
            console.print(
                f"  [red]Drift detected: section '{dr['section_id']}' "
                f"exceeded {dr['exceeded_count']} dims -- REJECTED, "
                f"evolved prompts NOT deployed[/red]"
            )

        # D-OUT-03 drift_report.txt sections -- last-run explanation only
        drift_report_lines.append(f"## Section: {dr['section_id']}\n\n")
        for dim, v in dr["per_dim"].items():
            if not v["exceeded"]:
                decision = "pass"
            elif dr["severity"] == "warn":
                decision = "warn"
            else:
                decision = "reject"
            drift_report_lines.append(
                f"### Dim: {dim}\n"
                f"- Mean: {v['mean']:.4f}\n"
                f"- Stdev: {v['stdev']:.4f}\n"
                f"- Threshold: {drift_thresholds[dim]:.2f}\n"
                f"- Decision: {decision}\n"
                f"- Raw scores: {v['raw']}\n\n"
            )
        drift_report_lines.append(
            f"**Explanation:** {dr['explanation']}\n\n"
        )

    drift_passed = not any(
        dr["severity"] == "reject" for dr in drift_results
    )

    # D-OUT-01: Rich Table -- 5 sections x 4 dims = up to 20 rows
    drift_table = Table(
        title="Drift Detection (per-section x per-dim, 3-run averaged)"
    )
    drift_table.add_column("Section", style="bold")
    drift_table.add_column("Dim")
    drift_table.add_column("Mean", justify="right")
    drift_table.add_column("Stdev", justify="right")
    drift_table.add_column("Threshold", justify="right")
    drift_table.add_column("Exceeded", justify="center")
    drift_table.add_column("Status")
    for dr in drift_results:
        for dim in DRIFT_DIMENSIONS:
            v = dr["per_dim"][dim]
            exc_str = "[red]x[/red]" if v["exceeded"] else "[green]ok[/green]"
            status = ""
            if dr["severity"] == "warn" and v["exceeded"]:
                status = "[yellow]WARN[/yellow]"
            elif dr["severity"] == "reject" and v["exceeded"]:
                status = "[red]REJECT[/red]"
            drift_table.add_row(
                dr["section_id"],
                dim,
                f"{v['mean']:.3f}",
                f"{v['stdev']:.3f}",
                f"{drift_thresholds[dim]:.2f}",
                exc_str,
                status,
            )
    console.print(drift_table)

    # 8d. Print all constraint results (was step 8c pre-Phase-18)
    for c in all_constraint_results:
        icon = "+" if c.passed else "x"
        color = "green" if c.passed else "red"
        console.print(
            f"  [{color}]{icon} {c.constraint_name}[/{color}]: {c.message}"
        )

    if not all_pass:
        # Save failed results for inspection (D-GATE-04 + D-OUT-03)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = Path("output") / "prompts" / f"FAILED_{timestamp}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # FAILED metrics -- include drift_* so post-mortem can read why
        failed_metrics = {
            "timestamp": timestamp,
            "status": "FAILED",
            "constraints_passed": False,
        }
        if drift_results:
            failed_metrics["drift_passed"] = drift_passed
            failed_metrics["drift_per_dim"] = drift_per_dim_metrics
            failed_metrics["drift_thresholds"] = drift_thresholds
            failed_metrics["drift_exceeded_dims"] = drift_exceeded_dims
        (output_dir / "metrics.json").write_text(
            json.dumps(failed_metrics, indent=2)
        )

        # Also write evolved_sections.json, diff.txt, drift_report.txt
        # to enable human review of REJECT decision (D-GATE-04 + D-OUT-03)
        if drift_results:
            evolved_data_failed = [
                {"section_id": s.section_id, "text": s.text}
                for s in evolved_sections
            ]
            (output_dir / "evolved_sections.json").write_text(
                json.dumps(evolved_data_failed, indent=2)
            )
            (output_dir / "diff.txt").write_text(
                _generate_diff(original_sections, evolved_sections)
            )
            (output_dir / "drift_report.txt").write_text(
                "".join(drift_report_lines)
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

        # WR-05 fix: snapshot section ids before the loop, since
        # `ab_baseline_module = ab_optimizer.compile(...)` rebinds the
        # variable each iteration. This makes the loop body independent
        # of dspy.GEPA.compile's return semantics (same instance vs
        # deep-copied module).
        ab_section_ids = list(ab_baseline_module._section_ids)
        for ab_sid in ab_section_ids:
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
        # space (`EPSILON_PP / 100`) for direct comparison with raw scores.
        # WR-06 fix: this is a STRICT less-than — a regression that lands
        # exactly at -EPSILON_PP is treated as acceptable (within tolerance).
        # Per Plan 17-03 soft-gate semantics: "warn when joint regresses by
        # MORE THAN 1pp". To stabilize the boundary against IEEE-754 noise
        # (e.g. 0.60 - 0.59 == 0.010000000000000009, not 0.01), we round the
        # scores to 4 decimal places before the comparison. 4dp << 1pp so
        # this preserves semantic resolution; it only smooths the very last
        # bit of float representation, making the gate decision deterministic
        # across CPython / hardware / OS combinations.
        evolved_rounded = round(evolved_score, 4)
        baseline_rounded = round(roundrobin_baseline_score, 4)
        if evolved_rounded < baseline_rounded - (EPSILON_PP / 100):
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

    # ── 10.5. Benchmark gate (Phase 20 D-18) — opt-in, OUT OF GEPA loop ─
    # Decision lattice:
    #   benchmark == "none"   -> skip (default; pre-Phase-20 behavior).
    #   benchmark == "tblite" -> stratified 30-task subset, 3-run avg.
    #   benchmark == "tblite-full" -> CONTEXT D-06 — NOT YET IMPLEMENTED
    #       in Plan 06 (full 100-task run is reserved for Phase 22
    #       async-full-verify orchestration). Surfaced as
    #       click.ClickException.
    # wait_mode == "detach"  -> NOT YET IMPLEMENTED. exits non-zero.
    benchmark_results: list = []
    benchmark_decision = "skipped"
    benchmark_risk_score: Optional[float] = None
    benchmark_per_tier: dict = {}
    benchmark_passed: Optional[bool] = None
    benchmark_tracker_spent = 0.0

    if benchmark != "none":
        if benchmark == "tblite-full":
            raise click.ClickException(
                "--benchmark=tblite-full is reserved for Phase 22 "
                "(async full verify). Use --benchmark=tblite for the "
                "stratified 30-task subset."
            )
        if wait_mode == "detach":
            click.echo(
                "--detach is reserved for Phase 22 "
                "(see .planning/todos/pending/2026-05-19-benchmark-detach-subcommands.md). "
                "Plan 06 ships synchronous --wait only.",
                err=True,
            )
            sys.exit(1)

        console.print(
            f"\n[bold]Running TBLite benchmark gate (mode={benchmark})[/bold]"
        )
        # D-Discretion-1 lazy import: never import benchmark_gate at module
        # load time. Plan 01's evolution/benchmarks/__init__.py is a
        # lazy-guard so callers running with --benchmark=none on a host
        # without hermes-agent / huggingface_hub still work.
        #
        # W-4 (2026-05-19): tests must double-patch this lazy import. After
        # the next line executes, `TBLiteBenchmarkGate` is bound as a NAME
        # in the evolve_prompt_sections module namespace AS WELL AS being
        # available at evolution.benchmarks.benchmark_gate.TBLiteBenchmarkGate.
        # Patching only the source site does NOT intercept this binding.
        from evolution.benchmarks.benchmark_gate import TBLiteBenchmarkGate

        # Load anchor + stratified subset (Wave 4 artifacts).
        anchor_path = Path("datasets/prompts/tblite_anchor.json")
        subset_path = Path("datasets/prompts/tblite_stratified_subset.json")
        if not anchor_path.exists():
            raise click.ClickException(
                f"{anchor_path} not found. Run "
                f"`python -m evolution.benchmarks.build_tblite_calibration` first "
                f"(Phase 20 D-13 prerequisite — Plan 05 produces this; "
                f"B-1 forbids mock fallback)."
            )
        if not subset_path.exists():
            raise click.ClickException(
                f"{subset_path} not found. Plan 01 should have placed "
                f"a placeholder; check phase 20 wave 1 completion."
            )
        anchor = json.loads(anchor_path.read_text())
        subset = json.loads(subset_path.read_text())

        # Mock-tier audit: warn loudly so accept decisions are recognized
        # as non-authoritative. Per Plan 05's B-1 revision (2026-05-19)
        # no mock anchor SHOULD ever ship — this warning is a runtime
        # guard against historical / external archive artifacts that
        # bypass the planning flow.
        if anchor.get("_meta", {}).get("tier") == "mock":
            console.print(
                "[bold yellow]⚠ Anchor is _meta.tier='mock' — gate "
                "accept/reject decisions are NOT trustworthy. Plan 05 "
                "(B-1) forbids mock-anchor authoring; this file appears "
                "to be a stale or external artifact. Re-run "
                "build_tblite_calibration before relying on the "
                "gate.[/bold yellow]"
            )

        # D-05 + W-7 (2026-05-19): --benchmark-tier CSV subset filter.
        # Reads item['tier'] directly (W-7 schema: task_filter is list of
        # {name, tier} dicts). NO index slicing — the previous
        # offset-based implementation depended on subset being sorted
        # easy→medium→hard→extreme, which is no longer a contract.
        if benchmark_tier:
            selected_tiers = set(
                t.strip().lower() for t in benchmark_tier.split(",") if t.strip()
            )
            bad = selected_tiers - {"easy", "medium", "hard", "extreme"}
            if bad:
                raise click.ClickException(
                    f"--benchmark-tier contains unknown tiers: {sorted(bad)} "
                    f"(expected subset of easy,medium,hard,extreme)"
                )
            subset = dict(subset)
            full_filter = subset.get("task_filter", [])
            # Tolerate both W-7 object form AND legacy flat-string form
            # during transition: if items are strings, fall back to the
            # per_tier_counts index slice as last resort with a warning.
            if full_filter and isinstance(full_filter[0], dict):
                new_filter = [
                    item for item in full_filter
                    if str(item.get("tier", "")).strip().lower() in selected_tiers
                ]
                new_counts = {}
                for item in new_filter:
                    t = str(item["tier"]).strip().lower()
                    new_counts[t] = new_counts.get(t, 0) + 1
            else:
                # Legacy schema — log + best-effort index slice.
                console.print(
                    "[yellow]Subset uses legacy flat-string task_filter "
                    "(pre-W-7 schema). --benchmark-tier filter will fall "
                    "back to per_tier_counts index slicing.[/yellow]"
                )
                full_counts = subset.get("per_tier_counts", {})
                new_filter = []
                offset = 0
                new_counts = {}
                for tier_name in ("easy", "medium", "hard", "extreme"):
                    n = full_counts.get(tier_name, 0)
                    if tier_name in selected_tiers:
                        new_filter.extend(full_filter[offset:offset + n])
                        new_counts[tier_name] = n
                    offset += n
            subset["task_filter"] = new_filter
            subset["per_tier_counts"] = new_counts
            if not new_filter:
                raise click.ClickException(
                    f"--benchmark-tier produced an empty subset. "
                    f"Pick at least one of: easy,medium,hard,extreme."
                )

        # Load moving_avg_history if present (D-01 first-run-falls-back-to-anchor).
        history_path = Path("output/prompts/tblite_history.json")
        moving_avg_history: list = []
        if history_path.exists():
            try:
                moving_avg_history = json.loads(history_path.read_text())
                if not isinstance(moving_avg_history, list):
                    moving_avg_history = []
            except json.JSONDecodeError:
                console.print(
                    f"[yellow]{history_path} malformed; using empty history "
                    f"(moving_avg falls back to anchor per D-01).[/yellow]"
                )
                moving_avg_history = []

        gate = TBLiteBenchmarkGate(
            config,
            anchor=anchor,
            stratified_subset=subset,
            moving_avg_history=moving_avg_history,
        )

        cache_dir = (
            Path.home() / ".cache" / "hermes-evolution" / "tblite"
        )
        cache_dir.mkdir(parents=True, exist_ok=True)

        # D-16: dual-track budget. The benchmark tracker is independent
        # from the optimization tracker (Edit 0 wires that one).
        benchmark_tracker = CostTracker(max_usd=benchmark_max_cost)
        try:
            with benchmark_tracker:
                benchmark_results = gate.check_all(
                    original_sections,
                    evolved_sections,
                    cache_dir=cache_dir,
                    use_cache=benchmark_cache,
                )
            benchmark_tracker_spent = benchmark_tracker.spent_usd
        except CostBudgetExceeded as e:
            console.print(f"[red]Benchmark cost budget exceeded: {e}[/red]")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            aborted_dir = Path("output") / "prompts" / f"ABORTED_{timestamp}"
            aborted_dir.mkdir(parents=True, exist_ok=True)
            (aborted_dir / "metrics.json").write_text(
                json.dumps({
                    "timestamp": timestamp,
                    "status": "ABORTED",
                    "benchmark_decision": "aborted_cost",
                    "benchmark_max_cost_usd": benchmark_max_cost,
                    "benchmark_spent_usd": getattr(e, "spent_usd", 0.0),
                }, indent=2)
            )
            console.print(f"  Saved aborted-cost state to {aborted_dir}/")
            return

        # Single-element list per TBLiteBenchmarkGate.check_all contract.
        bench = benchmark_results[0]
        benchmark_decision = bench["decision"]
        benchmark_risk_score = bench["risk_score"]
        benchmark_per_tier = bench["per_tier"]
        benchmark_passed = (benchmark_decision == "accept")

        # D-OUT-01-style Rich Table (mirror Phase 18 drift_table at line 722).
        bench_table = Table(
            title=(
                f"TBLite Benchmark Gate "
                f"(Risk_Score={benchmark_risk_score:.2f} / "
                f"reject_threshold={bench['reject_threshold']:.2f})"
            )
        )
        bench_table.add_column("Tier", style="bold")
        bench_table.add_column("Mean", justify="right")
        bench_table.add_column("Stdev", justify="right")
        bench_table.add_column("Threshold", justify="right")
        bench_table.add_column("Anchor", justify="right")
        bench_table.add_column("MovingAvg", justify="right")
        bench_table.add_column("Breach", justify="center")
        for tier in ("easy", "medium", "hard", "extreme"):
            v = benchmark_per_tier.get(tier, {})
            if not v:
                continue
            breach_icon = (
                "[red]x[/red]" if v.get("breach")
                else "[green]ok[/green]"
            )
            bench_table.add_row(
                tier,
                f"{v.get('mean', 0):.3f}",
                f"{v.get('stdev', 0):.3f}",
                f"{v.get('threshold', 0):.3f}",
                f"{v.get('anchor', 0):.3f}",
                f"{v.get('moving_avg', 0):.3f}",
                breach_icon,
            )
        console.print(bench_table)

        # Hard reject -> FAILED_<ts>/ + return BEFORE write-back (D-18 + D-GATE-04 mirror).
        if benchmark_decision == "reject":
            console.print(
                f"[red]Benchmark gate REJECTED "
                f"(Risk_Score={benchmark_risk_score:.2f} >= "
                f"{bench['reject_threshold']:.2f}) — "
                f"evolved prompts NOT deployed[/red]"
            )
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = (
                Path("output") / "prompts" / f"FAILED_{timestamp}"
            )
            output_dir.mkdir(parents=True, exist_ok=True)
            failed_metrics = {
                "timestamp": timestamp,
                "status": "FAILED",
                "constraints_passed": True,  # in-loop constraints passed; benchmark gate rejected
                "benchmark_decision": "reject",
                "benchmark_passed": False,
                "benchmark_risk_score": benchmark_risk_score,
                "benchmark_per_tier": benchmark_per_tier,
                "benchmark_reason": (
                    f"Risk_Score {benchmark_risk_score:.2f} >= "
                    f"{bench['reject_threshold']:.2f}"
                ),
                # W-2/W-3: optimization_tracker_spent is now a real local
                # variable established by Edit 0. NO locals().get(...)
                # fallback — if Edit 0 was skipped, this AttributeError
                # fails loudly (good) rather than silently reporting 0.0.
                # WR-09: cost breakdown produced via _cost_breakdown to
                # keep this path and the success path in lockstep.
                "total_cost_breakdown": _cost_breakdown(
                    optimization_tracker_spent, benchmark_tracker_spent
                ),
            }
            (output_dir / "metrics.json").write_text(
                json.dumps(failed_metrics, indent=2)
            )
            # tblite_report.json (D-04 schema sans constraint_result).
            serializable_report = {
                k: v for k, v in bench.items()
                if k != "constraint_result"
            }
            (output_dir / "tblite_report.json").write_text(
                json.dumps(serializable_report, indent=2, sort_keys=True)
            )
            (output_dir / "evolved_sections.json").write_text(
                json.dumps(
                    [
                        {"section_id": s.section_id, "text": s.text}
                        for s in evolved_sections
                    ],
                    indent=2,
                )
            )
            (output_dir / "diff.txt").write_text(
                _generate_diff(original_sections, evolved_sections)
            )
            console.print(f"  Saved failed results to {output_dir}/")
            return

        # If we reach here, gate accepted. Step 11 continues normally.
        console.print(
            f"[green]Benchmark gate ACCEPTED "
            f"(Risk_Score={benchmark_risk_score:.2f} < "
            f"{bench['reject_threshold']:.2f})[/green]"
        )

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
    # Phase 18 / D-OUT-02 + D-ROB-04: drift_* fields written UNCONDITIONALLY
    # for BOTH joint AND round-robin modes. This block sits at 4-space indent
    # (function-body level), OUTSIDE the joint-only `if` block above.
    if drift_results:
        metrics["drift_per_dim"] = drift_per_dim_metrics
        metrics["drift_thresholds"] = drift_thresholds
        metrics["drift_exceeded_dims"] = drift_exceeded_dims
        metrics["drift_passed"] = drift_passed
        if drift_exceeded_dims:
            # D-OUT-02: drift_max_section / drift_max_dim = (section, dim) with highest mean
            max_entry = max(
                (
                    (sid, dim, drift_per_dim_metrics[sid][dim]["mean"])
                    for sid in drift_per_dim_metrics
                    for dim in drift_per_dim_metrics[sid]
                ),
                key=lambda x: x[2],
            )
            metrics["drift_max_section"] = max_entry[0]
            metrics["drift_max_dim"] = max_entry[1]

    # Phase 20 D-04: benchmark_* fields. ALWAYS write benchmark_decision
    # (default 'skipped') so Phase 16 dashboard can filter by status.
    metrics["benchmark_decision"] = benchmark_decision
    if benchmark_results:
        metrics["benchmark_passed"] = benchmark_passed
        metrics["benchmark_risk_score"] = benchmark_risk_score
        metrics["benchmark_per_tier"] = benchmark_per_tier
        metrics["benchmark_tier_weights"] = benchmark_results[0]["tier_weights"]
        metrics["benchmark_reject_threshold"] = (
            benchmark_results[0]["reject_threshold"]
        )

    # Phase 20 D-16: dual-track cost breakdown.
    # W-2/W-3 (2026-05-19): optimization_tracker_spent is captured by
    # Edit 0's `with optimization_tracker:` context at line ~616.
    # optimization_tracker.spent_usd holds the real GEPA + MIPROv2 + A/B
    # baseline LM spend. NO locals-dict fallback — if Edit 0 was not
    # applied this line raises NameError loudly. Previous draft used a
    # locals-dict fallback which silently masked the missing tracker as
    # 0.0 (the W-2/W-3 bug).
    # WR-09: cost breakdown produced via _cost_breakdown so this path
    # and the FAILED path share the same shape.
    metrics["total_cost_breakdown"] = _cost_breakdown(
        optimization_tracker_spent, benchmark_tracker_spent
    )

    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2)
    )

    # Save diff
    diff_text = _generate_diff(original_sections, evolved_sections)
    (output_dir / "diff.txt").write_text(diff_text)

    # D-OUT-03: drift_report.txt (success path)
    if drift_results:
        (output_dir / "drift_report.txt").write_text(
            "".join(drift_report_lines)
        )

    # Phase 20 D-04: tblite_report.json side-by-side with evolved_sections.json
    # so Phase 16 dashboard can ingest per-tier breakdown without re-reading
    # metrics.json.
    if benchmark_results:
        serializable_report = {
            k: v for k, v in benchmark_results[0].items()
            if k != "constraint_result"
        }
        (output_dir / "tblite_report.json").write_text(
            json.dumps(serializable_report, indent=2, sort_keys=True)
        )

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
@click.option(
    "--drift-thresholds-path",
    type=click.Path(exists=True, path_type=Path),
    default=Path("datasets/prompts/drift_thresholds.json"),
    help=(
        "Path to drift_thresholds.json (per-dim F1-optimized thresholds "
        "derived by `python -m evolution.prompts.build_drift_calibration`). "
        "Phase 18 D-BYPASS-02. There is no bypass flag (D-BYPASS-01). "
        "Do not bypass drift detection without re-calibrating thresholds."
    ),
)
@click.option(
    "--session-source",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help=(
        "Phase 19 D-21. Path to a directory produced by "
        "`python -m evolution.prompts.mine_prompt_sessions` containing "
        "train.jsonl / val.jsonl / holdout.jsonl. When provided, the "
        "session-mined dataset is UNION-merged (hash dedup, session "
        "wins on collision per D-16) with the synthetic PromptDatasetBuilder "
        "output. Works in both --mode joint and --mode round-robin. "
        "Omitting this flag preserves pre-Phase-19 behavior."
    ),
)
@click.option(
    "--benchmark",
    type=click.Choice(["none", "tblite", "tblite-full"]),
    default="none",
    help=(
        "Phase 20 D-18. Run TBLite benchmark gate after step 10 (out "
        "of GEPA loop, PITFALL #7). 'none' (default) = pre-Phase-20 "
        "behavior. 'tblite' = stratified 30-task subset. "
        "'tblite-full' = reserved for Phase 22 (errors out)."
    ),
)
@click.option(
    "--benchmark-tier",
    default=None,
    help=(
        "CSV of tiers to include (subset of easy,medium,hard,extreme). "
        "Default = all four. Phase 20 D-05 + W-7 (filters by item['tier'])."
    ),
)
@click.option(
    "--benchmark-cache/--no-benchmark-cache",
    default=True,
    help=(
        "Content-addressed cache at ~/.cache/hermes-evolution/tblite/ "
        "(Phase 20 D-15). Disable for a single forced re-run."
    ),
)
@click.option(
    "--benchmark-max-cost",
    default=50.0,
    type=float,
    help=(
        "USD cap for the benchmark cost tracker (Phase 20 D-16 dual-track). "
        "Distinct from --max-cost-usd which governs GEPA + LLM judge."
    ),
)
@click.option(
    "--wait/--detach",
    default=True,
    help=(
        "Phase 20 D-12. --wait blocks until TBLite subprocess exits then "
        "decides write-back (DEFAULT). --detach is reserved for Phase 22 "
        "(currently exits non-zero)."
    ),
)
@click.option(
    "--async-full-verify/--no-async-full-verify",
    default=True,
    help=(
        "Phase 20 D-07. NO-OP in Plan 06 — accepted for forward "
        "compatibility but the background full-verify dispatch is "
        "reserved for Phase 22."
    ),
)
def main(section, iterations, eval_source, hermes_repo, dry_run, model,
         api_base, mode, drift_thresholds_path, session_source,
         benchmark, benchmark_tier, benchmark_cache, benchmark_max_cost,
         wait, async_full_verify):
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
        drift_thresholds_path=drift_thresholds_path,
        session_source=session_source,
        benchmark=benchmark,
        benchmark_tier=benchmark_tier,
        benchmark_cache=benchmark_cache,
        benchmark_max_cost=benchmark_max_cost,
        wait_mode="wait" if wait else "detach",
        async_full_verify=async_full_verify,
    )


if __name__ == "__main__":
    main()
