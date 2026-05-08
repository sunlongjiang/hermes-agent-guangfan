"""Wave 0 RED test scaffolding for Phase 14 session-signal extractors.

Covers 14-VALIDATION.md rows 1-4 (B/A/C extractor + parser tolerance). All
test bodies are placeholders (`pytest.skip`) until Wave 1+ implements
`evolution/tools/session_miner.py`. The test function names are load-bearing:
the planner's per-task `<automated>` verify commands reference them directly.
"""

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "sessions"


def test_parse_assistant_with_tool_calls():
    """Parser tolerates reasoning_details / multi tool_calls / missing role.

    Reads malformed_msg.json + error_retry_b.json; asserts the extractor
    does not raise on non-array tool_calls and silently skips messages
    missing the `role` field (RESEARCH Pitfall 1).
    """
    pytest.skip("Wave 1+ 实现 — 见 14-02-PLAN.md / 14-03-PLAN.md")


def test_b_error_retry():
    """B (error_retry) extractor produces a candidate from error_retry_b.json.

    Expected behaviour: candidate.original_tool == 'legacy_grep',
    candidate.correct_tool == 'search_files', signal == 'error_retry'
    (RESEARCH Pitfall 2 — tolerates exit_code!=0 OR truthy `error` string).
    """
    pytest.skip("Wave 1+ 实现 — 见 14-03-PLAN.md")


def test_a_user_correction(mock_lm_with_usage):
    """A (user_correction) extractor matches keyword list + calls LLM 二判.

    Reads user_correction_a.json; asserts keyword regex catches '应该用' and
    the LLM 二判 mock is invoked. candidate.original_tool == 'terminal',
    candidate.correct_tool == 'search_files'.
    """
    pytest.skip("Wave 1+ 实现 — 见 14-03-PLAN.md")


def test_c_oracle_disagreement(mock_lm_with_usage):
    """C (oracle_disagreement) extractor produces a candidate when baseline
    ToolModule mock returns a different tool than the session actually used.

    Reads oracle_disagreement_c.json; mocked ToolModule returns 'read_file'
    while the session used 'terminal'; extractor emits a candidate
    for LLM judge evaluation.
    """
    pytest.skip("Wave 1+ 实现 — 见 14-03-PLAN.md")
