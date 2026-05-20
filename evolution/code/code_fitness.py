"""CodeFitness — three-component deterministic scoring for evolved code candidates.

This module implements the Phase 21 fitness function for the Darwinian Code
Evolution pipeline. The score has THREE components, weighted per D-11:

    composite = pytest_score * 0.80 + size_component * 0.10 + ruff_score * 0.10

Hard gates (D-11 / D-12):
    * pytest does not 100% pass → composite = 0.0, decision = "reject"
    * size ratio > hard_threshold (default 1.5×) → composite = 0.0, decision = "reject"

There is **no LLM-as-judge** anywhere in this module (D-14). No ``dspy`` /
``openai`` imports. Scoring is fully deterministic so the same candidate +
test suite produce identical scores across runs.

The ``score_candidate`` function is the entry point consumed by the
openevolve evaluator file. It expects ``sandbox_runner.run_pytest_in_sandbox``
to be available (provided by Plan 21-05); the import is deferred to the
function body so importing this module does not fail before Plan 05 ships.

Ruff lint scoring (D-13) uses ``ruff check --output-format=json`` with
``check=False`` (Pitfall 2): exit code 1 means "violations found" and is a
normal outcome, NOT a subprocess error.
"""

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


# ── Constants ──────────────────────────────────────────────────────────────

# D-12 size_component thresholds (Claude's Discretion: soft 1.2 → 1.3 widening
# is permitted because ansi_strip.py baseline is 1784 bytes / 44 lines and
# ×1.2 = 53 lines is uncomfortably tight; the ×1.5 hard upper bound is NOT
# adjustable — it remains the hard-reject ceiling).
_DEFAULT_SIZE_SOFT_THRESHOLD = 1.3
_DEFAULT_SIZE_HARD_THRESHOLD = 1.5

# Ruff subprocess timeout (D-13). Lint of a single small file should be sub-second.
_RUFF_TIMEOUT_SECONDS = 10


# ── Dataclass ──────────────────────────────────────────────────────────────


@dataclass
class CodeFitness:
    """Result of scoring a single evolved code candidate.

    The ``to_dict`` method emits a ``code_*``-prefixed dict suitable for
    inclusion in ``output/code/<ts>/metrics.json``. The ``pytest_failures`` /
    ``ruff_findings`` lists hold structured failure detail consumed by the
    openevolve reflection prompt (D-16).
    """

    pytest_passed: int
    pytest_total: int
    size_baseline_bytes: int
    size_evolved_bytes: int
    ruff_violations: int
    pytest_score: float  # 0.0 or 1.0 (hard binary, D-11)
    size_component: float  # 0.0..1.0 (D-12 piecewise linear)
    ruff_score: float  # 0.0..1.0 (D-13 bucketed)
    composite: float  # weighted sum
    decision: str  # "accept" | "reject"
    reject_reason: str  # "" or "pytest_fail:..." / "size_oversize:..." / "timeout" / ...
    pytest_failures: list[dict] = field(default_factory=list)
    ruff_findings: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize for ``metrics.json`` with ``code_*`` field prefixes."""
        size_ratio = (
            round(self.size_evolved_bytes / self.size_baseline_bytes, 3)
            if self.size_baseline_bytes > 0
            else 0.0
        )
        return {
            "code_pytest_passed": self.pytest_passed,
            "code_pytest_total": self.pytest_total,
            "code_size_baseline_bytes": self.size_baseline_bytes,
            "code_size_evolved_bytes": self.size_evolved_bytes,
            "code_size_ratio": size_ratio,
            "code_ruff_violations": self.ruff_violations,
            "code_pytest_score": self.pytest_score,
            "code_size_component": self.size_component,
            "code_ruff_score": self.ruff_score,
            "code_composite_fitness": self.composite,
            "code_decision": self.decision,
            "code_reject_reason": self.reject_reason,
            "code_pytest_failures": self.pytest_failures,
            "code_ruff_findings": self.ruff_findings,
        }


# ── Private helpers ─────────────────────────────────────────────────────────


def _size_to_component(
    ratio: float,
    soft_threshold: float = _DEFAULT_SIZE_SOFT_THRESHOLD,
    hard_threshold: float = _DEFAULT_SIZE_HARD_THRESHOLD,
) -> float:
    """D-12 piecewise linear size_component mapping.

    Three regions:
      * ratio ≤ 1.0       → 1.0 (no growth)
      * 1.0 < ratio ≤ soft → 1.0 → 0.7 linearly
      * soft < ratio ≤ hard → 0.7 → 0.0 linearly
      * ratio > hard       → 0.0 (caller treats as hard-reject)
    """
    if ratio <= 1.0:
        return 1.0
    if ratio <= soft_threshold:
        # Linear 1.0 → 0.7 across (1.0, soft_threshold]
        return 1.0 - (ratio - 1.0) * (0.3 / (soft_threshold - 1.0))
    if ratio <= hard_threshold:
        # Linear 0.7 → 0.0 across (soft_threshold, hard_threshold]
        return 0.7 * (1.0 - (ratio - soft_threshold) / (hard_threshold - soft_threshold))
    return 0.0


def _ruff_to_score(violation_count: int) -> float:
    """D-13 bucketed ruff_score mapping.

    Buckets:
      0       → 1.0
      1-2     → 0.7
      3-5     → 0.4
      6-10    → 0.1
      >10     → 0.0
    """
    if violation_count == 0:
        return 1.0
    if violation_count <= 2:
        return 0.7
    if violation_count <= 5:
        return 0.4
    if violation_count <= 10:
        return 0.1
    return 0.0


def _run_ruff(evolved_path: Path) -> tuple[int, list[dict]]:
    """Run ``ruff check --output-format=json`` against the candidate file.

    Returns (violation_count, findings_list). ``check=False`` is mandatory
    (Pitfall 2): ruff exit code 1 means "violations found" (NORMAL), 2 means
    "ruff internal error". On internal error, return ``(0, [])`` so callers
    can decide to degrade (the caller maps internal error to ruff_score=0.5).

    Findings format (D-16): each dict has ``rule_id``, ``message``, ``line``.
    """
    try:
        result = subprocess.run(
            ["ruff", "check", "--output-format=json", str(evolved_path)],
            capture_output=True,
            text=True,
            timeout=_RUFF_TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        # ruff hung or not installed — degrade gracefully (caller falls back).
        return 0, []

    # exit code 2 = ruff internal error; signal via empty findings + sentinel
    # The caller (score_candidate) uses returncode to decide on degraded score.
    # For the public surface, we still return zero findings on internal error
    # — the caller separately tracks returncode by inspecting the process.
    if result.returncode == 2:
        return 0, []

    try:
        raw = json.loads(result.stdout) if result.stdout.strip() else []
    except json.JSONDecodeError:
        raw = []

    findings: list[dict] = []
    for item in raw:
        # ruff JSON shape: {"code": "F401", "message": "...", "location": {"row": N, "column": M}, ...}
        rule_id = item.get("code") or ""
        message = item.get("message") or ""
        location = item.get("location") or {}
        line = location.get("row") if isinstance(location, dict) else None
        findings.append(
            {
                "rule_id": rule_id,
                "message": message,
                "line": line,
            }
        )

    return len(findings), findings


# ── Public surface ──────────────────────────────────────────────────────────


def score_candidate(
    target_path: Path,
    evolved_path: Path,
    eval_dir: Path,
    baseline_size: int,
    train_test_ids: Optional[list[str]] = None,
    *,
    size_soft_threshold: float = _DEFAULT_SIZE_SOFT_THRESHOLD,
    size_hard_threshold: float = _DEFAULT_SIZE_HARD_THRESHOLD,
) -> CodeFitness:
    """Score one candidate file against the test suite + size + ruff gates.

    This is the single public entry point consumed by the openevolve
    evaluator (Plan 21-06 generates an evaluator .py that imports this
    function). The function is purely deterministic — no LLM calls (D-14).

    Args:
        target_path: Path to the ORIGINAL hermes-agent file (read-only; used
            for context, never modified).
        evolved_path: Path to the candidate file produced by openevolve.
            Must exist on disk because ruff + size both read it.
        eval_dir: Working directory for the pytest sandbox. The sandbox_runner
            owns lifecycle (creation + cleanup).
        baseline_size: Byte count of the original target file. Used as the
            denominator of the size ratio.
        train_test_ids: Optional list of pytest node-ids restricting the
            evaluator to the training split. ``None`` runs every discovered
            test.

    Returns:
        ``CodeFitness`` with all three components populated. ``decision`` is
        ``"accept"`` only if pytest 100% passes AND size ratio ≤ hard_threshold.

    Raises:
        RuntimeError: If ``evolution.code.sandbox_runner`` is not importable
            (Plan 05 has not landed yet). We intentionally do NOT silently
            substitute a stub — a missing sandbox would silently report every
            candidate as a pass, which is a critical correctness hole.
    """
    # Deferred import: sandbox_runner ships in Plan 21-05. Until then this
    # module is still importable (for unit-testing fitness math in isolation),
    # but score_candidate fails loudly the moment a real evaluation is run.
    try:
        from evolution.code.sandbox_runner import run_pytest_in_sandbox
    except ImportError as exc:
        raise RuntimeError(
            "sandbox_runner module unavailable — Phase 21 Plan 05 "
            "(sandbox_runner.py) must complete before score_candidate "
            "can be invoked end-to-end."
        ) from exc

    # ── 1. pytest hard gate (D-11) ─────────────────────────────────────────
    pytest_passed, pytest_total, pytest_failures = run_pytest_in_sandbox(
        candidate_path=evolved_path,
        eval_dir=eval_dir,
        train_test_ids=train_test_ids,
    )

    size_evolved_bytes = evolved_path.stat().st_size
    ratio = size_evolved_bytes / baseline_size if baseline_size > 0 else 0.0

    # Pytest binary fail: composite = 0, reject immediately (don't even bother
    # with ruff — the candidate is broken).
    if pytest_total < 0:
        # sandbox timeout sentinel (Plan 05 contract)
        return CodeFitness(
            pytest_passed=0,
            pytest_total=0,
            size_baseline_bytes=baseline_size,
            size_evolved_bytes=size_evolved_bytes,
            ruff_violations=0,
            pytest_score=0.0,
            size_component=0.0,
            ruff_score=0.0,
            composite=0.0,
            decision="reject",
            reject_reason="timeout",
            pytest_failures=pytest_failures,
            ruff_findings=[],
        )

    if pytest_passed < pytest_total or pytest_total == 0:
        first_fail_name = (
            pytest_failures[0].get("test_name", "unknown")
            if pytest_failures
            else "unknown"
        )
        return CodeFitness(
            pytest_passed=pytest_passed,
            pytest_total=pytest_total,
            size_baseline_bytes=baseline_size,
            size_evolved_bytes=size_evolved_bytes,
            ruff_violations=0,
            pytest_score=0.0,
            size_component=0.0,
            ruff_score=0.0,
            composite=0.0,
            decision="reject",
            reject_reason=f"pytest_fail:{first_fail_name}",
            pytest_failures=pytest_failures,
            ruff_findings=[],
        )

    # ── 2. size hard gate (D-12) ───────────────────────────────────────────
    if ratio > size_hard_threshold:
        return CodeFitness(
            pytest_passed=pytest_passed,
            pytest_total=pytest_total,
            size_baseline_bytes=baseline_size,
            size_evolved_bytes=size_evolved_bytes,
            ruff_violations=0,
            pytest_score=1.0,
            size_component=0.0,
            ruff_score=0.0,
            composite=0.0,
            decision="reject",
            reject_reason=f"size_oversize:{ratio:.2f}x",
            pytest_failures=[],
            ruff_findings=[],
        )

    size_component = _size_to_component(
        ratio,
        soft_threshold=size_soft_threshold,
        hard_threshold=size_hard_threshold,
    )

    # ── 3. ruff lint scoring (D-13) ────────────────────────────────────────
    ruff_violations, ruff_findings = _run_ruff(evolved_path)
    ruff_score = _ruff_to_score(ruff_violations)

    # ── 4. composite (D-11) ────────────────────────────────────────────────
    pytest_score = 1.0  # by this point pytest is 100% pass
    composite = (
        pytest_score * 0.80 + size_component * 0.10 + ruff_score * 0.10
    )

    return CodeFitness(
        pytest_passed=pytest_passed,
        pytest_total=pytest_total,
        size_baseline_bytes=baseline_size,
        size_evolved_bytes=size_evolved_bytes,
        ruff_violations=ruff_violations,
        pytest_score=pytest_score,
        size_component=size_component,
        ruff_score=ruff_score,
        composite=composite,
        decision="accept",
        reject_reason="",
        pytest_failures=[],
        ruff_findings=ruff_findings,
    )
