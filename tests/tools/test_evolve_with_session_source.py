"""Wave 0 RED test scaffolding for Phase 14 evolve CLI session-source integration.

Covers 14-VALIDATION.md rows 27-28 — session-side examples override synth
(same hash → session wins), and train.jsonl predupped by miner is NOT
doubly multiplied when loaded through evolve CLI.
"""

import pytest


def test_session_overrides_synth(tmp_path):
    """Same hash → session-sourced example wins; synth example dropped.

    Build synth dataset with 1 example at hash H (value=synth), load a
    session JSONL also at hash H (value=session). After --session-source
    merge: exactly 1 example at H with value=session (CONTEXT D-14 — session
    signal is higher-priority than synth defaults).
    """
    pytest.skip("Wave 1+ 实现 — 见 14-06-PLAN.md")


def test_no_double_duplication(tmp_path):
    """Pre-duplicated train.jsonl is NOT re-multiplied by evolve CLI.

    mine_tool_sessions.py writes train.jsonl already expanded by
    misselection_multiplier. evolve CLI's --session-source loader must
    load lines as-is without re-applying the multiplier (D-14 — avoid
    quadratic multiplication).
    """
    pytest.skip("Wave 1+ 实现 — 见 14-06-PLAN.md")
