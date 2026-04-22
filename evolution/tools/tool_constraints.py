"""Factual accuracy validation for evolved tool descriptions.

Compares original and evolved tool descriptions using an LLM judge to
detect false capability claims introduced during evolution. Works alongside
ConstraintValidator._check_size() (reused from core) for size-based gating.
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


class ToolFactualChecker:
    """Checks evolved tool descriptions for factual accuracy.

    Uses an LLM to compare original and evolved descriptions, detecting
    any false capability claims introduced during evolution. A conservative
    approach: if the LLM is uncertain, we reject (passed=False).

    Args:
        config: EvolutionConfig providing eval_model for LLM calls.
    """

    class FactualCheckSignature(dspy.Signature):
        """Compare original and evolved tool descriptions to detect false claims.

        Determine whether the evolved description claims capabilities that
        are NOT present in the original description. Rewording, clarifying,
        or making descriptions more concise is acceptable. Adding entirely
        new capabilities that the tool does not have is a false claim.
        """
        tool_name: str = dspy.InputField(
            desc="Name of the tool being checked",
        )
        original_description: str = dspy.InputField(
            desc="The original tool description before evolution",
        )
        evolved_description: str = dspy.InputField(
            desc="The evolved tool description to check for false claims",
        )
        has_false_claims: bool = dspy.OutputField(
            desc="True if evolved description claims capabilities NOT in original",
        )
        explanation: str = dspy.OutputField(
            desc="Explanation of what false claims were found, or why none were found",
        )

    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.checker = dspy.ChainOfThought(self.FactualCheckSignature)

    def check(
        self,
        tool_name: str,
        original_description: str,
        evolved_description: str,
    ) -> ConstraintResult:
        """Check a single tool description for factual accuracy.

        Args:
            tool_name: Name of the tool being checked.
            original_description: The original description before evolution.
            evolved_description: The evolved description to validate.

        Returns:
            ConstraintResult with passed=True if no false claims detected.
        """
        lm = dspy.LM(self.config.eval_model, **self.config.get_lm_kwargs())

        with dspy.context(lm=lm):
            result = self.checker(
                tool_name=tool_name,
                original_description=original_description,
                evolved_description=evolved_description,
            )

        has_false = _parse_bool(result.has_false_claims)
        explanation = str(result.explanation)

        if has_false:
            return ConstraintResult(
                passed=False,
                constraint_name="factual_accuracy",
                message=f"False claims detected in '{tool_name}'",
                details=explanation,
            )
        else:
            return ConstraintResult(
                passed=True,
                constraint_name="factual_accuracy",
                message=f"No false claims in '{tool_name}'",
                details=explanation,
            )

    def check_all(
        self,
        original_tools: list,
        evolved_tools: list,
    ) -> list[ConstraintResult]:
        """Check all evolved tool descriptions against their originals.

        Only checks tools that exist in both original and evolved lists
        (matched by name). New tools in evolved_tools that have no
        original counterpart are skipped.

        Args:
            original_tools: List of original ToolDescription objects.
            evolved_tools: List of evolved ToolDescription objects.

        Returns:
            List of ConstraintResult, one per matched tool.
        """
        original_map = {t.name: t for t in original_tools}
        results = []

        for evolved in evolved_tools:
            original = original_map.get(evolved.name)
            if original is None:
                continue
            result = self.check(
                evolved.name,
                original.description,
                evolved.description,
            )
            results.append(result)

        return results
