# Coding Conventions

**Analysis Date:** 2026-04-15

## Naming Patterns

**Files:**
- Use `snake_case.py` for all Python modules: `dataset_builder.py`, `evolve_skill.py`, `external_importers.py`
- Test files use `test_` prefix: `test_constraints.py`, `test_external_importers.py`, `test_skill_module.py`
- Top-level scripts are `snake_case.py`: `generate_report.py`

**Functions:**
- Use `snake_case` for all functions and methods: `load_skill()`, `find_skill()`, `validate_all()`
- Private/internal functions prefixed with underscore: `_check_size()`, `_parse_scoring_json()`, `_contains_secret()`, `_is_relevant_to_skill()`
- Static methods and class methods follow the same pattern: `extract_messages()`, `from_dict()`, `to_dict()`

**Variables:**
- Use `snake_case` for all variables: `skill_text`, `eval_model`, `max_examples`
- Constants use `UPPER_SNAKE_CASE`: `SECRET_PATTERNS`, `VALID_DIFFICULTIES`, `MIN_DATASET_SIZE`, `HISTORY_PATH`, `SESSION_DIR`
- Numeric constants use underscores for readability: `15_000`, `20_000`

**Classes:**
- Use `PascalCase`: `EvolutionConfig`, `ConstraintValidator`, `ConstraintResult`, `EvalExample`, `SyntheticDatasetBuilder`
- DSPy Signature classes are nested inside their parent class as inner classes: `class GenerateTestCases(dspy.Signature)` inside `SyntheticDatasetBuilder`

**Types:**
- Use `PascalCase` for dataclasses and type names: `FitnessScore`, `EvalDataset`, `ConstraintResult`

## Code Style

**Formatting:**
- No formatter configuration detected (no `.prettierrc`, `pyproject.toml [tool.black]`, `ruff.toml`, etc.)
- Indent: 4 spaces (standard Python)
- Line length: generally under 120 characters, no hard enforcement
- Trailing commas used in multi-line function calls and data structures

**Linting:**
- No linter configuration detected (no `.flake8`, `ruff.toml`, `[tool.ruff]`, or `[tool.pylint]` in `pyproject.toml`)
- Code follows PEP 8 conventions organically

**Type Hints:**
- Use modern Python type hints throughout: `list[ConstraintResult]`, `dict[str, int]`, `Optional[str]`
- Use `from typing import Optional` for optional parameters
- Return types specified on public functions; sometimes omitted on private helpers
- Dataclass fields use type annotations: `passed: bool`, `constraint_name: str`

## Import Organization

**Order:**
1. Standard library imports: `json`, `os`, `re`, `random`, `subprocess`, `time`, `sys`
2. Third-party imports: `dspy`, `click`, `rich`, `reportlab`
3. Local imports: `from evolution.core.config import EvolutionConfig`

**Style:**
- Use `from X import Y` for specific items (preferred over `import X` for local modules)
- Group related imports on separate lines
- Separate groups with a blank line
- Example from `evolution/skills/evolve_skill.py`:
```python
import json
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

import click
import dspy
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from evolution.core.config import EvolutionConfig, get_hermes_agent_path
from evolution.core.dataset_builder import SyntheticDatasetBuilder, EvalDataset, GoldenDatasetLoader
```

**Path Aliases:**
- No path aliases used. All imports use full module paths from the `evolution` package root.

## Module Docstrings

**Every module has a docstring** explaining its purpose and context. Use triple-quote docstrings at the top of every file.

Pattern:
```python
"""Short summary of what this module does.

Longer explanation of design decisions, usage patterns, or architecture context.
Multi-paragraph explanations are common and expected.
"""
```

Examples:
- `evolution/core/constraints.py`: Explains the constraint validation philosophy (all-or-nothing)
- `evolution/core/external_importers.py`: Documents supported sources, CLI usage, and programmatic usage
- `evolution/core/fitness.py`: Explains the LLM-as-judge approach and scoring dimensions

## Class Design

**Dataclasses for data:**
- Use `@dataclass` for plain data objects: `EvolutionConfig`, `ConstraintResult`, `EvalExample`, `FitnessScore`
- Use `field(default_factory=...)` for mutable defaults
- Include `to_dict()` and `from_dict()` classmethods for serialization when needed

**Classes for behavior:**
- Use regular classes for stateful components: `ConstraintValidator`, `LLMJudge`, `RelevanceFilter`
- Constructor takes config/dependencies: `def __init__(self, config: EvolutionConfig)`
- DSPy modules inherit from `dspy.Module`: `class SkillModule(dspy.Module)`

**Inner classes for DSPy Signatures:**
- Define DSPy `Signature` classes as nested inner classes of their consuming class
- Pattern used in `evolution/core/dataset_builder.py`, `evolution/core/fitness.py`, `evolution/core/external_importers.py`, `evolution/skills/skill_module.py`
```python
class LLMJudge:
    class JudgeSignature(dspy.Signature):
        """Docstring explaining the signature's contract."""
        task_input: str = dspy.InputField(desc="...")
        correctness: float = dspy.OutputField(desc="...")

    def __init__(self, config):
        self.judge = dspy.ChainOfThought(self.JudgeSignature)
```

## Error Handling

**Patterns:**
- Raise specific exceptions with descriptive messages for unrecoverable errors:
  ```python
  raise FileNotFoundError(
      "Cannot find hermes-agent repo. Set HERMES_AGENT_REPO env var "
      "or ensure it exists at ~/.hermes/hermes-agent"
  )
  ```
- Use `try/except` with bare `Exception` for resilient parsing (e.g., JSON from LLM output):
  ```python
  try:
      entry = json.loads(line)
  except json.JSONDecodeError:
      continue
  ```
- Return neutral/default values on parse failure rather than crashing:
  ```python
  def _parse_score(value) -> float:
      try:
          return min(1.0, max(0.0, float(str(value).strip())))
      except (ValueError, TypeError):
          return 0.5  # Default to neutral on parse failure
  ```
- Use `ConstraintResult` dataclass to represent pass/fail without exceptions
- CLI commands use `sys.exit(1)` or `raise SystemExit(1)` for user-facing errors
- Process errors are logged via `rich.console` and counted (error rate tracking in `RelevanceFilter`)

## Logging

**Framework:** `rich.console.Console` for all user-facing output

**Patterns:**
- Create a module-level console: `console = Console()` (in `evolution/core/external_importers.py`, `evolution/skills/evolve_skill.py`)
- Use Rich markup for colored output: `[bold cyan]`, `[red]`, `[green]`, `[yellow]`
- Use `console.print()` for all output, never bare `print()` (except in `generate_report.py`)
- Progress bars via `rich.progress.Progress` for long-running operations
- Tables via `rich.table.Table` for structured results display
- No logging framework (`logging` module) is used

## Comments

**When to Comment:**
- Section separators using unicode box-drawing comments:
  ```python
  # ── Secret Detection ──────────────────────────────────────────────────────
  ```
- Inline comments for non-obvious decisions: `# Penalty ramps from 0 at 90% to 0.3 at 100%+`
- Step numbering in orchestration functions: `# ── 1. Find and load the skill ──`

**Docstrings:**
- All public classes and functions have docstrings
- Use Google-style docstring format with `Args:` and `Returns:` sections
- Private methods have shorter docstrings or none

## Function Design

**Size:** Functions are moderate size (10-50 lines typical). The `evolve()` function in `evolution/skills/evolve_skill.py` is the largest (~260 lines) and uses section comments to organize.

**Parameters:**
- Use keyword arguments with defaults for optional config: `num_cases: Optional[int] = None`
- Use `click.option` decorators for CLI parameters
- Config objects passed as single parameter rather than many individual args

**Return Values:**
- Use dataclasses for structured returns: `ConstraintResult`, `FitnessScore`, `EvalDataset`
- Use `Optional[X]` when a function may not find a result: `find_skill() -> Optional[Path]`
- Use `list[X]` for collection returns
- Properties for computed values: `@property def composite(self) -> float`

## CLI Design

**Framework:** Click (`click>=8.0`)

**Pattern:**
- `@click.command()` decorator on `main()` function
- `@click.option()` for each parameter with help text
- Guard `if __name__ == "__main__": main()`
- Modules runnable via `python -m evolution.module.name`
- Separate the CLI entry point (`main`) from the business logic function (`evolve()`)

## Serialization

**JSON/JSONL:**
- Use JSONL (one JSON object per line) for datasets: `train.jsonl`, `val.jsonl`, `holdout.jsonl`
- Use `json.dumps(obj) + "\n"` for writing, line-by-line `json.loads()` for reading
- Use `json.dumps(metrics, indent=2)` for human-readable config/metrics files
- Dataclasses provide `to_dict()` / `from_dict()` methods for JSON serialization

---

*Convention analysis: 2026-04-15*
