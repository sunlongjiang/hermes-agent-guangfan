"""Tests for @evolvable_agent / @evolvable_prompt / @evolvable_tool."""

import importlib
import sys
from pathlib import Path

import pytest

from evolution.sdk.decorators import (
    evolvable_agent, evolvable_prompt, evolvable_tool,
    ArtifactExtractionError,
)
from evolution.sdk import registry
from evolution.sdk.artifact import compute_baseline_hash


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "agents"


@pytest.fixture(autouse=True)
def _clean(clear_registry, monkeypatch):
    # Add fixtures dir to path so import works.
    if str(FIXTURE_DIR) not in sys.path:
        monkeypatch.syspath_prepend(str(FIXTURE_DIR.parent.parent))
    # Force re-import of fixture modules each test (so decorators re-run).
    for mod_name in list(sys.modules):
        if mod_name.startswith("fixtures.agents"):
            del sys.modules[mod_name]


def test_three_form_bot_registers_three_artifacts():
    # Import fixture (must succeed)
    importlib.import_module("fixtures.agents.three_form_bot")

    reg = registry.get_agent("three-form-bot")
    assert reg is not None
    assert len(reg.artifacts) == 3
    ids = {a.artifact_id for a in reg.artifacts}
    assert ids == {"system", "planner", "searcher"}


def test_form1_param_text_extracted():
    importlib.import_module("fixtures.agents.three_form_bot")
    reg = registry.get_agent("three-form-bot")
    a = next(a for a in reg.artifacts if a.artifact_id == "system")
    assert a.baseline_text == "You are FORM-1."
    assert a.text_source == "param"
    assert a.kind == "prompt"


def test_form2_return_value_extracted():
    importlib.import_module("fixtures.agents.three_form_bot")
    reg = registry.get_agent("three-form-bot")
    a = next(a for a in reg.artifacts if a.artifact_id == "planner")
    assert a.baseline_text == "Plan FORM-2 carefully."
    assert a.text_source == "return_value"


def test_form3_docstring_extracted():
    importlib.import_module("fixtures.agents.three_form_bot")
    reg = registry.get_agent("three-form-bot")
    a = next(a for a in reg.artifacts if a.artifact_id == "searcher")
    assert a.baseline_text == "FORM-3: search the web for the query."
    assert a.text_source == "docstring"
    assert a.kind == "tool"


def test_baseline_hash_matches_extracted_text():
    importlib.import_module("fixtures.agents.three_form_bot")
    reg = registry.get_agent("three-form-bot")
    a = next(a for a in reg.artifacts if a.artifact_id == "system")
    assert a.baseline_hash == compute_baseline_hash("You are FORM-1.")


def test_duplicate_artifact_id_raises_at_import():
    with pytest.raises(ArtifactExtractionError, match="duplicate artifact id"):
        importlib.import_module("fixtures.agents.bad_id_conflict")


def test_constraints_propagate_from_decorator():
    importlib.import_module("fixtures.agents.three_form_bot")
    reg = registry.get_agent("three-form-bot")
    a = next(a for a in reg.artifacts if a.artifact_id == "system")
    assert a.constraints.get("max_chars") == 2000


def test_evolvable_prompt_without_any_text_source_raises():
    with pytest.raises(ArtifactExtractionError, match="no text source"):
        @evolvable_prompt(id="empty")
        def no_text(self, x):  # has args → can't use return-value, no docstring, no text= → error
            return x


def test_evolvable_agent_records_source_file_and_lineno():
    importlib.import_module("fixtures.agents.three_form_bot")
    reg = registry.get_agent("three-form-bot")
    a = next(a for a in reg.artifacts if a.artifact_id == "system")
    assert a.source_file.name == "three_form_bot.py"
    assert a.decorator_lineno > 0


def test_evolvable_agent_class_carries_meta():
    mod = importlib.import_module("fixtures.agents.three_form_bot")
    assert hasattr(mod.ThreeFormBot, "_evolution_meta")
    assert mod.ThreeFormBot._evolution_meta["name"] == "three-form-bot"


def test_evolvable_agent_run_method_wrapped(monkeypatch):
    """Agent.run() should be intercepted so traces can be captured (Task 5 wires this)."""
    mod = importlib.import_module("fixtures.agents.three_form_bot")
    bot = mod.ThreeFormBot()
    # The method should be wrapped (different from the original)
    # We just verify the marker attribute exists; full trace test is Task 5.
    assert hasattr(bot.run, "__wrapped__") or hasattr(type(bot).run, "_evolution_wrapped")


def test_evolvable_agent_no_auto_persist(tmp_evolution_home, monkeypatch):
    """Decorator import期 must not write registry.json (production safety)."""
    monkeypatch.delenv("EVOLUTION_AUTO_REGISTER", raising=False)
    importlib.import_module("fixtures.agents.three_form_bot")
    assert not (tmp_evolution_home / "registry.json").exists()
