"""Wave 1 GREEN tests for Phase 14 ConfirmMisselection LLM judge.

Covers 14-VALIDATION.md rows 5-6 (judge verdict round-trip + fail-closed on
LM errors). Uses unittest.mock.patch to patch the bound judge predictor,
mirroring the style in tests/tools/test_param_consistency.py.
"""

from unittest.mock import patch

import dspy

from evolution.core.config import EvolutionConfig
from evolution.tools.session_miner import Candidate, SessionToolMiner


def _mk_miner_and_candidate() -> tuple[SessionToolMiner, Candidate]:
    miner = SessionToolMiner(EvolutionConfig())
    cand = Candidate(
        task="find the TODO comment",
        session_path="/tmp/session.json",
        originally_used_tool="terminal",
        available_tools=["terminal", "search_files"],
        tool_call_id="tc-1",
        signal="error_retry",
        downstream_context="[assistant] tool_calls=['search_files']",
    )
    return miner, cand


def test_verdict_round_trip(mock_lm_with_usage):
    """Judge parses `confirm_misselection` and falls back on unknown labels."""
    miner, cand = _mk_miner_and_candidate()

    # Case 1: valid confirm_misselection verdict → preserved
    good_pred = dspy.Prediction(
        verdict="confirm_misselection",
        correct_tool="search_files",
        rationale="search_files is built for this",
    )
    with patch.object(miner, "judge") as mock_judge:
        mock_judge.return_value = good_pred
        v = miner._judge_candidate(cand)
    assert v.label == "confirm_misselection", (
        f"expected confirm_misselection, got {v.label}"
    )
    assert v.correct_tool == "search_files"
    assert "search_files" in v.rationale

    # Case 2: unknown label → fail-closed to false_positive
    bad_pred = dspy.Prediction(
        verdict="SOMETHING_UNKNOWN",
        correct_tool="search_files",
        rationale="weird output",
    )
    with patch.object(miner, "judge") as mock_judge:
        mock_judge.return_value = bad_pred
        v = miner._judge_candidate(cand)
    assert v.label == "false_positive", (
        f"unknown label should fall back to false_positive, got {v.label}"
    )

    # Case 3: confirm_misselection but correct_tool not in available_tools → fail-closed
    drift_pred = dspy.Prediction(
        verdict="confirm_misselection",
        correct_tool="nonexistent_tool",
        rationale="",
    )
    with patch.object(miner, "judge") as mock_judge:
        mock_judge.return_value = drift_pred
        v = miner._judge_candidate(cand)
    assert v.label == "false_positive", (
        f"correct_tool drift should fall back, got {v.label}"
    )


def test_lm_failure_drops_candidate(mock_lm_with_usage):
    """LLM call raising any Exception → verdict='false_positive' + rationale mentions error (T-14-01)."""
    miner, cand = _mk_miner_and_candidate()
    with patch.object(miner, "judge") as mock_judge:
        mock_judge.side_effect = RuntimeError("api boom")
        v = miner._judge_candidate(cand)
    assert v.label == "false_positive"
    assert "boom" in v.rationale or "judge_error" in v.rationale
