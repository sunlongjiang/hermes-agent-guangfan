"""Wave 0 RED tests — per-parameter Predict discovery (Phase 13).

These tests encode the D-01/D-02/D-03/D-04 contracts before any implementation
change. They are expected to FAIL against the current Phase 3 ToolModule and
PASS only after the Phase 13 sub-Module-per-tool upgrade.
"""

from pathlib import Path

import dspy
import pytest

from evolution.tools.tool_loader import ToolDescription, ToolParam
from evolution.tools.tool_module import ToolModule


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_3x3_tools() -> list[ToolDescription]:
    """3 tools each with 3 params — 9 total per-param predictors expected."""
    return [
        ToolDescription(
            name="search_files",
            file_path=Path("/fake/search.py"),
            description="Search files by pattern",
            params=[
                ToolParam(name="pattern", type="string", required=True, description="Search regex pattern"),
                ToolParam(name="file_pattern", type="string", required=False, description="File glob pattern"),
                ToolParam(name="case_sensitive", type="boolean", required=False, description="Case-sensitive match"),
            ],
        ),
        ToolDescription(
            name="read_file",
            file_path=Path("/fake/read.py"),
            description="Read file contents",
            params=[
                ToolParam(name="path", type="string", required=True, description="File path to read"),
                ToolParam(name="encoding", type="string", required=False, description="File encoding"),
                ToolParam(name="max_bytes", type="integer", required=False, description="Maximum bytes to read"),
            ],
        ),
        ToolDescription(
            name="write_file",
            file_path=Path("/fake/write.py"),
            description="Write content to file",
            params=[
                ToolParam(name="path", type="string", required=True, description="Destination file path"),
                ToolParam(name="content", type="string", required=True, description="Content to write"),
                ToolParam(name="append", type="boolean", required=False, description="Append instead of overwrite"),
            ],
        ),
    ]


def _make_tool_with_empty_param_desc() -> list[ToolDescription]:
    """1 tool with 2 params, one of which has empty description (D-03)."""
    return [
        ToolDescription(
            name="memory",
            file_path=Path("/fake/memory.py"),
            description="",  # also empty tool-level desc → defaults to 'Tool: memory'
            params=[
                ToolParam(name="action", type="string", required=True, enum=["store", "retrieve"], description=""),
                ToolParam(name="key", type="string", required=True, description=""),
            ],
        ),
    ]


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestNamedParametersDiscovery:
    """Success Criterion 1: named_predictors() returns one entry per (tool, param) pair."""

    def test_named_parameters_discovery(self):
        """3 tools × 3 params = 9 per-param predictors discoverable by named_predictors().

        D-01 via RESEARCH §Pattern 1 sub-Module-per-tool.
        D-04 hierarchical naming preserved.
        """
        tools = _make_3x3_tools()
        tm = ToolModule(tools)
        names = [n for n, _ in tm.named_predictors()]

        # At least 9 entries with the per-param naming pattern
        param_entries = [n for n in names if ".param_predictors[" in n]
        assert len(param_entries) == 9, (
            f"Expected 9 per-param predictor entries, got {len(param_entries)}. "
            f"All names: {names}"
        )

    def test_key_hierarchy_preserved(self):
        """Predictor keys follow tools['<tool>'].param_predictors['<param>'] shape (D-04)."""
        tools = _make_3x3_tools()
        tm = ToolModule(tools)
        names = [n for n, _ in tm.named_predictors()]

        # search_files safe name is search_files (no hyphen)
        assert any("tools['search_files'].param_predictors['pattern']" in n for n in names), (
            f"Expected pattern param path in named_predictors. Got: {names}"
        )
        assert any("tools['read_file'].param_predictors['encoding']" in n for n in names), (
            f"Expected encoding param path in named_predictors. Got: {names}"
        )
        assert any("tools['write_file'].param_predictors['append']" in n for n in names), (
            f"Expected append param path in named_predictors. Got: {names}"
        )


class TestToolDescriptionFrozen:
    """Success Criterion 2: tool-level description is physically isolated in _frozen_tool_desc."""

    def test_tool_description_frozen(self):
        """_frozen_tool_desc is dict[str, str] — every value is a str, not Predict or Module (D-02)."""
        tools = _make_3x3_tools()
        tm = ToolModule(tools)

        assert hasattr(tm, "_frozen_tool_desc"), "_frozen_tool_desc attribute must exist"
        assert isinstance(tm._frozen_tool_desc, dict), "_frozen_tool_desc must be a dict"

        for key, val in tm._frozen_tool_desc.items():
            assert isinstance(val, str), (
                f"_frozen_tool_desc['{key}'] must be str, got {type(val).__name__}"
            )

        # No entry in named_predictors() should have _frozen_tool_desc in its key
        names = [n for n, _ in tm.named_predictors()]
        frozen_hits = [n for n in names if "_frozen_tool_desc" in n]
        assert len(frozen_hits) == 0, (
            f"_frozen_tool_desc should NOT appear in named_predictors. Found: {frozen_hits}"
        )

    def test_frozen_desc_keyed_by_original_name(self):
        """_frozen_tool_desc uses the original tool name (not safe-key) (D-02)."""
        tools = [
            ToolDescription(
                name="list-files",
                file_path=Path("/fake/list.py"),
                description="List files in directory",
                params=[ToolParam(name="path", type="string", required=True, description="Directory path")],
            )
        ]
        tm = ToolModule(tools)
        # Original hyphenated name must be the key
        assert "list-files" in tm._frozen_tool_desc, (
            f"Expected 'list-files' key in _frozen_tool_desc, got: {list(tm._frozen_tool_desc.keys())}"
        )
        assert tm._frozen_tool_desc["list-files"] == "List files in directory"


class TestEmptyParamRegistered:
    """D-03: empty param descriptions still get a Predict registered."""

    def test_empty_param_registered(self):
        """ToolParam with description='' still yields a discoverable Predict (D-03)."""
        tools = _make_tool_with_empty_param_desc()
        tm = ToolModule(tools)
        names = [n for n, _ in tm.named_predictors()]

        param_entries = [n for n in names if ".param_predictors[" in n]
        # Both 'action' and 'key' params must be registered
        assert any("param_predictors['action']" in n for n in param_entries), (
            f"Expected 'action' param predictor, got: {names}"
        )
        assert any("param_predictors['key']" in n for n in param_entries), (
            f"Expected 'key' param predictor, got: {names}"
        )

    def test_empty_param_predictor_is_a_dspy_predict(self):
        """Empty-description params still produce a dspy.Predict instance (not None).

        Note: DSPy 3.1.3 replaces instructions='' with a default template string
        ('Given the fields...'). We assert the Predict exists and is a dspy.Predict,
        not that its instructions are literally ''. The D-03 contract is that every
        param is registered, not that the instructions value is ''.
        """
        tools = _make_tool_with_empty_param_desc()
        tm = ToolModule(tools)
        safe = "memory"
        bundle = tm.tools[safe]
        assert isinstance(bundle.param_predictors["action"], dspy.Predict), (
            f"Expected dspy.Predict for 'action' param, got: "
            f"{type(bundle.param_predictors['action'])}"
        )
        assert isinstance(bundle.param_predictors["key"], dspy.Predict), (
            f"Expected dspy.Predict for 'key' param, got: "
            f"{type(bundle.param_predictors['key'])}"
        )
