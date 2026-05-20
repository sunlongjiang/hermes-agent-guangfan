"""Unit tests for evolution/code/sandbox_runner.py.

Coverage matrix (per Plan 21-05 task 2 + 21-VALIDATION.md):

- test_restricted_env_removes_api_keys      -> T-21-SECRET
- test_sandbox_timeout_returns_zero_fitness -> T-21-DOS
- test_eval_dir_is_cleaned_after_run        -> T-21-LEAK
- test_candidate_with_implicit_hermes_import_fails_cleanly
                                            -> T-21-IMPORT / Pitfall 3

All tests mock ``subprocess.run`` (except the cleanup test which can
optionally exercise a real subprocess if pytest happens to be on the
worker path). NO real LLM invocation; NO real openevolve invocation;
NO writes outside ``tmp_path``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evolution.code.sandbox_runner import (
    _API_KEY_ENV_VARS,
    build_restricted_env,
    run_pytest_in_sandbox,
)


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _write_dummy_candidate(path: Path) -> None:
    """Create a minimal but valid Python candidate file."""
    path.write_text(
        "import re\n"
        "_ANSI_RE = re.compile(r'\\x1b\\[[0-9;]*m')\n"
        "def strip_ansi(s):\n"
        "    return _ANSI_RE.sub('', s)\n"
    )


def _write_dummy_test(path: Path) -> None:
    """Create a minimal pytest file that exercises the candidate."""
    path.write_text(
        "from tools.ansi_strip import strip_ansi\n"
        "def test_pass():\n"
        "    assert strip_ansi('\\x1b[31mhi\\x1b[0m') == 'hi'\n"
    )


# ── T-21-SECRET ────────────────────────────────────────────────────────────────


class TestRestrictedEnv:
    def test_restricted_env_removes_api_keys(self, tmp_path, monkeypatch):
        """T-21-SECRET: every key in _API_KEY_ENV_VARS is stripped."""
        # Force a value for every key so we can prove it is removed, not
        # merely absent from the parent env.
        for key in _API_KEY_ENV_VARS:
            monkeypatch.setenv(key, "sk-test-leaky-value")

        env = build_restricted_env(tmp_path)

        for key in _API_KEY_ENV_VARS:
            assert key not in env, f"T-21-SECRET violation: {key!r} leaked to candidate env"

        # OPENAI_API_KEY is the canonical example; assert explicitly so a
        # grep over this file still catches the requirement.
        assert "OPENAI_API_KEY" not in env

        # HERMES_AGENT_REPO must be redirected to the sandbox dir, not
        # the real repo (Pitfall 3).
        assert "HERMES_AGENT_REPO" in env
        assert env["HERMES_AGENT_REPO"] == str(tmp_path)

        # PYTHONPATH must be pinned to the sandbox dir only.
        assert "PYTHONPATH" in env
        assert env["PYTHONPATH"] == str(tmp_path)

# ── T-21-DOS ───────────────────────────────────────────────────────────────────


class TestSandboxTimeout:
    def test_sandbox_timeout_returns_zero_fitness(self, tmp_path):
        """T-21-DOS: subprocess.TimeoutExpired -> (0, -1, [timeout_rec]); no raise."""
        candidate_path = tmp_path / "candidate.py"
        test_file_path = tmp_path / "test_dummy.py"
        _write_dummy_candidate(candidate_path)
        _write_dummy_test(test_file_path)
        eval_dir_base = tmp_path / "evals"

        with patch(
            "evolution.code.sandbox_runner.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="pytest", timeout=120),
        ):
            result = run_pytest_in_sandbox(
                candidate_path,
                eval_dir_base,
                test_file_path,
                "test_run",
                timeout_seconds=120,
            )

        assert result == (
            0,
            -1,
            [
                {
                    "test_name": "timeout",
                    "assertion_msg": "Timeout after 120s",
                    "traceback_one_line": "",
                }
            ]
        ), f"timeout return shape regressed: {result!r}"

# ── T-21-LEAK ──────────────────────────────────────────────────────────────────


class TestEvalDirCleanup:
    def test_eval_dir_is_cleaned_after_run(self, tmp_path):
        """T-21-LEAK: ``eval_dir`` is removed from disk after a successful run."""
        candidate_path = tmp_path / "candidate.py"
        test_file_path = tmp_path / "test_dummy.py"
        _write_dummy_candidate(candidate_path)
        _write_dummy_test(test_file_path)
        eval_dir_base = tmp_path / "evals"
        run_id = "test_cleanup"

        # Mock subprocess.run to simulate a clean "1 passed" pytest run
        # without actually spawning a process.
        mock_result = MagicMock()
        mock_result.stdout = "1 passed in 0.04s\n"
        mock_result.returncode = 0
        with patch(
            "evolution.code.sandbox_runner.subprocess.run",
            return_value=mock_result,
        ):
            run_pytest_in_sandbox(
                candidate_path,
                eval_dir_base,
                test_file_path,
                run_id,
                timeout_seconds=60,
            )

        assert not (eval_dir_base / run_id).exists(), (
            "T-21-LEAK violation: eval_dir was not cleaned up after run"
        )

# ── T-21-IMPORT / Pitfall 3 ────────────────────────────────────────────────────


class TestImplicitHermesImport:
    def test_candidate_with_implicit_hermes_import_fails_cleanly(self, tmp_path):
        """Pitfall 3: a candidate that `import hermes`s must fail in pytest,
        not crash the sandbox or leak across processes."""
        candidate_path = tmp_path / "candidate.py"
        candidate_path.write_text(
            "import hermes  # implicit boundary violation\n"
            "def strip_ansi(s):\n"
            "    return s\n"
        )
        test_file_path = tmp_path / "test_dummy.py"
        _write_dummy_test(test_file_path)
        eval_dir_base = tmp_path / "evals"

        # pytest would discover the ImportError at collection time and
        # exit with rc=1, printing a FAILED line.
        mock_result = MagicMock()
        mock_result.stdout = (
            "FAILED test_ansi_strip.py::test_pass - ImportError: No module named 'hermes'\n"
            "1 failed in 0.05s\n"
        )
        mock_result.returncode = 1

        with patch(
            "evolution.code.sandbox_runner.subprocess.run",
            return_value=mock_result,
        ):
            # No exception must escape — that is the "fails cleanly" core.
            result = run_pytest_in_sandbox(
                candidate_path,
                eval_dir_base,
                test_file_path,
                "import_boundary",
                timeout_seconds=60,
            )

        passed, total, failures = result
        assert passed == 0, f"expected 0 passed on import boundary violation, got {passed}"
        assert len(failures) > 0, "expected at least one recorded failure"
        # The FAILED line carries the ImportError signature — verify the
        # parser surfaced it so reject_reason='pytest_fail' downstream
        # can reason about it.
        assert "ImportError" in failures[0]["traceback_one_line"], (
            f"expected ImportError traceback line; got {failures[0]!r}"
        )
