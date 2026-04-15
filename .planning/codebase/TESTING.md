# Testing Patterns

**Analysis Date:** 2026-04-15

## Test Framework

**Runner:**
- pytest >= 7.0
- pytest-asyncio >= 0.21 (installed as dev dependency, no async tests yet)
- Config: `pyproject.toml` `[tool.pytest.ini_options]`

**Assertion Library:**
- Built-in `assert` statements (pytest rewriting)

**Run Commands:**
```bash
pytest                      # Run all tests
pytest tests/               # Run all tests (explicit path)
pytest tests/core/          # Run core module tests only
pytest tests/skills/        # Run skills module tests only
pytest -q --tb=short        # Quick summary output
```

## Test File Organization

**Location:**
- Separate `tests/` directory mirroring `evolution/` package structure
- NOT co-located with source code

**Naming:**
- Test files: `test_<module_name>.py`
- Test classes: `Test<FeatureName>` (PascalCase with `Test` prefix)
- Test methods: `test_<description>` (snake_case with `test_` prefix)

**Structure:**
```
tests/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── test_constraints.py        # Tests for evolution/core/constraints.py
│   └── test_external_importers.py # Tests for evolution/core/external_importers.py
└── skills/
    ├── __init__.py
    └── test_skill_module.py       # Tests for evolution/skills/skill_module.py
```

**Not tested (no test files):**
- `evolution/core/config.py` - No dedicated test file
- `evolution/core/dataset_builder.py` - No dedicated test file (partially covered via roundtrip tests in `test_external_importers.py`)
- `evolution/core/fitness.py` - No dedicated test file
- `evolution/skills/evolve_skill.py` - No dedicated test file
- `generate_report.py` - No test file

## Test Structure

**Suite Organization:**
```python
"""Tests for external session importers.

Tests cover:
  - Secret detection and filtering (true positives + false positives)
  - Skill relevance heuristics
  - Claude Code history parsing + edge cases
  ...
"""

import pytest
from evolution.core.external_importers import (
    _contains_secret,
    _is_relevant_to_skill,
    ...
)


class TestSecretDetection:
    """Verify that known secret formats are caught and normal text is not."""

    def test_detects_anthropic_key(self):
        assert _contains_secret("here is sk-ant-api03-abc123def456 my key")

    def test_ignores_normal_text(self):
        assert not _contains_secret("sort these messages by topic")
```

**Patterns:**
- Group related tests into classes (e.g., `TestSizeConstraints`, `TestGrowthConstraints`, `TestNonEmpty`)
- Each test class focuses on one feature or component
- Module docstring at the top of test files lists all coverage areas
- Class docstrings explain the testing goal
- No `setUp`/`tearDown` methods -- use pytest fixtures instead

## Fixtures

**Pattern:**
```python
@pytest.fixture
def validator():
    config = EvolutionConfig()
    return ConstraintValidator(config)
```

- Use `@pytest.fixture` for shared setup
- Fixtures are defined at the top of the test file, before test classes
- `tmp_path` (built-in pytest fixture) used extensively for file I/O tests
- Fixtures are method-scoped (default) -- no session or module scoped fixtures

**Complex fixture example (mocked DSPy):**
```python
@pytest.fixture
def mock_dspy(self):
    """Mock dspy.LM and dspy.context to avoid real LLM calls."""
    with patch("evolution.core.external_importers.dspy") as mock:
        mock.context.return_value.__enter__ = MagicMock(return_value=None)
        mock.context.return_value.__exit__ = MagicMock(return_value=False)
        yield mock
```

## Mocking

**Framework:** `unittest.mock` (standard library)

**Patterns:**

**1. Patching class attributes (file paths):**
```python
with patch.object(ClaudeCodeImporter, "HISTORY_PATH", history):
    messages = ClaudeCodeImporter.extract_messages()
```

**2. Patching static methods:**
```python
with patch.object(ClaudeCodeImporter, "extract_messages", return_value=mock_messages):
    dataset = build_dataset_from_external(...)
```

**3. Multiple patches stacked:**
```python
with patch.object(ClaudeCodeImporter, "extract_messages", return_value=mock_messages), \
     patch.object(RelevanceFilter, "filter_and_score", return_value=mock_examples):
    dataset = build_dataset_from_external(...)
```

**4. Mocking DSPy scorer (avoiding LLM calls):**
```python
rf = RelevanceFilter.__new__(RelevanceFilter)  # Skip __init__
rf.model = "test-model"
rf.scorer = MagicMock()
rf.scorer.return_value = SimpleNamespace(
    scoring='{"relevant": true, "expected_behavior": "group by topic"}'
)
```

**5. Side effects for exception testing:**
```python
rf.scorer = MagicMock(side_effect=RuntimeError("API timeout"))
```

**What to Mock:**
- LLM API calls (DSPy scorer, LM context) -- always mock, never make real API calls in tests
- File system paths (class-level constants like `HISTORY_PATH`, `SESSION_DIR`) -- redirect to `tmp_path`
- External dependencies that require network or credentials

**What NOT to Mock:**
- Core logic (constraint validation, JSON parsing, skill loading)
- File I/O operations -- use `tmp_path` with real files instead of mocking open()
- Dataclass construction and serialization

## Fixtures and Factories

**Test Data:**
```python
SAMPLE_SKILL = """---
name: test-skill
description: A skill for testing things
version: 1.0.0
metadata:
  hermes:
    tags: [testing]
---

# Test Skill — Testing Things

## When to Use
Use this when you need to test things.
"""
```

- Use module-level constants for reusable test data (e.g., `SAMPLE_SKILL` in `tests/skills/test_skill_module.py`)
- Construct test data inline for one-off cases
- Create temporary files via `tmp_path` for file I/O tests:
```python
def test_parses_history_jsonl(self, tmp_path):
    history = tmp_path / "history.jsonl"
    history.write_text(
        json.dumps({"display": "sort my slack messages", ...}) + "\n"
    )
```

**Location:**
- Test data defined in-line within test files
- No separate fixtures directory or conftest.py files

## Coverage

**Requirements:** None enforced. No coverage configuration in `pyproject.toml`.

**View Coverage:**
```bash
pip install pytest-cov
pytest --cov=evolution --cov-report=term-missing
```

## Test Types

**Unit Tests:**
- Primary test type in the codebase
- Test individual functions and methods in isolation
- Located in `tests/core/test_constraints.py`, `tests/skills/test_skill_module.py`
- Focus areas: constraint validation, skill parsing, secret detection, JSON parsing, relevance heuristics

**Integration Tests:**
- End-to-end roundtrip tests in `tests/core/test_external_importers.py`
- Class `TestEndToEndRoundtrip`: creates fake session files, runs the pipeline with mocked LLM, saves to disk, reloads with `GoldenDatasetLoader`
- Class `TestBuildDataset`: tests orchestration function with mocked importers and filters

**E2E Tests:**
- Not present. No tests that make real LLM API calls.

**CLI Tests:**
- Uses `click.testing.CliRunner` for testing CLI entry points
- Located in `tests/core/test_external_importers.py` (class `TestCLI`)
- Tests both `--dry-run` mode and error handling (missing skill)

## Common Patterns

**Testing Both True and False Cases:**
```python
class TestSecretDetection:
    def test_detects_anthropic_key(self):
        assert _contains_secret("sk-ant-api03-abc123def456")

    def test_ignores_normal_text(self):
        assert not _contains_secret("sort these messages by topic")
```
Always test both positive and negative cases for detection/validation functions.

**File-Based Testing:**
```python
def test_parses_frontmatter(self, tmp_path):
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_text(SAMPLE_SKILL)
    skill = load_skill(skill_file)
    assert skill["name"] == "test-skill"
```
Use `tmp_path` to create real files, test actual file I/O.

**Error/Edge Case Testing:**
```python
def test_handles_missing_file(self, tmp_path):
    with patch.object(ClaudeCodeImporter, "HISTORY_PATH", tmp_path / "nonexistent.jsonl"):
        messages = ClaudeCodeImporter.extract_messages()
    assert messages == []

def test_handles_malformed_json(self, tmp_path):
    (tmp_path / "bad.json").write_text("{not valid json")
    with patch.object(HermesSessionImporter, "SESSION_DIR", tmp_path):
        msgs = HermesSessionImporter.extract_messages()
    assert msgs == []
```
Every importer tests: missing files, malformed data, empty inputs, permission errors.

**Assertion Style:**
- Plain `assert` with comparison: `assert result.passed`
- String containment: `assert "exceeded" in result.message`
- Collection checks: `assert len(messages) == 1`
- Set membership: `assert "claude-code" in sources`
- No custom assertion helpers or assertion libraries

## Input Validation Testing

**Pattern from `tests/core/test_external_importers.py`:**
```python
class TestInputValidation:
    def test_valid_input_passes(self):
        result = _validate_eval_example("task", "behavior", "easy", "sorting")
        assert result is not None
        assert result["difficulty"] == "easy"

    def test_empty_task_input_rejected(self):
        assert _validate_eval_example("", "behavior", "easy", "sorting") is None

    def test_invalid_difficulty_normalized(self):
        result = _validate_eval_example("task", "behavior", "super-hard", "sorting")
        assert result["difficulty"] == "medium"

    def test_long_task_input_truncated(self):
        long_input = "x" * 5000
        result = _validate_eval_example(long_input, "behavior", "easy", "sorting")
        assert len(result["task_input"]) == 2000
```
Validate that input normalization functions handle edge cases: empty inputs, invalid enums, oversized strings.

---

*Testing analysis: 2026-04-15*
