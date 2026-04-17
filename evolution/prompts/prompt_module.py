"""Wraps prompt sections as GEPA-optimizable DSPy module.

Each prompt section's text is stored as a dspy.Predict instance's Signature
instructions. Only the active section is discoverable by named_parameters();
other sections' instructions are held as plain strings in a private dict,
invisible to the DSPy optimizer.
"""

import dspy

from evolution.prompts.prompt_loader import PromptSection


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
    instances) so DSPy's named_parameters() cannot discover them.

    Args:
        sections: List of PromptSection from prompt_loader.extract_prompt_sections()
    """

    def __init__(self, sections: list[PromptSection]):
        super().__init__()
        # Active section predictor -- discoverable by named_parameters()
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
        # Move current active back to frozen (extract instructions from Predict)
        if self._active_section is not None:
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

    def forward(self, task_input: str) -> dspy.Prediction:
        """Respond to task using active section + frozen context.

        Args:
            task_input: The task or user message to respond to.

        Returns:
            dspy.Prediction with output attribute.

        Raises:
            RuntimeError: If no active section has been set.
        """
        if self._active_section is None:
            raise RuntimeError(
                "No active section set. Call set_active_section() first."
            )
        frozen_context = self._build_frozen_context()
        result = self.selector(
            frozen_context=frozen_context,
            task_input=task_input,
        )
        return dspy.Prediction(output=result.output)

    def _build_frozen_context(self) -> str:
        """Concatenate non-active sections as context string."""
        parts = []
        for sid in self._section_ids:
            if sid != self._active_section:
                text = self._frozen_instructions[sid]
                parts.append(f"[{sid}]: {text}")
        return "\n\n".join(parts)

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
