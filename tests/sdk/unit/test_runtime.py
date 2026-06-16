"""Tests for runtime trace capture + optimized loading."""

import importlib
import json
import sys
from pathlib import Path

import pytest

from evolution.sdk import runtime, registry
from evolution.sdk.artifact import compute_baseline_hash


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "agents"


@pytest.fixture(autouse=True)
def _clean(clear_registry, monkeypatch):
    if str(FIXTURE_DIR.parent.parent) not in sys.path:
        monkeypatch.syspath_prepend(str(FIXTURE_DIR.parent.parent))
    for mod_name in list(sys.modules):
        if mod_name.startswith("fixtures.agents"):
            del sys.modules[mod_name]


def test_run_emits_trace_record(tmp_evolution_home):
    mod = importlib.import_module("fixtures.agents.three_form_bot")
    bot = mod.ThreeFormBot()
    out = bot.run("hello")
    assert out == "echo: hello"

    traces_dir = tmp_evolution_home / "traces" / "three-form-bot"
    files = list(traces_dir.glob("*.jsonl"))
    assert len(files) == 1
    lines = files[0].read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["agent"] == "three-form-bot"
    assert rec["input"] == {"q": "hello"} or rec["input"] == {"args": ["hello"]}
    assert rec["output"] == "echo: hello"
    assert any(a["id"] == "system" for a in rec["artifacts"])


def test_run_exception_recorded_then_reraised(tmp_evolution_home):
    """If agent.run() raises, trace records the error and exception propagates."""
    from evolution.sdk.decorators import evolvable_agent, evolvable_prompt

    @evolvable_agent(name="raiser", version="0.1.0", min_samples=3,
                     schedule=None, auto_optimize=False, max_cost_usd=1.0)
    class Raiser:
        @evolvable_prompt(id="sys", text="x")
        def sys(self): return "x"
        def run(self, q):
            raise RuntimeError("boom")

    bot = Raiser()
    with pytest.raises(RuntimeError, match="boom"):
        bot.run("trigger")

    traces_dir = tmp_evolution_home / "traces" / "raiser"
    rec = json.loads(list(traces_dir.glob("*.jsonl"))[0].read_text().splitlines()[0])
    assert rec["signals"]["errors"] >= 1
    assert "boom" in (rec.get("output") or "") or "boom" in str(rec.get("error") or "")


def test_load_optimized_when_hash_matches(tmp_evolution_home):
    mod = importlib.import_module("fixtures.agents.three_form_bot")
    reg = registry.get_agent("three-form-bot")
    sys_artifact = next(a for a in reg.artifacts if a.artifact_id == "system")

    # Write a matching optimized file.
    opt_dir = tmp_evolution_home / "optimized" / "three-form-bot"
    opt_dir.mkdir(parents=True)
    (opt_dir / "system.json").write_text(json.dumps({
        "agent": "three-form-bot",
        "agent_version": "0.1.0",
        "artifact_id": "system",
        "kind": "prompt",
        "baseline_hash": sys_artifact.baseline_hash,
        "optimized_text": "OPTIMIZED!",
        "optimization": {},
    }))

    resolved = runtime.resolve_text("three-form-bot", "system")
    assert resolved == "OPTIMIZED!"


def test_load_optimized_ignored_on_hash_mismatch(tmp_evolution_home):
    mod = importlib.import_module("fixtures.agents.three_form_bot")
    opt_dir = tmp_evolution_home / "optimized" / "three-form-bot"
    opt_dir.mkdir(parents=True)
    (opt_dir / "system.json").write_text(json.dumps({
        "agent": "three-form-bot",
        "agent_version": "0.1.0",
        "artifact_id": "system",
        "kind": "prompt",
        "baseline_hash": "sha256:STALE_HASH",
        "optimized_text": "STALE",
        "optimization": {},
    }))
    resolved = runtime.resolve_text("three-form-bot", "system")
    assert resolved == "You are FORM-1."  # baseline


def test_load_optimized_missing_returns_baseline(tmp_evolution_home):
    importlib.import_module("fixtures.agents.three_form_bot")
    # No optimized file exists.
    resolved = runtime.resolve_text("three-form-bot", "system")
    assert resolved == "You are FORM-1."


def test_load_optimized_corrupt_json_returns_baseline(tmp_evolution_home):
    importlib.import_module("fixtures.agents.three_form_bot")
    opt_dir = tmp_evolution_home / "optimized" / "three-form-bot"
    opt_dir.mkdir(parents=True)
    (opt_dir / "system.json").write_text("{NOT VALID JSON")
    resolved = runtime.resolve_text("three-form-bot", "system")
    assert resolved == "You are FORM-1."  # silent fallback


def test_resolve_text_unknown_artifact_raises():
    importlib.import_module("fixtures.agents.three_form_bot")
    with pytest.raises(KeyError):
        runtime.resolve_text("three-form-bot", "nonexistent_id")
