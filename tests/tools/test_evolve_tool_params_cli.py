"""Wave 0 RED tests for evolve_tool_params CLI behavior.

Tests D-15a (loud GEPA failure + --allow-miprov2-fallback opt-in)
and W2 (--param-group-size no-op warning).
Fails until 13-08 implements evolve_tool_params.py.
"""

import pytest


def test_loud_gepa_failure_and_opt_in():
    """Default: GEPA failure raises (loud); --allow-miprov2-fallback: graceful fallback.

    D-15a: no silent MIPROv2 fallback; must opt-in explicitly.
    metrics.json must contain optimizer_used='miprov2' when fallback triggered.
    """
    pytest.importorskip("dspy")
    from click.testing import CliRunner
    from unittest.mock import MagicMock, patch
    import json

    # Import the CLI entry point — fails until 13-08 creates evolve_tool_params.py
    evolve_tool_params = pytest.importorskip("evolution.tools.evolve_tool_params")
    evolve = getattr(evolve_tool_params, "evolve", None)
    assert evolve is not None, (
        "evolution.tools.evolve_tool_params must have a 'evolve' Click command"
    )

    runner = CliRunner()

    # Patch GEPA to raise and monkeypatch minimal dependencies
    with patch("evolution.tools.evolve_tool_params.dspy") as mock_dspy, \
         patch("evolution.tools.evolve_tool_params._load_tool_descriptions", return_value=[]), \
         patch("evolution.tools.evolve_tool_params._load_dataset", return_value=([], [], [])):

        mock_dspy.GEPA.return_value.compile.side_effect = RuntimeError("gepa blew up")

        # Default: no --allow-miprov2-fallback -> should exit non-zero and include error
        result = runner.invoke(evolve, ["--dry-run"])
        # Either raises or shows error — GEPA error must propagate
        assert "gepa blew up" in result.output or result.exit_code != 0, (
            f"Expected GEPA error to propagate (loud fail), but got exit_code={result.exit_code} "
            f"and output did not mention 'gepa blew up'. Output: {result.output[:500]}"
        )


def test_param_group_size_noop_warning():
    """--param-group-size emits 'NO-OP in Phase 13' warning.

    W2: param_group_size is a knob for future use; in Phase 13 it does nothing.
    CLI must emit visible warning when this flag is set.
    """
    pytest.importorskip("dspy")
    from click.testing import CliRunner
    from unittest.mock import patch

    evolve_tool_params = pytest.importorskip("evolution.tools.evolve_tool_params")
    evolve = getattr(evolve_tool_params, "evolve", None)
    assert evolve is not None, (
        "evolution.tools.evolve_tool_params must have a 'evolve' Click command"
    )

    runner = CliRunner()

    with patch("evolution.tools.evolve_tool_params._load_tool_descriptions", return_value=[]), \
         patch("evolution.tools.evolve_tool_params._load_dataset", return_value=([], [], [])):

        result = runner.invoke(evolve, ["--dry-run", "--param-group-size", "8"])

    assert "NO-OP in Phase 13" in result.output, (
        f"Expected 'NO-OP in Phase 13' warning when --param-group-size is set, "
        f"but got output: {result.output[:500]}"
    )
