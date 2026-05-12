"""Unit tests for persist_raw_predictions (Phase 16: D-12 dashboard helper)."""
import pytest

pytest.importorskip("dspy")  # match tests/tools/ defensive convention

from evolution.tools.tool_metric import persist_raw_predictions


def test_immutability_and_shape():
    """persist_raw_predictions does not mutate inputs; returns new dict with raw_predictions key."""
    metrics = {"timestamp": "abc", "iterations": 5}
    recs = [{"correct_tool": "a", "selected_tool": "b", "difficulty": "easy", "num_available_tools": 3}]

    out = persist_raw_predictions(metrics, recs)

    # Original inputs not mutated
    assert metrics == {"timestamp": "abc", "iterations": 5}
    assert recs[0] == {"correct_tool": "a", "selected_tool": "b", "difficulty": "easy", "num_available_tools": 3}

    # Return value is a new dict
    assert out is not metrics

    # Original keys preserved
    assert out["timestamp"] == "abc"
    assert out["iterations"] == 5

    # raw_predictions has correct schema
    assert len(out["raw_predictions"]) == 1
    assert out["raw_predictions"][0].keys() == {"correct_tool", "selected_tool", "difficulty", "num_available_tools"}


def test_field_coercion():
    """Extra keys stripped; None values coerced; missing difficulty defaults to 'medium'."""
    recs = [{"correct_tool": "a", "selected_tool": None, "difficulty": "medium",
             "num_available_tools": None, "extra_field": "leak"}]

    out = persist_raw_predictions({}, recs)
    first = out["raw_predictions"][0]

    assert first["selected_tool"] == ""
    assert first["num_available_tools"] == 0
    assert "extra_field" not in first

    # Missing difficulty defaults to "medium"
    recs2 = [{"correct_tool": "x", "selected_tool": "y", "num_available_tools": 1}]
    out2 = persist_raw_predictions({}, recs2)
    assert out2["raw_predictions"][0]["difficulty"] == "medium"


def test_empty_and_none():
    """Empty list and None input both produce raw_predictions == []."""
    out_empty = persist_raw_predictions({}, [])
    assert out_empty["raw_predictions"] == []

    out_none = persist_raw_predictions({}, None)
    assert out_none["raw_predictions"] == []


def test_large_list_warning(capsys):
    """2001 records triggers yellow warning on stdout; list is NOT truncated."""
    recs = [
        {"correct_tool": "t", "selected_tool": "t", "difficulty": "easy", "num_available_tools": 2}
        for _ in range(2001)
    ]

    out = persist_raw_predictions({}, recs)

    # List not truncated
    assert len(out["raw_predictions"]) == 2001

    # Warning emitted
    captured = capsys.readouterr()
    # Rich Console might render to stderr in some environments; check both
    combined = captured.out + captured.err
    assert "raw_predictions large" in combined, (
        f"Expected 'raw_predictions large' in output, got stdout={captured.out!r} stderr={captured.err!r}"
    )
