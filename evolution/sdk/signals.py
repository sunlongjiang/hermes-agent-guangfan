"""Automatic signal detection + signal_score weighting.

Five signals (see spec §5.2):
  - error_in_run     (negative, -0.4)
  - retry_pattern    (negative, -0.3)
  - user_correction  (negative, -0.5)
  - clean_completion (positive, no penalty; informational)
  - latency_outlier  (weak negative, -0.1)

compute_signal_score combines them; annotate_traces_with_signals applies the
detection + score to a full trace list (pairwise for user_correction).
"""

import re
import statistics
from typing import Optional


# User correction patterns (case-insensitive). Add patterns sparingly — every
# false positive will mark a clean run as negative.
_CORRECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE) for p in [
        r"不对", r"应该是", r"\bredo\b", r"\bactually\b",
        r"\bno (that's |thats |that is )?wrong\b", r"\bnot quite\b",
    ]
]


def detect_error_in_run(trace: dict) -> bool:
    """True if any tool call errored or output contains a Python traceback."""
    for call in trace.get("tool_calls", []):
        if call.get("error"):
            return True
    output = trace.get("output") or ""
    if isinstance(output, str) and "Traceback (most recent" in output:
        return True
    signals = trace.get("signals", {})
    if signals.get("errors", 0) > 0:
        return True
    if signals.get("error_text"):
        return True
    return False


def detect_retry_pattern(trace: dict) -> bool:
    """True if any tool_id appears ≥2 times consecutively with identical args."""
    calls = trace.get("tool_calls", [])
    for i in range(len(calls) - 1):
        a, b = calls[i], calls[i + 1]
        if a.get("id") == b.get("id") and a.get("args") == b.get("args"):
            return True
    return False


def detect_user_correction(trace: dict, next_trace: Optional[dict]) -> bool:
    """True if the *next* trace's input contains a correction phrase.

    The current trace gets the negative signal because its output prompted the
    correction.
    """
    if next_trace is None:
        return False
    nxt_input = next_trace.get("input", {})
    text = " ".join(str(v) for v in (nxt_input.values() if isinstance(nxt_input, dict) else [nxt_input]))
    return any(p.search(text) for p in _CORRECTION_PATTERNS)


def detect_clean_completion(trace: dict) -> bool:
    """True if no errors, no retries, non-empty output."""
    if detect_error_in_run(trace):
        return False
    if detect_retry_pattern(trace):
        return False
    output = trace.get("output")
    if output is None or (isinstance(output, str) and not output.strip()):
        return False
    return True


def detect_latency_outlier(trace: dict, all_traces: list[dict]) -> bool:
    """True if trace.signals.latency_ms > p95(all) * 2.

    Returns False when the dataset is too small to compute p95 (<5 records).
    The target trace is excluded from the p95 population to avoid self-reference.
    """
    target = trace.get("signals", {}).get("latency_ms")
    if target is None:
        return False
    latencies = [
        t.get("signals", {}).get("latency_ms")
        for t in all_traces
        if t is not trace and t.get("signals", {}).get("latency_ms") is not None
    ]
    if len(latencies) < 5:
        return False
    p95 = statistics.quantiles(latencies, n=20)[18]  # index 18 = 95th percentile
    return target > p95 * 2


def compute_signal_score(
    *,
    error_in_run: bool,
    retry_pattern: bool,
    user_correction: bool,
    latency_outlier: bool,
) -> float:
    """Combine signals into a [0, 1] score. Clean run = 1.0."""
    score = 1.0
    if error_in_run:
        score -= 0.4
    if retry_pattern:
        score -= 0.3
    if user_correction:
        score -= 0.5
    if latency_outlier:
        score -= 0.1
    return max(0.0, min(1.0, score))


def annotate_traces_with_signals(traces: list[dict]) -> list[dict]:
    """Mutate `scores.signal_score` on each trace in-place. Returns same list.

    user_correction is pairwise: trace[i] is annotated based on trace[i+1].
    Traces are processed in chronological order (by ts).
    """
    sorted_traces = sorted(traces, key=lambda t: t.get("ts", ""))

    for i, t in enumerate(sorted_traces):
        nxt = sorted_traces[i + 1] if i + 1 < len(sorted_traces) else None
        flags = {
            "error_in_run": detect_error_in_run(t),
            "retry_pattern": detect_retry_pattern(t),
            "user_correction": detect_user_correction(t, nxt),
            "latency_outlier": detect_latency_outlier(t, sorted_traces),
        }
        score = compute_signal_score(**flags)
        scores = t.setdefault("scores", {})
        scores["signal_score"] = score
        # Stash flags for debugging.
        t.setdefault("signals", {})["detected"] = flags
    return sorted_traces
