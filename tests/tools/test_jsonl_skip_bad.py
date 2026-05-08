"""Wave 1 GREEN tests for Phase 14 JSONL bad-line tolerance helper.

Covers 14-VALIDATION.md rows 18-19 — `_load_jsonl_skip_bad` helper skips
malformed lines with a counter + threshold warn, while the strict
`EvalDataset.load` path remains unchanged (D-18 scope guard — mining
tolerance is additive, not a rewrite).
"""

import json

import pytest

from evolution.tools.session_miner import _load_jsonl_skip_bad


def test_skip_bad_line(tmp_path, capsys):
    """Helper skips malformed JSON lines + increments counter + warns > 5%.

    Writes 100 lines, 10 invalid (>5% threshold); expects (90, 10) and a
    Rich-formatted warn on the captured output.
    """
    path = tmp_path / "train.jsonl"
    with open(path, "w") as f:
        for i in range(100):
            if i % 10 == 0:
                f.write("not-valid-json\n")
            else:
                f.write(json.dumps({"i": i}) + "\n")
    rows, skipped = _load_jsonl_skip_bad(path)
    assert len(rows) == 90, f"expected 90 rows, got {len(rows)}"
    assert skipped == 10, f"expected 10 skipped, got {skipped}"
    out = capsys.readouterr().out + capsys.readouterr().err
    # Rich console.print writes to stdout by default; capsys captures both streams.
    assert "skipped" in out.lower() or "skipped" in capsys.readouterr().out.lower()


def test_evaldataset_strict_unchanged(tmp_path):
    """EvalDataset.load must still abort on malformed lines (D-18 scope guard)."""
    from evolution.core.dataset_builder import EvalDataset

    ds_dir = tmp_path / "ds"
    ds_dir.mkdir()
    # valid jsonl for val/holdout so load() doesn't skip-short-circuit on missing files
    (ds_dir / "val.jsonl").write_text("")
    (ds_dir / "holdout.jsonl").write_text("")
    # train.jsonl with 1 invalid line
    (ds_dir / "train.jsonl").write_text("not-valid-json\n")
    with pytest.raises((json.JSONDecodeError, ValueError)):
        EvalDataset.load(ds_dir)
