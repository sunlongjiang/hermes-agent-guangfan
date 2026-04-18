"""Tests for prompt behavioral dataset classes and builder."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import dspy
import pytest

from evolution.prompts.prompt_dataset import (
    PromptBehavioralExample,
    PromptBehavioralDataset,
    PromptDatasetBuilder,
)
from evolution.core.config import EvolutionConfig


# ── PromptBehavioralExample Tests ──────────────────────────────────────────


class TestPromptBehavioralExample:
    """Tests for PromptBehavioralExample dataclass."""

    def test_round_trip_serialization(self):
        """to_dict() then from_dict() preserves all fields."""
        ex = PromptBehavioralExample(
            section_id="memory_guidance",
            user_message="How do I save a preference?",
            expected_behavior="Agent should use memory tool to persist preference",
            difficulty="hard",
            source="golden",
        )
        d = ex.to_dict()
        restored = PromptBehavioralExample.from_dict(d)
        assert restored.section_id == ex.section_id
        assert restored.user_message == ex.user_message
        assert restored.expected_behavior == ex.expected_behavior
        assert restored.difficulty == ex.difficulty
        assert restored.source == ex.source

    def test_defaults(self):
        """Default values are set correctly."""
        ex = PromptBehavioralExample(
            section_id="skills_guidance",
            user_message="test message",
            expected_behavior="test behavior",
        )
        assert ex.difficulty == "medium"
        assert ex.source == "synthetic"

    def test_from_dict_ignores_unknown_keys(self):
        """from_dict gracefully ignores keys not in the dataclass."""
        d = {
            "section_id": "memory_guidance",
            "user_message": "test",
            "expected_behavior": "test behavior",
            "extra_field": "should be ignored",
            "another_unknown": 42,
        }
        ex = PromptBehavioralExample.from_dict(d)
        assert ex.section_id == "memory_guidance"
        assert ex.user_message == "test"
        assert not hasattr(ex, "extra_field")

    def test_to_dict_contains_all_fields(self):
        """to_dict() includes all five fields."""
        ex = PromptBehavioralExample(
            section_id="default_agent_identity",
            user_message="Who are you?",
            expected_behavior="Should identify as Hermes",
            difficulty="easy",
            source="synthetic",
        )
        d = ex.to_dict()
        assert set(d.keys()) == {
            "section_id", "user_message", "expected_behavior",
            "difficulty", "source",
        }


# ── PromptBehavioralDataset Tests ──────────────────────────────────────────


class TestPromptBehavioralDataset:
    """Tests for PromptBehavioralDataset dataclass."""

    def _make_examples(self, n: int, section_id: str = "memory_guidance") -> list:
        """Helper to create n examples."""
        return [
            PromptBehavioralExample(
                section_id=section_id,
                user_message=f"Message {i}",
                expected_behavior=f"Behavior {i}",
                difficulty=["easy", "medium", "hard"][i % 3],
            )
            for i in range(n)
        ]

    def test_save_creates_three_jsonl_files(self, tmp_path):
        """save() writes train.jsonl, val.jsonl, holdout.jsonl."""
        ds = PromptBehavioralDataset(
            train=self._make_examples(3),
            val=self._make_examples(2),
            holdout=self._make_examples(1),
        )
        ds.save(tmp_path / "dataset")
        assert (tmp_path / "dataset" / "train.jsonl").exists()
        assert (tmp_path / "dataset" / "val.jsonl").exists()
        assert (tmp_path / "dataset" / "holdout.jsonl").exists()

        # Check line counts
        train_lines = (tmp_path / "dataset" / "train.jsonl").read_text().strip().split("\n")
        assert len(train_lines) == 3

    def test_save_load_round_trip(self, tmp_path):
        """Load reads back saved JSONL and produces identical examples."""
        ds = PromptBehavioralDataset(
            train=self._make_examples(4),
            val=self._make_examples(2),
            holdout=self._make_examples(1),
        )
        ds.save(tmp_path / "dataset")
        loaded = PromptBehavioralDataset.load(tmp_path / "dataset")

        assert len(loaded.train) == 4
        assert len(loaded.val) == 2
        assert len(loaded.holdout) == 1

        # Check content preservation
        for orig, restored in zip(ds.train, loaded.train):
            assert orig.section_id == restored.section_id
            assert orig.user_message == restored.user_message
            assert orig.expected_behavior == restored.expected_behavior
            assert orig.difficulty == restored.difficulty

    def test_all_examples(self):
        """all_examples returns concatenation of all splits."""
        ds = PromptBehavioralDataset(
            train=self._make_examples(3),
            val=self._make_examples(2),
            holdout=self._make_examples(1),
        )
        all_ex = ds.all_examples
        assert len(all_ex) == 6

    def test_to_dspy_examples_basic(self):
        """to_dspy_examples returns dspy.Example with task_input as input."""
        ds = PromptBehavioralDataset(
            train=self._make_examples(3),
            val=[],
            holdout=[],
        )
        dspy_examples = ds.to_dspy_examples("train")
        assert len(dspy_examples) == 3
        ex = dspy_examples[0]
        assert hasattr(ex, "task_input")
        assert hasattr(ex, "expected_behavior")
        assert "task_input" in ex.inputs()

    def test_to_dspy_examples_with_section_texts(self):
        """to_dspy_examples injects section_text from section_texts dict."""
        ds = PromptBehavioralDataset(
            train=self._make_examples(2, section_id="memory_guidance"),
            val=[],
            holdout=[],
        )
        section_texts = {
            "memory_guidance": "You should save important user preferences.",
        }
        dspy_examples = ds.to_dspy_examples("train", section_texts=section_texts)
        assert len(dspy_examples) == 2
        ex = dspy_examples[0]
        assert hasattr(ex, "section_text")
        assert ex.section_text == "You should save important user preferences."

    def test_to_dspy_examples_without_section_texts(self):
        """to_dspy_examples without section_texts omits section_text field."""
        ds = PromptBehavioralDataset(
            train=self._make_examples(2),
            val=[],
            holdout=[],
        )
        dspy_examples = ds.to_dspy_examples("train")
        ex = dspy_examples[0]
        # section_text should NOT be present when no section_texts provided
        assert not hasattr(ex, "section_text")


# ── PromptDatasetBuilder Tests ─────────────────────────────────────────────


class TestPromptDatasetBuilder:
    """Tests for PromptDatasetBuilder class."""

    def _make_config(self) -> EvolutionConfig:
        return EvolutionConfig(
            judge_model="openai/gpt-4.1",
            train_ratio=0.5,
            val_ratio=0.25,
            holdout_ratio=0.25,
        )

    def _make_sections(self):
        """Create mock PromptSection objects for all 5 categories."""
        from evolution.prompts.prompt_loader import PromptSection

        sections = [
            PromptSection(
                section_id="default_agent_identity",
                text="You are Hermes, a helpful AI assistant.",
                char_count=40,
                line_range=(1, 10),
                source_path=Path("/fake/prompt_builder.py"),
            ),
            PromptSection(
                section_id="memory_guidance",
                text="Save important user preferences to memory.",
                char_count=43,
                line_range=(11, 20),
                source_path=Path("/fake/prompt_builder.py"),
            ),
            PromptSection(
                section_id="skills_guidance",
                text="Use skills when the user asks for help.",
                char_count=40,
                line_range=(21, 30),
                source_path=Path("/fake/prompt_builder.py"),
            ),
            PromptSection(
                section_id="platform_hints.whatsapp",
                text="WhatsApp platform hints.",
                char_count=24,
                line_range=(31, 35),
                source_path=Path("/fake/prompt_builder.py"),
            ),
            PromptSection(
                section_id="platform_hints.telegram",
                text="Telegram platform hints.",
                char_count=24,
                line_range=(36, 40),
                source_path=Path("/fake/prompt_builder.py"),
            ),
            PromptSection(
                section_id="session_search_guidance",
                text="Search sessions for relevant context.",
                char_count=37,
                line_range=(41, 50),
                source_path=Path("/fake/prompt_builder.py"),
            ),
        ]
        return sections

    def test_section_weights_exist(self):
        """SECTION_WEIGHTS class constant has expected keys and values."""
        assert hasattr(PromptDatasetBuilder, "SECTION_WEIGHTS")
        weights = PromptDatasetBuilder.SECTION_WEIGHTS
        assert weights["default_agent_identity"] == 20
        assert weights["memory_guidance"] == 15
        assert weights["skills_guidance"] == 15
        assert weights["platform_hints"] == 20
        assert weights["session_search_guidance"] == 10

    def test_init_creates_chain_of_thought(self):
        """Constructor creates ChainOfThought predictor."""
        config = self._make_config()
        builder = PromptDatasetBuilder(config)
        assert builder.generator is not None

    def test_generate_produces_correct_per_section_counts(self):
        """generate() with mocked LLM produces correct per-section scenario counts.

        D2 weights: identity=20, memory=15, skills=15, platform=20 (split across 2 keys),
        session=10. Total = 80.
        """
        config = self._make_config()
        builder = PromptDatasetBuilder(config)
        sections = self._make_sections()

        # Track calls per section_id to verify correct counts
        call_log = []

        def generator_side_effect(**kwargs):
            section_id = kwargs.get("section_id", "")
            num_scenarios = kwargs.get("num_scenarios", 0)
            call_log.append({"section_id": section_id, "num_scenarios": num_scenarios})
            result = MagicMock()
            scenarios = [
                {
                    "user_message": f"Scenario {i} for {section_id}",
                    "expected_behavior": f"Expected behavior {i}",
                    "difficulty": ["easy", "medium", "hard"][i % 3],
                }
                for i in range(num_scenarios)
            ]
            result.scenarios = json.dumps(scenarios)
            return result

        builder.generator = MagicMock(side_effect=generator_side_effect)

        with patch("dspy.LM"), patch("dspy.context") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=None)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            dataset = builder.generate(sections)

        assert isinstance(dataset, PromptBehavioralDataset)

        # Count examples per section
        section_counts = {}
        for ex in dataset.all_examples:
            section_counts[ex.section_id] = section_counts.get(ex.section_id, 0) + 1

        # Verify D2 weighted counts
        assert section_counts.get("default_agent_identity", 0) == 20
        assert section_counts.get("memory_guidance", 0) == 15
        assert section_counts.get("skills_guidance", 0) == 15
        assert section_counts.get("session_search_guidance", 0) == 10

        # Platform hints: 20 total split across 2 keys (10 each)
        platform_total = (
            section_counts.get("platform_hints.whatsapp", 0)
            + section_counts.get("platform_hints.telegram", 0)
        )
        assert platform_total == 20

        # Total should be 80
        total = len(dataset.all_examples)
        assert total == 80

    def test_generate_split_ratios(self):
        """Generated dataset has approximately 50/25/25 split ratios."""
        config = self._make_config()
        builder = PromptDatasetBuilder(config)
        sections = self._make_sections()

        def generator_side_effect(**kwargs):
            num = kwargs.get("num_scenarios", 5)
            section_id = kwargs.get("section_id", "")
            result = MagicMock()
            result.scenarios = json.dumps([
                {
                    "user_message": f"Scenario {i}",
                    "expected_behavior": f"Behavior {i}",
                    "difficulty": "medium",
                }
                for i in range(num)
            ])
            return result

        builder.generator = MagicMock(side_effect=generator_side_effect)

        with patch("dspy.LM"), patch("dspy.context") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=None)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            dataset = builder.generate(sections)

        total = len(dataset.all_examples)
        assert total > 0

        # Check 50/25/25 split within tolerance
        train_ratio = len(dataset.train) / total
        val_ratio = len(dataset.val) / total
        assert 0.40 <= train_ratio <= 0.60, f"Train ratio {train_ratio} outside expected range"
        assert 0.15 <= val_ratio <= 0.35, f"Val ratio {val_ratio} outside expected range"

    def test_generate_filters_empty_user_messages(self):
        """generate() filters out examples with empty user_message."""
        config = self._make_config()
        builder = PromptDatasetBuilder(config)

        from evolution.prompts.prompt_loader import PromptSection
        sections = [
            PromptSection(
                section_id="memory_guidance",
                text="Save preferences.",
                char_count=17,
                line_range=(1, 5),
                source_path=Path("/fake/prompt_builder.py"),
            ),
        ]

        def generator_side_effect(**kwargs):
            result = MagicMock()
            result.scenarios = json.dumps([
                {"user_message": "Valid message", "expected_behavior": "Valid behavior", "difficulty": "easy"},
                {"user_message": "", "expected_behavior": "Should be filtered", "difficulty": "medium"},
                {"user_message": "   ", "expected_behavior": "Also filtered", "difficulty": "hard"},
            ])
            return result

        builder.generator = MagicMock(side_effect=generator_side_effect)

        with patch("dspy.LM"), patch("dspy.context") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=None)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            dataset = builder.generate(sections)

        # Only the valid message should remain
        for ex in dataset.all_examples:
            assert ex.user_message.strip() != ""
