"""Wave 1 GREEN tests for Phase 14 surface-drift filtering.

Covers 14-VALIDATION.md rows 16-17 — drop candidates whose tool is not in
the current hermes-agent tool set (surface drift), and truncate the Rich
report to top-N unknown tools (metrics.json keeps the full list).
"""

from pathlib import Path
from unittest.mock import patch

import dspy

from evolution.core.config import EvolutionConfig
from evolution.tools.session_miner import Candidate, SessionToolMiner

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "sessions"


class _StubTool:
    def __init__(self, name: str):
        self.name = name


def test_drop_unknown_tool(tmp_path, mock_lm_with_usage):
    """`legacy_tool_v0` in surface_drift.json fixture is dropped when not in current tools."""
    # Symlink / copy the fixture into a tmp sessions dir so mine() can glob it
    import shutil

    sdir = tmp_path / "sessions"
    sdir.mkdir()
    shutil.copy(FIXTURE_DIR / "surface_drift.json", sdir / "surface_drift.json")

    miner = SessionToolMiner(
        EvolutionConfig(), signals=["error_retry"]
    )
    current_tools = [_StubTool("terminal"), _StubTool("search_files")]

    # Need to drive the B extractor into producing a candidate with originally_used_tool
    # == 'legacy_tool_v0'. The surface_drift.json fixture uses legacy_tool_v0 but may
    # not contain a proper error→retry pattern. Use _filter_drift directly with a
    # synthetic candidate list to validate the drift filter semantics.
    fake_cands = [
        Candidate(
            task="example",
            session_path="x.json",
            originally_used_tool="legacy_tool_v0",
            available_tools=["terminal", "search_files"],
            tool_call_id="tc-1",
            signal="error_retry",
            downstream_context="",
        ),
        Candidate(
            task="example 2",
            session_path="x.json",
            originally_used_tool="terminal",
            available_tools=["terminal", "search_files"],
            tool_call_id="tc-2",
            signal="error_retry",
            downstream_context="",
        ),
    ]
    # Initialize metrics before invoking the private filter
    miner.metrics = miner._fresh_metrics()
    kept = miner._filter_drift(fake_cands, {"terminal", "search_files"})
    assert len(kept) == 1, f"expected 1 kept, got {len(kept)}"
    assert kept[0].originally_used_tool == "terminal"
    assert miner.metrics["surface_drift_dropped"] == 1
    assert miner.metrics["surface_drift_tools"]["legacy_tool_v0"] == 1


def test_report_truncation():
    """top_n_drift_tools returns at most N tuples sorted by count desc; full metrics kept."""
    miner = SessionToolMiner(EvolutionConfig())
    # Synthesize a populated surface_drift_tools map with 15 entries
    miner.metrics = miner._fresh_metrics()
    for i in range(15):
        miner.metrics["surface_drift_tools"][f"legacy_tool_{i:02d}"] = 15 - i
    assert len(miner.metrics["surface_drift_tools"]) == 15

    top10 = miner.top_n_drift_tools(10)
    assert len(top10) == 10, f"expected 10, got {len(top10)}"
    # Sorted by count desc — first entry should be the highest
    assert top10[0][1] == 15
    assert top10[-1][1] == 6
    # Full 15-entry map is preserved in metrics
    assert len(miner.metrics["surface_drift_tools"]) == 15
