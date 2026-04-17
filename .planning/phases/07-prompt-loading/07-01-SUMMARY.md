---
phase: 07-prompt-loading
plan: 01
subsystem: prompts
tags: [ast-parsing, prompt-extraction, write-back, tdd]
dependency_graph:
  requires: []
  provides: [PromptSection, extract_prompt_sections, write_back_section]
  affects: [evolution/prompts/]
tech_stack:
  added: []
  patterns: [ast-parse-walk, line-level-replacement, paren-concat-formatting]
key_files:
  created:
    - evolution/prompts/prompt_loader.py
    - tests/prompts/__init__.py
    - tests/prompts/test_prompt_loader.py
  modified:
    - evolution/prompts/__init__.py
decisions:
  - Used Assign node line_range for str constants, Constant node line_range for dict values (per Pitfall 2)
  - _split_text_lines at 70-char width for str assignments, 60-char for dict values
  - _escape_str handles backslash, double-quote, newline, tab
metrics:
  duration: 27min
  completed: 2026-04-17T12:32:19Z
  tasks_completed: 2
  tasks_total: 2
  test_count: 9
  files_changed: 4
---

# Phase 7 Plan 1: Prompt Section Extraction and Write-Back Summary

AST-based extraction of 13 prompt sections (4 str constants + 9 PLATFORM_HINTS keys) from prompt_builder.py with format-preserving parenthesized-concat write-back.

## What Was Built

### PromptSection Dataclass and Extraction (Task 1)
- `PromptSection` dataclass with `section_id`, `text`, `char_count`, `line_range`, `source_path` plus `to_dict()`/`from_dict()` serialization
- `extract_prompt_sections()` uses `ast.parse()` + `ast.walk()` to find 4 `TARGET_STR_VARS` and expand `PLATFORM_HINTS` dict into 9 independent sections
- Sections sorted by `line_range[0]` for deterministic order
- 4 str section IDs: `default_agent_identity`, `memory_guidance`, `session_search_guidance`, `skills_guidance`
- 9 platform hint IDs: `platform_hints.{whatsapp,telegram,discord,slack,signal,email,cron,cli,sms}`

### Write-Back (Task 2)
- `write_back_section()` determines section type from `section_id` prefix, formats replacement text, and does line-level replacement
- `_format_paren_concat()` produces `VAR_NAME = (\n    "line"\n)` format for str assignments
- `_format_dict_value_paren_concat()` produces indented string lines for dict values
- `_split_text_lines()` splits at word boundaries (~70 char for str, ~60 for dict)
- `_escape_str()` handles backslash, double-quote, newline, tab in evolved text

### Tests (9 total)
- 4 extraction tests: count, metadata, str IDs, platform hints expansion
- 5 write-back tests: str round-trip, platform hint round-trip, py_compile validation, isolation, multiple sequential write-backs

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | 209d476 | PromptSection dataclass and extract_prompt_sections |
| 2 | ec105aa | write_back_section with round-trip tests |

## Deviations from Plan

None -- plan executed exactly as written.

## Decisions Made

1. **Assign vs Constant line_range**: Str constants use Assign node's `lineno/end_lineno` (covers full `VAR = (...)` block); dict values use Constant node's `lineno/end_lineno` (covers only string content, not key line)
2. **Line width split**: 70 chars for top-level str assignments, 60 chars for dict values (narrower due to deeper indent)
3. **String escaping**: Handles `\`, `"`, `\n`, `\t` -- sufficient for prompt text evolution

## Verification Results

- `python -m pytest tests/prompts/test_prompt_loader.py -x -v`: 9/9 passed
- `python -m pytest tests/ -x -q`: 255/255 passed (full suite green)
- `python -c "from evolution.prompts.prompt_loader import PromptSection, extract_prompt_sections, write_back_section"`: imports OK

## Self-Check: PASSED

All 5 files found. Both commits (209d476, ec105aa) verified in git log.
