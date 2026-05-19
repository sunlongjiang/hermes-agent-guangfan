"""Standalone CLI for building the TBLite anchor calibration.

Phase 20 D-13: blocking step before TBLiteBenchmarkGate goes live in
evolve_prompt_sections.py. PITFALL #7 prevention #6: this CLI MUST run
successfully before `python -m evolution.prompts.evolve_prompt_sections
--benchmark=tblite` is invoked for the first time on a fresh
hermes-agent revision (BenchmarkGate's _check_anchor_existence checks
anchor.hermes_agent_commit == git HEAD).

Usage:
    python -m evolution.benchmarks.build_tblite_calibration \\
        [--hermes-repo PATH] [--seed 42] [--runs 3] \\
        [--output-json datasets/prompts/tblite_anchor.json] \\
        [--benchmark-max-cost 50.0] \\
        [--model openrouter/anthropic/claude-opus-4.6] \\
        [--api-base https://openrouter.ai/api/v1]

Outputs `datasets/prompts/tblite_anchor.json` (git-tracked per .gitignore
exception added in Plan 01). On success, prints "Next: commit ..." prompt.

Pre-flight checks (D-10 + D-14 + D-17):
  1. hermes-agent `git status --porcelain` is empty.
  2. ~/.hermes/tmp and ~/.hermes/backups creatable + writable.
  3. Watermark = cost-per-task × num_tasks × num_runs × 3 must fit in
     --benchmark-max-cost minus already_spent.
"""

from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from evolution.core.config import EvolutionConfig
from evolution.core.cost_tracker import CostTracker, CostBudgetExceeded
from evolution.benchmarks.tblite_runner import (
    TBLITE_RUNNER_VERSION,
    TBLiteRunner,
    TBLiteRunResult,
)
from evolution.benchmarks.benchmark_gate import TIERS

console = Console()


# ── HuggingFace dataset revision helper (D-15 + Risk Anchor 5) ─────────────


def _hf_dataset_revision() -> str:
    """D-15 cache fingerprint: read NousResearch/openthoughts-tblite commit sha.

    Risk Anchor 5: graceful fallback to 'unknown_v<runner_version>' on
    any failure (no huggingface_hub, network, auth, rate limit, dataset
    moved). Fallback STILL invalidates cache when TBLITE_RUNNER_VERSION
    bumps. Returning a stable string here is preferable to raising —
    Phase 18 / D-CAL-05 precedent: calibration should NOT block on
    external API hiccups.
    """
    try:
        from huggingface_hub import HfApi
        info = HfApi().dataset_info("NousResearch/openthoughts-tblite")
        sha = getattr(info, "sha", None) or getattr(info, "etag", None)
        if not sha:
            raise RuntimeError("HfApi returned dataset_info without sha")
        return str(sha)
    except Exception as e:
        console.print(
            f"[yellow]HuggingFace dataset_info failed "
            f"({type(e).__name__}: {e}); falling back to "
            f"'unknown_v{TBLITE_RUNNER_VERSION}' as "
            f"dataset_revision_hash. Cache will still invalidate when "
            f"TBLITE_RUNNER_VERSION bumps.[/yellow]"
        )
        return f"unknown_v{TBLITE_RUNNER_VERSION}"


# ── Git Pre-flight helpers (D-10 + D-14) ────────────────────────────────────


def _git_head(hermes_repo: Path) -> str:
    """Return git HEAD sha or '' on error.

    Args:
        hermes_repo: Path to the hermes-agent repository root.

    Returns:
        Full SHA string, or empty string when git fails.
    """
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(hermes_repo),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if res.returncode != 0:
            return ""
        return res.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _check_hermes_clean(hermes_repo: Path) -> None:
    """D-10: refuse to calibrate against a dirty hermes-agent tree.

    Raises click.ClickException (which click.testing.CliRunner converts
    to non-zero exit_code) on any uncommitted change.

    Args:
        hermes_repo: Path to the hermes-agent repository root.
    """
    try:
        res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(hermes_repo),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        raise click.ClickException(
            f"git status check failed: {type(e).__name__}: {e}"
        )
    if res.stdout.strip():
        raise click.ClickException(
            f"hermes-agent has uncommitted changes — refusing to "
            f"calibrate against a dirty tree.\n"
            f"Stash or commit first:\n{res.stdout}"
        )


# ── Per-tier aggregation helper ──────────────────────────────────────────────


def _one_run_per_tier_pass_rate(
    run_result: TBLiteRunResult,
) -> dict[str, float]:
    """Compute per-tier pass rate from one TBLite run.

    Mirrors TBLiteBenchmarkGate._one_run_per_tier_pass_rate but kept LOCAL
    to avoid build_tblite_calibration depending on benchmark_gate's full
    Virtual Prompt Overlay machinery.

    Args:
        run_result: Result from one TBLiteRunner.run() call.

    Returns:
        Dict mapping tier name to float pass rate [0.0, 1.0]. Missing tiers
        (no tasks) return 0.0.
    """
    by_tier: dict[str, list[bool]] = {t: [] for t in TIERS}
    for task in run_result.per_task:
        if task.get("infra_fail"):
            continue
        tier = str(task.get("category", "")).strip().lower()
        if tier in by_tier:
            by_tier[tier].append(bool(task.get("passed", False)))
    return {
        t: (sum(v) / len(v) if v else 0.0)
        for t, v in by_tier.items()
    }


# ── Click CLI main ───────────────────────────────────────────────────────────


@click.command()
@click.option(
    "--hermes-repo",
    default=None,
    type=click.Path(),
    help="Override HERMES_AGENT_REPO. Defaults to env / ~/.hermes/hermes-agent.",
)
@click.option(
    "--seed",
    default=42,
    type=int,
    help="Random seed persisted in anchor (D-CAL-01).",
)
@click.option(
    "--runs",
    default=None,
    type=int,
    help=(
        "TBLite invocations per calibration run (D-03 median-of-N). "
        "Defaults to config.benchmark_runs (3)."
    ),
)
@click.option(
    "--output-json",
    default=Path("datasets/prompts/tblite_anchor.json"),
    type=click.Path(path_type=Path),
    help=(
        "Output path for anchor JSON. Default is git-tracked per "
        ".gitignore exception added in Plan 01."
    ),
)
@click.option(
    "--benchmark-max-cost",
    default=None,
    type=float,
    help=(
        "Phase 20 D-16 dual-track budget for this calibration run "
        "(USD). Defaults to config.benchmark_max_cost_usd (50.0)."
    ),
)
@click.option(
    "--model",
    default=None,
    help="Override calibration_model field (e.g. openai/gpt-4.1).",
)
@click.option(
    "--api-base",
    default=None,
    help="Override API base URL.",
)
@click.option(
    "--accept-stale-anchor",
    is_flag=True,
    default=False,
    help=(
        "[unsafe] Allow writing the anchor even if hermes-agent has "
        "uncommitted changes. Default is to refuse (D-10). Only use "
        "for debug runs with --output-json /tmp/anchor.json."
    ),
)
def main(
    hermes_repo,
    seed,
    runs,
    output_json,
    benchmark_max_cost,
    model,
    api_base,
    accept_stale_anchor,
):
    """Build TBLite anchor + persist datasets/prompts/tblite_anchor.json."""
    console.print("[bold]Phase 20: TBLite anchor calibration[/bold]\n")

    overrides: dict = {}
    if hermes_repo:
        overrides["hermes_repo"] = hermes_repo
    if model:
        overrides["model"] = model
    if api_base:
        overrides["api_base"] = api_base
    if benchmark_max_cost is not None:
        overrides["benchmark_max_cost_usd"] = benchmark_max_cost
    if runs is not None:
        overrides["benchmark_runs"] = runs
    config = EvolutionConfig.load(**overrides)
    n_runs = int(config.benchmark_runs)
    budget = float(config.benchmark_max_cost_usd)

    # ── 1. Pre-flight ─────────────────────────────────────────────
    console.print("[bold]1. Pre-flight checks[/bold]")
    hermes_path = Path(config.hermes_agent_path)
    if not hermes_path.exists():
        raise click.ClickException(
            f"hermes-agent path not found: {hermes_path}. "
            f"Set HERMES_AGENT_REPO or --hermes-repo."
        )
    prompt_builder = hermes_path / "agent" / "prompt_builder.py"
    if not prompt_builder.exists():
        raise click.ClickException(
            f"prompt_builder.py not found at {prompt_builder}. "
            f"Phase 7 anchor — confirm hermes-agent revision."
        )
    if not accept_stale_anchor:
        _check_hermes_clean(hermes_path)
    else:
        console.print(
            "[yellow]--accept-stale-anchor: skipping git-dirty check; "
            "anchor commit_id will reflect HEAD only.[/yellow]"
        )
    current_commit = _git_head(hermes_path)
    if not current_commit:
        raise click.ClickException(
            f"Could not read git HEAD in {hermes_path}. "
            f"Is the repo initialized?"
        )
    for p in (
        Path.home() / ".hermes" / "tmp",
        Path.home() / ".hermes" / "backups",
    ):
        try:
            p.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise click.ClickException(f"Cannot create {p}: {e}")
        if not os.access(p, os.W_OK):
            raise click.ClickException(f"Not writable: {p}")
    console.print(f"  hermes-agent commit: {current_commit[:12]}")

    # ── 2. Load stratified subset (placed by Plan 01) ─────────────
    console.print("\n[bold]2. Loading stratified subset[/bold]")
    stratified_path = Path("datasets/prompts/tblite_stratified_subset.json")
    if not stratified_path.exists():
        raise click.ClickException(
            f"{stratified_path} not found. Plan 01 should have placed "
            f"a placeholder; run that plan first."
        )
    stratified = json.loads(stratified_path.read_text())
    task_filter_items = stratified.get("task_filter", [])
    if not task_filter_items:
        raise click.ClickException(
            f"{stratified_path} has empty task_filter."
        )
    # W-7 schema: task_filter items are {name, tier} dicts. Extract
    # names for TBLiteRunner.run (which still consumes list[str]).
    # Tolerate both schemas during transition: object form (W-7) AND
    # legacy flat-string form (pre-W-7) — strings pass through unchanged.
    task_names: list[str] = []
    for item in task_filter_items:
        if isinstance(item, dict) and "name" in item:
            task_names.append(item["name"])
        elif isinstance(item, str):
            task_names.append(item)
        else:
            raise click.ClickException(
                f"{stratified_path} task_filter item has unexpected "
                f"shape: {item!r} (expected str or {{name, tier}})"
            )
    num_tasks = len(task_names)
    console.print(
        f"  {num_tasks} tasks across "
        f"{stratified.get('per_tier_counts', {})}"
    )
    if stratified.get("_meta", {}).get("placeholder"):
        console.print(
            "[yellow]  Wave-1 placeholder task names detected — "
            "these are not real TBLite tasks. The calibration run "
            "below will likely fail at the subprocess level. Run "
            "this CLI again after Plan 05 generates real task "
            "names.[/yellow]"
        )

    # ── 3. Pre-flight Watermark (D-17) ────────────────────────────
    console.print("\n[bold]3. Pre-flight Watermark[/bold]")
    cost_per_task = float(config.tblite_estimated_cost_per_task_usd)
    estimated = cost_per_task * num_tasks * n_runs
    watermark = estimated * 3
    console.print(
        f"  estimated_cost = ${cost_per_task:.2f}/task × "
        f"{num_tasks} tasks × {n_runs} runs = ${estimated:.2f}"
    )
    console.print(
        f"  watermark = ${watermark:.2f}; "
        f"available_budget = ${budget:.2f}"
    )
    if watermark > budget:
        raise click.ClickException(
            f"Insufficient benchmark budget: watermark ${watermark:.2f} "
            f"exceeds --benchmark-max-cost ${budget:.2f}. Either raise "
            f"the cap or reduce --runs."
        )

    # ── 4. HuggingFace dataset revision (D-15) ────────────────────
    console.print("\n[bold]4. HuggingFace dataset_revision_hash[/bold]")
    dataset_revision_hash = _hf_dataset_revision()
    console.print(f"  dataset_revision_hash = {dataset_revision_hash[:12]}")

    # ── 5. Run TBLite N times ──────────────────────────────────────
    console.print(
        f"\n[bold]5. Running TBLite × {n_runs} (stratified subset)[/bold]"
    )
    runner = TBLiteRunner(config)
    tracker = CostTracker(max_usd=budget)
    per_run_per_tier: list[dict[str, float]] = []
    # WR-04 (2026-05-19): track per-tier valid-sample counts across runs
    # so we can fail loudly when a tier produces 0 valid samples instead
    # of silently anchoring at 0.0 (which makes the gate's
    # max(0.0, 0.0) - 1.96 * stdev threshold permanently negative,
    # so candidate pass rates can never breach the empty tier).
    per_tier_observed: dict[str, int] = {t: 0 for t in TIERS}
    runtime_total = 0.0
    try:
        with tracker:
            for r in range(n_runs):
                console.print(f"\n[bold]  Run {r + 1}/{n_runs}[/bold]")
                run_out = (
                    Path("output") / "prompts" / "_calibration"
                    / current_commit[:12] / f"run_{r}"
                )
                run_out.mkdir(parents=True, exist_ok=True)
                run_result = runner.run(
                    task_filter=list(task_names),
                    output_dir=run_out,
                )
                if run_result.status != "ok":
                    # WR-02 (2026-05-19): stderr_tail is already the
                    # LAST 20 stderr lines; slicing [:5] would yield the
                    # OLDEST 5 — exactly the opposite of "show me the
                    # most recent error messages" diagnostic intent.
                    raise click.ClickException(
                        f"TBLite run {r + 1} status={run_result.status} "
                        f"(exit_code={run_result.exit_code}). "
                        f"stderr tail: {run_result.stderr_tail[-5:]}"
                    )
                per_run_per_tier.append(
                    _one_run_per_tier_pass_rate(run_result)
                )
                # WR-04: count valid samples per tier (excludes infra_fail
                # rows; mirrors _one_run_per_tier_pass_rate's filter).
                for task in run_result.per_task:
                    if task.get("infra_fail"):
                        continue
                    tier = str(task.get("category", "")).strip().lower()
                    if tier in per_tier_observed:
                        per_tier_observed[tier] += 1
                runtime_total += run_result.subprocess_runtime_seconds
                if tracker.exceeded():
                    raise CostBudgetExceeded(
                        tracker.spent_usd, tracker.max_usd
                    )
    except CostBudgetExceeded as e:
        raise click.ClickException(
            f"Calibration aborted on budget cap: {e}"
        )

    # ── 6. Aggregate per-tier mean+stdev ──────────────────────────
    # WR-04: detect zero-sample tiers BEFORE writing the anchor. A
    # mistyped per_tier_counts key (e.g. 'mediun' instead of 'medium')
    # would otherwise produce a passing gate forever for the silently
    # dropped tier.
    empty_tiers = [t for t in TIERS if per_tier_observed[t] == 0]
    if empty_tiers:
        raise click.ClickException(
            f"Tier(s) {sorted(empty_tiers)} produced 0 valid samples "
            f"across {n_runs} runs. Check per_tier_counts and the "
            f"'tier' field of each item in {stratified_path} — a "
            f"mis-spelled tier name silently disappears here. Observed "
            f"counts: {per_tier_observed}."
        )

    anchor_per_tier: dict[str, dict] = {}
    for tier in TIERS:
        scores = [run.get(tier, 0.0) for run in per_run_per_tier]
        anchor_per_tier[tier] = {
            "mean": round(statistics.mean(scores), 4) if scores else 0.0,
            "stdev": (
                round(statistics.stdev(scores), 4)
                if len(scores) > 1 else 0.0
            ),
            "n": n_runs,
            "scores": [round(s, 4) for s in scores],
        }

    # ── 7. Rich Table summary ──────────────────────────────────────
    console.print("\n[bold]6. Anchor summary[/bold]")
    table = Table(title="TBLite Anchor Calibration")
    table.add_column("Tier", style="bold")
    table.add_column("N tasks", justify="right")
    for i in range(n_runs):
        table.add_column(f"Run {i + 1}", justify="right")
    table.add_column("Mean", justify="right")
    table.add_column("Stdev", justify="right")
    for tier in TIERS:
        n_tasks_for_tier = stratified.get("per_tier_counts", {}).get(tier, 0)
        row = [tier, str(n_tasks_for_tier)]
        for s in anchor_per_tier[tier]["scores"]:
            row.append(f"{s:.3f}")
        row.extend([
            f"{anchor_per_tier[tier]['mean']:.3f}",
            f"{anchor_per_tier[tier]['stdev']:.3f}",
        ])
        table.add_row(*row)
    console.print(table)

    # ── 8. Measured per-task cost ──────────────────────────────────
    measured_cost_per_task = (
        tracker.spent_usd / (num_tasks * n_runs)
        if num_tasks * n_runs > 0 else cost_per_task
    )

    # ── 9. Persist anchor with metadata (D-CAL-01) ────────────────
    anchor = {
        "anchor_per_tier": anchor_per_tier,
        "calibration_model": (
            config.optimizer_model if not model else model
        ),
        "calibration_timestamp": datetime.now(timezone.utc).isoformat(),
        "dataset_revision_hash": dataset_revision_hash,
        "hermes_agent_commit": current_commit,
        "stratified_subset_seed": int(stratified.get("seed", seed)),
        "subprocess_runtime_seconds_total": round(runtime_total, 2),
        "tblite_estimated_cost_per_task_usd": round(
            measured_cost_per_task, 4
        ),
        "tblite_runner_version": TBLITE_RUNNER_VERSION,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        json.dumps(anchor, indent=2, sort_keys=True)
    )
    console.print(
        f"\n  Wrote {output_json} "
        f"(cost ${tracker.spent_usd:.4f}, measured "
        f"${measured_cost_per_task:.4f}/task)"
    )
    console.print(
        "\n[bold green]Anchor calibration complete.[/bold green]"
    )
    console.print(
        f"  Next: commit {output_json} to git so other machines "
        f"reproduce this baseline."
    )


if __name__ == "__main__":
    main()
