"""Shared fixtures for evolution.sdk tests."""

import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def tmp_evolution_home(tmp_path, monkeypatch):
    """Isolate ~/.evolution/ into a tmp directory per-test.

    Sets EVOLUTION_HOME env var; SDK modules MUST honor this when locating
    registry.json / traces / optimized / datasets / locks.
    """
    home = tmp_path / "evolution_home"
    home.mkdir()
    monkeypatch.setenv("EVOLUTION_HOME", str(home))
    return home


@pytest.fixture
def clear_registry():
    """Force a clean in-memory registry between tests.

    Some tests import agent modules which write to evolution.sdk.registry._REGISTRY.
    This fixture resets it so each test starts from an empty state.
    """
    from evolution.sdk import registry
    registry._REGISTRY.clear()
    yield
    registry._REGISTRY.clear()


@pytest.fixture
def mock_dspy_lm():
    """A mock dspy.LM that returns predictable strings.

    Configure via .respond_with(text) or .respond_sequence([t1, t2, ...]).
    """
    class _Mock:
        def __init__(self):
            self._responses = [""]
            self._call_count = 0
            self.model = "mock/predictable"

        def respond_with(self, text: str):
            self._responses = [text]
            return self

        def respond_sequence(self, texts: list[str]):
            self._responses = list(texts)
            return self

        def __call__(self, prompt=None, messages=None, **kwargs):
            text = self._responses[min(self._call_count, len(self._responses) - 1)]
            self._call_count += 1
            return [text]

    return _Mock()


@pytest.fixture
def fake_trace_factory():
    """Build TraceRecord dicts for testing signals + dataset construction."""
    def factory(
        agent="test-bot",
        agent_version="0.1.0",
        input_data=None,
        output=None,
        tool_calls=None,
        signals_dict=None,
        scores_dict=None,
        ts="2026-06-13T10:00:00Z",
    ):
        return {
            "ts": ts,
            "agent": agent,
            "agent_version": agent_version,
            "run_id": f"uuid-{ts}",
            "input": input_data or {"query": "test"},
            "output": output if output is not None else "test output",
            "artifacts": [
                {"id": "system", "kind": "prompt", "text_hash": "sha256:abc"},
            ],
            "tool_calls": tool_calls or [],
            "signals": signals_dict or {"errors": 0, "retries": 0, "user_correction": None},
            "scores": scores_dict or {"metric": None, "signal_score": 1.0, "judge_score": None},
        }
    return factory


@pytest.fixture
def write_trace_file(tmp_evolution_home):
    """Write a list of trace dicts to ~/.evolution/traces/<agent>/<date>.jsonl."""
    def writer(agent: str, date: str, records: list[dict]) -> Path:
        traces_dir = tmp_evolution_home / "traces" / agent
        traces_dir.mkdir(parents=True, exist_ok=True)
        path = traces_dir / f"{date}.jsonl"
        with path.open("w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
        return path
    return writer
