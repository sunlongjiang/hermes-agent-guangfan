"""Standalone CLI for building the drift calibration set + deriving thresholds.

Phase 18 D-CAL-05: blocking step before DriftDetector goes live in
evolve_prompt_sections.py. Pitfall 6 prevention #1: this CLI MUST run before
`python -m evolution.prompts.evolve_prompt_sections` uses DriftDetector for
the first time after a hermes-agent prompt revision.

Quarterly recalibration: re-run this CLI (with a new --seed) to refresh
thresholds when hermes-agent prompts evolve substantially (PITFALL §6.6 /
Pitfall 6 prevention #6 — cadence is process, not code).

WARNING: do not bypass DriftDetector or hand-edit drift_thresholds.json
without re-calibrating. The _meta block in drift_thresholds.json
(calibration_timestamp / generator_model / seed / f1_self / f1_tier) lets
ops detect unexplained edits — regenerate if those fields go missing or
stale.

Usage:
    python -m evolution.prompts.build_drift_calibration \\
        [--hermes-repo PATH] [--seed N] \\
        [--output-jsonl PATH] [--output-thresholds PATH]
"""
import dataclasses
import json
import os
import statistics
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from evolution.core.config import EvolutionConfig
from evolution.prompts.drift_calibration import (
    DriftCalibrationBuilder,
    DriftCalibrationDataset,
    derive_thresholds,
)
from evolution.prompts.drift_detector import DRIFT_DIMENSIONS, DriftDetector
from evolution.prompts.prompt_loader import extract_prompt_sections


console = Console()


def _compute_per_dim_f1(
    calibration: DriftCalibrationDataset,
    thresholds: dict,
    config: EvolutionConfig,
) -> dict:
    """Compute per-dim and macro F1 on the calibration set self-eval (RA6).

    Returns dict: {<dim>: f1_float, "macro": macro_f1_float}.
    Pure stdlib — same approach as derive_thresholds (RA3).
    """
    detector = DriftDetector(config, thresholds)
    scored = []
    for ex in calibration.examples:
        scores, _ = detector._check_one_run(
            ex.section_id, ex.original_text, ex.evolved_text,
        )
        scored.append((ex.is_drift, ex.drift_dim, scores))

    result = {}
    per_dim_f1s = []
    for dim in DRIFT_DIMENSIONS:
        t = thresholds[dim]
        tp = sum(1 for is_d, d_truth, sc in scored
                 if sc[dim] > t and is_d and d_truth == dim)
        fp = sum(1 for is_d, d_truth, sc in scored
                 if sc[dim] > t and not (is_d and d_truth == dim))
        fn = sum(1 for is_d, d_truth, sc in scored
                 if sc[dim] <= t and is_d and d_truth == dim)
        if tp == 0:
            f1 = 0.0
        else:
            p = tp / (tp + fp)
            r = tp / (tp + fn)
            f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        result[dim] = round(f1, 4)
        per_dim_f1s.append(f1)
    result["macro"] = round(statistics.mean(per_dim_f1s), 4)
    return result


def _classify_f1_tier(
    f1_self: dict,
    target_self: float = 0.85,
    per_dim_floor: float = 0.70,
    macro_floor: float = 0.80,
) -> tuple:
    """RESEARCH §Verification F1 Targets — return (tier, warned_dims).

    TIER 1: all 4 dims >= target_self.
    TIER 2: no dim below per_dim_floor AND macro >= macro_floor (some dims
            may fall in [per_dim_floor, target_self)).
    TIER 3 (fail): any dim < per_dim_floor OR macro < macro_floor.

    Targets are parametrized so the CLI can opt into a v1-pragmatic preset
    (0.60 / 0.35 / 0.50) when the available judge model can't clear the
    research-strict defaults — see `--target-self` / `--per-dim-floor` /
    `--macro-floor` flags. Whichever values are used at run time get
    recorded in thresholds.json `_meta.f1_targets` for audit.
    """
    per_dim = [f1_self[d] for d in DRIFT_DIMENSIONS]
    macro = f1_self["macro"]
    if all(f >= target_self for f in per_dim):
        return 1, []
    if any(f < per_dim_floor for f in per_dim) or macro < macro_floor:
        return 3, [d for d in DRIFT_DIMENSIONS if f1_self[d] < per_dim_floor]
    # Tier 2: borderline dims in [per_dim_floor, target_self)
    warned = [d for d in DRIFT_DIMENSIONS if f1_self[d] < target_self]
    return 2, warned


@click.command()
@click.option(
    "--hermes-repo",
    default=None,
    type=click.Path(),
    help="Path to hermes-agent repo (default: HERMES_AGENT_REPO env var).",
)
@click.option(
    "--seed",
    default=42,
    type=int,
    help="Random seed for the generator (D-CAL-01 — reproducible).",
)
@click.option(
    "--output-jsonl",
    default=Path("datasets/prompts/drift_calibration.jsonl"),
    type=click.Path(path_type=Path),
    help="Output path for the 30-example calibration set (git-tracked per D-CAL-02).",
)
@click.option(
    "--output-thresholds",
    default=Path("datasets/prompts/drift_thresholds.json"),
    type=click.Path(path_type=Path),
    help="Output path for the F1-optimized thresholds JSON (git-tracked per D-CAL-02).",
)
@click.option(
    "--model",
    default=None,
    help="Override judge_model (e.g. openai/qwen-plus)",
)
@click.option(
    "--api-base",
    default=None,
    help="Override API base URL",
)
@click.option(
    "--no-derive",
    is_flag=True,
    help="Generate the calibration JSONL only; skip threshold derivation.",
)
@click.option(
    "--reuse-jsonl",
    is_flag=True,
    help=(
        "Skip generation and re-use the existing JSONL at --output-jsonl "
        "(re-derive thresholds + F1 only; saves ~$0.50-2 generator cost when "
        "iterating on --eval-model)."
    ),
)
@click.option(
    "--eval-model",
    default=None,
    help=(
        "Override eval_model used by the detector / F1 self-eval. Use a "
        "DIFFERENT model family from the generator to satisfy RA5 (same-model "
        "bias mitigation). Example: --eval-model openai/gpt-4.1-mini when the "
        "generator is qwen-plus."
    ),
)
@click.option(
    "--eval-api-base",
    default=None,
    help=(
        "Override api_base for the detector only (generator keeps its api_base). "
        "Pair with --eval-model when the two models live on different backends "
        "(e.g. detector on api.openai.com, generator on dashscope.aliyuncs.com)."
    ),
)
@click.option(
    "--eval-api-key",
    default=None,
    envvar="EVAL_API_KEY",
    help=(
        "Override api_key for the detector only. If --eval-model starts with "
        "'openai/' and --eval-api-key is not provided, falls back to "
        "$OPENAI_API_KEY when set."
    ),
)
@click.option(
    "--target-self",
    default=0.85,
    type=float,
    show_default=True,
    help=(
        "Tier 1 per-dim F1 target on calibration self-eval (RESEARCH default 0.85). "
        "Lower to e.g. 0.60 to accept the v1-pragmatic preset when the judge can't "
        "hit research-strict targets."
    ),
)
@click.option(
    "--per-dim-floor",
    default=0.70,
    type=float,
    show_default=True,
    help=(
        "Tier 3 trigger: any dim F1 below this floor fails calibration. "
        "RESEARCH default 0.70; v1-pragmatic 0.35."
    ),
)
@click.option(
    "--macro-floor",
    default=0.80,
    type=float,
    show_default=True,
    help=(
        "Tier 3 trigger: macro F1 below this floor fails calibration. "
        "RESEARCH default 0.80; v1-pragmatic 0.50."
    ),
)
@click.option(
    "--accept-tier-3",
    is_flag=True,
    help=(
        "Persist thresholds.json even when the run lands in Tier 3 "
        "(default behavior raises ClickException without writing the file). "
        "Use to ship a v1-pragmatic gate when the available judge can't clear "
        "the tier targets — `_meta.f1_tier` will record the actual tier (3) "
        "so downstream operators see the gate is permissive."
    ),
)
def main(
    hermes_repo, seed, output_jsonl, output_thresholds, model, api_base,
    no_derive, reuse_jsonl, eval_model, eval_api_base, eval_api_key,
    target_self, per_dim_floor, macro_floor, accept_tier_3,
):
    """Build the drift calibration set + derive F1-optimized thresholds."""
    console.print("[bold]Phase 18: Drift calibration build[/bold]\n")
    overrides = {}
    if hermes_repo:
        overrides["hermes_repo"] = hermes_repo
    if model:
        overrides["model"] = model
    if api_base:
        overrides["api_base"] = api_base
    config = EvolutionConfig.load(**overrides)

    # Per-side config: detector (eval/F1) can use a different model + backend
    # from the generator. Required to satisfy RA5 when evolution.yaml sets
    # eval == judge (same-model bias collapse).
    eval_config = dataclasses.replace(config)
    if eval_model:
        eval_config.eval_model = eval_model
    if eval_api_base:
        eval_config.api_base = eval_api_base
    if eval_api_key:
        eval_config.api_key = eval_api_key
    elif eval_model and not eval_api_key:
        # Auto-route ONLY OpenAI-hosted families (gpt-/o1-/chatgpt-) to api.openai.com
        # via $OPENAI_API_KEY. Other "openai/<name>" model ids (qwen-*, glm-*, etc.)
        # use the OpenAI-compatible adapter against a non-OpenAI api_base — keep
        # the inherited config.api_base + config.api_key in that case.
        m = eval_model.removeprefix("openai/")
        is_openai_hosted = (
            m.startswith("gpt-") or m.startswith("o1-") or m.startswith("chatgpt-")
        )
        if is_openai_hosted:
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                eval_config.api_key = openai_key
                if not eval_api_base:
                    eval_config.api_base = None

    console.print(f"  hermes-agent repo: {config.hermes_agent_path}")
    same_model = config.judge_model == eval_config.eval_model
    ra5_tag = "[red]RA5 VIOLATION: same model[/red]" if same_model else "[green]RA5 OK[/green]"
    console.print(
        f"  generator: model={config.judge_model} api_base={config.api_base or '<default>'}"
    )
    console.print(
        f"  detector:  model={eval_config.eval_model} api_base={eval_config.api_base or '<default>'}  {ra5_tag}"
    )
    console.print(f"  seed: {seed}")
    if reuse_jsonl:
        console.print("  [yellow]--reuse-jsonl: generation will be skipped[/yellow]")

    # 1. Extract prompt sections
    # NOTE: extract_prompt_sections expects the PATH TO prompt_builder.py,
    # NOT the repo root. Mirror evolve_prompt_sections.py:163-166.
    console.print("\n[bold]1. Extracting prompt sections[/bold]")
    prompt_builder_path = (
        config.hermes_agent_path / "agent" / "prompt_builder.py"
    )
    if not prompt_builder_path.exists():
        raise click.ClickException(
            f"prompt_builder.py not found at {prompt_builder_path}. "
            f"Check HERMES_AGENT_REPO env var or --hermes-repo flag."
        )
    sections = extract_prompt_sections(prompt_builder_path)
    console.print(f"  Extracted {len(sections)} sections from {prompt_builder_path}")
    if len(sections) < 5:
        raise click.ClickException(
            f"D-CAL-03 requires >= 5 sections; got {len(sections)}."
        )

    # 2. Generate or reuse 30 examples
    if reuse_jsonl:
        if not output_jsonl.exists():
            raise click.ClickException(
                f"--reuse-jsonl requires {output_jsonl} to exist. Run once "
                f"without --reuse-jsonl first."
            )
        console.print(
            f"\n[bold]2. Re-using existing calibration set at {output_jsonl}[/bold]"
        )
        dataset = DriftCalibrationDataset.load(output_jsonl)
        drift_count = sum(1 for ex in dataset.examples if ex.is_drift)
        no_drift_count = len(dataset.examples) - drift_count
        console.print(
            f"  Loaded {len(dataset.examples)} examples: "
            f"{drift_count} drift + {no_drift_count} no-drift"
        )
    else:
        console.print(
            "\n[bold]2. Generating 30 calibration examples "
            "(5 sections x 6 variants)[/bold]"
        )
        console.print("  This invokes the LLM ~30 times. Expect $0.50-2.00 in API cost.")
        builder = DriftCalibrationBuilder(config, seed=seed)
        dataset = builder.generate(sections)
        drift_count = sum(1 for ex in dataset.examples if ex.is_drift)
        no_drift_count = len(dataset.examples) - drift_count
        console.print(
            f"  Generated {len(dataset.examples)} examples: "
            f"{drift_count} drift + {no_drift_count} no-drift"
        )
    if len(dataset.examples) != 30:
        raise click.ClickException(
            f"D-CAL-03 expects 30 examples; got {len(dataset.examples)}."
        )

    # 3. Persist JSONL (skipped when re-using)
    if not reuse_jsonl:
        console.print(f"\n[bold]3. Saving calibration set to {output_jsonl}[/bold]")
        dataset.save(output_jsonl)
        console.print(f"  Wrote {output_jsonl} ({output_jsonl.stat().st_size} bytes)")

    if no_derive:
        console.print(
            "\n[yellow]--no-derive set: skipping threshold derivation.[/yellow]"
        )
        console.print(
            "[yellow]Run again WITHOUT --no-derive after human spot-check.[/yellow]"
        )
        return

    # 4. Derive thresholds (detector-side config → eval_config)
    console.print(
        "\n[bold]4. Deriving F1-optimal thresholds "
        "(brute-scan 17 candidates per dim)[/bold]"
    )
    thresholds = derive_thresholds(dataset, eval_config)
    console.print(f"  Thresholds: {thresholds}")

    # 5. Compute F1 self-eval (RA6 / Tier classification) — detector-side
    console.print("\n[bold]5. Computing F1 self-eval (calibration set)[/bold]")
    f1_self = _compute_per_dim_f1(dataset, thresholds, eval_config)
    tier, warned_dims = _classify_f1_tier(
        f1_self,
        target_self=target_self,
        per_dim_floor=per_dim_floor,
        macro_floor=macro_floor,
    )
    is_relaxed = (
        target_self < 0.85 or per_dim_floor < 0.70 or macro_floor < 0.80
    )
    if is_relaxed:
        console.print(
            f"  [yellow]Using relaxed F1 targets: target_self={target_self} "
            f"per_dim_floor={per_dim_floor} macro_floor={macro_floor}[/yellow]"
        )

    f1_table = Table(title="F1 Calibration Self-Eval")
    f1_table.add_column("Dim", style="bold")
    f1_table.add_column("F1", justify="right")
    f1_table.add_column("Status")
    for dim in DRIFT_DIMENSIONS:
        f = f1_self[dim]
        if f >= target_self:
            status = "[green]OK[/green]"
        elif f >= per_dim_floor:
            status = "[yellow]WARN[/yellow]"
        else:
            status = "[red]FAIL[/red]"
        f1_table.add_row(dim, f"{f:.3f}", status)
    macro = f1_self["macro"]
    f1_table.add_row(
        "macro", f"{macro:.3f}",
        "[green]OK[/green]" if macro >= target_self
        else "[yellow]WARN[/yellow]" if macro >= macro_floor
        else "[red]FAIL[/red]",
    )
    f1_table.add_row(
        "Tier", str(tier),
        "[green]PASS[/green]" if tier == 1
        else "[yellow]PASS (borderline)[/yellow]" if tier == 2
        else (
            "[yellow]ACCEPTED (--accept-tier-3)[/yellow]" if accept_tier_3
            else "[red]FAIL — re-roll calibration[/red]"
        ),
    )
    console.print(f1_table)

    if tier == 3:
        console.print(
            f"\n[red]Tier 3 FAIL: macro-F1 {macro:.3f} < {macro_floor} "
            f"or some dim below per-dim floor {per_dim_floor} "
            f"(warned: {warned_dims}).[/red]"
        )
        if accept_tier_3:
            console.print(
                "[yellow]--accept-tier-3 set: persisting thresholds anyway "
                "with _meta.f1_tier=3 so the weak-gate state is auditable. "
                "Plans 18-04/18-05 will wire the gate using these thresholds; "
                "re-calibrate with a stronger judge to tighten in a future phase.[/yellow]"
            )
        else:
            console.print(
                "[red]This indicates same-model bias collapse or noisy "
                "calibration; re-run with a different --seed, switch judge "
                "model, or pass --accept-tier-3 to ship a permissive gate.[/red]"
            )
            raise click.ClickException("Tier 3 F1 failure — calibration unfit for deploy")

    # 6. Persist thresholds JSON with _meta (f1_fresh deferred to Phase 19+)
    thresholds_with_meta = dict(thresholds)
    thresholds_with_meta["_meta"] = {
        "derived_from": str(output_jsonl),
        "f1_self": f1_self,
        "f1_tier": tier,
        "f1_warned_dims": warned_dims,
        "f1_targets": {
            "target_self": target_self,
            "per_dim_floor": per_dim_floor,
            "macro_floor": macro_floor,
            "preset": "v1-pragmatic" if is_relaxed else "research-strict",
        },
        "calibration_timestamp": datetime.now(timezone.utc).isoformat(),
        "generator_model": config.judge_model,
        "judge_model": eval_config.eval_model,
        "judge_api_base": eval_config.api_base,
        "seed": seed,
        "num_examples": len(dataset.examples),
    }
    output_thresholds.parent.mkdir(parents=True, exist_ok=True)
    output_thresholds.write_text(
        json.dumps(thresholds_with_meta, indent=2, sort_keys=True)
    )
    console.print(f"\n  Wrote {output_thresholds} (tier {tier})")
    console.print("\n[bold green]Calibration complete.[/bold green]")
    console.print(
        "  Next: review 10/30 examples in datasets/prompts/drift_calibration.jsonl,"
    )
    console.print("        then commit both artifacts to git.")


if __name__ == "__main__":
    main()
