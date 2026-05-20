"""E2E CLI tests for evolution/code/evolve_code.py.

All tests mock code_evolver_adapter.evolve and score_candidate — no real
openevolve invocation, no real pytest subprocess. Tests verify the orchestration
glue (pre-flight, dry-run, config-passthrough) end-to-end.

Coverage map (Plan 21-07 task 3):
- test_dry_run_exits_0_without_openevolve_call → dry-run early exit (step 5b)
- test_preflight_fails_without_license → preflight step 5 hard-fail
- test_cli_passes_model_to_evolution_config → CLI → EvolutionConfig.load wiring
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from evolution.code.evolve_code import main


def _make_mock_hermes(root: Path) -> Path:
    """Create a minimal hermes-agent mock under root with strip_ansi + test."""
    hermes = root / "hermes-agent"
    (hermes / "tools").mkdir(parents=True)
    (hermes / "tests" / "tools").mkdir(parents=True)
    (hermes / "tools" / "ansi_strip.py").write_text(
        "import re\n\nANSI_RE = re.compile(r'\\x1b\\\\[[0-9;]*m')\n\n"
        "def strip_ansi(text):\n    return ANSI_RE.sub('', text)\n",
        encoding="utf-8",
    )
    (hermes / "tests" / "tools" / "test_ansi_strip.py").write_text(
        "from tools.ansi_strip import strip_ansi\n\n"
        "def test_basic():\n    assert strip_ansi('hi') == 'hi'\n",
        encoding="utf-8",
    )
    (hermes / ".git").mkdir()
    return hermes


def _setup_project_root(root: Path) -> None:
    """Drop LICENSE + .gitignore + .pre-commit-config.yaml into root."""
    (root / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (root / ".gitignore").write_text("output/\n", encoding="utf-8")
    (root / ".pre-commit-config.yaml").write_text(
        "repos:\n  - repo: local\n    hooks:\n"
        "      - id: openevolve-single-import-surface\n"
        "        name: gate\n        entry: true\n        language: system\n",
        encoding="utf-8",
    )


def _stub_target() -> MagicMock:
    """Return a CodeTarget-shaped MagicMock."""
    target = MagicMock()
    target.component_path = Path("tools/ansi_strip.py")
    target.test_file_path = Path("tests/tools/test_ansi_strip.py")
    target.baseline_size_bytes = 1024
    target.original_source = "def strip_ansi(t): return t\n"
    target.hermes_agent_commit = "deadbeef"
    return target


def _stub_fitness(passed: int = 30, total: int = 30) -> MagicMock:
    """Return a CodeFitness-shaped MagicMock that passes the D-15 gate."""
    f = MagicMock()
    f.pytest_passed = passed
    f.pytest_total = total
    f.size_component = 1.0
    f.ruff_score = 1.0
    f.composite = 1.0
    f.pytest_failures = []
    f.to_dict = MagicMock(return_value={"composite": 1.0})
    return f


class TestDryRun:
    def test_dry_run_exits_0_without_openevolve_call(self, tmp_path: Path) -> None:
        """--dry-run returns exit 0 without invoking code_evolver_adapter.evolve."""
        hermes = _make_mock_hermes(tmp_path)
        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=str(tmp_path)) as proj_root:
            proj_root = Path(proj_root)
            _setup_project_root(proj_root)

            # EvolutionConfig.load must return a config whose api_key is non-empty
            mock_config = MagicMock()
            mock_config.api_key = "test-key"
            mock_config.api_base = None
            mock_config.iterations = 20
            mock_config.hermes_agent_path = hermes
            mock_config.max_cost_usd = 5.0

            adapter_evolve_path = "evolution.code.code_evolver_adapter.evolve"
            with patch(
                "evolution.code.evolve_code.EvolutionConfig.load",
                return_value=mock_config,
            ), patch(
                "evolution.code.evolve_code.find_target", return_value=_stub_target()
            ), patch(
                "evolution.code.evolve_code.find_target_tests", return_value=[]
            ), patch(
                "evolution.code.evolve_code.stratify_tests",
                return_value={"train_ids": ["t1"], "holdout_ids": ["t2"]},
            ), patch(
                "evolution.code.evolve_code.score_candidate", return_value=_stub_fitness()
            ), patch(adapter_evolve_path) as mock_adapter:
                result = runner.invoke(
                    main,
                    [
                        "--component",
                        "tools/ansi_strip.py",
                        "--dry-run",
                        "--hermes-repo",
                        str(hermes),
                    ],
                )

            assert result.exit_code == 0, f"unexpected exit {result.exit_code}\n{result.output}"
            assert mock_adapter.call_count == 0, "adapter.evolve must NOT be called in dry-run"
            assert "DRY RUN" in result.output


class TestPreflightLicense:
    def test_preflight_fails_without_license(self, tmp_path: Path) -> None:
        """Pre-flight step 5 hard-fails when LICENSE missing at cwd root."""
        hermes = _make_mock_hermes(tmp_path)
        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=str(tmp_path)) as proj_root:
            proj_root = Path(proj_root)
            # NOTE: deliberately NOT creating LICENSE here
            (proj_root / ".gitignore").write_text("output/\n", encoding="utf-8")
            (proj_root / ".pre-commit-config.yaml").write_text(
                "openevolve-single-import-surface\n", encoding="utf-8"
            )

            mock_config = MagicMock()
            mock_config.api_key = "test-key"
            mock_config.iterations = 20
            mock_config.hermes_agent_path = hermes

            with patch(
                "evolution.code.evolve_code.EvolutionConfig.load",
                return_value=mock_config,
            ):
                result = runner.invoke(
                    main,
                    [
                        "--component",
                        "tools/ansi_strip.py",
                        "--dry-run",
                        "--hermes-repo",
                        str(hermes),
                    ],
                )

            assert result.exit_code != 0, "preflight must fail without LICENSE"
            assert "license" in result.output.lower()


class TestConfigPassthrough:
    def test_cli_passes_model_to_evolution_config(self, tmp_path: Path) -> None:
        """--model is forwarded to EvolutionConfig.load(model=...)."""
        hermes = _make_mock_hermes(tmp_path)
        runner = CliRunner()

        with runner.isolated_filesystem(temp_dir=str(tmp_path)) as proj_root:
            proj_root = Path(proj_root)
            _setup_project_root(proj_root)

            mock_config = MagicMock()
            mock_config.api_key = "test-key"
            mock_config.iterations = 20
            mock_config.hermes_agent_path = hermes

            with patch(
                "evolution.code.evolve_code.EvolutionConfig.load",
                return_value=mock_config,
            ) as mock_load, patch(
                "evolution.code.evolve_code.find_target", return_value=_stub_target()
            ), patch(
                "evolution.code.evolve_code.find_target_tests", return_value=[]
            ), patch(
                "evolution.code.evolve_code.stratify_tests",
                return_value={"train_ids": [], "holdout_ids": []},
            ), patch(
                "evolution.code.evolve_code.score_candidate",
                return_value=_stub_fitness(),
            ):
                result = runner.invoke(
                    main,
                    [
                        "--component",
                        "tools/ansi_strip.py",
                        "--model",
                        "qwen-plus",
                        "--dry-run",
                        "--hermes-repo",
                        str(hermes),
                    ],
                )

            assert result.exit_code == 0, f"unexpected exit {result.exit_code}\n{result.output}"
            assert mock_load.call_count >= 1
            kwargs = mock_load.call_args.kwargs
            assert kwargs.get("model") == "qwen-plus", f"model passthrough broken: {kwargs}"
            assert kwargs.get("hermes_repo") == str(hermes)
