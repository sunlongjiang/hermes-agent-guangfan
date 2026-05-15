"""RED tests for DriftCalibrationBuilder + derive_thresholds (Phase 18, Wave 0).

Imports of `evolution.prompts.drift_calibration` fail until Wave 1.
"""
import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import dspy
import pytest

from evolution.core.config import EvolutionConfig


class _FakeSection:
    def __init__(self, section_id, text):
        self.section_id = section_id
        self.text = text


class TestDeriveThresholds:
    def test_derive_thresholds_f1_optimal(self, drift_calibration_mini_path):
        """derive_thresholds picks F1-optimal threshold per dim on mini fixture.

        The mini fixture has 3 drift rows (one per dim: tone/formality/vocabulary)
        + 3 no-drift rows. With a mocked detector that returns score=1.0 for the
        drift row's true dim and 0.0 for all other rows, the optimal threshold is
        any value in (0.0, 1.0) — derive_thresholds picks SOME t in [0.10, 0.90]
        yielding F1 = 1.0 on each dim that has positive examples.
        """
        from evolution.prompts.drift_calibration import (
            DriftCalibrationDataset,
            derive_thresholds,
            DriftCalibrationExample,
        )
        from evolution.prompts.drift_detector import DRIFT_DIMENSIONS

        # Load mini fixture
        with open(drift_calibration_mini_path) as f:
            rows = [json.loads(line) for line in f if line.strip()]
        examples = [
            DriftCalibrationExample(
                section_id=r["section_id"],
                original_text=r["original_text"],
                evolved_text=r["evolved_text"],
                is_drift=r["is_drift"],
                drift_dim=r["drift_dim"],
                generation_metadata=r["generation_metadata"],
            )
            for r in rows
        ]
        calibration = DriftCalibrationDataset(examples=examples)

        # Mock DriftDetector._check_one_run via patching the symbol used in
        # drift_calibration. For each example, return 1.0 on the labeled
        # drift_dim, 0.0 elsewhere.
        def fake_check_one_run(self, sid, orig, evolved):
            row = next(
                r for r in rows
                if r["evolved_text"] == evolved
            )
            scores = {dim: 0.0 for dim in DRIFT_DIMENSIONS}
            if row["is_drift"]:
                scores[row["drift_dim"]] = 1.0
            return scores, "mock"

        config = EvolutionConfig.__new__(EvolutionConfig)
        config.eval_model = "openai/gpt-4.1-mini"
        config.api_base = None
        config.api_key = None
        with patch("evolution.prompts.drift_calibration.DriftDetector._check_one_run", new=fake_check_one_run):
            with patch("evolution.prompts.drift_detector.dspy.LM"):
                thresholds = derive_thresholds(calibration, config)

        # All 4 dims must be present
        assert set(thresholds.keys()) >= set(DRIFT_DIMENSIONS)
        # tone/formality/vocabulary have a positive example -> threshold in (0.0, 1.0)
        for dim in ("tone", "formality", "vocabulary"):
            assert 0.0 < thresholds[dim] < 1.0, (
                f"{dim}: expected threshold in (0,1), got {thresholds[dim]}"
            )

    def test_no_sklearn_dependency(self):
        """derive_thresholds must NOT depend on sklearn (CLAUDE.md no-new-deps + RA3).

        Two-layer guard:
          (a) drift_calibration.py source must not contain `import sklearn`.
          (b) After importing the module, sys.modules must not include sklearn.
        """
        import importlib
        # Layer (a): grep source
        module_path = Path("evolution/prompts/drift_calibration.py")
        assert module_path.exists(), f"{module_path} must exist (Wave 1)"
        source = module_path.read_text()
        assert "import sklearn" not in source, "RA3: sklearn import forbidden"
        assert "from sklearn" not in source, "RA3: sklearn import forbidden"
        assert "import numpy" not in source, "RA3: numpy import forbidden"
        assert "import scipy" not in source, "RA3: scipy import forbidden"
        # Layer (b): module loads without pulling sklearn into sys.modules
        sys.modules.pop("sklearn", None)
        importlib.import_module("evolution.prompts.drift_calibration")
        assert "sklearn" not in sys.modules, "RA3: sklearn must not be transitively imported"


class TestDriftCalibrationBuilder:
    def test_generator_uses_judge_model(self):
        """DriftCalibrationBuilder constructs dspy.LM with config.judge_model (RA5)."""
        from evolution.prompts.drift_calibration import DriftCalibrationBuilder

        config = EvolutionConfig.__new__(EvolutionConfig)
        config.eval_model = "openai/gpt-4.1-mini"
        config.judge_model = "openai/gpt-4.1"  # MUST be used by generator
        config.api_base = None
        config.api_key = None
        with patch("evolution.prompts.drift_calibration.dspy.LM") as mock_lm:
            DriftCalibrationBuilder(config, seed=42)
        assert mock_lm.called, "dspy.LM not called from DriftCalibrationBuilder.__init__"
        # First positional arg OR 'model' kwarg must be judge_model
        args, kwargs = mock_lm.call_args
        model_value = args[0] if args else kwargs.get("model")
        assert model_value == "openai/gpt-4.1", (
            f"RA5: expected generator to use config.judge_model='openai/gpt-4.1', "
            f"got {model_value!r} (eval_model='openai/gpt-4.1-mini' would be wrong)"
        )

    @pytest.mark.skipif(
        not os.getenv("RUN_LIVE_LLM"),
        reason="Live-LLM test; gated on RUN_LIVE_LLM=1",
    )
    def test_f1_target_self_eval(self):
        """F1 >= 0.85 on calibration set self-eval (RA6 verify-gate target).

        Live test: generates 30 examples, derives thresholds, computes
        macro-F1 on the same set. Gated by RUN_LIVE_LLM env to avoid
        burning API credits in CI.
        """
        pytest.skip("Skeleton — wire up after Wave 2 ships derive_thresholds + builder")
