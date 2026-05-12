"""Tool selection metrics and cross-tool regression detection.

Provides:
- tool_selection_metric(): DSPy-compatible 0/1 metric for GEPA optimization
- CrossToolRegressionChecker: Post-optimization gate detecting per-tool regression

Phase 13 additions:
- joint_tool_param_metric(): joint tool + param exact-match metric (D-10, D-17).
  Use as acceptance gate / holdout scorer (returns plain float).
- joint_tool_param_metric_with_feedback(): GEPA-facing ScoreWithFeedback variant
  (Pitfall 7 mitigation). Returns dspy.Prediction(score, feedback) for attribute-
  safe consumption by reflection_lm. Do NOT use for acceptance / holdout scoring.
"""

import dspy
import json
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


# ── Joint Tool-Param Metric (Phase 13: D-10, D-17) ───────────────────────────


# Normalization rule sourced from Wave 0 dataset inspection
# (see .planning/phases/13-per-parameter-description-optimization/
# 13-correct-params-type-inspection.txt). Value distribution showed 6 value
# types (str=363, int=26, list=19, bool=15, dict=7, float=3), so the
# recommendation is `strip_plus_coerce`: strip whitespace on strings AND try
# cross-type numeric coercion (e.g. "123" vs 123, "true" vs True) so LLM
# stringified outputs do not spuriously break exact-match against typed
# correct_params values.
_NORMALIZATION_RULE = "strip_plus_coerce"


def _coerce_scalar(v):
    """Try to coerce a string scalar to its natural type (int/float/bool).

    Returns the coerced value if the conversion is unambiguous; otherwise
    returns the stripped string. Only used when _NORMALIZATION_RULE ==
    "strip_plus_coerce". Non-string, non-bool inputs are returned unchanged.

    Bools are preserved distinctly from ints per PEP 285 (isinstance order
    matters: check bool BEFORE int since bool is a subclass of int).
    """
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v
    if not isinstance(v, str):
        return v
    s = v.strip()
    # bool-ish strings
    lowered = s.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    # int first (so "1" becomes int 1, not float 1.0)
    try:
        return int(s)
    except (TypeError, ValueError):
        pass
    try:
        return float(s)
    except (TypeError, ValueError):
        pass
    return s


def _normalize_param_value(v):
    """Light normalization for joint-metric param value comparison.

    Policy (evidence-based from 13-01 Wave 0 inspection output
    NORMALIZATION_RULE=strip_plus_coerce):
    - Strings: str.strip(), then attempt int/float/bool coerce if policy allows.
    - Containers (list / dict): recursively normalize element values to handle
      e.g. `{"service_data": {"brightness": "180"}}` vs {"brightness": 180}`.
    - bool / int / float / None: returned as-is.

    When _NORMALIZATION_RULE == "strip_only", only string stripping occurs; no
    type coercion. The "strip_plus_coerce" branch is the Phase 13 default
    because the dataset has 6 value types and LLMs frequently stringify
    numeric outputs.
    """
    if isinstance(v, str):
        if _NORMALIZATION_RULE == "strip_plus_coerce":
            return _coerce_scalar(v)
        return v.strip()
    if isinstance(v, list):
        return [_normalize_param_value(item) for item in v]
    if isinstance(v, dict):
        return {k: _normalize_param_value(val) for k, val in v.items()}
    return v


def _parse_selected_params_json(raw) -> Optional[dict]:
    """Parse a selected_params value into a dict, or None on malformed input.

    Returns:
        dict if the raw string parses to a JSON object (or the input is
        already a dict); None on any parse failure / non-object / non-dict
        result. None signals "do not award param_match credit" (Pitfall 7 +
        T-13-08 mitigation): malformed LLM output is explicitly penalized
        rather than silently awarded partial credit.
    """
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        try:
            return dict(raw)
        except (TypeError, ValueError):
            return None
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _param_match_score(
    predicted_params: Optional[dict], correct_params: dict
) -> float:
    """Return 1.0 iff dict-equal after normalization; 0.0 otherwise.

    Pitfall 4 mitigation: strip + coerce normalization applied to both sides
    so trailing whitespace, stringified numerics, and case-varied bool
    literals in LLM output do not spuriously break exact match.
    """
    if predicted_params is None:
        return 0.0
    if set(predicted_params.keys()) != set(correct_params.keys()):
        return 0.0
    for k, v_correct in correct_params.items():
        v_pred = predicted_params.get(k)
        if _normalize_param_value(v_correct) != _normalize_param_value(v_pred):
            return 0.0
    return 1.0


def joint_tool_param_metric(
    example: dspy.Example,
    prediction: dspy.Prediction,
    trace=None,
    pred_name=None,
    pred_trace=None,
) -> float:
    """Joint tool + param metric (D-10, D-17).

    Returns:
        float in [0.0, 1.0]: 0.5 * tool_match + 0.5 * param_match, both
        exact-match after strip+lower normalization (tool_match) or
        strip+coerce value comparison (param_match).

    Contract (D-10):
        - tool_match = 1.0 iff selected_tool.strip().lower() == correct_tool.strip().lower()
        - param_match = 1.0 iff parsed selected_params dict-equals correct_params
          after strip_plus_coerce normalization
        - Malformed JSON in selected_params -> param_match = 0.0 (Pitfall 7)
        - Signature is GEPA's 5-param form (gepa.py:368 binding check).

    Args:
        example: DSPy Example with correct_tool and correct_params fields.
        prediction: DSPy Prediction with selected_tool (str) and
            selected_params (JSON string) fields.
        trace: Unused, accepted for DSPy/GEPA compatibility.
        pred_name: GEPA predictor name (unused).
        pred_trace: GEPA predictor trace (unused).

    Returns:
        Composite score in [0.0, 1.0].
    """
    selected_tool = (getattr(prediction, "selected_tool", "") or "").strip().lower()
    correct_tool = (getattr(example, "correct_tool", "") or "").strip().lower()
    tool_match = 1.0 if selected_tool == correct_tool else 0.0

    correct_params = getattr(example, "correct_params", {}) or {}
    raw = getattr(prediction, "selected_params", "")
    predicted = _parse_selected_params_json(raw)
    param_match = _param_match_score(predicted, correct_params)

    return 0.5 * tool_match + 0.5 * param_match


def joint_tool_param_metric_with_feedback(
    example: dspy.Example,
    prediction: dspy.Prediction,
    trace=None,
    pred_name=None,
    pred_trace=None,
) -> dspy.Prediction:
    """GEPA-facing metric returning ScoreWithFeedback (Pitfall 7 mitigation).

    Returns:
        dspy.Prediction with:
            - score (float): identical to joint_tool_param_metric()'s return.
            - feedback (str): short human-readable reason string that GEPA's
              reflection_lm uses when proposing new param descriptions.

    Why dspy.Prediction and not a bare dict:
        DSPy 3.1.3's GEPA reflection code paths use attribute access
        (`result.score`, `result.feedback`) on the metric return. A bare
        `{"score": ..., "feedback": ...}` dict would require subscript
        access and is NOT guaranteed compatible across all GEPA 3.1.3
        internals. `dspy.Prediction` exposes both attribute AND dict-style
        access, so it is the safe cross-path return type.

    Important:
        Do NOT use this for acceptance / holdout scoring -- use
        joint_tool_param_metric (plain float) instead. Mixing the two in
        cross-tool regression gates would break the CrossToolRegressionChecker
        contract (expects float input).

    Info-disclosure stance (T-13-09 mitigation): feedback only names keys and
    summarizes diff class ("missing keys", "wrong values"); does NOT echo the
    full correct_params dict verbatim. Accepted risk for Phase 13 single-user
    CLI; Phase 22 continuous loop will need tighter redaction.
    """
    score = joint_tool_param_metric(
        example, prediction, trace, pred_name, pred_trace
    )
    correct_tool = (getattr(example, "correct_tool", "") or "").strip().lower()
    selected_tool = (getattr(prediction, "selected_tool", "") or "").strip().lower()
    correct_params = getattr(example, "correct_params", {}) or {}
    raw = getattr(prediction, "selected_params", "")
    predicted = _parse_selected_params_json(raw)

    fb_parts: list[str] = []
    if selected_tool != correct_tool:
        fb_parts.append(
            f"Wrong tool: picked '{selected_tool}', expected '{correct_tool}'."
        )
    if predicted is None:
        fb_parts.append(
            "selected_params was not valid JSON; return a JSON object like "
            "'{\"pattern\":\"foo\"}'."
        )
    else:
        # Normalize both sides once for mismatch analysis.
        norm_correct = {k: _normalize_param_value(v) for k, v in correct_params.items()}
        norm_predicted = {k: _normalize_param_value(v) for k, v in predicted.items()}
        if norm_predicted != norm_correct:
            missing = sorted(set(norm_correct) - set(norm_predicted))
            extra = sorted(set(norm_predicted) - set(norm_correct))
            bad_val = sorted(
                k for k in set(norm_correct) & set(norm_predicted)
                if norm_correct[k] != norm_predicted[k]
            )
            fb_parts.append(
                f"Param mismatch -- missing keys: {missing}; extra keys: {extra};"
                f" wrong values for keys: {bad_val}."
            )
    if not fb_parts:
        fb_parts.append("Perfect match.")

    return dspy.Prediction(score=float(score), feedback=" ".join(fb_parts))


# ── Per-Tool Rate Persistence (Phase 13: D-12) ───────────────────────────────


def persist_per_tool_rates(
    metrics: dict,
    baseline_rates: dict[str, float],
    evolved_rates: dict[str, float],
) -> dict:
    """Merge per-tool rate dicts into a metrics dict (for metrics.json).

    Closes folded todo 2026-05-07-persist-per-tool-regression-rates.md.
    Extends CONCERNS §M3's pass/fail-only gate with full per-tool rate
    persistence so Phase 16's dashboard has raw data to aggregate.

    The function:
    - Does NOT mutate its inputs (returns a shallow copy of metrics).
    - Coerces every rate value to float for safe json.dumps serialization.
    - Sorts keys in both rate dicts alphabetically for stable diffs across runs.

    Args:
        metrics: The in-progress metrics dict that will be serialized to
            metrics.json by the CLI (13-08).
        baseline_rates: Per-tool accuracy BEFORE optimization
            (CrossToolRegressionChecker.compute_per_tool_rates output).
        evolved_rates: Per-tool accuracy AFTER optimization (same shape).

    Returns:
        A new dict equal to `metrics` plus two keys:
            - per_tool_baseline_rates: {tool: float}
            - per_tool_evolved_rates: {tool: float}
    """
    out = dict(metrics)  # shallow copy — callers may reuse `metrics` afterwards
    out["per_tool_baseline_rates"] = {
        k: float(v) for k, v in sorted((baseline_rates or {}).items())
    }
    out["per_tool_evolved_rates"] = {
        k: float(v) for k, v in sorted((evolved_rates or {}).items())
    }
    return out


# ── Raw Predictions Persistence (Phase 16: D-12 dashboard) ───────────────────


def persist_raw_predictions(
    metrics: dict,
    raw_predictions: list[dict],
) -> dict:
    """Merge raw_predictions list into a metrics dict (Phase 16: D-12 dashboard).

    Pattern matches persist_per_tool_rates: shallow copy of metrics, None
    tolerance, stable schema. Differs from persist_per_tool_rates: does NOT
    sort (raw_predictions is order-sensitive time-series); does NOT all-float-
    coerce (per-field types are str/str/str/int); emits stdout yellow warning
    when len > 2000 (Pitfall 10 retention placeholder).

    Args:
        metrics: The in-progress metrics dict to extend.
        raw_predictions: List of per-prediction dicts, each with fields:
            correct_tool (str), selected_tool (str), difficulty (str),
            num_available_tools (int).

    Returns:
        A new dict equal to `metrics` plus one key:
            - raw_predictions: list[dict] with schema
              {correct_tool, selected_tool, difficulty, num_available_tools}
    """
    out = dict(metrics)  # shallow copy
    cleaned: list[dict] = []
    for rec in (raw_predictions or []):
        cleaned.append({
            "correct_tool": str(rec.get("correct_tool", "") or ""),
            "selected_tool": str(rec.get("selected_tool", "") or ""),
            "difficulty": str(rec.get("difficulty", "medium") or "medium"),
            "num_available_tools": int(rec.get("num_available_tools", 0) or 0),
        })
    out["raw_predictions"] = cleaned
    if len(cleaned) > 2000:
        console.print(
            f"[yellow]raw_predictions large ({len(cleaned)} records); "
            f"metrics.json may exceed 1MB[/yellow]"
        )
    return out
