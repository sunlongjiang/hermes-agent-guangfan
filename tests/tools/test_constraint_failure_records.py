"""Regression tests for BL-02 (constraint-failure records preserve tool identity).

Pre-fix: evolve_tool_params._evolve_impl produced constraint_failures records
where:
  - factual_accuracy failures had `tool` set to ConstraintResult.constraint_name
    (which is always 'factual_accuracy', never the tool name);
  - param_consistency failures had `tool` set to None.

Both broke per-tool triage from metrics.json. These tests pin the post-fix
contract: `tool` is the evolved tool's `.name` string.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_tool(name: str, params: list[tuple[str, str]] | None = None):
    """Build a minimal ToolDescription. params is list of (param_name, desc)."""
    from evolution.tools.tool_loader import ToolDescription, ToolParam

    return ToolDescription(
        name=name,
        file_path=Path(f"/fake/{name}.py"),
        description=f"{name} description (frozen)",
        params=[
            ToolParam(name=pn, type="string", required=True, description=pd)
            for (pn, pd) in (params or [])
        ],
    )


def test_factual_failure_records_carry_evolved_tool_name():
    """BL-02: factual_accuracy failure dicts must use evolved.name as `tool`.

    Pre-fix the code wrote `getattr(r, "constraint_name", "factual_accuracy")`
    which produced `tool: "factual_accuracy"` (constraint type) for every
    failure, losing per-tool identity.
    """
    pytest.importorskip("dspy")
    import dspy
    from click.testing import CliRunner

    from evolution.tools.evolve_tool_params import evolve

    fake_tool_a = _make_tool("read_file", params=[("path", "Path to file")])
    fake_tool_b = _make_tool("write_file", params=[("path", "Where to write")])

    fake_train = [
        dspy.Example(
            task_description="t",
            correct_tool="read_file",
            correct_params={"path": "/tmp/x"},
        ).with_inputs("task_description")
    ]

    # Build a stub OptimizedModule that returns the same evolved tools (no
    # actual evolution); GEPA.compile is mocked to return it directly.
    class _StubModule:
        def __init__(self, tools):
            self._tools = tools

        def get_evolved_descriptions(self):
            return self._tools

        def named_predictors(self):
            return []

        def __call__(self, *_a, **_kw):
            return dspy.Prediction(selected_tool="read_file", selected_params="{}")

    runner = CliRunner()

    # Make ToolFactualChecker.check_all return ALL failures so the record
    # path is exercised. Simulate matched filter: both tools match.
    from evolution.core.constraints import ConstraintResult

    def fake_check_all_factual(self, original, evolved):
        out = []
        for ev in evolved:
            out.append(
                ConstraintResult(
                    passed=False,
                    constraint_name="factual_accuracy",
                    message=f"False claims detected in '{ev.name}'",
                    details="explanation",
                )
            )
        return out

    def fake_check_all_consistency(self, *, evolved_tools, frozen_tool_descs):
        # All consistency results pass — we only want to verify factual records here.
        return [
            ConstraintResult(
                passed=True,
                constraint_name="param_consistency",
                message=f"OK for '{ev.name}'",
                details="ok",
            )
            for ev in evolved_tools
        ]

    with runner.isolated_filesystem():
        with patch(
            "evolution.tools.evolve_tool_params._load_tool_descriptions",
            return_value=[fake_tool_a, fake_tool_b],
        ), patch(
            "evolution.tools.evolve_tool_params._load_dataset",
            return_value=(fake_train, fake_train, fake_train),
        ), patch(
            "evolution.tools.evolve_tool_params.dspy.GEPA"
        ) as mock_gepa, patch(
            "evolution.tools.evolve_tool_params.dspy.LM"
        ), patch(
            "evolution.tools.tool_constraints.ToolFactualChecker.check_all",
            new=fake_check_all_factual,
        ), patch(
            "evolution.tools.tool_constraints.ParamConsistencyChecker.check_all",
            new=fake_check_all_consistency,
        ):
            mock_gepa.return_value.compile.return_value = _StubModule(
                [fake_tool_a, fake_tool_b]
            )
            result = runner.invoke(evolve, [], catch_exceptions=False)

        # Expect CLI exit 1 (CONSTRAINTS_FAILED) and a FAILED_*/metrics.json.
        assert result.exit_code == 1, (
            f"Expected exit 1 from CONSTRAINTS_FAILED gate, got "
            f"{result.exit_code}. Output: {result.output[:500]}"
        )
        # Locate the FAILED_<ts>/ directory the CLI just wrote.
        failed_dirs = list(Path("output/tools").glob("FAILED_*"))
        assert failed_dirs, (
            f"Expected at least one output/tools/FAILED_* dir; "
            f"contents: {list(Path('output/tools').iterdir())}"
        )
        # Pick the most recent (sort by name, which is timestamped).
        failed_dir = sorted(failed_dirs)[-1]
        metrics = json.loads((failed_dir / "metrics.json").read_text())
        details = metrics.get("constraint_failure_details", [])
        factual_records = [
            d for d in details if d.get("constraint") == "factual_accuracy"
        ]
        assert len(factual_records) == 2, (
            f"expected 2 factual_accuracy failure records, got "
            f"{len(factual_records)}: {factual_records}"
        )
        tool_field_values = {d["tool"] for d in factual_records}
        # Pre-fix: tool_field_values would be {'factual_accuracy'}.
        # Post-fix: tool_field_values should be {'read_file', 'write_file'}.
        assert tool_field_values == {"read_file", "write_file"}, (
            f"BL-02 regression: factual_accuracy failure records must use "
            f"the evolved tool's .name as the `tool` field. Got "
            f"{tool_field_values!r} (pre-fix value was 'factual_accuracy')."
        )


def test_consistency_failure_records_carry_evolved_tool_name():
    """BL-02: param_consistency failure dicts must use evolved.name as `tool`.

    Pre-fix the code wrote `tool: None` for every consistency failure even
    though the tool name was available in the per-tool batch.
    """
    pytest.importorskip("dspy")
    import dspy
    from click.testing import CliRunner

    from evolution.tools.evolve_tool_params import evolve
    from evolution.core.constraints import ConstraintResult

    fake_tool_a = _make_tool("alpha", params=[("p", "param a")])
    fake_tool_b = _make_tool("beta", params=[("p", "param b")])

    fake_train = [
        dspy.Example(
            task_description="t",
            correct_tool="alpha",
            correct_params={"p": "x"},
        ).with_inputs("task_description")
    ]

    class _StubModule:
        def __init__(self, tools):
            self._tools = tools

        def get_evolved_descriptions(self):
            return self._tools

        def named_predictors(self):
            return []

        def __call__(self, *_a, **_kw):
            return dspy.Prediction(selected_tool="alpha", selected_params="{}")

    runner = CliRunner()

    def fake_check_all_factual(self, original, evolved):
        return [
            ConstraintResult(
                passed=True,
                constraint_name="factual_accuracy",
                message=f"No false claims in '{ev.name}'",
                details="ok",
            )
            for ev in evolved
        ]

    def fake_check_all_consistency(self, *, evolved_tools, frozen_tool_descs):
        return [
            ConstraintResult(
                passed=False,
                constraint_name="param_consistency",
                message=f"Param description inconsistency detected in '{ev.name}'",
                details="contradiction",
            )
            for ev in evolved_tools
        ]

    with runner.isolated_filesystem():
        with patch(
            "evolution.tools.evolve_tool_params._load_tool_descriptions",
            return_value=[fake_tool_a, fake_tool_b],
        ), patch(
            "evolution.tools.evolve_tool_params._load_dataset",
            return_value=(fake_train, fake_train, fake_train),
        ), patch(
            "evolution.tools.evolve_tool_params.dspy.GEPA"
        ) as mock_gepa, patch(
            "evolution.tools.evolve_tool_params.dspy.LM"
        ), patch(
            "evolution.tools.tool_constraints.ToolFactualChecker.check_all",
            new=fake_check_all_factual,
        ), patch(
            "evolution.tools.tool_constraints.ParamConsistencyChecker.check_all",
            new=fake_check_all_consistency,
        ):
            mock_gepa.return_value.compile.return_value = _StubModule(
                [fake_tool_a, fake_tool_b]
            )
            result = runner.invoke(evolve, [], catch_exceptions=False)

        assert result.exit_code == 1, (
            f"Expected exit 1 from CONSTRAINTS_FAILED gate, got "
            f"{result.exit_code}. Output: {result.output[:500]}"
        )
        failed_dirs = list(Path("output/tools").glob("FAILED_*"))
        assert failed_dirs
        failed_dir = sorted(failed_dirs)[-1]
        metrics = json.loads((failed_dir / "metrics.json").read_text())
        details = metrics.get("constraint_failure_details", [])
        consistency_records = [
            d for d in details if d.get("constraint") == "param_consistency"
        ]
        assert len(consistency_records) == 2
        tool_field_values = {d["tool"] for d in consistency_records}
        # Pre-fix: tool_field_values would be {None}.
        # Post-fix: {'alpha', 'beta'}.
        assert tool_field_values == {"alpha", "beta"}, (
            f"BL-02 regression: param_consistency failure records must use "
            f"the evolved tool's .name as the `tool` field. Got "
            f"{tool_field_values!r} (pre-fix value was None)."
        )
