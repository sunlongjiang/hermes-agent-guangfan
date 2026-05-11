"""Wraps all tool descriptions as a GEPA-optimizable DSPy module.

Phase 13 upgrade: each tool's parameter descriptions become independently
optimizable Predict instances. Tool-level description stays physically
isolated in _frozen_tool_desc (never exposed as a Predict) so GEPA cannot
mutate it. Per-tool params are wrapped in a sub-dspy.Module (the only way
DSPy 3.1.3's named_parameters() will recurse into a dict-of-Predict;
raw dict[str, dict[str, Predict]] at ToolModule level is invisible --
see 13-RESEARCH.md §Pitfall 1 for source-level verification).

Phase 15: optional reasoner Predict exposed via enable_reasoning=True (D-01..D-07).
"""

from typing import Optional

import dspy

from evolution.tools.tool_loader import ToolDescription, ToolParam


# ── Signatures ──────────────────────────────────────────────────────────────

class ToolSelectionWithParamsSignature(dspy.Signature):
    """Given a task and available tools, pick the tool AND infer its params.

    Responds with `selected_tool` (the exact tool name) and `selected_params`
    (a JSON-encoded object -- e.g. '{"pattern":"foo","file_pattern":"*.py"}';
    use '{}' if the tool takes no arguments).
    """
    task_description: str = dspy.InputField(
        desc="The task that needs to be accomplished",
    )
    available_tools: str = dspy.InputField(
        desc="Formatted list of available tools with their descriptions and parameters",
    )
    reasoning: str = dspy.InputField(
        default="",
        desc=(
            "Optional pre-reasoning from think-on path; empty string '' on "
            "think-off path. If non-empty, treat as advisory context — do not "
            "blindly defer; reasoning may be wrong."
        ),
    )
    selected_tool: str = dspy.OutputField(
        desc="The exact name of the most appropriate tool for this task",
    )
    selected_params: str = dspy.OutputField(
        desc=(
            "JSON object mapping param_name to value, e.g. "
            '\'{"pattern":"foo","file_pattern":"*.py"}\'. '
            "Return '{}' if the tool requires no parameters."
        ),
    )


# ── Phase 15 Reasoning Signature ────────────────────────────────────────

class ToolReasoningSignature(dspy.Signature):
    """Briefly reason about which tool best fits this task.

    Be concise (≤200 tokens). Mention what makes the candidate tools
    different in this context. Do NOT pre-select a tool — that is the
    selector's job. Focus on disambiguating overlapping tools by their
    intent, scope, or side-effects.
    """
    task_description: str = dspy.InputField(
        desc="The task to accomplish",
    )
    available_tools: str = dspy.InputField(
        desc="Formatted listing of available tools with descriptions and params",
    )
    reasoning: str = dspy.OutputField(
        desc="Short rationale comparing top candidates, ≤200 tokens. Do not name a winner.",
    )


# ── Per-Tool Bundle (discoverable by DSPy) ─────────────────────────────────

class _ToolParamBundle(dspy.Module):
    """Per-tool container holding a flat dict[param_name, dspy.Predict].

    Must be a dspy.Module (not a raw dict-of-dict) because DSPy 3.1.3's
    base_module.add_parameter() recurses into Module values but silently
    drops nested dict-of-dict values (VERIFIED: .venv dspy 3.1.3 source +
    runtime smoke test in 13-RESEARCH.md §Pitfall 1).
    """

    def __init__(
        self,
        tool_name: str,
        params: list[ToolParam],
    ):
        super().__init__()
        self.tool_name = tool_name
        self.param_names: list[str] = [p.name for p in params]
        self.param_predictors: dict[str, dspy.Predict] = {}

        for p in params:
            # D-03: register every param as Predict, including empty-description ones.
            # Empty/None description → instruction string "" (literal empty) so the
            # test_empty_param_registered contract can assert both: (a) a Predict
            # exists for every param, and (b) empty-desc params preserve "" (not
            # a synthetic placeholder that GEPA would then have to strip).
            desc_text = (p.description or "").strip()
            sig = dspy.Signature(
                "param_name -> confirmation",
                instructions=desc_text,
            )
            self.param_predictors[p.name] = dspy.Predict(sig)

    def forward(self, param_name: str) -> dspy.Prediction:
        """Never called during Phase 13 GEPA -- param_predictors are instruction
        carriers only. Defined so dspy.Module contract is satisfied.
        """
        return dspy.Prediction(confirmation="")


# ── ToolModule (top-level) ──────────────────────────────────────────────────

class ToolModule(dspy.Module):
    """Phase-13 ToolModule exposing per-parameter descriptions as GEPA targets.

    Phase 15: optional think-on path via enable_reasoning=True (D-01..D-07).

    Args:
        tool_descriptions: List of ToolDescription from tool_loader.extract_tool_descriptions().
        enable_reasoning: If True, constructs self.reasoner = dspy.Predict(ToolReasoningSignature)
            with max_tokens=200 LM override. If False (default), Phase 13 behavior preserved.
        eval_model: LM model name for the reasoner's per-Predict LM override (D-04).
        lm_kwargs: Extra LM kwargs (max_tokens excluded -- always 200 for reasoner).

    Contract:
        - named_predictors() yields one entry per (tool, param), path
          `tools['<name>'].param_predictors['<param>']` (D-04).
        - tool-level text is held in `_frozen_tool_desc: dict[str, str]`,
          physically absent from the predictor graph (D-02).
        - forward(task_description) returns dspy.Prediction with both
          `selected_tool` and `selected_params` (JSON-string) fields (D-05, D-18).
        - Phase 15: forward also returns `reasoning` (str) and `reasoning_tokens` (int).
    """

    def __init__(
        self,
        tool_descriptions: list[ToolDescription],
        *,
        enable_reasoning: bool = False,
        eval_model: str = "openai/gpt-4.1-mini",
        lm_kwargs: Optional[dict] = None,
    ):
        super().__init__()

        # D-01/D-04: per-tool sub-Module dict -- discoverable + hierarchical.
        self.tools: dict[str, _ToolParamBundle] = {}

        # D-02: physically isolated top-level descriptions.
        self._frozen_tool_desc: dict[str, str] = {}

        # Full ToolDescription snapshot for get_evolved_descriptions() round-trip.
        self._frozen_tools: dict[str, ToolDescription] = {}
        self._tool_names: list[str] = []

        for td in tool_descriptions:
            safe_name = self._safe_key(td.name)
            self.tools[safe_name] = _ToolParamBundle(td.name, list(td.params))
            self._frozen_tool_desc[td.name] = (
                td.description or f"Tool: {td.name}"
            )
            self._frozen_tools[td.name] = td
            self._tool_names.append(td.name)

        # Selector: ChainOfThought with upgraded signature (D-05).
        self.selector = dspy.ChainOfThought(ToolSelectionWithParamsSignature)

        # ── Phase 15: Optional reasoner Predict ─────────────────────────
        # D-05: opt-in flag, static branching at constructor.
        # D-07: enable_reasoning is immutable after __init__ — never set self.reasoner
        # outside this block.
        self.enable_reasoning: bool = bool(enable_reasoning)
        self.reasoner: Optional[dspy.Predict] = None
        if self.enable_reasoning:
            # D-04 双保险其一: reasoner LM max_tokens=200.
            # Filter caller-supplied lm_kwargs to avoid double-max_tokens.
            filtered_kwargs = {
                k: v for k, v in (lm_kwargs or {}).items()
                if k != "max_tokens"
            }
            reasoning_lm = dspy.LM(eval_model, max_tokens=200, **filtered_kwargs)
            # D-01: separate Predict, NOT a CoT — selector retains independence.
            self.reasoner = dspy.Predict(ToolReasoningSignature)
            # RESEARCH §1.3 Path C: per-Predict LM override for token cap.
            self.reasoner.set_lm(reasoning_lm)

    # ── internals ───────────────────────────────────────────────────────────

    @staticmethod
    def _safe_key(tool_name: str) -> str:
        """Normalize tool name for use as a Python-safe dict key.

        Mirrors Phase 3 behavior: replace '-' with '_'. Do NOT otherwise
        rename -- preservation of original tool_name goes via self._tool_names
        and self._frozen_tools lookup.
        """
        return tool_name.replace("-", "_")

    def _format_available_tools(self) -> str:
        """Assemble the human-readable tool listing fed to the selector.

        D-02 compliance: reads the frozen string map -- GEPA cannot influence
        this text because _frozen_tool_desc is not a Predict.
        """
        parts = []
        for name in self._tool_names:
            safe = self._safe_key(name)
            tool_desc = self._frozen_tool_desc[name]
            param_lines = []
            bundle = self.tools[safe]
            for pn in bundle.param_names:
                p_desc = bundle.param_predictors[pn].signature.instructions
                param_lines.append(f"    - {pn}: {p_desc}")
            param_block = "\n".join(param_lines) if param_lines else "    (no parameters)"
            parts.append(f"- {name}: {tool_desc}\n{param_block}")
        return "\n".join(parts)

    # ── public surface ──────────────────────────────────────────────────────

    def forward(self, task_description: str) -> dspy.Prediction:
        """Select the best tool AND its parameters for a given task.

        Phase 15: if self.reasoner is not None (enable_reasoning=True), run the
        reasoner first to produce a short rationale, then pass it to selector as
        an InputField. Otherwise the path is identical to Phase 13.

        Args:
            task_description: Description of the task to accomplish.

        Returns:
            dspy.Prediction with:
                - selected_tool (str)
                - selected_params (str, JSON-encoded dict; may be '{}')
                - reasoning (str; '' on think-off path)
                - reasoning_tokens (int; 0 on think-off path)
        """
        available_tools = self._format_available_tools()

        # Phase 15: think-on path runs reasoner first (D-01, D-02).
        reasoning_text = ""
        if self.reasoner is not None:
            reasoning_pred = self.reasoner(
                task_description=task_description,
                available_tools=available_tools,
            )
            # Defensive: reasoner Prediction may have empty/None reasoning under
            # certain LM error states. Coerce to str.
            reasoning_text = str(getattr(reasoning_pred, "reasoning", "") or "")

        # Selector retains FULL tools listing (D-02 — no rubber-stamp). The
        # `reasoning` InputField is advisory; default "" preserves Phase 13
        # behavior on think-off path.
        result = self.selector(
            task_description=task_description,
            available_tools=available_tools,
            reasoning=reasoning_text,
        )
        selected_params = getattr(result, "selected_params", "") or "{}"
        # Do NOT attempt json.loads here -- that's the metric's job (D-17).
        # Preserve raw string so metric can flag malformed output (Pitfall 7).

        # RESEARCH §1.4 Path 1: token estimate = len(text)/4 — good enough for
        # ThinkABGate decisioning with 200-token cap (Phase 16 dashboard can
        # upgrade to precise LM usage later).
        reasoning_tokens = int(len(reasoning_text) / 4) if reasoning_text else 0

        return dspy.Prediction(
            selected_tool=result.selected_tool,
            selected_params=selected_params,
            reasoning=reasoning_text,
            reasoning_tokens=reasoning_tokens,
        )

    def get_evolved_descriptions(self) -> list[ToolDescription]:
        """Reassemble ToolDescription list from (frozen tool-level text, evolved per-param text).

        Returns:
            List of ToolDescription where .description stays untouched (D-02
            -- tool-level is frozen) and each .params[i].description reflects
            whatever GEPA has mutated the corresponding Predict's instructions
            to (possibly identical to the original if no iteration changed it).
        """
        evolved: list[ToolDescription] = []
        for name in self._tool_names:
            safe = self._safe_key(name)
            bundle = self.tools[safe]
            original = self._frozen_tools[name]
            # Build new ToolParam list with evolved description, frozen everything else.
            new_params: list[ToolParam] = []
            for p in original.params:
                pred = bundle.param_predictors.get(p.name)
                evolved_desc = (
                    pred.signature.instructions if pred is not None else p.description
                )
                new_params.append(
                    ToolParam(
                        name=p.name,
                        type=p.type,
                        required=p.required,
                        description=evolved_desc,
                        # Preserve frozen ToolParam fields via reflection:
                        **{
                            k: getattr(p, k)
                            for k in p.__dataclass_fields__
                            if k not in ("name", "type", "required", "description")
                        },
                    )
                )
            evolved.append(
                ToolDescription(
                    name=original.name,
                    file_path=original.file_path,
                    description=self._frozen_tool_desc[original.name],  # unchanged
                    params=new_params,
                    desc_format=original.desc_format,
                    schema_var_name=original.schema_var_name,
                    raw_source=original.raw_source,
                )
            )
        return evolved
