"""Wave 0 RED tests for ParamConsistencyChecker.

Tests D-11: per-tool batch LLM consistency check for evolved param descriptions.
Fails until 13-04 implements ParamConsistencyChecker in evolution/tools/tool_constraints.py.
"""

import pytest
from unittest.mock import MagicMock, patch


def test_detects_conflicts(mock_lm_with_usage):
    """ParamConsistencyChecker rejects intentionally conflicting param descriptions.

    D-11: is_consistent=False when evolved params contradict frozen tool description.
    Conservative _parse_bool: ambiguous -> False -> reject.
    """
    pytest.importorskip("dspy")
    import dspy
    from evolution.core.config import EvolutionConfig
    from evolution.tools.tool_constraints import ParamConsistencyChecker  # fails until 13-04
    from evolution.core.constraints import ConstraintResult

    config = EvolutionConfig()
    checker = ParamConsistencyChecker(config)

    # Simulate LLM returning is_consistent=False with explanation
    mock_pred = dspy.Prediction(
        is_consistent=False,
        explanation="conflict: param says 'absolute path only' but tool says 'relative paths supported'",
    )
    with patch.object(checker, "checker") as mock_checker:
        mock_checker.return_value = mock_pred
        result = checker.check(
            tool_name="search_files",
            frozen_desc="Search files; supports both absolute and relative paths",
            param_descs={"path": "ABSOLUTE paths only — relative paths not supported"},
        )

    assert isinstance(result, ConstraintResult), (
        f"Expected ConstraintResult, got {type(result)}"
    )
    assert result.passed is False, (
        f"Expected passed=False for conflicting params, got passed={result.passed}"
    )
    assert "conflict" in result.details.lower(), (
        f"Expected 'conflict' in details, got: {result.details!r}"
    )


def test_malformed_json_fallback(mock_lm_with_usage):
    """_parse_bool conservative: ambiguous LLM output -> passed=False (reject).

    D-11: parse failure is_consistent -> False -> ConstraintResult(passed=False).
    This mirrors the _parse_bool conservative strategy (only "true"/"yes"/"1" = True).
    """
    pytest.importorskip("dspy")
    import dspy
    from evolution.core.config import EvolutionConfig
    from evolution.tools.tool_constraints import ParamConsistencyChecker  # fails until 13-04
    from evolution.core.constraints import ConstraintResult

    config = EvolutionConfig()
    checker = ParamConsistencyChecker(config)

    # Simulate LLM returning ambiguous is_consistent value
    mock_pred = dspy.Prediction(
        is_consistent="maybe ok?",  # not recognized by _parse_bool -> False
        explanation="unclear",
    )
    with patch.object(checker, "checker") as mock_checker:
        mock_checker.return_value = mock_pred
        result = checker.check(
            tool_name="my_tool",
            frozen_desc="Tool description",
            param_descs={"p": "param description"},
        )

    assert isinstance(result, ConstraintResult), (
        f"Expected ConstraintResult, got {type(result)}"
    )
    assert result.passed is False, (
        f"Expected passed=False for ambiguous LLM output (conservative _parse_bool), "
        f"got passed={result.passed}"
    )


def test_whole_tool_rejection(mock_lm_with_usage):
    """check_all returns at least one passed=False when one tool is inconsistent.

    D-11: one inconsistent tool in a batch causes that tool's result to fail.
    """
    pytest.importorskip("dspy")
    import dspy
    from evolution.core.config import EvolutionConfig
    from evolution.tools.tool_constraints import ParamConsistencyChecker  # fails until 13-04
    from evolution.core.constraints import ConstraintResult
    from evolution.tools.tool_loader import ToolDescription, ToolParam
    from pathlib import Path

    config = EvolutionConfig()
    checker = ParamConsistencyChecker(config)

    # Two tools: first consistent, second not
    consistent_pred = dspy.Prediction(is_consistent=True, explanation="All good.")
    inconsistent_pred = dspy.Prediction(is_consistent=False, explanation="Contradiction found.")

    call_count = [0]
    def side_effect(**kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            return consistent_pred
        return inconsistent_pred

    evolved_tools = [
        ToolDescription(
            name="tool_ok",
            file_path=Path("/fake/tool_ok.py"),
            description="A good tool",
            params=[ToolParam(name="p", type="string", required=True, description="consistent param")],
        ),
        ToolDescription(
            name="tool_bad",
            file_path=Path("/fake/tool_bad.py"),
            description="A problematic tool",
            params=[ToolParam(name="q", type="string", required=True, description="conflicting param")],
        ),
    ]
    frozen_descs = {
        "tool_ok": "A good tool",
        "tool_bad": "A problematic tool",
    }

    with patch.object(checker, "checker") as mock_checker:
        mock_checker.side_effect = side_effect
        results = checker.check_all(evolved_tools, frozen_descs)

    assert isinstance(results, list), f"Expected list, got {type(results)}"
    assert len(results) >= 1, "Expected at least one result"
    failed = [r for r in results if not r.passed]
    assert len(failed) >= 1, (
        f"Expected at least 1 failed result from check_all, got 0. "
        f"All results: {[(r.constraint_name, r.passed) for r in results]}"
    )
