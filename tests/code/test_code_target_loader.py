"""Tests for evolution.code.code_target_loader.

Covers four canonical paths (per VALIDATION.md Per-Task Verification Map):
  1. test_find_target_by_relative_path — mock hermes-agent tree, verify
     CodeTarget construction and field population.
  2. test_ast_parse_discovers_30_tests — real hermes-agent integration;
     skipped if HERMES_AGENT_REPO unreachable.
  3. test_stratified_split_respects_buckets — pure-logic check of bucket
     accounting + holdout total + train/holdout disjointness.
  4. test_loader_rejects_evolution_path — T-21-RECURSE guard; refuses to
     evolve `evolution/` itself.

The mock hermes-agent builder (`_build_mock_hermes`) writes a synthetic
`tools/ansi_strip.py` (small but valid Python) plus a `tests/tools/test_ansi_strip.py`
that contains 30 `def test_*` functions spread across CSI/SGR/OSC/other
keyword buckets so the AST scan + stratification can be exercised offline.
"""

import os
from pathlib import Path

import pytest

from evolution.code.code_target_loader import (
    HOLDOUT_PER_BUCKET,
    CodeTarget,
    find_target,
    find_target_tests,
    stratify_tests,
)


# ────────────────────────────────────────────────────────────────────
# Mock hermes-agent builder.
# ────────────────────────────────────────────────────────────────────


# 30 test function names spread across the four buckets so the AST scan
# (which classifies by keyword) populates each bucket non-trivially.
_MOCK_TEST_NAMES: list[str] = [
    # CSI bucket (cursor/move/csi/alt_screen/keypad/charset/dcs/8bit — 12 names)
    "test_cursor_show_hide",
    "test_cursor_shape",
    "test_save_restore_cursor",
    "test_alt_screen",
    "test_bracketed_paste",
    "test_keypad_modes",
    "test_reverse_index",
    "test_index_and_newline",
    "test_charset_selection",
    "test_dcs",
    "test_8bit_csi",
    "test_8bit_standalone",
    # SGR bucket (color/bold/reset/sgr — 9 names)
    "test_color_red",
    "test_color_blue",
    "test_truecolor_rgb",
    "test_bold_underline",
    "test_reset_sgr",
    "test_stacked_sgr",
    "test_blink",
    "test_dim_attribute",
    "test_reverse_video",
    # OSC bucket (osc/title/hyperlink/bel — 5 names)
    "test_osc_title",
    "test_osc_hyperlink",
    "test_bel_terminator",
    "test_st_terminator",
    "test_hyperlink_preserves_text",
    # other bucket (catch-all — 4 names; none of these match any keyword)
    "test_plain_text",
    "test_empty",
    "test_none",
    "test_whitespace_preserved",
]
# Sanity: total == 30 so the discovery assertion is exact.
assert len(_MOCK_TEST_NAMES) == 30, "mock must contain exactly 30 test functions"


def _build_mock_hermes(tmp_path: Path) -> Path:
    """Create a minimal hermes-agent layout under `tmp_path`.

    Layout written:
        tmp_path/
        ├── tools/
        │   ├── __init__.py
        │   └── ansi_strip.py        (44 lines of valid python; `import re`)
        └── tests/
            └── tools/
                ├── __init__.py
                └── test_ansi_strip.py   (30 def test_* funcs in a TestStripAnsi class)

    Returns:
        `tmp_path` (so the caller can use it as `hermes_repo`).
    """
    # ── tools package ─
    tools_dir = tmp_path / "tools"
    tools_dir.mkdir()
    (tools_dir / "__init__.py").write_text("")

    # Minimal but valid 44-line ansi_strip.py — short enough to test, large
    # enough to exercise file-size accounting (>0 bytes).
    ansi_strip_src = (
        '"""Strip ANSI escape sequences (mock for tests)."""\n'
        "\n"
        "import re\n"
        "\n"
        "_ESC_RE = re.compile(\n"
        "    r'\\x1b'           # ESC\n"
        "    r'\\[?'             # optional [\n"
        "    r'[0-9;]*'          # parameters\n"
        "    r'[@-~]'            # final byte\n"
        ")\n"
        "\n"
        "\n"
        "def strip_ansi(text: str) -> str:\n"
        "    \"\"\"Remove ANSI escape sequences from text.\"\"\"\n"
        "    if not text:\n"
        "        return text\n"
        "    return _ESC_RE.sub('', text)\n"
    )
    (tools_dir / "ansi_strip.py").write_text(ansi_strip_src)

    # ── tests/tools package ─
    tests_tools_dir = tmp_path / "tests" / "tools"
    tests_tools_dir.mkdir(parents=True)
    (tmp_path / "tests").joinpath("__init__.py").write_text("")
    (tests_tools_dir / "__init__.py").write_text("")

    # Build a test file with 30 def test_* methods nested in a class
    # (matches real hermes-agent layout where tests are class-organized).
    lines = [
        '"""Mock test_ansi_strip.py for unit tests."""',
        "",
        "from tools.ansi_strip import strip_ansi",
        "",
        "",
        "class TestStripAnsiMock:",
    ]
    for name in _MOCK_TEST_NAMES:
        lines.append(f"    def {name}(self):")
        lines.append("        assert strip_ansi('') == ''")
    test_file_text = "\n".join(lines) + "\n"
    (tests_tools_dir / "test_ansi_strip.py").write_text(test_file_text)

    return tmp_path


# ────────────────────────────────────────────────────────────────────
# Tests
# ────────────────────────────────────────────────────────────────────


def test_find_target_by_relative_path(tmp_path):
    """find_target() resolves a component into a CodeTarget with populated fields."""
    hermes_repo = _build_mock_hermes(tmp_path)

    target = find_target("tools/ansi_strip.py", hermes_repo)

    assert isinstance(target, CodeTarget)
    assert target.component_path.exists()
    assert target.component_path == hermes_repo / "tools" / "ansi_strip.py"
    # Inferred test file path follows the `tests/<package>/test_<leaf>` convention.
    assert target.test_file_path == hermes_repo / "tests" / "tools" / "test_ansi_strip.py"
    assert target.test_file_path.exists()
    assert target.baseline_size_bytes > 0
    assert isinstance(target.original_source, str)
    assert "strip_ansi" in target.original_source
    assert target.schema_version == "1.0"
    # hermes_agent_commit is best-effort; in tmp_path (no git repo) it should be empty.
    assert isinstance(target.hermes_agent_commit, str)


def test_ast_parse_discovers_30_tests():
    """find_target_tests() returns a manifest with >=30 entries on real hermes-agent.

    Skipped when HERMES_AGENT_REPO (or default ~/.hermes/hermes-agent) is
    unreachable, so CI environments without the dep can still pass.
    """
    repo_env = os.getenv("HERMES_AGENT_REPO")
    if repo_env:
        hermes_repo = Path(repo_env).expanduser()
    else:
        hermes_repo = Path.home() / ".hermes" / "hermes-agent"

    if not hermes_repo.exists():
        pytest.skip(f"hermes-agent not found at {hermes_repo} (set HERMES_AGENT_REPO)")

    component = "tools/ansi_strip.py"
    if not (hermes_repo / component).exists():
        pytest.skip(f"{component} missing from hermes-agent at {hermes_repo}")

    target = find_target(component, hermes_repo)
    if not target.test_file_path.exists():
        pytest.skip(f"test file missing: {target.test_file_path}")

    manifest = find_target_tests(target)

    # RESEARCH.md anchors 30 native pytests; allow >= because hermes-agent may grow.
    assert len(manifest) >= 30, f"expected >= 30 tests, got {len(manifest)}"
    # All entries must have the required keys.
    for entry in manifest:
        assert set(entry.keys()) >= {
            "test_id", "bucket", "parametrize_count", "schema_version", "hermes_agent_commit"
        }
        assert entry["test_id"].startswith("test_")
        assert entry["bucket"] in {"csi", "sgr", "osc", "other"}
        assert entry["parametrize_count"] >= 1


def test_stratified_split_respects_buckets():
    """stratify_tests() honors per-bucket holdout quotas and disjointness.

    Constructs a mock manifest with csi×8, sgr×7, osc×6, other×5 = 26 entries
    and verifies:
      - holdout total == sum(HOLDOUT_PER_BUCKET.values()) == 10
      - train and holdout are disjoint
      - train + holdout == input set
      - per-bucket holdout count matches HOLDOUT_PER_BUCKET
    """
    manifest = []
    counts = {"csi": 8, "sgr": 7, "osc": 6, "other": 5}
    for bucket, n in counts.items():
        for i in range(n):
            manifest.append({
                "test_id": f"test_{bucket}_{i}",
                "bucket": bucket,
                "parametrize_count": 1,
                "schema_version": "1.0",
                "hermes_agent_commit": "",
            })

    result = stratify_tests(manifest, seed=42)
    train_ids = result["train_ids"]
    holdout_ids = result["holdout_ids"]

    # Holdout total matches HOLDOUT_PER_BUCKET sum (4+3+2+1 = 10).
    assert len(holdout_ids) == sum(HOLDOUT_PER_BUCKET.values()) == 10

    # Disjointness — no test in both sets.
    assert len(set(holdout_ids) & set(train_ids)) == 0

    # Union recovers the full input set (no entry dropped).
    all_input_ids = {e["test_id"] for e in manifest}
    assert set(train_ids) | set(holdout_ids) == all_input_ids

    # Per-bucket holdout count matches the quota (since each bucket has enough).
    holdout_buckets = {}
    for tid in holdout_ids:
        # test_id has the form "test_<bucket>_<i>"
        bucket = tid.split("_")[1]
        holdout_buckets[bucket] = holdout_buckets.get(bucket, 0) + 1
    for bucket, quota in HOLDOUT_PER_BUCKET.items():
        assert holdout_buckets.get(bucket, 0) == quota, (
            f"bucket {bucket!r}: expected {quota} holdout entries, got {holdout_buckets.get(bucket, 0)}"
        )


def test_loader_rejects_evolution_path(tmp_path):
    """find_target() raises ValueError for any component beginning with 'evolution/'.

    This is the T-21-RECURSE mitigation — we must never evolve our own evolver.
    """
    hermes_repo = _build_mock_hermes(tmp_path)

    # Place a dummy "evolution/core/config.py" inside the mock repo so the
    # filesystem-existence check is not what trips first — the guard MUST fire
    # purely on the path prefix.
    (hermes_repo / "evolution" / "core").mkdir(parents=True)
    (hermes_repo / "evolution" / "core" / "config.py").write_text("# dummy\n")

    with pytest.raises(ValueError, match="evolution/"):
        find_target("evolution/core/config.py", hermes_repo)
