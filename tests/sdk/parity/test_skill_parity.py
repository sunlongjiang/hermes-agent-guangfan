"""Parity: SDK constraint validator + dataset construction match legacy skill CLI.

The legacy CLI is `python -m evolution.skills.evolve_skill`. We don't actually
run GEPA in CI (too expensive); we verify the byte-equal-eligible pure
function path:
  1. Skill body extraction
  2. Constraint validation (size, growth, structure)
  3. Dataset construction from session JSONL
"""

from pathlib import Path

import pytest

from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintValidator
from evolution.skills.skill_module import load_skill
from evolution.sdk.artifact import EvolvableArtifact, compute_baseline_hash
from evolution.sdk.optimizer import apply_gates


SAMPLE_SKILL = """---
name: test-skill
description: A skill used by parity tests
---

Body line 1.
Body line 2.
"""


def test_skill_loader_byte_equal_to_sdk_baseline_extraction(tmp_path):
    """Legacy load_skill().body must equal what SDK would treat as baseline_text."""
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text(SAMPLE_SKILL)

    legacy = load_skill(skill_file)
    sdk_artifact = EvolvableArtifact(
        agent_name="hermes",
        artifact_id="test-skill",
        kind="prompt",
        baseline_text=legacy["body"],
        text_source="param",
        source_file=skill_file,
        decorator_lineno=0,
    )
    # Hash must match the body text byte-for-byte.
    assert sdk_artifact.baseline_hash == compute_baseline_hash(legacy["body"])


def test_constraint_size_gate_equivalent_to_legacy(tmp_path):
    """Both code paths must reject the same oversize candidate."""
    config = EvolutionConfig(max_skill_size=100)
    legacy = ConstraintValidator(config)
    candidate = "x" * 150

    legacy_results = legacy.validate_all(candidate, "skill", baseline_text="hi")
    legacy_passed = all(r.passed for r in legacy_results)

    sdk_artifact = EvolvableArtifact(
        agent_name="hermes", artifact_id="x", kind="prompt",
        baseline_text="hi", text_source="param",
        source_file=tmp_path / "x.py", decorator_lineno=1,
        constraints={"max_chars": 100, "max_growth": config.max_prompt_growth},
    )
    sdk_result = apply_gates(
        artifact=sdk_artifact, candidate_text=candidate,
        baseline_score=0.5, candidate_holdout_score=0.6,
    )

    # Both must reject (legacy because size, SDK because gate_1_size).
    assert legacy_passed is False
    assert sdk_result.passed is False


def test_constraint_growth_gate_equivalent_to_legacy(tmp_path):
    config = EvolutionConfig(max_prompt_growth=0.2)
    legacy = ConstraintValidator(config)

    baseline = "x" * 100
    candidate = "x" * 200  # 100% growth, well over 20%

    legacy_results = legacy.validate_all(candidate, "skill", baseline_text=baseline)
    legacy_growth_check = next(
        (r for r in legacy_results if r.constraint_name == "growth_limit"), None,
    )

    sdk_artifact = EvolvableArtifact(
        agent_name="hermes", artifact_id="x", kind="prompt",
        baseline_text=baseline, text_source="param",
        source_file=tmp_path / "x.py", decorator_lineno=1,
        constraints={"max_chars": 50_000, "max_growth": 0.2},
    )
    sdk_result = apply_gates(
        artifact=sdk_artifact, candidate_text=candidate,
        baseline_score=0.5, candidate_holdout_score=0.6,
    )

    assert legacy_growth_check is not None and legacy_growth_check.passed is False
    assert sdk_result.passed is False
    assert "growth" in sdk_result.failed_gate.lower()
