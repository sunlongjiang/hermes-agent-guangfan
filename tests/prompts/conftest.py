"""Shared pytest fixtures for tests/prompts/.

Phase 18 adds drift-detection-specific fixtures (mock_drift_lm, dummy_thresholds).
Other prompt tests use module-local helpers (e.g. _make_checker) and are unaffected.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import dspy
import pytest


@pytest.fixture
def dummy_thresholds() -> dict[str, float]:
    """Placeholder drift thresholds matching CONTEXT D-CAL-01 example values.

    Use in DriftDetector unit tests that don't exercise threshold-derivation logic.
    Real production thresholds come from datasets/prompts/drift_thresholds.json.
    """
    return {
        "tone": 0.55,
        "formality": 0.50,
        "vocabulary": 0.45,
        "persona": 0.65,
    }


@pytest.fixture
def mock_drift_lm():
    """Patch dspy.LM in evolution.prompts.drift_detector to a controllable mock.

    Returns an object with set_scores(**kwargs) and set_explanation(str).
    Each invocation of the patched LM-backed ChainOfThought yields a
    dspy.Prediction whose tone_score / formality_score / vocabulary_score /
    persona_score / explanation reflect the most recent set_*() call.

    Usage:
        def test_severity_warn(mock_drift_lm):
            mock_drift_lm.set_scores(tone=0.8, formality=0.2,
                                     vocabulary=0.2, persona=0.2)
            # ... construct DriftDetector and call check()
    """
    class _MockDriftLM:
        def __init__(self):
            self._scores = {
                "tone": 0.0, "formality": 0.0,
                "vocabulary": 0.0, "persona": 0.0,
            }
            self._explanation = "mock"

        def set_scores(self, **kwargs):
            self._scores.update(kwargs)

        def set_explanation(self, text: str):
            self._explanation = text

        def __call__(self, *args, **kwargs):
            # DSPy LM call returns the prediction dict-shape; the
            # ChainOfThought wrapper is patched separately when needed.
            return dspy.Prediction(
                tone_score=self._scores["tone"],
                formality_score=self._scores["formality"],
                vocabulary_score=self._scores["vocabulary"],
                persona_score=self._scores["persona"],
                explanation=self._explanation,
            )

    mock = _MockDriftLM()
    # Patch BOTH paths because drift_detector imports dspy and constructs
    # dspy.LM(...) in __init__ — must intercept at the module-attribute level.
    with patch("evolution.prompts.drift_detector.dspy.LM", return_value=mock):
        yield mock


@pytest.fixture
def drift_calibration_mini_path() -> Path:
    """Path to the 6-example mini fixture for offline derive_thresholds tests."""
    return Path(__file__).parent / "fixtures" / "drift_calibration_mini.jsonl"
