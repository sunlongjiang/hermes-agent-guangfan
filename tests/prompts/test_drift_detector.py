"""RED tests for DriftDetector (Phase 18, Wave 0).

Imports of `evolution.prompts.drift_detector` will fail until Wave 3.
pytest collection succeeds (file is syntactically valid); individual tests
fail with ImportError or assertion failure. This is the intended RED baseline.
"""
import json
import statistics
from unittest.mock import MagicMock, patch

import dspy
import pytest
from pydantic import ValidationError

from evolution.core.config import EvolutionConfig
from evolution.core.constraints import ConstraintResult


def _make_detector(thresholds=None):
    """Helper: build DriftDetector with mocked dspy.LM (returns None on construct).

    Imports DriftDetector lazily so collection succeeds even before Wave 3.
    """
    from evolution.prompts.drift_detector import DriftDetector, DRIFT_DIMENSIONS

    config = EvolutionConfig.__new__(EvolutionConfig)
    config.eval_model = "openai/gpt-4.1-mini"
    config.api_base = None
    config.api_key = None
    thresholds = thresholds or {dim: 0.5 for dim in DRIFT_DIMENSIONS}
    with patch("evolution.prompts.drift_detector.dspy.LM"):
        return DriftDetector(config, thresholds)


class _FakeSection:
    """Stand-in for PromptSection — only needs section_id + text attributes."""
    def __init__(self, section_id, text):
        self.section_id = section_id
        self.text = text


class TestDriftDetector:
    # ── RA1 (typed float OutputField + 0.0 fallback) ─────────────────

    def test_typed_float_parsing(self):
        """DriftScoreSignature uses Python type annotation float (not type= kwarg)."""
        from evolution.prompts.drift_detector import DriftDetector
        sig = DriftDetector.DriftScoreSignature
        # DSPy 3.x: float type lives in model_fields[<name>].annotation
        assert sig.model_fields["tone_score"].annotation is float
        assert sig.model_fields["formality_score"].annotation is float
        assert sig.model_fields["vocabulary_score"].annotation is float
        assert sig.model_fields["persona_score"].annotation is float

    def test_parse_failure_fallback_zero(self):
        """ValidationError in judge call -> all 4 scores fallback to 0.0 (NOT 0.5)."""
        detector = _make_detector()
        # Make the wrapped ChainOfThought raise ValidationError on call
        from pydantic import ValidationError as PVE
        mock_judge = MagicMock(side_effect=PVE.from_exception_data(title="x", line_errors=[]))
        detector.judge = mock_judge

        scores, explanation = detector._check_one_run(
            "memory_guidance", "orig text", "evolved text",
        )
        assert scores == {"tone": 0.0, "formality": 0.0, "vocabulary": 0.0, "persona": 0.0}, (
            f"expected 0.0 fallback (M4 prevention), got {scores}"
        )
        assert "Parse failure" in explanation, (
            f"expected fallback explanation, got {explanation!r}"
        )

    # ── RA2 (temperature=0.7 + cache=False + non-zero stdev) ────────

    def test_lm_constructed_with_temperature(self):
        """DriftDetector.__init__ calls dspy.LM with temperature=0.7 (RA2 / Pitfall A)."""
        from evolution.prompts.drift_detector import DriftDetector, DRIFT_DIMENSIONS
        config = EvolutionConfig.__new__(EvolutionConfig)
        config.eval_model = "openai/gpt-4.1-mini"
        config.api_base = None
        config.api_key = None
        with patch("evolution.prompts.drift_detector.dspy.LM") as mock_lm:
            DriftDetector(config, {dim: 0.5 for dim in DRIFT_DIMENSIONS})
        assert mock_lm.called, "dspy.LM was never called from DriftDetector.__init__"
        kwargs = mock_lm.call_args.kwargs
        assert kwargs.get("temperature") == 0.7, (
            f"RA2: expected temperature=0.7 in dspy.LM kwargs, got {kwargs}"
        )
        # Belt-and-suspenders: cache must be disabled too (Open Q1)
        assert kwargs.get("cache") is False, (
            f"expected cache=False to prevent identical 3-run responses, got {kwargs}"
        )

    def test_three_run_stdev_nonzero(self):
        """3 stochastic runs -> per-dim stdev > 0 (RA2 — proves cache is not biting)."""
        detector = _make_detector()
        # Return 3 different scores across 3 invocations
        preds = [
            dspy.Prediction(tone_score=0.4, formality_score=0.1, vocabulary_score=0.1, persona_score=0.1, explanation="r1"),
            dspy.Prediction(tone_score=0.5, formality_score=0.1, vocabulary_score=0.1, persona_score=0.1, explanation="r2"),
            dspy.Prediction(tone_score=0.6, formality_score=0.1, vocabulary_score=0.1, persona_score=0.1, explanation="r3"),
        ]
        detector.judge = MagicMock(side_effect=preds)
        with patch("evolution.prompts.drift_detector.dspy.context"):
            result = detector.check("memory_guidance", "orig", "evolved")
        assert result["per_dim"]["tone"]["stdev"] > 0.0, (
            f"3 distinct scores must yield stdev > 0; got {result['per_dim']['tone']}"
        )
        assert result["per_dim"]["tone"]["raw"] == [0.4, 0.5, 0.6]

    # ── D-ROB-02 conservative decision rule ──────────────────────────

    def test_conservative_decision_rule(self):
        """exceeded := (mean - 1*stdev) > threshold[dim] — boundary case."""
        detector = _make_detector(thresholds={"tone": 0.45, "formality": 0.5, "vocabulary": 0.5, "persona": 0.5})
        # Scores 0.4 / 0.5 / 0.6 -> mean=0.5, stdev=0.1, mean-stdev=0.4. threshold=0.45.
        # 0.4 > 0.45 is FALSE -> exceeded must be False (conservative).
        preds = [
            dspy.Prediction(tone_score=0.4, formality_score=0.0, vocabulary_score=0.0, persona_score=0.0, explanation="r1"),
            dspy.Prediction(tone_score=0.5, formality_score=0.0, vocabulary_score=0.0, persona_score=0.0, explanation="r2"),
            dspy.Prediction(tone_score=0.6, formality_score=0.0, vocabulary_score=0.0, persona_score=0.0, explanation="r3"),
        ]
        detector.judge = MagicMock(side_effect=preds)
        with patch("evolution.prompts.drift_detector.dspy.context"):
            result = detector.check("memory_guidance", "o", "e")
        assert result["per_dim"]["tone"]["exceeded"] is False, (
            f"D-ROB-02: mean-stdev=0.4 < threshold=0.45 must NOT exceed; got {result['per_dim']['tone']}"
        )

    # ── D-GATE-01 severity ladder ────────────────────────────────────

    def test_check_returns_4_dim_scores(self):
        """check() returns dict with per_dim covering exactly the 4 DRIFT_DIMENSIONS."""
        from evolution.prompts.drift_detector import DRIFT_DIMENSIONS
        detector = _make_detector()
        preds = [dspy.Prediction(tone_score=0.1, formality_score=0.1, vocabulary_score=0.1, persona_score=0.1, explanation=f"r{i}") for i in range(3)]
        detector.judge = MagicMock(side_effect=preds)
        with patch("evolution.prompts.drift_detector.dspy.context"):
            result = detector.check("memory_guidance", "orig", "evolved")
        assert set(result["per_dim"].keys()) == set(DRIFT_DIMENSIONS)
        for dim in DRIFT_DIMENSIONS:
            pd = result["per_dim"][dim]
            assert set(pd.keys()) >= {"mean", "stdev", "exceeded", "raw"}
            assert len(pd["raw"]) == 3

    def test_severity_ladder_pass(self):
        """0 dims exceeded -> severity=pass, passed=True."""
        detector = _make_detector(thresholds={"tone": 0.9, "formality": 0.9, "vocabulary": 0.9, "persona": 0.9})
        preds = [dspy.Prediction(tone_score=0.1, formality_score=0.1, vocabulary_score=0.1, persona_score=0.1, explanation=f"r{i}") for i in range(3)]
        detector.judge = MagicMock(side_effect=preds)
        with patch("evolution.prompts.drift_detector.dspy.context"):
            result = detector.check("memory_guidance", "o", "e")
        assert result["severity"] == "pass"
        assert result["exceeded_count"] == 0
        assert result["constraint_result"].passed is True

    def test_severity_ladder_warn(self):
        """1 dim exceeded -> severity=warn, passed=True (D-GATE-01: still deploy)."""
        detector = _make_detector(thresholds={"tone": 0.3, "formality": 0.9, "vocabulary": 0.9, "persona": 0.9})
        preds = [dspy.Prediction(tone_score=0.8, formality_score=0.1, vocabulary_score=0.1, persona_score=0.1, explanation=f"r{i}") for i in range(3)]
        detector.judge = MagicMock(side_effect=preds)
        with patch("evolution.prompts.drift_detector.dspy.context"):
            result = detector.check("memory_guidance", "o", "e")
        assert result["severity"] == "warn"
        assert result["exceeded_count"] == 1
        assert result["constraint_result"].passed is True, "D-GATE-01: 1 dim warn must still pass constraint"

    def test_severity_ladder_reject(self):
        """2+ dims exceeded -> severity=reject, passed=False (D-GATE-01: hard reject)."""
        detector = _make_detector(thresholds={"tone": 0.3, "formality": 0.3, "vocabulary": 0.9, "persona": 0.9})
        preds = [dspy.Prediction(tone_score=0.8, formality_score=0.8, vocabulary_score=0.1, persona_score=0.1, explanation=f"r{i}") for i in range(3)]
        detector.judge = MagicMock(side_effect=preds)
        with patch("evolution.prompts.drift_detector.dspy.context"):
            result = detector.check("memory_guidance", "o", "e")
        assert result["severity"] == "reject"
        assert result["exceeded_count"] >= 2
        assert result["constraint_result"].passed is False, "D-GATE-01: 2+ dims must fail constraint"


class TestDriftDetectorCheckAll:
    def test_drift_report_payload(self):
        """check_all returns list of dicts whose schema matches downstream consumers."""
        from evolution.prompts.drift_detector import DRIFT_DIMENSIONS
        detector = _make_detector()
        preds = [dspy.Prediction(tone_score=0.1, formality_score=0.1, vocabulary_score=0.1, persona_score=0.1, explanation=f"r{i}") for i in range(3)]
        detector.judge = MagicMock(side_effect=preds)
        originals = [_FakeSection("memory_guidance", "orig text")]
        evolved = [_FakeSection("memory_guidance", "evolved text")]
        with patch("evolution.prompts.drift_detector.dspy.context"):
            results = detector.check_all(originals, evolved)
        assert len(results) == 1
        r = results[0]
        assert r["section_id"] == "memory_guidance"
        assert set(r["per_dim"].keys()) == set(DRIFT_DIMENSIONS)
        assert r["severity"] in ("pass", "warn", "reject")
        assert isinstance(r["constraint_result"], ConstraintResult)
        assert r["constraint_result"].constraint_name == "drift_detection"
        assert isinstance(r["explanation"], str)  # last-run explanation
