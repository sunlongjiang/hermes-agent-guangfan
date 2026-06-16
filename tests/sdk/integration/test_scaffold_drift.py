"""Integration: full drift detection scenarios."""

import json
from pathlib import Path

import pytest

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.registry import AgentRegistration, register_agent
from evolution.sdk.scaffold import scaffold_gh_actions, check_drift


@pytest.fixture(autouse=True)
def _clean(clear_registry):
    pass


def _mk_reg(name, schedule="weekly"):
    return AgentRegistration(
        name=name, module=f"app.{name}:X", version="0.1.0",
        schedule=schedule, min_samples=10, auto_optimize=True, apply="runtime",
        max_cost_usd=5.0,
        artifacts=[EvolvableArtifact(
            agent_name=name, artifact_id="x", kind="prompt",
            baseline_text="x", text_source="param",
            source_file=Path("/tmp/x.py"), decorator_lineno=1,
        )],
        source_files=[Path(f"/tmp/{name}.py")],
    )


def test_full_drift_lifecycle(tmp_path):
    # 1. Register + scaffold → CLEAN
    register_agent(_mk_reg("bot-a", schedule="weekly"))
    register_agent(_mk_reg("bot-b", schedule="daily"))
    scaffold_gh_actions(output_dir=tmp_path)
    statuses = {s.agent: s.status for s in check_drift(output_dir=tmp_path)}
    assert statuses == {"bot-a": "CLEAN", "bot-b": "CLEAN"}

    # 2. Delete a file → MISSING
    (tmp_path / "evolve-bot-a.yml").unlink()
    statuses = {s.agent: s.status for s in check_drift(output_dir=tmp_path)}
    assert statuses["bot-a"] == "MISSING"

    # 3. Recreate + change schedule on registry → DRIFT
    scaffold_gh_actions(output_dir=tmp_path)
    # Update registry: change bot-a's schedule.
    from evolution.sdk import registry as r
    r._REGISTRY["bot-a"].schedule = "daily"
    statuses = {s.agent: s.status for s in check_drift(output_dir=tmp_path)}
    assert statuses["bot-a"] == "DRIFT"
