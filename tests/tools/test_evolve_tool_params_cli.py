"""Wave 0 RED tests for evolve_tool_params CLI behavior.

Tests D-15a (loud GEPA failure + --allow-miprov2-fallback opt-in)
and W2 (--param-group-size no-op warning).
Fails until 13-08 implements evolve_tool_params.py.
"""

from pathlib import Path

import pytest


def test_loud_gepa_failure_and_opt_in():
    """Default: GEPA failure raises (loud); --allow-miprov2-fallback: graceful fallback.

    D-15a: no silent MIPROv2 fallback; must opt-in explicitly.

    BL-03 fix: previously this test patched _load_tool_descriptions to []
    which short-circuited at evolve_tool_params.py:614-628 with `return 1`
    BEFORE dspy.GEPA was ever instantiated, so the
    `mock_gepa.compile.side_effect = RuntimeError(...)` never fired and
    the loud-fail-vs-opt-in branching was never exercised. The assertion
    `exit_code != 0` trivially passed via the empty-tools path.

    The post-fix test provides at least one non-empty ToolDescription and a
    non-empty dataset, then verifies that GEPA failure actually raises
    (default) or routes through MIPROv2 (opt-in).
    """
    pytest.importorskip("dspy")
    import dspy
    from click.testing import CliRunner
    from unittest.mock import patch

    # Import the CLI entry point — fails until 13-08 creates evolve_tool_params.py
    evolve_tool_params = pytest.importorskip("evolution.tools.evolve_tool_params")
    evolve = getattr(evolve_tool_params, "evolve", None)
    assert evolve is not None, (
        "evolution.tools.evolve_tool_params must have a 'evolve' Click command"
    )

    from evolution.tools.tool_loader import ToolDescription, ToolParam

    fake_tool = ToolDescription(
        name="x",
        file_path=Path("/fake/x.py"),
        description="x description",
        params=[
            ToolParam(
                name="p",
                type="string",
                required=True,
                description="param description",
            )
        ],
    )
    fake_ds = [
        dspy.Example(
            task_description="t",
            correct_tool="x",
            correct_params={"p": "v"},
        ).with_inputs("task_description")
    ]

    runner = CliRunner()

    # ─── Default path: GEPA failure must raise (D-15a loud) ──────────────
    with patch(
        "evolution.tools.evolve_tool_params._load_tool_descriptions",
        return_value=[fake_tool],
    ), patch(
        "evolution.tools.evolve_tool_params._load_dataset",
        return_value=(fake_ds, fake_ds, fake_ds),
    ), patch(
        "evolution.tools.evolve_tool_params.dspy.GEPA"
    ) as mock_gepa, patch(
        "evolution.tools.evolve_tool_params.dspy.LM"
    ):
        mock_gepa.return_value.compile.side_effect = RuntimeError("gepa blew up")
        # catch_exceptions=True so the runner stores the exception object;
        # we need to inspect it to prove the side_effect actually fired.
        result = runner.invoke(evolve, [], catch_exceptions=True)

        # CRITICAL: prove dspy.GEPA was actually instantiated AND .compile()
        # was called. Pre-fix the empty-tools short-circuit returned 1
        # before this point.
        assert mock_gepa.called, (
            "dspy.GEPA was never instantiated — the empty-tools short-circuit "
            "(or another early return) prevented the test from reaching the "
            "GEPA branch. BL-03 regression: this test does NOT cover D-15a."
        )
        assert mock_gepa.return_value.compile.called, (
            "dspy.GEPA().compile() was never called — side_effect did not fire."
        )

        assert result.exit_code != 0, (
            f"Expected non-zero exit (loud GEPA raise), got {result.exit_code}. "
            f"Output: {result.output[:500]}"
        )
        # The exception that propagated must be the RuntimeError from
        # the mocked compile, NOT something incidental.
        assert isinstance(result.exception, RuntimeError), (
            f"Expected RuntimeError to propagate from GEPA, got "
            f"{type(result.exception).__name__}: {result.exception!r}"
        )
        assert "gepa blew up" in str(result.exception), (
            f"Expected 'gepa blew up' in propagated exception, got "
            f"{result.exception!r}"
        )

    # ─── Opt-in path: --allow-miprov2-fallback routes to MIPROv2 ────────
    with patch(
        "evolution.tools.evolve_tool_params._load_tool_descriptions",
        return_value=[fake_tool],
    ), patch(
        "evolution.tools.evolve_tool_params._load_dataset",
        return_value=(fake_ds, fake_ds, fake_ds),
    ), patch(
        "evolution.tools.evolve_tool_params.dspy.GEPA"
    ) as mock_gepa2, patch(
        "evolution.tools.evolve_tool_params.dspy.MIPROv2"
    ) as mock_mipro, patch(
        "evolution.tools.evolve_tool_params.dspy.LM"
    ):
        mock_gepa2.return_value.compile.side_effect = RuntimeError("gepa blew up")
        # MIPROv2 also fails — we just need to verify the fallback CODEPATH
        # was reached (MIPROv2 instantiated). Reaching MIPROv2 proves the
        # GEPA loud-raise was suppressed by --allow-miprov2-fallback.
        mock_mipro.return_value.compile.side_effect = RuntimeError(
            "mipro also blew up"
        )

        result2 = runner.invoke(
            evolve, ["--allow-miprov2-fallback"], catch_exceptions=True
        )

        assert mock_gepa2.called and mock_gepa2.return_value.compile.called, (
            "GEPA should still be called first under --allow-miprov2-fallback."
        )
        assert mock_mipro.called, (
            "Expected MIPROv2 to be instantiated under --allow-miprov2-fallback "
            "after GEPA raised. Got mock_mipro.called=False — the fallback "
            "codepath was not reached."
        )
        # The fallback's own raise propagates with mipro message — confirms
        # we DID land in the except-Exception block of the fallback (not
        # the bare GEPA raise).
        assert result2.exit_code != 0
        assert isinstance(result2.exception, RuntimeError)
        assert "mipro also blew up" in str(result2.exception), (
            f"Expected MIPROv2's own RuntimeError to propagate, got "
            f"{result2.exception!r}"
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
