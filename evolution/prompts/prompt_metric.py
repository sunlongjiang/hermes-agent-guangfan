"""Behavioral metric for prompt section optimization.

Provides PromptBehavioralMetric, a callable class that serves as the
DSPy-compatible metric function for prompt section evolution via GEPA.

Symmetric to tool_selection_metric (Phase 4) but continuous rather than
binary: returns float 0.0-1.0 with structured feedback per D3/D4.

Two execution paths:
- trace is not None (optimization loop): fast keyword heuristic, no LLM call
- trace is None (final evaluation): full LLMJudge scoring with feedback

Usage:
    metric = PromptBehavioralMetric(config)
    optimizer = dspy.GEPA(metric=metric, ...)
"""

import dspy

from evolution.core.config import EvolutionConfig
from evolution.core.fitness import LLMJudge


class PromptBehavioralMetric:
    """Callable DSPy metric for prompt section behavioral evaluation.

    Per D3: Uses FitnessScore dimensions (correctness 0.5, procedure_following 0.3, conciseness 0.2).
    Per D4: Returns float 0.0-1.0, compatible with dspy.GEPA(metric=...).

    Usage:
        metric = PromptBehavioralMetric(config)
        optimizer = dspy.GEPA(metric=metric, ...)
    """

    def __init__(self, config: EvolutionConfig):
        """Initialize with config and create LLMJudge instance.

        Args:
            config: EvolutionConfig with model names for LLMJudge.
        """
        self.config = config
        self.judge = LLMJudge(config)

    def __call__(
        self,
        example: dspy.Example,
        prediction: dspy.Prediction,
        trace=None,
        pred_name=None,
        pred_trace=None,
    ) -> float:
        """Score a prompt section's behavioral output.

        Args:
            example: DSPy Example with task_input, expected_behavior, section_text fields.
            prediction: DSPy Prediction with output field.
            trace: If not None, use fast heuristic (optimization loop).
                   If None, use full LLMJudge scoring (final eval).
            pred_name: GEPA predictor name (unused).
            pred_trace: GEPA predictor trace (unused).

        Returns:
            Float 0.0-1.0 score.
        """
        agent_output = getattr(prediction, "output", "") or ""
        expected = getattr(example, "expected_behavior", "") or ""
        task = getattr(example, "task_input", "") or ""
        section_text = getattr(example, "section_text", "") or ""

        # Empty output -> 0.0
        if not agent_output.strip():
            return 0.0

        # ── Fast heuristic path (optimization loop) ──
        if trace is not None:
            return self._quick_heuristic(agent_output, expected)

        # ── Full LLMJudge path (final evaluation) ──
        score = self.judge.score(
            task_input=task,
            expected_behavior=expected,
            agent_output=agent_output,
            skill_text=section_text,
        )

        # Attach feedback to prediction for GEPA consumption (PMPT-07)
        prediction.feedback = score.feedback

        return score.composite

    def _quick_heuristic(self, agent_output: str, expected: str) -> float:
        """Fast keyword overlap heuristic for optimization loop.

        Mirrors skill_fitness_metric pattern: base 0.5, keyword overlap
        bonus up to 1.0. Does NOT call LLMJudge.

        Args:
            agent_output: The agent's response text.
            expected: The expected behavior rubric text.

        Returns:
            Float in [0.0, 1.0].
        """
        expected_lower = expected.lower()
        output_lower = agent_output.lower()

        expected_words = set(expected_lower.split())
        output_words = set(output_lower.split())

        if not expected_words:
            return 0.5

        overlap = len(expected_words & output_words) / len(expected_words)
        score = 0.3 + (0.7 * overlap)

        return min(1.0, max(0.0, score))
