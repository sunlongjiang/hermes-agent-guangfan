"""Personality drift detection across 4 dimensions.

Compares original vs evolved prompt sections using a pairwise LLM judge.
3-run averaging at the final constraint gate (NOT inside GEPA). Threshold
per-dim from F1-optimized calibration. Severity ladder: 0 dims exceeded
= pass, 1 = warn, 2+ = reject (D-GATE-01).

NOTE: temperature=0.7 + cache=False are CRITICAL constructor kwargs.
Without them DSPy's cache=True default makes 3 identical calls return
the same response and stdev=0 collapses the conservative decision rule
(RA2 / Pitfall A — see .planning/phases/18-personality-drift-detection/18-RESEARCH.md).
"""

import json
import statistics

import dspy
from pydantic import ValidationError

from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintResult


DRIFT_DIMENSIONS: tuple[str, ...] = ("tone", "formality", "vocabulary", "persona")


def _clamp_unit(x: float) -> float:
    """Clamp a float into the closed [0.0, 1.0] interval."""
    return max(0.0, min(1.0, x))


class DriftScoreSignature(dspy.Signature):
    """Pairwise comparison of original vs evolved prompt section.

    Score each dimension independently on 0.0 to 1.0:
        0.0 = no drift (identical character / style)
        1.0 = total drift (completely different voice / role)

    Dimensions:
    - tone: emotional register (formal / neutral / warm / playful / aggressive)
    - formality: sentence structure and word-choice formality
    - vocabulary: lexical choices (technical / colloquial / jargon)
    - persona: speaker identity / role consistency (e.g. "helpful AI"
      vs "expert peer")

    Output each <dim>_score as a single decimal between 0.0 and 1.0,
    nothing else on the score lines. Output explanation as a single
    paragraph citing concrete textual evidence for the highest-scoring
    dimension.
    """
    section_id: str = dspy.InputField(
        desc="Section identifier (e.g. memory_guidance)",
    )
    original_text: str = dspy.InputField(
        desc="Original section text before evolution",
    )
    evolved_text: str = dspy.InputField(
        desc="Evolved section text to compare",
    )
    tone_score: float = dspy.OutputField(
        desc="Tone drift 0.0 (same emotional register) - 1.0 (totally different)",
    )
    formality_score: float = dspy.OutputField(
        desc="Formality drift 0.0 (same structure/formality) - 1.0 (totally different)",
    )
    vocabulary_score: float = dspy.OutputField(
        desc="Vocabulary drift 0.0 (same lexical choices) - 1.0 (totally different)",
    )
    persona_score: float = dspy.OutputField(
        desc="Persona drift 0.0 (same speaker identity) - 1.0 (totally different)",
    )
    explanation: str = dspy.OutputField(
        desc="One-paragraph rationale citing concrete textual evidence",
    )


class DriftDetector:
    """Detects personality drift between original and evolved prompt sections.

    Sibling of PromptRoleChecker (Phase 10) — same shape, different judgement.
    Uses DSPy ChainOfThought with typed float OutputFields for reliable parsing
    (RA1 / M4 prevention via dspy.OutputField + pydantic ValidationError handling).

    Args:
        config: EvolutionConfig providing eval_model.
        thresholds: Per-dim drift thresholds. Must contain keys matching
            DRIFT_DIMENSIONS exactly. Loaded from drift_thresholds.json,
            typically derived via DriftCalibrationBuilder + derive_thresholds.

    Raises:
        ValueError: If thresholds dict is missing any of DRIFT_DIMENSIONS.
    """

    # Exposed as class attribute so tests / callers can introspect the
    # Signature via DriftDetector.DriftScoreSignature.
    DriftScoreSignature = DriftScoreSignature

    def __init__(
        self,
        config: EvolutionConfig,
        thresholds: dict,
    ):
        missing = set(DRIFT_DIMENSIONS) - set(thresholds.keys())
        if missing:
            raise ValueError(
                f"thresholds missing dimensions: {sorted(missing)}"
            )
        self.config = config
        self.thresholds = thresholds
        # RA2 / Pitfall A: temperature=0.7 + cache=False are MANDATORY.
        # Without temperature>0, DSPy's cache=True default makes 3 identical
        # calls return the same cached response -> stdev=0 -> D-ROB-02
        # `mean - 1*stdev > threshold` decision collapses to `mean > threshold`.
        # cache=False is belt-and-suspenders (RESEARCH §Open Q1) — cache
        # key includes temperature in DSPy 3.1.3 but disabling cache costs
        # nothing for gate-time 60-call workload and prevents cross-instance
        # contamination.
        self._lm = dspy.LM(
            config.eval_model,
            temperature=0.7,
            cache=False,
            **config.get_lm_kwargs(),
        )
        self.judge = dspy.ChainOfThought(DriftScoreSignature)

    def _check_one_run(
        self,
        section_id: str,
        original_text: str,
        evolved_text: str,
    ) -> tuple[dict, str]:
        """Run the LLM judge once. Returns (scores_per_dim, explanation).

        RA1 / M4 prevention: on parse failure (LLM emits non-float text),
        fallback each score to 0.0 (NOT 0.5). 0.0 is observable in
        metrics; 0.5 is invisible.
        """
        try:
            with dspy.context(lm=self._lm):
                result = self.judge(
                    section_id=section_id,
                    original_text=original_text,
                    evolved_text=evolved_text,
                )
            scores = {
                "tone": _clamp_unit(float(result.tone_score)),
                "formality": _clamp_unit(float(result.formality_score)),
                "vocabulary": _clamp_unit(float(result.vocabulary_score)),
                "persona": _clamp_unit(float(result.persona_score)),
            }
            return scores, str(result.explanation)
        except (ValidationError, ValueError, TypeError) as e:
            return (
                {dim: 0.0 for dim in DRIFT_DIMENSIONS},
                f"[Parse failure: {type(e).__name__}: {e}]",
            )

    def check(
        self,
        section_id: str,
        original_text: str,
        evolved_text: str,
    ) -> dict:
        """Check a single section pair with 3-run averaging (D-ROB-01).

        Returns:
            dict with keys:
              - section_id: str
              - per_dim: dict[str, dict] mapping each DRIFT_DIMENSIONS element to
                  {"mean": float, "stdev": float, "exceeded": bool, "raw": [float]*3}
              - exceeded_count: int (number of dims with exceeded=True)
              - severity: "pass" | "warn" | "reject"
              - explanation: str (third-run LLM explanation, per D-OUT-03)
              - constraint_result: ConstraintResult — passed/name/message/details
                  with details = json.dumps(per_dim, sort_keys=True)
        """
        runs = []
        last_explanation = ""
        for _ in range(3):
            scores, explanation = self._check_one_run(
                section_id, original_text, evolved_text,
            )
            runs.append(scores)
            last_explanation = explanation  # D-OUT-03: only 3rd persisted

        per_dim = {}
        for dim in DRIFT_DIMENSIONS:
            raw = [r[dim] for r in runs]
            mean = statistics.mean(raw)
            sd = statistics.stdev(raw)  # always 3 points -> defined
            # D-ROB-02: conservative — prefers false negative
            exceeded = (mean - sd) > self.thresholds[dim]
            per_dim[dim] = {
                "mean": round(mean, 4),
                "stdev": round(sd, 4),
                "exceeded": exceeded,
                "raw": [round(r, 4) for r in raw],
            }

        exceeded_count = sum(1 for d in per_dim.values() if d["exceeded"])
        if exceeded_count == 0:
            severity = "pass"
            passed = True
            message = f"Drift OK in '{section_id}': no dims exceeded"
        elif exceeded_count == 1:
            severity = "warn"
            passed = True  # D-GATE-01: 1 dim warn STILL DEPLOYS
            exceeded_dim = next(
                dim for dim, d in per_dim.items() if d["exceeded"]
            )
            message = (
                f"Drift WARN in '{section_id}': dim '{exceeded_dim}' "
                f"exceeded — review before deploying"
            )
        else:
            severity = "reject"
            passed = False  # D-GATE-01: 2+ dims HARD REJECT
            message = (
                f"Drift REJECT in '{section_id}': "
                f"{exceeded_count} dims exceeded"
            )

        return {
            "section_id": section_id,
            "per_dim": per_dim,
            "exceeded_count": exceeded_count,
            "severity": severity,
            "explanation": last_explanation,
            "constraint_result": ConstraintResult(
                passed=passed,
                constraint_name="drift_detection",
                message=message,
                details=json.dumps(per_dim, sort_keys=True),
            ),
        }

    def check_all(
        self,
        original_sections: list,
        evolved_sections: list,
    ) -> list:
        """Check all evolved sections. Returns list of per-section drift dicts.

        Mirrors PromptRoleChecker.check_all signature for pipeline drop-in.
        Sections present in evolved but missing from original are skipped.
        """
        original_map = {s.section_id: s for s in original_sections}
        results = []
        for evolved in evolved_sections:
            original = original_map.get(evolved.section_id)
            if original is None:
                continue
            results.append(
                self.check(
                    evolved.section_id, original.text, evolved.text,
                )
            )
        return results
