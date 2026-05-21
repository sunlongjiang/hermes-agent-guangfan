"""Phase 22 V2-LOOP-01 — continuous evolution loop CLI orchestrator.

Serially invokes 6 evolve_* CLI subprocesses (D-07 canonical order),
inspects each one's output directory to determine holdout gate pass/fail
(D-10), creates PRs against hermes-agent for successful runs via the
pr_creator helper (D-03/D-04/D-05), and writes an audit-trail
run_summary.json to output/loop/<loop_ts>/ (Phase 20 D-13 pattern).

This module is pure subprocess orchestration — it does NOT import dspy,
openevolve, or any evolution.* module besides config and external_importers
(for _contains_secret hygiene).

Usage:
    python -m evolution.loop.run_loop                          # full loop
    python -m evolution.loop.run_loop --dry-run                # all CLIs --dry-run, no PRs
    python -m evolution.loop.run_loop --cli skill --cli code   # subset
    python -m evolution.loop.run_loop --no-pr                  # skip PR creation
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from evolution.core.config import EvolutionConfig, LOOP_CLI_NAMES
from evolution.core.external_importers import _contains_secret

console = Console()

# ── Dispatch tables ─────────────────────────────────────────────────────

CLI_DISPATCH: dict[str, list[str]] = {
    "skill":             ["python", "-m", "evolution.skills.evolve_skill"],
    "tool_descriptions": ["python", "-m", "evolution.tools.evolve_tool_descriptions"],
    "tool_params":       ["python", "-m", "evolution.tools.evolve_tool_params"],
    "tool_reasoning":    ["python", "-m", "evolution.tools.evolve_tool_reasoning"],
    "prompt_sections":   ["python", "-m", "evolution.prompts.evolve_prompt_sections"],
    "code":              ["python", "-m", "evolution.code.evolve_code"],
}

CLI_OUTPUT_ROOT: dict[str, str] = {
    "skill":             "output",             # globs output/<skill_name>/<ts>/
    "tool_descriptions": "output/tools",
    "tool_params":       "output/tools",
    "tool_reasoning":    "output/tools_reasoning",
    "prompt_sections":   "output/prompts",
    "code":              "output/code",
}

# CLIs that accept --max-cost as a CLI flag. Others (skill, tool_descriptions)
# take it via env EVOLUTION_MAX_COST_USD.
CLI_MAX_COST_FLAG: dict[str, Optional[str]] = {
    "skill":             None,
    "tool_descriptions": None,
    "tool_params":       "--max-cost-usd",
    "tool_reasoning":    "--max-cost-usd",
    "prompt_sections":   "--max-cost-usd",
    "code":              "--max-cost",
}

TS_RE = re.compile(r"^\d{8}_\d{6}$")
FAILED_RE = re.compile(r"^(FAILED|ABORTED)_\d{8}_\d{6}$")
STDOUT_TAIL_LIMIT = 4000

# Non-skill output roots — used to exclude them when scanning for skill output.
_NON_SKILL_OUTPUT_ROOTS = {"tools", "tools_reasoning", "prompts", "code", "loop"}


# ── Helpers ─────────────────────────────────────────────────────────────


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _safe_tail(text: str, limit: int = STDOUT_TAIL_LIMIT) -> str:
    if not text:
        return ""
    tail = text[-limit:]
    if _contains_secret(tail):
        return "[REDACTED — contains secret-pattern match]"
    return tail


def _snapshot_dir_children(root: Path) -> set[str]:
    if not root.exists():
        return set()
    return {p.name for p in root.iterdir() if p.is_dir()}


def _parse_cost_from_metrics(metrics_path: Path) -> float:
    if not metrics_path.exists():
        return 0.0
    try:
        data = json.loads(metrics_path.read_text())
    except Exception:
        return 0.0
    for key in ("total_cost_usd", "cost_usd", "actual_cost_usd"):
        val = data.get(key)
        if isinstance(val, (int, float)):
            return float(val)
    return 0.0


def _parse_holdout_from_metrics(metrics_path: Path) -> Optional[bool]:
    """Return explicit holdout_gate_passed from metrics.json if present.

    Phase 22 D-10 says all CLIs write this field; in practice only evolve_code
    does. For other CLIs we fall back to dir-name pattern (see _classify_new_dir).
    """
    if not metrics_path.exists():
        return None
    try:
        data = json.loads(metrics_path.read_text())
    except Exception:
        return None
    val = data.get("holdout_gate_passed")
    if isinstance(val, bool):
        return val
    return None


def _classify_new_dir(dir_name: str) -> tuple[str, bool]:
    """Return (status, holdout_gate_passed) based on dir naming convention."""
    if TS_RE.match(dir_name):
        return ("success", True)
    if FAILED_RE.match(dir_name):
        return ("failed", False)
    return ("unknown", False)


def _find_new_dir(root: Path, snapshot: set[str]) -> Optional[Path]:
    """Return the newly-created dir under root (if any) by diffing snapshot.

    Returns the lexicographically-largest new dir (most recent timestamp).
    """
    if not root.exists():
        return None
    new_names = {p.name for p in root.iterdir() if p.is_dir()} - snapshot
    if not new_names:
        return None
    winner = sorted(new_names)[-1]
    return root / winner


def _find_new_dir_for_skill(snapshot_by_subdir: dict[str, set[str]]) -> Optional[Path]:
    """Skill writes to output/<skill_name>/<ts>/ — scan all subdirs of output/.

    snapshot_by_subdir: dict of subdir_name → set of <ts>-style child names
    captured BEFORE the subprocess invocation.
    """
    root = Path("output")
    if not root.exists():
        return None
    new_dirs: list[Path] = []
    for subdir in root.iterdir():
        if not subdir.is_dir():
            continue
        if subdir.name in _NON_SKILL_OUTPUT_ROOTS:
            continue
        pre = snapshot_by_subdir.get(subdir.name, set())
        post = {p.name for p in subdir.iterdir() if p.is_dir()}
        for new_name in post - pre:
            new_dirs.append(subdir / new_name)
    if not new_dirs:
        return None
    return sorted(new_dirs, key=lambda p: p.name)[-1]


def _snapshot_for_skill() -> dict[str, set[str]]:
    """Snapshot every output/<subdir>/ child set for the skill CLI scanner."""
    output_root = Path("output")
    snap: dict[str, set[str]] = {}
    if output_root.exists():
        for subdir in output_root.iterdir():
            if subdir.is_dir() and subdir.name not in _NON_SKILL_OUTPUT_ROOTS:
                snap[subdir.name] = {p.name for p in subdir.iterdir() if p.is_dir()}
    return snap


# ── Per-CLI runner ──────────────────────────────────────────────────────


def _run_one_cli(
    name: str,
    config: EvolutionConfig,
    dry_run: bool,
    no_pr: bool,
    per_cli_timeout: int,
    loop_ts: str,
) -> dict:
    """Invoke one CLI as subprocess, classify result, optionally create PR."""
    cfg_entry = config.loop_cli_config.get(name, {})
    max_cost = cfg_entry.get("max_cost_usd", 5.0)

    # Pre-snapshot
    if name == "skill":
        snapshot_skill = _snapshot_for_skill()
        snapshot: set[str] = set()
    else:
        snapshot_skill = {}
        snapshot = _snapshot_dir_children(Path(CLI_OUTPUT_ROOT[name]))

    # Build argv
    argv = list(CLI_DISPATCH[name])
    if dry_run:
        argv.append("--dry-run")
    flag = CLI_MAX_COST_FLAG[name]
    if flag is not None:
        argv.extend([flag, str(max_cost)])

    # Build env
    env = os.environ.copy()
    if config.deploy_mode is not None:
        env["EVOLUTION_DEPLOY_MODE"] = config.deploy_mode
    if flag is None:
        env["EVOLUTION_MAX_COST_USD"] = str(max_cost)

    started_at = _utcnow_iso()
    t0 = datetime.now(timezone.utc)
    try:
        proc = subprocess.run(
            argv,
            timeout=per_cli_timeout,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        exit_code = proc.returncode
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        timed_out = False
    except subprocess.TimeoutExpired as e:
        exit_code = -1
        stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        timed_out = True
    t1 = datetime.now(timezone.utc)
    duration_s = (t1 - t0).total_seconds()
    finished_at = _utcnow_iso()

    # Locate new output dir
    if name == "skill":
        new_dir = _find_new_dir_for_skill(snapshot_skill)
    else:
        new_dir = _find_new_dir(Path(CLI_OUTPUT_ROOT[name]), snapshot)

    # Classify
    if timed_out:
        status = "timeout"
        holdout_gate_passed = False
        failure_reason = f"subprocess exceeded per_cli_timeout={per_cli_timeout}s"
    elif new_dir is None:
        status = "crashed"
        holdout_gate_passed = False
        failure_reason = f"no new output dir created; exit_code={exit_code}"
    else:
        status, holdout_gate_passed = _classify_new_dir(new_dir.name)
        metrics_path = new_dir / "metrics.json"
        explicit = _parse_holdout_from_metrics(metrics_path)
        if explicit is not None:
            holdout_gate_passed = explicit
            # If explicit says False but dir name is success-pattern, trust
            # metrics.json (the CLI knows best) and downgrade status to failed.
            if not explicit and status == "success":
                status = "failed"
        failure_reason = (
            None if status == "success"
            else f"holdout gate failed (dir={new_dir.name})"
        )

    cost_usd = _parse_cost_from_metrics(new_dir / "metrics.json") if new_dir else 0.0
    evolved_artifact_path = str(new_dir) if new_dir else None

    # PR creation (only on full success, not dry-run, not no_pr)
    pr_url = None
    if status == "success" and not dry_run and not no_pr:
        from evolution.loop.pr_creator import create_pr
        try:
            pr_result = create_pr(
                cli_name=name,
                output_dir=new_dir,
                loop_ts=loop_ts,
                hermes_repo=config.hermes_agent_path,
            )
            pr_url = pr_result.get("pr_url")
            if pr_result.get("status") != "created":
                failure_reason = (
                    f"pr_creator status={pr_result.get('status')}: "
                    f"{pr_result.get('reason', '')}"
                )
        except Exception as e:
            failure_reason = f"pr_creator raised: {type(e).__name__}: {e}"

    return {
        "name": name,
        "status": status,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_seconds": round(duration_s, 2),
        "exit_code": exit_code,
        "max_cost_cap_usd": max_cost,
        "cost_usd": cost_usd,
        "output_dir": evolved_artifact_path,
        "holdout_gate_passed": holdout_gate_passed,
        "pr_url": pr_url,
        "failure_reason": failure_reason,
        "stdout_tail": _safe_tail(stdout),
        "stderr_tail": _safe_tail(stderr),
    }


# ── Main pipeline ───────────────────────────────────────────────────────


def evolve_loop(
    config_path: Optional[str],
    cli_filter: tuple[str, ...],
    dry_run: bool,
    no_pr: bool,
    per_cli_timeout: int,
    loop_output_dir: str,
) -> Path:
    """Run the loop. Returns path to run_summary.json."""
    config = EvolutionConfig.load(config_path=config_path)
    loop_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    loop_dir = Path(loop_output_dir) / loop_ts
    loop_dir.mkdir(parents=True, exist_ok=True)

    console.print(Panel.fit(
        f"loop_ts: {loop_ts}\n"
        f"deploy_mode: {config.deploy_mode or '(unset)'}\n"
        f"dry_run: {dry_run}\nno_pr: {no_pr}\n"
        f"per_cli_timeout: {per_cli_timeout}s\n"
        f"loop_output: {loop_dir}",
        title="Phase 22 Continuous Evolution Loop",
        border_style="cyan",
    ))

    runs: list[dict] = []
    for name in LOOP_CLI_NAMES:
        cfg_entry = config.loop_cli_config.get(
            name, {"enabled": True, "max_cost_usd": 5.0}
        )

        if cli_filter and name not in cli_filter:
            runs.append({
                "name": name, "status": "skipped_filter",
                "started_at": _utcnow_iso(), "finished_at": _utcnow_iso(),
                "duration_seconds": 0.0, "exit_code": None,
                "max_cost_cap_usd": cfg_entry.get("max_cost_usd", 5.0),
                "cost_usd": 0.0, "output_dir": None,
                "holdout_gate_passed": None, "pr_url": None,
                "failure_reason": "excluded by --cli filter",
                "stdout_tail": "", "stderr_tail": "",
            })
            continue
        if not cfg_entry.get("enabled", True):
            runs.append({
                "name": name, "status": "skipped_disabled",
                "started_at": _utcnow_iso(), "finished_at": _utcnow_iso(),
                "duration_seconds": 0.0, "exit_code": None,
                "max_cost_cap_usd": cfg_entry.get("max_cost_usd", 5.0),
                "cost_usd": 0.0, "output_dir": None,
                "holdout_gate_passed": None, "pr_url": None,
                "failure_reason": "loop_cli_config[name].enabled = false",
                "stdout_tail": "", "stderr_tail": "",
            })
            console.print(
                f"[yellow]⊝ skip {name}: disabled in evolution.yaml loop.cli[/yellow]"
            )
            continue

        console.print(f"\n[bold cyan]▶ {name}[/bold cyan]")
        run_record = _run_one_cli(
            name=name, config=config, dry_run=dry_run, no_pr=no_pr,
            per_cli_timeout=per_cli_timeout, loop_ts=loop_ts,
        )
        runs.append(run_record)
        icon = {"success": "+", "failed": "x", "crashed": "✗", "timeout": "⏱"}.get(
            run_record["status"], "?"
        )
        color = "green" if run_record["status"] == "success" else "red"
        console.print(
            f"  [{color}]{icon} {run_record['status']}[/{color}] "
            f"({run_record['duration_seconds']}s, "
            f"cost ${run_record['cost_usd']:.2f})"
        )

    # Build summary
    succeeded = sum(1 for r in runs if r["status"] == "success")
    failed = sum(
        1 for r in runs if r["status"] in {"failed", "crashed", "timeout"}
    )
    skipped = sum(1 for r in runs if r["status"].startswith("skipped"))
    prs_created = sum(1 for r in runs if r["pr_url"])
    total_cost = round(sum(r["cost_usd"] for r in runs), 4)

    summary = {
        "loop_ts": loop_ts,
        "started_at": runs[0]["started_at"] if runs else _utcnow_iso(),
        "finished_at": _utcnow_iso(),
        "config_snapshot": {
            "deploy_mode": config.deploy_mode,
            "loop_cli_config": config.loop_cli_config,
            "hermes_agent_path": str(config.hermes_agent_path),
        },
        "deploy_mode": config.deploy_mode,
        "cli_runs": runs,
        "summary": {
            "total_clis": len(LOOP_CLI_NAMES),
            "succeeded": succeeded,
            "failed": failed,
            "skipped": skipped,
            "prs_created": prs_created,
            "total_cost_usd": total_cost,
        },
    }

    summary_path = loop_dir / "run_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, default=str))

    # Final Rich table
    table = Table(title=f"Loop Summary — {loop_ts}")
    table.add_column("CLI")
    table.add_column("Status")
    table.add_column("Cost $", justify="right")
    table.add_column("Dur s", justify="right")
    table.add_column("PR")
    for r in runs:
        color = (
            "green" if r["status"] == "success"
            else ("yellow" if r["status"].startswith("skipped") else "red")
        )
        table.add_row(
            r["name"],
            f"[{color}]{r['status']}[/{color}]",
            f"{r['cost_usd']:.2f}",
            f"{r['duration_seconds']:.0f}",
            (r["pr_url"] or "-")[-60:],
        )
    console.print()
    console.print(table)
    console.print(f"\n[bold]run_summary:[/bold] {summary_path}")
    return summary_path


# ── Click CLI ───────────────────────────────────────────────────────────


@click.command()
@click.option(
    "--config", "config_path", default=None, type=click.Path(),
    help="Path to evolution.yaml (default: ./evolution.yaml)",
)
@click.option(
    "--cli", "cli_filter", multiple=True,
    type=click.Choice(list(LOOP_CLI_NAMES)),
    help="Run only specific CLIs (repeatable). Default: all enabled per loop_cli_config.",
)
@click.option(
    "--dry-run", is_flag=True, default=False,
    help="Append --dry-run to each CLI invocation; skip PR creation.",
)
@click.option(
    "--no-pr", is_flag=True, default=False,
    help="Run CLIs normally but skip PR creation step (useful for CI).",
)
@click.option(
    "--per-cli-timeout", default=900, type=int,
    help="Max seconds per subprocess invocation (default: 900 = 15min).",
)
@click.option(
    "--loop-output-dir", default="output/loop", type=click.Path(),
    help="Root for run_summary.json (default: output/loop)",
)
def main(config_path, cli_filter, dry_run, no_pr, per_cli_timeout, loop_output_dir):
    """Phase 22 V2-LOOP-01 continuous evolution loop runner."""
    evolve_loop(
        config_path=config_path,
        cli_filter=tuple(cli_filter),
        dry_run=dry_run,
        no_pr=no_pr,
        per_cli_timeout=per_cli_timeout,
        loop_output_dir=loop_output_dir,
    )


if __name__ == "__main__":
    main()
