"""Integration: per-artifact failure does not block other artifacts."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def test_artifact_failure_isolation_via_run_summary(tmp_evolution_home, write_trace_file,
                                                    fake_trace_factory, monkeypatch):
    """Even if one artifact rejects, run_summary lists all artifacts."""
    # Set up an agent with 2 artifacts (use ThreeFormBot which has 3).
    monkeypatch.syspath_prepend(str(Path(__file__).parent.parent.parent))
    import importlib
    importlib.import_module("tests.sdk.fixtures.agents.three_form_bot")
    from evolution.sdk import registry
    registry.persist_to_file()

    write_trace_file("three-form-bot", "20260613", [
        fake_trace_factory(agent="three-form-bot",
                           ts=f"2026-06-13T0{i}:00:00Z") for i in range(1, 6)
    ])

    result = subprocess.run(
        [sys.executable, "-m", "evolution.sdk.optimizer",
         "--agent", "three-form-bot", "--dry-run"],
        capture_output=True, text=True,
        env={**os.environ, "EVOLUTION_HOME": str(tmp_evolution_home)},
    )
    assert result.returncode == 0, result.stderr
    # Find run_summary.
    summaries = list((Path("output") / "sdk" / "three-form-bot").rglob("run_summary.json"))
    assert len(summaries) >= 1
    data = json.loads(summaries[-1].read_text())
    # All 3 artifacts must appear.
    artifact_ids = {a["artifact_id"] for a in data["artifacts"]}
    assert artifact_ids == {"system", "planner", "searcher"}
    import shutil
    shutil.rmtree(Path("output") / "sdk" / "three-form-bot", ignore_errors=True)
