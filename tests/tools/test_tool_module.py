"""Phase 3 ToolModule tests -- MIGRATED for Phase 13 (per-param structure).

Previous Phase 3 contract: module.tool_predictors_dict[name].signature.instructions
Phase 13 replacement:
  - tool-level text: module._frozen_tool_desc[name]  (frozen, dict[str,str])
  - param-level text: module.tools[safe_name].param_predictors[param_name]
                      .signature.instructions

All 10 prior call sites into the old tool_predictors attribute migrated;
hard-coded `len(predictors) == 4` replaced with `N_params + 1` formula (see
test_named_predictors_count_is_params_plus_selector).
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

import dspy
import pytest

from evolution.tools.tool_loader import ToolDescription, ToolParam
from evolution.tools.tool_module import ToolModule


# ── Test Fixtures ───────────────────────────────────────────────────────────

def _make_tool_descriptions() -> list[ToolDescription]:
    """Create 3 test ToolDescription instances covering varied schema shapes."""
    return [
        ToolDescription(
            name="memory",
            file_path=Path("/fake/memory.py"),
            description="Store and retrieve conversation memory",
            params=[
                ToolParam(name="action", type="string", required=True, enum=["store", "retrieve"]),
                ToolParam(name="key", type="string", required=True),
            ],
        ),
        ToolDescription(
            name="terminal",
            file_path=Path("/fake/terminal.py"),
            description="Execute shell commands",
            params=[
                ToolParam(name="command", type="string", required=True),
            ],
        ),
        ToolDescription(
            name="list-files",
            file_path=Path("/fake/list_files.py"),
            description="List files in a directory",
            params=[
                ToolParam(name="path", type="string", required=True),
            ],
        ),
    ]


# ── TestToolModule ──────────────────────────────────────────────────────────

class TestToolModule:
    """Core ToolModule construction and forward pass tests."""

    def test_named_predictors_count_is_params_plus_selector(self):
        """ToolModule with 3 tools should expose N_params + selector predictors.

        Fixture tools have: memory (2 params) + terminal (1 param) + list-files (1 param)
        = 4 per-param predictors. ChainOfThought selector adds 1. Total >= 5.
        Also assert exactly 4 per-param entries (via .param_predictors[ pattern).
        """
        tools = _make_tool_descriptions()
        module = ToolModule(tools)
        predictors = list(module.named_predictors())

        # Count per-param entries explicitly
        param_entries_count = sum(1 for n, _ in predictors if ".param_predictors[" in n)
        assert param_entries_count == 4, (
            f"Expected 4 per-param predictors (N_params), got {param_entries_count}. "
            f"All names: {[n for n, _ in predictors]}"
        )

        # Total: at least N_params + 1 (selector) = 5
        total = len(predictors)
        n_params = 4
        assert total >= n_params + 1, (
            f"Expected >= {n_params + 1} total predictors, got {total}"
        )
        # Sanity upper bound
        assert total <= 10, (
            f"Total predictors suspiciously large: {total}. Check for unexpected registrations."
        )

    def test_frozen_tool_descriptions_match_input(self):
        """_frozen_tool_desc should map each tool's original name to its description."""
        tools = _make_tool_descriptions()
        module = ToolModule(tools)

        # Note: _frozen_tool_desc uses the ORIGINAL tool name (not safe-key)
        assert module._frozen_tool_desc["memory"] == "Store and retrieve conversation memory"
        assert module._frozen_tool_desc["terminal"] == "Execute shell commands"
        assert module._frozen_tool_desc["list-files"] == "List files in a directory"

    def test_forward_returns_prediction(self):
        """forward() should return a dspy.Prediction with selected_tool and selected_params."""
        tools = _make_tool_descriptions()
        module = ToolModule(tools)

        # Mock the selector's forward to avoid LLM calls
        mock_result = dspy.Prediction(selected_tool="memory", selected_params='{"action":"store","key":"pref"}')
        with patch.object(module.selector, "forward", return_value=mock_result):
            result = module.forward("store user preference")

        assert isinstance(result, dspy.Prediction)
        assert result.selected_tool == "memory"
        assert result.selected_params == '{"action":"store","key":"pref"}'

    def test_empty_description_frozen_desc_and_empty_param_predictor(self):
        """ToolDescription with empty description: _frozen_tool_desc gets 'Tool: {name}';
        every param in .tools['memory'].param_predictors is a dspy.Predict."""
        tools = [
            ToolDescription(
                name="memory",
                file_path=Path("/fake/memory.py"),
                description="",
                params=[
                    ToolParam(name="action", type="string", required=True, enum=["store", "retrieve"]),
                    ToolParam(name="key", type="string", required=True),
                ],
            ),
        ]
        module = ToolModule(tools)

        # (a) tool-level: defaults to "Tool: memory"
        assert module._frozen_tool_desc["memory"] == "Tool: memory"

        # (b) param-level: both params present as dspy.Predict instances
        bundle = module.tools["memory"]
        assert "action" in bundle.param_predictors
        assert "key" in bundle.param_predictors
        assert isinstance(bundle.param_predictors["action"], dspy.Predict)
        assert isinstance(bundle.param_predictors["key"], dspy.Predict)

    def test_hyphenated_name_safe(self):
        """Hyphenated tool names should be stored with underscores in tools dict."""
        tools = _make_tool_descriptions()
        module = ToolModule(tools)
        assert "list_files" in module.tools
        assert "list-files" not in module.tools


# ── TestSchemaFreeze ────────────────────────────────────────────────────────

class TestSchemaFreeze:
    """Verify schema frozen fields are not exposed to DSPy optimizer."""

    def test_frozen_fields_not_optimizable(self):
        """named_parameters() should not yield ToolDescription or ToolParam objects."""
        tools = _make_tool_descriptions()
        module = ToolModule(tools)

        for param_name, param_value in module.named_parameters():
            assert not isinstance(param_value, ToolDescription), (
                f"ToolDescription found in named_parameters at {param_name}"
            )
            assert not isinstance(param_value, ToolParam), (
                f"ToolParam found in named_parameters at {param_name}"
            )

    def test_evolved_descriptions_preserve_schema_and_evolve_params(self):
        """Mutating a param Predict signature propagates to get_evolved_descriptions();
        tool-level description stays frozen (D-02)."""
        tools = _make_tool_descriptions()
        module = ToolModule(tools)

        # Mutate the action param's signature in memory bundle
        module.tools["memory"].param_predictors["action"].signature = (
            module.tools["memory"].param_predictors["action"].signature.with_instructions(
                "EVOLVED action param desc"
            )
        )

        evolved = module.get_evolved_descriptions()

        # Find the memory tool in the evolved list
        memory_tool = next(t for t in evolved if t.name == "memory")

        # Tool-level description stays frozen (D-02)
        assert memory_tool.description == "Store and retrieve conversation memory"

        # Param-level description is evolved
        assert memory_tool.params[0].description == "EVOLVED action param desc"

        # Schema frozen fields preserved
        assert len(memory_tool.params) == 2
        assert memory_tool.params[0].name == "action"
        assert memory_tool.params[0].enum == ["store", "retrieve"]
        assert memory_tool.params[1].name == "key"
        assert memory_tool.file_path == Path("/fake/memory.py")
        assert memory_tool.name == "memory"


# ── TestGetEvolvedDescriptions ──────────────────────────────────────────────

class TestGetEvolvedDescriptions:
    """Tests for get_evolved_descriptions() output shape and content."""

    def test_returns_tool_description_list(self):
        """get_evolved_descriptions() should return list[ToolDescription] with correct length."""
        tools = _make_tool_descriptions()
        module = ToolModule(tools)
        evolved = module.get_evolved_descriptions()

        assert isinstance(evolved, list)
        assert len(evolved) == 3
        assert all(isinstance(t, ToolDescription) for t in evolved)

    def test_description_reflects_predictor_instructions(self):
        """Manually set param predictor instructions appear in evolved descriptions;
        tool-level description stays frozen."""
        tools = _make_tool_descriptions()
        module = ToolModule(tools)

        # Evolve terminal's command param description
        module.tools["terminal"].param_predictors["command"].signature = (
            module.tools["terminal"].param_predictors["command"].signature.with_instructions(
                "Run commands in shell environment"
            )
        )

        evolved = module.get_evolved_descriptions()
        terminal_tool = next(t for t in evolved if t.name == "terminal")

        # Param evolved
        assert terminal_tool.params[0].description == "Run commands in shell environment"

        # Tool-level stays frozen (D-02)
        assert terminal_tool.description == "Execute shell commands"
