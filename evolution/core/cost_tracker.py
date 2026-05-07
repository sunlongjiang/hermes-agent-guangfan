"""Cost tracking + abort-on-budget-exceeded for GEPA optimization runs.

Closes folded todo 2026-05-07-max-cost-usd-and-reflection-model.md and
addresses CONCERNS §M8 (Phase 13 fan-out multiplies optimization cost).

Key pieces:
  - CostTracker: context manager wrapping dspy.utils.usage_tracker.track_usage()
    with USD conversion via litellm.cost_per_token.
  - estimate_cost_usd: pure helper converting the UsageTracker's output dict to USD.
  - CostBudgetExceeded: exception raised by CLI callers when CostTracker.exceeded()
    triggers a hard stop.

Usage pattern (wired in 13-08 CLI):

    import dspy
    from evolution.core.cost_tracker import CostTracker, CostBudgetExceeded

    dspy.configure(lm=lm, track_usage=True)   # REQUIRED — track_usage=False by default
    with CostTracker(max_usd=config.max_cost_usd) as tracker:
        optimizer.compile(student, trainset=train, valset=val)
        if tracker.exceeded():
            tracker.write_aborted_json(
                output_dir,
                extra={
                    "evaluated_candidates": N,
                    "partial_diff": [...],
                },
            )
            raise CostBudgetExceeded(tracker.spent_usd, tracker.max_usd)

Pitfall 2 reminder: if the caller forgets track_usage=True, the tracker will
never see tokens — poll() returns 0.0 and exceeded() always False.
CostTracker.__enter__ emits a RuntimeWarning when it cannot detect track_usage
enabled (W4 in 13-01 Wave 0 scaffold). Poll-side empty-usage detection is a
known gap tracked as W5 / scaffolded xfail; see test_poll_side_empty_usage_warning.
"""

from __future__ import annotations

import json
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import dspy
import litellm
from dspy.utils.usage_tracker import track_usage


# ── Exceptions ──────────────────────────────────────────────────────────────


class CostBudgetExceeded(Exception):
    """Raised by CLI when CostTracker.exceeded() is True.

    Args:
        spent_usd: The accumulated USD at abort time.
        max_usd: The configured ceiling.
    """

    def __init__(self, spent_usd: float, max_usd: float):
        self.spent_usd = spent_usd
        self.max_usd = max_usd
        super().__init__(
            f"Cost budget exceeded: spent ${spent_usd:.4f} > cap ${max_usd:.4f}"
        )


# ── USD conversion ──────────────────────────────────────────────────────────


def estimate_cost_usd(usage_by_lm: dict[str, dict]) -> tuple[float, dict[str, dict]]:
    """Convert a DSPy UsageTracker total-tokens dict into USD.

    Args:
        usage_by_lm: Shape produced by UsageTracker.get_total_tokens():
            {lm_name: {"prompt_tokens": int, "completion_tokens": int, ...}}

    Returns:
        (total_usd, breakdown) where breakdown maps lm_name → dict with
        prompt_tokens, completion_tokens, usd, and optionally 'fallback': True
        when litellm.cost_per_token raised and the hand-rolled estimate was used.
    """
    total_usd = 0.0
    breakdown: dict[str, dict] = {}

    for lm_name, usage in (usage_by_lm or {}).items():
        pt = int(usage.get("prompt_tokens", 0) or 0)
        ct = int(usage.get("completion_tokens", 0) or 0)
        used_fallback = False
        try:
            prompt_cost, completion_cost = litellm.cost_per_token(
                model=lm_name,
                prompt_tokens=pt,
                completion_tokens=ct,
            )
            if prompt_cost is None or completion_cost is None:
                raise ValueError("litellm returned None cost")
            lm_usd = float(prompt_cost) + float(completion_cost)
            if lm_usd != lm_usd:  # NaN guard
                raise ValueError("NaN cost")
        except Exception:
            # Conservative fallback — $0.001/1K prompt + $0.003/1K completion.
            # Matches OpenAI gpt-4-mini ballpark; Phase 14 can refine if needed.
            used_fallback = True
            lm_usd = (pt / 1000.0) * 0.001 + (ct / 1000.0) * 0.003

        entry = {
            "prompt_tokens": pt,
            "completion_tokens": ct,
            "usd": round(lm_usd, 6),
        }
        if used_fallback:
            entry["fallback"] = True
        breakdown[lm_name] = entry
        total_usd += lm_usd

    return total_usd, breakdown


# ── CostTracker context manager ─────────────────────────────────────────────


class CostTracker:
    """Context manager that accumulates LM usage and enforces a USD cap.

    Args:
        max_usd: Budget ceiling. `exceeded()` is True when spent > max.
            Set to <= 0 to disable enforcement (not recommended; still polls).
    """

    def __init__(self, max_usd: float):
        self.max_usd = float(max_usd)
        self.spent_usd = 0.0
        self.breakdown: dict[str, dict] = {}
        # Optional manually-injected usage used by tests + direct callers that
        # can't enable dspy.settings.track_usage. Keyed by lm_name → dict of
        # token totals matching UsageTracker.get_total_tokens() shape.
        self._injected_usage: dict[str, dict] = {}
        self._ctx = None
        self._tracker = None

    def __enter__(self) -> "CostTracker":
        # Pitfall 2 (W4): warn if track_usage is False on dspy.settings.
        track_flag = getattr(dspy.settings, "track_usage", False)
        if not track_flag:
            warnings.warn(
                "CostTracker entered but dspy.settings.track_usage is False. "
                "Call dspy.configure(lm=..., track_usage=True) before entering "
                "CostTracker, otherwise poll() will always return 0.0 from the "
                "real UsageTracker (manually-injected usage via "
                "_inject_usage_for_test still works).",
                RuntimeWarning,
                stacklevel=2,
            )
        self._ctx = track_usage()
        self._tracker = self._ctx.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._ctx is not None:
            self._ctx.__exit__(exc_type, exc, tb)
            self._ctx = None
            self._tracker = None
        return False  # never suppress

    # ── Test + direct-caller injection hook ────────────────────────────────

    def _inject_usage_for_test(self, usage_by_lm: dict[str, dict]) -> None:
        """Manually merge usage into the tracker, bypassing dspy.settings.

        Used by Wave 0 tests (test_accumulation, test_abort_threshold) which
        need to exercise the cost math without spinning up a real LM + enabling
        track_usage. Callers outside tests SHOULD prefer
        dspy.configure(track_usage=True) + real LM invocations.

        Args:
            usage_by_lm: {lm_name: {"prompt_tokens": int, "completion_tokens": int, ...}}
                matching UsageTracker.get_total_tokens() shape.
        """
        for lm_name, usage in (usage_by_lm or {}).items():
            dest = self._injected_usage.setdefault(lm_name, {})
            # Accumulate across multiple injections.
            for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                if key in usage:
                    dest[key] = int(dest.get(key, 0) or 0) + int(usage.get(key, 0) or 0)
            # Carry any other fields through (last write wins for non-token keys).
            for key, val in usage.items():
                if key not in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    dest[key] = val

    # ── Polling + threshold logic ──────────────────────────────────────────

    def poll(self) -> float:
        """Compute current spent_usd from the tracker's running total.

        Returns:
            Current total USD spent since entering the context. 0.0 when
            track_usage is disabled and no usage has been injected. Merges
            real UsageTracker output with manually-injected usage.
        """
        # Merge: real UsageTracker output + injected usage. The injected path
        # dominates when both exist (real UT is empty in tests that use
        # _inject_usage_for_test anyway).
        combined: dict[str, dict] = {}

        if self._tracker is not None:
            try:
                real_usage = self._tracker.get_total_tokens() or {}
            except Exception:
                real_usage = {}
            for lm, u in real_usage.items():
                combined[lm] = dict(u)

        for lm, u in self._injected_usage.items():
            if lm in combined:
                # Accumulate into existing
                for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
                    if key in u:
                        combined[lm][key] = int(combined[lm].get(key, 0) or 0) + int(u.get(key, 0) or 0)
                for key, val in u.items():
                    if key not in ("prompt_tokens", "completion_tokens", "total_tokens"):
                        combined[lm][key] = val
            else:
                combined[lm] = dict(u)

        # If we have neither a live tracker nor injected usage, retain whatever
        # spent_usd was directly set (test_aborted_json_schema sets it manually).
        if not combined and self._tracker is None:
            return self.spent_usd

        total_usd, breakdown = estimate_cost_usd(combined)
        self.spent_usd = total_usd
        self.breakdown = breakdown
        return total_usd

    def exceeded(self) -> bool:
        """Return True when current spent > max_usd. Refreshes via poll()."""
        if self.max_usd <= 0:
            return False
        return self.poll() > self.max_usd

    # ── Persistence ────────────────────────────────────────────────────────

    def write_aborted_json(
        self,
        output_dir: Path,
        *,
        extra: Optional[dict] = None,
        **kwargs: Any,
    ) -> Path:
        """Persist the ABORTED_<ts>/aborted.json payload with required keys.

        Two calling conventions supported:

          1. kwargs style::

                 tracker.write_aborted_json(
                     output_dir,
                     evaluated_candidates=5,
                     partial_diff=[...],
                     optimizer_used="gepa",
                 )

          2. `extra` dict style (Wave 0 test contract)::

                 tracker.write_aborted_json(
                     output_dir,
                     extra={"evaluated_candidates": 5, "partial_diff": []},
                 )

        Both forms end up merged into the top-level payload. When the same key
        appears in both, the explicit kwargs win over `extra`.

        Required keys present on every payload:
            - final_cost_usd: float
            - max_cost_usd: float
            - evaluated_candidates: int  (defaults to 0 when neither caller form sets it)
            - aborted_at_iso: str  (ISO-8601 UTC)
            - partial_diff: list   (defaults to [] when neither caller form sets it)
            - spent_breakdown_by_lm: dict[str, dict]
            - status: "ABORTED_COST_CAP"

        Args:
            output_dir: Directory to create (if needed) + write aborted.json into.
            extra: Optional dict of fields to merge into the top-level payload.
                Keys in ``extra`` are overridden by matching kwargs.
            **kwargs: Any additional top-level keys to store (e.g.
                evaluated_candidates=N, partial_diff=[...], optimizer_used="gepa").

        Returns:
            Path to the written aborted.json file.
        """
        self.poll()  # refresh self.spent_usd + self.breakdown

        merged: dict[str, Any] = {}
        if extra:
            merged.update(extra)
        merged.update(kwargs)  # kwargs override extra

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Required fields — inject defaults when caller omitted them.
        evaluated_candidates = int(merged.pop("evaluated_candidates", 0) or 0)
        partial_diff = list(merged.pop("partial_diff", None) or [])

        payload: dict[str, Any] = {
            "final_cost_usd": float(round(self.spent_usd, 6)),
            "max_cost_usd": float(self.max_usd),
            "evaluated_candidates": evaluated_candidates,
            "aborted_at_iso": datetime.now(timezone.utc).isoformat(),
            "partial_diff": partial_diff,
            "spent_breakdown_by_lm": self.breakdown,
            "status": "ABORTED_COST_CAP",
        }
        payload.update(merged)  # any remaining extras

        out = output_dir / "aborted.json"
        out.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        return out
