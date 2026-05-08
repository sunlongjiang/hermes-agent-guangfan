"""Wave 0 RED test scaffolding for Phase 14 surface-drift filtering.

Covers 14-VALIDATION.md rows 16-17 — drop candidates whose tool is not in
the current hermes-agent tool set (surface drift), and truncate the Rich
report to top-N unknown tools (metrics.json keeps the full list).
"""

from pathlib import Path

import pytest

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "sessions"


def test_drop_unknown_tool():
    """Candidate using `legacy_tool_v0` is dropped when not in current tools.

    Reads surface_drift.json fixture (tool name literal `legacy_tool_v0`).
    Mock the current tool set = {terminal, search_files} (no legacy_tool_v0).
    Expected: candidate dropped, metrics.surface_drift_dropped == 1,
    metrics.surface_drift_tools contains 'legacy_tool_v0'.
    """
    pytest.skip("Wave 1+ 实现 — 见 14-04-PLAN.md")


def test_report_truncation():
    """Surface-drift Rich report truncates to top-10; metrics.json keeps all.

    Feed >10 unknown tools (e.g., legacy_tool_0..legacy_tool_14). Assert that
    the console / log output shows at most 10 rows plus a "(+4 more)" style
    suffix, but metrics.json surface_drift_tools list preserves all 15.
    """
    pytest.skip("Wave 1+ 实现 — 见 14-04-PLAN.md / 14-05-PLAN.md")
