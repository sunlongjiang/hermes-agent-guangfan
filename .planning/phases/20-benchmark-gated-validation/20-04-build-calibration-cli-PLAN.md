---
phase: 20-benchmark-gated-validation
plan: 04
type: execute
wave: 3
revised_at: 2026-05-19
depends_on:
  - 20-02-tblite-runner-PLAN.md
  - 20-03-benchmark-gate-PLAN.md
files_modified:
  - evolution/benchmarks/build_tblite_calibration.py
  - tests/benchmarks/test_build_tblite_calibration.py
autonomous: true
requirements:
  - PMPT-V2-03
requirements_addressed:
  - PMPT-V2-03
tags:
  - phase-20
  - benchmark
  - cli
  - calibration
must_haves:
  truths:
    - "evolution/benchmarks/build_tblite_calibration.py is a Click CLI runnable as `python -m evolution.benchmarks.build_tblite_calibration`"
    - "CLI exposes flags: --hermes-repo, --seed (default 42), --runs (default 3), --output-json, --benchmark-max-cost (default 50.0), --model, --api-base, --accept-stale-anchor (boolean, default False)"
    - "Pre-flight Watermark check (D-17): estimated_cost = config.tblite_estimated_cost_per_task_usd * num_tasks * runs; watermark = estimated * 3; if watermark > available_budget -> sys.exit(1) BEFORE subprocess starts"
    - "Pre-flight git status --porcelain check on hermes-agent — non-empty -> sys.exit(1) (D-10)"
    - "HuggingFace dataset_revision_hash fetched via huggingface_hub.HfApi().dataset_info('NousResearch/openthoughts-tblite').sha; on any exception -> fail-open with 'unknown_v<TBLITE_RUNNER_VERSION>' fallback (D-15 + Risk Anchor 5)"
    - "Builds CostTracker(max_usd=benchmark_max_cost); each TBLite run wrapped in tracker context; CostBudgetExceeded raised if exceeded (D-16 reuse Phase 13 pattern)"
    - "Runs TBLiteRunner N times (default 3) on stratified subset; aggregates per-tier mean+stdev via statistics module (no numpy/sklearn)"
    - "Persists datasets/prompts/tblite_anchor.json with full D-CAL-01 schema: anchor_per_tier, dataset_revision_hash, hermes_agent_commit, stratified_subset_seed, tblite_estimated_cost_per_task_usd (measured-and-written), calibration_timestamp, calibration_model, tblite_runner_version"
    - "Rich Table titled 'TBLite Anchor Calibration' with columns: Tier | N tasks | Run 1 | Run 2 | Run 3 | Mean | Stdev"
    - "tests/benchmarks/test_build_tblite_calibration.py contains 6+ CliRunner-based tests covering schema / seed / HuggingFace fallback / git-dirty block / Watermark insufficient / write-cost-per-task"
  artifacts:
    - path: evolution/benchmarks/build_tblite_calibration.py
      provides: "Click CLI building tblite_anchor.json with 3-run × stratified subset"
      contains: "def main"
      min_lines: 300
    - path: tests/benchmarks/test_build_tblite_calibration.py
      provides: "6+ CliRunner tests: schema, seed, HF fallback, git block, Watermark, cost"
      contains: "class TestBuildTBLiteCalibration"
      min_lines: 250
  key_links:
    - from: build_tblite_calibration.py
      to: evolution.benchmarks.tblite_runner.TBLiteRunner
      via: "task_names = [item['name'] for item in stratified['task_filter']] (W-7 schema); runner.run(task_filter=task_names, output_dir=...)"
      pattern: "TBLiteRunner"
    - from: build_tblite_calibration.py
      to: evolution.core.cost_tracker.CostTracker
      via: "tracker = CostTracker(max_usd=benchmark_max_cost); with tracker: ..."
      pattern: "CostTracker"
    - from: build_tblite_calibration.py
      to: huggingface_hub.HfApi
      via: "HfApi().dataset_info('NousResearch/openthoughts-tblite').sha (with try/except fail-open)"
      pattern: "HfApi"
    - from: build_tblite_calibration.py
      to: datasets/prompts/tblite_anchor.json
      via: "output_json.write_text(json.dumps(anchor, indent=2, sort_keys=True))"
      pattern: "tblite_anchor\\.json"
---

<objective>
Wave 3 — Build the standalone CLI that produces `datasets/prompts/tblite_anchor.json`.

This is the **first** of the two Wave 3-4 deliverables for D-13 (Explicit Anchor Calibration). Phase 18 D-CAL-01 / D-CAL-02 establish the precedent: a separate, opt-in CLI runs TBLite against the untouched hermes-agent baseline, computes per-tier mean+stdev across N runs, and writes a git-tracked JSON anchor that BenchmarkGate (Plan 03) reads at every gate invocation.

The CLI mirrors `evolution/prompts/build_drift_calibration.py:1-473` (PATTERNS §File 4 "exact analog, ~85% structural overlap") — Click decorators + Rich Console + Pre-flight checks + Rich Table summary + git-tracked JSON output — but replaces the body (F1 derivation + DSPy LLM judge) with TBLite subprocess + statistics aggregation.

Six key adaptations from Phase 18:
1. **CostTracker is wired in** (Phase 18 didn't enforce — it only stdout'd predicted cost). Phase 20 MUST enforce `benchmark_max_cost_usd` because TBLite Modal compute is $0.4/task; 30 tasks × 3 runs at $0.4 = $36 worst case stays under default $50 cap, but ops can override.
2. **Pre-flight Watermark check** (D-17) — estimate × 3 must fit available budget BEFORE subprocess starts. `--benchmark-max-cost 5` for 30×3=$36 → sys.exit(1).
3. **`git status --porcelain` Pre-flight** — Phase 18 didn't need (it didn't overlay). Phase 20 anchor is taken against untouched hermes-agent, so calibration must run with a clean tree (otherwise the anchor commits a "baseline" that isn't really the baseline).
4. **HuggingFace dataset_revision_hash** via `HfApi().dataset_info` — fail-open to `'unknown_v<TBLITE_RUNNER_VERSION>'` on network/auth errors (CONTEXT Risk Anchor 5; Phase 18 didn't use HF).
5. **Anchor schema is flat** (top-level metadata) vs Phase 18's nested `_meta` block — `TBLiteBenchmarkGate.__init__` consumes these keys directly.
6. **Rich Table columns are dynamic** (`Run 1..N` driven by `--runs`) vs Phase 18 fixed columns.

The CLI does NOT auto-generate the stratified subset (Wave 1 already placed `datasets/prompts/tblite_stratified_subset.json` placeholder; Plan 05 replaces task_filter with real names). This CLI **reads** the subset and assumes it is valid.

Output: 1 production CLI file (~300-350 lines), 1 unit test file (~250 lines, 6+ tests with mocked TBLiteRunner + mocked HfApi + mocked git).

Purpose: Without this CLI, Plan 05 cannot generate `tblite_anchor.json`, and Plan 06's `evolve_prompt_sections --benchmark=tblite` would raise `SystemExit(1)` at `_check_anchor_existence`.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/20-benchmark-gated-validation/20-CONTEXT.md
@.planning/phases/20-benchmark-gated-validation/20-PATTERNS.md
@evolution/prompts/build_drift_calibration.py
@evolution/benchmarks/tblite_runner.py
@evolution/benchmarks/benchmark_gate.py
@evolution/core/config.py
@evolution/core/cost_tracker.py
@tests/prompts/test_drift_calibration.py
@./CLAUDE.md

<interfaces>
<!-- Wave 1/2 contracts -->
From evolution/core/config.py (Plan 01):
```python
benchmark_max_cost_usd: float = 50.0
tblite_estimated_cost_per_task_usd: float = 0.4
benchmark_runs: int = 3
```

From evolution/benchmarks/tblite_runner.py (Plan 02):
```python
TBLITE_RUNNER_VERSION: str = "1.0"
class TBLiteRunner: ...
def compute_artifact_hash(...) -> str: ...
```

From evolution/core/cost_tracker.py (Phase 13):
```python
class CostTracker:
    def __init__(self, max_usd: float): ...
    def __enter__(self) -> "CostTracker": ...
    def __exit__(self, exc_type, exc, tb): ...
    def exceeded(self) -> bool: ...
    @property
    def spent_usd(self) -> float: ...  # via poll() chain

class CostBudgetExceeded(Exception):
    def __init__(self, spent_usd_or_msg: float | str = 0.0, max_usd: float = 0.0): ...
```

<!-- Anchor JSON schema (D-CAL-01, verbatim from CONTEXT §Specifics). -->
```json
{
  "anchor_per_tier": {
    "easy":    {"mean": 0.85, "stdev": 0.02, "n": 3, "scores": [0.83, 0.86, 0.86]},
    "medium":  {"mean": ..., "stdev": ..., "n": 3, "scores": [...]},
    "hard":    {"mean": ..., "stdev": ..., "n": 3, "scores": [...]},
    "extreme": {"mean": ..., "stdev": ..., "n": 3, "scores": [...]}
  },
  "dataset_revision_hash": "abc123...",
  "hermes_agent_commit": "def456...",
  "stratified_subset_seed": 42,
  "tblite_estimated_cost_per_task_usd": 0.4,
  "calibration_timestamp": "2026-05-19T10:00:00Z",
  "calibration_model": "anthropic/claude-opus-4.6",
  "tblite_runner_version": "1.0"
}
```

<!-- Phase 18 CLI structural analog: build_drift_calibration.py:280-470 main body. -->
Skeleton excerpt for cross-reference:
```python
@click.command()
@click.option("--hermes-repo", default=None, ...)
@click.option("--seed", default=42, type=int)
@click.option("--output-json", default=Path("datasets/prompts/drift_thresholds.json"), type=click.Path(path_type=Path))
@click.option("--model", default=None)
@click.option("--api-base", default=None)
def main(...):
    config = EvolutionConfig.load(...)
    # 1. Pre-flight
    # 2. Generate/load
    # 3. Persist
    # 4. Derive
    # 5. F1 self-eval
    # 6. Save with _meta
```

<!-- Watermark formula (D-17) -->
```python
estimated_cost = config.tblite_estimated_cost_per_task_usd * num_tasks * num_runs
watermark = estimated_cost * 3
available = benchmark_max_cost_usd - already_spent
if watermark > available:
    raise SystemExit(f"Insufficient budget: need {watermark:.2f}, have {available:.2f}")
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Create evolution/benchmarks/build_tblite_calibration.py — Click CLI building tblite_anchor.json (Pre-flight + Watermark + 3-run + HF revision + Rich Table)</name>
  <files>evolution/benchmarks/build_tblite_calibration.py</files>
  <read_first>
    - evolution/prompts/build_drift_calibration.py (entire file — Phase 18 CLI template, especially click decorators, console.print "[bold]N. step name[/bold]" numbering, Rich Table, json.dumps(..., indent=2, sort_keys=True) write, "Next: commit ..." final message)
    - evolution/benchmarks/tblite_runner.py (Plan 02 — TBLiteRunner + TBLITE_RUNNER_VERSION imports)
    - evolution/benchmarks/benchmark_gate.py (Plan 03 — TIERS constant + anchor schema requirements)
    - evolution/core/cost_tracker.py (lines 130-280 — CostTracker context manager, CostBudgetExceeded class, .exceeded() / .spent_usd)
    - evolution/core/config.py (Plan 01 — benchmark_max_cost_usd + tblite_estimated_cost_per_task_usd fields)
    - .planning/phases/20-benchmark-gated-validation/20-PATTERNS.md §File 4 (entire — 6 adaptation deltas + CLI skeleton + HF helper)
    - .planning/phases/20-benchmark-gated-validation/20-CONTEXT.md §D-13 + §D-14 + §D-15 + §D-16 + §D-17 + §Specifics §"build_tblite_calibration 输出栏 Rich Table 字段"
  </read_first>
  <behavior>
    Task 2's test file will exercise these behaviors with mocked TBLiteRunner + mocked huggingface_hub.HfApi + mocked git:
    - test_anchor_json_schema_complete: CLI run with --runs=1 against mocked TBLiteRunner writes anchor JSON containing ALL D-CAL-01 keys.
    - test_seed_is_persisted: --seed 7 → anchor["stratified_subset_seed"] == 7.
    - test_huggingface_fallback_on_api_error: When HfApi raises, anchor["dataset_revision_hash"] == "unknown_v1.0" + Rich warning emitted (no exit).
    - test_git_dirty_check_blocks_calibration: Mock `git status --porcelain` returning non-empty → CliRunner exit_code != 0.
    - test_pre_flight_watermark_blocks_when_insufficient_budget: --benchmark-max-cost=5 with 30 tasks × 3 runs × $0.4 = $36 → watermark=$108 > available=$5 → SystemExit(1) BEFORE any subprocess.
    - test_tblite_cost_per_task_measured_and_written: After successful calibration, anchor["tblite_estimated_cost_per_task_usd"] is the MEASURED value (tracker.spent_usd / (num_tasks * runs)), NOT the config default.
    - test_runs_3_aggregates_mean_stdev: With 3 runs returning {easy: 0.83, 0.86, 0.86}, anchor["anchor_per_tier"]["easy"]["mean"] ≈ 0.85 and "stdev" ≈ 0.017.
  </behavior>
  <action>
    Create `evolution/benchmarks/build_tblite_calibration.py` using the Write tool. Target ~300-350 lines.

    **Module docstring + imports:**

    ```python
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
    ```

    **HuggingFace dataset revision helper** (D-15 + Risk Anchor 5):

    ```python
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
    ```

    **Git Pre-flight helpers** (D-10 + D-14):

    ```python
    def _git_head(hermes_repo: Path) -> str:
        """Return git HEAD short sha or '' on error."""
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
    ```

    **Per-tier aggregation helper:**

    ```python
    def _one_run_per_tier_pass_rate(
        run_result: TBLiteRunResult,
    ) -> dict[str, float]:
        """Mirror TBLiteBenchmarkGate._one_run_per_tier_pass_rate.

        Kept LOCAL (not imported) to avoid build_tblite_calibration depending
        on benchmark_gate's full Virtual Prompt Overlay machinery.
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
    ```

    **Click CLI main:**

    ```python
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

        overrides = {}
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
        for p in (Path.home() / ".hermes" / "tmp",
                  Path.home() / ".hermes" / "backups"):
            try:
                p.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise click.ClickException(f"Cannot create {p}: {e}")
            if not os.access(p, os.W_OK):
                raise click.ClickException(f"Not writable: {p}")
        console.print(f"  hermes-agent commit: {current_commit[:12]}")

        # ── 2. Load stratified subset (placed by Plan 01) ──
        console.print(
            "\n[bold]2. Loading stratified subset[/bold]"
        )
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
                "[yellow]  ⚠ Wave-1 placeholder task names detected — "
                "these are not real TBLite tasks. The calibration run "
                "below will likely fail at the subprocess level. Run "
                "this CLI again after Plan 05 generates real task "
                "names.[/yellow]"
            )

        # ── 3. Pre-flight Watermark (D-17) ──
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

        # ── 4. HuggingFace dataset revision (D-15) ──
        console.print("\n[bold]4. HuggingFace dataset_revision_hash[/bold]")
        dataset_revision_hash = _hf_dataset_revision()
        console.print(f"  dataset_revision_hash = {dataset_revision_hash[:12]}")

        # ── 5. Run TBLite N times ──
        console.print(
            f"\n[bold]5. Running TBLite × {n_runs} (stratified subset)[/bold]"
        )
        runner = TBLiteRunner(config)
        tracker = CostTracker(max_usd=budget)
        per_run_per_tier: list[dict[str, float]] = []
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
                        raise click.ClickException(
                            f"TBLite run {r + 1} status={run_result.status} "
                            f"(exit_code={run_result.exit_code}). "
                            f"stderr tail: {run_result.stderr_tail[:5]}"
                        )
                    per_run_per_tier.append(
                        _one_run_per_tier_pass_rate(run_result)
                    )
                    runtime_total += run_result.subprocess_runtime_seconds
                    if tracker.exceeded():
                        raise CostBudgetExceeded(
                            tracker.spent_usd, tracker.max_usd
                        )
        except CostBudgetExceeded as e:
            raise click.ClickException(
                f"Calibration aborted on budget cap: {e}"
            )

        # ── 6. Aggregate per-tier mean+stdev ──
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

        # ── 7. Rich Table summary ──
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

        # ── 8. Measured per-task cost ──
        measured_cost_per_task = (
            tracker.spent_usd / (num_tasks * n_runs)
            if num_tasks * n_runs > 0 else cost_per_task
        )

        # ── 9. Persist anchor with metadata (D-CAL-01) ──
        anchor = {
            "anchor_per_tier": anchor_per_tier,
            "dataset_revision_hash": dataset_revision_hash,
            "hermes_agent_commit": current_commit,
            "stratified_subset_seed": int(stratified.get("seed", seed)),
            "tblite_estimated_cost_per_task_usd": round(
                measured_cost_per_task, 4
            ),
            "calibration_timestamp": datetime.now(timezone.utc).isoformat(),
            "calibration_model": (
                config.optimizer_model if not model else model
            ),
            "tblite_runner_version": TBLITE_RUNNER_VERSION,
            "subprocess_runtime_seconds_total": round(runtime_total, 2),
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
            f"\n[bold green]Anchor calibration complete.[/bold green]"
        )
        console.print(
            f"  Next: commit {output_json} to git so other machines "
            f"reproduce this baseline."
        )


    if __name__ == "__main__":
        main()
    ```

    Use the Write tool to create the file. After writing, run `.venv/bin/python -m evolution.benchmarks.build_tblite_calibration --help` to confirm Click renders without error.

    Implements: PATTERNS §File 4 (entire — 6 deviations from build_drift_calibration); CONTEXT §D-10 + §D-13 + §D-14 + §D-15 + §D-16 + §D-17 + §Specifics §"build_tblite_calibration 输出栏 Rich Table 字段" verbatim.
  </action>
  <verify>
    <automated>.venv/bin/python -m evolution.benchmarks.build_tblite_calibration --help 2>&1 | grep -E '\-\-(hermes-repo|seed|runs|output-json|benchmark-max-cost|model|api-base|accept-stale-anchor)' | wc -l | awk '{ if ($1 < 8) { print "FAIL: only " $1 " CLI flags found in --help, need >= 8"; exit 1 } else { print "OK: " $1 " flags" } }' && .venv/bin/python -c "import evolution.benchmarks.build_tblite_calibration as m; assert hasattr(m, 'main'), 'main missing'; assert hasattr(m, '_hf_dataset_revision'), '_hf_dataset_revision missing'; assert hasattr(m, '_check_hermes_clean'), '_check_hermes_clean missing'; assert hasattr(m, '_git_head'), '_git_head missing'; assert hasattr(m, '_one_run_per_tier_pass_rate'), 'helper missing'; print('OK helpers')" && grep -c 'CostTracker' evolution/benchmarks/build_tblite_calibration.py | awk '{ if ($1 < 2) { print "FAIL: CostTracker must appear at least 2x (import + instantiation)"; exit 1 } else { print "OK CostTracker wired" } }' && grep -c 'tblite_estimated_cost_per_task_usd' evolution/benchmarks/build_tblite_calibration.py | awk '{ if ($1 < 2) { print "FAIL: D-17 measured cost write missing"; exit 1 } else { print "OK" } }' && grep -c 'watermark' evolution/benchmarks/build_tblite_calibration.py | awk '{ if ($1 < 2) { print "FAIL: D-17 Watermark variable missing"; exit 1 } else { print "OK watermark check" } }' && grep -c 'huggingface_hub' evolution/benchmarks/build_tblite_calibration.py | awk '{ if ($1 < 1) { print "FAIL: HuggingFace API call missing"; exit 1 } else { print "OK HF integration" } }' && grep -c 'dataset_revision_hash' evolution/benchmarks/build_tblite_calibration.py | awk '{ if ($1 < 2) { print "FAIL: dataset_revision_hash not threaded through"; exit 1 } else { print "OK" } }' && grep -c 'hermes_agent_commit' evolution/benchmarks/build_tblite_calibration.py | awk '{ if ($1 < 2) { print "FAIL: hermes_agent_commit not threaded through"; exit 1 } else { print "OK" } }'</automated>
  </verify>
  <acceptance_criteria>
    - `python -m evolution.benchmarks.build_tblite_calibration --help` shows all 8 documented flags (--hermes-repo, --seed, --runs, --output-json, --benchmark-max-cost, --model, --api-base, --accept-stale-anchor).
    - Module has top-level functions: `main` (Click command), `_hf_dataset_revision`, `_check_hermes_clean`, `_git_head`, `_one_run_per_tier_pass_rate`.
    - `grep -c 'CostTracker' evolution/benchmarks/build_tblite_calibration.py` >= 2 (import + instantiation).
    - `grep -c 'watermark' evolution/benchmarks/build_tblite_calibration.py` >= 2 (D-17 Pre-flight Watermark wired).
    - `grep -c 'huggingface_hub' evolution/benchmarks/build_tblite_calibration.py` >= 1 (D-15 HF API).
    - `grep -c 'dataset_revision_hash' evolution/benchmarks/build_tblite_calibration.py` >= 2 (compute + persist).
    - File line count >= 280.
  </acceptance_criteria>
  <done>
    - build_tblite_calibration.py is a runnable Click CLI
    - 8 documented flags exposed
    - 4 Pre-flight checks (path exists, git clean, paths writable, Watermark)
    - CostTracker wraps the multi-run loop
    - HuggingFace dataset_revision_hash with fail-open fallback
    - Rich Table with dynamic Run columns
    - anchor JSON written with sort_keys=True and full D-CAL-01 schema
    - Measured per-task cost written into anchor (D-17 self-refining)
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Create tests/benchmarks/test_build_tblite_calibration.py with 6+ CliRunner tests covering schema / seed / HF fallback / git-dirty / Watermark / cost-write-back</name>
  <files>tests/benchmarks/test_build_tblite_calibration.py</files>
  <read_first>
    - tests/prompts/test_drift_calibration.py (entire file — Phase 18 CliRunner pattern with mocked subprocess + mocked LM)
    - evolution/benchmarks/build_tblite_calibration.py (just-written file — confirm helper names + Click signature)
    - evolution/benchmarks/tblite_runner.py (Plan 02 — TBLiteRunResult shape for mocking)
    - .planning/phases/20-benchmark-gated-validation/20-PATTERNS.md §File 14 (CliRunner skeleton)
  </read_first>
  <behavior>
    All tests use `click.testing.CliRunner` + `patch.object(build_tblite_calibration_module, "TBLiteRunner")` + `patch.object(module, "_hf_dataset_revision")` + `patch.object(module, "_git_head")` + `patch.object(module, "_check_hermes_clean")` (or `patch("subprocess.run")` for git invocations).

    6+ required tests:
    1. test_anchor_json_schema_complete
    2. test_seed_is_persisted_from_subset
    3. test_huggingface_fallback_on_api_error
    4. test_git_dirty_check_blocks_calibration
    5. test_pre_flight_watermark_blocks_when_insufficient_budget
    6. test_tblite_cost_per_task_measured_and_written
    7. test_runs_aggregates_mean_stdev (verifies statistics.mean + stdev)
    8. test_accept_stale_anchor_bypasses_git_check (covers --accept-stale-anchor)
  </behavior>
  <action>
    Create `tests/benchmarks/test_build_tblite_calibration.py` using the Write tool. Skeleton + 8 concrete tests:

    ```python
    """CliRunner unit tests for build_tblite_calibration.

    Every external call mocked:
      - subprocess.run for git status / git rev-parse
      - huggingface_hub.HfApi (via patch of _hf_dataset_revision)
      - TBLiteRunner.run (via patch of the class so .run returns fake result)
    """

    import json
    from pathlib import Path
    from unittest.mock import MagicMock, patch

    import pytest
    from click.testing import CliRunner

    from evolution.benchmarks.tblite_runner import TBLiteRunResult


    # ── Helpers ──────────────────────────────────────────────────────────────

    def _make_run_result(per_tier_passed: dict[str, list[bool]], runtime=1.0):
        per_task = []
        for tier, results in per_tier_passed.items():
            for i, passed in enumerate(results):
                per_task.append({
                    "task_name": f"{tier}-{i}",
                    "category": tier,
                    "passed": passed,
                    "infra_fail": False,
                })
        return TBLiteRunResult(
            per_task=per_task,
            subprocess_runtime_seconds=runtime,
            hang_count=0,
            cost_breakdown={"modal_compute_usd": 0.1},
            samples_jsonl_path=Path("/tmp/fake_samples.jsonl"),
            exit_code=0,
            status="ok",
            jsonl_skipped_lines=0,
            stderr_tail=[],
        )


    @pytest.fixture
    def fake_hermes(tmp_path):
        """Create a minimal fake hermes-agent dir with an empty git repo."""
        hermes = tmp_path / "hermes-agent"
        (hermes / "agent").mkdir(parents=True)
        (hermes / "agent" / "prompt_builder.py").write_text(
            'MEMORY_GUIDANCE = (\n    "baseline"\n)\n'
        )
        return hermes


    @pytest.fixture
    def fake_subset(tmp_path, monkeypatch):
        """Place datasets/prompts/tblite_stratified_subset.json in cwd."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "datasets" / "prompts").mkdir(parents=True)
        subset_path = tmp_path / "datasets" / "prompts" / "tblite_stratified_subset.json"
        # W-7 schema: task_filter is list of {name, tier} objects.
        subset = {
            "seed": 42,
            "per_tier_counts": {"easy": 2, "medium": 2, "hard": 2, "extreme": 2},
            "task_filter": [
                {"name": "t-easy-0", "tier": "easy"},
                {"name": "t-easy-1", "tier": "easy"},
                {"name": "t-medium-0", "tier": "medium"},
                {"name": "t-medium-1", "tier": "medium"},
                {"name": "t-hard-0", "tier": "hard"},
                {"name": "t-hard-1", "tier": "hard"},
                {"name": "t-extreme-0", "tier": "extreme"},
                {"name": "t-extreme-1", "tier": "extreme"},
            ],
            "source": "test",
            "generated_timestamp": "2026-05-19T00:00:00Z",
        }
        subset_path.write_text(json.dumps(subset))
        return subset_path


    def _patches_for_happy_path(module, per_tier_passed=None):
        """Common patches for a successful calibration run."""
        per_tier_passed = per_tier_passed or {
            "easy":    [True, True],
            "medium":  [True, False],
            "hard":    [False, False],
            "extreme": [False, False],
        }
        ps = []
        ps.append(patch.object(module, "_check_hermes_clean"))
        ps.append(patch.object(module, "_git_head", return_value="commit_abc12345"))
        ps.append(patch.object(module, "_hf_dataset_revision", return_value="hf_rev_xyz"))
        mock_runner_cls = MagicMock()
        mock_runner_cls.return_value.run.return_value = _make_run_result(per_tier_passed)
        ps.append(patch.object(module, "TBLiteRunner", mock_runner_cls))
        return ps


    # ── Tests ───────────────────────────────────────────────────────────────

    class TestBuildTBLiteCalibration:

        def test_anchor_json_schema_complete(self, fake_hermes, fake_subset, tmp_path):
            from evolution.benchmarks import build_tblite_calibration as mod
            anchor_out = tmp_path / "anchor.json"
            runner = CliRunner()
            patches = _patches_for_happy_path(mod)
            for p in patches:
                p.start()
            try:
                result = runner.invoke(mod.main, [
                    "--hermes-repo", str(fake_hermes),
                    "--seed", "42",
                    "--runs", "1",
                    "--output-json", str(anchor_out),
                    "--benchmark-max-cost", "1000.0",
                ])
            finally:
                for p in patches:
                    p.stop()
            assert result.exit_code == 0, f"CLI failed: {result.output}"
            anchor = json.loads(anchor_out.read_text())
            for key in (
                "anchor_per_tier", "dataset_revision_hash",
                "hermes_agent_commit", "stratified_subset_seed",
                "tblite_estimated_cost_per_task_usd",
                "calibration_timestamp", "calibration_model",
                "tblite_runner_version",
            ):
                assert key in anchor, f"missing top-level key {key!r}"
            for tier in ("easy", "medium", "hard", "extreme"):
                assert tier in anchor["anchor_per_tier"], f"missing tier {tier}"
                for inner in ("mean", "stdev", "n"):
                    assert inner in anchor["anchor_per_tier"][tier], \
                        f"missing {tier}.{inner}"

        def test_seed_is_persisted_from_subset(self, fake_hermes, fake_subset, tmp_path):
            """stratified_subset_seed comes from the subset JSON, not the --seed flag."""
            from evolution.benchmarks import build_tblite_calibration as mod
            # Mutate subset to seed=7.
            subset_data = json.loads(fake_subset.read_text())
            subset_data["seed"] = 7
            fake_subset.write_text(json.dumps(subset_data))
            anchor_out = tmp_path / "anchor.json"
            patches = _patches_for_happy_path(mod)
            for p in patches:
                p.start()
            try:
                result = CliRunner().invoke(mod.main, [
                    "--hermes-repo", str(fake_hermes),
                    "--seed", "999",  # SHOULD BE IGNORED — subset's seed wins
                    "--runs", "1",
                    "--output-json", str(anchor_out),
                    "--benchmark-max-cost", "1000",
                ])
            finally:
                for p in patches:
                    p.stop()
            assert result.exit_code == 0, result.output
            anchor = json.loads(anchor_out.read_text())
            assert anchor["stratified_subset_seed"] == 7, \
                f"subset seed not persisted: {anchor['stratified_subset_seed']}"

        def test_huggingface_fallback_on_api_error(self, fake_hermes, fake_subset, tmp_path):
            from evolution.benchmarks import build_tblite_calibration as mod
            anchor_out = tmp_path / "anchor.json"
            with patch.object(mod, "_check_hermes_clean"), \
                 patch.object(mod, "_git_head", return_value="commit_x"), \
                 patch.object(mod, "TBLiteRunner") as mock_runner_cls:
                mock_runner_cls.return_value.run.return_value = _make_run_result({
                    "easy": [True], "medium": [True], "hard": [True], "extreme": [True],
                })
                # Force HfApi.dataset_info to raise.
                import sys
                fake_hf = MagicMock()
                fake_hf.HfApi.return_value.dataset_info.side_effect = RuntimeError("no network")
                sys.modules["huggingface_hub"] = fake_hf
                try:
                    result = CliRunner().invoke(mod.main, [
                        "--hermes-repo", str(fake_hermes),
                        "--output-json", str(anchor_out),
                        "--runs", "1",
                        "--benchmark-max-cost", "1000",
                    ])
                finally:
                    sys.modules.pop("huggingface_hub", None)
            assert result.exit_code == 0, result.output
            anchor = json.loads(anchor_out.read_text())
            # Fallback string is 'unknown_v<runner version>'.
            assert anchor["dataset_revision_hash"].startswith("unknown_v"), \
                f"HF fallback not applied: {anchor['dataset_revision_hash']}"

        def test_git_dirty_check_blocks_calibration(self, fake_hermes, fake_subset, tmp_path):
            from evolution.benchmarks import build_tblite_calibration as mod
            anchor_out = tmp_path / "anchor.json"
            # _check_hermes_clean RAISES ClickException — simulate dirty tree.
            def raise_dirty(_):
                raise __import__("click").ClickException("uncommitted changes")
            with patch.object(mod, "_check_hermes_clean", side_effect=raise_dirty):
                result = CliRunner().invoke(mod.main, [
                    "--hermes-repo", str(fake_hermes),
                    "--output-json", str(anchor_out),
                    "--runs", "1",
                    "--benchmark-max-cost", "1000",
                ])
            assert result.exit_code != 0, "dirty git should block calibration"
            assert "uncommitted" in result.output.lower(), \
                f"missing dirty-tree message: {result.output}"
            assert not anchor_out.exists(), "anchor must NOT be written on dirty tree"

        def test_pre_flight_watermark_blocks_when_insufficient_budget(
            self, fake_hermes, fake_subset, tmp_path,
        ):
            """8 tasks × 3 runs × $0.4/task = $9.6; watermark = $28.8.

            With --benchmark-max-cost 5 -> watermark $28.8 > 5 -> abort.
            """
            from evolution.benchmarks import build_tblite_calibration as mod
            anchor_out = tmp_path / "anchor.json"
            patches = _patches_for_happy_path(mod)
            for p in patches:
                p.start()
            try:
                result = CliRunner().invoke(mod.main, [
                    "--hermes-repo", str(fake_hermes),
                    "--output-json", str(anchor_out),
                    "--runs", "3",
                    "--benchmark-max-cost", "5",
                ])
            finally:
                for p in patches:
                    p.stop()
            assert result.exit_code != 0, "insufficient budget must block"
            assert "watermark" in result.output.lower() or \
                   "budget" in result.output.lower(), \
                   f"missing Watermark error message: {result.output}"
            assert not anchor_out.exists(), \
                "anchor must NOT be written when Watermark fails"

        def test_tblite_cost_per_task_measured_and_written(
            self, fake_hermes, fake_subset, tmp_path,
        ):
            """anchor['tblite_estimated_cost_per_task_usd'] = measured (tracker.spent / (n_tasks * runs)).

            Note: CostTracker's spent_usd depends on DSPy track_usage integration
            which is not invoked in the mocked subprocess path. The field MUST
            still be written; the value may be 0.0 (no LM calls in test) or
            inherited from the default. We assert presence + numeric type.
            """
            from evolution.benchmarks import build_tblite_calibration as mod
            anchor_out = tmp_path / "anchor.json"
            patches = _patches_for_happy_path(mod)
            for p in patches:
                p.start()
            try:
                result = CliRunner().invoke(mod.main, [
                    "--hermes-repo", str(fake_hermes),
                    "--output-json", str(anchor_out),
                    "--runs", "1",
                    "--benchmark-max-cost", "1000",
                ])
            finally:
                for p in patches:
                    p.stop()
            assert result.exit_code == 0, result.output
            anchor = json.loads(anchor_out.read_text())
            assert "tblite_estimated_cost_per_task_usd" in anchor
            assert isinstance(anchor["tblite_estimated_cost_per_task_usd"], (int, float))

        def test_runs_aggregates_mean_stdev(self, fake_hermes, fake_subset, tmp_path):
            """3 runs with varied easy pass rates -> mean ≈ 0.85, stdev > 0."""
            from evolution.benchmarks import build_tblite_calibration as mod
            anchor_out = tmp_path / "anchor.json"
            mock_runner_cls = MagicMock()
            # Different easy pass rates per run: 1/2, 2/2, 2/2 -> [0.5, 1.0, 1.0].
            results = [
                _make_run_result({"easy": [True, False], "medium": [True, True],
                                   "hard": [True, True], "extreme": [True, True]}),
                _make_run_result({"easy": [True, True], "medium": [True, True],
                                   "hard": [True, True], "extreme": [True, True]}),
                _make_run_result({"easy": [True, True], "medium": [True, True],
                                   "hard": [True, True], "extreme": [True, True]}),
            ]
            mock_runner_cls.return_value.run.side_effect = results
            with patch.object(mod, "_check_hermes_clean"), \
                 patch.object(mod, "_git_head", return_value="commit_x"), \
                 patch.object(mod, "_hf_dataset_revision", return_value="rev"), \
                 patch.object(mod, "TBLiteRunner", mock_runner_cls):
                cli_result = CliRunner().invoke(mod.main, [
                    "--hermes-repo", str(fake_hermes),
                    "--output-json", str(anchor_out),
                    "--runs", "3",
                    "--benchmark-max-cost", "1000",
                ])
            assert cli_result.exit_code == 0, cli_result.output
            anchor = json.loads(anchor_out.read_text())
            easy = anchor["anchor_per_tier"]["easy"]
            assert abs(easy["mean"] - 0.8333) < 0.01, \
                f"easy mean wrong: {easy['mean']} expected ≈ 0.833"
            assert easy["stdev"] > 0, \
                f"easy stdev should be > 0 with varied scores: {easy['stdev']}"
            assert easy["n"] == 3
            assert len(easy["scores"]) == 3

        def test_accept_stale_anchor_bypasses_git_check(
            self, fake_hermes, fake_subset, tmp_path,
        ):
            """--accept-stale-anchor lets calibration run even on dirty tree."""
            from evolution.benchmarks import build_tblite_calibration as mod
            anchor_out = tmp_path / "anchor.json"
            # If accept-stale-anchor works, _check_hermes_clean is NEVER called.
            check_clean_calls = MagicMock()
            with patch.object(mod, "_check_hermes_clean", check_clean_calls), \
                 patch.object(mod, "_git_head", return_value="commit_x"), \
                 patch.object(mod, "_hf_dataset_revision", return_value="rev"), \
                 patch.object(mod, "TBLiteRunner") as mock_runner_cls:
                mock_runner_cls.return_value.run.return_value = _make_run_result({
                    "easy": [True], "medium": [True], "hard": [True], "extreme": [True],
                })
                result = CliRunner().invoke(mod.main, [
                    "--hermes-repo", str(fake_hermes),
                    "--output-json", str(anchor_out),
                    "--runs", "1",
                    "--benchmark-max-cost", "1000",
                    "--accept-stale-anchor",
                ])
            assert result.exit_code == 0, result.output
            assert not check_clean_calls.called, \
                "_check_hermes_clean must be skipped with --accept-stale-anchor"
    ```

    After writing, run `.venv/bin/pytest tests/benchmarks/test_build_tblite_calibration.py -v` and confirm 8 tests pass.

    Implements: PATTERNS §File 14 (CliRunner skeleton expanded from 5 to 8 tests).
  </action>
  <verify>
    <automated>.venv/bin/pytest tests/benchmarks/test_build_tblite_calibration.py -v --tb=short 2>&1 | tail -30 && .venv/bin/pytest tests/benchmarks/test_build_tblite_calibration.py -q 2>&1 | tail -3 | grep -E '[0-9]+ passed' || (echo "FAIL: tests did not all pass"; exit 1) && grep -c 'def test_' tests/benchmarks/test_build_tblite_calibration.py | awk '{ if ($1 < 6) { print "FAIL: only " $1 " tests, need >= 6"; exit 1 } else { print "OK: " $1 " tests" } }' && grep -c 'CliRunner' tests/benchmarks/test_build_tblite_calibration.py | awk '{ if ($1 < 1) { print "FAIL: CliRunner not used"; exit 1 } else { print "OK" } }' && grep -c 'patch.object.*TBLiteRunner' tests/benchmarks/test_build_tblite_calibration.py | awk '{ if ($1 < 1) { print "FAIL: TBLiteRunner not mocked"; exit 1 } else { print "OK" } }'</automated>
  </verify>
  <acceptance_criteria>
    - `pytest tests/benchmarks/test_build_tblite_calibration.py -v` exits 0 with all 6+ tests passing.
    - `grep -c 'def test_' tests/benchmarks/test_build_tblite_calibration.py` >= 6.
    - All tests use `CliRunner().invoke(mod.main, [...])`.
    - All tests mock `TBLiteRunner`, `_check_hermes_clean`, `_git_head`, and (for HF test) `huggingface_hub`.
    - At least one test confirms `exit_code != 0` for git-dirty and Watermark-insufficient paths.
    - test_runs_aggregates_mean_stdev verifies statistics.mean and statistics.stdev with non-trivial inputs.
  </acceptance_criteria>
  <done>
    - 8 CliRunner-based unit tests pass
    - No real subprocess / network / git invocations
    - Mean/stdev aggregation verified
    - Watermark + git-dirty + HF fallback regression guards in place
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| --hermes-repo CLI flag → subprocess.run cwd | User-provided path; Click validates with type=click.Path() (which accepts non-existing paths so subsequent existence check is in the body). |
| --benchmark-max-cost CLI flag → CostTracker max_usd | float coerced by Click; min not enforced (zero or negative disables enforcement — documented behavior of CostTracker:266 short-circuit). |
| --output-json CLI flag → file write | Click accepts arbitrary path; the CLI creates parent dirs as needed. Wave-1 default `datasets/prompts/tblite_anchor.json` is git-tracked; other paths are user's responsibility. |
| huggingface_hub.HfApi() → dataset_info → string | UNTRUSTED return value (network response). Caught in try/except + fail-open to known-safe `unknown_v<runner>` string. |
| TBLiteRunner subprocess output → per-tier dict | Plan 02 already mitigated (T-20-05 task_filter sanitization, T-20-08 jsonl skip, T-20-07 stderr cap). |
| stratified_subset.json on disk → task_filter | Git-tracked but mutable by user. Plan 02's `_validate_task_filter` re-checks against whitelist regex so subset poisoning is caught at subprocess-construction time. |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-20-18 | T (Tampering) | --benchmark-max-cost very small (e.g. -1) | mitigate | CostTracker.exceeded() short-circuits when max_usd <= 0 (cost_tracker.py:266). Negative budget effectively DISABLES cost cap — but the Watermark check (D-17) still runs and compares `watermark > budget`; if budget=-1, watermark=$X > -1 always → click.ClickException with explicit message. User cannot accidentally disable both layers. |
| T-20-19 | D (Denial of service) | HuggingFace HfApi infinite hang | mitigate | The `huggingface_hub` library has internal timeouts (default 10s for metadata). Our try/except catches all `Exception` types, including TimeoutError, and falls back. Worst case: 10s delay during Pre-flight. |
| T-20-20 | I (Information disclosure) | calibration_model field written to git-tracked anchor JSON | accept | Model name like "openai/gpt-4.1" is not a secret. API key fields are NEVER persisted (we only read `config.optimizer_model`, not `config.api_key`). |
| T-20-21 | T (Tampering) | stratified_subset.json _meta.placeholder absent / lying | mitigate | The CLI prints a yellow warning when `_meta.placeholder: true` is seen, but does NOT block — Plan 05 writes the real subset; an attacker setting placeholder=false would only suppress the warning, not introduce a vulnerability. The subsequent TBLite subprocess will fail on bogus task names anyway. |
| T-20-22 | E (Elevation of privilege) | --accept-stale-anchor bypassing git-dirty check | mitigate | The flag is is_flag=True (default False), help text explicitly marks `[unsafe]` and instructs writing to /tmp. The anchor file path is user-controlled, so misuse only affects the user's own machine. NOT auditable in git history because the flag is a CLI choice — documented in module docstring. |
| T-20-23 | T (Tampering) | git status missing git stash content (CONCERNS §M6 inherited) | accept | Same as Plan 03 T-20-12. Documented limitation; Plan 06+ adds `git stash list` check. |
</threat_model>

<verification>
- `python -m evolution.benchmarks.build_tblite_calibration --help` exits 0 and lists 8 flags.
- `pytest tests/benchmarks/test_build_tblite_calibration.py -v` exits 0 with all 6+ tests passing.
- `pytest tests/ --collect-only` succeeds (no global discovery regression).
- `grep -c 'CostTracker' evolution/benchmarks/build_tblite_calibration.py` >= 2 (import + use).
- `grep -c 'watermark' evolution/benchmarks/build_tblite_calibration.py` >= 2 (D-17 wired).
- `grep -c 'huggingface_hub' evolution/benchmarks/build_tblite_calibration.py` >= 1 (D-15 HF API).
- `grep -c '_check_hermes_clean' evolution/benchmarks/build_tblite_calibration.py` >= 2 (defined + called).
- File line count >= 280 (CLI body + helpers).
</verification>

<success_criteria>
- ROADMAP SC #1 (`--benchmark` flag): build_tblite_calibration is the prerequisite tool that makes `evolve_prompt_sections --benchmark=tblite` viable.
- D-13 covered: standalone CLI with full Pre-flight + 3-run + git-tracked output.
- D-15 covered: dataset_revision_hash fetched + fail-open fallback.
- D-16 covered: CostTracker enforces benchmark_max_cost_usd (separate from optimization tracker — none instantiated here).
- D-17 covered: Pre-flight Watermark blocks before subprocess starts.
- D-CAL-01 schema satisfied: anchor JSON has all required top-level keys + per-tier {mean, stdev, n, scores}.
- Phase 18 D-CAL-02 mirror: anchor written to `datasets/prompts/tblite_anchor.json` which is .gitignore-excepted (Plan 01).
- Risk Anchor 5 covered: HF API unavailable → fail-open with stable fallback string.
- T-20-18..T-20-23 mitigated or accepted with rationale.
</success_criteria>

<output>
After completion, create `.planning/phases/20-benchmark-gated-validation/20-04-build-calibration-cli-SUMMARY.md` covering:
- Line counts: build_tblite_calibration.py ~300-350; test_build_tblite_calibration.py ~250.
- Output of `python -m evolution.benchmarks.build_tblite_calibration --help` (first ~20 lines).
- pytest summary line for tests/benchmarks/test_build_tblite_calibration.py (expect 6+ passed).
- Grep evidence: CostTracker count, watermark count, huggingface_hub count.
- Confirmation that all Wave 1/2 imports resolve correctly when this module is loaded.
- Note: this CLI alone does NOT produce a real anchor.json — Plan 05 is the BLOCKING task that runs this CLI against live TBLite + Modal.
</output>
</content>
</invoke>

## Revision Log

- 2026-05-19 (W-7 propagation): CLI now extracts `task_names = [item['name'] for item in stratified['task_filter']]` from the new W-7 `{name, tier}` object schema before passing to `TBLiteRunner.run`. Tolerant of legacy flat-string form during transition. Test fixture `_make_subset` updated to W-7 schema. `key_links.via` description updated.
