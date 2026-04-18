"""Tests for PromptBehavioralMetric callable class.

Validates:
- Callable interface (example, prediction, trace=None) -> float
- Empty output returns 0.0
- Heuristic path when trace is not None (no LLMJudge call)
- Full LLMJudge path when trace is None
- Feedback propagation to prediction (PMPT-07)
- Score range [0.0, 1.0]
"""

from unittest.mock import MagicMock, patch

import dspy

from evolution.core.config import EvolutionConfig
from evolution.core.fitness import FitnessScore
from evolution.prompts.prompt_metric import PromptBehavioralMetric


# ── Helpers ─────────────────────────────────────────────────────────────────


def _make_config() -> EvolutionConfig:
    """Create a minimal EvolutionConfig for tests."""
    return EvolutionConfig()


def _make_example(**kwargs) -> dspy.Example:
    """Build a dspy.Example with common defaults."""
    defaults = {
        "task_input": "How do I save a memory?",
        "expected_behavior": "Agent should use memory save tool with a concise summary",
        "section_text": "When the user asks to remember something, use the memory_save tool.",
    }
    defaults.update(kwargs)
    return dspy.Example(**defaults).with_inputs("task_input")


def _make_prediction(**kwargs) -> dspy.Prediction:
    """Build a dspy.Prediction with common defaults."""
    defaults = {
        "output": "I'll save that to memory using the memory_save tool with a summary.",
    }
    defaults.update(kwargs)
    return dspy.Prediction(**defaults)


# ── TestPromptBehavioralMetricInit ──────────────────────────────────────────


class TestPromptBehavioralMetricInit:
    """Construction and callable interface."""

    def test_construct_with_config(self):
        """Can construct with EvolutionConfig."""
        config = _make_config()
        metric = PromptBehavioralMetric(config)
        assert metric is not None

    def test_is_callable(self):
        """Has __call__ method."""
        config = _make_config()
        metric = PromptBehavioralMetric(config)
        assert callable(metric)

    def test_call_signature(self):
        """__call__ accepts (example, prediction, trace=None) and returns float."""
        config = _make_config()
        metric = PromptBehavioralMetric(config)
        example = _make_example()
        prediction = _make_prediction()
        # Should not raise; returns a float
        result = metric(example, prediction, trace=None)
        assert isinstance(result, float)


# ── TestPromptBehavioralMetricEmpty ─────────────────────────────────────────


class TestPromptBehavioralMetricEmpty:
    """Returns 0.0 for empty or None output."""

    def test_empty_string_output(self):
        """Returns 0.0 when agent output is empty string."""
        config = _make_config()
        metric = PromptBehavioralMetric(config)
        example = _make_example()
        prediction = _make_prediction(output="")
        assert metric(example, prediction) == 0.0

    def test_none_output(self):
        """Returns 0.0 when agent output is None."""
        config = _make_config()
        metric = PromptBehavioralMetric(config)
        example = _make_example()
        prediction = _make_prediction(output=None)
        assert metric(example, prediction) == 0.0

    def test_whitespace_only_output(self):
        """Returns 0.0 when agent output is whitespace only."""
        config = _make_config()
        metric = PromptBehavioralMetric(config)
        example = _make_example()
        prediction = _make_prediction(output="   \n  ")
        assert metric(example, prediction) == 0.0


# ── TestPromptBehavioralMetricHeuristic ─────────────────────────────────────


class TestPromptBehavioralMetricHeuristic:
    """When trace is not None, uses fast heuristic without LLMJudge."""

    @patch("evolution.prompts.prompt_metric.LLMJudge")
    def test_heuristic_does_not_call_judge(self, mock_judge_cls):
        """When trace is not None, LLMJudge.score() is never called."""
        config = _make_config()
        metric = PromptBehavioralMetric(config)
        example = _make_example()
        prediction = _make_prediction()
        metric(example, prediction, trace="some_trace")
        # LLMJudge.score should not have been called
        if mock_judge_cls.return_value.score.called:
            raise AssertionError("LLMJudge.score() was called during heuristic path")

    @patch("evolution.prompts.prompt_metric.LLMJudge")
    def test_heuristic_returns_float(self, mock_judge_cls):
        """Heuristic path returns a float in [0.0, 1.0]."""
        config = _make_config()
        metric = PromptBehavioralMetric(config)
        example = _make_example()
        prediction = _make_prediction()
        result = metric(example, prediction, trace="opt_trace")
        assert isinstance(result, float)
        assert 0.0 <= result <= 1.0

    @patch("evolution.prompts.prompt_metric.LLMJudge")
    def test_heuristic_uses_keyword_overlap(self, mock_judge_cls):
        """Heuristic score increases with keyword overlap."""
        config = _make_config()
        metric = PromptBehavioralMetric(config)

        # High overlap
        example_high = _make_example(
            expected_behavior="memory save tool concise summary",
        )
        pred_high = _make_prediction(
            output="I will use memory save tool to create a concise summary",
        )
        score_high = metric(example_high, pred_high, trace="t")

        # Low overlap
        example_low = _make_example(
            expected_behavior="memory save tool concise summary",
        )
        pred_low = _make_prediction(
            output="Hello world, completely unrelated text here",
        )
        score_low = metric(example_low, pred_low, trace="t")

        assert score_high > score_low


# ── TestPromptBehavioralMetricFull ──────────────────────────────────────────


class TestPromptBehavioralMetricFull:
    """When trace is None, calls LLMJudge.score() with correct args."""

    @patch("evolution.prompts.prompt_metric.LLMJudge")
    def test_full_calls_judge(self, mock_judge_cls):
        """When trace is None, calls LLMJudge.score()."""
        mock_judge = mock_judge_cls.return_value
        mock_judge.score.return_value = FitnessScore(
            correctness=0.8,
            procedure_following=0.7,
            conciseness=0.9,
            feedback="Good behavior",
        )
        config = _make_config()
        metric = PromptBehavioralMetric(config)
        example = _make_example()
        prediction = _make_prediction()
        metric(example, prediction, trace=None)
        assert mock_judge.score.called

    @patch("evolution.prompts.prompt_metric.LLMJudge")
    def test_full_passes_skill_text_as_section_text(self, mock_judge_cls):
        """LLMJudge.score() receives skill_text= with the section_text value."""
        mock_judge = mock_judge_cls.return_value
        mock_judge.score.return_value = FitnessScore(
            correctness=0.8,
            procedure_following=0.7,
            conciseness=0.9,
            feedback="Good behavior",
        )
        config = _make_config()
        metric = PromptBehavioralMetric(config)
        section_text = "When the user asks to remember something, save it."
        example = _make_example(section_text=section_text)
        prediction = _make_prediction()
        metric(example, prediction, trace=None)
        _, kwargs = mock_judge.score.call_args
        assert kwargs.get("skill_text") == section_text

    @patch("evolution.prompts.prompt_metric.LLMJudge")
    def test_full_returns_composite(self, mock_judge_cls):
        """Returns FitnessScore.composite value."""
        mock_judge = mock_judge_cls.return_value
        score = FitnessScore(
            correctness=0.8,
            procedure_following=0.7,
            conciseness=0.9,
            feedback="Good behavior",
        )
        mock_judge.score.return_value = score
        config = _make_config()
        metric = PromptBehavioralMetric(config)
        example = _make_example()
        prediction = _make_prediction()
        result = metric(example, prediction, trace=None)
        assert result == score.composite


# ── TestPromptBehavioralMetricFeedback ──────────────────────────────────────


class TestPromptBehavioralMetricFeedback:
    """Feedback propagation to prediction per PMPT-07."""

    @patch("evolution.prompts.prompt_metric.LLMJudge")
    def test_feedback_attached_to_prediction(self, mock_judge_cls):
        """After full scoring, prediction.feedback is set."""
        mock_judge = mock_judge_cls.return_value
        mock_judge.score.return_value = FitnessScore(
            correctness=0.8,
            procedure_following=0.7,
            conciseness=0.9,
            feedback="Good behavior observed",
        )
        config = _make_config()
        metric = PromptBehavioralMetric(config)
        example = _make_example()
        prediction = _make_prediction()
        metric(example, prediction, trace=None)
        assert hasattr(prediction, "feedback")
        assert prediction.feedback == "Good behavior observed"

    @patch("evolution.prompts.prompt_metric.LLMJudge")
    def test_feedback_is_nonempty_string(self, mock_judge_cls):
        """FitnessScore.feedback is non-empty after full scoring."""
        mock_judge = mock_judge_cls.return_value
        mock_judge.score.return_value = FitnessScore(
            correctness=0.5,
            procedure_following=0.5,
            conciseness=0.5,
            feedback="Needs improvement in conciseness",
        )
        config = _make_config()
        metric = PromptBehavioralMetric(config)
        example = _make_example()
        prediction = _make_prediction()
        metric(example, prediction, trace=None)
        assert isinstance(prediction.feedback, str)
        assert len(prediction.feedback) > 0
