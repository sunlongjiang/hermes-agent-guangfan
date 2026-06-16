"""Tests for in-memory + file-persisted agent registry."""

import json
import os
from pathlib import Path

import pytest

from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.registry import (
    AgentRegistration,
    DuplicateAgentError,
    register_agent,
    get_agent,
    list_agents,
    persist_to_file,
    load_from_file,
    _REGISTRY,
)


@pytest.fixture(autouse=True)
def _clear(clear_registry):
    pass


def _mk_artifact(agent="bot", aid="system"):
    return EvolvableArtifact(
        agent_name=agent,
        artifact_id=aid,
        kind="prompt",
        baseline_text="hi",
        text_source="param",
        source_file=Path("/tmp/x.py"),
        decorator_lineno=1,
    )


def test_register_agent_stores_in_memory():
    reg = AgentRegistration(
        name="bot",
        module="myapp.bot:Bot",
        version="0.1.0",
        schedule="weekly",
        min_samples=50,
        auto_optimize=True,
        apply="runtime",
        max_cost_usd=5.0,
        artifacts=[_mk_artifact()],
        source_files=[Path("/tmp/x.py")],
    )
    register_agent(reg)
    assert "bot" in _REGISTRY
    assert _REGISTRY["bot"].name == "bot"


def test_register_agent_duplicate_different_module_raises():
    reg1 = AgentRegistration(
        name="bot", module="myapp.a:Bot", version="0.1.0",
        schedule=None, min_samples=10, auto_optimize=False, apply="runtime",
        max_cost_usd=5.0, artifacts=[_mk_artifact()], source_files=[Path("/tmp/a.py")],
    )
    reg2 = AgentRegistration(
        name="bot", module="myapp.b:Bot", version="0.1.0",
        schedule=None, min_samples=10, auto_optimize=False, apply="runtime",
        max_cost_usd=5.0, artifacts=[_mk_artifact()], source_files=[Path("/tmp/b.py")],
    )
    register_agent(reg1)
    with pytest.raises(DuplicateAgentError, match="different module"):
        register_agent(reg2)


def test_register_agent_duplicate_same_module_replaces():
    """Re-importing the same module (test reload, IDE) replaces silently."""
    reg = AgentRegistration(
        name="bot", module="myapp.a:Bot", version="0.1.0",
        schedule=None, min_samples=10, auto_optimize=False, apply="runtime",
        max_cost_usd=5.0, artifacts=[_mk_artifact()], source_files=[Path("/tmp/a.py")],
    )
    register_agent(reg)
    register_agent(reg)  # idempotent
    assert len(_REGISTRY) == 1


def test_get_agent_returns_none_for_unknown():
    assert get_agent("nonexistent") is None


def test_list_agents_sorted():
    for name in ["c-bot", "a-bot", "b-bot"]:
        register_agent(AgentRegistration(
            name=name, module=f"myapp.{name}:X", version="0.1.0",
            schedule=None, min_samples=10, auto_optimize=False, apply="runtime",
            max_cost_usd=5.0, artifacts=[_mk_artifact(agent=name)],
            source_files=[Path(f"/tmp/{name}.py")],
        ))
    names = list_agents()
    assert names == ["a-bot", "b-bot", "c-bot"]


def test_persist_to_file_writes_registry_json(tmp_evolution_home):
    reg = AgentRegistration(
        name="bot", module="myapp.a:Bot", version="0.1.0",
        schedule="weekly", min_samples=50, auto_optimize=True, apply="runtime",
        max_cost_usd=5.0, artifacts=[_mk_artifact()],
        source_files=[Path("/tmp/a.py")],
    )
    register_agent(reg)
    path = persist_to_file()
    assert path == tmp_evolution_home / "registry.json"
    data = json.loads(path.read_text())
    assert data["version"] == 1
    assert "bot" in data["agents"]
    assert data["agents"]["bot"]["schedule"] == "weekly"


def test_load_from_file_restores_registry(tmp_evolution_home):
    reg = AgentRegistration(
        name="bot", module="myapp.a:Bot", version="0.1.0",
        schedule="daily", min_samples=20, auto_optimize=True, apply="patch",
        max_cost_usd=10.0, artifacts=[_mk_artifact()],
        source_files=[Path("/tmp/a.py")],
    )
    register_agent(reg)
    persist_to_file()

    _REGISTRY.clear()
    load_from_file()

    loaded = get_agent("bot")
    assert loaded is not None
    assert loaded.schedule == "daily"
    assert loaded.apply == "patch"


def test_load_from_file_missing_file_is_noop(tmp_evolution_home):
    # No registry.json exists; should not raise.
    load_from_file()
    assert _REGISTRY == {}


def test_persist_skipped_unless_env_var_or_explicit(tmp_evolution_home, monkeypatch):
    """Decorator import期不能自动写文件 (production safety)."""
    monkeypatch.delenv("EVOLUTION_AUTO_REGISTER", raising=False)
    reg = AgentRegistration(
        name="bot", module="myapp.a:Bot", version="0.1.0",
        schedule="weekly", min_samples=50, auto_optimize=True, apply="runtime",
        max_cost_usd=5.0, artifacts=[_mk_artifact()],
        source_files=[Path("/tmp/a.py")],
    )
    register_agent(reg)
    # Registry is in-memory only; no file should exist.
    assert not (tmp_evolution_home / "registry.json").exists()

    # Now flip the flag; explicit persist still required (auto-write would be the wrong default).
    monkeypatch.setenv("EVOLUTION_AUTO_REGISTER", "1")
    # Re-registering doesn't auto-write either; user must call persist_to_file().
    register_agent(reg)
    assert not (tmp_evolution_home / "registry.json").exists()
    persist_to_file()
    assert (tmp_evolution_home / "registry.json").exists()
