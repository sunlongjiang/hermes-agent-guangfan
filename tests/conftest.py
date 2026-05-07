"""Shared pytest fixtures for all test suites."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_lm_with_usage():
    """Returns a callable that mimics a dspy.LM whose Prediction carries usage.

    Usage:
        def test_foo(mock_lm_with_usage):
            lm = mock_lm_with_usage(
                response_text='{"selected_tool":"x","selected_params":"{}"}',
                prompt_tokens=100,
                completion_tokens=20,
                model_name="openai/gpt-4.1-mini",
            )
            # Pass `lm` wherever dspy.configure(lm=...) is expected.
    """
    def factory(*, response_text: str = "", prompt_tokens: int = 100,
                completion_tokens: int = 20, model_name: str = "openai/gpt-4.1-mini"):
        lm = MagicMock(name=f"mock_lm[{model_name}]")
        lm.model = model_name
        # Callable signature mirrors dspy.LM.__call__(prompt: str, **kwargs) -> list[str]
        lm.return_value = [response_text]
        # Attach a usage record that downstream cost_tracker tests can read via
        # dspy.utils.usage_tracker.UsageTracker when dspy.configure(track_usage=True).
        lm._usage_records = [{
            "model": model_name,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }]
        return lm
    return factory
