"""Wave 0 RED test scaffolding for Phase 14 JSONL bad-line tolerance helper.

Covers 14-VALIDATION.md rows 18-19 — `_load_jsonl_skip_bad` helper skips
malformed lines with a counter + threshold warn, while the strict
`EvalDataset.load` path remains unchanged (D-18 scope guard — mining
tolerance is additive, not a rewrite).
"""

import pytest


def test_skip_bad_line(tmp_path, capsys):
    """Helper skips a single malformed JSON line + increments counter.

    Write a file with 100 lines where 1 is invalid JSON. Expected:
      - return list has 99 entries
      - counter (return value or metrics dict) reports 1 skipped
      - no exception raised
      - ≥ 6% bad lines threshold triggers a Rich-formatted warn on stderr
    """
    pytest.skip("Wave 1+ 实现 — 见 14-04-PLAN.md")


def test_evaldataset_strict_unchanged(tmp_path):
    """EvalDataset.load must still abort on malformed lines (D-18 scope guard).

    Write a file with 1 invalid line. `EvalDataset.load` must raise (strict
    behaviour preserved). Only the new mining helper tolerates bad lines.
    """
    pytest.skip("Wave 1+ 实现 — 见 14-04-PLAN.md")
