"""Phase 15 think-augmented A/B gate + latency/token sampler (D-08, D-14..D-17).

Three-AND gate validating that enable_reasoning=True is a net win:

  1. full_regression: think-on holdout_score >= think-off - 2pp tolerance (D-14.1)
  2. ambiguous:       think-on subset_score - think-off subset_score >= +3pp (D-14.2)
                      skipped when ambiguous sample size < 5 (D-16)
  3. latency:         think-on p95 latency <= 5.0 sec budget (D-14.3)

Mirrors evolution/tools/v1_baseline_gate.py dual-API pattern:
  - check_think_ab_gate(...)  ->  ConstraintResult (constraint-chain compatible)
  - ThinkABGate.check(...)    ->  full metrics dict (CLI consumes for metrics.json)

Default thresholds hardcoded as module-level constants per D-15 -- the config
dataclass is NOT extended (Phase 15 stays config-clean). CLI flags override at call time.

Pitfall 12 guard: this module MUST NOT export any 5-param GEPA metric. Gate runs
POST-compile, never inside GEPA's reflection loop. RESEARCH section 1.5 / 10.2
guardian test test_no_gepa_metric_added scans this module and asserts no 5-param
signature function exists.
"""

from __future__ import annotations

import json
import statistics
import time
from typing import Any, Optional

from evolution.core.constraints import ConstraintResult


# ── Module-level defaults (D-15) ────────────────────────────────────────────

DEFAULT_FULL_REGRESSION_TOLERANCE_PP = 2.0
DEFAULT_AMBIGUOUS_IMPROVEMENT_PP = 3.0
DEFAULT_LATENCY_P95_BUDGET_SEC = 5.0
AMBIGUOUS_SMALL_SAMPLE_THRESHOLD = 5  # D-16


# ── Internal: three-gate metric computation ──────────────────────────────────


def _compute_think_ab_metrics(
    *,
    think_on_holdout_score: float,
    think_off_holdout_score: float,
    ambiguous_think_on_score: float,
    ambiguous_think_off_score: float,
    ambiguous_sample_size: int,
    latency_p95_seconds: float,
    full_regression_tolerance_pp: float = DEFAULT_FULL_REGRESSION_TOLERANCE_PP,
    ambiguous_improvement_pp: float = DEFAULT_AMBIGUOUS_IMPROVEMENT_PP,
    latency_p95_budget_sec: float = DEFAULT_LATENCY_P95_BUDGET_SEC,
) -> dict:
    """Compute the three-AND gate metrics.

    Returns a dict containing per-gate pass/fail + deltas + tolerances + an
    overall `passed` boolean + a human-readable message. Designed to be the
    single source of truth consumed by both check_think_ab_gate (function API)
    and ThinkABGate.check (class API).

    Args:
        think_on_holdout_score: Full holdout score with reasoning enabled.
        think_off_holdout_score: Full holdout score with reasoning disabled.
        ambiguous_think_on_score: Ambiguous-subset score with reasoning enabled.
        ambiguous_think_off_score: Ambiguous-subset score with reasoning disabled.
        ambiguous_sample_size: Number of examples in the ambiguous subset.
        latency_p95_seconds: p95 latency (seconds) measured during think-on eval.
        full_regression_tolerance_pp: Max allowed regression in percentage points.
        ambiguous_improvement_pp: Min required improvement on ambiguous subset (pp).
        latency_p95_budget_sec: Max allowed p95 latency in seconds.

    Returns:
        dict with keys: passed, full_regression_delta, ambiguous_delta,
        ambiguous_sample_size, ambiguous_gate_skipped, latency_p95_seconds,
        tolerances, evolved_scores, gates, message.
    """
    # ── Gate 1: full regression ──────────────────────────────────────────────
    full_delta = round(
        float(think_on_holdout_score) - float(think_off_holdout_score), 10
    )
    full_threshold = -(float(full_regression_tolerance_pp) / 100.0)
    full_passed = bool(full_delta >= full_threshold)

    # ── Gate 2: ambiguous improvement (with small-sample skip, D-16) ────────
    ambiguous_delta = round(
        float(ambiguous_think_on_score) - float(ambiguous_think_off_score), 10
    )
    ambiguous_threshold = float(ambiguous_improvement_pp) / 100.0
    ambiguous_skipped = int(ambiguous_sample_size) < AMBIGUOUS_SMALL_SAMPLE_THRESHOLD
    if ambiguous_skipped:
        # D-16: small sample -> skip gate, treat as PASS.
        ambiguous_passed = True
    else:
        ambiguous_passed = bool(ambiguous_delta >= ambiguous_threshold)

    # ── Gate 3: latency p95 budget ───────────────────────────────────────────
    latency_passed = bool(float(latency_p95_seconds) <= float(latency_p95_budget_sec))

    # ── Three-AND total ──────────────────────────────────────────────────────
    all_passed = bool(full_passed and ambiguous_passed and latency_passed)

    # Human-readable message
    msg_parts = [
        f"full_regression={'OK' if full_passed else 'FAIL'} "
        f"(delta={full_delta:+.4f}, tolerance={full_regression_tolerance_pp}pp)",
    ]
    if ambiguous_skipped:
        msg_parts.append(
            f"ambiguous=SKIPPED (sample_size={ambiguous_sample_size} "
            f"< {AMBIGUOUS_SMALL_SAMPLE_THRESHOLD})"
        )
    else:
        msg_parts.append(
            f"ambiguous={'OK' if ambiguous_passed else 'FAIL'} "
            f"(delta={ambiguous_delta:+.4f}, "
            f"required>={ambiguous_improvement_pp}pp, "
            f"n={ambiguous_sample_size})"
        )
    msg_parts.append(
        f"latency={'OK' if latency_passed else 'FAIL'} "
        f"(p95={latency_p95_seconds:.2f}s, budget={latency_p95_budget_sec}s)"
    )

    status = "PASS" if all_passed else "FAIL"
    message = f"think_ab_gate {status} | " + " | ".join(msg_parts)

    return {
        "passed": all_passed,
        "full_regression_delta": full_delta,
        "ambiguous_delta": ambiguous_delta,
        "ambiguous_sample_size": int(ambiguous_sample_size),
        "ambiguous_gate_skipped": ambiguous_skipped,
        "latency_p95_seconds": float(latency_p95_seconds),
        "tolerances": {
            "full_regression_tolerance_pp": float(full_regression_tolerance_pp),
            "ambiguous_improvement_pp": float(ambiguous_improvement_pp),
            "latency_p95_budget_sec": float(latency_p95_budget_sec),
        },
        "evolved_scores": {
            "think_on_holdout_score": float(think_on_holdout_score),
            "think_off_holdout_score": float(think_off_holdout_score),
            "ambiguous_think_on_score": float(ambiguous_think_on_score),
            "ambiguous_think_off_score": float(ambiguous_think_off_score),
        },
        "gates": {
            "full_regression_gate_passed": full_passed,
            "ambiguous_gate_passed": ambiguous_passed,
            "latency_gate_passed": latency_passed,
        },
        "message": message,
    }


# ── Function API: returns ConstraintResult ───────────────────────────────────


def check_think_ab_gate(
    *,
    think_on_holdout_score: float,
    think_off_holdout_score: float,
    ambiguous_think_on_score: float,
    ambiguous_think_off_score: float,
    ambiguous_sample_size: int,
    latency_p95_seconds: float,
    full_regression_tolerance_pp: float = DEFAULT_FULL_REGRESSION_TOLERANCE_PP,
    ambiguous_improvement_pp: float = DEFAULT_AMBIGUOUS_IMPROVEMENT_PP,
    latency_p95_budget_sec: float = DEFAULT_LATENCY_P95_BUDGET_SEC,
) -> ConstraintResult:
    """Three-AND gate facade returning ConstraintResult (constraint-chain compatible).

    Mirrors evolution/tools/v1_baseline_gate.check_v1_baseline_gate API shape.
    The full metrics dict is serialized into the .details field as sort_keys
    JSON for CLI to echo into metrics.json.

    Args:
        think_on_holdout_score: Full holdout score with reasoning enabled.
        think_off_holdout_score: Full holdout score with reasoning disabled.
        ambiguous_think_on_score: Ambiguous-subset score with reasoning enabled.
        ambiguous_think_off_score: Ambiguous-subset score with reasoning disabled.
        ambiguous_sample_size: Number of examples in the ambiguous subset.
        latency_p95_seconds: p95 latency (seconds) measured during think-on eval.
        full_regression_tolerance_pp: Max allowed regression in percentage points.
        ambiguous_improvement_pp: Min required improvement on ambiguous subset (pp).
        latency_p95_budget_sec: Max allowed p95 latency in seconds.

    Returns:
        ConstraintResult with passed flag, constraint_name='think_ab_gate',
        human-readable message, and details containing JSON-encoded full metrics
        (sort_keys=True for reproducible serialization per T-15-03-02).
    """
    metrics = _compute_think_ab_metrics(
        think_on_holdout_score=think_on_holdout_score,
        think_off_holdout_score=think_off_holdout_score,
        ambiguous_think_on_score=ambiguous_think_on_score,
        ambiguous_think_off_score=ambiguous_think_off_score,
        ambiguous_sample_size=ambiguous_sample_size,
        latency_p95_seconds=latency_p95_seconds,
        full_regression_tolerance_pp=full_regression_tolerance_pp,
        ambiguous_improvement_pp=ambiguous_improvement_pp,
        latency_p95_budget_sec=latency_p95_budget_sec,
    )
    details = json.dumps(metrics, sort_keys=True, ensure_ascii=False)
    return ConstraintResult(
        passed=metrics["passed"],
        constraint_name="think_ab_gate",
        message=metrics["message"],
        details=details,
    )


# ── Class API: returns full metrics dict (for CLI metrics.json) ──────────────


class ThinkABGate:
    """Three-AND gate class API for Phase 15 think-augmented selection.

    Mirrors evolution.tools.v1_baseline_gate.V1BaselineGate construction:
    instantiate once with tolerances, call .check() with run-time scores.
    Returns the full metrics dict so the CLI can splat into metrics.json.

    Default thresholds follow D-15 module-level constants; override at
    construction time so a single gate instance stays consistent across
    multiple .check() calls within one CLI run.
    """

    def __init__(
        self,
        *,
        full_regression_tolerance_pp: float = DEFAULT_FULL_REGRESSION_TOLERANCE_PP,
        ambiguous_improvement_pp: float = DEFAULT_AMBIGUOUS_IMPROVEMENT_PP,
        latency_p95_budget_sec: float = DEFAULT_LATENCY_P95_BUDGET_SEC,
    ):
        self.full_regression_tolerance_pp = float(full_regression_tolerance_pp)
        self.ambiguous_improvement_pp = float(ambiguous_improvement_pp)
        self.latency_p95_budget_sec = float(latency_p95_budget_sec)

    def check(
        self,
        *,
        think_on_holdout_score: float,
        think_off_holdout_score: float,
        ambiguous_think_on_score: float,
        ambiguous_think_off_score: float,
        ambiguous_sample_size: int,
        latency_p95_seconds: float,
    ) -> dict:
        """Run the three-AND gate. Returns the full metrics dict.

        Args:
            think_on_holdout_score: Full holdout score with reasoning enabled.
            think_off_holdout_score: Full holdout score with reasoning disabled.
            ambiguous_think_on_score: Ambiguous-subset score with reasoning enabled.
            ambiguous_think_off_score: Ambiguous-subset score with reasoning disabled.
            ambiguous_sample_size: Number of examples in the ambiguous subset.
            latency_p95_seconds: p95 latency (seconds) measured during think-on eval.

        Returns:
            Full metrics dict (see _compute_think_ab_metrics for key list).
        """
        return _compute_think_ab_metrics(
            think_on_holdout_score=think_on_holdout_score,
            think_off_holdout_score=think_off_holdout_score,
            ambiguous_think_on_score=ambiguous_think_on_score,
            ambiguous_think_off_score=ambiguous_think_off_score,
            ambiguous_sample_size=ambiguous_sample_size,
            latency_p95_seconds=latency_p95_seconds,
            full_regression_tolerance_pp=self.full_regression_tolerance_pp,
            ambiguous_improvement_pp=self.ambiguous_improvement_pp,
            latency_p95_budget_sec=self.latency_p95_budget_sec,
        )


# ── Helper: per-example latency + reasoning-token sampler (D-17) ─────────────


def _percentile(values: list[float], p: float) -> float:
    """Compute p-th percentile (0..100) of values; 0.0 on empty.

    Uses linear interpolation between adjacent values (same method as
    numpy.percentile with interpolation='linear'). Does not require numpy.

    Args:
        values: List of numeric values.
        p: Percentile in [0, 100].

    Returns:
        Interpolated p-th percentile; 0.0 when values is empty.
    """
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    if n == 1:
        return float(sorted_vals[0])
    rank = (p / 100.0) * (n - 1)
    lo = int(rank)
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return float(sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac)


def sample_latency_tokens(
    module: Any,
    examples: list,
    lm: Any,
) -> dict:
    """Per-example latency + reasoning-token sampler for think-on holdout (D-17).

    Wraps the module call with time.perf_counter and reads
    `pred.reasoning_tokens` (set by ToolModule.forward when enable_reasoning=True;
    defaults to 0 for think-off modules so callers can still pass a baseline
    module without crashes).

    Failed example calls (raised exception) are skipped -- keep going so a
    single transient LM error does not tear down the whole sampling pass.
    Mirrors evolution/tools/v1_baseline_gate.py _score_module_on_holdout
    error-handling style.

    Args:
        module: ToolModule-like callable accepting task_description= kwarg.
        examples: List of examples with task_description attribute.
        lm: dspy.LM instance (or None) for context switching. When None,
            calls run without an explicit LM context.

    Returns:
        dict with keys:
            latency_seconds: list[float] -- per-example wall-clock times
            reasoning_tokens: list[int] -- per-example reasoning token counts
            stats: dict with latency_p50, latency_p95, latency_mean,
                   reasoning_token_p50, reasoning_token_p95, reasoning_token_mean
    """
    import dspy  # local import -- keeps module importable in tests that skip dspy

    latencies: list[float] = []
    rtokens: list[int] = []

    ctx_mgr = dspy.context(lm=lm) if lm is not None else _NullCtx()
    with ctx_mgr:
        for ex in examples:
            # Defensive task extraction -- examples may be dspy.Example, dataclass,
            # or MagicMock. Mirror v1_baseline_gate BL-04 pattern.
            try:
                task = ex.task_description
            except AttributeError:
                task = getattr(ex, "task_description", "")

            t0 = time.perf_counter()
            try:
                pred = module(task_description=task)
            except Exception:
                # Mirror _score_module_on_holdout: skip the example on LM error.
                continue
            t1 = time.perf_counter()

            latencies.append(t1 - t0)
            # reasoning_tokens may be missing on think-off Predictions -- default 0.
            tokens = int(getattr(pred, "reasoning_tokens", 0) or 0)
            rtokens.append(tokens)

    stats = {
        "latency_p50": _percentile(latencies, 50.0),
        "latency_p95": _percentile(latencies, 95.0),
        "latency_mean": (statistics.fmean(latencies) if latencies else 0.0),
        "reasoning_token_p50": _percentile([float(t) for t in rtokens], 50.0),
        "reasoning_token_p95": _percentile([float(t) for t in rtokens], 95.0),
        "reasoning_token_mean": (statistics.fmean(rtokens) if rtokens else 0.0),
    }

    return {
        "latency_seconds": latencies,
        "reasoning_tokens": rtokens,
        "stats": stats,
    }


class _NullCtx:
    """No-op context manager when sample_latency_tokens called without LM."""

    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False
