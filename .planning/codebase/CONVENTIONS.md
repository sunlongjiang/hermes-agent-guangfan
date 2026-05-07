# Coding Conventions

**Analysis Date:** 2026-05-06

## Naming Patterns

**Files:**
- All Python modules use `snake_case.py`: `dataset_builder.py`, `evolve_skill.py`, `external_importers.py`, `tool_loader.py`, `prompt_metric.py`
- Tests prefixed `test_<module>.py`: `tests/tools/test_tool_loader.py`, `tests/prompts/test_prompt_module.py`, `tests/core/test_constraints.py`
- CLI entry-point scripts use `evolve_<artifact>.py`: `evolution/skills/evolve_skill.py`, `evolution/tools/evolve_tool_descriptions.py`, `evolution/prompts/evolve_prompt_sections.py`
- Top-level scripts use `snake_case.py`: `generate_report.py`

**Functions:**
- Public functions: `snake_case` — `load_skill()`, `find_skill()`, `reassemble_skill()`, `discover_tool_files()`, `extract_tool_descriptions()`, `write_back_description()`, `build_dataset_from_external()`
- Private/internal helpers prefixed with underscore: `_check_size()`, `_check_growth()`, `_check_skill_structure()`, `_parse_score()`, `_parse_bool()`, `_parse_scoring_json()`, `_contains_secret()`, `_is_relevant_to_skill()`, `_extract_description_at()`, `_find_matching_bracket()`, `_resolve_variable()`, `_format_paren_concat()`, `_load_skill_text()`, `_validate_eval_example()`
- DSPy metric functions: `snake_case` — `skill_fitness_metric()` in `evolution/core/fitness.py:107`, `tool_selection_metric()` in `evolution/tools/tool_metric.py`
- Static/class methods: `extract_messages()`, `to_dict()`, `from_dict()`, `load()`, `save()` (e.g. `evolution/core/external_importers.py:168` `ClaudeCodeImporter.extract_messages`)

**Variables:**
- All variables: `snake_case` — `skill_text`, `eval_model`, `max_examples`, `evolved_module`, `baseline_constraints`, `tool_files`, `original_tools`
- Constants: `UPPER_SNAKE_CASE` — `SECRET_PATTERNS`, `VALID_DIFFICULTIES`, `MIN_DATASET_SIZE`, `HISTORY_PATH`, `SESSION_DIR`, `TARGET_STR_VARS`, `TARGET_DICT_VAR`
- Numeric literals use underscores for readability: `15_000`, `20_000` (e.g. `evolution/core/config.py:31` `max_skill_size: int = 15_000`)
- Module-level singleton: `console = Console()` at file head (`evolution/skills/evolve_skill.py:33`, `evolution/tools/tool_loader.py:21`, `evolution/core/external_importers.py:38`)

**Types:**
- Classes use `PascalCase`: `EvolutionConfig`, `ConstraintValidator`, `ConstraintResult`, `EvalExample`, `EvalDataset`, `SyntheticDatasetBuilder`, `LLMJudge`, `FitnessScore`, `RelevanceFilter`, `ToolDescription`, `ToolParam`, `DescFormat`, `ToolModule`, `SkillModule`, `PromptModule`, `PromptSection`, `ToolFactualChecker`, `PromptRoleChecker`, `CrossToolRegressionChecker`, `PromptBehavioralMetric`
- DSPy `Signature` classes are nested as INNER classes of their consuming class:
  - `evolution/core/dataset_builder.py:96` `class GenerateTestCases(dspy.Signature)` inside `SyntheticDatasetBuilder`
  - `evolution/core/fitness.py:41` `class JudgeSignature(dspy.Signature)` inside `LLMJudge`
  - `evolution/tools/tool_constraints.py:43` `class FactualCheckSignature(dspy.Signature)` inside `ToolFactualChecker`
  - `evolution/prompts/prompt_constraints.py:44` `class RoleCheckSignature(dspy.Signature)` inside `PromptRoleChecker`
- Top-level Signature only when reused: `evolution/tools/tool_module.py:16` `class ToolSelectionSignature(dspy.Signature)` (used by `ToolModule.selector`)
- Enums use `PascalCase` with `UPPER_SNAKE_CASE` values: `evolution/tools/tool_loader.py:26` `class DescFormat(Enum)` with `SINGLE_LINE`, `PAREN_CONCAT`, `TRIPLE_QUOTE`, `VARIABLE_REF`

## Code Style

**Formatting:**
- No formatter is configured (no `[tool.black]`, `[tool.ruff]` in `pyproject.toml`, no `.prettierrc`, no `pre-commit` hooks)
- Indent: 4 spaces (PEP 8 standard)
- Line length: generally under 120 chars; not enforced
- Trailing commas used in multi-line function calls and data structures (e.g. `evolution/core/config.py:13-50`)

**Linting:**
- No linter configured (no `ruff.toml`, `.flake8`, `[tool.pylint]`)
- Code follows PEP 8 organically

**Type Hints:**
- Modern syntax used throughout: `list[X]`, `dict[K, V]`, `tuple[int, int]`
- `Optional[X]` imported `from typing import Optional`
- Public function signatures always include parameter and return types: `evolution/core/constraints.py:30-35` `validate_all(self, artifact_text: str, artifact_type: str, baseline_text: Optional[str] = None) -> list[ConstraintResult]`
- Private helpers occasionally omit return type: `evolution/core/external_importers.py:78` `def _contains_secret(text: str) -> bool:` (still typed)
- Dataclass fields always type-annotated: `evolution/core/constraints.py:18-21`

## Import Organization

**Order:**
1. Standard library: `import json`, `import re`, `import sys`, `import time`, `from pathlib import Path`, `from datetime import datetime`, `from dataclasses import dataclass, field`, `from typing import Optional`
2. Blank line
3. Third-party: `import click`, `import dspy`, `from rich.console import Console`, `from rich.panel import Panel`, `from rich.table import Table`, `from rich.progress import Progress`
4. Blank line
5. Project-local: `from evolution.core.config import EvolutionConfig`, `from evolution.tools.tool_loader import ...`

Reference: `evolution/skills/evolve_skill.py:8-31`, `evolution/tools/evolve_tool_descriptions.py:9-29`

**Style:**
- Project-local: prefer `from X import Y` over `import X.Y` — pulls specific symbols
- Stdlib: mix of `import X` and `from X import Y` (e.g. `import json` but `from pathlib import Path`)

**Path Aliases:**
- None. All imports use full module paths from the `evolution` package root.

## Module Docstrings

Every module begins with a docstring explaining its role.

**Examples:**
- `evolution/core/constraints.py:1-5`: explains the all-or-nothing constraint philosophy
- `evolution/core/fitness.py:1-5`: explains LLM-as-judge approach and scoring dimensions
- `evolution/core/external_importers.py:1-23`: documents supported sources, CLI usage, and programmatic usage with example commands
- `evolution/tools/tool_loader.py:1-10`: documents the four supported description formats
- `evolution/prompts/prompt_loader.py:1-13`: documents target variables and write-back strategy
- `evolution/prompts/prompt_metric.py:1-16`: documents the dual heuristic/LLMJudge execution paths

CLI modules include a `Usage:` section in the module docstring:
- `evolution/tools/evolve_tool_descriptions.py:1-7`
- `evolution/skills/evolve_skill.py:1-6`

## Class Design

**Dataclasses for value objects:**
- `@dataclass` used for all plain data: `EvolutionConfig` (`evolution/core/config.py:11`), `ConstraintResult` (`evolution/core/constraints.py:16`), `EvalExample` and `EvalDataset` (`evolution/core/dataset_builder.py:21,44`), `FitnessScore` (`evolution/core/fitness.py:15`), `ToolParam` and `ToolDescription` (`evolution/tools/tool_loader.py:37,77`), `PromptSection` (`evolution/prompts/prompt_loader.py:40`), `ToolSelectionExample` (`evolution/tools/tool_dataset.py`)
- Mutable defaults use `field(default_factory=...)`: `evolution/core/dataset_builder.py:46-48`, `evolution/core/config.py:15`, `evolution/tools/tool_loader.py:92`
- Computed properties via `@property`: `evolution/core/dataset_builder.py:50-52` `all_examples`, `evolution/core/fitness.py:23-31` `composite`

**Serialization on dataclasses:**
- All persisted dataclasses provide `to_dict()` and `from_dict()` classmethods
- `from_dict` uses defensive `**{k: v for k, v in d.items() if k in cls.__dataclass_fields__}` pattern to ignore unknown keys (`evolution/core/dataset_builder.py:39`)
- Reference implementations: `evolution/tools/tool_loader.py:54-73` (`ToolParam`), `evolution/tools/tool_loader.py:98-115` (`ToolDescription`)

**Stateful classes:**
- Constructor takes a single `config: EvolutionConfig` parameter: `evolution/core/constraints.py:27` `ConstraintValidator(config)`, `evolution/core/fitness.py:60` `LLMJudge(config)`, `evolution/tools/tool_constraints.py:67` `ToolFactualChecker(config)`, `evolution/prompts/prompt_constraints.py:68` `PromptRoleChecker(config)`, `evolution/prompts/prompt_metric.py:35` `PromptBehavioralMetric(config)`
- Importer classes use `@staticmethod extract_messages(limit: int = 0)` with no instance state: `evolution/core/external_importers.py:157` `ClaudeCodeImporter`, line 210 `CopilotImporter`, `HermesSessionImporter`
- Class-level constants for paths: `HISTORY_PATH = Path.home() / ".claude" / "history.jsonl"` (`evolution/core/external_importers.py:165`), `SESSION_DIR = Path.home() / ".copilot" / "session-state"` (line 222)

**DSPy module pattern:**
- All optimizable artifacts inherit from `dspy.Module`:
  - `evolution/skills/skill_module.py` `SkillModule(dspy.Module)`
  - `evolution/tools/tool_module.py:35` `ToolModule(dspy.Module)`
  - `evolution/prompts/prompt_module.py` `PromptModule(dspy.Module)`
- `__init__` calls `super().__init__()` first, then registers `dspy.Predict` instances and `dspy.ChainOfThought` selectors
- Frozen schema fields stored on private attributes (e.g. `self._frozen_tools`, `self._frozen_instructions`) — invisible to `named_parameters()` (`evolution/tools/tool_module.py:58-61`)
- A `forward()` method returns `dspy.Prediction(**fields)`
- A `get_evolved_<thing>()` method merges current predictor instructions with frozen schema into the original dataclass type (`evolution/tools/tool_module.py:88-112`)

## Error Handling

**Raise specific exceptions for unrecoverable errors:**
- File not found: `evolution/core/config.py:142-145` `raise FileNotFoundError(...)` with descriptive message naming the env var
- Invalid state: `evolution/prompts/prompt_module.py` raises `RuntimeError("No active section")` and `ValueError("Unknown section: ...")` (verified in `tests/prompts/test_prompt_module.py:88-89,149`)
- Format/structure failures: `evolution/tools/tool_loader.py:557` `raise ValueError(f"Cannot find schema variable {tool.schema_var_name} in {file_path}")`

**Resilient parsing with `except Exception`:**
- LLM output parsing: `evolution/tools/tool_loader.py:209-211` wraps schema extraction so a malformed schema produces a warning + skip instead of crashing the whole run
- File read errors: `evolution/tools/tool_loader.py:138-141` continues to next file when `read_text()` raises
- AST evaluation fallback: `evolution/tools/tool_loader.py:310-314` falls back from `ast.literal_eval` to manual string extraction
- JSON decode in event streaming: `evolution/core/external_importers.py:288-289` skips malformed lines

**Return neutral defaults on parse failure:**
- Score parsing: `evolution/core/fitness.py:139-146` `_parse_score()` returns `0.5` (neutral) on `ValueError`/`TypeError`, clamps to `[0.0, 1.0]`
- Boolean parsing: `evolution/tools/tool_constraints.py:15-29` `_parse_bool()` is conservative — non-truthy strings always return `False`
- Variable resolution: `evolution/tools/tool_loader.py:384-389` returns empty string when a referenced variable is not found
- Workspace metadata: `evolution/core/external_importers.py:260-270` `_read_copilot_workspace()` returns `""` on any error

**`ConstraintResult` for pass/fail without exceptions:**
- Failure conditions become `ConstraintResult(passed=False, ...)` rather than exceptions: `evolution/core/constraints.py:113-117`, `evolution/tools/tool_constraints.py:99-105`, `evolution/prompts/prompt_constraints.py:107-113`
- Subprocess timeout/failure becomes a failed result: `evolution/core/constraints.py:82-93`

**CLI exits:**
- User-facing failures use `sys.exit(1)`: `evolution/skills/evolve_skill.py:65, 97, 115`, `evolution/tools/evolve_tool_descriptions.py:109, 117, 157, 162`
- Exit accompanied by a Rich-formatted error: `console.print(f"[red]✗ ...[/red]")` then `sys.exit(1)`

## Logging

**Framework:** No `logging` module is used anywhere in `evolution/`. All output goes through Rich.

**Pattern:**
- One module-level `console = Console()` at file head (verified in 9 source files: `evolution/skills/evolve_skill.py:33`, `evolution/tools/evolve_tool_descriptions.py:31`, `evolution/tools/tool_loader.py:21`, `evolution/tools/tool_metric.py:15`, `evolution/tools/tool_dataset.py:26`, `evolution/core/external_importers.py:38`, `evolution/prompts/evolve_prompt_sections.py:34`, `evolution/prompts/prompt_loader.py:22`, `evolution/prompts/prompt_dataset.py:27`)
- Use `console.print()` exclusively, never bare `print()` (exception: `generate_report.py` uses ReportLab + raw print)
- Rich markup for color: `[bold cyan]`, `[red]`, `[green]`, `[yellow]`, `[bold]`
- Status icons inline: `✓`/`✗` (skill_evolve), `+`/`x` (tool/prompt evolve to avoid encoding issues)

**Structured output:**
- Tables for comparison results: `rich.table.Table` (`evolution/skills/evolve_skill.py:230-253` Evolution Results table; `evolution/tools/evolve_tool_descriptions.py:120-126` Discovered Tools)
- Progress bars for long iteration: `rich.progress.Progress` (`evolution/core/external_importers.py:241-251` while parsing Copilot sessions)
- Panels for highlighted callouts: imported but used sparingly

## Comments

**Section separators (unicode box-drawing):**
- Format: `# ── Section Name ──────────────────────────────────────────────────`
- Used to demarcate logical regions inside long files
- Examples: `evolution/tools/tool_loader.py:24` `# ── Description Format Enum ──`, line 34 `# ── Data Classes ──`, line 118 `# ── File Discovery ──`, line 147 `# ── Schema Constant Discovery ──`, line 156 `# ── Core Extraction ──`, line 216 `# ── Internal Helpers ──`, line 520 `# ── Write-Back ──`
- Same pattern in `evolution/tools/evolve_tool_descriptions.py:34, 69, 397`

**Step numbering in orchestration functions:**
- Format: `# ── 1. Step description ──────────────────────────────────────────`
- Used in `evolve()` pipelines for the 8-11 stage flow
- Examples: `evolution/skills/evolve_skill.py:59, 80, 119, 134, 151, 182, 187, 207, 229, 255` (steps 1-10), `evolution/tools/evolve_tool_descriptions.py:91, 104, 128, 139, 143, 169, 211, 214, 284, 329, 350` (steps 1-11)

**Inline comments only for non-obvious decisions:**
- `evolution/core/fitness.py:95` `# Penalty ramps from 0 at 90% to 0.3 at 100%+`
- `evolution/core/external_importers.py:75` `MIN_DATASET_SIZE = 3  # Minimum examples needed to produce a meaningful split`
- `evolution/core/dataset_builder.py:53` clarifying property semantics

**Docstrings — Google style:**
- All public classes and functions have docstrings
- Format: one-line summary + blank line + `Args:` block + `Returns:` block
- Example: `evolution/tools/tool_loader.py:120-131` `discover_tool_files`
- Example: `evolution/core/constraints.py:55-93` `run_test_suite`
- Private helpers may have shorter docstrings or omit them (e.g. `evolution/core/external_importers.py:78-80` is single line)
- Module docstrings detailed in the **Module Docstrings** section above

## Function Design

**Parameters:**
- Keyword arguments with defaults for optional config: `evolution/core/dataset_builder.py:115-119` `def generate(self, artifact_text, artifact_type="skill", num_cases: Optional[int] = None)`
- CLI parameters via `@click.option` decorators (see CLI Design)
- Config dependency injection via single `config: EvolutionConfig` parameter rather than many positional args

**Return values:**
- `Optional[X]` when result may be missing: `evolution/skills/skill_module.py` `find_skill() -> Optional[Path]`, `evolution/core/external_importers.py` `_validate_eval_example() -> Optional[dict]`
- `list[X]` for collection returns: `validate_all() -> list[ConstraintResult]`, `extract_messages() -> list[dict]`, `extract_tool_descriptions() -> list[ToolDescription]`
- Tuples for paired offsets: `evolution/tools/tool_loader.py:284` `_extract_description_at(...) -> tuple[str, DescFormat, int, int]`
- Dataclasses for structured results: `ConstraintResult`, `FitnessScore`, `EvalDataset`

**Properties for computed values:**
- `evolution/core/dataset_builder.py:50-52` `all_examples`
- `evolution/core/fitness.py:23-31` `composite` (weighted score with length penalty applied)

## CLI Design

**Pattern:**
- `@click.command()` decorator on a `main()` function
- One `@click.option(...)` per parameter, each with `help=` text
- `main()` immediately delegates to a separate business function (`evolve()`) — keeps logic testable
- File ends with `if __name__ == "__main__": main()`
- Reference: `evolution/skills/evolve_skill.py:296-323`, `evolution/tools/evolve_tool_descriptions.py:400-421`, `evolution/prompts/evolve_prompt_sections.py`, `evolution/core/external_importers.py:729-785`

**Standard CLI options across pipelines:**
- `--iterations` (int, default 10) — GEPA iterations
- `--eval-source` (Choice, default `synthetic`) — `synthetic | load | golden | sessiondb`
- `--hermes-repo` (str, optional) — override `HERMES_AGENT_REPO`
- `--dry-run` (flag) — validate setup without invoking GEPA
- `--model` (str, optional) — override all LLM models
- `--api-base` (str, optional) — override OpenAI-compatible API base URL
- Skill-specific: `--skill <name>` (required), `--dataset-path`, `--optimizer-model`, `--eval-model`, `--run-tests`
- Prompt-specific: `--section <id>` (optional)

**Module invocation:**
- All CLIs runnable via `python -m evolution.<package>.<module>`:
  - `python -m evolution.skills.evolve_skill --skill arxiv --iterations 10`
  - `python -m evolution.tools.evolve_tool_descriptions --iterations 10`
  - `python -m evolution.prompts.evolve_prompt_sections --section memory_guidance`
  - `python -m evolution.core.external_importers --source all --skill my-skill --dry-run`

## Serialization

**JSONL for datasets (one JSON object per line):**
- Format: `train.jsonl`, `val.jsonl`, `holdout.jsonl` per dataset
- Write: `f.write(json.dumps(ex.to_dict()) + "\n")` — `evolution/core/dataset_builder.py:57-60`
- Read: line-by-line `json.loads()` skipping blank lines — `evolution/core/dataset_builder.py:69-74`
- Storage layout: `datasets/skills/<skill>/`, `datasets/tools/`, `datasets/prompts/`

**Indented JSON for human-readable artifacts:**
- Metrics: `(output_dir / "metrics.json").write_text(json.dumps(metrics, indent=2))` (`evolution/skills/evolve_skill.py:284`, `evolution/tools/evolve_tool_descriptions.py:379`)
- Evolved descriptions: `evolution/tools/evolve_tool_descriptions.py:360-362`
- Failed/regression results: `evolution/tools/evolve_tool_descriptions.py:275-279, 318-324`

**YAML for config (read-only):**
- `evolution.yaml` is the project-level config file, parsed by `EvolutionConfig.load()` via `yaml.safe_load(f)` (`evolution/core/config.py:73-76`)
- Skill frontmatter parsed manually (no YAML library invocation in `evolution/skills/skill_module.py`)

**Output directory layout:**
- `output/<artifact-type>/<timestamp>/` for successful runs
- `output/<artifact-type>/FAILED_<timestamp>/` for failed constraint validations
- Each contains `metrics.json` plus artifact-specific files (`evolved_skill.md`, `evolved_descriptions.json`, `diff.txt`, `baseline_*.md`)

## LLM Output Parsing

**Two-stage strategy for JSON in LLM output:**
1. Try `json.loads(text)`
2. On failure, fall back to brace-counting extraction (find first `{`/`[`, count balanced brackets, slice, retry parse)
- Reference implementation: `_parse_scoring_json()` in `evolution/core/external_importers.py`

**Score clamping:**
- `evolution/core/fitness.py:139-146` `_parse_score()` casts to `float`, clamps to `[0.0, 1.0]`, returns `0.5` on parse failure (neutral)

**Boolean parsing:**
- `evolution/tools/tool_constraints.py:15-29` and `evolution/prompts/prompt_constraints.py:15-29` define duplicate `_parse_bool()` helpers
- Conservative: only `True`, `"true"`, `"yes"`, `"1"` (case-insensitive, stripped) return `True`. Anything else → `False`

**Secret detection in mined data:**
- `evolution/core/external_importers.py:45-70` `SECRET_PATTERNS` — single anchored regex covering Anthropic/OpenAI/OpenRouter API keys, GitHub PAT/user tokens, Slack bot/app tokens, Notion tokens, AWS access keys, Bearer headers, PEM headers, env-var names (`ANTHROPIC_API_KEY`, etc.), and assignment patterns (`password=`, `secret=`, `token=`)
- `_contains_secret()` returns `True` → message is silently skipped (no error, no warning)
- Anchored to known formats to minimize false positives (e.g. "ask" containing "sk" does NOT trigger, verified at `tests/core/test_external_importers.py:103-104`)

---

*Convention analysis: 2026-05-06*
