<!-- GSD:project-start source:PROJECT.md -->
## Project

**Hermes Agent Self-Evolution: Phase 2 & 3**

在已实现 Phase 1（技能进化）的基础上，实现 Phase 2（工具描述优化）和 Phase 3（系统提示词进化）。复用核心基础设施（dataset_builder、fitness、constraints），为每个 Phase 构建独立可用的优化管道。目标是让 GEPA 能优化 hermes-agent 的工具描述和系统提示词组件。

**Core Value:** 让 GEPA 优化循环能覆盖工具描述和系统提示词——不仅是技能文件——使 hermes-agent 的核心文本制品都能被系统性地自动改进。

### Constraints

- **Architecture**: 严格遵循 Phase 1 的代码模式和目录结构
- **Dependency**: 不引入新的外部依赖，复用现有 DSPy/Click/Rich 栈
- **hermes-agent**: 只读访问，通过 HERMES_AGENT_REPO 环境变量定位
- **Size**: 工具描述 ≤500 chars，参数描述 ≤200 chars，提示词段 ≤ 基线 +20%
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python >=3.10 - All source code (`.venv` uses Python 3.13.3, system Python is 3.14.3)
- YAML - Skill frontmatter parsing (inline, no YAML library dependency)
- JSON/JSONL - Dataset serialization, session import formats
## Runtime
- CPython 3.13.3 (virtualenv at `.venv/`)
- Minimum supported: Python 3.10 (declared in `pyproject.toml`)
- pip + setuptools (build-system requires `setuptools>=68.0`, `wheel`)
- Lockfile: **missing** - no `requirements.txt`, `poetry.lock`, or `uv.lock`
## Frameworks
- DSPy `>=3.0.0` - LLM programming framework; provides `dspy.Module`, `dspy.Signature`, `dspy.ChainOfThought`, `dspy.GEPA`, `dspy.MIPROv2`, `dspy.LM`, `dspy.Example`, `dspy.Prediction`
- Click `>=8.0` - CLI framework for `evolve_skill.py` and `external_importers.py`
- pytest `>=7.0` - Test runner (configured in `pyproject.toml` `[tool.pytest.ini_options]`)
- pytest-asyncio `>=0.21` - Async test support (dev dependency)
- setuptools `>=68.0` - Build backend
- wheel - Wheel distribution support
## Key Dependencies
- `dspy>=3.0.0` - Core optimization engine; defines all LLM interactions, optimization loops (GEPA/MIPROv2), and module abstractions. Used in `evolution/core/fitness.py`, `evolution/core/dataset_builder.py`, `evolution/core/external_importers.py`, `evolution/skills/skill_module.py`, `evolution/skills/evolve_skill.py`
- `openai>=1.0.0` - OpenAI-compatible API client; used transitively through DSPy's `dspy.LM()` for model access
- `pyyaml>=6.0` - YAML parsing (declared dependency, though current code does manual YAML frontmatter parsing)
- `click>=8.0` - CLI argument parsing in `evolution/skills/evolve_skill.py` and `evolution/core/external_importers.py`
- `rich>=13.0` - Terminal output formatting (Console, Panel, Table, Progress bars) throughout the codebase
- `darwinian-evolver` - Code evolution engine (Phase 4, AGPL v3 licensed). Installed via `pip install .[darwinian]`
- `reportlab` - PDF generation in `generate_report.py` (not declared in `pyproject.toml` dependencies)
## Configuration
- `HERMES_AGENT_REPO` env var - Path to the hermes-agent repository (see `evolution/core/config.py` lines 55-56)
- Falls back to `~/.hermes/hermes-agent` or `../hermes-agent` sibling directory
- LLM API keys are required by DSPy/OpenAI but managed externally (e.g., `OPENAI_API_KEY`, `OPENROUTER_API_KEY`)
- Optimizer model: `openai/gpt-4.1` (GEPA reflections)
- Eval model: `openai/gpt-4.1-mini` (LLM-as-judge scoring)
- Judge model: `openai/gpt-4.1` (dataset generation)
- CLI default for external importers: `openrouter/google/gemini-2.5-flash`
- `pyproject.toml` - Single source of truth for project metadata, dependencies, build config, and pytest config
- Package discovery: `[tool.setuptools.packages.find]` includes `evolution*`
- Max skill size: 15,000 chars
- Max tool description: 500 chars
- Max param description: 200 chars
- Max prompt growth: 20% over baseline
- Eval dataset: 20 examples, split 50/25/25 train/val/holdout
## Platform Requirements
- Python >=3.10
- Access to LLM APIs (OpenAI, OpenRouter, or compatible)
- Access to a hermes-agent repository checkout (for skill files)
- No GPU required - all optimization via API calls
- Same as development - this is a CLI tool, not a deployed service
- Typical optimization run costs $2-10 in API credits
- Optimization time: 60 seconds (BootstrapFewShot) to 15-30 minutes (GEPA)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Use `snake_case.py` for all Python modules: `dataset_builder.py`, `evolve_skill.py`, `external_importers.py`
- Test files use `test_` prefix: `test_constraints.py`, `test_external_importers.py`, `test_skill_module.py`
- Top-level scripts are `snake_case.py`: `generate_report.py`
- Use `snake_case` for all functions and methods: `load_skill()`, `find_skill()`, `validate_all()`
- Private/internal functions prefixed with underscore: `_check_size()`, `_parse_scoring_json()`, `_contains_secret()`, `_is_relevant_to_skill()`
- Static methods and class methods follow the same pattern: `extract_messages()`, `from_dict()`, `to_dict()`
- Use `snake_case` for all variables: `skill_text`, `eval_model`, `max_examples`
- Constants use `UPPER_SNAKE_CASE`: `SECRET_PATTERNS`, `VALID_DIFFICULTIES`, `MIN_DATASET_SIZE`, `HISTORY_PATH`, `SESSION_DIR`
- Numeric constants use underscores for readability: `15_000`, `20_000`
- Use `PascalCase`: `EvolutionConfig`, `ConstraintValidator`, `ConstraintResult`, `EvalExample`, `SyntheticDatasetBuilder`
- DSPy Signature classes are nested inside their parent class as inner classes: `class GenerateTestCases(dspy.Signature)` inside `SyntheticDatasetBuilder`
- Use `PascalCase` for dataclasses and type names: `FitnessScore`, `EvalDataset`, `ConstraintResult`
## Code Style
- No formatter configuration detected (no `.prettierrc`, `pyproject.toml [tool.black]`, `ruff.toml`, etc.)
- Indent: 4 spaces (standard Python)
- Line length: generally under 120 characters, no hard enforcement
- Trailing commas used in multi-line function calls and data structures
- No linter configuration detected (no `.flake8`, `ruff.toml`, `[tool.ruff]`, or `[tool.pylint]` in `pyproject.toml`)
- Code follows PEP 8 conventions organically
- Use modern Python type hints throughout: `list[ConstraintResult]`, `dict[str, int]`, `Optional[str]`
- Use `from typing import Optional` for optional parameters
- Return types specified on public functions; sometimes omitted on private helpers
- Dataclass fields use type annotations: `passed: bool`, `constraint_name: str`
## Import Organization
- Use `from X import Y` for specific items (preferred over `import X` for local modules)
- Group related imports on separate lines
- Separate groups with a blank line
- Example from `evolution/skills/evolve_skill.py`:
- No path aliases used. All imports use full module paths from the `evolution` package root.
## Module Docstrings
- `evolution/core/constraints.py`: Explains the constraint validation philosophy (all-or-nothing)
- `evolution/core/external_importers.py`: Documents supported sources, CLI usage, and programmatic usage
- `evolution/core/fitness.py`: Explains the LLM-as-judge approach and scoring dimensions
## Class Design
- Use `@dataclass` for plain data objects: `EvolutionConfig`, `ConstraintResult`, `EvalExample`, `FitnessScore`
- Use `field(default_factory=...)` for mutable defaults
- Include `to_dict()` and `from_dict()` classmethods for serialization when needed
- Use regular classes for stateful components: `ConstraintValidator`, `LLMJudge`, `RelevanceFilter`
- Constructor takes config/dependencies: `def __init__(self, config: EvolutionConfig)`
- DSPy modules inherit from `dspy.Module`: `class SkillModule(dspy.Module)`
- Define DSPy `Signature` classes as nested inner classes of their consuming class
- Pattern used in `evolution/core/dataset_builder.py`, `evolution/core/fitness.py`, `evolution/core/external_importers.py`, `evolution/skills/skill_module.py`
## Error Handling
- Raise specific exceptions with descriptive messages for unrecoverable errors:
- Use `try/except` with bare `Exception` for resilient parsing (e.g., JSON from LLM output):
- Return neutral/default values on parse failure rather than crashing:
- Use `ConstraintResult` dataclass to represent pass/fail without exceptions
- CLI commands use `sys.exit(1)` or `raise SystemExit(1)` for user-facing errors
- Process errors are logged via `rich.console` and counted (error rate tracking in `RelevanceFilter`)
## Logging
- Create a module-level console: `console = Console()` (in `evolution/core/external_importers.py`, `evolution/skills/evolve_skill.py`)
- Use Rich markup for colored output: `[bold cyan]`, `[red]`, `[green]`, `[yellow]`
- Use `console.print()` for all output, never bare `print()` (except in `generate_report.py`)
- Progress bars via `rich.progress.Progress` for long-running operations
- Tables via `rich.table.Table` for structured results display
- No logging framework (`logging` module) is used
## Comments
- Section separators using unicode box-drawing comments:
- Inline comments for non-obvious decisions: `# Penalty ramps from 0 at 90% to 0.3 at 100%+`
- Step numbering in orchestration functions: `# ── 1. Find and load the skill ──`
- All public classes and functions have docstrings
- Use Google-style docstring format with `Args:` and `Returns:` sections
- Private methods have shorter docstrings or none
## Function Design
- Use keyword arguments with defaults for optional config: `num_cases: Optional[int] = None`
- Use `click.option` decorators for CLI parameters
- Config objects passed as single parameter rather than many individual args
- Use dataclasses for structured returns: `ConstraintResult`, `FitnessScore`, `EvalDataset`
- Use `Optional[X]` when a function may not find a result: `find_skill() -> Optional[Path]`
- Use `list[X]` for collection returns
- Properties for computed values: `@property def composite(self) -> float`
## CLI Design
- `@click.command()` decorator on `main()` function
- `@click.option()` for each parameter with help text
- Guard `if __name__ == "__main__": main()`
- Modules runnable via `python -m evolution.module.name`
- Separate the CLI entry point (`main`) from the business logic function (`evolve()`)
## Serialization
- Use JSONL (one JSON object per line) for datasets: `train.jsonl`, `val.jsonl`, `holdout.jsonl`
- Use `json.dumps(obj) + "\n"` for writing, line-by-line `json.loads()` for reading
- Use `json.dumps(metrics, indent=2)` for human-readable config/metrics files
- Dataclasses provide `to_dict()` / `from_dict()` methods for JSON serialization
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- Standalone optimization pipeline that operates on an external repository (hermes-agent)
- DSPy-based module system where text artifacts become optimizable parameters
- Multi-phase design: only Phase 1 (skill evolution) is implemented; Phases 2-5 are placeholder packages
- All optimization happens via LLM API calls -- no GPU training involved
- Strict constraint gating: every evolved variant must pass validators before acceptance
## Layers
- Purpose: Define optimization parameters, discover the hermes-agent repo
- Location: `evolution/core/config.py`
- Contains: `EvolutionConfig` dataclass, `get_hermes_agent_path()` discovery function
- Depends on: Environment variables (`HERMES_AGENT_REPO`), filesystem
- Used by: All other layers
- Purpose: Build and manage evaluation datasets from multiple sources
- Location: `evolution/core/dataset_builder.py`, `evolution/core/external_importers.py`
- Contains: `EvalExample`, `EvalDataset`, `SyntheticDatasetBuilder`, `GoldenDatasetLoader`, session importers (Claude Code, Copilot, Hermes)
- Depends on: DSPy (for synthetic generation), external session files on disk
- Used by: Orchestration layer (`evolve_skill.py`)
- Purpose: Score agent outputs using LLM-as-judge and heuristic metrics
- Location: `evolution/core/fitness.py`
- Contains: `FitnessScore`, `LLMJudge`, `skill_fitness_metric()` (DSPy-compatible metric)
- Depends on: DSPy, config
- Used by: Optimization loop in `evolve_skill.py`
- Purpose: Hard-gate validation of evolved artifacts (size, growth, structure, tests)
- Location: `evolution/core/constraints.py`
- Contains: `ConstraintValidator`, `ConstraintResult`
- Depends on: Config, subprocess (for running pytest on hermes-agent)
- Used by: Orchestration layer -- both baseline validation and post-evolution gating
- Purpose: Wrap hermes-agent artifacts as DSPy modules for optimization
- Location: `evolution/skills/skill_module.py`
- Contains: `SkillModule` (DSPy Module subclass), `load_skill()`, `find_skill()`, `reassemble_skill()`
- Depends on: DSPy
- Used by: Orchestration layer
- Purpose: End-to-end evolution pipeline with CLI interface
- Location: `evolution/skills/evolve_skill.py`
- Contains: `evolve()` function, Click CLI
- Depends on: All other layers
- Used by: End users via `python -m evolution.skills.evolve_skill`
- Purpose: Generate PDF validation reports
- Location: `generate_report.py`
- Contains: ReportLab-based PDF generation
- Depends on: ReportLab (not in core dependencies)
- Used by: Manual execution for documentation
## Data Flow
- No persistent state between runs -- each evolution run is independent
- Eval datasets can be saved to `datasets/skills/<name>/` for reuse
- Evolution output (evolved artifacts, metrics) saved to `output/` directory
- The hermes-agent repo is read-only during evolution; changes are proposed as PRs
## Key Abstractions
- Purpose: Makes a SKILL.md file optimizable by DSPy
- Examples: `evolution/skills/skill_module.py` lines 84-114
- Pattern: The skill body text is the parameter; `forward()` uses it as instructions for a `ChainOfThought` predictor. GEPA/MIPROv2 can mutate the instructions to maximize the fitness metric.
- Purpose: Standardized evaluation data with train/val/holdout splits
- Examples: `evolution/core/dataset_builder.py` lines 21-86
- Pattern: Dataclass with `to_dict()`/`from_dict()` serialization, JSONL persistence, and `to_dspy_examples()` conversion
- Purpose: Hard-gate validation ensuring evolved artifacts are safe to deploy
- Examples: `evolution/core/constraints.py` lines 15-174
- Pattern: Each check returns a `ConstraintResult` with passed/failed status + message. `validate_all()` runs all applicable checks. Failures cause immediate rejection.
- Purpose: Multi-dimensional quality scoring for agent outputs
- Examples: `evolution/core/fitness.py` lines 14-105
- Pattern: Weighted composite of correctness (0.5), procedure_following (0.3), conciseness (0.2) minus length penalty. `skill_fitness_metric()` is a fast heuristic proxy used during optimization; `LLMJudge` provides full rubric-based scoring.
- Purpose: Extract real user messages from external AI tool history
- Examples: `ClaudeCodeImporter`, `CopilotImporter`, `HermesSessionImporter` in `evolution/core/external_importers.py`
- Pattern: Static `extract_messages()` method reads from standard filesystem paths, filters secrets, returns normalized dicts
## Entry Points
- Location: `evolution/skills/evolve_skill.py` lines 296-323
- Triggers: User CLI invocation
- Responsibilities: Full skill evolution pipeline (load, dataset, optimize, validate, evaluate, save)
- Location: `evolution/core/external_importers.py` lines 729-785
- Triggers: User CLI invocation
- Responsibilities: Import session data from external tools, filter for relevance, generate eval datasets
- Location: `generate_report.py`
- Triggers: Manual execution
- Responsibilities: Generate Phase 1 validation report PDF
## Error Handling
- CLI entry points use `sys.exit(1)` on critical failures (skill not found, no eval data)
- DSPy optimizer failures trigger fallback: GEPA -> MIPROv2 (`evolve_skill.py` lines 156-177)
- JSON parsing from LLM output uses two-stage strategy: try `json.loads()`, fall back to brace-counting extraction (`_parse_scoring_json()`)
- Score parsing clamps to [0.0, 1.0] range with 0.5 default on failure (`_parse_score()`)
- Secret detection silently skips messages containing potential API keys/tokens
- Session file read errors are silently skipped (continue to next file)
- Constraint validation failures on the baseline emit a warning but proceed; failures on evolved output cause rejection
## Cross-Cutting Concerns
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
