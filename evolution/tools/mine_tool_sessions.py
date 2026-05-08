"""SessionDB tool-misselection mining CLI — Phase 14 (TOOL-V2-01).

Reads ~/.hermes/sessions/*.json transcripts and produces ToolSelectionExample
JSONL files suitable for unioning with synthetic Phase 4 datasets.

Usage:
    python -m evolution.tools.mine_tool_sessions \\
        --i-have-consent \\
        --sessions-dir ~/.hermes/sessions \\
        --signals error_retry,user_correction,oracle_disagreement \\
        --baseline-module output/tools/<latest> \\
        --output datasets/tools/sessions/<ts>

Output topology (D-08):
    datasets/tools/sessions/<YYYYMMDD_HHMMSS>/
        ├── train.jsonl / val.jsonl / holdout.jsonl
        ├── metrics.json
        └── miner_log.jsonl

Failure paths:
    FAILED_<ts>/   — sessions empty / consent missing / 0 candidate after filter
    ABORTED_<ts>/  — Ctrl+C / --limit early stop (reserved for future)

READ-ONLY guarantee: this CLI never calls tool_loader.write_back_description
or any hermes-agent mutation path. It only reads session JSON + the current
tool surface via discover_tool_files / extract_tool_descriptions.
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from evolution.core.config import EvolutionConfig
from evolution.tools.session_miner import (
    DEFAULT_MULTIPLIER,
    VALID_SIGNALS,
    SessionToolMiner,
)
from evolution.tools.tool_loader import discover_tool_files, extract_tool_descriptions

console = Console()


# ── Helpers ──────────────────────────────────────────────────────────────
def _parse_signals(value: str) -> list[str]:
    """Parse '--signals' CSV into a deduped list. Unknown signals → UsageError."""
    items = [s.strip() for s in (value or "").split(",") if s.strip()]
    bad = [s for s in items if s not in VALID_SIGNALS]
    if bad:
        raise click.UsageError(
            f"--signals contains unknown signal(s): {bad}. "
            f"Valid: {sorted(VALID_SIGNALS)}"
        )
    if not items:
        raise click.UsageError("--signals is empty after parsing")
    return list(dict.fromkeys(items))


def _parse_multiplier_override(value: Optional[str]) -> dict[str, int]:
    """Parse '--misselection-multiplier' kv string into dict[str, int].

    Format: 'error_retry=3,user_correction=3,oracle_disagreement=2'.
    Empty / None returns {}. Unknown signal keys raise UsageError.
    """
    if not value:
        return {}
    out: dict[str, int] = {}
    for part in value.split(","):
        if not part.strip():
            continue
        if "=" not in part:
            raise click.UsageError(
                f"--misselection-multiplier item {part!r} missing '='"
            )
        k, v = part.split("=", 1)
        k = k.strip()
        if k not in VALID_SIGNALS:
            raise click.UsageError(
                f"--misselection-multiplier unknown signal {k!r}; "
                f"valid: {sorted(VALID_SIGNALS)}"
            )
        try:
            out[k] = int(v.strip())
        except ValueError:
            raise click.UsageError(
                f"--misselection-multiplier value for {k!r} must be int, got {v!r}"
            )
    return out


def _load_baseline_module(output_dir: Path, hermes_repo: Path):
    """Reconstruct a ToolModule from a Phase 5 / 13 output dir (Pitfall 4).

    Reads <output_dir>/evolved_descriptions.json. Falls back to current
    hermes-agent toolset for any tool not present in the artifact.
    Returns ToolModule or raises click.UsageError.
    """
    from evolution.tools.tool_module import ToolModule

    evolved_path = output_dir / "evolved_descriptions.json"
    if not evolved_path.exists():
        raise click.UsageError(
            f"--baseline-module {output_dir} missing evolved_descriptions.json"
        )
    payload = json.loads(evolved_path.read_text())
    current_tools: list = []
    for fp in discover_tool_files(hermes_repo):
        current_tools.extend(extract_tool_descriptions(fp))
    desc_map = {item.get("name"): item.get("description", "") for item in payload}
    params_map = {
        item.get("name"): {
            p.get("name"): p.get("description", "") for p in item.get("params", [])
        }
        for item in payload
    }
    for t in current_tools:
        if t.name in desc_map:
            t.description = desc_map[t.name]
            pm = params_map.get(t.name, {})
            for p in getattr(t, "params", []):
                if p.name in pm:
                    p.description = pm[p.name]
    return ToolModule(current_tools)


def _write_miner_log(out_dir: Path, miner: SessionToolMiner) -> None:
    """Write miner_log.jsonl: one line per metric snapshot for audit."""
    log_path = out_dir / "miner_log.jsonl"
    with open(log_path, "w") as f:
        f.write(
            json.dumps({"event": "metrics_snapshot", "metrics": miner.metrics})
            + "\n"
        )


def _print_summary_table(metrics: dict, total_examples: int) -> None:
    """Rich Table summary (D-08)."""
    t = Table(
        title="SessionDB Mining Summary",
        show_header=True,
        header_style="bold cyan",
    )
    t.add_column("Signal", style="bold")
    t.add_column("Candidates", justify="right")
    t.add_column("Confirmed", justify="right")
    t.add_column("False Positives", justify="right")
    for s in ("error_retry", "user_correction", "oracle_disagreement"):
        t.add_row(
            s,
            str(metrics["total_candidates_by_signal"].get(s, 0)),
            str(metrics["judge_confirmed_by_signal"].get(s, 0)),
            str(metrics["judge_false_positives_by_signal"].get(s, 0)),
        )
    t.add_row(
        "[bold]TOTAL[/]",
        str(sum(metrics["total_candidates_by_signal"].values())),
        str(sum(metrics["judge_confirmed_by_signal"].values())),
        str(sum(metrics["judge_false_positives_by_signal"].values())),
    )
    console.print(t)
    console.print(f"  surface_drift_dropped: {metrics['surface_drift_dropped']}")
    console.print(f"  secret_filter_skipped: {metrics['secret_filter_skipped']}")
    console.print(f"  judge_calls: {metrics.get('judge_calls', 0)}")
    drift = metrics.get("surface_drift_tools") or {}
    if drift:
        top = sorted(drift.items(), key=lambda kv: kv[1], reverse=True)[:10]
        console.print(f"  surface_drift_tools (top-{len(top)}): {dict(top)}")
    console.print(f"  total_examples_post_judge: {total_examples}")


# ── Main orchestration ──────────────────────────────────────────────────
def mine(
    sessions_dir: Optional[str],
    output: Optional[str],
    limit: int,
    i_have_consent: bool,
    signals: str,
    baseline_module: Optional[str],
    judge_model: Optional[str],
    misselection_multiplier: Optional[str],
    hermes_repo: Optional[str],
    model: Optional[str],
    api_base: Optional[str],
    dry_run: bool,
) -> int:
    """Run the mining pipeline. Returns exit code (0 success, 1 failure)."""
    if not i_have_consent:
        click.echo(
            "--i-have-consent is REQUIRED — refusing to read session data "
            "without explicit consent.\n"
            "Pass --i-have-consent to proceed.",
            err=True,
        )
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    config = EvolutionConfig.load(
        api_base=api_base,
        model=model,
        hermes_repo=hermes_repo,
    )
    if judge_model:
        config.judge_model = judge_model

    sessions_path = (
        Path(sessions_dir).expanduser()
        if sessions_dir
        else (Path.home() / ".hermes" / "sessions")
    )
    out_dir = (
        Path(output)
        if output
        else Path("datasets") / "tools" / "sessions" / timestamp
    )

    signals_list = _parse_signals(signals)
    multiplier_override = _parse_multiplier_override(misselection_multiplier)

    console.print(
        Panel.fit(
            f"[bold cyan]Phase 14 SessionDB Mining[/]\n"
            f"sessions={sessions_path}  output={out_dir}\n"
            f"signals={signals_list}  judge_model={config.judge_model}\n"
            f"limit={'all' if limit == 0 else limit}  dry_run={dry_run}",
        )
    )

    if not sessions_path.exists() or not sessions_path.is_dir():
        console.print(
            f"[red]✗ sessions-dir {sessions_path} does not exist or is not a directory[/red]"
        )
        failed = Path("datasets") / "tools" / "sessions" / f"FAILED_{timestamp}"
        failed.mkdir(parents=True, exist_ok=True)
        (failed / "metrics.json").write_text(
            json.dumps(
                {"error": "sessions_dir_missing", "path": str(sessions_path)},
                indent=2,
            )
        )
        return 1

    current_tools: list = []
    try:
        for fp in discover_tool_files(config.hermes_agent_path):
            current_tools.extend(extract_tool_descriptions(fp))
    except Exception as e:
        console.print(f"[red]✗ Failed to discover current tools: {e}[/red]")
        current_tools = []

    if not current_tools:
        console.print(
            f"[red]✗ No tools discovered under {config.hermes_agent_path}[/red]"
        )
        failed = Path("datasets") / "tools" / "sessions" / f"FAILED_{timestamp}"
        failed.mkdir(parents=True, exist_ok=True)
        (failed / "metrics.json").write_text(
            json.dumps({"error": "no_tools_found"}, indent=2)
        )
        return 1

    baseline_mod = None
    if baseline_module:
        baseline_mod = _load_baseline_module(
            Path(baseline_module), config.hermes_agent_path
        )
    elif "oracle_disagreement" in signals_list:
        console.print(
            "[yellow]⚠ --baseline-module not provided; "
            "oracle_disagreement signal will be skipped[/yellow]"
        )

    miner = SessionToolMiner(
        config=config,
        signals=signals_list,
        multiplier_override=multiplier_override,
        baseline_module=baseline_mod,
    )

    if dry_run:
        console.print(
            "[bold yellow]DRY-RUN[/]: enumerating candidates only — no LLM calls"
        )
        cands = miner.enumerate_candidates(sessions_path, current_tools, limit=limit)
        _print_summary_table(miner.metrics, len(cands))
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "metrics.json").write_text(json.dumps(miner.metrics, indent=2))
        console.print(
            f"\n[bold green]Dry-run complete[/]: {out_dir}/metrics.json"
        )
        return 0

    examples = miner.mine(sessions_path, current_tools, limit=limit)
    if not examples:
        console.print(
            "[yellow]⚠ No misselection examples after judge; "
            "writing FAILED_<ts>/[/yellow]"
        )
        failed = Path("datasets") / "tools" / "sessions" / f"FAILED_{timestamp}"
        failed.mkdir(parents=True, exist_ok=True)
        (failed / "metrics.json").write_text(json.dumps(miner.metrics, indent=2))
        _print_summary_table(miner.metrics, 0)
        return 1

    split = miner.split_and_duplicate(examples)

    out_dir.mkdir(parents=True, exist_ok=True)
    for split_name in ("train", "val", "holdout"):
        with open(out_dir / f"{split_name}.jsonl", "w") as f:
            for ex in split[split_name]:
                f.write(json.dumps(ex.to_dict(), ensure_ascii=False) + "\n")
    (out_dir / "metrics.json").write_text(json.dumps(miner.metrics, indent=2))
    _write_miner_log(out_dir, miner)

    _print_summary_table(miner.metrics, len(examples))
    console.print(f"\n[bold green]Mining complete[/]: {out_dir}/")
    return 0


# ── Click CLI ────────────────────────────────────────────────────────────
@click.command()
@click.option(
    "--sessions-dir",
    default=None,
    type=click.Path(),
    help="Directory containing session_*.json (default ~/.hermes/sessions)",
)
@click.option(
    "--output",
    default=None,
    type=click.Path(),
    help="Output directory (default datasets/tools/sessions/<YYYYMMDD_HHMMSS>/)",
)
@click.option("--limit", default=0, type=int, help="0 = scan all sessions")
@click.option(
    "--i-have-consent",
    is_flag=True,
    help="REQUIRED — explicit consent to read session data (Layer 3 privacy gate)",
)
@click.option(
    "--signals",
    default="error_retry,user_correction,oracle_disagreement",
    help="Comma-separated subset of {error_retry, user_correction, oracle_disagreement}",
)
@click.option(
    "--baseline-module",
    default=None,
    type=click.Path(),
    help="Path to a Phase 5/13 output dir for oracle (C signal); omit → skip C",
)
@click.option(
    "--judge-model",
    default=None,
    help="Override config.judge_model for ConfirmMisselection LLM judge",
)
@click.option(
    "--misselection-multiplier",
    default=None,
    help='Override defaults, format "error_retry=3,user_correction=3,oracle_disagreement=2"',
)
@click.option(
    "--hermes-repo",
    default=None,
    help="Path to hermes-agent repo (overrides HERMES_AGENT_REPO env)",
)
@click.option("--model", default=None, help="Override LLM model for non-judge calls")
@click.option("--api-base", default=None, help="Override API base URL")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Skip LLM judge; enumerate candidates and exit",
)
def main(
    sessions_dir: Optional[str],
    output: Optional[str],
    limit: int,
    i_have_consent: bool,
    signals: str,
    baseline_module: Optional[str],
    judge_model: Optional[str],
    misselection_multiplier: Optional[str],
    hermes_repo: Optional[str],
    model: Optional[str],
    api_base: Optional[str],
    dry_run: bool,
) -> None:
    """Mine hermes session JSONL transcripts for tool misselection patterns."""
    sys.exit(
        mine(
            sessions_dir=sessions_dir,
            output=output,
            limit=limit,
            i_have_consent=i_have_consent,
            signals=signals,
            baseline_module=baseline_module,
            judge_model=judge_model,
            misselection_multiplier=misselection_multiplier,
            hermes_repo=hermes_repo,
            model=model,
            api_base=api_base,
            dry_run=dry_run,
        )
    )


if __name__ == "__main__":
    main()
