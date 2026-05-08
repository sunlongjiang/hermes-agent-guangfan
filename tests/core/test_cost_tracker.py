"""Wave 0 RED tests for CostTracker.

Tests D-13: max_cost_usd cap + token accumulation + abort behavior.
Covers W4 (track_usage=False warning) and W5 (poll-side empty-usage, xfail scaffold).
Fails until 13-05 implements evolution/core/cost_tracker.py.
"""

import pytest
import warnings


def test_accumulation(mock_lm_with_usage):
    """CostTracker accumulates cost from mock LM usage across multiple calls.

    D-13: .poll() returns float > 0 after LM calls with usage data.
    """
    pytest.importorskip("dspy")
    from evolution.core.cost_tracker import CostTracker  # fails until 13-05

    tracker = CostTracker(max_usd=100.0)
    # Simulate usage being tracked (integration with real usage tracker is tested E2E)
    # Here we verify CostTracker.poll() can compute cost from injected usage
    with tracker:
        # Inject mock usage directly to verify accumulation logic
        mock_usage = {
            "openai/gpt-4.1-mini": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            }
        }
        tracker._inject_usage_for_test(mock_usage)
        cost = tracker.poll()
    assert isinstance(cost, float), f"poll() must return float, got {type(cost)}"
    assert cost > 0, f"poll() must return >0 after LM usage, got {cost}"


def test_abort_threshold(mock_lm_with_usage):
    """CostTracker.exceeded() returns True after crossing max_usd threshold.

    D-13: cost cap hard gate.
    """
    pytest.importorskip("dspy")
    from evolution.core.cost_tracker import CostTracker  # fails until 13-05

    tracker = CostTracker(max_usd=0.000001)  # Near-zero threshold
    with tracker:
        # Inject usage that definitely costs more than $0.000001
        mock_usage = {
            "openai/gpt-4.1": {
                "prompt_tokens": 100_000,
                "completion_tokens": 10_000,
                "total_tokens": 110_000,
            }
        }
        tracker._inject_usage_for_test(mock_usage)
        exceeded = tracker.exceeded()
    assert exceeded is True, (
        f"expected CostTracker(max_usd=0.000001).exceeded() to be True after large usage, "
        f"got {exceeded}"
    )


def test_aborted_json_schema(tmp_path):
    """CostTracker.write_aborted_json() creates file with required schema.

    D-13: ABORTED_ dir contains aborted.json with typed fields.
    """
    pytest.importorskip("dspy")
    import json
    from evolution.core.cost_tracker import CostTracker  # fails until 13-05

    tracker = CostTracker(max_usd=20.0)
    # Force spent amount for test
    tracker.spent_usd = 20.34

    output_dir = tmp_path / "ABORTED_test"
    output_dir.mkdir()
    tracker.write_aborted_json(
        output_dir=output_dir,
        extra={"evaluated_candidates": 5, "partial_diff": []},
    )

    aborted_file = output_dir / "aborted.json"
    assert aborted_file.exists(), f"aborted.json not created in {output_dir}"

    with aborted_file.open() as f:
        data = json.load(f)

    required_keys = {"final_cost_usd", "evaluated_candidates", "aborted_at_iso", "partial_diff"}
    missing = required_keys - set(data.keys())
    assert not missing, f"aborted.json missing required keys: {missing}"

    assert isinstance(data["final_cost_usd"], float), (
        f"final_cost_usd must be float, got {type(data['final_cost_usd'])}"
    )
    assert isinstance(data["evaluated_candidates"], int), (
        f"evaluated_candidates must be int, got {type(data['evaluated_candidates'])}"
    )
    assert isinstance(data["aborted_at_iso"], str), (
        f"aborted_at_iso must be str (ISO timestamp), got {type(data['aborted_at_iso'])}"
    )
    assert isinstance(data["partial_diff"], list), (
        f"partial_diff must be list, got {type(data['partial_diff'])}"
    )


def test_track_usage_false_warning():
    """CostTracker raises RuntimeWarning when dspy.settings.track_usage is False.

    W4: warn users that cost tracking requires dspy.configure(track_usage=True).
    """
    pytest.importorskip("dspy")
    import dspy
    from evolution.core.cost_tracker import CostTracker  # fails until 13-05

    # Ensure track_usage is False (default per DSPy settings.py:25)
    original = getattr(dspy.settings, "track_usage", False)
    try:
        dspy.settings.configure(track_usage=False)
        with pytest.warns(RuntimeWarning, match=r"track_usage"):
            tracker = CostTracker(max_usd=1.0)
            with tracker:
                pass  # Just entering the context should warn
    finally:
        # Restore original
        try:
            dspy.settings.configure(track_usage=original)
        except Exception:
            pass


@pytest.mark.xfail(
    reason="poll-side empty-usage detection deferred per 13-05 W5 honest-gap note",
    strict=False,
)
def test_poll_side_empty_usage_warning():
    """CostTracker emits RuntimeWarning when get_total_tokens() returns {} on poll.

    W5 scaffold: 13-05 may or may not implement poll-side guard. If implemented,
    this xfail converts to XPASS. If not, it stays xfail and is documented as gap.
    """
    pytest.importorskip("dspy")
    from unittest.mock import patch
    from evolution.core.cost_tracker import CostTracker  # fails until 13-05

    tracker = CostTracker(max_usd=1.0)
    with tracker:
        # Simulate tracker returning empty dict for 5+ polls
        with patch.object(tracker, "_tracker") as mock_tracker:
            mock_tracker.get_total_tokens.return_value = {}
            with pytest.warns(RuntimeWarning):
                for _ in range(5):
                    tracker.poll()


def test_poll_after_exit_returns_zero_regression():
    """BL-01 regression: poll() after __exit__ silently loses live UsageTracker state.

    This is the underlying defect that BL-01 forced evolve_tool_params to work
    around. Documenting it here as a regression test makes the contract
    explicit: callers MUST snapshot tracker.poll() BEFORE the context exits.

    Inside the `with`:
        - injected usage is visible, poll() returns >0.

    After __exit__:
        - the live UsageTracker is gone (set to None);
        - poll() falls back to self._injected_usage; since
          _inject_usage_for_test was called inside the context, the injection
          state IS still readable, so poll() should still report the injected
          spend (proving the architectural seam can be used by callers).
        - the regression we guard against is poll() returning 0.0 in
          production where _injected_usage is empty -- the docstring on
          CostTracker.poll() and the BL-01 fix in evolve_tool_params.py
          together encode "snapshot in-block, do not poll() after exit".
    """
    pytest.importorskip("dspy")
    from evolution.core.cost_tracker import CostTracker

    tracker = CostTracker(max_usd=100.0)
    with tracker:
        tracker._inject_usage_for_test(
            {
                "openai/gpt-4.1-mini": {
                    "prompt_tokens": 1000,
                    "completion_tokens": 200,
                    "total_tokens": 1200,
                }
            }
        )
        in_block_spent = tracker.poll()
        assert in_block_spent > 0, "sanity: in-block poll should see injection"

    # Post-exit: tracker._tracker is None.
    assert tracker._tracker is None, (
        "CostTracker.__exit__ must drop the live UsageTracker; if this changes, "
        "the BL-01 fix in evolve_tool_params._evolve_impl can be simplified."
    )

    # Post-exit poll: in this test, _injected_usage is non-empty (injection
    # survives __exit__), so poll() can still re-derive a number. The
    # PRODUCTION regression is that _injected_usage is empty AND _tracker
    # is None — under those conditions poll() returns the previously-set
    # spent_usd or 0.0. We exercise that branch separately:
    fresh_tracker = CostTracker(max_usd=100.0)
    with fresh_tracker:
        # No injection at all — simulates a real run that never polled inside.
        pass
    # Now both _tracker is None AND _injected_usage is empty. poll() must
    # return whatever spent_usd was last (default 0.0). This is the silent
    # zero that masked actual API spend in BL-01.
    assert fresh_tracker._tracker is None
    assert fresh_tracker._injected_usage == {}
    post_exit_spent = fresh_tracker.poll()
    assert post_exit_spent == 0.0, (
        f"With no injection and no live tracker, post-exit poll() returns "
        f"the last self.spent_usd (default 0.0). Got {post_exit_spent}. "
        f"This is the BL-01 silent-zero behavior: callers using live LM "
        f"calls (no injection) MUST snapshot poll() inside the `with` block "
        f"to capture real spend before __exit__ disposes the UsageTracker."
    )

