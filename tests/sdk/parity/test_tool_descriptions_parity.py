"""Parity: SDK tool-description gates match legacy tool_descriptions CLI.

Verifies the placeholder-preservation rule + the legacy max_tool_desc_size
constraint produce the same accept/reject decision.
"""

from pathlib import Path

import pytest

from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintValidator
from evolution.sdk.artifact import EvolvableArtifact
from evolution.sdk.optimizer import apply_gates


def test_tool_desc_size_limit_parity(tmp_path):
    """Both legacy and SDK reject tool desc > max_tool_desc_size (500 default)."""
    config = EvolutionConfig(max_tool_desc_size=100)
    legacy = ConstraintValidator(config)
    candidate = "x" * 200

    legacy_results = legacy.validate_all(candidate, "tool_description",
                                         baseline_text="hi")
    legacy_passed = all(r.passed for r in legacy_results)

    sdk_artifact = EvolvableArtifact(
        agent_name="hermes", artifact_id="t", kind="tool",
        baseline_text="hi", text_source="docstring",
        source_file=tmp_path / "x.py", decorator_lineno=1,
        constraints={"max_chars": 100, "max_growth": 0.5},
    )
    sdk_result = apply_gates(
        artifact=sdk_artifact, candidate_text=candidate,
        baseline_score=0.5, candidate_holdout_score=0.6,
    )

    assert legacy_passed is False
    assert sdk_result.passed is False


def test_tool_placeholder_preservation_sdk_strict(tmp_path):
    """SDK adds placeholder-preservation rule (legacy doesn't); verify it triggers."""
    sdk_artifact = EvolvableArtifact(
        agent_name="hermes", artifact_id="t", kind="tool",
        baseline_text="search the web for {query} and return top results",
        text_source="docstring",
        source_file=tmp_path / "x.py", decorator_lineno=1,
        constraints={"max_chars": 500, "max_growth": 0.5},
    )
    candidate_lost = "Search the web and return results"  # lost {query}
    sdk_result = apply_gates(
        artifact=sdk_artifact, candidate_text=candidate_lost,
        baseline_score=0.5, candidate_holdout_score=0.6,
    )
    assert sdk_result.passed is False
    assert "placeholder" in sdk_result.failed_gate.lower()


def test_tool_placeholder_preserved_passes(tmp_path):
    sdk_artifact = EvolvableArtifact(
        agent_name="hermes", artifact_id="t", kind="tool",
        baseline_text="search for {query} in {source}",
        text_source="docstring",
        source_file=tmp_path / "x.py", decorator_lineno=1,
        constraints={"max_chars": 500, "max_growth": 1.0},  # growth ~55%, needs room
    )
    candidate_ok = "Search {source} for {query} (return top 3 hits)"
    sdk_result = apply_gates(
        artifact=sdk_artifact, candidate_text=candidate_ok,
        baseline_score=0.5, candidate_holdout_score=0.6,
    )
    assert sdk_result.passed is True
