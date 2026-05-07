"""Wave 0 RED tests for joint_tool_param_metric.

Tests D-10 (joint fitness 0.5*tool + 0.5*param) and D-17 (5-param GEPA contract).
Also tests B2 guard: feedback variant returns dspy.Prediction with .score/.feedback attrs.
Fails until 13-03 implements joint_tool_param_metric + joint_tool_param_metric_with_feedback.
"""

import inspect
import pytest


def test_exact_match_cases():
    """joint_tool_param_metric produces correct scores for 4 match matrix cases.

    D-10: score = 0.5 * tool_match + 0.5 * param_match.
    """
    pytest.importorskip("dspy")
    import dspy
    from evolution.tools.tool_metric import joint_tool_param_metric  # fails until 13-03

    params = {"a": "b"}
    params_json = '{"a": "b"}'
    wrong_params_json = '{"a": "wrong"}'

    # (tool_correct, param_correct) -> 1.0
    ex = dspy.Example(correct_tool="tool_x", correct_params=params).with_inputs("task_description")
    pred = dspy.Prediction(selected_tool="tool_x", selected_params=params_json)
    score = joint_tool_param_metric(ex, pred)
    assert score == 1.0, f"Expected 1.0 for tool+param correct, got {score}"

    # (tool_correct, param_wrong) -> 0.5
    pred_wrong_param = dspy.Prediction(selected_tool="tool_x", selected_params=wrong_params_json)
    score = joint_tool_param_metric(ex, pred_wrong_param)
    assert score == 0.5, f"Expected 0.5 for tool correct, param wrong, got {score}"

    # (tool_wrong, param_correct) -> 0.5
    pred_wrong_tool = dspy.Prediction(selected_tool="other_tool", selected_params=params_json)
    score = joint_tool_param_metric(ex, pred_wrong_tool)
    assert score == 0.5, f"Expected 0.5 for tool wrong, param correct, got {score}"

    # (tool_wrong, param_wrong) -> 0.0
    pred_both_wrong = dspy.Prediction(selected_tool="other_tool", selected_params=wrong_params_json)
    score = joint_tool_param_metric(ex, pred_both_wrong)
    assert score == 0.0, f"Expected 0.0 for both wrong, got {score}"


def test_5_param_signature():
    """joint_tool_param_metric must accept 5 positional args (GEPA contract).

    GEPA (gepa.py:368-373) calls inspect.signature(metric).bind(None,None,None,None,None)
    and raises TypeError if it fails. This test mirrors that check.
    """
    pytest.importorskip("dspy")
    from evolution.tools.tool_metric import joint_tool_param_metric  # fails until 13-03

    try:
        inspect.signature(joint_tool_param_metric).bind(None, None, None, None, None)
    except TypeError as e:
        pytest.fail(
            f"joint_tool_param_metric does not accept 5 positional args (GEPA contract): {e}"
        )


def test_json_decode_error_handling():
    """Invalid JSON in selected_params -> param_match=0.0, no exception raised.

    D-17: robust JSON parsing; error does not propagate as exception.
    score = 0.5 * tool_match + 0.5 * 0.0
    """
    pytest.importorskip("dspy")
    import dspy
    from evolution.tools.tool_metric import joint_tool_param_metric  # fails until 13-03

    ex = dspy.Example(correct_tool="tool_x", correct_params={"a": "b"}).with_inputs("task_description")

    # Tool matches, params invalid JSON -> 0.5
    pred_invalid = dspy.Prediction(selected_tool="tool_x", selected_params="not json {{")
    try:
        score = joint_tool_param_metric(ex, pred_invalid)
    except Exception as e:
        pytest.fail(f"joint_tool_param_metric raised exception on invalid JSON: {e}")
    assert score == 0.5, (
        f"Expected 0.5 when tool matches but params invalid JSON, got {score}"
    )

    # Both wrong + invalid JSON -> 0.0
    pred_wrong_tool_invalid = dspy.Prediction(selected_tool="other_tool", selected_params="not json")
    score2 = joint_tool_param_metric(ex, pred_wrong_tool_invalid)
    assert score2 == 0.0, (
        f"Expected 0.0 when tool wrong and params invalid JSON, got {score2}"
    )


def test_feedback_metric_shape():
    """joint_tool_param_metric_with_feedback returns dspy.Prediction with .score/.feedback.

    B2 guard: attribute-access only (no dict-key access). Stub fails unless 13-03
    returns dspy.Prediction (not plain dict or namedtuple).
    """
    pytest.importorskip("dspy")
    import dspy
    from evolution.tools.tool_metric import (  # fails until 13-03
        joint_tool_param_metric,
        joint_tool_param_metric_with_feedback,
    )

    ex = dspy.Example(correct_tool="tool_x", correct_params={"key": "val"}).with_inputs("task_description")
    pred = dspy.Prediction(selected_tool="tool_x", selected_params='{"key": "val"}')

    ret = joint_tool_param_metric_with_feedback(ex, pred)

    # B2: must be dspy.Prediction (not dict)
    assert isinstance(ret, dspy.Prediction), (
        f"expected dspy.Prediction got {type(ret)}"
    )
    # B2: attribute access, not dict access
    assert isinstance(ret.score, float), f"score must be float got {type(ret.score)}"
    assert isinstance(ret.feedback, str), f"feedback must be str got {type(ret.feedback)}"
    assert 0.0 <= ret.score <= 1.0, f"score out of range: {ret.score}"
    assert len(ret.feedback) > 0, "feedback must be non-empty"

    # Score must match bare metric
    bare = joint_tool_param_metric(ex, pred)
    assert ret.score == bare, (
        f"feedback variant score {ret.score} != bare {bare}"
    )
