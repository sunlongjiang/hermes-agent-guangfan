"""Wraps all tool descriptions as a GEPA-optimizable DSPy module.

Each tool's description text is stored as a dspy.Predict instance's Signature
instructions. GEPA discovers these via named_parameters() and can independently
optimize each tool's description. Schema structure (param names, types, required,
enum) is frozen and inaccessible to the optimizer.
"""

import dspy

from evolution.tools.tool_loader import ToolDescription


# ── Signatures ──────────────────────────────────────────────────────────────

class ToolSelectionSignature(dspy.Signature):
    """Given a task and available tools, select the most appropriate tool.

    Analyze the task requirements and match them to the tool whose
    description best fits the task.
    """
    task_description: str = dspy.InputField(
        desc="The task that needs to be accomplished",
    )
    available_tools: str = dspy.InputField(
        desc="Formatted list of available tools with their descriptions",
    )
    selected_tool: str = dspy.OutputField(
        desc="The name of the most appropriate tool for this task",
    )


# ── ToolModule ──────────────────────────────────────────────────────────────

class ToolModule(dspy.Module):
    """Wraps all tool descriptions as GEPA-optimizable parameters.

    Each tool's description is stored as a Predict instance's Signature
    instructions. GEPA can independently optimize each tool's description
    text while schema structure remains frozen.

    Args:
        tool_descriptions: List of ToolDescription from tool_loader.extract_tool_descriptions()
    """

    def __init__(self, tool_descriptions: list[ToolDescription]):
        super().__init__()
        self.tool_predictors: dict[str, dspy.Predict] = {}
        self._tool_names: list[str] = []

        for td in tool_descriptions:
            safe_name = td.name.replace("-", "_")
            desc = td.description if td.description else f"Tool: {td.name}"
            sig = dspy.Signature("tool_name -> confirmation", instructions=desc)
            self.tool_predictors[safe_name] = dspy.Predict(sig)
            self._tool_names.append(td.name)

        # Frozen schema -- not discoverable by named_parameters()
        self._frozen_tools: dict[str, ToolDescription] = {
            td.name: td for td in tool_descriptions
        }

        # Selector uses ChainOfThought for reasoning about tool choice
        self.selector = dspy.ChainOfThought(ToolSelectionSignature)

    def forward(self, task_description: str) -> dspy.Prediction:
        """Select the best tool for a given task.

        Args:
            task_description: Description of the task to accomplish.

        Returns:
            dspy.Prediction with selected_tool field.
        """
        tool_list_parts = []
        for name in self._tool_names:
            safe_name = name.replace("-", "_")
            desc = self.tool_predictors[safe_name].signature.instructions
            tool_list_parts.append(f"- {name}: {desc}")

        available_tools = "\n".join(tool_list_parts)
        result = self.selector(
            task_description=task_description,
            available_tools=available_tools,
        )
        return dspy.Prediction(selected_tool=result.selected_tool)

    def get_evolved_descriptions(self) -> list[ToolDescription]:
        """Extract current (possibly evolved) descriptions merged with frozen schema.

        Returns:
            List of ToolDescription with evolved description text and original
            frozen fields (params, file_path, schema_var_name, etc.).
        """
        evolved = []
        for name in self._tool_names:
            safe_name = name.replace("-", "_")
            pred = self.tool_predictors[safe_name]
            current_desc = pred.signature.instructions
            original = self._frozen_tools[name]
            evolved.append(
                ToolDescription(
                    name=original.name,
                    file_path=original.file_path,
                    description=current_desc,
                    params=original.params,
                    desc_format=original.desc_format,
                    schema_var_name=original.schema_var_name,
                    raw_source=original.raw_source,
                )
            )
        return evolved
