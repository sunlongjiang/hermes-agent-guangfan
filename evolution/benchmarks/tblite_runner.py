"""TBLite subprocess wrapper stub for Wave 2 integration.

This is a STUB file created by Plan 03 (benchmark_gate.py) so that
tests/benchmarks/test_benchmark_gate.py can be collected and run
independently in this worktree. The full implementation is provided
by Plan 02 (parallel wave). At wave-end, Plan 02's implementation
replaces this stub.

IMPORTANT: Do not use this stub in production. Import guards are
intentionally minimal to support test isolation only.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# D-15 cache key version — must match Plan 02's value.
TBLITE_RUNNER_VERSION: str = "1.0"


@dataclass
class TBLiteRunResult:
    """Result of one TBLite subprocess invocation.

    Matches the interface defined in Plan 02's full implementation.
    """
    per_task: list = field(default_factory=list)
    subprocess_runtime_seconds: float = 0.0
    hang_count: int = 0
    cost_breakdown: dict = field(default_factory=dict)
    samples_jsonl_path: Optional[Path] = None
    exit_code: int = -1
    status: str = "ok"  # ok | hang_timeout | error
    jsonl_skipped_lines: int = 0
    stderr_tail: list = field(default_factory=list)


class TBLiteRunner:
    """TBLite benchmark runner stub.

    Full implementation provided by Plan 02. This stub raises
    NotImplementedError on run() to avoid accidental use in production.
    Tests mock this object via patch.object.
    """

    def __init__(
        self,
        config,
        *,
        heartbeat_seconds: int = 60,
        max_hangs: int = 3,
    ):
        self.config = config
        self.heartbeat_seconds = heartbeat_seconds
        self.max_hangs = max_hangs

    def run(
        self,
        task_filter: list,
        output_dir: Path,
        *,
        runs: int = 1,
    ) -> TBLiteRunResult:
        """Run TBLite evaluation subprocess.

        Raises:
            NotImplementedError: This stub must be replaced by Plan 02's
                full implementation before production use.
        """
        raise NotImplementedError(
            "tblite_runner.py stub — replace with Plan 02 full implementation."
        )


def _canonical_json(obj) -> str:
    """Canonical JSON for cache key — sorted keys, no spaces."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def compute_artifact_hash(
    evolved_sections: list,
    dataset_revision_hash: str,
    stratified_subset_seed: int,
    tblite_runner_version: str = TBLITE_RUNNER_VERSION,
) -> str:
    """D-15 cache key: sha256(canonical evolved + dataset hash + seed + runner ver)[:16].

    Args:
        evolved_sections: List of prompt sections with section_id and text attrs.
        dataset_revision_hash: HuggingFace dataset revision SHA.
        stratified_subset_seed: Seed used for stratified subset selection.
        tblite_runner_version: Runner version (default TBLITE_RUNNER_VERSION).

    Returns:
        First 16 hex chars of sha256 hash.
    """
    h = hashlib.sha256()
    h.update(_canonical_json(
        [{"section_id": s.section_id, "text": s.text} for s in evolved_sections]
    ).encode("utf-8"))
    h.update(dataset_revision_hash.encode("utf-8"))
    h.update(stratified_subset_seed.to_bytes(4, "big"))
    h.update(tblite_runner_version.encode("utf-8"))
    return h.hexdigest()[:16]
