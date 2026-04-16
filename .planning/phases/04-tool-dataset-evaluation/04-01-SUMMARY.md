---
phase: 04-tool-dataset-evaluation
plan: 01
status: complete
started: 2026-04-16
completed: 2026-04-16
tasks_completed: 2
tasks_total: 2
---

## Summary

Implemented tool selection data classes and synthetic dataset builder for evaluating tool description evolution.

## What Was Built

**ToolSelectionExample** — Dataclass representing a (task, correct_tool, correct_params) triple with difficulty, confuser tools, reason, and source metadata. Supports round-trip serialization via `to_dict()`/`from_dict()`.

**ToolSelectionDataset** — Train/val/holdout split container with JSONL persistence (`save()`/`load()`) and DSPy Example conversion (`to_dspy_examples()`). Mirrors the EvalDataset pattern from Phase 1.

**ToolDatasetBuilder** — Two-step LLM-based synthetic generator:
1. `AnalyzeToolSimilarity` signature identifies confuser pairs among tools
2. `GenerateToolTasks` generates per-tool baseline examples (easy/medium/hard)
3. `GenerateConfuserTasks` generates hard examples for overlapping tool pairs
4. Coverage check ensures every tool has >= 3 examples
5. Two-stage JSON parsing (direct + regex fallback) for LLM output resilience

## Key Decisions

- Confuser tasks always marked difficulty="hard" per D-07
- Difficulty distribution targets ~30/40/30 (easy/medium/hard) via generation counts per D-08
- Tool name validation via strip().lower() exact match per Pitfall 1
- Default save path: `datasets/tools/selection/`

## Commits

- `8f0c5b5` feat(04-01): add ToolSelectionExample and ToolSelectionDataset data classes
- `46d9320` feat(04-01): add ToolDatasetBuilder with two-step LLM synthesis and confuser generation

## Self-Check

- [x] ToolSelectionExample round-trip serialization
- [x] ToolSelectionDataset save/load JSONL
- [x] ToolSelectionDataset.to_dspy_examples with correct inputs
- [x] ToolDatasetBuilder 3 nested Signature classes
- [x] _validate_tool_name strip().lower() matching
- [x] _ensure_coverage identifies under-covered tools
- [x] _parse_json_array two-stage parsing
- [x] generate() produces dataset with splits
- [x] Confuser tasks have non-empty confuser_tools
- [x] Every tool has >= 3 examples
- [x] All 16 tests pass

## Self-Check: PASSED

## key-files

### created
- evolution/tools/tool_dataset.py
- tests/tools/test_tool_dataset.py
