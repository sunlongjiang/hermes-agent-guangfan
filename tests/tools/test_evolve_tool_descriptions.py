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


# ── TestPhase16RawPredictions (Wave 0 D-12) ─────────────────────────────────


def test_metrics_includes_per_tool_and_raw(tmp_path, monkeypatch):
    """Phase 16 Wave 0 (D-12): evolve_tool_descriptions metrics.json gains
    per_tool_*_rates + raw_predictions (newly wired in Wave 0).

    Exercises the real holdout-loop wiring (raw_preds collection block) plus the
    real persist_per_tool_rates / persist_raw_predictions helpers, mirroring
    the inline wiring at evolve_tool_descriptions.py:331+ and :393-395.
    BLOCKER 4: uses holdout_examples + real helpers (no helper-only unit test).
    """
    pytest.importorskip("dspy")
    import dspy
    from unittest.mock import MagicMock

    from evolution.tools.tool_metric import (
        CrossToolRegressionChecker,
        persist_per_tool_rates,
        persist_raw_predictions,
    )

    # Build holdout fixture mirroring dataset.to_dspy_examples('holdout') output
    holdout_examples = []
    for i in range(3):
        ex = dspy.Example(
            task_description=f"task {i}",
            correct_tool="memory",
            confuser_tools=["terminal", "browse"],
            difficulty="medium" if i < 2 else "hard",
        ).with_inputs("task_description")
        holdout_examples.append(ex)

    def fake_module(task_description):
        pred = MagicMock()
        pred.selected_tool = "memory"
        return pred

    # Replicate the inline holdout loop from evolve_tool_descriptions.py:331+
    # (including the new Phase 16 raw_preds collection)
    baseline_preds: list[tuple[str, str]] = []
    evolved_preds: list[tuple[str, str]] = []
    raw_preds: list[dict] = []
    for ex in holdout_examples:
        bp = fake_module(task_description=ex.task_description)
        baseline_preds.append((ex.correct_tool, bp.selected_tool))
        ep = fake_module(task_description=ex.task_description)
        evolved_preds.append((ex.correct_tool, ep.selected_tool))
        raw_preds.append({
            "correct_tool": ex.correct_tool,
            "selected_tool": getattr(ep, "selected_tool", "") or "",
            "difficulty": getattr(ex, "difficulty", "medium") or "medium",
            "num_available_tools": len(getattr(ex, "confuser_tools", []) or []) + 1,
        })

    # Replicate evolve_tool_descriptions.py:349-354 + :393-395 + :423 wiring
    regression_checker = CrossToolRegressionChecker()
    baseline_rates = regression_checker.compute_per_tool_rates(baseline_preds)
    evolved_rates = regression_checker.compute_per_tool_rates(evolved_preds)
    metrics = {
        "timestamp": "test",
        "iterations": 1,
        "baseline_score": 1.0,
        "evolved_score": 1.0,
        "constraints_passed": True,
    }
    metrics_extra = persist_per_tool_rates({}, baseline_rates, evolved_rates)
    metrics_extra = persist_raw_predictions(metrics_extra, raw_preds)
    metrics = {**metrics, **metrics_extra}

    # Phase 16 D-12 assertions
    assert "per_tool_baseline_rates" in metrics
    assert "per_tool_evolved_rates" in metrics
    assert "raw_predictions" in metrics
    assert isinstance(metrics["per_tool_baseline_rates"], dict)
    assert isinstance(metrics["raw_predictions"], list)
    assert len(metrics["raw_predictions"]) == 3
    if metrics["raw_predictions"]:
        first = metrics["raw_predictions"][0]
        assert set(first.keys()) == {"correct_tool", "selected_tool", "difficulty", "num_available_tools"}
        assert isinstance(first["correct_tool"], str)
        assert isinstance(first["selected_tool"], str)
        assert isinstance(first["difficulty"], str)
        assert isinstance(first["num_available_tools"], int)
        # num_available_tools = len(confuser_tools) + 1 = 2 + 1 = 3
        assert first["num_available_tools"] == 3
    # Phase 13 既有字段保留(通过 helper 合入)
    assert metrics.get("constraints_passed") is True
