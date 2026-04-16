"""Tests for evolve_tool_descriptions -- CLI entry point and end-to-end pipeline."""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from evolution.tools.tool_loader import ToolDescription, ToolParam


# ── Test Fixtures ───────────────────────────────────────────────────────────


def _make_fake_tools() -> list[ToolDescription]:
    """Create test ToolDescription instances for mocking."""
    return [
        ToolDescription(
            name="memory",
            file_path=Path("/fake/memory.py"),
            description="Store and retrieve conversation memory",
            params=[
                ToolParam(name="action", type="string", required=True, enum=["store", "retrieve"]),
                ToolParam(name="key", type="string", required=True),
            ],
        ),
        ToolDescription(
            name="terminal",
            file_path=Path("/fake/terminal.py"),
            description="Execute shell commands",
            params=[
                ToolParam(name="command", type="string", required=True),
            ],
        ),
    ]


# ── TestCLI ─────────────────────────────────────────────────────────────────


class TestCLI:
    """CLI parameter and help text tests."""

    def test_cli_help(self):
        """--help output contains all four expected options."""
        from click.testing import CliRunner
        from evolution.tools.evolve_tool_descriptions import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "--iterations" in result.output
        assert "--eval-source" in result.output
        assert "--hermes-repo" in result.output
        assert "--dry-run" in result.output

    def test_eval_source_choices(self):
        """--eval-source only accepts 'synthetic' and 'load'."""
        from click.testing import CliRunner
        from evolution.tools.evolve_tool_descriptions import main

        runner = CliRunner()
        result = runner.invoke(main, ["--eval-source", "invalid"])
        assert result.exit_code != 0
        assert "Invalid value" in result.output or "invalid" in result.output.lower()


# ── TestDryRun ──────────────────────────────────────────────────────────────


class TestDryRun:
    """Dry-run mode tests."""

    @patch("evolution.tools.evolve_tool_descriptions.extract_tool_descriptions")
    @patch("evolution.tools.evolve_tool_descriptions.discover_tool_files")
    def test_dry_run_shows_tools_no_gepa(self, mock_discover, mock_extract):
        """dry-run validates setup, shows tools, does NOT call GEPA."""
        mock_discover.return_value = [Path("/fake/memory.py"), Path("/fake/terminal.py")]
        mock_extract.side_effect = lambda f: [
            t for t in _make_fake_tools() if str(t.file_path) == str(f)
        ]

        from evolution.tools.evolve_tool_descriptions import evolve

        with patch("dspy.GEPA") as mock_gepa:
            # Should not raise and should not call GEPA
            evolve(
                iterations=5,
                eval_source="synthetic",
                hermes_repo="/fake",
                dry_run=True,
            )
            mock_gepa.assert_not_called()


# ── TestModuleImportable ────────────────────────────────────────────────────


class TestModuleImportable:
    """Module import and entry point tests."""

    def test_module_importable(self):
        """main and evolve can be imported from the module."""
        from evolution.tools.evolve_tool_descriptions import main, evolve
        assert callable(main)
        assert callable(evolve)
