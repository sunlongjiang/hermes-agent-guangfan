# Technology Stack

**Analysis Date:** 2026-05-06

## Languages

**Primary:**
- Python `>=3.10` — All source code under `evolution/` and top-level scripts (`generate_report.py`). Declared in `pyproject.toml` line 11 (`requires-python = ">=3.10"`).

**Secondary:**
- YAML — LLM backend configuration (`evolution.yaml`), parsed via `pyyaml` in `evolution/core/config.py`. Skill frontmatter is also YAML but parsed manually (no library call) inside `evolution/skills/skill_module.py`.
- JSON / JSONL — Dataset serialization (`train.jsonl`, `val.jsonl`, `holdout.jsonl`), evolution metrics, and external-tool session imports (Claude Code `~/.claude/history.jsonl`, Copilot `~/.copilot/session-state/*/events.jsonl`, Hermes `~/.hermes/sessions/*.json`).
- Markdown — Skill files (`SKILL.md`) and prompt sections inside the external hermes-agent repo are the actual artifacts being evolved.

## Runtime

**Environment:**
- CPython 3.13.3 — Active virtual environment at `.venv/` (verified via `.venv/bin/python --version`).
- Minimum supported runtime: Python 3.10 (per `pyproject.toml`).
- System Python is 3.14.3 but the project pins to the `.venv` interpreter.

**Package Manager:**
- pip + setuptools — Build backend declared in `pyproject.toml` lines 1-3 (`requires = ["setuptools>=68.0", "wheel"]`, `build-backend = "setuptools.build_meta"`).
- Lockfile: **MISSING** — there is no `requirements.txt`, `requirements-dev.txt`, `poetry.lock`, `uv.lock`, or `Pipfile.lock` anywhere in the repo. Dependency versions resolve transitively from the `>=` floors in `pyproject.toml` on each install. This is a known reproducibility gap.

## Frameworks

**Core:**
- DSPy `>=3.0.0` — LLM programming framework. Provides `dspy.Module`, `dspy.Signature`, `dspy.ChainOfThought`, `dspy.LM`, `dspy.Example`, `dspy.Prediction`, and the optimizers `dspy.GEPA` (primary) + `dspy.MIPROv2` (fallback). Used pervasively: `evolution/core/dataset_builder.py`, `evolution/core/fitness.py`, `evolution/core/external_importers.py`, `evolution/skills/skill_module.py`, `evolution/skills/evolve_skill.py`, `evolution/tools/tool_module.py`, `evolution/tools/tool_dataset.py`, `evolution/tools/tool_metric.py`, `evolution/tools/tool_constraints.py`, `evolution/tools/evolve_tool_descriptions.py`, `evolution/prompts/prompt_module.py`, `evolution/prompts/evolve_prompt_sections.py`.
- Click `>=8.0` — CLI framework. Decorator-based commands at `evolution/skills/evolve_skill.py`, `evolution/core/external_importers.py:729`, `evolution/tools/evolve_tool_descriptions.py:400`, `evolution/prompts/evolve_prompt_sections.py`.
- Rich `>=13.0` — Terminal UX (Console, Panel, Table, Progress). Imported across `evolution/tools/`, `evolution/prompts/`, `evolution/core/external_importers.py`, `evolution/skills/evolve_skill.py`.
- PyYAML `>=6.0` — Used only for backend config loading in `evolution/core/config.py:4` (`yaml.safe_load`). Skill frontmatter parsing is hand-rolled.

**Testing:**
- pytest `>=7.0` — Test runner, declared as a dev extra in `pyproject.toml` lines 26-29. Configuration block `[tool.pytest.ini_options]` (lines 41-43) sets `testpaths = ["tests"]` and `python_files = ["test_*.py"]`.
- pytest-asyncio `>=0.21` — Async test support; same `dev` extra group.

**Build / Packaging:**
- setuptools `>=68.0` — Build backend.
- wheel — Wheel distribution support.
- Package discovery: `[tool.setuptools.packages.find]` with `include = ["evolution*"]` (`pyproject.toml` lines 38-39). Top-level `generate_report.py` is intentionally outside the package.

## Key Dependencies

**Critical (declared in `pyproject.toml` `[project.dependencies]`):**
- `dspy>=3.0.0` — Core optimization engine; the entire pipeline is built around its `Module`/`Signature`/`LM`/`GEPA`/`MIPROv2` abstractions.
- `openai>=1.0.0` — OpenAI-compatible API client. Not imported directly in `evolution/` — used transitively by DSPy / LiteLLM through `dspy.LM(model, api_base=..., api_key=...)`.
- `pyyaml>=6.0` — YAML config parsing in `evolution/core/config.py`.
- `click>=8.0` — All CLI entry points.
- `rich>=13.0` — All terminal output (`console.print`, Panel, Table, Progress).

**Optional extras (`pyproject.toml` lines 25-32):**
- `dev` extra: `pytest>=7.0`, `pytest-asyncio>=0.21`. Install with `pip install .[dev]`.
- `darwinian` extra: `darwinian-evolver` — Phase 4 code-evolution engine. **AGPL v3 licensed**, opt-in only via `pip install .[darwinian]` so the AGPL terms do not infect normal installs.

**Undeclared but used (gap):**
- `reportlab` — Used by `generate_report.py` (lines 3-12) for PDF generation of validation reports. **Not declared** in `pyproject.toml` — anyone running the report generator must `pip install reportlab` separately. This is a known dependency gap.

## Configuration

**Environment:**
- `HERMES_AGENT_REPO` — Absolute path to the hermes-agent checkout. Resolved by `get_hermes_agent_path()` in `evolution/core/config.py:120-145` with fallback chain: env var → `~/.hermes/hermes-agent` → `../hermes-agent` (sibling).
- LLM API keys: `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, or any provider-specific key consumed by DSPy/LiteLLM. Not read directly by this codebase.
- Phase 12 layered overrides (handled in `EvolutionConfig.load()` at `evolution/core/config.py:60-117`):
  - `EVOLUTION_API_BASE` — overrides `api_base` from `evolution.yaml`.
  - `EVOLUTION_API_KEY` — overrides `api_key` from `evolution.yaml`.
  - `EVOLUTION_MODEL` — overrides `optimizer_model`, `eval_model`, and `judge_model` simultaneously.
- CLI flags (`--model`, `--api-base`, `--api-key`, `--iterations`, `--hermes-repo`) override env vars and YAML.

**Backend config file (Phase 12):**
- `evolution.yaml` — Single source of truth for multi-model backend selection. Schema:
  ```yaml
  models:
    optimizer: "openai/qwen-max"   # GEPA reflections
    eval: "openai/qwen-plus"        # LLM-as-judge scoring
    judge: "openai/qwen-plus"       # Synthetic dataset generation
  api_base: "https://..."           # OpenAI-compatible endpoint (optional)
  api_key: "sk-..."                 # Provider key (optional)
  ```
- `evolution.example.yaml` — Documented template covering OpenAI, Qwen/DashScope, Claude proxy, OpenRouter, and local vLLM/Ollama setups.
- `evolution.yaml` is gitignored (`.gitignore` line includes `evolution.yaml`) so live API keys stay local.

**Build / Project metadata:**
- `pyproject.toml` — Single source of truth for project metadata, dependencies, build config, AND pytest config. There is no `setup.py`, `setup.cfg`, `tox.ini`, or separate `pytest.ini`.
- No formatter config (no `[tool.black]`, `[tool.ruff]`, `.prettierrc`, `ruff.toml`, `.flake8`).

## Default Models

Set as `EvolutionConfig` dataclass defaults in `evolution/core/config.py:22-24`:
- Optimizer (GEPA reflection LM): `openai/gpt-4.1`
- Eval (LLM-as-judge metric): `openai/gpt-4.1-mini`
- Judge (dataset generation): `openai/gpt-4.1`
- External importers CLI default: `openrouter/google/gemini-2.5-flash` (`evolution/core/external_importers.py:739`).

## Hard Constraints

Defined as `EvolutionConfig` defaults (`evolution/core/config.py:31-34`):
- `max_skill_size`: 15,000 chars
- `max_tool_desc_size`: 500 chars
- `max_param_desc_size`: 200 chars
- `max_prompt_growth`: 0.2 (20% over baseline)
- `eval_dataset_size`: 20 examples, split 50/25/25 train/val/holdout

## Platform Requirements

**Development:**
- Python `>=3.10` (project tested on 3.13.3).
- Network access to at least one LLM API (OpenAI, OpenRouter, DashScope/Qwen, or any OpenAI-compatible endpoint).
- A local checkout of the hermes-agent repository accessible at `HERMES_AGENT_REPO` or one of the fallback paths.
- No GPU — all optimization happens via API calls.

**Production:**
- Same as development. This is a CLI tool, not a deployed service. Each run is independent; no persistent state between invocations.
- Typical optimization run: $2-10 in API credits, 60s (BootstrapFewShot) to 15-30 min (GEPA).

---

*Stack analysis: 2026-05-06*
