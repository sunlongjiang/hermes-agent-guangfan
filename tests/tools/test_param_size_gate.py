"""B3 SC3 coverage — 200-char per-param size gate.

Exercises ConstraintValidator._check_size(text, 'param_description')
directly; the branch already exists in evolution/core/constraints.py
lines 101-102 (via config.max_param_desc_size = 200). 13-08 wires the
reuse call into the evolve_tool_params constraint chain.

These tests are expected to PASS at Wave 0 (GREEN) — they exercise an
already-present branch. If either fails, it signals a defect in the
pre-existing _check_size branch that must be fixed before proceeding.
"""


def test_param_desc_201_chars_rejected():
    """_check_size rejects param description of 201 chars (over 200-char limit).

    SC3: param_description size gate. Message must reference the 200-char limit.
    """
    from evolution.core.config import EvolutionConfig
    from evolution.core.constraints import ConstraintValidator

    cv = ConstraintValidator(config=EvolutionConfig())
    result = cv._check_size("a" * 201, "param_description")
    assert result.passed is False, result.message
    assert "200" in result.message, (
        f"message must reference 200-char limit: {result.message}"
    )


def test_param_desc_200_chars_accepted():
    """_check_size accepts param description of exactly 200 chars.

    SC3: boundary condition — exactly at limit must pass.
    """
    from evolution.core.config import EvolutionConfig
    from evolution.core.constraints import ConstraintValidator

    cv = ConstraintValidator(config=EvolutionConfig())
    result = cv._check_size("a" * 200, "param_description")
    assert result.passed is True, result.message
