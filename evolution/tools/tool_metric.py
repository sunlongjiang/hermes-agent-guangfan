"""Binary tool selection metric and cross-tool regression detection.

Provides:
- tool_selection_metric(): DSPy-compatible 0/1 metric for GEPA optimization
- CrossToolRegressionChecker: Post-optimization gate detecting per-tool regression
"""

import dspy
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from rich.console import Console

console = Console()


def tool_selection_metric(example: dspy.Example, prediction: dspy.Prediction, trace=None) -> float:
    """DSPy-compatible metric for tool selection. Returns 0.0 or 1.0.

    Exact string match after strip().lower() normalization.
    Per D-10: selected_tool.strip().lower() == correct_tool.strip().lower()
    Per D-11: Only tool name is scored, correct_params ignored.

    Args:
        example: DSPy Example with correct_tool field.
        prediction: DSPy Prediction with selected_tool field.
        trace: Unused, accepted for DSPy compatibility.

    Returns:
        1.0 if tool selection matches, 0.0 otherwise.
    """
    selected = getattr(prediction, "selected_tool", "") or ""
    correct = getattr(example, "correct_tool", "") or ""
    if selected.strip().lower() == correct.strip().lower():
        return 1.0
    return 0.0
