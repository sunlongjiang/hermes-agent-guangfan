# Testing Patterns

**Analysis Date:** 2026-05-06

## Test Framework

**Runner:**
- pytest >=7.0 (declared in `pyproject.toml:27`)
- Config: `[tool.pytest.ini_options]` at `pyproject.toml:41-43`
  - `testpaths = ["tests"]`
  - `python_files = ["test_*.py"]`
- No additional flags configured (no `addopts`, no markers, no fixtures dir)

**Async support:**
- `pytest-asyncio>=0.21` declared as dev dependency (`pyproject.toml:28`)
- Currently unused — no `async def` test or `await` calls in `tests/`. Reserved for future async work.

**Assertion library:**
- pytest's built-in assert rewriting — no extra library
- `pytest.raises(...)` for exception assertions:
  - `tests/prompts/test_prompt_module.py:88` — `pytest.raises(ValueError, match="Unknown section")`
  - `tests/prompts/test_prompt_module.py:149` — `pytest.raises(RuntimeError, match="No active section")`

**Run commands:**
```bash
pytest tests/                                # Run full suite
pytest tests/tools/                          # Run tools area only
pytest tests/prompts/test_prompt_module.py   # Run a single file
pytest tests/ -k "test_secret"               # Run by name match
pytest tests/ -v                             # Verbose
pytest tests/ --tb=short                     # Compact tracebacks
```

---

## Test File Organization

**Location:** All tests live under `tests/`. Tests are NOT co-located with source — separate `tests/` tree mirrors `evolution/` layout.

**Layout (mirrors `evolution/`):**

```
tests/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── test_constraints.py             # 16 tests (98 lines)
│   └── test_external_importers.py      # 116 tests (1233 lines)
├── prompts/
│   ├── __init__.py
│   ├── test_evolve_prompt_sections.py  # 6 tests (268 lines)
│   ├── test_prompt_constraints.py      # 25 tests (288 lines)
│   ├── test_prompt_dataset.py          # 15 tests (399 lines)
│   ├── test_prompt_loader.py           # 9 tests (260 lines)
│   ├── test_prompt_metric.py           # 14 tests (270 lines)
│   └── test_prompt_module.py           # 14 tests (223 lines)
├── skills/
│   ├── __init__.py
│   └── test_skill_module.py            # 7 tests (92 lines)
└── tools/
    ├── __init__.py
    ├── test_evolve_tool_descriptions.py  # 4 tests (105 lines)
    ├── test_tool_constraints.py          # 21 tests (233 lines)
    ├── test_tool_dataset.py              # 16 tests (378 lines)
    ├── test_tool_loader.py               # 40 tests (701 lines)
    ├── test_tool_metric.py               # 17 tests (158 lines)
    └── test_tool_module.py               # 9 tests (169 lines)
```

**Naming:**
- Test modules: `test_<source-module>.py` (1:1 with `evolution/<area>/<module>.py`)
- Test classes: `TestSomeFeature` grouping related tests for a class/function
- Test functions: `test_<behavior>` describing a single behavior

---

## Test Counts

v1 baseline as of Phase 12 stabilization:

| Area              | Files | Tests |
|-------------------|-------|-------|
| `tests/tools/`    | 6     | 107   |
| `tests/prompts/`  | 6     | 83    |
| `tests/core/`     | 2     | 132   |
| `tests/skills/`   | 1     | 7     |
| **Total**         | **15**| **329** |

The CLAUDE.md baseline cites core = 139 — the live count is 132 (likely includes tests since consolidated or removed). All present tests pass per the v1 stabilization claim.

**Largest suites:**
- `tests/core/test_external_importers.py` — 116 tests covering secret detection, skill relevance heuristics, Claude Code/Copilot/Hermes parsers, JSON parsing, RelevanceFilter, `build_dataset_from_external` orchestration, CLI via CliRunner, EvalExample round-trips
- `tests/tools/test_tool_loader.py` — 40 tests covering DescFormat enum, ToolParam/ToolDescription dataclasses, `discover_tool_files()`, all 4 description formats, parameter extraction, list-of-schemas pattern, write-back per format, round-trip preservation, real hermes-agent integration (`@pytest.mark.skipif` gated)

---

## Test Structure

**Suite organization pattern** (see `tests/tools/test_tool_module.py` for reference):

```python
"""Tests for <module> -- <one-line purpose>."""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import dspy
import pytest

from evolution.<area>.<module> import (
    <Class>,
    <function>,
)

# ── Test Fixtures ───────────────────────────────────────────────────────

def _make_<thing>() -> list[<Type>]:
    """Helper to build test data."""
    return [...]

# ── TestClassName ───────────────────────────────────────────────────────

class TestClassName:
    """<one-line description of what this group covers>."""

    def test_<behavior>(self):
        """<single-line: what this asserts>."""
        ...
```

**Conventions:**
- One `class TestX` per behavior cluster
- Module-level helper functions prefixed `_make_*` build test data: `_make_tool_descriptions()`, `_make_prompt_sections()`, `_make_fake_tools()`, `_make_example()`, `_make_prediction()`, `_make_config()`
- Section separators (unicode box-drawing) demarcate test class groupings: `# ── TestToolModule ──`, `# ── TestSchemaFreeze ──`, `# ── _parse_bool tests ──`
- One-line docstrings on test methods describe the asserted behavior

**Fixtures:**
- `pytest.fixture` used sparingly — only for object construction shared across many tests
  - `tests/core/test_constraints.py:8-11` — `validator` fixture creates `ConstraintValidator(EvolutionConfig())`
  - `tests/core/test_external_importers.py:593, 1038` — local fixtures (one per test class)
- Built-in `tmp_path` fixture used heavily for filesystem isolation (no setup/teardown needed)
- `monkeypatch` not used in current suite

---

## Mocking

**Framework:** `unittest.mock` (stdlib) — `patch`, `patch.object`, `MagicMock`

**Pattern 1 — Method patching with `patch.object`** (`tests/tools/test_tool_module.py:73-75`):

```python
mock_result = dspy.Prediction(selected_tool="memory")
with patch.object(module.selector, "forward", return_value=mock_result):
    result = module.forward("store user preference")
```

**Pattern 2 — Function patching with decorator** (`tests/tools/test_evolve_tool_descriptions.py:73-92`):

```python
@patch("evolution.tools.evolve_tool_descriptions.extract_tool_descriptions")
@patch("evolution.tools.evolve_tool_descriptions.discover_tool_files")
def test_dry_run_shows_tools_no_gepa(self, mock_discover, mock_extract):
    mock_discover.return_value = [Path("/fake/memory.py")]
    mock_extract.side_effect = lambda f: [...]
    with patch("dspy.GEPA") as mock_gepa:
        evolve(iterations=5, dry_run=True)
        mock_gepa.assert_not_called()
```

**Pattern 3 — Class patching for DSPy LMs** (`tests/prompts/test_prompt_metric.py:67-79`):

```python
@patch("evolution.prompts.prompt_metric.LLMJudge")
def test_call_signature(self, mock_judge_cls):
    mock_judge_cls.return_value.score.return_value = FitnessScore(
        correctness=0.5, procedure_following=0.5, conciseness=0.5, feedback="ok",
    )
    metric = PromptBehavioralMetric(_make_config())
    result = metric(_make_example(), _make_prediction(), trace=None)
    assert isinstance(result, float)
```

**Pattern 4 — Stacked context patches for DSPy infrastructure** (`tests/tools/test_tool_constraints.py:84-86`):

```python
with patch.object(checker, "checker", return_value=mock_result):
    with patch("evolution.tools.tool_constraints.dspy.LM"):
        with patch("evolution.tools.tool_constraints.dspy.context"):
            ...
```

### What to mock

- All `dspy.LM(...)` constructor calls (avoids API calls)
- `dspy.GEPA`, `dspy.MIPROv2` (avoids long-running optimizer compile)
- `dspy.context` and `dspy.configure` (avoids global state mutation)
- `LLMJudge` (in metric tests)
- DSPy ChainOfThought returns simulated via `MagicMock` populated with the expected output fields
- File discovery results (`discover_tool_files`, `extract_tool_descriptions`) when end-to-end pipeline behavior is the focus

### What NOT to mock

- `dspy.Example`, `dspy.Prediction`, `dspy.Signature` — pure data containers; tests build them directly
- Filesystem operations under `tmp_path` — real `Path.read_text()` / `write_text()` preferred
- Dataclass construction and serialization — exercised end-to-end

### Hermeticity

- Tests do NOT make real LLM API calls. All `dspy.LM`, `dspy.GEPA`, and `dspy.ChainOfThought` invocations are mocked.
- No environment variables required for the test suite (`HERMES_AGENT_REPO` fallback at `evolution/core/config.py:120-145` is exercised only by `@pytest.mark.skipif(not HERMES_AVAILABLE, ...)`-gated tests)
- No external network calls

---

## Fixtures and Factories

**Module-level helper functions (preferred pattern)** (`tests/tools/test_tool_module.py:15-43`):

```python
def _make_tool_descriptions() -> list[ToolDescription]:
    """Create 3 test ToolDescription instances covering varied schema shapes."""
    return [
        ToolDescription(name="memory", file_path=Path("/fake/memory.py"), ...),
        ToolDescription(name="terminal", file_path=Path("/fake/terminal.py"), ...),
        ToolDescription(name="list-files", file_path=Path("/fake/list_files.py"), ...),
    ]
```

Same pattern: `tests/prompts/test_prompt_module.py:15-39` `_make_prompt_sections()`, `tests/prompts/test_prompt_metric.py:24-46` `_make_config()` / `_make_example()` / `_make_prediction()`, `tests/tools/test_evolve_tool_descriptions.py:14-34` `_make_fake_tools()`.

**Inline sample strings for parser tests:**
- `tests/tools/test_tool_loader.py:20-142` defines five `SAMPLE_*` module-level constants (`SAMPLE_SINGLE_LINE`, `SAMPLE_PAREN_CONCAT`, `SAMPLE_TRIPLE_QUOTE`, `SAMPLE_VARIABLE_REF`, `SAMPLE_LIST_SCHEMAS`) — each is a self-contained Python source snippet used for round-trip extraction tests

**Real skill content for skill module tests:**
- `tests/skills/test_skill_module.py:8-29` `SAMPLE_SKILL` constant — a complete SKILL.md file with frontmatter + body — written to `tmp_path` per test

**No `conftest.py`:** The repo has no shared `conftest.py`. All helpers live in their respective test files.

---

## Coverage

**Requirements:** None enforced. No coverage tool configured (no `coverage.py`, no `pytest-cov`, no `[tool.coverage]` block in `pyproject.toml`).

### Coverage by area (qualitative, derived from test counts and read-through)

| Area | Source File | Tests | Coverage Notes |
|------|-------------|-------|----------------|
| Tool loader | `evolution/tools/tool_loader.py` | 40 | All 4 DescFormat variants × extract + write-back; round-trip syntax verification via `py_compile`; real-hermes integration (skip-gated) |
| Tool module | `evolution/tools/tool_module.py` | 9 | Predictor count, schema freeze (no ToolDescription/ToolParam in `named_parameters()`), evolved descriptions reflect predictor instructions |
| Tool dataset | `evolution/tools/tool_dataset.py` | 16 | Round-trip serialization, default values, `from_dict` ignores unknown keys |
| Tool metric | `evolution/tools/tool_metric.py` | 17 | Selection accuracy metric, cross-tool regression checker |
| Tool constraints | `evolution/tools/tool_constraints.py` | 21 | `_parse_bool` edge cases (10+ branches), `ToolFactualChecker.check` / `check_all` with mocked DSPy |
| Tool CLI | `evolution/tools/evolve_tool_descriptions.py` | 4 | CLI help, eval-source choice validation, dry-run does-not-call-GEPA, importability |
| Prompt loader | `evolution/prompts/prompt_loader.py` | 9 | AST-based section extraction, line range tracking |
| Prompt module | `evolution/prompts/prompt_module.py` | 14 | Active section switching, frozen context construction, `forward()` requires active section, evolved char_count/metadata |
| Prompt metric | `evolution/prompts/prompt_metric.py` | 14 | Empty/None/whitespace output, heuristic vs full-LLM paths, feedback propagation to prediction (PMPT-07) |
| Prompt constraints | `evolution/prompts/prompt_constraints.py` | 25 | `_parse_bool`, role preservation pass/fail, batch checking |
| Prompt dataset | `evolution/prompts/prompt_dataset.py` | 15 | Behavioral dataset round-trip, splits |
| Prompt CLI | `evolution/prompts/evolve_prompt_sections.py` | 6 | CLI help, dry-run, importability |
| Core constraints | `evolution/core/constraints.py` | 16 | Size limits per artifact type, growth limits, non-empty, skill structure validation |
| External importers | `evolution/core/external_importers.py` | 116 | 16 secret-pattern positives, 6 false-positive avoidance, all 3 importers (Claude Code/Copilot/Hermes), JSON parser, RelevanceFilter, full pipeline orchestration, CLI |
| Skill module | `evolution/skills/skill_module.py` | 7 | YAML frontmatter parsing, body extraction, raw round-trip, reassembly |

### Coverage gaps

- `evolution/skills/evolve_skill.py` — no dedicated test file (only `test_skill_module.py` covers loading)
- `evolution/core/dataset_builder.py` — no dedicated test file (`SyntheticDatasetBuilder.generate` tested only indirectly via mocked DSPy in other suites)
- `evolution/core/fitness.py` — no dedicated test file for `LLMJudge` / `skill_fitness_metric` (covered transitively via prompt-metric tests)
- `evolution/core/config.py` — no dedicated test file for `EvolutionConfig.load()` precedence chain
- `generate_report.py` — no tests (manual script)

---

## Test Types

### Unit tests (majority)

Single function or class method exercised in isolation. Filesystem isolated via `tmp_path`, LLM calls mocked. Examples: `tests/core/test_constraints.py`, `tests/tools/test_tool_loader.py::TestDescFormat`, `tests/prompts/test_prompt_metric.py::TestPromptBehavioralMetricEmpty`.

### Integration tests (limited, skip-gated)

- `tests/tools/test_tool_loader.py:574-701` `class TestRealHermesAgent` — runs against the actual hermes-agent checkout when available
- Gated by `@pytest.mark.skipif(not HERMES_AVAILABLE, reason="hermes-agent not available")` (`tests/tools/test_tool_loader.py:583`)
- `HERMES_AVAILABLE` resolved at import time by attempting `get_hermes_agent_path()` and checking existence (`tests/tools/test_tool_loader.py:574-580`)
- Verifies real-world contracts: ≥15 tool files discovered, `memory_tool.py` has paren_concat description, `terminal_tool.py` uses variable_ref, `browser_tool.py` has ≥10 schemas, write-back to copies of all tool files keeps `py_compile` clean

### CLI tests

Use `click.testing.CliRunner` from Click — `tests/tools/test_evolve_tool_descriptions.py:45-64`, `tests/core/test_external_importers.py` (CLI section). `runner.invoke(main, ["--help"])` to verify option presence; `runner.invoke(main, ["--eval-source", "invalid"])` to verify Choice validation.

### End-to-end (E2E) tests

**Not used.** The full pipeline (dataset generation → GEPA → constraint gating → write-back) is not exercised in tests; this is intentional given LLM API costs. The `--dry-run` mode is exercised instead.

---

## Common Patterns

**Filesystem isolation with `tmp_path`** (`tests/skills/test_skill_module.py:33-39`):

```python
def test_parses_frontmatter(self, tmp_path):
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text(SAMPLE_SKILL)
    skill = load_skill(skill_file)
    assert skill["name"] == "test-skill"
```

**Round-trip serialization** (`tests/tools/test_tool_loader.py:193-206`):

```python
def test_from_dict_roundtrip(self):
    original = ToolParam(name="target", type="string", ...)
    restored = ToolParam.from_dict(original.to_dict())
    assert restored.name == original.name
```

**Round-trip write-back with syntax verification** (`tests/tools/test_tool_loader.py:426-435`):

```python
def test_single_line_top_level(self, tmp_path):
    tool_file = tmp_path / "test_tool.py"
    tool_file.write_text(SAMPLE_SINGLE_LINE)
    tools = extract_tool_descriptions(tool_file)
    new_desc = "EVOLVED: ..."
    write_back_description(tool_file, tools[0], new_desc)
    tools_after = extract_tool_descriptions(tool_file)
    assert tools_after[0].description == new_desc
    py_compile.compile(str(tool_file), doraise=True)  # syntax check
```

**Error testing with `pytest.raises`** (`tests/prompts/test_prompt_module.py:88-89`):

```python
with pytest.raises(ValueError, match="Unknown section"):
    module.set_active_section("nonexistent")
```

**Behavior assertions on mocked dependencies** (`tests/prompts/test_prompt_metric.py:128-129`):

```python
if mock_judge_cls.return_value.score.called:
    raise AssertionError("LLMJudge.score() was called during heuristic path")
```

---

## Skipped Phases

### Phase 6 — `06-tool-pipeline-tests`: SKIPPED

**Reason:** TDD-driven implementation in Phases 2-5 produced sufficient coverage (`tests/tools/` has 107 tests across 6 files including the 40-test `test_tool_loader.py` and 21-test `test_tool_constraints.py`). A dedicated end-to-end pipeline test suite was deemed redundant.

### Phase 11 — `11-prompt-pipeline-tests`: SKIPPED

**Reason:** Phases 7-10 produced 83 tests across 6 files for the prompt area (largest: 25-test `test_prompt_constraints.py`, 15-test `test_prompt_dataset.py`, 14-test `test_prompt_metric.py`). The pipeline integration is exercised through `tests/prompts/test_evolve_prompt_sections.py` (6 tests on CLI/dry-run/importability), matching the tools-area pattern.

Phase directories `.planning/phases/06-tool-pipeline-tests/` and `.planning/phases/11-prompt-pipeline-tests/` exist as historical artifacts — no source or test files were created under them.

---

## CI Configuration

**Status:** No CI configuration is checked into this repository.

Verified absent:
- No `.github/` directory at the repo root (no GitHub Actions workflows)
- No `.gitlab-ci.yml`
- No `.circleci/` directory
- No `azure-pipelines.yml`, `bitbucket-pipelines.yml`, `Jenkinsfile`, or `.travis.yml`

**Implications:**
- All test gating is local. Developers run `pytest tests/` manually before commits/PRs.
- Phase 12 (v1-stabilization) verified the 329-test baseline passes locally, but no pull-request gating is automated.
- Adding CI would require a new `.github/workflows/test.yml` (or equivalent) that runs `pip install -e ".[dev]" && pytest tests/`.
- LLM-touching integration tests (`TestRealHermesAgent` in `test_tool_loader.py`) are skip-gated, so they would be safely no-op'd in a CI without hermes-agent checked out.

---

*Testing analysis: 2026-05-06*
