# Technology Stack

**Analysis Date:** 2026-04-15

## Languages

**Primary:**
- Python >=3.10 - All source code (`.venv` uses Python 3.13.3, system Python is 3.14.3)

**Secondary:**
- YAML - Skill frontmatter parsing (inline, no YAML library dependency)
- JSON/JSONL - Dataset serialization, session import formats

## Runtime

**Environment:**
- CPython 3.13.3 (virtualenv at `.venv/`)
- Minimum supported: Python 3.10 (declared in `pyproject.toml`)

**Package Manager:**
- pip + setuptools (build-system requires `setuptools>=68.0`, `wheel`)
- Lockfile: **missing** - no `requirements.txt`, `poetry.lock`, or `uv.lock`

## Frameworks

**Core:**
- DSPy `>=3.0.0` - LLM programming framework; provides `dspy.Module`, `dspy.Signature`, `dspy.ChainOfThought`, `dspy.GEPA`, `dspy.MIPROv2`, `dspy.LM`, `dspy.Example`, `dspy.Prediction`
- Click `>=8.0` - CLI framework for `evolve_skill.py` and `external_importers.py`

**Testing:**
- pytest `>=7.0` - Test runner (configured in `pyproject.toml` `[tool.pytest.ini_options]`)
- pytest-asyncio `>=0.21` - Async test support (dev dependency)

**Build/Dev:**
- setuptools `>=68.0` - Build backend
- wheel - Wheel distribution support

## Key Dependencies

**Critical (runtime):**
- `dspy>=3.0.0` - Core optimization engine; defines all LLM interactions, optimization loops (GEPA/MIPROv2), and module abstractions. Used in `evolution/core/fitness.py`, `evolution/core/dataset_builder.py`, `evolution/core/external_importers.py`, `evolution/skills/skill_module.py`, `evolution/skills/evolve_skill.py`
- `openai>=1.0.0` - OpenAI-compatible API client; used transitively through DSPy's `dspy.LM()` for model access
- `pyyaml>=6.0` - YAML parsing (declared dependency, though current code does manual YAML frontmatter parsing)
- `click>=8.0` - CLI argument parsing in `evolution/skills/evolve_skill.py` and `evolution/core/external_importers.py`
- `rich>=13.0` - Terminal output formatting (Console, Panel, Table, Progress bars) throughout the codebase

**Optional:**
- `darwinian-evolver` - Code evolution engine (Phase 4, AGPL v3 licensed). Installed via `pip install .[darwinian]`

**Report generation (not in declared deps, used standalone):**
- `reportlab` - PDF generation in `generate_report.py` (not declared in `pyproject.toml` dependencies)

## Configuration

**Environment:**
- `HERMES_AGENT_REPO` env var - Path to the hermes-agent repository (see `evolution/core/config.py` lines 55-56)
- Falls back to `~/.hermes/hermes-agent` or `../hermes-agent` sibling directory
- LLM API keys are required by DSPy/OpenAI but managed externally (e.g., `OPENAI_API_KEY`, `OPENROUTER_API_KEY`)

**Default LLM Models (configured in `evolution/core/config.py`):**
- Optimizer model: `openai/gpt-4.1` (GEPA reflections)
- Eval model: `openai/gpt-4.1-mini` (LLM-as-judge scoring)
- Judge model: `openai/gpt-4.1` (dataset generation)
- CLI default for external importers: `openrouter/google/gemini-2.5-flash`

**Build:**
- `pyproject.toml` - Single source of truth for project metadata, dependencies, build config, and pytest config
- Package discovery: `[tool.setuptools.packages.find]` includes `evolution*`

**Constraint Defaults (in `evolution/core/config.py`):**
- Max skill size: 15,000 chars
- Max tool description: 500 chars
- Max param description: 200 chars
- Max prompt growth: 20% over baseline
- Eval dataset: 20 examples, split 50/25/25 train/val/holdout

## Platform Requirements

**Development:**
- Python >=3.10
- Access to LLM APIs (OpenAI, OpenRouter, or compatible)
- Access to a hermes-agent repository checkout (for skill files)
- No GPU required - all optimization via API calls

**Production:**
- Same as development - this is a CLI tool, not a deployed service
- Typical optimization run costs $2-10 in API credits
- Optimization time: 60 seconds (BootstrapFewShot) to 15-30 minutes (GEPA)

---

*Stack analysis: 2026-04-15*
