"""AgentModule: DSPy wrapper for one EvolvableArtifact.

Mirrors evolution/skills/skill_module.py SkillModule pattern but per-artifact
instead of per-skill. The artifact text is the parameter GEPA mutates.

build_composite_metric implements spec §5.2 weighted scoring with automatic
weight redistribution when components are missing.
"""

import logging
from dataclasses import dataclass
from typing import Callable, Optional

import dspy

from evolution.sdk.artifact import EvolvableArtifact

log = logging.getLogger("evolution.sdk.agent_module")


@dataclass
class JudgeConfig:
    """Configuration for the LLM-judge component of composite_metric."""
    model: str
    dimensions: tuple[str, ...]


class AgentModule(dspy.Module):
    """DSPy module wrapping a single EvolvableArtifact for GEPA optimization.

    The artifact's baseline_text becomes the initial value of the parameter
    that GEPA mutates. forward() composes the parameter as instructions to a
    ChainOfThought predictor over a kind-specific Signature.
    """

    def __init__(self, artifact: EvolvableArtifact, judge_dimensions: tuple[str, ...]):
        super().__init__()
        self.artifact = artifact
        self.judge_dimensions = judge_dimensions
        self.current_text = artifact.baseline_text

        if artifact.kind == "prompt":
            self._sig = self._build_prompt_signature()
        elif artifact.kind == "tool":
            self._sig = self._build_tool_signature()
        else:
            raise ValueError(f"unknown artifact kind: {artifact.kind!r}")

        self.predictor = dspy.ChainOfThought(self._sig)

    def _build_prompt_signature(self):
        class _PromptSig(dspy.Signature):
            """Apply the prompt instructions to the user input."""
            prompt_text: str = dspy.InputField(desc="The prompt instructions to follow")
            user_input: str = dspy.InputField(desc="The user-provided input")
            output: str = dspy.OutputField(desc="Response following the prompt")
        return _PromptSig

    def _build_tool_signature(self):
        class _ToolSig(dspy.Signature):
            """Decide if this tool description matches the user's intent."""
            tool_description: str = dspy.InputField(desc="The tool description to evaluate")
            user_intent: str = dspy.InputField(desc="What the user wants to do")
            output: str = dspy.OutputField(desc="Whether/how this tool applies")
        return _ToolSig

    def set_text(self, new_text: str) -> None:
        """Mutate the current artifact text. Called by GEPA between generations."""
        self.current_text = new_text

    def forward(self, **kwargs) -> dspy.Prediction:
        if self.artifact.kind == "prompt":
            result = self.predictor(prompt_text=self.current_text,
                                    user_input=kwargs.get("user_input", ""))
        else:
            result = self.predictor(tool_description=self.current_text,
                                    user_intent=kwargs.get("user_intent", ""))
        return dspy.Prediction(output=result.output)


def build_composite_metric(
    *,
    user_metric: Optional[Callable[[dict, str], float]],
    judge_config: Optional[JudgeConfig],
    signals_provider: Callable[[dict], float],
) -> Callable:
    """Construct a DSPy-compatible metric implementing the spec §5.2 weighted score.

    Args:
        user_metric: optional (trace_dict, output) -> float in [0,1]
        judge_config: JudgeConfig if LLM-judge is enabled, else None
        signals_provider: (trace_dict) -> signal_score in [0,1]

    Returns:
        metric(example, prediction) -> float — usable by dspy.GEPA(metric=...).

    Weight redistribution:
        - all three: 0.5 * user + 0.3 * judge + 0.2 * signal
        - no user_metric: 0.7 * judge + 0.3 * signal
        - no judge (None or empty dimensions): 1.0 * signal (or 1.0 * user if provided)
        - user_metric raises: fall back as if user_metric was None
    """
    has_user = user_metric is not None
    has_judge = judge_config is not None and len(judge_config.dimensions) > 0

    def metric(example, prediction, trace=None):
        trace_dict = getattr(example, "trace", {}) or {}
        output = getattr(prediction, "output", "")
        # judge score may be precomputed and attached to prediction by the
        # optimizer (avoids per-metric-call LLM hits during inner loops).
        precomputed_judge = getattr(prediction, "_judge_score", None)

        # Signal component (always available).
        signal_score = signals_provider(trace_dict)

        # User metric component (defensive).
        user_score = None
        if has_user:
            try:
                user_score = float(user_metric(trace_dict, output))
                user_score = max(0.0, min(1.0, user_score))
            except Exception as e:  # noqa: BLE001
                log.warning("user metric raised; falling back: %s", e)
                user_score = None

        # Judge component.
        judge_score = None
        if has_judge:
            if precomputed_judge is not None:
                judge_score = max(0.0, min(1.0, float(precomputed_judge)))
            else:
                judge_score = _invoke_judge(judge_config, trace_dict, output)

        # Combine with redistribution.
        if user_score is not None and judge_score is not None:
            return 0.5 * user_score + 0.3 * judge_score + 0.2 * signal_score
        if judge_score is not None:
            return 0.7 * judge_score + 0.3 * signal_score
        if user_score is not None:
            return 0.7 * user_score + 0.3 * signal_score
        return signal_score

    return metric


def _invoke_judge(cfg: JudgeConfig, trace: dict, output: str) -> float:
    """LLM-as-judge call. Returns mean across dimensions in [0,1].

    Defensive: returns 0.5 on any LLM error (neutral score, doesn't bias optimization).
    Mocked tests bypass this via prediction._judge_score.
    """
    try:
        from evolution.core.fitness import LLMJudge  # type: ignore
        from evolution.core.config import EvolutionConfig
        # Load full config so api_base/api_key flow through to the judge LM.
        ec = EvolutionConfig.load()
        ec.eval_model = cfg.model
        judge = LLMJudge(ec)
        # The hermes LLMJudge expects (task_input, expected_behavior, agent_output, skill_text).
        # For SDK runs we don't have an authoritative "expected_behavior" — the trace's recorded
        # output IS the current behaviour. Passing the recorded output as the expected_behavior
        # gives the judge a concrete reference; the optimizer's job is to find a prompt that
        # makes a different policy produce something equally good or better.
        scored = judge.score(
            task_input=str(trace.get("input", "")),
            expected_behavior=str(trace.get("output", "")),
            agent_output=output,
            skill_text=str(trace.get("artifacts", "")),
        )
        # composite is a [0,1] value
        return getattr(scored, "composite", 0.5)
    except Exception as e:  # noqa: BLE001
        log.warning("judge failed: %s", e)
        return 0.5
