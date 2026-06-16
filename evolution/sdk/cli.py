"""evolution CLI: discover / scaffold / optimize / status / rollback."""

import importlib
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from evolution.sdk import registry, scaffold as scaffold_mod
from evolution.sdk.trace_sink import _evolution_home

console = Console()


@click.group()
def main():
    """Evolution SDK — generic Python agent self-evolution."""


@main.command()
@click.argument("modules", nargs=-1, required=True)
@click.option("--package", "is_package", is_flag=True,
              help="Treat MODULES as package paths to import recursively.")
def discover(modules, is_package):
    """Import agent modules to populate the registry, then persist to disk."""
    for spec in modules:
        try:
            if is_package:
                importlib.import_module(spec)
            else:
                importlib.import_module(spec)
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]could not import {spec}: {e}[/red]")
            sys.exit(1)

    registry.persist_to_file()
    names = registry.list_agents()
    console.print(f"[green]discovered {len(names)} agent(s):[/green] {', '.join(names)}")


@main.command()
@click.option("--backend", type=click.Choice(["gh-actions"]), default="gh-actions",
              help="Scheduling backend (P0 only supports gh-actions).")
@click.option("--output", "output_dir", type=click.Path(file_okay=False, path_type=Path),
              default=Path(".github/workflows"),
              help="Output directory for generated configs.")
@click.option("--agent", default=None, help="Only scaffold for this agent.")
@click.option("--dry-run", is_flag=True, help="Preview without writing files.")
@click.option("--check", is_flag=True, help="Drift detection mode (CI use).")
def scaffold(backend, output_dir, agent, dry_run, check):
    """Generate scheduling configs from registered agents."""
    registry.load_from_file()
    if check:
        statuses = scaffold_mod.check_drift(output_dir=output_dir)
        _print_drift_table(statuses)
        exit_code = _drift_exit_code(statuses)
        sys.exit(exit_code)

    if dry_run:
        for name in (registry.list_agents() if agent is None else [agent]):
            reg = registry.get_agent(name)
            if reg is None:
                continue
            if reg.schedule_managed_by or reg.schedule in (None, "on_min_samples"):
                continue
            console.print(f"[cyan]would write[/cyan] {output_dir}/evolve-{name}.yml")
        return

    written = scaffold_mod.scaffold_gh_actions(
        output_dir=output_dir, only_agent=agent,
    )
    for path in written:
        console.print(f"[green]wrote[/green] {path}")


def _print_drift_table(statuses):
    table = Table(title="Scaffold drift status")
    table.add_column("Agent")
    table.add_column("Status")
    table.add_column("Detail")
    for s in statuses:
        color = {"CLEAN": "green", "MISSING": "red", "DRIFT": "red",
                 "MANUAL_EDIT": "yellow", "STALE": "yellow"}.get(s.status, "white")
        table.add_row(s.agent, f"[{color}]{s.status}[/{color}]", s.detail or "")
    console.print(table)


def _drift_exit_code(statuses) -> int:
    fail = any(s.status in ("DRIFT", "MISSING") for s in statuses)
    warn = any(s.status in ("MANUAL_EDIT", "STALE") for s in statuses)
    if fail:
        return 2
    if warn:
        return 1
    return 0


@main.command()
@click.option("--agent", required=True)
@click.option("--dry-run", is_flag=True)
@click.option("--mock-llm", is_flag=True)
def optimize(agent, dry_run, mock_llm):
    """Manually trigger optimization for one agent."""
    from evolution.sdk import optimizer
    argv = ["--agent", agent]
    if dry_run:
        argv.append("--dry-run")
    if mock_llm:
        argv.append("--mock-llm")
    sys.argv = ["optimize"] + argv
    sys.exit(optimizer.main())


@main.command()
@click.option("--agent", required=True)
def status(agent):
    """Show registration + traces + optimized state for one agent."""
    registry.load_from_file()
    reg = registry.get_agent(agent)
    if reg is None:
        console.print(f"[red]agent {agent!r} not registered[/red]")
        sys.exit(1)
    table = Table(title=f"Status: {agent}")
    table.add_column("Field"); table.add_column("Value")
    table.add_row("module", reg.module)
    table.add_row("version", reg.version)
    table.add_row("schedule", str(reg.schedule))
    table.add_row("apply", reg.apply)
    table.add_row("artifacts", ", ".join(a.artifact_id for a in reg.artifacts))

    opt_dir = _evolution_home() / "optimized" / agent
    if opt_dir.exists():
        for opt_file in opt_dir.glob("*.json"):
            try:
                data = json.loads(opt_file.read_text())
                table.add_row(f"optimized:{opt_file.stem}",
                              f"score={data.get('optimization', {}).get('optimized_score')}")
            except json.JSONDecodeError:
                table.add_row(f"optimized:{opt_file.stem}", "[red]corrupt[/red]")
    console.print(table)


@main.command()
@click.option("--agent", required=True)
@click.option("--artifact", required=True)
def rollback(agent, artifact):
    """Delete an optimized artifact (revert to baseline)."""
    path = _evolution_home() / "optimized" / agent / f"{artifact}.json"
    if not path.exists():
        console.print(f"[yellow]no optimized file for {agent}/{artifact}[/yellow]")
        sys.exit(0)
    path.unlink()
    console.print(f"[green]removed[/green] {path}")


if __name__ == "__main__":
    main()
