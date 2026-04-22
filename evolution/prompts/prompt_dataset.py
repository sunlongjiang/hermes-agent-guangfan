"""Prompt behavioral dataset classes and synthetic builder.

Provides data structures for prompt behavioral evaluation examples
(section_id -> user_message -> expected_behavior) and a per-section
weighted scenario generator using DSPy ChainOfThought.

Classes:
    PromptBehavioralExample -- single behavioral test scenario for a prompt section
    PromptBehavioralDataset -- train/val/holdout split collection with JSONL persistence
    PromptDatasetBuilder   -- per-section weighted synthetic generation via DSPy
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
from evolution.prompts.prompt_loader import PromptSection

console = Console()


# ── Data Classes ────────────────────────────────────────────────────────────


@dataclass
class PromptBehavioralExample:
    """A single prompt behavioral evaluation example.

    Represents a scenario that tests whether an agent following a prompt
    section's guidance exhibits correct behavior.

    Args:
        section_id: Which section this scenario tests (e.g. "memory_guidance").
        user_message: Simulated user input.
        expected_behavior: Rubric describing correct agent behavior.
        difficulty: One of 'easy', 'medium', 'hard'.
        source: Provenance: 'synthetic', 'golden'.
    """
    section_id: str
    user_message: str
    expected_behavior: str
    difficulty: str = "medium"
    source: str = "synthetic"

    def to_dict(self) -> dict:
        """Serialize all fields to a dict."""
        return {
            "section_id": self.section_id,
            "user_message": self.user_message,
            "expected_behavior": self.expected_behavior,
            "difficulty": self.difficulty,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PromptBehavioralExample":
        """Deserialize from dict, ignoring unknown keys."""
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PromptBehavioralDataset:
    """Train/val/holdout split of prompt behavioral examples.

    Mirrors the ToolSelectionDataset pattern from evolution/tools/tool_dataset.py,
    with JSONL persistence and DSPy Example conversion.
    """
    train: list[PromptBehavioralExample] = field(default_factory=list)
    val: list[PromptBehavioralExample] = field(default_factory=list)
    holdout: list[PromptBehavioralExample] = field(default_factory=list)

    @property
    def all_examples(self) -> list[PromptBehavioralExample]:
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
    def load(cls, path: Path) -> "PromptBehavioralDataset":
        """Load dataset splits from JSONL files.

        Args:
            path: Directory containing train.jsonl, val.jsonl, holdout.jsonl.

        Returns:
            PromptBehavioralDataset with loaded examples.
        """
        dataset = cls()
        for split_name in ["train", "val", "holdout"]:
            split_file = path / f"{split_name}.jsonl"
            if split_file.exists():
                examples = []
                with open(split_file) as f:
                    for line in f:
                        if line.strip():
                            examples.append(PromptBehavioralExample.from_dict(json.loads(line)))
                setattr(dataset, split_name, examples)
        return dataset

    def to_dspy_examples(
        self,
        split: str = "train",
        section_texts: Optional[dict[str, str]] = None,
    ) -> list[dspy.Example]:
        """Convert a split to DSPy Example objects.

        Maps user_message -> task_input, expected_behavior -> expected_behavior.
        Optionally injects section_text from a section_texts lookup dict.

        Args:
            split: Which split to convert ('train', 'val', or 'holdout').
            section_texts: Optional dict mapping section_id -> section text.
                If provided and the example's section_id is found, adds a
                section_text field to the DSPy Example.

        Returns:
            List of dspy.Example instances with task_input as input.
        """
        data = getattr(self, split)
        examples = []
        for ex in data:
            fields = {
                "task_input": ex.user_message,
                "expected_behavior": ex.expected_behavior,
            }
            if section_texts and ex.section_id in section_texts:
                fields["section_text"] = section_texts[ex.section_id]
            examples.append(dspy.Example(**fields).with_inputs("task_input"))
        return examples


# ── Dataset Builder ────────────────────────────────────────────────────────


class PromptDatasetBuilder:
    """Per-section weighted synthetic dataset builder for prompt evaluation.

    Generates behavioral test scenarios for each prompt section using
    DSPy ChainOfThought, with scenario counts weighted by section importance
    per D2 allocation.

    Follows the ToolDatasetBuilder pattern from evolution/tools/tool_dataset.py:
    nested DSPy Signature, ChainOfThought predictor, two-stage JSON parsing.
    """

    # D2 weighted scenario allocation (total = 80)
    SECTION_WEIGHTS: dict[str, int] = {
        "default_agent_identity": 20,
        "memory_guidance": 15,
        "skills_guidance": 15,
        "platform_hints": 20,
        "session_search_guidance": 10,
    }

    class GenerateSectionScenarios(dspy.Signature):
        """Generate behavioral test scenarios for a prompt section.

        Given a prompt section's text, generate realistic scenarios that test
        whether an agent following this guidance exhibits correct behavior.
        """
        section_text: str = dspy.InputField(desc="The prompt section text being tested")
        section_id: str = dspy.InputField(desc="Section identifier (e.g. 'memory_guidance')")
        num_scenarios: int = dspy.InputField(desc="Number of scenarios to generate")
        difficulty_mix: str = dspy.InputField(
            desc="Target difficulty distribution, e.g. 'easy:30%,medium:50%,hard:20%'"
        )
        scenarios: str = dspy.OutputField(
            desc="JSON array of {user_message, expected_behavior, difficulty}"
        )

    def __init__(self, config: EvolutionConfig):
        self.config = config
        self.generator = dspy.ChainOfThought(self.GenerateSectionScenarios)

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

    def _compute_section_targets(
        self, sections: list[PromptSection],
    ) -> dict[str, int]:
        """Compute per-section scenario counts from D2 weights.

        Platform hint sections share the "platform_hints" weight, divided
        evenly with remainder distributed to first keys.

        Args:
            sections: List of PromptSection objects.

        Returns:
            Dict mapping section_id -> target scenario count.
        """
        targets: dict[str, int] = {}
        platform_sections = []

        for section in sections:
            if section.section_id.startswith("platform_hints."):
                platform_sections.append(section.section_id)
            elif section.section_id in self.SECTION_WEIGHTS:
                targets[section.section_id] = self.SECTION_WEIGHTS[section.section_id]

        # Spread platform_hints weight across platform sub-keys
        if platform_sections:
            total_platform = self.SECTION_WEIGHTS.get("platform_hints", 20)
            per_key = total_platform // len(platform_sections)
            remainder = total_platform % len(platform_sections)
            for i, sid in enumerate(platform_sections):
                targets[sid] = per_key + (1 if i < remainder else 0)

        return targets

    def generate(self, sections: list[PromptSection]) -> PromptBehavioralDataset:
        """Generate a prompt behavioral evaluation dataset.

        Per-section weighted generation following D2 allocation:
        identity=20, memory=15, skills=15, platform=20 (split), session=10.

        Args:
            sections: List of PromptSection objects from prompt_loader.

        Returns:
            PromptBehavioralDataset with train/val/holdout splits.
        """
        targets = self._compute_section_targets(sections)
        section_map = {s.section_id: s for s in sections}

        lm = dspy.LM(self.config.judge_model, **self.config.get_lm_kwargs())
        all_examples: list[PromptBehavioralExample] = []

        with dspy.context(lm=lm):
            for section_id, target_count in targets.items():
                section = section_map.get(section_id)
                if not section:
                    console.print(f"  [yellow]Warning:[/] Section {section_id} not found, skipping")
                    continue

                console.print(
                    f"[bold cyan]Generating[/] {target_count} scenarios "
                    f"for [green]{section_id}[/]..."
                )

                try:
                    result = self.generator(
                        section_text=section.text,
                        section_id=section_id,
                        num_scenarios=target_count,
                        difficulty_mix="easy:30%,medium:50%,hard:20%",
                    )
                    scenarios = self._parse_json_array(result.scenarios)
                    for scenario in scenarios:
                        all_examples.append(PromptBehavioralExample(
                            section_id=section_id,
                            user_message=scenario.get("user_message", ""),
                            expected_behavior=scenario.get("expected_behavior", ""),
                            difficulty=scenario.get("difficulty", "medium"),
                            source="synthetic",
                        ))
                except Exception as e:
                    console.print(
                        f"  [yellow]Warning:[/] Failed generating scenarios "
                        f"for {section_id}: {e}"
                    )

        # Filter out examples with empty user messages
        all_examples = [ex for ex in all_examples if ex.user_message.strip()]

        console.print(f"[bold green]Total valid examples:[/] {len(all_examples)}")

        # Shuffle and split
        random.shuffle(all_examples)
        n_total = len(all_examples)
        n_train = max(1, int(n_total * self.config.train_ratio))
        n_val = max(1, int(n_total * self.config.val_ratio))

        return PromptBehavioralDataset(
            train=all_examples[:n_train],
            val=all_examples[n_train:n_train + n_val],
            holdout=all_examples[n_train + n_val:],
        )
