# Codebase Structure

**Analysis Date:** 2026-04-15

## Directory Layout

```
hermes-agent-self-evolution/
├── evolution/                  # Main Python package — all evolution logic
│   ├── __init__.py             # Package root, exports __version__
│   ├── core/                   # Shared infrastructure (config, data, fitness, constraints)
│   │   ├── __init__.py         # Re-exports EvolutionConfig, get_hermes_agent_path
│   │   ├── config.py           # EvolutionConfig dataclass + repo discovery
│   │   ├── constraints.py      # ConstraintValidator — hard-gate checks
│   │   ├── dataset_builder.py  # EvalExample, EvalDataset, SyntheticDatasetBuilder
│   │   ├── external_importers.py  # Session importers (Claude Code, Copilot, Hermes) + CLI
│   │   └── fitness.py          # FitnessScore, LLMJudge, skill_fitness_metric
│   ├── skills/                 # Phase 1: Skill evolution (IMPLEMENTED)
│   │   ├── __init__.py
│   │   ├── evolve_skill.py     # Main CLI + evolve() orchestrator
│   │   └── skill_module.py     # SkillModule (DSPy Module), load/find/reassemble helpers
│   ├── tools/                  # Phase 2: Tool description evolution (PLACEHOLDER)
│   │   └── __init__.py
│   ├── prompts/                # Phase 3: System prompt evolution (PLACEHOLDER)
│   │   └── __init__.py
│   ├── code/                   # Phase 4: Code evolution (PLACEHOLDER)
│   │   └── __init__.py
│   └── monitor/                # Phase 5: Continuous improvement (PLACEHOLDER)
│       └── __init__.py
├── datasets/                   # Eval dataset storage (JSONL, gitignored)
│   ├── skills/                 # Per-skill eval datasets
│   │   └── .gitkeep
│   └── tools/                  # Per-tool eval datasets
│       └── .gitkeep
├── tests/                      # Pytest test suite
│   ├── __init__.py
│   ├── core/                   # Tests for evolution/core/
│   │   ├── __init__.py
│   │   ├── test_constraints.py
│   │   └── test_external_importers.py
│   └── skills/                 # Tests for evolution/skills/
│       ├── __init__.py
│       └── test_skill_module.py
├── reports/                    # Generated reports (PDFs)
│   └── phase1_validation_report.pdf
├── generate_report.py          # Standalone report generator (uses ReportLab)
├── pyproject.toml              # Project metadata, dependencies, pytest config
├── PLAN.md                     # Full project plan (40KB)
├── README.md                   # Project overview and quick start
└── .gitignore                  # Ignores datasets/*.jsonl, .venv, .env, snapshots, IDE
```

## Directory Purposes

**`evolution/`:**
- Purpose: All evolution logic as a single installable Python package
- Contains: Core infrastructure + phase-specific subpackages
- Key files: `evolution/__init__.py` (version), `evolution/core/` (shared), `evolution/skills/` (Phase 1)

**`evolution/core/`:**
- Purpose: Shared infrastructure used by all evolution phases
- Contains: Configuration, dataset building, fitness evaluation, constraint validation, external importers
- Key files: `config.py`, `dataset_builder.py`, `external_importers.py`, `fitness.py`, `constraints.py`

**`evolution/skills/`:**
- Purpose: Phase 1 implementation — evolve SKILL.md files
- Contains: DSPy module wrapper, skill loader, main CLI orchestrator
- Key files: `evolve_skill.py` (entry point), `skill_module.py` (DSPy module)

**`evolution/tools/`, `evolution/prompts/`, `evolution/code/`, `evolution/monitor/`:**
- Purpose: Placeholder packages for Phases 2-5
- Contains: Only `__init__.py` with docstring
- Key files: None yet — these are empty stubs

**`datasets/`:**
- Purpose: Store evaluation datasets per skill/tool (JSONL files)
- Contains: `skills/` and `tools/` subdirectories, both empty with `.gitkeep`
- Generated: Yes — created by dataset builders and importers
- Committed: No — JSONL/JSON files are gitignored

**`tests/`:**
- Purpose: Pytest test suite mirroring `evolution/` structure
- Contains: Unit tests for core and skills modules
- Key files: `tests/core/test_constraints.py`, `tests/core/test_external_importers.py`, `tests/skills/test_skill_module.py`

**`reports/`:**
- Purpose: Generated PDF validation reports
- Contains: Phase 1 validation report
- Generated: Yes — via `generate_report.py`
- Committed: Yes — the PDF is tracked in git

## Key File Locations

**Entry Points:**
- `evolution/skills/evolve_skill.py`: Main CLI for skill evolution (`python -m evolution.skills.evolve_skill`)
- `evolution/core/external_importers.py`: CLI for session import (`python -m evolution.core.external_importers`)
- `generate_report.py`: Standalone report generator (`python generate_report.py`)

**Configuration:**
- `pyproject.toml`: Project metadata, dependencies, pytest config
- `evolution/core/config.py`: Runtime configuration (`EvolutionConfig` dataclass)
- `.gitignore`: Defines what is not committed (datasets, snapshots, venv)

**Core Logic:**
- `evolution/core/dataset_builder.py`: Eval dataset generation and management
- `evolution/core/external_importers.py`: Session importers + relevance filtering (largest file, 785 lines)
- `evolution/core/fitness.py`: Fitness scoring (LLM-as-judge + heuristic)
- `evolution/core/constraints.py`: Constraint validation gates
- `evolution/skills/skill_module.py`: DSPy module wrapper for skills

**Testing:**
- `tests/core/test_constraints.py`: Constraint validator tests
- `tests/core/test_external_importers.py`: External importer tests (comprehensive)
- `tests/skills/test_skill_module.py`: Skill module tests

## Naming Conventions

**Files:**
- Snake case for all Python files: `evolve_skill.py`, `dataset_builder.py`
- Test files prefixed with `test_`: `test_constraints.py`, `test_external_importers.py`
- Constants files are uppercase: `SKILL.md`, `PLAN.md`

**Directories:**
- Snake case for Python packages: `evolution/core/`, `evolution/skills/`
- Lowercase for data directories: `datasets/`, `reports/`
- Test directories mirror source structure: `tests/core/` mirrors `evolution/core/`

**Modules:**
- Each `__init__.py` has a docstring describing the package's purpose/phase
- Core `__init__.py` re-exports key symbols: `EvolutionConfig`, `get_hermes_agent_path`

## Where to Add New Code

**New Evolution Phase (e.g., Phase 2 - Tool Descriptions):**
- Implementation: `evolution/tools/` (stub already exists)
- Add modules following the Phase 1 pattern:
  - `evolution/tools/tool_module.py` — DSPy module wrapping tool descriptions
  - `evolution/tools/evolve_tool.py` — CLI orchestrator
- Tests: `tests/tools/test_tool_module.py`
- Datasets: `datasets/tools/<tool_name>/` (directory exists)

**New Core Infrastructure:**
- Implementation: `evolution/core/<module_name>.py`
- Tests: `tests/core/test_<module_name>.py`
- Re-export in `evolution/core/__init__.py` if it's a key public symbol

**New Session Importer:**
- Add a new class in `evolution/core/external_importers.py` following the `ClaudeCodeImporter` / `CopilotImporter` / `HermesSessionImporter` pattern
- Register in the `importers` dict in `build_dataset_from_external()` (line 632)
- Add to CLI `--source` choices (line 731)

**New Constraint:**
- Add method to `ConstraintValidator` in `evolution/core/constraints.py`
- Call it from `validate_all()` method
- Add test class in `tests/core/test_constraints.py`

**New Fitness Dimension:**
- Add field to `FitnessScore` dataclass in `evolution/core/fitness.py`
- Update `composite` property weights
- Add field to `LLMJudge.JudgeSignature`

**Utilities/Helpers:**
- If specific to a phase: add to that phase's package
- If shared across phases: add to `evolution/core/`

## Special Directories

**`output/` (not in repo):**
- Purpose: Evolution run outputs (evolved skills, metrics, baselines)
- Generated: Yes — created at runtime by `evolve_skill.py`
- Committed: No — not in .gitignore but not tracked
- Structure: `output/<skill_name>/<timestamp>/` with `evolved_skill.md`, `baseline_skill.md`, `metrics.json`

**`snapshots/` (not in repo):**
- Purpose: DSPy optimization snapshots (pickled state)
- Generated: Yes — by DSPy during optimization
- Committed: No — explicitly gitignored

**`.venv/`:**
- Purpose: Python virtual environment
- Generated: Yes
- Committed: No

---

*Structure analysis: 2026-04-15*
