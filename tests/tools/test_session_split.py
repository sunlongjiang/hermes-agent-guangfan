"""Wave 0 RED test scaffolding for Phase 14 hash-bucket split + normalization.

Covers 14-VALIDATION.md rows 7-10: hash bucket edges, determinism,
normalize robustness, and signals union across multiple extractor hits.
"""

import pytest


def test_hash_bucket_edges():
    """Hash bucket boundaries: 69→train, 70→val, 84→val, 85→holdout.

    Construct task strings whose sha256 hex first 8 chars mod 100 land on
    the four boundary values (69, 70, 84, 85). Verify `_hash_to_split`
    returns the expected split per RESEARCH Pattern 2 / CONTEXT D-13.
    """
    pytest.skip("Wave 1+ 实现 — 见 14-03-PLAN.md")


def test_hash_determinism():
    """Same task text → same bucket across repeated calls and runs.

    Invokes `_normalize_task_hash` on the same string ten times; all
    results must be identical. Also asserts stability against Python
    hash randomization (str.__hash__ is NOT used; sha256 is).
    """
    pytest.skip("Wave 1+ 实现 — 见 14-03-PLAN.md")


def test_normalize_robust():
    """Normalization collapses whitespace + lowercases + strips.

    Assert `_normalize_task_hash('Read   FILE')` ==
    `_normalize_task_hash('read file')` ==
    `_normalize_task_hash('  read\\tfile\\n')` (whitespace-robust).
    """
    pytest.skip("Wave 1+ 实现 — 见 14-03-PLAN.md")


def test_signals_union():
    """Same task hash hit by multiple extractors → 1 example with union.

    Build two candidates with identical normalized task, one from B
    (error_retry) and one from A (user_correction). After miner reduce,
    expect 1 ToolSelectionExample with
    misselection_signals == ['error_retry', 'user_correction'] (sorted).
    """
    pytest.skip("Wave 1+ 实现 — 见 14-03-PLAN.md")
