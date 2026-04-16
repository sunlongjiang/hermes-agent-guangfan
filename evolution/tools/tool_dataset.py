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
