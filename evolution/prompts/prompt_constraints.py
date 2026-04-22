"""Role preservation validation for evolved prompt sections.

Compares original and evolved prompt sections using an LLM judge to
detect functional role changes introduced during evolution. Works alongside
ConstraintValidator._check_growth() (reused from core) for growth-based gating.
"""

import dspy
from typing import Optional

from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintResult


def _parse_bool(value) -> bool:
    """Parse a boolean value from various LLM output formats.

    Conservative strategy: only explicit truthy values return True.
    Everything else (including unrecognized text) returns False.

    Args:
        value: A bool, string, or other value to parse.

    Returns:
        True only for bool True or strings "true", "yes", "1".
    """
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("true", "yes", "1")


class PromptRoleChecker:
    """Checks evolved prompt sections for role preservation.

    Uses an LLM to compare original and evolved sections, detecting
    any functional role changes introduced during evolution. A section's
    role is its fundamental purpose (e.g., memory guidance remains about
    memory, not identity).

    Args:
        config: EvolutionConfig providing eval_model for LLM calls.
    """

    class RoleCheckSignature(dspy.Signature):
        """Compare original and evolved prompt sections to verify role preservation.

        Determine whether the evolved section still fulfills the same functional
        role as the original. Rewording, improving clarity, or restructuring is
        acceptable. Changing the fundamental purpose (e.g., memory guidance
        becoming identity guidance) is a role violation.
        """
        section_id: str = dspy.InputField(
            desc="Section identifier (e.g. memory_guidance)",
        )
        original_text: str = dspy.InputField(
            desc="Original section text before evolution",
        )
        evolved_text: str = dspy.InputField(
            desc="Evolved section text to check",
        )
        role_preserved: bool = dspy.OutputField(
            desc="True if evolved text maintains the same functional role as original",
        )
        explanation: str = dspy.OutputField(
            desc="Explanation of role assessment",
        )

    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.checker = dspy.ChainOfThought(self.RoleCheckSignature)

    def check(
        self,
        section_id: str,
        original_text: str,
        evolved_text: str,
    ) -> ConstraintResult:
        """Check a single prompt section for role preservation.

        Args:
            section_id: Identifier for the section being checked.
            original_text: The original section text before evolution.
            evolved_text: The evolved section text to validate.

        Returns:
            ConstraintResult with passed=True if role is preserved.
        """
        lm = dspy.LM(self.config.eval_model, **self.config.get_lm_kwargs())

        with dspy.context(lm=lm):
            result = self.checker(
                section_id=section_id,
                original_text=original_text,
                evolved_text=evolved_text,
            )

        role_kept = _parse_bool(result.role_preserved)
        explanation = str(result.explanation)

        if role_kept:
            return ConstraintResult(
                passed=True,
                constraint_name="role_preservation",
                message=f"Role preserved in '{section_id}'",
                details=explanation,
            )
        else:
            return ConstraintResult(
                passed=False,
                constraint_name="role_preservation",
                message=f"Role changed in '{section_id}'",
                details=explanation,
            )

    def check_all(
        self,
        original_sections: list,
        evolved_sections: list,
    ) -> list[ConstraintResult]:
        """Check all evolved prompt sections against their originals.

        Only checks sections that exist in both original and evolved lists
        (matched by section_id). Evolved sections with no original
        counterpart are skipped.

        Args:
            original_sections: List of original PromptSection objects.
            evolved_sections: List of evolved PromptSection objects.

        Returns:
            List of ConstraintResult, one per matched section.
        """
        original_map = {s.section_id: s for s in original_sections}
        results = []

        for evolved in evolved_sections:
            original = original_map.get(evolved.section_id)
            if original is None:
                continue
            result = self.check(
                evolved.section_id,
                original.text,
                evolved.text,
            )
            results.append(result)

        return results
