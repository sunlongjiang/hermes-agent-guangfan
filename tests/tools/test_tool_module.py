"""Tests for ToolModule -- DSPy module wrapping tool descriptions for GEPA optimization."""

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

    def test_named_predictors_count(self):
        """ToolModule with 3 tools should expose 4 named predictors (3 tools + 1 selector)."""
        tools = _make_tool_descriptions()
        module = ToolModule(tools)
        predictors = list(module.named_predictors())
        assert len(predictors) == 4, f"Expected 4 predictors, got {len(predictors)}"

    def test_tool_predictor_instructions_match_descriptions(self):
        """Each tool predictor's signature instructions should match the input description."""
        tools = _make_tool_descriptions()
        module = ToolModule(tools)

        assert module.tool_predictors["memory"].signature.instructions == "Store and retrieve conversation memory"
        assert module.tool_predictors["terminal"].signature.instructions == "Execute shell commands"
        assert module.tool_predictors["list_files"].signature.instructions == "List files in a directory"

    def test_forward_returns_prediction(self):
        """forward() should return a dspy.Prediction with selected_tool attribute."""
        tools = _make_tool_descriptions()
        module = ToolModule(tools)

        # Mock the selector's __call__ to avoid LLM calls
        mock_result = dspy.Prediction(selected_tool="memory")
        with patch.object(module.selector, "__call__", return_value=mock_result):
            result = module.forward("store user preference")

        assert isinstance(result, dspy.Prediction)
        assert result.selected_tool == "memory"

    def test_empty_description_gets_default(self):
        """ToolDescription with empty description should get 'Tool: {name}' as default."""
        tools = [
            ToolDescription(
                name="memory",
                file_path=Path("/fake/memory.py"),
                description="",
            ),
        ]
        module = ToolModule(tools)
        assert module.tool_predictors["memory"].signature.instructions == "Tool: memory"

    def test_hyphenated_name_safe(self):
        """Hyphenated tool names should be stored with underscores in tool_predictors."""
        tools = _make_tool_descriptions()
        module = ToolModule(tools)
        assert "list_files" in module.tool_predictors
        assert "list-files" not in module.tool_predictors


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

    def test_evolved_descriptions_preserve_schema(self):
        """After modifying predictor instructions, get_evolved_descriptions() should
        return new description text but preserve original frozen fields."""
        tools = _make_tool_descriptions()
        module = ToolModule(tools)

        # Simulate GEPA evolving the memory tool's description
        module.tool_predictors["memory"].signature = (
            module.tool_predictors["memory"].signature.with_instructions("EVOLVED memory desc")
        )

        evolved = module.get_evolved_descriptions()

        # Find the memory tool in the evolved list
        memory_tool = next(t for t in evolved if t.name == "memory")
        assert memory_tool.description == "EVOLVED memory desc"
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
        """Manually set predictor instructions should appear in evolved descriptions."""
        tools = _make_tool_descriptions()
        module = ToolModule(tools)

        # Evolve terminal's description
        module.tool_predictors["terminal"].signature = (
            module.tool_predictors["terminal"].signature.with_instructions("Run commands in shell environment")
        )

        evolved = module.get_evolved_descriptions()
        terminal_tool = next(t for t in evolved if t.name == "terminal")
        assert terminal_tool.description == "Run commands in shell environment"
