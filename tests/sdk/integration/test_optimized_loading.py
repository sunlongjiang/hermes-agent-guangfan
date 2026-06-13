"""End-to-end: decorator + runtime + optimized file + baseline_hash transitions."""

import importlib
import json
import sys
from pathlib import Path

import pytest

from evolution.sdk import registry, runtime


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "agents"


@pytest.fixture(autouse=True)
def _clean(clear_registry, monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_DIR.parent.parent))
    for m in list(sys.modules):
        if m.startswith("fixtures.agents"):
            del sys.modules[m]


def test_lifecycle_baseline_then_optimize_then_source_change(tmp_evolution_home):
    # Step 1: Import — baseline in effect.
    mod = importlib.import_module("fixtures.agents.three_form_bot")
    assert runtime.resolve_text("three-form-bot", "system") == "You are FORM-1."

    # Step 2: Optimizer writes optimized file with current baseline_hash.
    reg = registry.get_agent("three-form-bot")
    a = next(art for art in reg.artifacts if art.artifact_id == "system")
    opt_dir = tmp_evolution_home / "optimized" / "three-form-bot"
    opt_dir.mkdir(parents=True)
    (opt_dir / "system.json").write_text(json.dumps({
        "baseline_hash": a.baseline_hash,
        "optimized_text": "VERSION_2 OPTIMIZED",
        "agent": "three-form-bot",
        "agent_version": "0.1.0",
        "artifact_id": "system", "kind": "prompt", "optimization": {},
    }))
    assert runtime.resolve_text("three-form-bot", "system") == "VERSION_2 OPTIMIZED"

    # Step 3: User changes source — simulate by registering with a different baseline.
    registry._REGISTRY["three-form-bot"].artifacts[0] = type(a)(
        agent_name=a.agent_name,
        artifact_id=a.artifact_id,
        kind=a.kind,
        baseline_text="NEW BASELINE TEXT",  # user changed it
        text_source=a.text_source,
        source_file=a.source_file,
        decorator_lineno=a.decorator_lineno,
        constraints=a.constraints,
    )
    # Stored hash no longer matches → fall back to NEW baseline.
    assert runtime.resolve_text("three-form-bot", "system") == "NEW BASELINE TEXT"
