"""Wave 1 GREEN tests for Phase 14 session miner (end-to-end).

Covers 14-VALIDATION.md rows 11, 12, 25, 26 — duplication (train-only),
multiplier max policy, metrics.json schema, full mine_end_to_end pipeline.
"""

import json
import shutil
from pathlib import Path
from unittest.mock import patch

import dspy

from evolution.core.config import EvolutionConfig
from evolution.tools.session_miner import (
    DEFAULT_MULTIPLIER,
    SessionToolMiner,
    _hash_to_split,
    _normalize_task_hash,
)
from evolution.tools.tool_dataset import ToolSelectionExample

FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "sessions"


class _StubTool:
    def __init__(self, name: str):
        self.name = name


def test_duplicate_train_only():
    """Train-only duplication: val/holdout stay 1, train grows by max multiplier."""
    miner = SessionToolMiner(EvolutionConfig())
    # Use task strings whose buckets land in distinct splits (pre-computed).
    train_ex = ToolSelectionExample(
        task_description="task 35",   # bucket 69 → train
        correct_tool="search_files",
        confuser_tools=["legacy_grep"],
        source="session",
        misselection_signals=["error_retry"],  # multiplier 3
    )
    val_ex = ToolSelectionExample(
        task_description="task 60",   # bucket 70 → val
        correct_tool="search_files",
        confuser_tools=["legacy_grep"],
        source="session",
        misselection_signals=["error_retry"],
    )
    holdout_ex = ToolSelectionExample(
        task_description="task 190",  # bucket 85 → holdout
        correct_tool="search_files",
        confuser_tools=["legacy_grep"],
        source="session",
        misselection_signals=["error_retry"],
    )

    # Sanity: buckets align as expected
    assert _hash_to_split(_normalize_task_hash("task 35")) == "train"
    assert _hash_to_split(_normalize_task_hash("task 60")) == "val"
    assert _hash_to_split(_normalize_task_hash("task 190")) == "holdout"

    split = miner.split_and_duplicate([train_ex, val_ex, holdout_ex])
    assert len(split["train"]) == 3, (
        f"expected train duplicated 3x, got {len(split['train'])}"
    )
    assert len(split["val"]) == 1, f"val should not duplicate, got {len(split['val'])}"
    assert len(split["holdout"]) == 1, (
        f"holdout should not duplicate, got {len(split['holdout'])}"
    )
    # metrics mirror the split
    assert miner.metrics["final_train_after_duplication"] == 3
    assert miner.metrics["final_examples_by_split"]["train"] == 1  # pre-dup
    assert miner.metrics["final_examples_by_split"]["val"] == 1
    assert miner.metrics["final_examples_by_split"]["holdout"] == 1


def test_multiplier_max():
    """Multi-source hit takes max policy (not accumulation) — D-11."""
    miner = SessionToolMiner(EvolutionConfig())
    ex = ToolSelectionExample(
        task_description="task 35",  # train bucket
        correct_tool="search_files",
        confuser_tools=["legacy_grep"],
        source="session",
        misselection_signals=["error_retry", "oracle_disagreement"],
    )
    # max(DEFAULT_MULTIPLIER["error_retry"]=3, DEFAULT_MULTIPLIER["oracle_disagreement"]=2) = 3
    split = miner.split_and_duplicate([ex])
    assert len(split["train"]) == 3, (
        f"expected 3 copies (max 3,2), got {len(split['train'])}"
    )
    # multiplier_override should be respected
    miner2 = SessionToolMiner(
        EvolutionConfig(),
        multiplier_override={"error_retry": 5},
    )
    split2 = miner2.split_and_duplicate([ex])
    assert len(split2["train"]) == 5, (
        f"expected override 5 copies, got {len(split2['train'])}"
    )
    assert miner2.metrics["multiplier_used"]["error_retry"] == 5


def test_metrics_schema():
    """metrics has all 13 CONTEXT-mandated keys on initialization + post-split."""
    miner = SessionToolMiner(EvolutionConfig())
    required_keys = {
        "total_candidates_by_signal",
        "judge_confirmed_by_signal",
        "judge_false_positives_by_signal",
        "surface_drift_dropped",
        "surface_drift_tools",
        "final_examples_by_split",
        "final_train_after_duplication",
        "multiplier_used",
        "secret_filter_skipped",
        "jsonl_skipped_lines",
        "cost_usd_spent",
        "judge_calls",
        "judge_calls_by_signal",
    }
    have = set(miner.metrics.keys())
    missing = required_keys - have
    assert not missing, f"missing keys after init: {missing}"
    # Post-split metrics still complete
    ex = ToolSelectionExample(
        task_description="task 35",
        correct_tool="search_files",
        confuser_tools=["legacy_grep"],
        source="session",
        misselection_signals=["error_retry"],
    )
    miner.split_and_duplicate([ex])
    have2 = set(miner.metrics.keys())
    assert not (required_keys - have2), (
        f"missing keys after split: {required_keys - have2}"
    )


def test_mine_end_to_end(mock_lm_with_usage, tmp_path):
    """Full pipeline: fixtures dir → candidates → judge mock → examples."""
    # Copy a subset of fixtures into a tmp sessions dir
    sdir = tmp_path / "sessions"
    sdir.mkdir()
    for name in ("error_retry_b.json", "user_correction_a.json"):
        shutil.copy(FIXTURE_DIR / name, sdir / name)

    miner = SessionToolMiner(
        EvolutionConfig(), signals=["error_retry"]
    )  # focus on B for determinism
    current_tools = [
        _StubTool("legacy_grep"),
        _StubTool("search_files"),
        _StubTool("terminal"),
    ]
    # Patch judge to always confirm
    with patch.object(miner, "judge") as mock_judge:
        mock_judge.return_value = dspy.Prediction(
            verdict="confirm_misselection",
            correct_tool="search_files",
            rationale="session data confirms",
        )
        examples = miner.mine(sdir, current_tools)

    assert len(examples) >= 1, (
        f"expected ≥1 example from B signal, got {len(examples)}"
    )
    ex = examples[0]
    assert ex.source == "session"
    assert "error_retry" in ex.misselection_signals
    assert ex.correct_tool == "search_files"

    split = miner.split_and_duplicate(examples)
    assert isinstance(split["train"], list)
    assert isinstance(split["val"], list)
    assert isinstance(split["holdout"], list)
    # metrics are populated
    assert miner.metrics["judge_calls"] >= 1
    assert miner.metrics["judge_confirmed_by_signal"]["error_retry"] >= 1
