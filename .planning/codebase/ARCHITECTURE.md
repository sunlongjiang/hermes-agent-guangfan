# Architecture

**Analysis Date:** 2026-05-06

## Pattern Overview

**Overall:** Standalone optimization pipeline operating on an external repository (`hermes-agent`). DSPy modules wrap text artifacts (skill bodies, tool descriptions, prompt sections) as optimizable parameters; GEPA mutates them via reflection; constraint validators hard-gate every variant; a held-out split provides the final accept/reject signal.

**Key Characteristics:**
- The `hermes-agent` repo is treated as **read-only input** during evolution. Writes go to the local `output/<artifact_kind>/<timestamp>/` tree only — there is no auto-PR step.
- Every text artifact is reified as a `dspy.Module` whose `Signature.instructions` (or analogous string) is what GEPA mutates. Schema/structure (param names, frontmatter keys, section IDs) is held outside the optimizable surface so it cannot drift.
- Three independent CLI pipelines (`skills`, `tools`, `prompts`) share the same five-layer spine via the `evolution.core` package. Phase 13+ work continues to land under existing `evolution/tools/` paths.
- v1 (Phases 1-11, complete) and v2 (Phase 12 complete, Phase 13 next) share the **same architecture**. Phase 12 added a multi-model backend layer (`evolution.yaml` + env + CLI override hierarchy) without changing the layer boundaries.
- Strict constraint gating: a variant must pass every applicable `ConstraintResult` before it is allowed to overwrite the baseline pointer in `output/`.

## Layers

**Config layer:**
- Purpose: Define optimization parameters, resolve the hermes-agent repo location, and merge multi-source backend configuration.
- Location: `evolution/core/config.py`
- Contains: `EvolutionConfig` dataclass, `EvolutionConfig.load()` (YAML → env → CLI override hierarchy), `get_lm_kwargs()`, `get_hermes_agent_path()` discovery function.
- Depends on: `HERMES_AGENT_REPO`, `EVOLUTION_API_BASE`, `EVOLUTION_API_KEY`, `EVOLUTION_MODEL` env vars; `evolution.yaml`; the local filesystem.
- Used by: All other layers. Every orchestrator's first step is `EvolutionConfig.load(...)` (skills uses the older direct constructor; tools/prompts use `.load()`).

**Dataset layer:**
- Purpose: Build train/val/holdout splits from synthetic generation, mined external sessions, or hand-curated golden files.
- Location: `evolution/core/dataset_builder.py`, `evolution/core/external_importers.py`, `evolution/tools/tool_dataset.py`, `evolution/prompts/prompt_dataset.py`
- Contains: `EvalExample`, `EvalDataset`, `SyntheticDatasetBuilder` (skill), `GoldenDatasetLoader`, `build_dataset_from_external()`, `ClaudeCodeImporter`, `CopilotImporter`, `HermesSessionImporter`, `RelevanceFilter`, `ToolDatasetBuilder` + `ToolSelectionDataset`, `PromptDatasetBuilder` + `PromptBehavioralDataset`.
- Depends on: DSPy (for the synthetic generator's `Signature`), external session files on disk, `SECRET_PATTERNS` regex.
- Used by: All three orchestration entry points. Persisted to `datasets/<kind>/{train,val,holdout}.jsonl`.

**Fitness/metric layer:**
- Purpose: Score outputs for the optimizer. Each pipeline ships a metric tuned to its artifact's behavior surface.
- Location: `evolution/core/fitness.py`, `evolution/tools/tool_metric.py`, `evolution/prompts/prompt_metric.py`
- Contains: `FitnessScore` (weighted composite — correctness 0.5, procedure_following 0.3, conciseness 0.2, minus length penalty), `LLMJudge`, `skill_fitness_metric()`, `tool_selection_metric()` (binary correct/incorrect), `CrossToolRegressionChecker`, `PromptBehavioralMetric` (callable class).
- Depends on: DSPy LM, `EvolutionConfig`.
- Used by: GEPA/MIPROv2 as the `metric=` argument; orchestrator for holdout scoring.

**Constraints layer:**
- Purpose: Hard-gate evolved artifacts. All-or-nothing — any failure rejects the variant.
- Location: `evolution/core/constraints.py`, `evolution/tools/tool_constraints.py`, `evolution/prompts/prompt_constraints.py`
- Contains: `ConstraintValidator` (`_check_size`, `_check_growth`, `_check_non_empty`, `_check_skill_structure`, `run_test_suite`), `ConstraintResult` dataclass, per-pipeline `ToolFactualChecker`, `PromptRoleChecker`.
- Depends on: `EvolutionConfig` for limits (`max_skill_size=15_000`, `max_tool_desc_size=500`, `max_param_desc_size=200`, `max_prompt_growth=0.2`); `subprocess` for invoking `pytest` inside the hermes-agent repo.
- Used by: Orchestration runs `validate_all()` once on the baseline (warn-only) and again on the evolved artifact (rejection on failure). Tools and prompts pipelines also chain pipeline-specific factual/role checks plus `CrossToolRegressionChecker` against holdout predictions.

**Module layer:**
- Purpose: Wrap each text artifact as a `dspy.Module` so its mutable surface is exactly the text GEPA should evolve, with frozen schema kept outside `named_parameters()`.
- Location: `evolution/skills/skill_module.py`, `evolution/tools/tool_module.py`, `evolution/prompts/prompt_module.py`; loaders alongside (`evolution/tools/tool_loader.py`, `evolution/prompts/prompt_loader.py`).
- Contains: `SkillModule` (single `dspy.ChainOfThought` over `TaskWithSkill` signature whose `skill_text` is the parameter); `ToolModule` (one `dspy.Predict` per tool, names sanitized via `-` → `_`, frozen schema in `_frozen_tools`, selector via `dspy.ChainOfThought(ToolSelectionSignature)`); `PromptModule` (single-active-section pattern: only `set_active_section()`'d section is a `dspy.Predict`; others remain plain strings in `_frozen_instructions` invisible to `named_parameters()`).
- Depends on: DSPy.
- Used by: Orchestration layer.

**Orchestration / CLI layer:**
- Purpose: End-to-end pipeline: discover → load → wrap → dataset → optimize → constraint-gate → holdout-eval → save.
- Location: `evolution/skills/evolve_skill.py`, `evolution/tools/evolve_tool_descriptions.py`, `evolution/prompts/evolve_prompt_sections.py`
- Contains: a Click `@click.command()` `main()` that calls a parallel `evolve(...)` business function (the `evolve()` function holds all logic; `main()` only translates CLI flags).
- Depends on: every other layer.
- Used by: End users via `python -m evolution.<pkg>.<module>`.

**Reporting layer:**
- Purpose: Manual generation of validation PDFs.
- Location: `generate_report.py` (repo root)
- Contains: ReportLab-driven layout for the Phase 1 validation report.
- Depends on: `reportlab` (NOT declared in `pyproject.toml` — install separately).
- Used by: Manual invocation. Output written to `reports/phase1_validation_report.pdf`.

## Data Flow

**Single evolution run (any of the three pipelines):**

1. Click `main()` parses flags and calls `evolve(...)`.
2. `EvolutionConfig.load(...)` merges `evolution.yaml` ← env vars (`EVOLUTION_API_BASE`, `EVOLUTION_API_KEY`, `EVOLUTION_MODEL`) ← CLI overrides (`--model`, `--api-base`, `--hermes-repo`, `--iterations`).
3. `get_hermes_agent_path()` resolves the read-only hermes-agent repo (`HERMES_AGENT_REPO` → `~/.hermes/hermes-agent` → `../hermes-agent`).
4. The pipeline's loader reads the artifact: `find_skill()` + `load_skill()` for skills, `discover_tool_files()` + `extract_tool_descriptions()` for tools, `extract_prompt_sections()` against `agent/prompt_builder.py` for prompts.
5. The text is wrapped in a DSPy module (`SkillModule` / `ToolModule` / `PromptModule`). The original is also retained as `original_tools` / `original_sections` for diffing and growth checks.
6. The dataset is built (`synthetic`) or loaded (`load` / `golden` / `sessiondb`). Splits persist to `datasets/<kind>/{train,val,holdout}.jsonl`. Each split converts to `dspy.Example` lists via `to_dspy_examples()`.
7. `dspy.LM(...)` is configured with the eval model + `config.get_lm_kwargs()`. A separate `reflection_lm = dspy.LM(config.optimizer_model, ...)` is constructed for GEPA's reflection step in tools and prompts pipelines.
8. **Optimizer:** `dspy.GEPA(metric=..., max_metric_calls=iterations*50, reflection_lm=reflection_lm).compile(module, trainset, valset)`. **Fallback:** wrapped in a `try/except`; on any exception the orchestrator drops to `dspy.MIPROv2(metric=..., auto="light").compile(module, trainset)`. This GEPA→MIPROv2 fallback exists in `evolution/skills/evolve_skill.py` (lines 156-177) and `evolution/tools/evolve_tool_descriptions.py` (lines 184-206); the prompts pipeline iterates this per-section in a loop.
9. `module.get_evolved_descriptions()` / `get_evolved_sections()` (or `optimized_module.skill_text` for skills) extracts the mutated text.
10. `ConstraintValidator` runs all applicable checks; pipeline-specific extras run too (`ToolFactualChecker`, `PromptRoleChecker`). On any failure, results are written to `output/<kind>/FAILED_<timestamp>/` and the run aborts before holdout scoring.
11. Holdout examples are scored on baseline vs evolved with `dspy.context(lm=lm)`; tools pipeline additionally runs `CrossToolRegressionChecker` and aborts to `FAILED_<timestamp>/` on regression.
12. On success, `output/<kind>/<timestamp>/` is created with `evolved_*.{md,json}`, `baseline_skill.md` (skills), `diff.txt` (tools/prompts), and `metrics.json`.

**State persistence:**
- No persistent in-process state between runs.
- Cached eval datasets live at `datasets/skills/<name>/`, `datasets/tools/`, `datasets/prompts/` for reuse via `--eval-source load`.
- Per-run artifacts live at `output/<kind>/<timestamp>/` (or `FAILED_<timestamp>/`).
- The hermes-agent repo is never modified.

## Key Abstractions

**DSPy Module wrapper of text artifact:**
- Purpose: Make a hermes-agent text artifact mutable by GEPA while keeping schema frozen.
- Examples: `evolution/skills/skill_module.py` lines 84-114, `evolution/tools/tool_module.py` lines 35-112, `evolution/prompts/prompt_module.py` lines 35-155.
- Pattern: The mutable surface is a `dspy.Signature.instructions` string (or `Predict` instance for per-element optimization). Frozen metadata is held in `_frozen_*` dicts that DSPy's `named_parameters()` cannot reach. `get_evolved_*()` reassembles the evolved text with the original frozen metadata.

**EvalDataset with train/val/holdout split:**
- Purpose: Standardized evaluation data with serializable splits.
- Examples: `evolution/core/dataset_builder.py` lines 43-86 (`EvalDataset`), `evolution/tools/tool_dataset.py` (`ToolSelectionDataset`), `evolution/prompts/prompt_dataset.py` (`PromptBehavioralDataset`).
- Pattern: Dataclass with `train`/`val`/`holdout` lists, an `all_examples` property, JSONL `save()`/`load()`, and `to_dspy_examples(split)` returning `dspy.Example(...).with_inputs("task_input")` lists. Default split is 50/25/25 of 20 examples.

**ConstraintResult dataclass:**
- Purpose: Pass/fail signal without exceptions, suitable for both reporting and gating.
- Examples: `evolution/core/constraints.py` lines 15-21.
- Pattern: `ConstraintResult(passed: bool, constraint_name: str, message: str, details: Optional[str])`. `validate_all()` returns `list[ConstraintResult]`; orchestrators iterate and aggregate `all_pass`.

**FitnessScore weighted composite:**
- Purpose: Multi-dimensional rubric scoring for skill outputs.
- Examples: `evolution/core/fitness.py` lines 14-105, used by `LLMJudge`.
- Pattern: Weighted composite (correctness 0.5, procedure_following 0.3, conciseness 0.2) minus a length penalty that ramps from 0 at 90% size budget to 0.3 at 100%+. `skill_fitness_metric()` is the fast heuristic proxy used during the optimization inner loop; full rubric scoring happens via `LLMJudge` when explicitly invoked.

**Session importer pattern with secret filtering:**
- Purpose: Mine real user messages from external AI tool history for cold-start dataset bootstrapping.
- Examples: `ClaudeCodeImporter`, `CopilotImporter`, `HermesSessionImporter` in `evolution/core/external_importers.py`.
- Pattern: Each importer exposes a static `extract_messages()` returning normalized `dict[str, str]` rows. `SECRET_PATTERNS` (`evolution/core/external_importers.py` lines 45-70) filters Anthropic / OpenRouter / OpenAI / GitHub / Slack / AWS credentials and `password=`/`secret=`/`token=` assignments. Messages containing matches are silently skipped. Read errors per-file are also silently skipped to keep mining resilient.

## Entry Points

**Skill evolution CLI (Phase 1):**
- Location: `evolution/skills/evolve_skill.py` (lines 296-323 = `main`; `evolve()` at lines 36-294)
- Triggers: `python -m evolution.skills.evolve_skill --skill <name> --iterations 10`
- Responsibilities: Full skill evolution loop. Uses `EvolutionConfig(...)` constructor directly (legacy path) — does not use `EvolutionConfig.load()`. Implements the GEPA→MIPROv2 fallback at lines 156-177. Skips `reflection_lm` (passes only `max_steps`).

**Tool description evolution CLI (Phase 5):**
- Location: `evolution/tools/evolve_tool_descriptions.py` (lines 400-417 = `main`; `evolve()` at lines 72-394)
- Triggers: `python -m evolution.tools.evolve_tool_descriptions --iterations 10`
- Responsibilities: Discover tools, optimize all descriptions in one GEPA run, run factual + cross-tool regression gates, save unified diff. Uses `EvolutionConfig.load(...)` and supports `--model` / `--api-base` overrides. Builds explicit `reflection_lm`.

**Prompt section evolution CLI (Phase 10):**
- Location: `evolution/prompts/evolve_prompt_sections.py` (lines 474-513 = `main`; `evolve()` at lines 78-468)
- Triggers: `python -m evolution.prompts.evolve_prompt_sections --section <id> --iterations 10`
- Responsibilities: Optimize one or all prompt sections, looping `module.set_active_section(active_sid)` so only one section is GEPA-discoverable at a time. Holdout evaluation rebuilds a fresh `baseline_module = PromptModule(original_sections)` for fair comparison.

**External session importer CLI:**
- Location: `evolution/core/external_importers.py` lines 729-785
- Triggers: `python -m evolution.core.external_importers --source claude-code --skill <name>`
- Responsibilities: Bridge ingestion path. Reads session files, filters for skill relevance via `RelevanceFilter`, drops messages matching `SECRET_PATTERNS`, writes a usable golden-style `EvalDataset`.

**Validation report generator:**
- Location: `generate_report.py` (repo root)
- Triggers: Manual `python generate_report.py`
- Responsibilities: ReportLab-driven Phase 1 validation PDF; output at `reports/phase1_validation_report.pdf`. Note: `reportlab` is not in `pyproject.toml` — install separately if running.

## Error Handling

**Strategy:** Layer-appropriate. CLI entry points exit hard on missing inputs; the optimization layer is resilient with explicit fallbacks; data layers swallow per-file errors to keep mining alive.

**Patterns:**
- CLI entry points use `sys.exit(1)` on critical failures: skill not found (`evolution/skills/evolve_skill.py:65`), no relevant sessions (`evolution/skills/evolve_skill.py:97`), no tool files discovered (`evolution/tools/evolve_tool_descriptions.py:109`), unknown `--section` (`evolution/prompts/evolve_prompt_sections.py:161`).
- GEPA failures are caught and rerouted to MIPROv2 with `auto="light"`. The prompts pipeline has a second nested try/except so MIPROv2 failure on one section just skips that section instead of aborting.
- LLM JSON-output parsing uses a two-stage strategy: `json.loads()` first, fall back to brace-counting extraction (`_parse_scoring_json` in `evolution/core/fitness.py`).
- Score parsing clamps to `[0.0, 1.0]` with a 0.5 default on failure (`_parse_score`).
- Constraint failures on the **baseline** emit a yellow warning and proceed; failures on the **evolved** artifact write to `output/<kind>/FAILED_<timestamp>/` and abort before holdout.
- Cross-tool regression failures are a separate hard gate after holdout scoring (`evolution/tools/evolve_tool_descriptions.py:308-327`).
- `subprocess.run(... timeout=300)` in `ConstraintValidator.run_test_suite` is the only externally-triggered process; timeout returns a failed `ConstraintResult` rather than raising.
- Session importers silently skip files on `Exception` and silently drop messages matching `SECRET_PATTERNS`.

## Cross-Cutting Concerns

**Logging:** No `logging` module. Module-level `console = Console()` from `rich` in every CLI entry point and in `external_importers`. Use `console.print(...)` with Rich markup (`[bold cyan]`, `[red]`, `[green]`, `[yellow]`); never bare `print()` (the only exception is `generate_report.py`).

**Validation:** All artifact validation runs through `ConstraintValidator` for shared checks, with per-pipeline checkers (`ToolFactualChecker`, `PromptRoleChecker`, `CrossToolRegressionChecker`) chained from the orchestrator.

**Configuration:** Single `EvolutionConfig` dataclass holds every knob. Phase 12 multi-model backend layer lives in `EvolutionConfig.load()` (`evolution/core/config.py:60-117`) implementing YAML → env → CLI override precedence. `evolution.yaml` is gitignored; `evolution.example.yaml` documents Qwen, Claude-via-proxy, OpenRouter, and local-model recipes.

**Authentication:** API keys are pulled in by DSPy/LiteLLM from the standard env (`OPENAI_API_KEY`, `OPENROUTER_API_KEY`) or supplied through `EVOLUTION_API_KEY` / `evolution.yaml::api_key`. Keys are never logged. The `SECRET_PATTERNS` regex blocks any leakage from session imports back into datasets.

**Output isolation:** All write activity is confined to `output/`, `datasets/`, and `reports/`. The hermes-agent repo is never written to. There is no auto-PR step in v1 or v2 to date — change deployment is a manual step the operator performs after reviewing `output/<kind>/<timestamp>/diff.txt`.

---

*Architecture analysis: 2026-05-06*
