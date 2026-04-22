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


def tool_selection_metric(
    example: dspy.Example,
    prediction: dspy.Prediction,
    trace=None,
    pred_name=None,
    pred_trace=None,
) -> float:
    """DSPy-compatible metric for tool selection. Returns 0.0 or 1.0.

    Exact string match after strip().lower() normalization.
    Per D-10: selected_tool.strip().lower() == correct_tool.strip().lower()
    Per D-11: Only tool name is scored, correct_params ignored.

    Args:
        example: DSPy Example with correct_tool field.
        prediction: DSPy Prediction with selected_tool field.
        trace: Unused, accepted for DSPy/GEPA compatibility.
        pred_name: GEPA predictor name (unused).
        pred_trace: GEPA predictor trace (unused).

    Returns:
        1.0 if tool selection matches, 0.0 otherwise.
    """
    selected = getattr(prediction, "selected_tool", "") or ""
    correct = getattr(example, "correct_tool", "") or ""
    if selected.strip().lower() == correct.strip().lower():
        return 1.0
    return 0.0


# ── ToolRegressionResult ─────────────────────────────────────────────────────


@dataclass
class ToolRegressionResult:
    """Result of cross-tool regression check.

    Attributes:
        passed: True if no tool regressed beyond threshold.
        tool_results: Per-tool breakdown with baseline_rate, evolved_rate, delta.
        regression_threshold: Absolute percentage-point threshold (default 0.02).
        regressed_tools: Names of tools that regressed beyond threshold.
        message: Human-readable summary.
    """
    passed: bool
    tool_results: dict[str, dict] = field(default_factory=dict)
    regression_threshold: float = 0.02
    regressed_tools: list[str] = field(default_factory=list)
    message: str = ""


# ── CrossToolRegressionChecker ───────────────────────────────────────────────


class CrossToolRegressionChecker:
    """Post-optimization gate: rejects if any tool's selection rate drops >2pp.

    Per D-13: Baseline computed by running original descriptions on full eval dataset.
    Per D-14: Threshold is absolute 2 percentage points (NOT relative %).
    Per D-15: Runs once on holdout set as final gate, same pattern as constraint validation.
    """

    def __init__(self, regression_threshold: float = 0.02):
        self.regression_threshold = regression_threshold

    def compute_per_tool_rates(
        self,
        predictions: list[tuple[str, str]],
    ) -> dict[str, float]:
        """Compute per-tool selection accuracy.

        Args:
            predictions: List of (correct_tool, selected_tool) tuples.

        Returns:
            Dict mapping tool name to accuracy rate (0.0-1.0).
        """
        correct_counts: dict[str, int] = defaultdict(int)
        total_counts: dict[str, int] = defaultdict(int)

        for correct_tool, selected_tool in predictions:
            total_counts[correct_tool] += 1
            if selected_tool.strip().lower() == correct_tool.strip().lower():
                correct_counts[correct_tool] += 1

        rates: dict[str, float] = {}
        for tool, total in total_counts.items():
            if total > 0:
                rates[tool] = correct_counts[tool] / total
            else:
                rates[tool] = 0.0

        return rates

    def check_regression(
        self,
        baseline_rates: dict[str, float],
        evolved_rates: dict[str, float],
    ) -> ToolRegressionResult:
        """Compare baseline vs evolved per-tool rates.

        Per D-14: Any tool where baseline_rate - evolved_rate > self.regression_threshold
        triggers failure. Note: strictly greater than threshold (>), not >= .

        Args:
            baseline_rates: Per-tool accuracy before optimization.
            evolved_rates: Per-tool accuracy after optimization.

        Returns:
            ToolRegressionResult with passed=False if any regression detected.
        """
        from rich.table import Table

        tool_results: dict[str, dict] = {}
        regressed_tools: list[str] = []

        for tool, baseline_rate in baseline_rates.items():
            evolved_rate = evolved_rates.get(tool, 0.0)
            # Round to 10 decimal places to avoid floating-point comparison artifacts
            # e.g., 0.80 - 0.78 == 0.020000000000000018 without rounding
            delta = round(baseline_rate - evolved_rate, 10)

            tool_results[tool] = {
                "baseline_rate": baseline_rate,
                "evolved_rate": evolved_rate,
                "delta": delta,
            }

            if delta > self.regression_threshold:
                regressed_tools.append(tool)

        passed = len(regressed_tools) == 0

        # ── Rich table output ──
        table = Table(title="Cross-Tool Regression Check")
        table.add_column("Tool", style="bold")
        table.add_column("Baseline", justify="right")
        table.add_column("Evolved", justify="right")
        table.add_column("Delta", justify="right")
        table.add_column("Status")

        for tool, info in sorted(tool_results.items()):
            delta = info["delta"]
            status = "[red]REGRESSED[/red]" if delta > self.regression_threshold else "[green]OK[/green]"
            table.add_row(
                tool,
                f"{info['baseline_rate']:.1%}",
                f"{info['evolved_rate']:.1%}",
                f"{delta:+.2%}",
                status,
            )

        console.print(table)

        if passed:
            message = f"All {len(baseline_rates)} tools within {self.regression_threshold:.0%} regression threshold"
        else:
            message = (
                f"Regression detected in {len(regressed_tools)} tool(s): "
                f"{', '.join(regressed_tools)} "
                f"(threshold: {self.regression_threshold:.0%})"
            )

        return ToolRegressionResult(
            passed=passed,
            tool_results=tool_results,
            regression_threshold=self.regression_threshold,
            regressed_tools=regressed_tools,
            message=message,
        )
