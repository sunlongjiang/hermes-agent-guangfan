"""Wave 0 RED test — ToolSelectionWithParamsSignature shape (Phase 13, D-05).

Encodes the contract: ToolSelectionWithParamsSignature is importable from
evolution.tools.tool_module and has exactly the right fields.
"""

import dspy
import pytest

from evolution.tools.tool_module import ToolSelectionWithParamsSignature


class TestSelectedParamsJsonShape:
    """D-05: ToolSelectionWithParamsSignature has the Phase 13 required fields."""

    def test_importable(self):
        """ToolSelectionWithParamsSignature is importable from evolution.tools.tool_module."""
        # Import already done at top; just assert it's a Signature subclass
        assert issubclass(ToolSelectionWithParamsSignature, dspy.Signature)

    def test_selected_params_json_shape(self):
        """Signature has: task_description (input), available_tools (input),
        selected_tool (output), selected_params (output — JSON string)."""
        fields = ToolSelectionWithParamsSignature.fields

        # Input fields
        assert "task_description" in fields, f"Missing task_description. Fields: {list(fields.keys())}"
        assert "available_tools" in fields, f"Missing available_tools. Fields: {list(fields.keys())}"
        # Output fields
        assert "selected_tool" in fields, f"Missing selected_tool. Fields: {list(fields.keys())}"
        assert "selected_params" in fields, f"Missing selected_params. Fields: {list(fields.keys())}"

    def test_field_directions(self):
        """task_description and available_tools are inputs; selected_tool and selected_params are outputs."""
        fields = ToolSelectionWithParamsSignature.fields

        def is_input(f):
            return getattr(f, "json_schema_extra", {}).get("prefix", "").strip().endswith("Input") or \
                   f.annotation is not None and (
                       hasattr(f, "json_schema_extra") and
                       f.json_schema_extra.get("__dspy_field_type", "") == "input"
                   )

        # Use DSPy's standard way: input_fields / output_fields via model_fields on the cls
        # DSPy Signature exposes .input_fields and .output_fields as class properties
        input_fields = ToolSelectionWithParamsSignature.input_fields
        output_fields = ToolSelectionWithParamsSignature.output_fields

        assert "task_description" in input_fields, (
            f"task_description should be input field. Input fields: {list(input_fields.keys())}"
        )
        assert "available_tools" in input_fields, (
            f"available_tools should be input field. Input fields: {list(input_fields.keys())}"
        )
        assert "selected_tool" in output_fields, (
            f"selected_tool should be output field. Output fields: {list(output_fields.keys())}"
        )
        assert "selected_params" in output_fields, (
            f"selected_params should be output field. Output fields: {list(output_fields.keys())}"
        )
