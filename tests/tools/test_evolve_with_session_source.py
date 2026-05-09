"""Wave 1 GREEN tests for Phase 14 --session-source integration.

Covers 14-VALIDATION.md rows 27-28: session-side examples override synth
on same hash (D-14), and train.jsonl pre-duplicated by miner is NOT re-
multiplied by the evolve CLI union path (Pitfall 5).
"""

import inspect
import json

from evolution.tools.evolve_tool_descriptions import (
    _union_session_into_dataset as _union_desc,
)
from evolution.tools.evolve_tool_params import (
    _union_session_into_dataset as _union_params,
)
from evolution.tools.tool_dataset import ToolSelectionDataset, ToolSelectionExample


def test_session_overrides_synth(tmp_path):
    """Same task hash → session-side example wins; synth replaced (D-14)."""
    synth = ToolSelectionDataset(
        train=[
            ToolSelectionExample(
                task_description="list files",
                correct_tool="terminal",
                source="synthetic",
            )
        ],
        val=[],
        holdout=[],
    )
    sess_dir = tmp_path / "session"
    sess_dir.mkdir()
    for split in ("val", "holdout"):
        (sess_dir / f"{split}.jsonl").write_text("")
    sess_ex = ToolSelectionExample(
        task_description="list files",
        correct_tool="search_files",
        source="session",
        misselection_signals=["error_retry"],
    )
    (sess_dir / "train.jsonl").write_text(json.dumps(sess_ex.to_dict()) + "\n")

    _union_desc(synth, sess_dir)
    assert len(synth.train) == 1, "same hash should collapse to 1 example"
    assert synth.train[0].correct_tool == "search_files", "session-side wins"
    assert synth.train[0].misselection_signals == ["error_retry"]


def test_no_double_duplication(tmp_path):
    """mine_tool_sessions pre-duplicates train.jsonl; evolve CLI does NOT re-multiply.

    Dual verification (W5):
      (a) behavior — 3 identical rows in train.jsonl → union dedupes to 1
      (b) source — neither helper body references `_multiplier_for`
          or `DEFAULT_MULTIPLIER`
    """
    synth = ToolSelectionDataset(train=[], val=[], holdout=[])
    sess_dir = tmp_path / "session"
    sess_dir.mkdir()
    same_ex = ToolSelectionExample(
        task_description="list files",
        correct_tool="search_files",
        source="session",
        misselection_signals=["error_retry"],
    )
    (sess_dir / "train.jsonl").write_text(
        (json.dumps(same_ex.to_dict()) + "\n") * 3
    )
    for split in ("val", "holdout"):
        (sess_dir / f"{split}.jsonl").write_text("")

    _union_desc(synth, sess_dir)
    assert len(synth.train) == 1, (
        f"by_hash dedup should yield 1 unique train example, got {len(synth.train)}"
    )

    # Source-level guard: helper body must not re-duplicate (W5)
    for fn in (_union_desc, _union_params):
        src = inspect.getsource(fn)
        assert "_multiplier_for" not in src, (
            f"W5: {fn.__module__}._union_session_into_dataset must NOT call "
            f"_multiplier_for (Pitfall 5)"
        )
        assert "DEFAULT_MULTIPLIER" not in src, (
            f"W5: {fn.__module__}._union_session_into_dataset must NOT reference "
            f"DEFAULT_MULTIPLIER (Pitfall 5)"
        )


def test_both_helpers_have_same_semantics(tmp_path):
    """Two CLI modules each own a helper with identical input→output semantics."""
    base_train = [
        ToolSelectionExample(
            task_description="same task",
            correct_tool="a",
            source="synthetic",
        )
    ]
    sess_dir = tmp_path / "session"
    sess_dir.mkdir()
    for split in ("val", "holdout"):
        (sess_dir / f"{split}.jsonl").write_text("")
    sess_ex = ToolSelectionExample(
        task_description="same task",
        correct_tool="b",
        source="session",
        misselection_signals=["error_retry"],
    )
    (sess_dir / "train.jsonl").write_text(json.dumps(sess_ex.to_dict()) + "\n")

    synth_desc = ToolSelectionDataset(
        train=list(base_train), val=[], holdout=[]
    )
    synth_params = ToolSelectionDataset(
        train=list(base_train), val=[], holdout=[]
    )
    _union_desc(synth_desc, sess_dir)
    _union_params(synth_params, sess_dir)

    assert len(synth_desc.train) == len(synth_params.train) == 1
    assert (
        synth_desc.train[0].correct_tool
        == synth_params.train[0].correct_tool
        == "b"
    )
