"""Wave 1 GREEN tests for Phase 14 session-signal extractors.

Covers 14-VALIDATION.md rows 1-4 (B/A/C extractor + parser tolerance).
The test function names are load-bearing: the planner's per-task
`<automated>` verify commands reference them directly.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import dspy

from evolution.core.config import EvolutionConfig
from evolution.tools.session_miner import SessionToolMiner

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "sessions"


def _load(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


def test_parse_assistant_with_tool_calls():
    """Parser tolerates malformed messages (missing role / non-array tool_calls)."""
    miner = SessionToolMiner(EvolutionConfig(), signals=["error_retry"])
    data = _load("malformed_msg.json")
    # Should not raise despite the message with missing role and non-array tool_calls
    cands = miner._extract_error_retry(
        data["messages"], "malformed.json", current_tool_names=set()
    )
    assert isinstance(cands, list)

    # error_retry_b.json should also parse without exceptions
    data2 = _load("error_retry_b.json")
    cands2 = miner._extract_error_retry(
        data2["messages"],
        "error_retry.json",
        current_tool_names={"legacy_grep", "search_files"},
    )
    assert isinstance(cands2, list)


def test_b_error_retry():
    """B (error_retry) extractor produces 1 candidate from error_retry_b.json."""
    miner = SessionToolMiner(EvolutionConfig(), signals=["error_retry"])
    data = _load("error_retry_b.json")
    cands = miner._extract_error_retry(
        data["messages"],
        "error_retry.json",
        current_tool_names={"legacy_grep", "search_files"},
    )
    assert len(cands) == 1, f"expected 1 candidate, got {len(cands)}"
    c = cands[0]
    assert c.originally_used_tool == "legacy_grep"
    assert c.signal == "error_retry"
    assert "list files" in c.task.lower()


def test_a_user_correction(mock_lm_with_usage):
    """A (user_correction) extractor catches '应该用 X' + LLM 二判 returns True."""
    miner = SessionToolMiner(EvolutionConfig(), signals=["user_correction"])
    data = _load("user_correction_a.json")
    # Patch the user_correction_judge to return is_correction=True
    with patch.object(miner, "user_correction_judge") as mock_judge:
        mock_judge.return_value = dspy.Prediction(is_correction=True)
        cands = miner._extract_user_correction(
            data["messages"],
            "user_correction.json",
            current_tool_names={"terminal", "search_files"},
        )
    assert len(cands) >= 1, f"expected ≥1 candidate, got {len(cands)}"
    c = cands[0]
    assert c.originally_used_tool == "terminal"
    assert c.signal == "user_correction"
    mock_judge.assert_called()


def test_c_oracle_disagreement(mock_lm_with_usage):
    """C (oracle_disagreement) extractor emits a candidate when baseline
    ToolModule recommends a different tool than the session used.
    """
    baseline = MagicMock()
    baseline.return_value = dspy.Prediction(
        selected_tool="read_file", selected_params="{}"
    )
    miner = SessionToolMiner(
        EvolutionConfig(),
        signals=["oracle_disagreement"],
        baseline_module=baseline,
    )
    data = _load("oracle_disagreement_c.json")
    cands = miner._extract_oracle_disagreement(
        data["messages"],
        "oracle.json",
        current_tool_names={"terminal", "read_file"},
    )
    assert len(cands) >= 1, f"expected ≥1 candidate, got {len(cands)}"
    c = cands[0]
    assert c.originally_used_tool == "terminal"
    assert c.signal == "oracle_disagreement"
