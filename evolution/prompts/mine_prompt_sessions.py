"""SessionDB prompt behavioral mining CLI — Phase 19 (PMPT-V2-04).

Reads ~/.hermes/sessions/*.json transcripts and produces
PromptBehavioralExample JSONL files suitable for unioning with
Phase 9 synthetic datasets via evolve_prompt_sections --session-source.

Usage:
    python -m evolution.prompts.mine_prompt_sessions \\
        --i-have-consent \\
        --sessions-dir ~/.hermes/sessions \\
        --signals user_correction,section_specific_failure,oracle_disagreement,persona_drift \\
        --baseline-module output/prompts/<latest> \\
        --drift-thresholds-path datasets/prompts/drift_thresholds.json \\
        --output datasets/prompts/sessions/<ts>

Output topology (D-20):
    datasets/prompts/sessions/<YYYYMMDD_HHMMSS>/
        ├── train.jsonl / val.jsonl / holdout.jsonl
        ├── metrics.json
        └── miner_log.jsonl

Failure paths:
    FAILED_<ts>/   — sessions empty / consent missing / 0 examples post-judge

READ-ONLY guarantee: this CLI never calls prompt_loader.write_back_section
or any hermes-agent mutation path. It only reads session JSON + the current
prompt surface via extract_prompt_sections.
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
from evolution.prompts.drift_detector import DRIFT_DIMENSIONS
from evolution.prompts.prompt_dataset import PromptBehavioralDataset
from evolution.prompts.prompt_loader import extract_prompt_sections
from evolution.prompts.session_prompt_miner import (
    DEFAULT_MULTIPLIER,
    SessionPromptMiner,
    VALID_SIGNALS,
    split_and_duplicate,
)

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
    """Parse '--behavioral-multiplier' kv string into dict[str, int].

    Format: 'user_correction=3,section_specific_failure=3,oracle_disagreement=2,persona_drift=2'.
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
                f"--behavioral-multiplier item {part!r} missing '='"
            )
        k, v = part.split("=", 1)
        k = k.strip()
        if k not in VALID_SIGNALS:
            raise click.UsageError(
                f"--behavioral-multiplier unknown signal {k!r}; "
                f"valid: {sorted(VALID_SIGNALS)}"
            )
        try:
            out[k] = int(v.strip())
        except ValueError:
            raise click.UsageError(
                f"--behavioral-multiplier value for {k!r} must be int, got {v!r}"
            )
    return out


# ── Click command ────────────────────────────────────────────────────────
@click.command()
@click.option(
    "--sessions-dir", default=None, type=click.Path(),
    help="Directory containing session_*.json (default ~/.hermes/sessions)",
)
@click.option(
    "--output", default=None, type=click.Path(),
    help="Output directory (default datasets/prompts/sessions/<YYYYMMDD_HHMMSS>/)",
)
@click.option("--limit", default=0, type=int, help="0 = scan all sessions")
@click.option(
    "--i-have-consent", is_flag=True,
    help="REQUIRED — explicit consent to read session data (Layer 3 privacy gate). "
         "Refuses to proceed without it. Phase 14 D-16 + Phase 19 D-25 mirror.",
)
@click.option(
    "--signals",
    default="user_correction,section_specific_failure,oracle_disagreement,persona_drift",
    help="Comma-separated subset of {user_correction, section_specific_failure, "
         "oracle_disagreement, persona_drift}",
)
@click.option(
    "--baseline-module", default=None, type=click.Path(),
    help="Path to a Phase 10/17/18 evolve_prompt_sections output dir for "
         "oracle_disagreement signal (omit → signal disabled + warn)",
)
@click.option(
    "--judge-model", default=None,
    help="Override config.judge_model for ConfirmBehavioralExample LLM judge",
)
@click.option(
    "--behavioral-multiplier", default=None,
    help='Override D-13 defaults; e.g. "user_correction=3,section_specific_failure=3,'
         'oracle_disagreement=2,persona_drift=2"',
)
@click.option(
    "--hermes-repo", default=None,
    help="Path to hermes-agent repo (overrides HERMES_AGENT_REPO env)",
)
@click.option("--model", default=None, help="Override LLM model for non-judge calls")
@click.option("--api-base", default=None, help="Override API base URL")
@click.option(
    "--dry-run", is_flag=True,
    help="Skip LLM judge; enumerate candidates and print distribution table",
)
@click.option(
    "--drift-thresholds-path",
    type=click.Path(path_type=Path),
    default=Path("datasets/prompts/drift_thresholds.json"),
    help="Path to drift_thresholds.json (Phase 18 D-BYPASS-02 mirror) for "
         "persona_drift signal. Used only when persona_drift signal is enabled. "
         "When the file does not exist → persona_drift disabled + warn (not fatal). "
         "W2 fix: NO exists=True — file missing must not block consent gate.",
)
def main(
    sessions_dir, output, limit, i_have_consent, signals, baseline_module,
    judge_model, behavioral_multiplier, hermes_repo, model, api_base,
    dry_run, drift_thresholds_path,
):
    """SessionDB behavioral mining CLI for Phase 19 (PMPT-V2-04)."""
    sys.exit(mine(
        sessions_dir=sessions_dir, output=output, limit=limit,
        i_have_consent=i_have_consent, signals=signals,
        baseline_module=baseline_module, judge_model=judge_model,
        behavioral_multiplier=behavioral_multiplier,
        hermes_repo=hermes_repo, model=model, api_base=api_base,
        dry_run=dry_run, drift_thresholds_path=drift_thresholds_path,
    ))


def _print_summary_table(metrics: dict, total_examples: int, out_dir: Path) -> None:
    """Print Rich Table summary of mining run. Phase 19 has 4 signal rows.

    B3 fix: explicitly prints BOTH session_load_failures (file-level, mine
    scope) and jsonl_skipped_lines (line-level, Plan 04 evolve_prompt_sections
    session-source helper scope) with clear labels so the two metric channels
    don't get conflated in audit logs.
    """
    t = Table(
        title="SessionDB Behavioral Mining Summary",
        show_header=True,
        header_style="bold cyan",
    )
    t.add_column("Signal", style="bold")
    t.add_column("Candidates", justify="right")
    t.add_column("Confirmed", justify="right")
    t.add_column("False Positives", justify="right")
    t.add_column("Judge Calls", justify="right")
    signals_order = (
        "user_correction", "section_specific_failure",
        "oracle_disagreement", "persona_drift",
    )
    for s in signals_order:
        t.add_row(
            s,
            str(metrics["total_candidates_by_signal"].get(s, 0)),
            str(metrics["judge_confirmed_by_signal"].get(s, 0)),
            str(metrics["judge_false_positives_by_signal"].get(s, 0)),
            str(metrics.get("judge_calls_by_signal", {}).get(s, 0)),
        )
    # TOTAL row
    t.add_row(
        "[bold]TOTAL[/]",
        str(sum(metrics["total_candidates_by_signal"].values())),
        str(sum(metrics["judge_confirmed_by_signal"].values())),
        str(sum(metrics["judge_false_positives_by_signal"].values())),
        str(metrics.get("judge_calls", 0)),
    )
    console.print(t)
    console.print(
        f"  Surface drift dropped: {metrics['surface_drift_dropped']} "
        f"(sections: {metrics.get('surface_drift_sections', {})})"
    )
    console.print(f"  Secret filter skipped: {metrics['secret_filter_skipped']}")
    # B3 fix: print BOTH session-level + line-level skip counters with clear labels.
    console.print(
        f"  Session load failures (file-level, mine_prompt_sessions scope): "
        f"{metrics.get('session_load_failures', 0)}"
    )
    console.print(
        f"  JSONL skipped lines (line-level, evolve_prompt_sections session-source scope): "
        f"{metrics.get('jsonl_skipped_lines', 0)}"
    )
    final_by_split = metrics.get("final_examples_by_split", {})
    console.print(
        f"  Final examples: train={final_by_split.get('train', 0)} "
        f"({metrics.get('final_train_after_duplication', 0)} after duplication) "
        f"/ val={final_by_split.get('val', 0)} "
        f"/ holdout={final_by_split.get('holdout', 0)} "
        f"/ flat total = {total_examples}"
    )
    console.print(f"  Output: {out_dir}")


def _write_failed(timestamp: str, error_key: str, extra: Optional[dict] = None) -> Path:
    """Write FAILED_<ts>/ failure marker directory. Returns its Path.

    Mirrors mine_tool_sessions.py:239-247. The extra dict is for diagnostic
    breadcrumbs only — paths, exception type+str. Never includes raw session
    content (T-19-03-I mitigation).
    """
    failed = Path("datasets") / "prompts" / "sessions" / f"FAILED_{timestamp}"
    failed.mkdir(parents=True, exist_ok=True)
    payload: dict = {"error": error_key}
    if extra:
        payload.update(extra)
    (failed / "metrics.json").write_text(json.dumps(payload, indent=2))
    console.print(f"[red]✗ FAILED: {error_key} → {failed}[/red]")
    return failed


def mine(
    sessions_dir: Optional[str],
    output: Optional[str],
    limit: int,
    i_have_consent: bool,
    signals: str,
    baseline_module: Optional[str],
    judge_model: Optional[str],
    behavioral_multiplier: Optional[str],
    hermes_repo: Optional[str],
    model: Optional[str],
    api_base: Optional[str],
    dry_run: bool,
    drift_thresholds_path: Path,
) -> int:
    """Main mining orchestration. Returns int exit code (0=success, 1=fail)."""
    # D-25: --i-have-consent gate (mirror mine_tool_sessions.py:194-201)
    if not i_have_consent:
        click.echo(
            "ERROR: --i-have-consent is REQUIRED — refusing to read "
            "session data from ~/.hermes/sessions/ without explicit "
            "consent. Pass --i-have-consent to proceed.\n"
            "Session text may contain personal context; auditors should "
            "review SECRET_PATTERNS coverage before enabling.",
            err=True,
        )
        return 1

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    console.print(Panel.fit(
        f"[bold cyan]SessionDB Behavioral Mining[/bold cyan]\n"
        f"  Timestamp: {timestamp}\n"
        f"  Signals:   {signals}\n"
        f"  Dry-run:   {dry_run}",
    ))

    # Parse signals + multiplier early — Click UsageError surfaces before any I/O.
    signals_list = _parse_signals(signals)
    multiplier_override = _parse_multiplier_override(behavioral_multiplier)

    # Resolve paths.
    sessions_path = (
        Path(sessions_dir).expanduser() if sessions_dir
        else (Path.home() / ".hermes" / "sessions")
    )
    out_dir = (
        Path(output) if output
        else Path("datasets") / "prompts" / "sessions" / timestamp
    )

    if not sessions_path.exists() or not sessions_path.is_dir():
        _write_failed(timestamp, "sessions_dir_missing", {"sessions_dir": str(sessions_path)})
        return 1

    # Load config + sections.
    try:
        config = EvolutionConfig.load(
            hermes_repo=hermes_repo, model=model, api_base=api_base,
        )
    except Exception as e:
        _write_failed(timestamp, "config_load_failed",
                      {"detail": f"{type(e).__name__}: {e}"})
        return 1
    if judge_model:
        config.judge_model = judge_model

    prompt_builder_path = config.hermes_agent_path / "agent" / "prompt_builder.py"
    try:
        current_sections = extract_prompt_sections(prompt_builder_path)
    except Exception as e:
        _write_failed(timestamp, "prompt_extraction_failed",
                      {"detail": f"{type(e).__name__}: {e}",
                       "prompt_builder_path": str(prompt_builder_path)})
        return 1
    if not current_sections:
        _write_failed(timestamp, "no_sections_found",
                      {"prompt_builder_path": str(prompt_builder_path)})
        return 1

    # Load drift thresholds (D-04) — only when persona_drift active.
    # W2 fix: file existence checked LAZILY here (not at Click parse time).
    # Missing thresholds is NOT fatal (graceful disable + remove from signals_list).
    drift_thresholds: Optional[dict] = None
    if "persona_drift" in signals_list:
        if not Path(drift_thresholds_path).exists():
            console.print(
                f"[yellow]⚠ drift_thresholds_path {drift_thresholds_path} does "
                f"not exist. persona_drift signal will be disabled "
                f"(symmetric with oracle_disagreement disabled mode).[/yellow]"
            )
            signals_list = [s for s in signals_list if s != "persona_drift"]
        else:
            try:
                raw = json.loads(Path(drift_thresholds_path).read_text())
                drift_thresholds = {d: float(raw[d]) for d in DRIFT_DIMENSIONS}
            except Exception as e:
                console.print(
                    f"[yellow]⚠ Cannot parse drift thresholds from "
                    f"{drift_thresholds_path}: {type(e).__name__}: {e}. "
                    f"persona_drift signal will be disabled.[/yellow]"
                )
                drift_thresholds = None
                signals_list = [s for s in signals_list if s != "persona_drift"]

    # Load baseline module (D-04) — only when oracle_disagreement active.
    # Missing baseline_module is NOT fatal.
    baseline_mod = None
    oracle_baseline_path_str: Optional[str] = None
    if "oracle_disagreement" in signals_list:
        if baseline_module:
            bp = Path(baseline_module)
            try:
                # Sanity check: baseline dir must contain evolved_sections.json
                if (bp / "evolved_sections.json").exists():
                    # Defer actual PromptModule reconstruction; SessionPromptMiner
                    # treats baseline_module=None as "signal disabled". Pass the
                    # path object so the miner can later wire it lazily.
                    baseline_mod = bp
                    oracle_baseline_path_str = str(bp)
                else:
                    console.print(
                        f"[yellow]⚠ baseline_module {bp} has no "
                        f"evolved_sections.json; oracle_disagreement disabled[/yellow]"
                    )
            except Exception as e:
                console.print(
                    f"[yellow]⚠ Cannot load baseline module: "
                    f"{type(e).__name__}: {e}; oracle_disagreement disabled[/yellow]"
                )
        else:
            console.print(
                "[yellow]⚠ --baseline-module not given; "
                "oracle_disagreement signal disabled[/yellow]"
            )

    # Build miner.
    miner = SessionPromptMiner(
        config=config,
        signals=signals_list,
        multiplier_override=multiplier_override,
        baseline_module=baseline_mod,
        drift_thresholds=drift_thresholds,
    )
    if oracle_baseline_path_str:
        miner.metrics["oracle_baseline_path"] = oracle_baseline_path_str

    # ── Dry-run branch — skip LLM judge, enumerate candidates only ──
    if dry_run:
        console.print("[bold yellow]DRY RUN — skipping LLM judge[/bold yellow]")
        # Walk candidates without calling judge (to estimate LLM budget).
        session_paths = sorted(sessions_path.glob("*.json"))
        if limit > 0:
            session_paths = session_paths[:limit]
        total_cands = 0
        for sp in session_paths:
            sess = miner._load_session(sp)
            if not sess:
                continue
            msgs = sess.get("messages") or []
            if not isinstance(msgs, list):
                continue
            cands: list = []
            cands.extend(miner._extract_user_correction(msgs, str(sp)))
            cands.extend(miner._extract_section_specific_failure(msgs, str(sp)))
            cands.extend(miner._extract_oracle_disagreement(msgs, str(sp)))
            cands.extend(miner._extract_persona_drift(msgs, str(sp)))
            cands = miner._filter_secrets(cands)
            total_cands += len(cands)
        console.print(f"  Sessions scanned: {len(session_paths)}")
        console.print(f"  Candidates before LLM judge: {total_cands}")
        console.print(f"  Estimated LLM judge calls (no dry-run): {total_cands}")
        return 0

    # ── Real mine path ─────────────────────────────────────────────
    try:
        examples = miner.mine(sessions_path, current_sections, limit=limit)
    except Exception as e:
        _write_failed(timestamp, "mine_exception",
                      {"detail": f"{type(e).__name__}: {e}"})
        return 1

    if not examples:
        _write_failed(timestamp, "no_examples_post_judge",
                      {"metrics": miner.metrics})
        return 1

    # Bucket-split + train-only duplication (D-13/D-15).
    train, val, holdout = split_and_duplicate(
        examples,
        multiplier_override=multiplier_override,
        metrics=miner.metrics,
    )

    # Persist 5-file output topology (D-20).
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset = PromptBehavioralDataset(train=train, val=val, holdout=holdout)
    dataset.save(out_dir)

    # metrics.json
    (out_dir / "metrics.json").write_text(json.dumps(miner.metrics, indent=2))

    # miner_log.jsonl — one audit row per example (user_message truncated to 200 chars
    # per threat register T-19-03-I; no raw secrets since _filter_secrets already ran).
    with open(out_dir / "miner_log.jsonl", "w") as f:
        for ex in examples:
            f.write(json.dumps({
                "section_id": ex.section_id,
                "mining_signals": ex.mining_signals,
                "difficulty": ex.difficulty,
                "user_message_excerpt": (ex.user_message or "")[:200],
            }) + "\n")

    _print_summary_table(miner.metrics, len(examples), out_dir)
    console.print(f"\n[bold green]✓ Mining complete[/bold green]: {out_dir}/")
    return 0


if __name__ == "__main__":
    main()
