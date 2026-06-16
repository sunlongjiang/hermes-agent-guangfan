"""Integration: apply=runtime / patch / pr produces correct artifacts."""

import json
import sys
from pathlib import Path

import pytest

from evolution.sdk import registry
from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.optimizer import (
    write_optimized_file, emit_patch_for_outcome, OptimizationOutcome,
)


def _mk_src(tmp_path):
    f = tmp_path / "bot.py"
    f.write_text(
        'from evolution.sdk.decorators import evolvable_agent, evolvable_prompt\n'
        '\n'
        '@evolvable_agent(name="bot", schedule=None, auto_optimize=False, min_samples=1, max_cost_usd=1.0)\n'
        'class Bot:\n'
        '    @evolvable_prompt(id="sys", text="OLD TEXT")\n'
        '    def sys_prompt(self):\n'
        '        return "x"\n'
        '    def run(self, q):\n'
        '        return q\n'
    )
    return f


def test_runtime_mode_writes_optimized_only(tmp_path, tmp_evolution_home):
    src = _mk_src(tmp_path)
    artifact = EvolvableArtifact(
        agent_name="bot", artifact_id="sys", kind="prompt",
        baseline_text="OLD TEXT", text_source="param",
        source_file=src, decorator_lineno=3,
    )
    path = write_optimized_file(
        artifact=artifact, agent_version="0.1.0",
        optimized_text="NEW TEXT",
        optimization_metadata={"run_id": "x", "ts": "2026-06-13T00:00:00Z",
                                "optimizer": "GEPA", "baseline_score": 0.5,
                                "optimized_score": 0.8, "holdout_score": 0.75,
                                "dataset_size": 10, "cost_usd": 0.5},
    )
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["optimized_text"] == "NEW TEXT"
    # Source file unchanged.
    assert "OLD TEXT" in src.read_text()


def test_patch_mode_emits_unified_diff(tmp_path, tmp_evolution_home):
    src = _mk_src(tmp_path)
    artifact = EvolvableArtifact(
        agent_name="bot", artifact_id="sys", kind="prompt",
        baseline_text="OLD TEXT", text_source="param",
        source_file=src, decorator_lineno=3,
    )
    outcome = OptimizationOutcome(
        artifact_id="sys", status="improved",
        baseline_score=0.5, optimized_score=0.8,
        rejection_reason=None, cost_usd=0.5,
    )
    patch_path = emit_patch_for_outcome(
        outcome=outcome, artifact=artifact, optimized_text="NEW TEXT",
        agent_name="bot",
    )
    assert patch_path.exists()
    diff = patch_path.read_text()
    assert "--- a/bot.py" in diff
    assert "+++ b/bot.py" in diff
    assert "-" in diff and "OLD TEXT" in diff
    assert "+" in diff and "NEW TEXT" in diff
    # Source not modified.
    assert "OLD TEXT" in src.read_text()
