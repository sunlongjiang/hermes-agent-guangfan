"""Unit tests for evolution/code/code_fitness.py — Plan 21-04 task 2.

Coverage matrix (6 tests, three scoring stages × pass / fail / partial):

    1. test_pytest_pass_gives_score_1                  — pytest binary gate green
    2. test_pytest_fail_gives_zero_and_reject          — pytest binary gate red (D-11)
    3. test_size_within_soft_threshold_gives_partial   — D-12 piecewise linear
    4. test_size_over_hard_threshold_rejects           — D-12 ×1.5 hard reject
    5. test_ruff_zero_violations_gives_1               — D-13 bucket [0,0]
    6. test_ruff_3_violations_gives_0_4                — D-13 bucket [3,5]

All tests mock subprocess (ruff) and inject a fake sandbox_runner module
via sys.modules so the production deferred-import succeeds before Plan 05
ships sandbox_runner.py.
"""

import json
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────


def _install_fake_sandbox_runner(monkeypatch, *, passed: int, total: int, failures: list[dict]):
    """Inject a stub ``evolution.code.sandbox_runner`` module into sys.modules.

    Returns the stub module so individual tests can override behaviour.
    The deferred-import inside ``score_candidate`` will pick up this stub.
    """
    fake_module = types.ModuleType("evolution.code.sandbox_runner")

    def run_pytest_in_sandbox(candidate_path, eval_dir_base, test_file_path, run_id, timeout_seconds=120):
        return passed, total, list(failures)

    fake_module.run_pytest_in_sandbox = run_pytest_in_sandbox
    monkeypatch.setitem(sys.modules, "evolution.code.sandbox_runner", fake_module)
    return fake_module


def _write_file_of_size(path: Path, size_bytes: int) -> None:
    """Create a file containing exactly ``size_bytes`` bytes."""
    # Pad with a printable ASCII repeat so the file is also a valid Python file
    # (ruff is mocked anyway, so the actual content does not matter — but using
    # a comment shape keeps human inspection easier).
    payload = ("# " + ("x" * max(0, size_bytes - 2))).encode("utf-8")
    payload = payload[:size_bytes].ljust(size_bytes, b"x")
    path.write_bytes(payload)
    assert path.stat().st_size == size_bytes


def _mock_ruff_completed(stdout_json, returncode: int = 1):
    """Build a mock subprocess.CompletedProcess for ``ruff check``.

    returncode=0 if zero violations, =1 if any violations (per ruff semantics).
    """
    class _CP:
        def __init__(self):
            self.stdout = json.dumps(stdout_json)
            self.stderr = ""
            self.returncode = returncode
    return _CP()


# ── The 6 tests ────────────────────────────────────────────────────────────


class TestCodeFitness:
    """Six unit tests for ``score_candidate`` covering all three scoring stages."""

    def test_pytest_pass_gives_score_1(self, tmp_path, monkeypatch):
        """30/30 pytest pass + baseline-equal size + zero ruff → composite=1.0."""
        _install_fake_sandbox_runner(monkeypatch, passed=30, total=30, failures=[])

        evolved_path = tmp_path / "ansi_strip.py"
        _write_file_of_size(evolved_path, 1784)  # exactly baseline size

        from evolution.code import code_fitness as cf

        with patch.object(cf.subprocess, "run", return_value=_mock_ruff_completed([], returncode=0)):
            result = cf.score_candidate(
                target_path=tmp_path / "target_ansi_strip.py",
                evolved_path=evolved_path,
                eval_dir=tmp_path / "eval",
                baseline_size=1784,
                train_test_ids=None,
            )

        assert result.pytest_score == 1.0
        assert result.size_component == 1.0
        assert result.ruff_score == 1.0
        assert result.composite == pytest.approx(1.0, abs=1e-9)
        assert result.decision == "accept"
        assert result.reject_reason == ""

    def test_pytest_fail_gives_zero_and_reject(self, tmp_path, monkeypatch):
        """29/30 pytest → composite=0.0, decision='reject', reject_reason contains 'pytest_fail'."""
        failure = {
            "test_name": "test_sgr_bold",
            "assertion_msg": "AssertionError: expected 'bold', got ''",
            "traceback_one_line": "test_ansi_strip.py:42 AssertionError",
        }
        _install_fake_sandbox_runner(monkeypatch, passed=29, total=30, failures=[failure])

        evolved_path = tmp_path / "ansi_strip.py"
        _write_file_of_size(evolved_path, 1784)

        from evolution.code import code_fitness as cf

        # Ruff should NOT be called when pytest fails (early-return path).
        with patch.object(cf.subprocess, "run") as mock_run:
            result = cf.score_candidate(
                target_path=tmp_path / "target_ansi_strip.py",
                evolved_path=evolved_path,
                eval_dir=tmp_path / "eval",
                baseline_size=1784,
                train_test_ids=None,
            )
            # Verify ruff subprocess was not invoked on a pytest-fail short-circuit
            assert mock_run.call_count == 0

        assert result.composite == 0.0
        assert result.decision == "reject"
        assert "pytest_fail" in result.reject_reason
        assert "test_sgr_bold" in result.reject_reason
        # D-16 feedback: pytest_failures must be populated for reflection prompt
        assert len(result.pytest_failures) == 1
        assert result.pytest_failures[0]["test_name"] == "test_sgr_bold"

    def test_size_within_soft_threshold_gives_partial_score(self, tmp_path, monkeypatch):
        """ratio=1.15 with soft_threshold=1.3 → 0.7 < size_component < 1.0."""
        _install_fake_sandbox_runner(monkeypatch, passed=30, total=30, failures=[])

        evolved_path = tmp_path / "ansi_strip.py"
        evolved_size = int(1784 * 1.15)  # ratio = 1.15, inside (1.0, 1.3] band
        _write_file_of_size(evolved_path, evolved_size)

        from evolution.code import code_fitness as cf

        with patch.object(cf.subprocess, "run", return_value=_mock_ruff_completed([], returncode=0)):
            result = cf.score_candidate(
                target_path=tmp_path / "target_ansi_strip.py",
                evolved_path=evolved_path,
                eval_dir=tmp_path / "eval",
                baseline_size=1784,
                train_test_ids=None,
            )

        assert result.decision == "accept"
        assert 0.7 < result.size_component < 1.0, (
            f"size_component={result.size_component} should be in (0.7, 1.0) "
            f"for ratio=1.15 under D-12 with soft_threshold=1.3"
        )

    def test_size_over_hard_threshold_rejects(self, tmp_path, monkeypatch):
        """ratio=1.6 → decision='reject', reject_reason contains 'size_oversize'.

        Verifies the size hard gate even when pytest is 100% passing.
        """
        _install_fake_sandbox_runner(monkeypatch, passed=30, total=30, failures=[])

        evolved_path = tmp_path / "ansi_strip.py"
        evolved_size = int(1784 * 1.6)  # ratio = 1.6, beyond ×1.5 hard ceiling
        _write_file_of_size(evolved_path, evolved_size)

        from evolution.code import code_fitness as cf

        with patch.object(cf.subprocess, "run", return_value=_mock_ruff_completed([], returncode=0)):
            result = cf.score_candidate(
                target_path=tmp_path / "target_ansi_strip.py",
                evolved_path=evolved_path,
                eval_dir=tmp_path / "eval",
                baseline_size=1784,
                train_test_ids=None,
            )

        assert result.decision == "reject"
        assert "size_oversize" in result.reject_reason
        assert "1.60x" in result.reject_reason

    def test_ruff_zero_violations_gives_1(self, tmp_path, monkeypatch):
        """ruff returns [] → ruff_score=1.0."""
        _install_fake_sandbox_runner(monkeypatch, passed=30, total=30, failures=[])

        evolved_path = tmp_path / "ansi_strip.py"
        _write_file_of_size(evolved_path, 1784)

        from evolution.code import code_fitness as cf

        # ruff returncode=0 when no violations
        with patch.object(cf.subprocess, "run", return_value=_mock_ruff_completed([], returncode=0)):
            result = cf.score_candidate(
                target_path=tmp_path / "target_ansi_strip.py",
                evolved_path=evolved_path,
                eval_dir=tmp_path / "eval",
                baseline_size=1784,
                train_test_ids=None,
            )

        assert result.ruff_score == 1.0
        assert result.ruff_violations == 0
        assert result.ruff_findings == []

    def test_ruff_3_violations_gives_0_4(self, tmp_path, monkeypatch):
        """ruff returns 3 violations → ruff_score=0.4 (D-13 bucket [3,5])."""
        _install_fake_sandbox_runner(monkeypatch, passed=30, total=30, failures=[])

        evolved_path = tmp_path / "ansi_strip.py"
        _write_file_of_size(evolved_path, 1784)

        ruff_violations_json = [
            {
                "code": "F401",
                "message": "`os` imported but unused",
                "filename": str(evolved_path),
                "location": {"row": 1, "column": 8},
                "severity": "error",
            },
            {
                "code": "E501",
                "message": "line too long (135 > 120)",
                "filename": str(evolved_path),
                "location": {"row": 17, "column": 121},
                "severity": "error",
            },
            {
                "code": "W605",
                "message": "invalid escape sequence",
                "filename": str(evolved_path),
                "location": {"row": 22, "column": 14},
                "severity": "warning",
            },
        ]

        from evolution.code import code_fitness as cf

        # ruff exit code 1 when violations found — must NOT raise CalledProcessError
        # (Pitfall 2: check=False is correct, exit 1 is normal).
        with patch.object(
            cf.subprocess, "run", return_value=_mock_ruff_completed(ruff_violations_json, returncode=1)
        ):
            result = cf.score_candidate(
                target_path=tmp_path / "target_ansi_strip.py",
                evolved_path=evolved_path,
                eval_dir=tmp_path / "eval",
                baseline_size=1784,
                train_test_ids=None,
            )

        assert result.ruff_violations == 3
        assert result.ruff_score == 0.4
        # D-16 feedback: ruff_findings should carry structured detail
        assert len(result.ruff_findings) == 3
        assert result.ruff_findings[0]["rule_id"] == "F401"
        assert result.ruff_findings[0]["line"] == 1
        # composite math: 0.80*1.0 + 0.10*1.0 + 0.10*0.4 = 0.94
        assert result.composite == pytest.approx(0.94, abs=1e-9)
        assert result.decision == "accept"


# ── 21-04↔21-05 contract integration test (no mock sandbox_runner) ─────────


class TestRealSandboxIntegration:
    """End-to-end smoke that exercises code_fitness ↔ sandbox_runner with NO
    mocking of run_pytest_in_sandbox. Catches the cross-plan signature drift
    that the earlier mock-based suite missed (verifier 21-VERIFICATION.md).

    Skips when ``HERMES_AGENT_REPO`` / ``~/.hermes/hermes-agent`` is unreachable
    so CI without that checkout stays green. The real ansi_strip.py + its
    test file are used because sandbox_runner hardcodes the in-sandbox names
    to ``tools/ansi_strip.py`` and ``test_ansi_strip.py``.
    """

    def test_score_candidate_real_sandbox_baseline(self, tmp_path):
        """Baseline score against the unmodified hermes-agent ansi_strip.py.

        Asserts:
        - score_candidate calls run_pytest_in_sandbox with the correct 4-arg
          contract (would raise TypeError on signature drift)
        - The real pytest subprocess returns >= 1 passed test
        - Returned CodeFitness has the expected shape
        """
        import os

        hermes_repo = Path(
            os.getenv("HERMES_AGENT_REPO") or Path.home() / ".hermes" / "hermes-agent"
        )
        target_path = hermes_repo / "tools" / "ansi_strip.py"
        test_file_path = hermes_repo / "tests" / "tools" / "test_ansi_strip.py"
        if not target_path.exists() or not test_file_path.exists():
            pytest.skip(f"hermes-agent not reachable at {hermes_repo}")

        from evolution.code.code_fitness import score_candidate

        eval_dir = tmp_path / "eval"
        eval_dir.mkdir()

        # Run baseline: evolved == original.
        result = score_candidate(
            target_path=target_path,
            evolved_path=target_path,
            eval_dir=eval_dir,
            baseline_size=target_path.stat().st_size,
            train_test_ids=None,
            test_file_path=test_file_path,
        )

        # Real sandbox MUST have run pytest and got at least 1 passed test;
        # ansi_strip.py shipping with a green test suite is a project invariant.
        assert result.pytest_total >= 1, "real pytest subprocess produced no tests"
        assert result.pytest_passed == result.pytest_total, "baseline must be 100% green"
        assert result.size_component == pytest.approx(1.0, abs=1e-9), "baseline size == baseline"
        assert result.decision == "accept", f"baseline rejected: {result.reject_reason}"
        assert result.composite > 0.7
