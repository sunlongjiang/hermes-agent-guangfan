"""Phase 15 shared fixtures for tests/tools/.

Created Wave 0 to support test_think_metrics.py and test_evolve_tool_reasoning.py.
Mocks ToolModule(enable_reasoning=True) with mocked LMs (zero real API calls).
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evolution.tools.tool_loader import ToolDescription, ToolParam


@pytest.fixture
def fake_tools() -> list[ToolDescription]:
    """Minimal 2-tool fixture for ToolModule construction tests."""
    return [
        ToolDescription(
            name="search",
            file_path=Path("/fake/search.py"),
            description="Search for stuff",
            params=[
                ToolParam(name="q", type="string", required=True, description="query"),
            ],
        ),
        ToolDescription(
            name="read_file",
            file_path=Path("/fake/read_file.py"),
            description="Read file contents",
            params=[
                ToolParam(name="path", type="string", required=True, description="file path"),
            ],
        ),
    ]


@pytest.fixture
def mock_reasoning_module(fake_tools):
    """ToolModule(enable_reasoning=True) with mocked LMs (zero real API calls).

    Returns a ToolModule instance whose selector and reasoner attrs are MagicMock
    instances returning canned dspy.Prediction objects. Used by test_think_metrics.py
    and test_evolve_tool_reasoning.py.

    NOTE: enable_reasoning kwarg added in Wave 1; this fixture will RED-fail
    until Wave 1 lands. That is expected — fixture exists so Wave 1 tests
    can immediately consume it once enable_reasoning is added.
    """
    pytest.importorskip("dspy")
    import dspy
    # Patch dspy.LM at module load to avoid real API key lookup.
    with patch("evolution.tools.tool_module.dspy.LM") as mock_lm_cls:
        mock_lm_cls.return_value = MagicMock()
        from evolution.tools.tool_module import ToolModule
        # NOTE: enable_reasoning kwarg added in Wave 1; this fixture will RED-fail
        # until Wave 1 lands. That is expected — fixture exists so Wave 1 tests
        # can immediately consume it once enable_reasoning is added.
        module = ToolModule(fake_tools, enable_reasoning=True)
    module.selector = MagicMock(return_value=dspy.Prediction(
        selected_tool="search",
        selected_params="{}",
    ))
    module.reasoner = MagicMock(return_value=dspy.Prediction(
        reasoning="(mock reasoning text)",
    ))
    return module
