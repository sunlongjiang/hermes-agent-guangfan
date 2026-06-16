"""Tests for hermes adapter — registers legacy 6-CLI pipeline as a single agent."""

import pytest

from evolution.adapters.hermes import register_hermes_adapter, HERMES_CLI_NAMES
from evolution.sdk import registry


@pytest.fixture(autouse=True)
def _clean(clear_registry):
    pass


def test_register_hermes_adapter_adds_agent():
    register_hermes_adapter(name="hermes")
    reg = registry.get_agent("hermes")
    assert reg is not None
    assert reg.module.startswith("evolution.adapters.hermes")
    assert reg.schedule_managed_by == "evolution-loop.yml"


def test_hermes_adapter_has_six_cli_artifacts():
    register_hermes_adapter(name="hermes")
    reg = registry.get_agent("hermes")
    ids = {a.artifact_id for a in reg.artifacts}
    assert ids == set(HERMES_CLI_NAMES)


def test_hermes_adapter_scaffold_skipped(tmp_path):
    """Hermes adapter must be skipped by scaffold (schedule_managed_by set)."""
    from evolution.sdk.scaffold import scaffold_gh_actions
    register_hermes_adapter(name="hermes")
    written = scaffold_gh_actions(output_dir=tmp_path)
    assert written == []  # nothing written for hermes


def test_hermes_adapter_artifacts_are_marked_tool_kind():
    """All 6 hermes CLIs operate on tool-like artifacts (descriptions/prompts)."""
    register_hermes_adapter(name="hermes")
    reg = registry.get_agent("hermes")
    # Six CLI names: skill, tool_descriptions, tool_params, tool_reasoning,
    # prompt_sections, code. Their EvolvableArtifact kind is best-effort:
    # we mark all of them as "prompt" except code (which is also prompt-ish for SDK).
    kinds = {a.kind for a in reg.artifacts}
    assert kinds.issubset({"prompt", "tool"})


def test_hermes_adapter_idempotent():
    register_hermes_adapter(name="hermes")
    register_hermes_adapter(name="hermes")  # second call must not raise
    assert "hermes" in registry.list_agents()
