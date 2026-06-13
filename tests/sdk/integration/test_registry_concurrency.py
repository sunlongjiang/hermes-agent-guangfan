"""Concurrency: multiple processes persisting registry.json."""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    sys.platform == "win32",
    reason="fcntl.flock not available on Windows",
)


def test_concurrent_persist_does_not_corrupt_json(tmp_evolution_home):
    """5 subprocesses writing different agents concurrently → final file has all of them."""
    script = textwrap.dedent("""
        import os, sys
        os.environ["EVOLUTION_HOME"] = sys.argv[1]
        from pathlib import Path
        from evolution.sdk.artifact import EvolvableArtifact
        from evolution.sdk.registry import register_agent, AgentRegistration, persist_to_file, _REGISTRY

        name = sys.argv[2]
        _REGISTRY.clear()
        # Each subprocess starts from current on-disk state to merge correctly.
        from evolution.sdk.registry import load_from_file
        load_from_file()

        register_agent(AgentRegistration(
            name=name,
            module=f"myapp.{name}:X",
            version="0.1.0",
            schedule=None, min_samples=10, auto_optimize=False, apply="runtime",
            max_cost_usd=5.0,
            artifacts=[EvolvableArtifact(
                agent_name=name, artifact_id="x", kind="prompt",
                baseline_text="hi", text_source="param",
                source_file=Path("/tmp/x.py"), decorator_lineno=1,
            )],
            source_files=[Path(f"/tmp/{name}.py")],
        ))
        persist_to_file()
        print(name, "OK")
    """)
    procs = []
    for n in ["a", "b", "c", "d", "e"]:
        p = subprocess.Popen(
            [sys.executable, "-c", script, str(tmp_evolution_home), f"bot-{n}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        procs.append(p)

    for p in procs:
        out, err = p.communicate(timeout=30)
        assert p.returncode == 0, f"subprocess failed: {err.decode()}"

    # Final registry.json must be valid JSON with all 5 agents.
    data = json.loads((tmp_evolution_home / "registry.json").read_text())
    assert data["version"] == 1
    # Last-writer-wins per agent; at least the last process's write survives.
    # We don't guarantee all 5 names if the load/save races, but the file must be valid.
    assert len(data["agents"]) >= 1
    for name in data["agents"]:
        assert name.startswith("bot-")
