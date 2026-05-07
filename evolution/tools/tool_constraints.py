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


# ── ParamConsistencyChecker (Phase 13: D-11) ─────────────────────────────────


class ParamConsistencyChecker:
    """Per-tool batch LLM check for param-description coherence.

    For each tool, this checker receives:
      - the frozen top-level description (unchanged by GEPA), and
      - the full dict of evolved param descriptions.

    It asks the LLM whether the set is mutually consistent. Polarity is
    INVERTED compared to ToolFactualChecker so that _parse_bool's
    conservative "unknown -> False" default means ambiguity fails CLOSED
    (i.e., suspicious candidates get rejected). See RESEARCH Pitfall 5
    for polarity rationale.

    Detected conflict classes (spelled out in the Signature instructions so
    the LLM knows what to look for):
      1. Contradictory constraints between top-level and a param (e.g.
         frozen desc says "supports relative paths" while `path` param
         says "absolute path only").
      2. Abbreviation / terminology drift across params within the same
         tool (e.g. "URL" in one param, "link" in another, "target URL"
         in a third -- all referring to the same concept).
      3. Required-field semantic mismatch (a description implying a param
         is required when schema lists it optional, or vice versa).

    Args:
        config: EvolutionConfig providing eval_model + LM kwargs.
    """

    class ConsistencySignature(dspy.Signature):
        """Verify a tool's frozen top-level description and all evolved
        parameter descriptions are mutually consistent.

        Inconsistency includes:
        1. Contradictory constraints between top-level and any param.
        2. Abbreviation / terminology drift across params.
        3. Required-field semantic mismatches.

        Respond strictly with a boolean is_consistent and a brief explanation.
        """
        tool_name: str = dspy.InputField(
            desc="Name of the tool whose descriptions are being checked",
        )
        frozen_tool_description: str = dspy.InputField(
            desc="The tool-level description (frozen -- not subject to evolution)",
        )
        evolved_param_descriptions: str = dspy.InputField(
            desc=(
                "JSON object mapping param_name to its (possibly evolved) "
                "description text, e.g. '{\"path\": \"...\", \"recursive\": \"...\"}'"
            ),
        )
        is_consistent: bool = dspy.OutputField(
            desc=(
                "True ONLY if all param descriptions are coherent with each "
                "other and with the frozen tool description. False on ANY "
                "contradiction, terminology drift, or required-field mismatch. "
                "When uncertain, prefer False."
            ),
        )
        explanation: str = dspy.OutputField(
            desc=(
                "If False: name the conflicting params and the nature of the "
                "conflict (one short sentence). If True: a one-line confirmation."
            ),
        )

    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.checker = dspy.ChainOfThought(self.ConsistencySignature)

    def check(
        self,
        tool_name: str,
        frozen_desc: str,
        param_descs: dict,
    ) -> ConstraintResult:
        """Run one batch consistency check against a single tool.

        Args:
            tool_name: Name of the tool being checked.
            frozen_desc: The unchanged tool-level description text.
            param_descs: Dict of param_name -> evolved description.

        Returns:
            ConstraintResult with passed=True when LLM says consistent AND
            _parse_bool agrees; False on any inconsistency OR parse ambiguity.
        """
        import json as _json  # local to avoid touching module imports if absent

        lm = dspy.LM(self.config.eval_model, **self.config.get_lm_kwargs())
        # Deterministic JSON: sort_keys for stable cross-run comparison in logs;
        # ensure_ascii=False so non-ASCII param text (e.g. CJK examples) renders.
        params_json = _json.dumps(
            param_descs or {}, ensure_ascii=False, sort_keys=True,
        )

        try:
            with dspy.context(lm=lm):
                result = self.checker(
                    tool_name=tool_name,
                    frozen_tool_description=frozen_desc or "",
                    evolved_param_descriptions=params_json,
                )
        except Exception as e:
            # Conservative: any LM / parsing failure rejects the candidate.
            return ConstraintResult(
                passed=False,
                constraint_name="param_consistency",
                message=f"Consistency check failed for '{tool_name}' (LLM error)",
                details=str(e),
            )

        # Polarity inversion: is_consistent True -> passed True.
        # _parse_bool returns False on anything ambiguous -> fails CLOSED.
        is_consistent = _parse_bool(getattr(result, "is_consistent", None))
        explanation = str(getattr(result, "explanation", "") or "")

        if is_consistent:
            return ConstraintResult(
                passed=True,
                constraint_name="param_consistency",
                message=f"Param descriptions consistent for '{tool_name}'",
                details=explanation,
            )
        return ConstraintResult(
            passed=False,
            constraint_name="param_consistency",
            message=f"Param description inconsistency detected in '{tool_name}'",
            details=explanation or "LLM flagged inconsistency (no explanation provided)",
        )

    def check_all(
        self,
        evolved_tools: list,
        frozen_tool_descs: dict,
    ) -> list[ConstraintResult]:
        """Run check() once per evolved tool.

        Args:
            evolved_tools: List of ToolDescription with possibly-evolved
                .params[*].description.
            frozen_tool_descs: Map tool_name -> frozen top-level description
                (from ToolModule._frozen_tool_desc).

        Returns:
            List of ConstraintResult, one per tool. Caller (13-08 CLI)
            rejects the whole run if any .passed == False.
        """
        results: list[ConstraintResult] = []
        for tool in evolved_tools:
            param_descs = {
                p.name: (p.description or "") for p in tool.params
            }
            frozen = frozen_tool_descs.get(tool.name, "")
            results.append(self.check(tool.name, frozen, param_descs))
        return results
