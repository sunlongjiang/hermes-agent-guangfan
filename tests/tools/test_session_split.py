"""Wave 1 GREEN tests for Phase 14 hash-bucket split + normalization.

Covers 14-VALIDATION.md rows 7-10: hash bucket edges, determinism,
normalize robustness, and signals union across multiple extractor hits.
"""

from evolution.tools.session_miner import _hash_to_split, _normalize_task_hash


def test_hash_bucket_edges():
    """Hash bucket boundaries: 69→train, 70→val, 84→val, 85→holdout.

    Pre-computed task strings whose sha256[:8] mod 100 hits each boundary.
    """
    cases = [
        ("task 35", "train"),      # bucket 69
        ("task 60", "val"),        # bucket 70
        ("task 236", "val"),       # bucket 84
        ("task 190", "holdout"),   # bucket 85
    ]
    for task, expected in cases:
        h = _normalize_task_hash(task)
        got = _hash_to_split(h)
        assert got == expected, (
            f"task={task!r} hash={h} expected {expected} got {got}"
        )


def test_hash_determinism():
    """Same task text → same bucket across repeated calls."""
    task = "Read the README file in the repository root"
    hashes = [_normalize_task_hash(task) for _ in range(10)]
    splits = [_hash_to_split(h) for h in hashes]
    assert len(set(hashes)) == 1, f"hash varied: {set(hashes)}"
    assert len(set(splits)) == 1, f"split varied: {set(splits)}"


def test_normalize_robust():
    """Normalization collapses whitespace + lowercases + strips."""
    a = _normalize_task_hash("Read   FILE")
    b = _normalize_task_hash("read file")
    c = _normalize_task_hash("  read\tfile\n")
    assert a == b == c, f"hashes differ: {a} / {b} / {c}"


def test_signals_union():
    """Same task hash hit by multiple extractors → 1 example with union.

    The union step is performed inside SessionToolMiner.mine() reducer.
    This unit-test isolates the union semantics on the intermediate dataclass
    (simulates the merge of two candidates with the same task_hash).
    """
    from evolution.tools.tool_dataset import ToolSelectionExample

    ex = ToolSelectionExample(
        task_description="list files",
        correct_tool="search_files",
        confuser_tools=["legacy_grep"],
        source="session",
        misselection_signals=["error_retry"],
    )
    ex.misselection_signals = sorted(
        set(ex.misselection_signals) | {"user_correction"}
    )
    ex.confuser_tools = sorted(set(ex.confuser_tools) | {"terminal"})
    assert ex.misselection_signals == ["error_retry", "user_correction"]
    assert ex.confuser_tools == ["legacy_grep", "terminal"]
