"""Tests for tool selection dataset classes and builder."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import dspy
import pytest

from evolution.tools.tool_dataset import (
    ToolSelectionExample,
    ToolSelectionDataset,
    ToolDatasetBuilder,
)
from evolution.core.config import EvolutionConfig


# ── ToolSelectionExample Tests ──────────────────────────────────────────────


class TestToolSelectionExample:
    """Tests for ToolSelectionExample dataclass."""

    def test_round_trip_serialization(self):
        """to_dict() then from_dict() preserves all fields."""
        ex = ToolSelectionExample(
            task_description="Search for files matching a pattern",
            correct_tool="glob_search",
            correct_params={"pattern": "*.py", "recursive": True},
            difficulty="hard",
            confuser_tools=["file_search", "grep"],
            reason="glob_search handles glob patterns natively",
            source="synthetic",
        )
        d = ex.to_dict()
        restored = ToolSelectionExample.from_dict(d)
        assert restored.task_description == ex.task_description
        assert restored.correct_tool == ex.correct_tool
        assert restored.correct_params == ex.correct_params
        assert restored.difficulty == ex.difficulty
        assert restored.confuser_tools == ex.confuser_tools
        assert restored.reason == ex.reason
        assert restored.source == ex.source

    def test_from_dict_ignores_unknown_keys(self):
        """from_dict gracefully ignores keys not in the dataclass."""
        d = {
            "task_description": "Do something",
            "correct_tool": "terminal",
            "extra_field": "should be ignored",
            "another_unknown": 42,
        }
        ex = ToolSelectionExample.from_dict(d)
        assert ex.task_description == "Do something"
        assert ex.correct_tool == "terminal"
        assert not hasattr(ex, "extra_field")

    def test_defaults(self):
        """Default values are set correctly."""
        ex = ToolSelectionExample(
            task_description="test",
            correct_tool="memory",
        )
        assert ex.correct_params == {}
        assert ex.difficulty == "medium"
        assert ex.confuser_tools == []
        assert ex.reason == ""
        assert ex.source == "synthetic"


# ── ToolSelectionDataset Tests ──────────────────────────────────────────────


class TestToolSelectionDataset:
    """Tests for ToolSelectionDataset dataclass."""

    def _make_examples(self, n: int) -> list[ToolSelectionExample]:
        """Helper to create n examples."""
        return [
            ToolSelectionExample(
                task_description=f"Task {i}",
                correct_tool=f"tool_{i}",
                correct_params={"key": f"val_{i}"},
                difficulty=["easy", "medium", "hard"][i % 3],
            )
            for i in range(n)
        ]

    def test_save_creates_three_jsonl_files(self, tmp_path):
        """save() writes train.jsonl, val.jsonl, holdout.jsonl."""
        ds = ToolSelectionDataset(
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
        ds = ToolSelectionDataset(
            train=self._make_examples(4),
            val=self._make_examples(2),
            holdout=self._make_examples(1),
        )
        ds.save(tmp_path / "dataset")
        loaded = ToolSelectionDataset.load(tmp_path / "dataset")

        assert len(loaded.train) == 4
        assert len(loaded.val) == 2
        assert len(loaded.holdout) == 1

        # Check content
        for orig, restored in zip(ds.train, loaded.train):
            assert orig.task_description == restored.task_description
            assert orig.correct_tool == restored.correct_tool
            assert orig.correct_params == restored.correct_params

    def test_to_dspy_examples(self):
        """to_dspy_examples returns dspy.Example with correct inputs."""
        ds = ToolSelectionDataset(
            train=self._make_examples(3),
            val=[],
            holdout=[],
        )
        dspy_examples = ds.to_dspy_examples("train")
        assert len(dspy_examples) == 3
        # Check that task_description is an input and correct_tool is available
        ex = dspy_examples[0]
        assert hasattr(ex, "task_description")
        assert hasattr(ex, "correct_tool")
        # task_description should be in inputs
        assert "task_description" in ex.inputs()

    def test_all_examples(self):
        """all_examples returns concatenation of all splits."""
        ds = ToolSelectionDataset(
            train=self._make_examples(3),
            val=self._make_examples(2),
            holdout=self._make_examples(1),
        )
        all_ex = ds.all_examples
        assert len(all_ex) == 6


# ── ToolDatasetBuilder Tests ────────────────────────────────────────────────


class TestToolDatasetBuilder:
    """Tests for ToolDatasetBuilder class."""

    def _make_config(self) -> EvolutionConfig:
        return EvolutionConfig(
            judge_model="openai/gpt-4.1",
            train_ratio=0.5,
            val_ratio=0.25,
            holdout_ratio=0.25,
        )

    def test_init_creates_chain_of_thought_instances(self):
        """Constructor creates ChainOfThought for all 3 Signatures."""
        config = self._make_config()
        builder = ToolDatasetBuilder(config)
        assert builder.similarity_cot is not None
        assert builder.tool_tasks_cot is not None
        assert builder.confuser_tasks_cot is not None

    def test_validate_tool_name_exact_match(self):
        """_validate_tool_name matches via strip().lower()."""
        config = self._make_config()
        builder = ToolDatasetBuilder(config)
        valid = ["memory", "terminal", "browser_navigate"]

        assert builder._validate_tool_name("memory", valid) == "memory"
        assert builder._validate_tool_name("  Memory  ", valid) == "memory"
        assert builder._validate_tool_name("TERMINAL", valid) == "terminal"
        assert builder._validate_tool_name("nonexistent", valid) is None

    def test_ensure_coverage(self):
        """_ensure_coverage identifies tools with < 3 examples."""
        config = self._make_config()
        builder = ToolDatasetBuilder(config)
        examples = [
            ToolSelectionExample(task_description=f"t{i}", correct_tool="memory")
            for i in range(5)
        ] + [
            ToolSelectionExample(task_description="t_term", correct_tool="terminal"),
        ]
        tool_names = ["memory", "terminal", "browser"]
        under = builder._ensure_coverage(examples, tool_names)
        assert "terminal" in under
        assert "browser" in under
        assert "memory" not in under

    def test_parse_json_array_direct(self):
        """_parse_json_array parses clean JSON array."""
        config = self._make_config()
        builder = ToolDatasetBuilder(config)
        text = '[{"a": 1}, {"b": 2}]'
        result = builder._parse_json_array(text)
        assert len(result) == 2
        assert result[0]["a"] == 1

    def test_parse_json_array_with_surrounding_text(self):
        """_parse_json_array uses regex fallback for wrapped JSON."""
        config = self._make_config()
        builder = ToolDatasetBuilder(config)
        text = 'Here are the results:\n[{"a": 1}]\nDone.'
        result = builder._parse_json_array(text)
        assert len(result) == 1

    def test_parse_json_array_empty_fallback(self):
        """_parse_json_array returns empty list on unparseable text."""
        config = self._make_config()
        builder = ToolDatasetBuilder(config)
        result = builder._parse_json_array("not json at all")
        assert result == []

    def test_generate_produces_dataset_with_splits(self):
        """generate() returns ToolSelectionDataset with correct split ratios."""
        from evolution.tools.tool_loader import ToolDescription

        tools = [
            ToolDescription(name=f"tool_{i}", file_path=Path(f"/fake/tool_{i}.py"),
                            description=f"Tool {i} does thing {i}")
            for i in range(5)
        ]

        config = self._make_config()
        builder = ToolDatasetBuilder(config)

        # Mock similarity analysis
        sim_result = MagicMock()
        sim_result.confuser_pairs = json.dumps([
            {"tools": ["tool_0", "tool_1"], "overlap": "both do similar things"},
        ])
        builder.similarity_cot = MagicMock(return_value=sim_result)

        def tool_task_side_effect(**kwargs):
            result = MagicMock()
            tool_name = kwargs.get("tool_name", "unknown")
            difficulty = kwargs.get("difficulty", "medium")
            num = kwargs.get("num_tasks", 3)
            result.tasks = json.dumps([
                {
                    "task_description": f"Do {difficulty} task {j} with {tool_name}",
                    "correct_params": {"key": "val"},
                    "confuser_tools": [],
                }
                for j in range(num)
            ])
            return result

        builder.tool_tasks_cot = MagicMock(side_effect=tool_task_side_effect)

        conf_result = MagicMock()
        conf_result.tasks = json.dumps([
            {
                "task_description": f"Ambiguous task {i} between tool_0 and tool_1",
                "correct_tool": "tool_0",
                "correct_params": {"key": "val"},
                "reason": "tool_0 is better because...",
            }
            for i in range(5)
        ])
        builder.confuser_tasks_cot = MagicMock(return_value=conf_result)

        with patch("dspy.LM"), patch("dspy.context") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=None)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            dataset = builder.generate(tools)

        assert isinstance(dataset, ToolSelectionDataset)
        total = len(dataset.all_examples)
        assert total > 0

        # Check split ratios approximately 50/25/25
        if total >= 4:
            train_ratio = len(dataset.train) / total
            assert 0.35 <= train_ratio <= 0.65, f"Train ratio {train_ratio} outside expected range"

    def test_generate_confuser_tasks_have_confuser_tools(self):
        """Confuser tasks have non-empty confuser_tools field."""
        from evolution.tools.tool_loader import ToolDescription

        tools = [
            ToolDescription(name=f"tool_{i}", file_path=Path(f"/fake/tool_{i}.py"),
                            description=f"Tool {i} does thing {i}")
            for i in range(3)
        ]

        config = self._make_config()
        builder = ToolDatasetBuilder(config)

        sim_result = MagicMock()
        sim_result.confuser_pairs = json.dumps([
            {"tools": ["tool_0", "tool_1"], "overlap": "overlap desc"},
        ])
        builder.similarity_cot = MagicMock(return_value=sim_result)

        def tool_task_side_effect(**kwargs):
            result = MagicMock()
            num = kwargs.get("num_tasks", 3)
            result.tasks = json.dumps([
                {"task_description": f"task {j}", "correct_params": {}, "confuser_tools": []}
                for j in range(num)
            ])
            return result
        builder.tool_tasks_cot = MagicMock(side_effect=tool_task_side_effect)

        conf_result = MagicMock()
        conf_result.tasks = json.dumps([
            {
                "task_description": f"confuser task {i}",
                "correct_tool": "tool_0",
                "correct_params": {},
                "reason": "tool_0 is correct because...",
            }
            for i in range(5)
        ])
        builder.confuser_tasks_cot = MagicMock(return_value=conf_result)

        with patch("dspy.LM"), patch("dspy.context") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=None)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            dataset = builder.generate(tools)

        confuser_examples = [ex for ex in dataset.all_examples if ex.confuser_tools]
        assert len(confuser_examples) > 0, "Should have confuser examples"
        for ex in confuser_examples:
            assert len(ex.confuser_tools) > 0

    def test_generate_every_tool_has_minimum_examples(self):
        """Every tool appears in at least 3 examples."""
        from evolution.tools.tool_loader import ToolDescription

        tools = [
            ToolDescription(name=f"tool_{i}", file_path=Path(f"/fake/tool_{i}.py"),
                            description=f"Tool {i} does thing {i}")
            for i in range(4)
        ]

        config = self._make_config()
        builder = ToolDatasetBuilder(config)

        sim_result = MagicMock()
        sim_result.confuser_pairs = json.dumps([])
        builder.similarity_cot = MagicMock(return_value=sim_result)

        def tool_task_side_effect(**kwargs):
            result = MagicMock()
            num = kwargs.get("num_tasks", 3)
            result.tasks = json.dumps([
                {"task_description": f"task {j}", "correct_params": {}, "confuser_tools": []}
                for j in range(num)
            ])
            return result
        builder.tool_tasks_cot = MagicMock(side_effect=tool_task_side_effect)
        builder.confuser_tasks_cot = MagicMock()

        with patch("dspy.LM"), patch("dspy.context") as mock_ctx:
            mock_ctx.return_value.__enter__ = MagicMock(return_value=None)
            mock_ctx.return_value.__exit__ = MagicMock(return_value=False)
            dataset = builder.generate(tools)

        tool_counts = {}
        for ex in dataset.all_examples:
            tool_counts[ex.correct_tool] = tool_counts.get(ex.correct_tool, 0) + 1

        for tool in tools:
            count = tool_counts.get(tool.name, 0)
            assert count >= 3, f"Tool {tool.name} has only {count} examples (need >= 3)"
