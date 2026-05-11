"""Wave 0 observation: ambiguous subset size in current holdout.

D-13: ambiguous subset = `[ex for ex in holdout if len(ex.confuser_tools) >= 2]`.
D-16: AMBIGUOUS_SMALL_SAMPLE_THRESHOLD = 5; subset < 5 → ThinkABGate skips the
ambiguous gate at runtime, falls back to full regression + latency only.

Non-gating: this test always passes; warns when subset < 5.
Skipped when datasets/tools/holdout.jsonl is absent (clean checkout).
"""
import json
import warnings
from pathlib import Path

import pytest


AMBIGUOUS_SMALL_SAMPLE_THRESHOLD = 5  # mirrors think_metrics.py constant


def test_holdout_ambiguous_subset_size():
    holdout_path = Path("datasets/tools/holdout.jsonl")
    if not holdout_path.exists():
        pytest.skip(f"holdout dataset not present: {holdout_path} — skip observation")

    examples = [
        json.loads(line)
        for line in holdout_path.read_text().splitlines()
        if line.strip()
    ]
    ambiguous = [
        ex for ex in examples
        if len(ex.get("confuser_tools", [])) >= 2
    ]
    n_total = len(examples)
    n_ambig = len(ambiguous)

    # Echo for planner / operator visibility.
    print(f"\n[Phase 15 dataset observation] holdout_total={n_total} "
          f"ambiguous_subset_size={n_ambig}")

    if n_ambig < AMBIGUOUS_SMALL_SAMPLE_THRESHOLD:
        warnings.warn(
            f"Ambiguous subset has only {n_ambig} examples "
            f"(< {AMBIGUOUS_SMALL_SAMPLE_THRESHOLD} small-sample threshold). "
            f"ThinkABGate will skip the ambiguous-improvement gate at runtime (D-16). "
            f"Consider regenerating dataset via "
            f"`evolve_tool_params --eval-source synthetic --tools <subset>` "
            f"or injecting Phase 14 sessiondb mined examples to grow ambiguous slice.",
            UserWarning,
        )

    # Always passes — observation only.
    assert n_total >= 0
    assert n_ambig >= 0
