"""Isolated subprocess runner for candidate code evaluation (Phase 21).

The sandbox is the single mitigation point for three high-severity
threats from the Phase 21 threat register:

- T-21-SECRET (Information Disclosure): every candidate subprocess
  runs with a restricted environment that has ALL recognised LLM API
  key environment variables stripped out (`build_restricted_env`).
  An evolved-but-malicious candidate can therefore not exfiltrate
  ``OPENAI_API_KEY`` / ``OPENROUTER_API_KEY`` / etc.
- T-21-DOS (Denial of Service): each subprocess is bounded by a
  ``timeout`` parameter (default 120s). On timeout we synthesise a
  failure record ``(0, -1, [{"test_name": "timeout", ...}])``
  instead of re-raising — score_candidate() can then mark the
  candidate as rejected without crashing the optimisation loop.
- T-21-LEAK (Information Disclosure): the per-candidate working
  directory under ``eval_dir_base/<run_id>/`` is wiped with
  ``shutil.rmtree(eval_dir, ignore_errors=True)`` in a ``finally``
  block — regardless of whether pytest passes, fails, times out,
  or the Python interpreter dies between subprocess and cleanup.

Pitfall 3 defence (`PYTHONPATH=str(eval_dir)`): the candidate runs
with a PYTHONPATH that contains ONLY ``eval_dir``. The real
hermes-agent source tree is NOT importable from inside the
sandbox, so a candidate that tries ``import hermes.agent`` (or any
other real package) will fail at import time inside pytest and be
recorded as a clean failure — not crash the parent process.

Analog: ``evolution/benchmarks/tblite_runner.py`` (Phase 20).
Phase 21 jobs are short (a single pytest invocation), so we use
``subprocess.run`` with a single ``timeout=`` argument rather than
the Popen + 2-thread heartbeat machinery from tblite_runner.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


# ── Module-level constants ─────────────────────────────────────────────────────

# T-21-SECRET mitigation: every recognised LLM provider API key
# environment variable is removed before the candidate subprocess
# starts. This is the canonical list — adding a new provider means
# adding its key here so build_restricted_env() will strip it.
_API_KEY_ENV_VARS = {
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "DASHSCOPE_KEY",
    "EVOLUTION_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
}

# Regex for "FAILED <test_id> - <ExcType>: <message>" lines emitted by
# ``pytest --tb=line``. ``test_id`` may include double colons for the
# parametrised form ``test_file.py::test_name[param]``.
_FAILED_LINE_RE = re.compile(
    r"^FAILED\s+(?P<test_id>\S+?)\s*-\s*(?P<exc>[^:]+):\s*(?P<msg>.*)$"
)

# Regex for the pytest summary line. Examples we must match:
#   "1 passed in 0.04s"
#   "2 failed, 1 passed in 0.10s"
#   "5 passed, 1 warning in 0.20s"
_COUNT_RE = re.compile(r"(?P<n>\d+)\s+(?P<kind>passed|failed)")


# ── Public API ─────────────────────────────────────────────────────────────────


def build_restricted_env(eval_dir: Path) -> dict:
    """Return a copy of the current environment with API keys stripped.

    The returned env additionally pins ``HERMES_AGENT_REPO`` and
    ``PYTHONPATH`` to ``str(eval_dir)`` so that imports inside the
    candidate subprocess resolve only to the sandbox copy of the
    minimal import closure (``tools/__init__.py`` + ``tools/ansi_strip.py``
    + ``test_ansi_strip.py``) — never to the real hermes-agent tree.

    Args:
        eval_dir: The per-candidate scratch directory. Must exist; the
            caller (run_pytest_in_sandbox) creates it before invocation.

    Returns:
        A new ``dict`` suitable for passing to ``subprocess.run(env=...)``.
        Never mutates ``os.environ``.
    """
    env = os.environ.copy()
    for key in _API_KEY_ENV_VARS:
        env.pop(key, None)
    # Pitfall 3 defence: HERMES_AGENT_REPO is redirected to the sandbox
    # so any candidate code that reads it lands inside eval_dir, not
    # the real repo. PYTHONPATH is the harder gate — it controls
    # ``import`` resolution and MUST be the eval_dir only.
    env["HERMES_AGENT_REPO"] = str(eval_dir)
    env["PYTHONPATH"] = str(eval_dir)
    return env


def run_pytest_in_sandbox(
    candidate_path: Path,
    eval_dir_base: Path,
    test_file_path: Path,
    run_id: str,
    timeout_seconds: int = 120,
) -> tuple[int, int, list[dict]]:
    """Run pytest on ``candidate_path`` inside an isolated sandbox.

    The sandbox topology written under ``eval_dir_base/<run_id>/``::

        <eval_dir>/
            tools/
                __init__.py            (empty — minimal import closure)
                ansi_strip.py          (= candidate_path)
            test_ansi_strip.py         (= test_file_path)

    pytest is invoked with ``-x --tb=line -q --no-header`` against the
    single test file. The working directory and ``PYTHONPATH`` are both
    pinned to ``eval_dir`` so the candidate cannot reach the real
    hermes-agent source (Pitfall 3).

    On ``subprocess.TimeoutExpired`` (T-21-DOS) we return a synthetic
    failure record ``(0, -1, [{"test_name": "timeout", ...}])`` rather
    than re-raising — score_candidate() can then mark the candidate
    rejected without bringing down the optimisation loop.

    The ``finally`` block (T-21-LEAK / Pitfall 6) wipes ``eval_dir``
    with ``shutil.rmtree(..., ignore_errors=True)`` on every exit
    path — success, failure, timeout, KeyboardInterrupt.

    Args:
        candidate_path: Path to the candidate Python file produced by
            the evolutionary loop. Copied to ``tools/ansi_strip.py``
            inside the sandbox.
        eval_dir_base: Parent directory for per-candidate sandboxes
            (e.g. ``~/.hermes/tmp/code_eval_<ts>/``).
        test_file_path: Path to the pytest file that will exercise the
            candidate. Copied to ``test_ansi_strip.py`` inside the
            sandbox.
        run_id: Unique-per-candidate identifier; becomes the leaf
            directory name under ``eval_dir_base``.
        timeout_seconds: Hard wallclock limit for the pytest subprocess.
            Defaults to 120s per D-20.

    Returns:
        A 3-tuple ``(passed, total, failures)``:
        - ``passed``: number of tests that passed (``0`` on timeout).
        - ``total``: number of tests collected (``-1`` on timeout — the
          sentinel ``-1`` distinguishes timeout from "0 passed, 0
          collected" which would be ``(0, 0, [])``).
        - ``failures``: list of ``{"test_name", "assertion_msg",
          "traceback_one_line"}`` dicts; empty list when all tests pass.
    """
    eval_dir = eval_dir_base / run_id
    try:
        eval_dir.mkdir(parents=True, exist_ok=True)

        # Minimal import closure (D-09): only the bare files needed to
        # exercise the candidate are written into the sandbox — NOT the
        # whole hermes-agent tree (Pitfall 3).
        tools_dir = eval_dir / "tools"
        tools_dir.mkdir(exist_ok=True)
        (tools_dir / "__init__.py").write_text("")
        shutil.copy2(candidate_path, tools_dir / "ansi_strip.py")
        shutil.copy2(test_file_path, eval_dir / "test_ansi_strip.py")

        # T-21-SECRET + Pitfall 3 defences live inside build_restricted_env.
        # We rebuild PYTHONPATH after the .copy() in case any caller
        # passes a pre-built env via a future overload — defence in depth.
        restricted_env = build_restricted_env(eval_dir)
        restricted_env["PYTHONPATH"] = str(eval_dir)

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "test_ansi_strip.py",
                    "-x",
                    "--tb=line",
                    "-q",
                    "--no-header",
                ],
                cwd=str(eval_dir),
                env=restricted_env,
                timeout=timeout_seconds,
                capture_output=True,
                text=True,
            )
        except subprocess.TimeoutExpired:
            # T-21-DOS: synthesise the failure record, do not re-raise.
            return (
                0,
                -1,
                [
                    {
                        "test_name": "timeout",
                        "assertion_msg": f"Timeout after {timeout_seconds}s",
                        "traceback_one_line": "",
                    }
                ],
            )

        return _parse_pytest_output(result.stdout, result.returncode)
    finally:
        # T-21-LEAK / Pitfall 6: wipe the per-candidate scratch dir on
        # EVERY exit path. ignore_errors=True so cleanup itself can never
        # mask a real test failure.
        shutil.rmtree(eval_dir, ignore_errors=True)


# ── Internal helpers ───────────────────────────────────────────────────────────


def _parse_pytest_output(stdout: str, returncode: int) -> tuple[int, int, list[dict]]:
    """Parse pytest ``--tb=line -q --no-header`` output.

    Args:
        stdout: Captured stdout from the pytest subprocess.
        returncode: ``subprocess.CompletedProcess.returncode``. pytest
            convention: 0 = all passed, 1 = some failed, 2 = internal
            error, 5 = no tests collected.

    Returns:
        ``(passed, total, failures)`` — see ``run_pytest_in_sandbox``.
        Empty/unparseable output with ``returncode == 0`` yields
        ``(0, 0, [])`` — the caller decides how to score that.
    """
    passed = 0
    failed = 0
    failures: list[dict] = []

    for line in stdout.splitlines():
        # Failure lines come from `--tb=line` mode and look like:
        #   FAILED test_x.py::test_name - AssertionError: <msg>
        match = _FAILED_LINE_RE.match(line.strip())
        if match:
            failures.append(
                {
                    "test_name": match.group("test_id"),
                    "assertion_msg": match.group("msg").strip(),
                    "traceback_one_line": line.strip(),
                }
            )

    # Pytest's `-q` summary line: e.g. "2 failed, 1 passed in 0.10s".
    for match in _COUNT_RE.finditer(stdout):
        n = int(match.group("n"))
        if match.group("kind") == "passed":
            passed = n
        elif match.group("kind") == "failed":
            failed = n

    total = passed + failed

    # Edge case: returncode==0 but no summary parsed (empty stdout).
    if returncode == 0 and total == 0 and not failures:
        return (0, 0, [])

    return (passed, total, failures)


__all__ = ["build_restricted_env", "run_pytest_in_sandbox"]
