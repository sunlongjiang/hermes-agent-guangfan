"""Tests for EvolvableArtifact data class."""

import hashlib
from pathlib import Path

import pytest

from evolution.sdk.artifact import (
    EvolvableArtifact,
    ArtifactKind,
    TextSource,
    compute_baseline_hash,
)


def test_artifact_construction_minimal():
    artifact = EvolvableArtifact(
        agent_name="bot",
        artifact_id="system",
        kind="prompt",
        baseline_text="You are a helpful assistant.",
        text_source="param",
        source_file=Path("/tmp/bot.py"),
        decorator_lineno=10,
    )
    assert artifact.agent_name == "bot"
    assert artifact.artifact_id == "system"
    assert artifact.kind == "prompt"
    assert artifact.constraints == {}


def test_artifact_baseline_hash_computed():
    artifact = EvolvableArtifact(
        agent_name="bot",
        artifact_id="sys",
        kind="prompt",
        baseline_text="hello world",
        text_source="param",
        source_file=Path("/tmp/x.py"),
        decorator_lineno=1,
    )
    expected = "sha256:" + hashlib.sha256("hello world".encode()).hexdigest()
    assert artifact.baseline_hash == expected


def test_artifact_kind_validated():
    with pytest.raises(ValueError, match="kind must be"):
        EvolvableArtifact(
            agent_name="bot",
            artifact_id="x",
            kind="invalid_kind",  # noqa
            baseline_text="t",
            text_source="param",
            source_file=Path("/tmp/x.py"),
            decorator_lineno=1,
        )


def test_artifact_text_source_validated():
    with pytest.raises(ValueError, match="text_source must be"):
        EvolvableArtifact(
            agent_name="bot",
            artifact_id="x",
            kind="prompt",
            baseline_text="t",
            text_source="invalid",  # noqa
            source_file=Path("/tmp/x.py"),
            decorator_lineno=1,
        )


def test_artifact_to_dict_roundtrip():
    artifact = EvolvableArtifact(
        agent_name="bot",
        artifact_id="search",
        kind="tool",
        baseline_text="Search the web",
        text_source="docstring",
        source_file=Path("/tmp/bot.py"),
        decorator_lineno=42,
        constraints={"max_chars": 500, "max_growth": 0.2},
    )
    d = artifact.to_dict()
    assert d["agent_name"] == "bot"
    assert d["kind"] == "tool"
    assert d["source_file"] == "/tmp/bot.py"  # serialized as str
    assert d["constraints"]["max_chars"] == 500

    restored = EvolvableArtifact.from_dict(d)
    assert restored.baseline_hash == artifact.baseline_hash
    assert restored.source_file == artifact.source_file


def test_compute_baseline_hash_deterministic():
    h1 = compute_baseline_hash("abc")
    h2 = compute_baseline_hash("abc")
    h3 = compute_baseline_hash("abd")
    assert h1 == h2
    assert h1 != h3
    assert h1.startswith("sha256:")


def test_artifact_global_id():
    artifact = EvolvableArtifact(
        agent_name="research-bot",
        artifact_id="system",
        kind="prompt",
        baseline_text="x",
        text_source="param",
        source_file=Path("/tmp/x.py"),
        decorator_lineno=1,
    )
    assert artifact.global_id == "research-bot:system"
