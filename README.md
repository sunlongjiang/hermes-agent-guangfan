# Hermes Agent Self-Evolution

**Evolutionary self-improvement for [Hermes Agent](https://github.com/NousResearch/hermes-agent).**

Uses DSPy + GEPA (Genetic-Pareto Prompt Evolution) to automatically evolve and optimize Hermes Agent's skills, tool descriptions, and system prompt sections — producing measurably better versions through reflective evolutionary search.

**No GPU training required.** Everything operates via API calls. ~$2-10 per optimization run.

## How It Works

```
Read artifact ──► Generate eval dataset (synthetic / session history)
                       │
                       ▼
                  GEPA Optimizer ◄── Execution traces (reflective mutation)
                       │
                       ▼
                  Candidate variants ──► LLM-as-Judge evaluation
                       │
                  Constraint gates ──► Size / Growth / Factual / Regression
                       │
                       ▼
                  Best variant ──► output/ (human review before deploy)
```

## Quick Start

```bash
# Install
git clone https://github.com/sunlongjiang/hermes-agent-guangfan.git
cd hermes-agent-self-evolution
pip install -e ".[dev]"

# Ensure hermes-agent is available (auto-discovery order):
#   1. $HERMES_AGENT_REPO env var
#   2. ~/.hermes/hermes-agent
#   3. ../hermes-agent (sibling directory)

# Set your LLM API key
export OPENAI_API_KEY="sk-..."
```

### Optimize Tool Descriptions

```bash
# Validate setup (free)
python -m evolution.tools.evolve_tool_descriptions --dry-run

# Quick trial (3 iterations, ~$1-2)
python -m evolution.tools.evolve_tool_descriptions --iterations 3

# Full optimization (10 iterations, ~$5-8)
python -m evolution.tools.evolve_tool_descriptions --iterations 10

# Reuse saved dataset
python -m evolution.tools.evolve_tool_descriptions --iterations 10 --eval-source load
```

### Optimize Prompt Sections

```bash
# Validate setup (free)
python -m evolution.prompts.evolve_prompt_sections --dry-run

# Optimize a single section
python -m evolution.prompts.evolve_prompt_sections --section default_agent_identity --iterations 5

# Optimize a specific platform hint
python -m evolution.prompts.evolve_prompt_sections --section platform_hints.whatsapp --iterations 5

# Optimize all 13 sections (~$10-20)
python -m evolution.prompts.evolve_prompt_sections --iterations 10
```

### Evolve a Skill

```bash
python -m evolution.skills.evolve_skill \
    --skill github-code-review \
    --iterations 10 \
    --eval-source synthetic
```

## What It Optimizes

| Pipeline | Target | Command | Status |
|----------|--------|---------|--------|
| **Skills** | Skill files (SKILL.md) | `evolve_skill` | ✅ v1 |
| **Tool Descriptions** | 47 tool schemas | `evolve_tool_descriptions` | ✅ v1 |
| **Prompt Sections** | 13 prompt sections | `evolve_prompt_sections` | ✅ v1 |
| **Per-Parameter** | Individual param descriptions | — | 🔲 v2 |
| **Code Evolution** | Tool implementation code | — | 🔲 v2 |

## Pipeline Architecture

Each pipeline follows the same pattern:

```
Loader ──► Module (DSPy) ──► Dataset ──► Metric ──► Constraints ──► CLI
```

### Tool Pipeline (`evolution/tools/`)

| Module | Purpose |
|--------|---------|
| `tool_loader.py` | Extract/write-back tool descriptions from Python source |
| `tool_module.py` | DSPy module — each tool description is an optimizable parameter |
| `tool_dataset.py` | Synthetic eval dataset with tool selection scenarios |
| `tool_metric.py` | Binary tool selection metric + cross-tool regression checker |
| `tool_constraints.py` | Factual accuracy checker (LLM-based) |
| `evolve_tool_descriptions.py` | CLI entry point orchestrating the full pipeline |

### Prompt Pipeline (`evolution/prompts/`)

| Module | Purpose |
|--------|---------|
| `prompt_loader.py` | AST-based extract/write-back of 5 prompt variables from `prompt_builder.py` |
| `prompt_module.py` | DSPy module — per-section optimization with frozen context isolation |
| `prompt_dataset.py` | Behavioral scenario dataset (80 scenarios, importance-weighted) |
| `prompt_metric.py` | Behavioral metric via LLM-as-Judge (correctness/procedure/conciseness) |
| `prompt_constraints.py` | Role preservation checker (LLM-based) |
| `evolve_prompt_sections.py` | CLI entry point with `--section` for targeted optimization |

### Core (`evolution/core/`)

| Module | Purpose |
|--------|---------|
| `config.py` | `EvolutionConfig` — models, limits, dataset splits |
| `constraints.py` | Size/growth/non-empty validators |
| `fitness.py` | `FitnessScore` + `LLMJudge` — multi-dimensional scoring |
| `dataset_builder.py` | `SyntheticDatasetBuilder` + session importers |

## Constraint Gates

Every evolved variant must pass before acceptance:

| Constraint | Tool Pipeline | Prompt Pipeline |
|------------|--------------|-----------------|
| **Size limit** | ≤500 chars (tool), ≤200 chars (param) | ≤baseline +20% growth |
| **Non-empty** | Description must not be blank | Section must not be blank |
| **Semantic check** | Factual accuracy (no false capabilities) | Role preservation (functional role maintained) |
| **Regression** | Per-tool selection rate ≤2pp drop | Per-section behavioral score |
| **Human review** | All output to `output/`, never auto-deploy | Same |

## Output

```
output/
├── tools/
│   └── 20260420_143000/
│       ├── evolved_descriptions.json   # Evolved tool descriptions
│       ├── metrics.json                # Baseline vs evolved scores
│       └── diff.txt                    # Before/after comparison
└── prompts/
    └── 20260420_150000/
        ├── evolved_sections.json
        ├── metrics.json
        └── diff.txt
```

## Model Configuration

| Role | Default | Config Key |
|------|---------|------------|
| GEPA optimizer | `openai/gpt-4.1` | `EvolutionConfig.optimizer_model` |
| LLM-as-Judge | `openai/gpt-4.1-mini` | `EvolutionConfig.eval_model` |
| Dataset generation | `openai/gpt-4.1` | `EvolutionConfig.judge_model` |

Models are accessed via DSPy's `dspy.LM()` — any OpenAI-compatible API works (OpenRouter, local vLLM, etc).

## Testing

```bash
# Full suite (329 tests, ~10s)
python -m pytest tests/ -v

# Tool tests only
python -m pytest tests/tools/ -v

# Prompt tests only
python -m pytest tests/prompts/ -v
```

## Roadmap

### v1 (Complete)

Phases 1-11: Skill evolution + tool description optimization + prompt section optimization. Two end-to-end pipelines with constraint gates, regression checks, and CLI entry points.

### v2 (In Progress)

| Phase | Feature |
|-------|---------|
| 12 | v1 stabilization ✅ |
| 13 | Per-parameter description optimization |
| 14 | SessionDB mining for tool training data |
| 15 | Think-augmented tool selection |
| 16 | Per-tool regression dashboard |
| 17 | Joint section optimization |
| 18 | Personality drift detection |
| 19 | SessionDB behavioral mining for prompts |
| 20 | Benchmark-gated validation (TBLite) |
| 21 | Darwinian code evolution |
| 22 | Continuous evolution loop |

## License

MIT
