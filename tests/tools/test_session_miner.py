"""Wave 0 RED test scaffolding for Phase 14 session miner (end-to-end).

Covers 14-VALIDATION.md rows 11, 12, 25, 26 — duplication (train-only), multiplier
max cap, metrics.json schema, full mine_end_to_end pipeline. All test bodies use
`pytest.skip` until Wave 1+ implements `evolution/tools/session_miner.py` and
`evolution/tools/mine_tool_sessions.py`.
"""

import pytest


def test_duplicate_train_only():
    """Misselection_multiplier duplication applies to train split only.

    Build a dataset with 1 confirmed misselection example per split; set
    multiplier=3; assert final_train=3 but val/holdout stay =1 (CONTEXT D-08
    — avoid inflating val/holdout which would bias metrics).
    """
    pytest.skip("Wave 1+ 实现 — 见 14-04-PLAN.md")


def test_multiplier_max():
    """Per-signal multiplier is capped at configured max (default 5).

    Pass misselection_multiplier={'error_retry': 99}; assert the actual
    duplication factor used is min(99, max)==5; metrics.multiplier_used
    reflects the capped value.
    """
    pytest.skip("Wave 1+ 实现 — 见 14-04-PLAN.md")


def test_metrics_schema():
    """metrics.json contains all CONTEXT-mandated keys.

    Required keys (see 14-CONTEXT.md specifics D-06 / D-13):
      - total_candidates_by_signal
      - judge_confirmed_by_signal
      - judge_false_positives_by_signal
      - surface_drift_dropped
      - surface_drift_tools
      - final_examples_by_split
      - final_train_after_duplication
      - multiplier_used
      - secret_filter_skipped
      - jsonl_skipped_lines
      - cost_usd_spent
      - judge_calls
      - judge_calls_by_signal
    """
    pytest.skip("Wave 1+ 实现 — 见 14-04-PLAN.md / 14-05-PLAN.md")


def test_mine_end_to_end(mock_lm_with_usage, tmp_path):
    """Full pipeline: sessions dir → train/val/holdout JSONL + metrics.json.

    Point session_miner at a tmp dir holding 3 fixture sessions; run with
    mock_lm_with_usage returning 'confirm_misselection' for all candidates;
    assert that each of {train, val, holdout}.jsonl + metrics.json are
    written and totals reconcile.
    """
    pytest.skip("Wave 1+ 实现 — 见 14-04-PLAN.md")
