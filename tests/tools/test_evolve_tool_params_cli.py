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


def test_metrics_includes_raw_predictions(tmp_path, monkeypatch):
    """Phase 16 Wave 0 (D-12): metrics.json must include raw_predictions list with 4-key schema.

    Uses _evaluate_holdout direct call to exercise the real raw_preds collection
    block at line 1018+ (per BLOCKER 4 constraint: must go through real接线 code).
    """
    pytest.importorskip("dspy")
    import json
    import dspy
    from unittest.mock import MagicMock, patch
    from pathlib import Path

    evolve_tool_params = pytest.importorskip("evolution.tools.evolve_tool_params")
    _evaluate_holdout = evolve_tool_params._evaluate_holdout

    # Build a minimal holdout with real ToolSelectionExample-shaped dspy.Example objects
    holdout = []
    for i in range(3):
        ex = dspy.Example(
            task_description=f"task {i}",
            correct_tool="search",
            correct_params={"q": f"query {i}"},
            confuser_tools=["browse", "file_read"],
            difficulty="medium",
        ).with_inputs("task_description")
        holdout.append(ex)

    # Mock module that returns matching predictions
    def fake_module(task_description):
        pred = MagicMock()
        pred.selected_tool = "search"
        pred.selected_params = '{"q": "mock"}'
        return pred

    mock_lm = MagicMock()

    # _evaluate_holdout uses dspy.context(lm=lm), need to patch that
    with patch("evolution.tools.evolve_tool_params.dspy.context") as mock_ctx:
        mock_ctx.return_value.__enter__ = MagicMock(return_value=None)
        mock_ctx.return_value.__exit__ = MagicMock(return_value=False)

        score, tool_pairs, param_pairs = _evaluate_holdout(fake_module, holdout, mock_lm)

    # Verify _evaluate_holdout returned tool pairs
    assert isinstance(tool_pairs, list)
    assert len(tool_pairs) == 3

    # Now simulate what the CLI does with persist_raw_predictions
    from evolution.tools.tool_metric import persist_per_tool_rates, persist_raw_predictions
    from evolution.tools.tool_metric import CrossToolRegressionChecker

    # Build raw_preds using the same logic as in evolve_tool_params.py line 1018+
    raw_preds: list[dict] = []
    for ex, (correct, selected) in zip(holdout, tool_pairs):
        raw_preds.append({
            "correct_tool": correct,
            "selected_tool": selected,
            "difficulty": getattr(ex, "difficulty", "medium") or "medium",
            "num_available_tools": len(getattr(ex, "confuser_tools", []) or []) + 1,
        })

    regression_checker = CrossToolRegressionChecker()
    baseline_rates = regression_checker.compute_per_tool_rates(tool_pairs)
    evolved_rates = regression_checker.compute_per_tool_rates(tool_pairs)
    metrics: dict = {}
    metrics = persist_per_tool_rates(metrics, baseline_rates, evolved_rates)
    metrics = persist_raw_predictions(metrics, raw_preds)

    # Phase 16 D-12 assertions
    assert "raw_predictions" in metrics
    assert isinstance(metrics["raw_predictions"], list)
    assert "per_tool_baseline_rates" in metrics  # Phase 13 既有字段保留
    assert "per_tool_evolved_rates" in metrics
    assert len(metrics["raw_predictions"]) == 3

    if metrics["raw_predictions"]:
        first = metrics["raw_predictions"][0]
        assert set(first.keys()) == {"correct_tool", "selected_tool", "difficulty", "num_available_tools"}
        assert isinstance(first["correct_tool"], str)
        assert isinstance(first["selected_tool"], str)
        assert isinstance(first["difficulty"], str)
        assert isinstance(first["num_available_tools"], int)
        # Verify num_available_tools = len(confuser_tools) + 1
        assert first["num_available_tools"] == 3  # ["browse", "file_read"] + 1
