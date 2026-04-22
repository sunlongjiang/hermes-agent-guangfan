"""Tool selection dataset classes and synthetic builder.

Provides data structures for tool selection evaluation examples (task -> tool mapping)
and a two-step LLM-based dataset builder that generates examples with confuser tasks
for overlapping tools.

Classes:
    ToolSelectionExample -- single (task, correct_tool, params) triple with metadata
    ToolSelectionDataset -- train/val/holdout split collection with JSONL persistence
    ToolDatasetBuilder   -- two-step synthetic generation via DSPy ChainOfThought
"""

import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import dspy

from rich.console import Console

from evolution.core.config import EvolutionConfig

console = Console()


# ── Data Classes ────────────────────────────────────────────────────────────


@dataclass
class ToolSelectionExample:
    """A single tool selection evaluation example.

    Represents a (task, correct_tool, correct_params) triple with difficulty,
    confuser information, and provenance metadata.

    Args:
        task_description: Natural language description of the user task.
        correct_tool: Name of the tool that should be selected.
        correct_params: Expected parameter values for the tool call.
        difficulty: One of 'easy', 'medium', 'hard'.
        confuser_tools: Tools that could plausibly be confused with correct_tool.
        reason: Explanation of why correct_tool is the right choice.
        source: Provenance: 'synthetic', 'golden', etc.
    """
    task_description: str
    correct_tool: str
    correct_params: dict = field(default_factory=dict)
    difficulty: str = "medium"  # easy, medium, hard
    confuser_tools: list[str] = field(default_factory=list)
    reason: str = ""
    source: str = "synthetic"

    def to_dict(self) -> dict:
        """Serialize all fields to a dict."""
        return {
            "task_description": self.task_description,
            "correct_tool": self.correct_tool,
            "correct_params": self.correct_params,
            "difficulty": self.difficulty,
            "confuser_tools": self.confuser_tools,
            "reason": self.reason,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ToolSelectionExample":
        """Deserialize from dict, ignoring unknown keys."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class ToolSelectionDataset:
    """Train/val/holdout split of tool selection examples.

    Mirrors the EvalDataset pattern from evolution/core/dataset_builder.py,
    with JSONL persistence and DSPy Example conversion.
    """
    train: list[ToolSelectionExample] = field(default_factory=list)
    val: list[ToolSelectionExample] = field(default_factory=list)
    holdout: list[ToolSelectionExample] = field(default_factory=list)

    @property
    def all_examples(self) -> list[ToolSelectionExample]:
        """Return concatenation of all splits."""
        return self.train + self.val + self.holdout

    def save(self, path: Path):
        """Save dataset splits to JSONL files.

        Creates train.jsonl, val.jsonl, holdout.jsonl in the given directory.

        Args:
            path: Directory to write files into (created if needed).
        """
        path.mkdir(parents=True, exist_ok=True)
        for split_name, split_data in [
            ("train", self.train),
            ("val", self.val),
            ("holdout", self.holdout),
        ]:
            with open(path / f"{split_name}.jsonl", "w") as f:
                for ex in split_data:
                    f.write(json.dumps(ex.to_dict()) + "\n")

    @classmethod
    def load(cls, path: Path) -> "ToolSelectionDataset":
        """Load dataset splits from JSONL files.

        Args:
            path: Directory containing train.jsonl, val.jsonl, holdout.jsonl.

        Returns:
            ToolSelectionDataset with loaded examples.
        """
        dataset = cls()
        for split_name in ["train", "val", "holdout"]:
            split_file = path / f"{split_name}.jsonl"
            if split_file.exists():
                examples = []
                with open(split_file) as f:
                    for line in f:
                        if line.strip():
                            examples.append(ToolSelectionExample.from_dict(json.loads(line)))
                setattr(dataset, split_name, examples)
        return dataset

    def to_dspy_examples(self, split: str = "train") -> list[dspy.Example]:
        """Convert a split to DSPy Example objects.

        Only task_description is marked as input; correct_tool is the label.

        Args:
            split: Which split to convert ('train', 'val', or 'holdout').

        Returns:
            List of dspy.Example instances.
        """
        data = getattr(self, split)
        return [
            dspy.Example(
                task_description=ex.task_description,
                correct_tool=ex.correct_tool,
            ).with_inputs("task_description")
            for ex in data
        ]


# ── Dataset Builder ────────────────────────────────────────────────────────


class ToolDatasetBuilder:
    """Two-step synthetic dataset builder for tool selection evaluation.

    Step 1: Analyze tool similarity to identify confuser pairs.
    Step 2: Generate per-tool baseline examples + confuser examples for overlapping pairs.

    Follows the SyntheticDatasetBuilder pattern from evolution/core/dataset_builder.py:
    nested DSPy Signatures, ChainOfThought instances, two-stage JSON parsing.
    """

    class AnalyzeToolSimilarity(dspy.Signature):
        """Identify pairs of tools with overlapping functionality.

        Given summaries of all available tools, find pairs where users might
        reasonably confuse one tool for another due to similar capabilities.
        """
        tool_summaries: str = dspy.InputField(desc="All tools as '- name: description' list")
        confuser_pairs: str = dspy.OutputField(
            desc="JSON array of {\"tools\": [\"tool_a\", \"tool_b\"], \"overlap\": \"description of overlap\"}"
        )

    class GenerateToolTasks(dspy.Signature):
        """Generate realistic user tasks that require a specific tool.

        Create diverse tasks at the specified difficulty level that a user would
        naturally ask, where the given tool is the correct choice.
        """
        tool_name: str = dspy.InputField(desc="Name of the target tool")
        tool_description: str = dspy.InputField(desc="Full description of the target tool")
        all_tools: str = dspy.InputField(desc="List of all available tools for context")
        difficulty: str = dspy.InputField(desc="Difficulty level: easy, medium, or hard")
        num_tasks: int = dspy.InputField(desc="Number of tasks to generate")
        tasks: str = dspy.OutputField(
            desc="JSON array of {\"task_description\": ..., \"correct_params\": {...}, \"confuser_tools\": [...]}"
        )

    class GenerateConfuserTasks(dspy.Signature):
        """Generate tasks where two similar tools could plausibly be confused.

        Create ambiguous tasks where the user's intent could map to either tool,
        but one is definitively correct. These test the agent's ability to
        distinguish between similar tools.
        """
        tool_a_name: str = dspy.InputField(desc="Name of first tool in confuser pair")
        tool_a_description: str = dspy.InputField(desc="Description of first tool")
        tool_b_name: str = dspy.InputField(desc="Name of second tool in confuser pair")
        tool_b_description: str = dspy.InputField(desc="Description of second tool")
        overlap_description: str = dspy.InputField(desc="Description of where the tools overlap")
        num_tasks: int = dspy.InputField(desc="Number of confuser tasks to generate")
        tasks: str = dspy.OutputField(
            desc="JSON array of {\"task_description\": ..., \"correct_tool\": ..., \"correct_params\": {...}, \"reason\": ...}"
        )

    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.similarity_cot = dspy.ChainOfThought(self.AnalyzeToolSimilarity)
        self.tool_tasks_cot = dspy.ChainOfThought(self.GenerateToolTasks)
        self.confuser_tasks_cot = dspy.ChainOfThought(self.GenerateConfuserTasks)

    def _parse_json_array(self, text: str) -> list[dict]:
        """Parse JSON array from LLM output with regex fallback.

        Args:
            text: Raw text potentially containing a JSON array.

        Returns:
            Parsed list of dicts, or empty list on failure.
        """
        # Stage 1: Direct parse
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except (json.JSONDecodeError, TypeError):
            pass

        # Stage 2: Regex extraction fallback
        try:
            match = re.search(r'\[.*\]', text, re.DOTALL)
            if match:
                result = json.loads(match.group())
                if isinstance(result, list):
                    return result
        except (json.JSONDecodeError, TypeError):
            pass

        return []

    def _validate_tool_name(self, name: str, valid_names: list[str]) -> Optional[str]:
        """Map LLM-generated tool name to actual tool name.

        Args:
            name: Tool name from LLM output.
            valid_names: List of known valid tool names.

        Returns:
            Matched tool name, or None if no match found.
        """
        normalized = name.strip().lower()
        for valid in valid_names:
            if valid.strip().lower() == normalized:
                return valid
        return None

    def _ensure_coverage(
        self,
        examples: list[ToolSelectionExample],
        tool_names: list[str],
    ) -> list[str]:
        """Identify tools with fewer than 3 examples.

        Args:
            examples: Current list of generated examples.
            tool_names: All tool names that should have coverage.

        Returns:
            List of tool names with < 3 examples.
        """
        counts: dict[str, int] = {}
        for ex in examples:
            counts[ex.correct_tool] = counts.get(ex.correct_tool, 0) + 1
        return [name for name in tool_names if counts.get(name, 0) < 3]

    def generate(self, tool_descriptions: list) -> ToolSelectionDataset:
        """Generate a tool selection evaluation dataset.

        Two-step process:
        1. Analyze tool similarity to find confuser pairs
        2. Generate per-tool baseline examples + confuser pair examples

        Args:
            tool_descriptions: List of ToolDescription objects from tool_loader.

        Returns:
            ToolSelectionDataset with train/val/holdout splits.
        """
        tool_names = [t.name for t in tool_descriptions]
        tool_map = {t.name: t for t in tool_descriptions}

        # Build tool summary string
        tool_summaries = "\n".join(
            f"- {t.name}: {t.description}" for t in tool_descriptions
        )
        all_tools_str = ", ".join(tool_names)

        lm = dspy.LM(self.config.judge_model, **self.config.get_lm_kwargs())
        all_examples: list[ToolSelectionExample] = []

        with dspy.context(lm=lm):
            # ── Step 1: Analyze tool similarity ──
            console.print("[bold cyan]Step 1:[/] Analyzing tool similarity...")
            sim_result = self.similarity_cot(tool_summaries=tool_summaries)
            confuser_pairs = self._parse_json_array(sim_result.confuser_pairs)
            console.print(f"  Found {len(confuser_pairs)} confuser pair(s)")

            # ── Step 2a: Generate per-tool baseline examples ──
            console.print("[bold cyan]Step 2a:[/] Generating per-tool baseline examples...")
            difficulties = [
                ("easy", 2),    # ~30% easy
                ("medium", 3),  # ~40% medium
                ("hard", 1),    # hard mainly from confusers
            ]

            for tool in tool_descriptions:
                for difficulty, count in difficulties:
                    try:
                        result = self.tool_tasks_cot(
                            tool_name=tool.name,
                            tool_description=tool.description,
                            all_tools=all_tools_str,
                            difficulty=difficulty,
                            num_tasks=count,
                        )
                        tasks = self._parse_json_array(result.tasks)
                        for task in tasks:
                            validated_name = self._validate_tool_name(tool.name, tool_names)
                            if validated_name:
                                all_examples.append(ToolSelectionExample(
                                    task_description=task.get("task_description", ""),
                                    correct_tool=validated_name,
                                    correct_params=task.get("correct_params", {}),
                                    difficulty=difficulty,
                                    confuser_tools=task.get("confuser_tools", []),
                                    source="synthetic",
                                ))
                    except Exception as e:
                        console.print(f"  [yellow]Warning:[/] Failed generating {difficulty} tasks for {tool.name}: {e}")

            console.print(f"  Generated {len(all_examples)} baseline examples")

            # ── Step 2b: Generate confuser tasks ──
            console.print("[bold cyan]Step 2b:[/] Generating confuser tasks...")
            for pair in confuser_pairs:
                pair_tools = pair.get("tools", [])
                if len(pair_tools) != 2:
                    continue

                tool_a_name = self._validate_tool_name(pair_tools[0], tool_names)
                tool_b_name = self._validate_tool_name(pair_tools[1], tool_names)
                if not tool_a_name or not tool_b_name:
                    continue

                tool_a = tool_map.get(tool_a_name)
                tool_b = tool_map.get(tool_b_name)
                if not tool_a or not tool_b:
                    continue

                try:
                    result = self.confuser_tasks_cot(
                        tool_a_name=tool_a.name,
                        tool_a_description=tool_a.description,
                        tool_b_name=tool_b.name,
                        tool_b_description=tool_b.description,
                        overlap_description=pair.get("overlap", ""),
                        num_tasks=7,
                    )
                    tasks = self._parse_json_array(result.tasks)
                    for task in tasks:
                        correct = self._validate_tool_name(
                            task.get("correct_tool", ""), tool_names
                        )
                        if correct:
                            other = tool_b.name if correct == tool_a.name else tool_a.name
                            all_examples.append(ToolSelectionExample(
                                task_description=task.get("task_description", ""),
                                correct_tool=correct,
                                correct_params=task.get("correct_params", {}),
                                difficulty="hard",
                                confuser_tools=[other],
                                reason=task.get("reason", ""),
                                source="synthetic",
                            ))
                except Exception as e:
                    console.print(f"  [yellow]Warning:[/] Failed generating confuser tasks for {pair_tools}: {e}")

            console.print(f"  Total examples after confusers: {len(all_examples)}")

            # ── Step 3: Coverage check and supplementary generation ──
            console.print("[bold cyan]Step 3:[/] Checking per-tool coverage...")
            under_covered = self._ensure_coverage(all_examples, tool_names)
            if under_covered:
                console.print(f"  Supplementing {len(under_covered)} under-covered tool(s): {under_covered}")
                for tool_name in under_covered:
                    tool = tool_map.get(tool_name)
                    if not tool:
                        continue
                    try:
                        result = self.tool_tasks_cot(
                            tool_name=tool.name,
                            tool_description=tool.description,
                            all_tools=all_tools_str,
                            difficulty="medium",
                            num_tasks=3,
                        )
                        tasks = self._parse_json_array(result.tasks)
                        for task in tasks:
                            all_examples.append(ToolSelectionExample(
                                task_description=task.get("task_description", ""),
                                correct_tool=tool.name,
                                correct_params=task.get("correct_params", {}),
                                difficulty="medium",
                                source="synthetic",
                            ))
                    except Exception as e:
                        console.print(f"  [yellow]Warning:[/] Supplementary generation failed for {tool_name}: {e}")

        # Filter out examples with empty task descriptions
        all_examples = [ex for ex in all_examples if ex.task_description.strip()]

        console.print(f"[bold green]Total valid examples:[/] {len(all_examples)}")

        # ── Step 4: Shuffle and split ──
        random.shuffle(all_examples)
        n_total = len(all_examples)
        n_train = max(1, int(n_total * self.config.train_ratio))
        n_val = max(1, int(n_total * self.config.val_ratio))

        return ToolSelectionDataset(
            train=all_examples[:n_train],
            val=all_examples[n_train:n_train + n_val],
            holdout=all_examples[n_train + n_val:],
        )
