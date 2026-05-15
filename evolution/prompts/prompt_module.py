"""Wraps prompt sections as GEPA-optimizable DSPy module.

Each prompt section's text is stored as a dspy.Predict instance's Signature
instructions. Only the active section is discoverable by named_predictors()
(the method GEPA introspects to discover optimization parameters); other
sections' instructions are held as plain strings in a private dict, which
DSPy's parameter-discovery APIs (named_parameters AND named_predictors)
never traverse because plain strings are neither dspy.Parameter nor
dspy.Predict instances.
"""

import dspy

from evolution.prompts.prompt_loader import PromptSection


# ── Constants ───────────────────────────────────────────────────────────────

JOINT_SENTINEL = "__JOINT__"
"""Sentinel value for PromptModule._active_section in joint optimization mode.

Indicates that all sections are simultaneously promoted to Predict instances
in section_predictors, making them all discoverable by named_predictors()
and mutable by GEPA with component_selector='all'.
"""


# ── Signatures ──────────────────────────────────────────────────────────────

class PromptSectionSignature(dspy.Signature):
    """Given a task and system prompt context, respond following the active section's guidance.

    Use the frozen context (other prompt sections) as background, and follow
    the active section's instructions to generate an appropriate response.
    """
    frozen_context: str = dspy.InputField(
        desc="Concatenated text from non-active prompt sections (read-only context)",
    )
    task_input: str = dspy.InputField(
        desc="The task or user message to respond to",
    )
    output: str = dspy.OutputField(
        desc="Response following the active section's guidance",
    )


# ── PromptModule ────────────────────────────────────────────────────────────

class PromptModule(dspy.Module):
    """Wraps prompt sections as GEPA-optimizable parameters.

    Only one section is active (optimizable) at a time. The others
    are frozen and passed as context input. Use set_active_section()
    to switch which section is being optimized.

    Frozen sections are stored as plain instruction strings (not Predict
    instances) so DSPy's parameter-discovery APIs (named_parameters AND
    named_predictors) cannot discover them — GEPA uses named_predictors().

    Args:
        sections: List of PromptSection from prompt_loader.extract_prompt_sections()
    """

    def __init__(self, sections: list[PromptSection]):
        super().__init__()
        # Active section predictor -- discoverable by named_predictors()
        self.section_predictors: dict[str, dspy.Predict] = {}
        # Frozen section instructions -- plain strings, NOT discoverable
        self._frozen_instructions: dict[str, str] = {}
        self._section_ids: list[str] = []
        self._active_section: str | None = None

        for section in sections:
            # Initially all in frozen as plain strings
            self._frozen_instructions[section.section_id] = section.text
            self._section_ids.append(section.section_id)

        # Frozen metadata -- not discoverable by named_parameters()
        self._frozen_sections: dict[str, PromptSection] = {
            s.section_id: s for s in sections
        }

        # Selector for forward pass
        self.selector = dspy.ChainOfThought(PromptSectionSignature)

        # IDs of internal predictors that must stay frozen (invisible to GEPA) in joint mode.
        # selector.predict is the underlying Predict of self.selector (ChainOfThought),
        # which exists for forward routing only — GEPA must not mutate its instructions.
        self._frozen_predictor_ids: set[str] = {"selector.predict"}

    def set_active_section(self, section_id: str) -> None:
        """Set which section is optimizable. Others become frozen context.

        Args:
            section_id: The section to activate for optimization.

        Raises:
            ValueError: If section_id is not a known section.
        """
        if section_id not in self._frozen_sections:
            raise ValueError(
                f"Unknown section: {section_id}. "
                f"Available: {self._section_ids}"
            )
        # Pitfall 3 guard: if currently in joint mode, demote all first (auto-recover)
        if self._active_section == JOINT_SENTINEL:
            self.set_joint_mode(False)
        # Move current active back to frozen (extract instructions from Predict)
        elif self._active_section is not None:
            pred = self.section_predictors.pop(self._active_section)
            self._frozen_instructions[self._active_section] = (
                pred.signature.instructions
            )

        # Move new active from frozen string to Predict instance
        text = self._frozen_instructions.pop(section_id)
        sig = dspy.Signature(
            "section_text -> confirmation",
            instructions=text,
        )
        self.section_predictors[section_id] = dspy.Predict(sig)
        self._active_section = section_id

    def set_joint_mode(self, active: bool = True) -> None:
        """Activate or deactivate joint optimization mode (all sections simultaneously).

        In joint mode (active=True), every section's instruction text is promoted
        from a plain string in _frozen_instructions to a dspy.Predict instance in
        section_predictors. This makes all sections discoverable by
        named_predictors() and mutable by GEPA when called with
        component_selector='all'.

        Joint mode is idempotent — calling set_joint_mode(True) twice is a no-op.
        Calling set_active_section(sid) while in joint mode auto-demotes joint
        first (see set_active_section guard).

        Args:
            active: True to enter joint mode, False to demote all back to frozen.
        """
        if active:
            if self._active_section == JOINT_SENTINEL:
                return  # idempotent
            # If a single section is currently active, move it back to frozen first
            if self._active_section is not None:
                pred = self.section_predictors.pop(self._active_section)
                self._frozen_instructions[self._active_section] = (
                    pred.signature.instructions
                )
            # Promote ALL frozen sections to Predict instances
            for sid in list(self._frozen_instructions.keys()):
                text = self._frozen_instructions.pop(sid)
                sig = dspy.Signature(
                    "section_text -> confirmation",
                    instructions=text,
                )
                self.section_predictors[sid] = dspy.Predict(sig)
            self._active_section = JOINT_SENTINEL
        else:
            # Demote: move every Predict back to frozen string
            for sid in list(self.section_predictors.keys()):
                pred = self.section_predictors.pop(sid)
                self._frozen_instructions[sid] = pred.signature.instructions
            self._active_section = None

    def forward(self, task_input: str) -> dspy.Prediction:
        """Respond to task using current optimization mode's section assembly.

        Three-state dispatch:
        - _active_section is None → RuntimeError (no section set; backward-compat)
        - _active_section == JOINT_SENTINEL → joint mode: concat ALL section
          instructions (from section_predictors[sid].signature.instructions) as
          frozen_context, feed selector once. GEPA mutations to any
          section_predictors[sid].signature.instructions thus actually affect
          forward output (precondition for component_selector='all' to work).
        - _active_section == <real_sid> → round-robin mode: build frozen_context
          including the active section's CURRENT Predict instructions
          (Pitfall 1 fix — previously the active text was not flowing into
          selector, making GEPA mutations no-ops at forward time).

        Args:
            task_input: The task or user message to respond to.

        Returns:
            dspy.Prediction with output attribute.

        Raises:
            RuntimeError: If no active section has been set.
        """
        if self._active_section is None:
            raise RuntimeError(
                "No active section set. Call set_active_section() "
                "or set_joint_mode() first."
            )
        frozen_context = self._build_frozen_context()
        result = self.selector(
            frozen_context=frozen_context,
            task_input=task_input,
        )
        return dspy.Prediction(output=result.output)

    def _build_frozen_context(self) -> str:
        """Concatenate section texts as context string.

        Joint mode (_active_section == JOINT_SENTINEL): concat ALL N sections
        from section_predictors[sid].signature.instructions (the GEPA-mutable
        Predict instances). Every section is jointly active, so no individual
        section is tagged — all use the plain `[sid]:` label.

        Round-robin mode (_active_section is a real sid): concat all N sections
        — non-active from _frozen_instructions[sid] (plain strings), active
        from section_predictors[active].signature.instructions (Pitfall 1 fix:
        the active section's current instructions must flow into selector for
        GEPA mutations to have any effect on forward output). WR-07 fix: the
        active section is tagged `[ACTIVE:{sid}]:` instead of plain `[{sid}]:`
        so the selector LLM (and GEPA reflection) can distinguish the
        currently-optimized section from frozen context, restoring semantic
        clarity that was lost when Pitfall 1 made the active text physically
        indistinguishable from frozen text in the input string.
        """
        parts = []
        for sid in self._section_ids:
            if self._active_section == JOINT_SENTINEL:
                # Joint mode: ALL sections live as Predicts (no single
                # "active" — all are jointly optimized).
                text = self.section_predictors[sid].signature.instructions
                label = f"[{sid}]:"
            elif sid == self._active_section:
                # Round-robin active: read from Predict (Pitfall 1 fix).
                # Tag with [ACTIVE:...] to disambiguate from frozen context
                # for the selector LLM and GEPA reflection (WR-07).
                text = self.section_predictors[sid].signature.instructions
                label = f"[ACTIVE:{sid}]:"
            else:
                # Round-robin frozen: read from string.
                text = self._frozen_instructions[sid]
                label = f"[{sid}]:"
            parts.append(f"{label} {text}")
        return "\n\n".join(parts)

    def named_predictors(self):
        """Override to exclude self.selector in joint mode (Phase 17 decision).

        In joint mode, only section_predictors entries should be visible to GEPA
        with component_selector='all'. The selector is a routing-only primitive
        whose instructions must remain stable across optimization runs.

        In round-robin mode, selector remains visible (existing behavior — see
        Phase 8 tests that expect selector.predict to be discoverable).

        Note (WR-02): Frozen sections live in `_frozen_instructions` as
        dict[str, str] — plain strings, NOT dspy.Parameter or dspy.Predict
        instances. They are therefore invisible to BOTH named_parameters()
        and named_predictors() via dspy's default traversal, with no special
        handling required here. This override only additionally excludes
        selector.predict in joint mode.
        """
        for name, pred in super().named_predictors():
            if self._active_section == JOINT_SENTINEL and name in self._frozen_predictor_ids:
                continue
            yield name, pred

    def get_evolved_sections(self) -> list[PromptSection]:
        """Extract current (possibly evolved) sections merged with frozen metadata.

        Returns:
            List of PromptSection with evolved description text and original
            frozen fields (section_id, line_range, source_path).
        """
        evolved = []
        for sid in self._section_ids:
            # Active section: read from Predict; frozen: read from string
            if sid in self.section_predictors:
                current_text = self.section_predictors[sid].signature.instructions
            else:
                current_text = self._frozen_instructions[sid]
            original = self._frozen_sections[sid]
            evolved.append(PromptSection(
                section_id=original.section_id,
                text=current_text,
                char_count=len(current_text),
                line_range=original.line_range,
                source_path=original.source_path,
            ))
        return evolved
