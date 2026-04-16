"""Tests for tool selection dataset classes and builder."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import dspy
import pytest

from evolution.tools.tool_dataset import (
    ToolSelectionExample,
    ToolSelectionDataset,
)


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
