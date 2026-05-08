"""v1 baseline hard-gate for Phase 13 per-param optimization (D-14).

Phase 13 evolved holdout score must NOT regress more than 2pp below the
v1 (Phase 5) baseline. The gate supports two baseline sources:

1. Historical -- user passes --baseline-run <dir> pointing at a completed
   Phase 5 output directory; we read `evolved_score` from its metrics.json.
2. Inline -- no --baseline-run (or path not found): we construct a baseline
   ToolModule from the original ToolDescription list and evaluate it on the
   same holdout with joint_tool_param_metric. Result is labeled
   v1_baseline_source='inline' to signal the gate's semantics degrade to
   "do not regress against self" rather than "do not regress against v1".

Semantics (RESEARCH Pitfall 8):
- The gate FAILS if evolved_score < v1_baseline_score - tolerance (default 0.02).
- Floating-point delta is rounded to 10 decimal places before comparison
  (same pattern as CrossToolRegressionChecker).
- The module does NOT create FAILED_ directories or write files -- that is
  the CLI's job (13-08). This keeps the gate testable without filesystem
  side-effects.

Phase 13 scope guard: this module MUST NOT import or invoke
evolution.tools.tool_loader.write_back_description. Write-back is deferred
to Phase 22 per CONTEXT.md. Output for Phase 13 runs stays in output/tools/.

Wave 0 RED test contract (tests/tools/test_v1_baseline_gate.py):
- check_v1_baseline_gate(...) returns evolution.core.constraints.ConstraintResult.
- compute_v1_baseline(baseline_run, baseline_module=, holdout=, lm=) returns
  a dict with keys v1_baseline_source / v1_baseline_holdout (and optionally
  metrics_source_path).
The dict-shaped, dataclass-style results required by 13-07 PLAN.md (passed /
delta / tolerance_pp / evolved_score / baseline_score / message) are exposed
via _compute_baseline_gate_metrics() helper and the V1BaselineGate.check()
facade.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import dspy

from evolution.core.constraints import ConstraintResult
from evolution.tools.tool_metric import joint_tool_param_metric


# ── Internal: gate metrics dict (calculation only, no semantics binding) ────


def _compute_baseline_gate_metrics(
    evolved_score: float,
    baseline_score: float,
    tolerance: float = 0.02,
) -> dict:
    """Compute the raw gate metrics as a dict.

    Returns dict with passed / delta / tolerance_pp / evolved_score /
    baseline_score / message. This is the data shape called for by
    13-07 PLAN.md and is the building block for V1BaselineGate.check().
    """
    delta = round(float(evolved_score) - float(baseline_score), 10)
    threshold = -float(tolerance)
    passed = delta >= threshold
    if passed:
        message = (
            f"v1 baseline gate OK: evolved={evolved_score:.4f} vs "
            f"baseline={baseline_score:.4f} (delta {delta:+.4f}, "
            f"tolerance {tolerance:+.2%})"
        )
    else:
        message = (
            f"v1 baseline gate FAILED: evolved={evolved_score:.4f} "
            f"regressed by {abs(delta):.4f} ({abs(delta) * 100:.1f}pp) "
            f"below baseline={baseline_score:.4f} "
            f"(2pp tolerance exceeded -- regression rejected)"
        )
    return {
        "passed": passed,
        "delta": delta,
        "tolerance_pp": float(tolerance),
        "evolved_score": float(evolved_score),
        "baseline_score": float(baseline_score),
        "message": message,
    }


# ── Public: ConstraintResult-shaped gate (Wave 0 test contract) ─────────────


def check_v1_baseline_gate(
    evolved_score: float,
    baseline_score: float,
    tolerance: float = 0.02,
) -> ConstraintResult:
    """Compare Phase 13 evolved holdout score to v1 baseline.

    D-14 hard regression gate: passed=False when evolved < baseline - tolerance.

    Args:
        evolved_score: Phase 13 evolved holdout score in [0, 1].
        baseline_score: v1 baseline holdout score in [0, 1].
        tolerance: Acceptable regression in absolute score units (default 0.02 = 2pp).

    Returns:
        ConstraintResult with passed flag, message referencing 2pp / regression
        terminology, and details containing JSON-encoded raw metrics
        (delta, tolerance_pp, evolved_score, baseline_score) for the CLI to
        echo into metrics.json.
    """
    metrics = _compute_baseline_gate_metrics(
        evolved_score=evolved_score,
        baseline_score=baseline_score,
        tolerance=tolerance,
    )
    details = json.dumps(
        {
            "delta": metrics["delta"],
            "tolerance_pp": metrics["tolerance_pp"],
            "evolved_score": metrics["evolved_score"],
            "baseline_score": metrics["baseline_score"],
        },
        sort_keys=True,
    )
    return ConstraintResult(
        passed=metrics["passed"],
        constraint_name="v1_baseline_gate",
        message=metrics["message"],
        details=details,
    )


# ── Baseline computation (historical + inline fallback) ─────────────────────


class _NullCtx:
    """Fallback context manager when no LM is supplied to inline scoring."""

    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False


class _InlineBaselineFailedError(RuntimeError):
    """Raised by _score_module_on_holdout when zero predictions succeed.

    WR-09: a fully-failing inline baseline used to silently return 0.0,
    making the V1 baseline gate trivially pass (evolved_score >= 0 -
    tolerance). compute_v1_baseline catches this exception and reports
    v1_baseline_source='inline_failed' so the caller can fail closed.
    """


def _score_module_on_holdout(
    module,
    holdout_examples: list,
    lm: Optional[Any] = None,
) -> float:
    """Average joint_tool_param_metric over a holdout set.

    Args:
        module: ToolModule-like callable returning
            dspy.Prediction(selected_tool, selected_params).
        holdout_examples: list of dspy.Example with correct_tool + correct_params.
        lm: optional dspy.LM; when provided, the loop runs under dspy.context.

    Returns:
        Mean score in [0, 1]; 0.0 when holdout is empty.

    Raises:
        _InlineBaselineFailedError: when holdout_examples is non-empty but
            EVERY example raised an LM error (zero predictions produced).
            WR-09: callers must distinguish this from a genuine 0.0 score
            so the V1 baseline gate cannot trivially pass on a broken
            inline baseline.
    """
    if not holdout_examples:
        return 0.0
    total = 0.0
    n = 0
    ctx = dspy.context(lm=lm) if lm is not None else _NullCtx()
    with ctx:
        for ex in holdout_examples:
            # BL-04: only catch AttributeError (MagicMock holdout examples
            # in unit tests may lack a real .task_description). A real LM
            # error (timeout / rate limit / malformed completion / network)
            # raised on the first call would raise again on the retry with
            # an identical argument, re-raising uncaught and aborting the
            # whole holdout. Skip the example instead so a single transient
            # failure does not tear down the inline baseline.
            try:
                task = ex.task_description
            except AttributeError:
                task = getattr(ex, "task_description", "")
            try:
                pred = module(task_description=task)
            except Exception:
                # Inline baseline path: this module is intentionally
                # filesystem-side-effect free (no Console / no logging
                # framework configured) per its docstring. Skip the
                # example WITHOUT incrementing n so a sequence of failures
                # does not silently dilute the average to 0.0 (which would
                # trivially pass the inline-baseline gate; see WR-09).
                continue
            score = joint_tool_param_metric(ex, pred)
            try:
                total += float(score)
            except (TypeError, ValueError):
                # WR-08: production LM should never return a non-numeric
                # score. This branch is purely test-mock accommodation.
                # v1_baseline_gate has no Console here by design (the
                # module is filesystem-side-effect free per its
                # docstring), so we cannot log via rich. Use stderr so a
                # real-world non-numeric leak is at least visible to a
                # human reading the run output. The contribution stays
                # 0.0 (n still increments) — failing would be too
                # aggressive given the existence of test mocks.
                import sys as _sys
                _sys.stderr.write(
                    f"⚠️  v1_baseline_gate non-numeric holdout score "
                    f"dropped: {score!r} (treated as 0.0)\n"
                )
            n += 1
    # WR-09: zero predictions in a non-empty holdout means EVERY example
    # raised. Distinguish from a true 0.0 average so callers can fail
    # closed. (When the holdout was empty we returned 0.0 above, which
    # is the expected degenerate case — only the all-failed case raises.)
    if n == 0:
        raise _InlineBaselineFailedError(
            f"all {len(holdout_examples)} inline-baseline examples failed; "
            f"cannot compute a trustworthy baseline score"
        )
    return total / max(1, n)


def _load_historical_baseline(baseline_run) -> Optional[float]:
    """Read evolved_score from a Phase 5 output metrics.json with type guards.

    Args:
        baseline_run: path (str or Path) to Phase 5 output directory.

    Returns:
        float in [0, 1] if valid; None on any failure mode.

    Threat T-13-21 (mitigation): explicit float() coercion + range check
    rejects out-of-range, non-numeric, or missing evolved_score safely.
    """
    if baseline_run is None:
        return None
    metrics_path = Path(baseline_run) / "metrics.json"
    if not metrics_path.is_file():
        return None
    try:
        data = json.loads(metrics_path.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    raw = data.get("evolved_score")
    if raw is None:
        return None
    # Reject bool-typed values (bool is a subclass of int but semantically wrong here).
    if isinstance(raw, bool):
        return None
    try:
        score = float(raw)
    except (TypeError, ValueError):
        return None
    if not (0.0 <= score <= 1.0):
        return None
    return score


def compute_v1_baseline(
    baseline_run: Optional[str] = None,
    *,
    baseline_module: Any = None,
    holdout: Optional[list] = None,
    lm: Optional[Any] = None,
) -> dict:
    """Determine the v1 baseline holdout score (historical > inline > missing).

    Preference order:
        1. baseline_run is not None AND metrics.json is loadable -> 'historical'.
        2. otherwise + baseline_module + holdout present -> 'inline'.
        3. neither available -> 'missing' (value 0.0; gate degrades to trivial).

    WR-09: if the inline path attempts to score but EVERY holdout example
    raises an LM error, _score_module_on_holdout raises
    _InlineBaselineFailedError. We catch it and return
    v1_baseline_source='inline_failed' with v1_baseline_holdout=1.0 so the
    gate fails closed (any evolved_score will be < 1.0 - tolerance,
    rejecting the run rather than silently passing on a broken baseline).

    Args:
        baseline_run: Optional Phase 5 output directory path.
        baseline_module: Optional baseline ToolModule for inline fallback
            (kw-only; aliased as inline_module via 13-07 PLAN.md naming).
        holdout: list of dspy.Example for inline scoring.
        lm: optional dspy.LM used during inline scoring.

    Returns:
        dict with v1_baseline_holdout (float) + v1_baseline_source
        ('historical'|'inline'|'inline_failed'|'missing') +
        metrics_source_path (str|None).
    """
    if baseline_run:
        br_path = Path(baseline_run)
        historical = _load_historical_baseline(br_path)
        if historical is not None:
            return {
                "v1_baseline_holdout": float(historical),
                "v1_baseline_source": "historical",
                "metrics_source_path": str((br_path / "metrics.json").resolve()),
            }

    if baseline_module is not None and holdout is not None:
        try:
            score = _score_module_on_holdout(baseline_module, holdout, lm=lm)
        except _InlineBaselineFailedError:
            # WR-09: every example failed. Set baseline to 1.0 so the
            # gate fails closed: evolved_score >= 1.0 - tolerance is
            # essentially impossible, so the run is rejected rather than
            # silently accepted on a broken baseline.
            return {
                "v1_baseline_holdout": 1.0,
                "v1_baseline_source": "inline_failed",
                "metrics_source_path": None,
            }
        return {
            "v1_baseline_holdout": float(score),
            "v1_baseline_source": "inline",
            "metrics_source_path": None,
        }

    return {
        "v1_baseline_holdout": 0.0,
        "v1_baseline_source": "missing",
        "metrics_source_path": None,
    }


# ── Composite class-y façade (for 13-08 convenience) ────────────────────────


class V1BaselineGate:
    """Thin OO wrapper combining compute_v1_baseline + gate metrics.

    Usage in 13-08 CLI:
        gate = V1BaselineGate(tolerance=0.02)
        baseline_info = gate.resolve(
            baseline_run=cli_arg, baseline_module=..., holdout=..., lm=...,
        )
        gate_result = gate.check(
            evolved_score=..., baseline=baseline_info,
        )
        # gate_result is a dict merging baseline_info + raw gate metrics
        # (passed, delta, tolerance_pp, evolved_score, baseline_score, message,
        # v1_baseline_holdout, v1_baseline_source, metrics_source_path).
    """

    def __init__(self, tolerance: float = 0.02):
        self.tolerance = float(tolerance)

    def resolve(
        self,
        *,
        baseline_run: Optional[str],
        baseline_module: Any = None,
        holdout: Optional[list] = None,
        lm: Optional[Any] = None,
    ) -> dict:
        return compute_v1_baseline(
            baseline_run=baseline_run,
            baseline_module=baseline_module,
            holdout=holdout,
            lm=lm,
        )

    def check(
        self,
        *,
        evolved_score: float,
        baseline: dict,
    ) -> dict:
        metrics = _compute_baseline_gate_metrics(
            evolved_score=evolved_score,
            baseline_score=float(baseline["v1_baseline_holdout"]),
            tolerance=self.tolerance,
        )
        return {**baseline, **metrics}
