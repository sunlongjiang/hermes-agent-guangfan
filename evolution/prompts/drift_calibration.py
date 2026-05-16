"""Synthetic drift calibration set builder + F1-optimized threshold derivation.

Phase 18 Task 1 (D-CAL-05): MUST run before DriftDetector is deployed.
Generates 30 paired examples (5 sections x 6 variants: 4 drift + 2 no-drift)
using config.judge_model — a different model than DriftDetector's judge
(config.eval_model) to reduce same-model bias (RA5).

Each section produces 4 drift variants (one per DriftDetector dim:
tone, formality, vocabulary, persona) + 2 no-drift variants so every
DriftDetector dimension has positive ground-truth labels for F1 derivation.

Pure stdlib F1 derivation (no sklearn / numpy / scipy — RA3).
"""

import json
import random
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import dspy

from evolution.core.config import EvolutionConfig
from evolution.prompts.drift_detector import DRIFT_DIMENSIONS, DriftDetector


@dataclass
class DriftCalibrationExample:
    """A single calibration pair with ground-truth drift label.

    Args:
        section_id: PromptSection identifier this variant rewrites.
        original_text: Original section text (anchor for the pair).
        evolved_text: LLM-generated rewrite (drift or preserve mode).
        is_drift: True if generator was instructed to drift; False otherwise.
        drift_dim: For is_drift=True, the targeted dimension
            (one of DRIFT_DIMENSIONS). For is_drift=False, "none".
        generation_metadata: Provenance metadata: seed, generator_model,
            target_dim, generation_timestamp, mode. Free-form dict — readers
            should access via .get(...) since older fixtures may omit fields.
    """
    section_id: str
    original_text: str
    evolved_text: str
    is_drift: bool
    drift_dim: str  # one of DRIFT_DIMENSIONS or "none"
    generation_metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DriftCalibrationExample":
        return cls(
            section_id=data["section_id"],
            original_text=data["original_text"],
            evolved_text=data["evolved_text"],
            is_drift=bool(data["is_drift"]),
            drift_dim=data["drift_dim"],
            generation_metadata=data.get("generation_metadata", {}),
        )


@dataclass
class DriftCalibrationDataset:
    """Calibration set (no train/val/holdout splits — single 30-example list).

    Persists as a single JSONL file (D-CAL-02). Differs from
    PromptBehavioralDataset.save which takes a directory and writes
    train/val/holdout splits — calibration is a stable evaluation asset
    used wholesale by derive_thresholds().
    """
    examples: list = field(default_factory=list)

    def save(self, path: Path) -> None:
        """Persist examples as JSONL at the given file path.

        Note: path is the JSONL FILE (not a directory).
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for ex in self.examples:
                f.write(json.dumps(ex.to_dict(), sort_keys=True) + "\n")

    @classmethod
    def load(cls, path: Path) -> "DriftCalibrationDataset":
        path = Path(path)
        examples = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    examples.append(
                        DriftCalibrationExample.from_dict(json.loads(line))
                    )
        return cls(examples=examples)


class DriftCalibrationBuilder:
    """Generates 30 calibration examples (5 sections x 6 variants).

    Per section:
      - 4 drift variants — one targeted per DriftDetector dim
        (tone, formality, vocabulary, persona)
      - 2 no-drift variants — rephrase preserving voice

    Per D-CAL-03 + RA5: uses config.judge_model with temperature=0.9 to
    diversify generated variants. DriftDetector judge uses config.eval_model
    — model differentiation reduces same-model bias.

    History note: the original layout was (3 drift + 3 no-drift) with
    persona omitted from drift coverage, which left persona F1 structurally
    0.0 (no positive examples for the derivation step). Phase 18-03 (paused)
    discovered this; the 4 drift + 2 no-drift balance restores full dim
    coverage while preserving the 30-example total (D-CAL-03).
    """

    class GenerateDriftVariant(dspy.Signature):
        """Generate a rewrite of a prompt section in either drift or preserve mode.

        For mode='drift': SIGNIFICANTLY change the named target_dim
        (tone, formality, vocabulary, or persona) while keeping ALL OTHER
        dimensions identical to the original. The rewrite should remain
        functionally similar but the targeted dim should be unmistakably
        different (e.g. tone change: serious -> playful, persona change:
        collaborative helper -> mechanical processor).

        For mode='preserve': rephrase or restructure for clarity, but
        COMPLETELY preserve tone, formality, vocabulary, and persona.
        The reader should not notice any character shift.
        """
        original_text: str = dspy.InputField(
            desc="Original prompt section text"
        )
        mode: str = dspy.InputField(
            desc="Either 'drift' or 'preserve'"
        )
        target_dim: str = dspy.InputField(
            desc="(drift mode) one of: tone, formality, vocabulary, persona; "
                 "(preserve mode) 'none'"
        )
        evolved_text: str = dspy.OutputField(
            desc="Rewritten section meeting the mode + target_dim requirements"
        )

    # Drift dims sampled across 4 variants per section (D-CAL-03).
    # ALL DriftDetector dims are covered so F1 derivation has positive
    # ground-truth labels for each dim (persona inclusive). Per RA5
    # Mitigation 5: each true-drift variant has EXACTLY ONE targeted dim so
    # per-dim ground-truth labels are clean.
    DRIFT_TARGET_DIMS_PER_SECTION = ("tone", "formality", "vocabulary", "persona")

    def __init__(self, config: EvolutionConfig, seed: int = 42):
        self.config = config
        self.seed = seed
        # RA5 Mitigation 1+3: judge_model (gpt-4.1) + temperature=0.9 for diversity
        self._lm = dspy.LM(
            config.judge_model,
            temperature=0.9,
            **config.get_lm_kwargs(),
        )
        self.generator = dspy.ChainOfThought(self.GenerateDriftVariant)

    def generate(self, sections: list) -> DriftCalibrationDataset:
        """Generate 30 examples (5 sections x 6 variants).

        D-CAL-01..04: 5 sections × (4 drift + 2 preserve) = 30 examples.
        Each example carries generation_metadata with seed, generator_model,
        target_dim, generation_timestamp, mode for reproducibility (D-CAL-02).
        """
        random.seed(self.seed)
        timestamp = datetime.now(timezone.utc).isoformat()
        generator_model = self.config.judge_model
        examples: list = []

        with dspy.context(lm=self._lm):
            for section in sections[:5]:  # D-CAL-03: 5 sections
                # 4 drift variants — one per DriftDetector dim
                for target_dim in self.DRIFT_TARGET_DIMS_PER_SECTION:
                    result = self.generator(
                        original_text=section.text,
                        mode="drift",
                        target_dim=target_dim,
                    )
                    examples.append(DriftCalibrationExample(
                        section_id=section.section_id,
                        original_text=section.text,
                        evolved_text=str(result.evolved_text),
                        is_drift=True,
                        drift_dim=target_dim,
                        generation_metadata={
                            "seed": self.seed,
                            "generator_model": generator_model,
                            "target_dim": target_dim,
                            "generation_timestamp": timestamp,
                            "mode": "drift",
                        },
                    ))
                # 2 no-drift variants
                for _ in range(2):
                    result = self.generator(
                        original_text=section.text,
                        mode="preserve",
                        target_dim="none",
                    )
                    examples.append(DriftCalibrationExample(
                        section_id=section.section_id,
                        original_text=section.text,
                        evolved_text=str(result.evolved_text),
                        is_drift=False,
                        drift_dim="none",
                        generation_metadata={
                            "seed": self.seed,
                            "generator_model": generator_model,
                            "target_dim": "none",
                            "generation_timestamp": timestamp,
                            "mode": "preserve",
                        },
                    ))

        return DriftCalibrationDataset(examples=examples)


def derive_thresholds(
    calibration: DriftCalibrationDataset,
    config: EvolutionConfig,
) -> dict:
    """Brute-scan thresholds in [0.10, 0.90] step 0.05, pick F1-optimal per dim.

    Pure stdlib (RA3 — sklearn not installed, see CLAUDE.md "no new deps").
    17 candidate thresholds × 30 examples × 4 dims = 2,040 ops < 1ms.

    D-ROB-01: calibration is 1-run per example (NOT the 3-run gate path).
    Per-dim ground truth: positive iff (is_drift AND drift_dim == dim).

    Tie-break: when multiple thresholds yield the same F1, the lower
    threshold wins (more conservative — flags more drift). The strict
    `if f1 > best_f1` check naturally picks the FIRST t to hit the max,
    which is the lowest t (since we iterate ascending).

    Returns:
        dict mapping each DRIFT_DIMENSIONS member to its F1-optimal
        threshold. Failure mode: if no threshold yields F1 > 0, falls
        back to 0.5 for that dim.
    """
    # Step 1: collect 1-run scores per example using a temporary detector
    # with placeholder thresholds (thresholds aren't used by _check_one_run).
    placeholder = {dim: 0.5 for dim in DRIFT_DIMENSIONS}
    detector = DriftDetector(config, placeholder)
    # scored: list of (is_drift, drift_dim_label, scores_dict)
    scored: list = []
    for ex in calibration.examples:
        scores, _ = detector._check_one_run(
            ex.section_id, ex.original_text, ex.evolved_text,
        )
        scored.append((ex.is_drift, ex.drift_dim, scores))

    # Step 2: per-dim F1 brute scan
    best: dict = {}
    for dim in DRIFT_DIMENSIONS:
        labeled = [
            (s[dim], (is_drift and dim_truth == dim))
            for is_drift, dim_truth, s in scored
        ]
        best_t, best_f1 = 0.5, -1.0
        for t10 in range(10, 91, 5):  # 0.10, 0.15, ..., 0.90 -> 17 candidates
            t = t10 / 100.0
            tp = sum(1 for sc, gt in labeled if sc > t and gt)
            fp = sum(1 for sc, gt in labeled if sc > t and not gt)
            fn = sum(1 for sc, gt in labeled if sc <= t and gt)
            if tp == 0:
                f1 = 0.0
            else:
                p = tp / (tp + fp)
                r = tp / (tp + fn)
                f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
            if f1 > best_f1:
                best_t, best_f1 = t, f1
        best[dim] = best_t

    return best
