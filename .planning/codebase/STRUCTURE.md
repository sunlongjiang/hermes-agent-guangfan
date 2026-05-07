# Directory Structure

**Analysis Date:** 2026-05-06

## Top-Level Layout

```
hermes-agent-self-evolution/
├── .claude/                   # Claude Code project configs
├── .planning/                 # GSD planning artifacts (see below)
├── .venv/                     # Local CPython 3.13.3 virtualenv (gitignored)
├── .gitignore
├── .idea/                     # JetBrains project config (gitignored-by-convention)
├── CLAUDE.md                  # Agent instructions (project-level)
├── PLAN.md                    # Top-level v1 plan snapshot (legacy — pre-GSD)
├── README.md                  # User-facing pipeline docs + usage
├── pyproject.toml             # Single source of truth for deps/build/pytest config
├── evolution.yaml             # Multi-model backend config (gitignored, contains keys)
├── evolution.example.yaml     # Safe template for evolution.yaml
├── generate_report.py         # Standalone PDF report script (outside evolution/ pkg)
├── evolution/                 # Main Python package — the pipeline code
├── tests/                     # Test tree (mirrors evolution/)
├── datasets/                  # Cached eval datasets (gitignored .jsonl)
├── output/                    # Per-run evolution artifacts (NOT gitignored — see CONCERNS H4)
└── reports/                   # Manual PDF reports from generate_report.py
```

---

## `evolution/` Package

```
evolution/
├── __init__.py
├── core/                      # Shared infrastructure (used by all pipelines)
│   ├── __init__.py
│   ├── config.py              # EvolutionConfig + get_hermes_agent_path + YAML/env/CLI override layer
│   ├── constraints.py         # ConstraintValidator + ConstraintResult (size/growth/non-empty/structure)
│   ├── dataset_builder.py     # EvalExample, EvalDataset, SyntheticDatasetBuilder, GoldenDatasetLoader
│   ├── external_importers.py  # ClaudeCode/Copilot/Hermes session importers + RelevanceFilter + CLI
│   └── fitness.py             # FitnessScore + LLMJudge + skill_fitness_metric (heuristic proxy)
│
├── skills/                    # Phase 1 — skill SKILL.md evolution
│   ├── __init__.py
│   ├── evolve_skill.py        # CLI entry point `python -m evolution.skills.evolve_skill`
│   └── skill_module.py        # SkillModule(dspy.Module) wrapping a single SKILL.md
│
├── tools/                     # Phases 2-5 — tool description evolution
│   ├── __init__.py
│   ├── tool_loader.py         # AST+regex extraction, ToolDescription/ToolParam dataclasses, write-back
│   ├── tool_module.py         # ToolModule(dspy.Module) — one dspy.Predict per tool description
│   ├── tool_dataset.py        # ToolSelectionExample/Dataset, ToolDatasetBuilder (synthetic + confuser)
│   ├── tool_metric.py         # tool_selection_metric (binary), CrossToolRegressionChecker
│   ├── tool_constraints.py    # ToolFactualChecker (LLM-based accuracy gate)
│   └── evolve_tool_descriptions.py  # CLI entry point
│
├── prompts/                   # Phases 7-10 — prompt_builder.py section evolution
│   ├── __init__.py
│   ├── prompt_loader.py       # AST extraction of 5 sections + write-back preserving structure
│   ├── prompt_module.py       # PromptModule(dspy.Module) — per-section optimization with frozen context
│   ├── prompt_dataset.py      # Behavioral scenarios per section (80 total across 5 sections)
│   ├── prompt_metric.py       # PromptBehavioralMetric — heuristic + full-LLM scoring paths
│   ├── prompt_constraints.py  # PromptRoleChecker (LLM role preservation gate)
│   └── evolve_prompt_sections.py   # CLI entry point
│
├── code/                      # Phase 21 placeholder (Darwinian code evolution) — empty package
│   └── __init__.py
└── monitor/                   # Phase 22 placeholder (continuous evolution loop) — empty package
    └── __init__.py
```

### Key locations

- **CLI entry points** (always `evolve_*.py`): `evolution/skills/evolve_skill.py`, `evolution/tools/evolve_tool_descriptions.py`, `evolution/prompts/evolve_prompt_sections.py`, `evolution/core/external_importers.py` (session import CLI)
- **DSPy module wrappers**: `evolution/skills/skill_module.py`, `evolution/tools/tool_module.py`, `evolution/prompts/prompt_module.py` — each inherits `dspy.Module`; the wrapped text artifact becomes a GEPA-optimizable parameter
- **Dataset classes**: per-pipeline builders in each subpackage; shared base patterns in `evolution/core/dataset_builder.py`
- **Fitness/metric**: `evolution/core/fitness.py` provides `LLMJudge` + heuristic `skill_fitness_metric`; tool/prompt pipelines each have domain-specific metric modules
- **Constraints**: shared base `ConstraintValidator` in `evolution/core/constraints.py`; per-pipeline LLM-based checkers in `tool_constraints.py` / `prompt_constraints.py`
- **Config**: single dataclass `EvolutionConfig` in `evolution/core/config.py` with `.load()` classmethod implementing YAML → env → CLI precedence

---

## `tests/` Tree

Mirrors the `evolution/` layout. Tests are NOT co-located with source.

```
tests/
├── __init__.py
├── core/
│   ├── __init__.py
│   ├── test_constraints.py             # 16 tests
│   └── test_external_importers.py      # 116 tests (largest suite)
├── skills/
│   ├── __init__.py
│   └── test_skill_module.py            # 7 tests
├── tools/
│   ├── __init__.py
│   ├── test_evolve_tool_descriptions.py  # 4 tests (CLI surface)
│   ├── test_tool_constraints.py          # 21 tests
│   ├── test_tool_dataset.py              # 16 tests
│   ├── test_tool_loader.py               # 40 tests (real-hermes skip-gated)
│   ├── test_tool_metric.py               # 17 tests
│   └── test_tool_module.py               # 9 tests
└── prompts/
    ├── __init__.py
    ├── test_evolve_prompt_sections.py  # 6 tests (CLI surface)
    ├── test_prompt_constraints.py      # 25 tests
    ├── test_prompt_dataset.py          # 15 tests
    ├── test_prompt_loader.py           # 9 tests
    ├── test_prompt_metric.py           # 14 tests
    └── test_prompt_module.py           # 14 tests
```

Total: 15 test files, 329 tests. See `TESTING.md` for detailed coverage.

**Coverage gap directories:** no `tests/skills/test_evolve_skill.py`, no `tests/core/test_config.py`, no `tests/core/test_dataset_builder.py`, no `tests/core/test_fitness.py` — see CONCERNS L2 / `TESTING.md` § Coverage gaps.

---

## `.planning/` (GSD Artifacts)

```
.planning/
├── PROJECT.md                 # Project vision, validated/active/out-of-scope requirements
├── REQUIREMENTS.md            # Full requirement list + traceability matrix (phase → requirement)
├── ROADMAP.md                 # Phase plan with success criteria (v1 milestone + v2.0 milestone)
├── STATE.md                   # Current position (milestone/phase/plan), progress bars, session continuity
├── config.json                # GSD workflow toggles
├── codebase/                  # ← This set of documents (STACK/ARCHITECTURE/STRUCTURE/CONVENTIONS/TESTING/INTEGRATIONS/CONCERNS)
├── research/                  # v2 research artifacts (STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md, SUMMARY.md)
└── phases/                    # Per-phase plan/research/context/verification folders
    ├── 02-tool-loading/
    ├── 03-tool-module/
    ├── 04-tool-dataset-evaluation/
    ├── 05-tool-constraints-cli/
    ├── 06-tool-pipeline-tests/     # SKIPPED — no source files
    ├── 07-prompt-loading/
    ├── 08-prompt-module/
    ├── 09-prompt-evaluation/
    ├── 10-prompt-constraints-cli/
    ├── 11-prompt-pipeline-tests/   # SKIPPED — no source files
    └── 12-v1-stabilization/
```

**Phase numbering:** Continuous across milestones — v2.0 starts at Phase 13 (not reset). Phase 01 is the Phase 1 skill pipeline (complete, predates this .planning directory structure).

Each active phase folder contains some subset of:
- `<NN>-CONTEXT.md` — discussion artifact (decisions for downstream agents)
- `<NN>-RESEARCH.md` — how-to-implement research
- `<NN>-<MM>-PLAN.md` — one plan per sub-task (0-indexed within phase)
- `<NN>-<MM>-SUMMARY.md` — execution summary
- `<NN>-VALIDATION.md` — Nyquist validation report
- `<NN>-VERIFICATION.md` — goal-backward verification
- `<NN>-REVIEW.md` / `<NN>-REVIEW-FIX.md` — code review and fixes

---

## Runtime / Output Directories

```
datasets/
├── skills/<skill-name>/       # Cached skill eval datasets (train/val/holdout.jsonl)
├── tools/                     # Cached tool selection datasets
└── prompts/                   # Cached prompt behavioral datasets
```

All `*.jsonl` files under `datasets/` are gitignored (`datasets/**/*.jsonl`).

```
output/                        # ⚠️ NOT in .gitignore — see CONCERNS.md H4
├── skills/<skill-name>/<YYYYMMDD_HHMMSS>/   # Per-run artifacts
├── tools/<YYYYMMDD_HHMMSS>/
└── prompts/<YYYYMMDD_HHMMSS>/
```

Each run directory contains:
- `evolved_*.json` — the evolved artifact (tool descriptions, skill text, prompt sections)
- `metrics.json` — baseline_score, evolved_score, iterations, elapsed_seconds, constraints_passed
- `diff.txt` — unified diff between baseline and evolved text
- Occasionally `FAILED_<timestamp>/` directories with failure metadata

```
reports/
└── <name>.pdf                 # Manual PDF reports from generate_report.py
```

---

## Naming Conventions (Cross-Repo)

### Source modules

- `snake_case.py` for all Python modules: `dataset_builder.py`, `evolve_skill.py`, `external_importers.py`
- Test files: `test_<source-module>.py` (1:1 with source)
- CLI entry points: `evolve_<artifact>.py` (e.g. `evolve_skill.py`, `evolve_tool_descriptions.py`, `evolve_prompt_sections.py`)
- Standalone scripts at repo root: `snake_case.py` (e.g. `generate_report.py`)

### Functions and variables

- `snake_case` for all functions, methods, variables
- `_private` underscore prefix for module-internal helpers
- Static methods and class methods follow the same pattern

### Constants

- `UPPER_SNAKE_CASE`: `SECRET_PATTERNS`, `VALID_DIFFICULTIES`, `MIN_DATASET_SIZE`, `HISTORY_PATH`, `SESSION_DIR`
- Numeric underscores for readability: `15_000`, `20_000`

### Classes and types

- `PascalCase`: `EvolutionConfig`, `ConstraintValidator`, `ConstraintResult`, `EvalExample`, `SyntheticDatasetBuilder`, `ToolDescription`, `ToolParam`
- DSPy `Signature` classes are nested as **inner classes** of their consuming class (e.g. `class GenerateTestCases(dspy.Signature)` inside `SyntheticDatasetBuilder`)

### Phase artifact naming

- Phase folders: `<NN>-<kebab-case-slug>/` where `NN` is zero-padded phase number
- Plan files: `<NN>-<MM>-PLAN.md` (MM = plan index within phase)

---

## Where Phase 13 Work Lands

**Extension target:** `evolution/tools/` subpackage (not a new subdirectory).

Per-parameter description optimization (TOOL-V2-02) extends these existing files:

| File | Extension |
|------|-----------|
| `evolution/tools/tool_module.py` | Add per-parameter `dspy.Predict` alongside the existing per-tool predictors |
| `evolution/tools/tool_dataset.py` | Extend `ToolSelectionExample` usage to exercise `correct_params` |
| `evolution/tools/tool_metric.py` | Add per-param accuracy subscore; `CrossToolRegressionChecker` may gain persistence |
| `evolution/tools/tool_constraints.py` | Wire `max_param_desc_size` (200 chars) per-param check (already supported in base `_check_size`) |
| `evolution/tools/evolve_tool_descriptions.py` | Add `--granularity tool|param|both` flag (per v2 research FEATURES.md) |
| `evolution/tools/tool_loader.py` | `ToolParam.description` field already exists; `write_back_description(param_name=...)` already supports per-param write |

**No new top-level directories** — Phase 13 is a fan-out within the existing tools pipeline.

---

## Files Referenced

- `/Users/slj/项目/hermes-agent-self-evolution/pyproject.toml`
- `/Users/slj/项目/hermes-agent-self-evolution/CLAUDE.md`
- `/Users/slj/项目/hermes-agent-self-evolution/README.md`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/core/config.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/core/constraints.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/core/dataset_builder.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/core/external_importers.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/core/fitness.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/skills/evolve_skill.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/skills/skill_module.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/tools/evolve_tool_descriptions.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/tools/tool_constraints.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/tools/tool_dataset.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/tools/tool_loader.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/tools/tool_metric.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/tools/tool_module.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/prompts/evolve_prompt_sections.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/prompts/prompt_constraints.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/prompts/prompt_dataset.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/prompts/prompt_loader.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/prompts/prompt_metric.py`
- `/Users/slj/项目/hermes-agent-self-evolution/evolution/prompts/prompt_module.py`
- `/Users/slj/项目/hermes-agent-self-evolution/generate_report.py`
- `/Users/slj/项目/hermes-agent-self-evolution/.planning/ROADMAP.md`
- `/Users/slj/项目/hermes-agent-self-evolution/.planning/research/FEATURES.md`

---

*Structure analysis: 2026-05-06*
