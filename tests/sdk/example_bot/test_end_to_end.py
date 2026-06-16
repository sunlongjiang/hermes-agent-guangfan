"""End-to-end: import → traces → optimize stub → resolve_text picks optimized."""

import importlib
import json
import sys
from pathlib import Path

import pytest

from evolution.sdk import registry, runtime
from evolution.sdk.optimizer import write_optimized_file
from evolution.sdk.artifact import EvolvableArtifact


FIXTURE_DIR = Path(__file__).parent


@pytest.fixture(autouse=True)
def _clean(clear_registry, monkeypatch):
    monkeypatch.syspath_prepend(str(FIXTURE_DIR.parent.parent))
    for m in list(sys.modules):
        if m.startswith("tests.sdk.example_bot") or m.endswith("echo_bot"):
            del sys.modules[m]


def test_full_lifecycle_baseline_optimize_runtime_load(tmp_evolution_home):
    # 1) Import the agent → registered.
    mod = importlib.import_module("tests.sdk.example_bot.echo_bot")
    reg = registry.get_agent("echo-bot-test")
    assert reg is not None
    assert len(reg.artifacts) == 2  # rewriter + echo_tool

    # 2) Instantiate + run 5 times → traces persisted.
    bot = mod.EchoBot()
    for q in ["a", "b", "c", "d", "e"]:
        out = bot.run(q)
        assert q in out  # echo round-trip

    traces_dir = tmp_evolution_home / "traces" / "echo-bot-test"
    jsonl_files = list(traces_dir.glob("*.jsonl"))
    assert len(jsonl_files) == 1
    lines = jsonl_files[0].read_text().splitlines()
    assert len(lines) == 5
    parsed = [json.loads(l) for l in lines]
    for p in parsed:
        assert p["agent"] == "echo-bot-test"
        assert any(a["id"] == "rewriter" for a in p["artifacts"])

    # 3) Simulate optimizer writing an optimized rewriter.
    rewriter = next(a for a in reg.artifacts if a.artifact_id == "rewriter")
    write_optimized_file(
        artifact=rewriter,
        agent_version="0.1.0",
        optimized_text="CONCISE: {input}",
        optimization_metadata={
            "run_id": "test-run",
            "ts": "2026-06-13T00:00:00Z",
            "optimizer": "mock",
            "baseline_score": 0.5,
            "optimized_score": 0.85,
            "holdout_score": 0.80,
            "dataset_size": 5,
            "cost_usd": 0.0,
        },
    )

    # 4) resolve_text returns optimized version (hash matches).
    resolved = runtime.resolve_text("echo-bot-test", "rewriter")
    assert resolved == "CONCISE: {input}"

    # 5) New invocation uses optimized prompt.
    out = bot.run("hello")
    assert "CONCISE" in out and "hello" in out

    # 6) Simulate user editing baseline → optimized is invalidated.
    # We can't easily edit the actual file in a test; mutate the in-memory
    # artifact's baseline_text and verify resolve_text falls back.
    rewriter_new = EvolvableArtifact(
        agent_name=rewriter.agent_name,
        artifact_id=rewriter.artifact_id,
        kind=rewriter.kind,
        baseline_text="DIFFERENT BASELINE NOW",
        text_source=rewriter.text_source,
        source_file=rewriter.source_file,
        decorator_lineno=rewriter.decorator_lineno,
        constraints=rewriter.constraints,
    )
    reg.artifacts[reg.artifacts.index(rewriter)] = rewriter_new
    assert runtime.resolve_text("echo-bot-test", "rewriter") == "DIFFERENT BASELINE NOW"


def test_min_samples_not_met_skips(tmp_evolution_home, write_trace_file, fake_trace_factory):
    """`evolution optimize` with too few traces writes SKIPPED, exit 0."""
    importlib.import_module("tests.sdk.example_bot.echo_bot")
    # min_samples=3; write only 1 trace.
    write_trace_file("echo-bot-test", "20260613", [
        fake_trace_factory(agent="echo-bot-test", ts="2026-06-13T01:00:00Z"),
    ])
    registry.persist_to_file()

    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "evolution.sdk.optimizer",
         "--agent", "echo-bot-test"],
        capture_output=True, text=True, env={**__import__("os").environ,
                                              "EVOLUTION_HOME": str(tmp_evolution_home)},
        cwd=str(Path.cwd()),
    )
    assert result.returncode == 0, result.stderr
    # SKIPPED directory exists.
    skipped = list((Path("output") / "sdk" / "echo-bot-test").glob("SKIPPED_*"))
    assert len(skipped) >= 1
    # Clean up
    import shutil
    shutil.rmtree(Path("output") / "sdk" / "echo-bot-test", ignore_errors=True)


def test_dry_run_writes_run_summary(tmp_evolution_home, write_trace_file, fake_trace_factory):
    importlib.import_module("tests.sdk.example_bot.echo_bot")
    write_trace_file("echo-bot-test", "20260613", [
        fake_trace_factory(agent="echo-bot-test",
                           ts=f"2026-06-13T0{i}:00:00Z") for i in range(1, 6)
    ])
    registry.persist_to_file()

    import subprocess, os, shutil
    result = subprocess.run(
        [sys.executable, "-m", "evolution.sdk.optimizer",
         "--agent", "echo-bot-test", "--dry-run"],
        capture_output=True, text=True,
        env={**os.environ, "EVOLUTION_HOME": str(tmp_evolution_home)},
    )
    assert result.returncode == 0, result.stderr
    runs = list((Path("output") / "sdk" / "echo-bot-test").glob("*"))
    assert any((p / "run_summary.json").exists() for p in runs if p.is_dir())
    shutil.rmtree(Path("output") / "sdk" / "echo-bot-test", ignore_errors=True)
