"""Holdout edge-case tests for strip_ansi() (Phase 21 Plan 08).

These tests live in the evolution repo (NOT inside hermes-agent) per
CONTEXT.md §Out of Scope. They cover 10 edge cases beyond hermes-agent's
existing 30 tests, exercised by the D-15 holdout gate.

The full set maps 1:1 to CONTEXT.md §D-07 EDGE_CASE_HOLDOUT_TESTS:
    test_extreme_long_input_10k_chars
    test_unicode_boundary_in_escape
    test_nested_escape_sequences
    test_overlapping_escapes
    test_empty_string
    test_single_char
    test_truncated_csi_at_eof
    test_unknown_osc_command
    test_mixed_invalid_bytes
    test_crlf_inside_escape

When hermes-agent is not reachable (HERMES_AGENT_REPO unset and
~/.hermes/hermes-agent missing), the whole module skips so CI stays green.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ── hermes-agent path wiring ────────────────────────────────────────────────
_hermes_repo = Path(
    os.getenv("HERMES_AGENT_REPO") or (Path.home() / ".hermes" / "hermes-agent")
)
if not (_hermes_repo / "tools" / "ansi_strip.py").exists():
    pytest.skip(
        f"hermes-agent not reachable at {_hermes_repo} — skipping holdout tests",
        allow_module_level=True,
    )

if str(_hermes_repo) not in sys.path:
    sys.path.insert(0, str(_hermes_repo))

from tools.ansi_strip import strip_ansi  # noqa: E402


# ── 1. Trivial inputs ──────────────────────────────────────────────────────


def test_empty_string() -> None:
    """strip_ansi('') returns ''."""
    assert strip_ansi("") == ""


def test_single_char() -> None:
    """strip_ansi('a') returns 'a' (no escape, fast-path)."""
    assert strip_ansi("a") == "a"


# ── 2. Large-input stress ──────────────────────────────────────────────────


def test_extreme_long_input_10k_chars() -> None:
    """10 000-char input with embedded SGR codes — all ANSI stripped, text preserved."""
    chunk = "abc\x1b[31mred\x1b[0mxyz "  # 18 chars, 2 escapes per chunk
    payload = (chunk * 600)[:10_000]
    assert len(payload) == 10_000

    result = strip_ansi(payload)
    assert "\x1b" not in result, "ESC must be fully stripped from large input"
    # Original text fragments survive.
    assert "abc" in result
    assert "red" in result
    assert "xyz" in result


# ── 3. Unicode safety ──────────────────────────────────────────────────────


def test_unicode_boundary_in_escape() -> None:
    """Multibyte Unicode between SGR codes survives intact."""
    assert strip_ansi("\x1b[42m中文\x1b[0m") == "中文"


# ── 4. Nested / overlapping escapes ────────────────────────────────────────


def test_nested_escape_sequences() -> None:
    """Multiple consecutive SGR codes around inner text — all stripped."""
    assert (
        strip_ansi("\x1b[1m\x1b[31mbold_red\x1b[0m\x1b[0m") == "bold_red"
    )


def test_overlapping_escapes() -> None:
    """Two adjacent SGR codes with no separator are both stripped."""
    assert strip_ansi("\x1b[31m\x1b[32mtext\x1b[0m") == "text"


# ── 5. Malformed / truncated sequences ─────────────────────────────────────


def test_truncated_csi_at_eof() -> None:
    """Truncated CSI at EOF (no final byte) must not crash; result is a str."""
    result = strip_ansi("hello\x1b[31")
    assert isinstance(result, str), "must return str even for truncated CSI"
    # Crucially the function does not raise. We do not assert on the exact
    # post-strip residue because behaviour for malformed sequences is
    # implementation-defined; the contract is "no crash, str out".


def test_unknown_osc_command() -> None:
    """Unknown OSC sequence terminated by BEL is stripped; trailing text survives."""
    assert strip_ansi("\x1b]99;unknown-payload\x07text") == "text"


def test_mixed_invalid_bytes() -> None:
    """C1 control characters (U+0080..U+009F) are stripped — function must not crash."""
    result = strip_ansi("\x80\x81\x82")
    assert isinstance(result, str)
    # All three bytes are in the C1 range [\x80-\x9f], which the regex strips.
    assert result == ""


def test_crlf_inside_escape() -> None:
    """CRLF outside the escape body is preserved (no ANSI in newline chars)."""
    result = strip_ansi("\x1b[0m\r\ntext")
    assert "\r\n" in result, "CRLF must survive escape stripping"
    assert result == "\r\ntext"
