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

    # Body filled by Task 3.2:
    raise NotImplementedError("Task 3.2 fills this in")


if __name__ == "__main__":
    main()
