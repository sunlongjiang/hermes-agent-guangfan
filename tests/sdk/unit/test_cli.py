"""Tests for evolution CLI commands."""

import json
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from evolution.sdk.cli import main


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "agents"


@pytest.fixture(autouse=True)
def _clean(clear_registry, monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_DIR.parent.parent))
    for m in list(sys.modules):
        if m.startswith("fixtures.agents"):
            del sys.modules[m]


def test_discover_imports_module_and_persists(tmp_evolution_home):
    runner = CliRunner()
    result = runner.invoke(
        main, ["discover", "fixtures.agents.three_form_bot"],
    )
    assert result.exit_code == 0, result.output
    reg = json.loads((tmp_evolution_home / "registry.json").read_text())
    assert "three-form-bot" in reg["agents"]


def test_discover_missing_module_fails():
    runner = CliRunner()
    result = runner.invoke(main, ["discover", "nonexistent.module"])
    assert result.exit_code != 0
    assert "could not import" in result.output.lower() or "modulenotfounderror" in result.output.lower()


def test_scaffold_dry_run_does_not_write(tmp_path, tmp_evolution_home):
    runner = CliRunner()
    runner.invoke(main, ["discover", "fixtures.agents.three_form_bot"])
    result = runner.invoke(main, [
        "scaffold", "--backend", "gh-actions",
        "--output", str(tmp_path), "--dry-run",
    ])
    assert result.exit_code == 0
    assert not (tmp_path / "evolve-three-form-bot.yml").exists()


def test_scaffold_writes_workflow_file(tmp_path, tmp_evolution_home, monkeypatch):
    # three_form_bot has schedule=None — we override via re-register.
    runner = CliRunner()
    runner.invoke(main, ["discover", "fixtures.agents.three_form_bot"])
    # Manually patch registry to schedule="weekly".
    from evolution.sdk import registry as r
    r._REGISTRY["three-form-bot"].schedule = "weekly"
    r.persist_to_file()

    result = runner.invoke(main, [
        "scaffold", "--backend", "gh-actions",
        "--output", str(tmp_path),
    ])
    assert result.exit_code == 0
    assert (tmp_path / "evolve-three-form-bot.yml").exists()


def test_status_lists_registered_agents(tmp_evolution_home):
    runner = CliRunner()
    runner.invoke(main, ["discover", "fixtures.agents.three_form_bot"])
    result = runner.invoke(main, ["status", "--agent", "three-form-bot"])
    assert result.exit_code == 0
    assert "three-form-bot" in result.output


def test_rollback_deletes_optimized_file(tmp_evolution_home):
    runner = CliRunner()
    runner.invoke(main, ["discover", "fixtures.agents.three_form_bot"])
    opt_dir = tmp_evolution_home / "optimized" / "three-form-bot"
    opt_dir.mkdir(parents=True)
    (opt_dir / "system.json").write_text("{}")
    result = runner.invoke(
        main, ["rollback", "--agent", "three-form-bot", "--artifact", "system"]
    )
    assert result.exit_code == 0
    assert not (opt_dir / "system.json").exists()


def test_optimize_dry_run_succeeds(tmp_evolution_home, write_trace_file, fake_trace_factory):
    """`evolution optimize --dry-run` works even without traces."""
    runner = CliRunner()
    runner.invoke(main, ["discover", "fixtures.agents.three_form_bot"])
    # Generate enough traces to pass min_samples=3.
    write_trace_file("three-form-bot", "20260612", [
        fake_trace_factory(agent="three-form-bot", ts="2026-06-12T01:00:00Z")
        for _ in range(5)
    ])
    result = runner.invoke(
        main, ["optimize", "--agent", "three-form-bot", "--dry-run"]
    )
    assert result.exit_code == 0
