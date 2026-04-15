# Architecture

**Analysis Date:** 2026-04-15

## Pattern Overview

**Overall:** Pipeline architecture with evolutionary optimization loop

**Key Characteristics:**
- Standalone optimization pipeline that operates on an external repository (hermes-agent)
- DSPy-based module system where text artifacts become optimizable parameters
- Multi-phase design: only Phase 1 (skill evolution) is implemented; Phases 2-5 are placeholder packages
- All optimization happens via LLM API calls -- no GPU training involved
- Strict constraint gating: every evolved variant must pass validators before acceptance

## Layers

**Configuration Layer:**
- Purpose: Define optimization parameters, discover the hermes-agent repo
- Location: `evolution/core/config.py`
- Contains: `EvolutionConfig` dataclass, `get_hermes_agent_path()` discovery function
- Depends on: Environment variables (`HERMES_AGENT_REPO`), filesystem
- Used by: All other layers

**Data Layer:**
- Purpose: Build and manage evaluation datasets from multiple sources
- Location: `evolution/core/dataset_builder.py`, `evolution/core/external_importers.py`
- Contains: `EvalExample`, `EvalDataset`, `SyntheticDatasetBuilder`, `GoldenDatasetLoader`, session importers (Claude Code, Copilot, Hermes)
- Depends on: DSPy (for synthetic generation), external session files on disk
- Used by: Orchestration layer (`evolve_skill.py`)

**Fitness Layer:**
- Purpose: Score agent outputs using LLM-as-judge and heuristic metrics
- Location: `evolution/core/fitness.py`
- Contains: `FitnessScore`, `LLMJudge`, `skill_fitness_metric()` (DSPy-compatible metric)
- Depends on: DSPy, config
- Used by: Optimization loop in `evolve_skill.py`

**Constraint Layer:**
- Purpose: Hard-gate validation of evolved artifacts (size, growth, structure, tests)
- Location: `evolution/core/constraints.py`
- Contains: `ConstraintValidator`, `ConstraintResult`
- Depends on: Config, subprocess (for running pytest on hermes-agent)
- Used by: Orchestration layer -- both baseline validation and post-evolution gating

**Module Layer:**
- Purpose: Wrap hermes-agent artifacts as DSPy modules for optimization
- Location: `evolution/skills/skill_module.py`
- Contains: `SkillModule` (DSPy Module subclass), `load_skill()`, `find_skill()`, `reassemble_skill()`
- Depends on: DSPy
- Used by: Orchestration layer

**Orchestration Layer:**
- Purpose: End-to-end evolution pipeline with CLI interface
- Location: `evolution/skills/evolve_skill.py`
- Contains: `evolve()` function, Click CLI
- Depends on: All other layers
- Used by: End users via `python -m evolution.skills.evolve_skill`

**Report Layer:**
- Purpose: Generate PDF validation reports
- Location: `generate_report.py`
- Contains: ReportLab-based PDF generation
- Depends on: ReportLab (not in core dependencies)
- Used by: Manual execution for documentation

## Data Flow

**Skill Evolution Pipeline (primary flow):**

1. User invokes `python -m evolution.skills.evolve_skill --skill <name>`
2. `find_skill()` searches `hermes-agent/skills/` for a matching `SKILL.md`
3. `load_skill()` parses the file into frontmatter + body
4. Eval dataset is built from one of three sources:
   - `synthetic`: LLM generates (task_input, expected_behavior) pairs from the skill text
   - `sessiondb`: Session importers extract real usage from Claude Code / Copilot / Hermes, then `RelevanceFilter` scores relevance via LLM
   - `golden`: Pre-curated JSONL files loaded from disk
5. Dataset is split into train/val/holdout (50/25/25)
6. `SkillModule` wraps the skill body as a DSPy module with optimizable instructions
7. DSPy optimizer (GEPA or MIPROv2 fallback) evolves the skill text over N iterations
8. Evolved skill is validated against constraints (size, growth, structure)
9. Holdout evaluation compares baseline vs evolved scores
10. Results saved to `output/<skill_name>/<timestamp>/` (evolved skill, baseline, metrics JSON)

**Session Import Pipeline (secondary flow):**

1. User invokes `python -m evolution.core.external_importers --skill <name>`
2. Importers read session history from standard locations:
   - Claude Code: `~/.claude/history.jsonl`
   - Copilot: `~/.copilot/session-state/*/events.jsonl`
   - Hermes: `~/.hermes/sessions/*.json`
3. Secret detection filters out messages containing API keys/tokens
4. Heuristic pre-filter checks keyword overlap with skill text
5. LLM-as-judge (`RelevanceFilter.ScoreRelevance`) scores remaining candidates
6. Relevant examples are split and saved as train/val/holdout JSONL

**State Management:**
- No persistent state between runs -- each evolution run is independent
- Eval datasets can be saved to `datasets/skills/<name>/` for reuse
- Evolution output (evolved artifacts, metrics) saved to `output/` directory
- The hermes-agent repo is read-only during evolution; changes are proposed as PRs

## Key Abstractions

**SkillModule (DSPy Module):**
- Purpose: Makes a SKILL.md file optimizable by DSPy
- Examples: `evolution/skills/skill_module.py` lines 84-114
- Pattern: The skill body text is the parameter; `forward()` uses it as instructions for a `ChainOfThought` predictor. GEPA/MIPROv2 can mutate the instructions to maximize the fitness metric.

**EvalExample / EvalDataset:**
- Purpose: Standardized evaluation data with train/val/holdout splits
- Examples: `evolution/core/dataset_builder.py` lines 21-86
- Pattern: Dataclass with `to_dict()`/`from_dict()` serialization, JSONL persistence, and `to_dspy_examples()` conversion

**ConstraintResult / ConstraintValidator:**
- Purpose: Hard-gate validation ensuring evolved artifacts are safe to deploy
- Examples: `evolution/core/constraints.py` lines 15-174
- Pattern: Each check returns a `ConstraintResult` with passed/failed status + message. `validate_all()` runs all applicable checks. Failures cause immediate rejection.

**FitnessScore / LLMJudge:**
- Purpose: Multi-dimensional quality scoring for agent outputs
- Examples: `evolution/core/fitness.py` lines 14-105
- Pattern: Weighted composite of correctness (0.5), procedure_following (0.3), conciseness (0.2) minus length penalty. `skill_fitness_metric()` is a fast heuristic proxy used during optimization; `LLMJudge` provides full rubric-based scoring.

**Session Importers:**
- Purpose: Extract real user messages from external AI tool history
- Examples: `ClaudeCodeImporter`, `CopilotImporter`, `HermesSessionImporter` in `evolution/core/external_importers.py`
- Pattern: Static `extract_messages()` method reads from standard filesystem paths, filters secrets, returns normalized dicts

## Entry Points

**`python -m evolution.skills.evolve_skill`:**
- Location: `evolution/skills/evolve_skill.py` lines 296-323
- Triggers: User CLI invocation
- Responsibilities: Full skill evolution pipeline (load, dataset, optimize, validate, evaluate, save)

**`python -m evolution.core.external_importers`:**
- Location: `evolution/core/external_importers.py` lines 729-785
- Triggers: User CLI invocation
- Responsibilities: Import session data from external tools, filter for relevance, generate eval datasets

**`python generate_report.py`:**
- Location: `generate_report.py`
- Triggers: Manual execution
- Responsibilities: Generate Phase 1 validation report PDF

## Error Handling

**Strategy:** Fail-fast with user-friendly Rich console output

**Patterns:**
- CLI entry points use `sys.exit(1)` on critical failures (skill not found, no eval data)
- DSPy optimizer failures trigger fallback: GEPA -> MIPROv2 (`evolve_skill.py` lines 156-177)
- JSON parsing from LLM output uses two-stage strategy: try `json.loads()`, fall back to brace-counting extraction (`_parse_scoring_json()`)
- Score parsing clamps to [0.0, 1.0] range with 0.5 default on failure (`_parse_score()`)
- Secret detection silently skips messages containing potential API keys/tokens
- Session file read errors are silently skipped (continue to next file)
- Constraint validation failures on the baseline emit a warning but proceed; failures on evolved output cause rejection

## Cross-Cutting Concerns

**Logging:** Rich console output (`rich.console.Console`) for all user-facing messages. No structured logging framework.

**Validation:** `_validate_eval_example()` normalizes and validates fields before creating `EvalExample` objects. `ConstraintValidator` gates evolved artifacts. Secret detection via compiled regex patterns.

**Authentication:** No auth within this repo. LLM API auth is handled by DSPy/LiteLLM via environment variables (e.g., `OPENAI_API_KEY`).

---

*Architecture analysis: 2026-04-15*
