# External Integrations

**Analysis Date:** 2026-05-06

## Summary

This is a CLI optimization tool, not a deployed service. It has **no inbound HTTP**, no databases, no message queues, no auth providers, no monitoring SDKs, and no CI/CD. The only network integration is **outbound LLM API calls** (routed through DSPy/LiteLLM). The only stateful external dependency is the **`hermes-agent` repository** read from the local filesystem.

---

## LLM Inference (Only Runtime API Integration)

All calls go through `dspy.LM(model, api_base=..., api_key=...)` via LiteLLM, so any OpenAI-compatible endpoint works. Wired through `EvolutionConfig.get_lm_kwargs()` at `evolution/core/config.py:51-58`.

### OpenAI

- **Defaults:** `openai/gpt-4.1` (optimizer), `openai/gpt-4.1-mini` (eval), `openai/gpt-4.1` (judge) — `evolution/core/config.py:22-24`
- **Auth:** `OPENAI_API_KEY` env var (consumed transitively by DSPy/LiteLLM)
- **SDK:** `openai>=1.0.0` declared in `pyproject.toml`, used transitively only

### OpenRouter

- **Default for session importers:** `openrouter/google/gemini-2.5-flash` — `evolution/core/external_importers.py:739`
- **Auth:** `OPENROUTER_API_KEY` env var
- **No `api_base` needed** — LiteLLM routes the `openrouter/` prefix automatically

### Qwen / DashScope (Currently Active)

- **`evolution.yaml`** sets `openai/qwen-max` (optimizer) + `openai/qwen-plus` (eval) against `https://dashscope.aliyuncs.com/compatible-mode/v1`
- The `openai/` prefix triggers OpenAI-compatible mode in LiteLLM; `api_base` redirects to DashScope

### Other Documented Backends (`evolution.example.yaml`)

- Claude via OpenAI-compatible proxy
- OpenRouter multi-model
- Local vLLM/Ollama at `http://localhost:8000/v1`

---

## External Repository (Read-Only Filesystem Dependency)

**`hermes-agent`** — discovered by `get_hermes_agent_path()` at `evolution/core/config.py:120-145`.

**Resolution chain (first match wins):**
1. `HERMES_AGENT_REPO` env var (path is `expanduser`'d)
2. `~/.hermes/hermes-agent` (standard install location)
3. `../hermes-agent` (sibling directory)

Raises `FileNotFoundError` (`config.py:142-145`) if none exist.

**Read access:** Tool source files (`hermes-agent/tools/*.py`), prompt builder (`hermes-agent/agent/prompt_builder.py`), tests (`hermes-agent/tests/`).

**Write access:** Yes — `evolution/tools/tool_loader.py:578` (`write_back_description`) and `evolution/prompts/prompt_loader.py:182` write back to hermes-agent. **CLAUDE.md states "read-only access" but this is a documentation contract, not enforced by code.** See CONCERNS.md M6.

**Test invocation:** `evolution/core/constraints.py` may invoke `pytest` against this repo when `run_pytest=True` (benchmark gating).

---

## Data Storage

**No databases.** No PostgreSQL, no Redis, no SQLite, no message queues, no caches.

**Local filesystem only:**
- Datasets: `datasets/skills/<name>/{train,val,holdout}.jsonl`, `datasets/tools/`, `datasets/prompts/`
- Evolution outputs: `output/<phase>/<timestamp>/` — gitignore status: see CONCERNS.md H4
- Reports: `reports/`

---

## Auth / Identity

- **None for end users** — this is a CLI tool, no login flows
- **LLM provider auth** via env vars or the `api_key` field in `evolution.yaml`
- **No `.env` auto-loading** — the codebase does not import `python-dotenv`; users must export vars themselves

---

## Monitoring / Observability

- **No error tracking SDK** (no Sentry, Datadog, Honeycomb, etc.)
- **No `logging` module usage** anywhere in `evolution/`
- All output via `rich.console.Console` markup and `rich.progress.Progress`
- Bare `print()` only in `generate_report.py`
- Per-run JSON metrics dumped under `output/`; no external metrics service

---

## CI/CD

**None detected.** Verified absent:
- No `.github/workflows/`
- No `.gitlab-ci.yml`, `.circleci/`, `azure-pipelines.yml`, `bitbucket-pipelines.yml`, `Jenkinsfile`, `.travis.yml`

**Distribution:** PEP 517 sdist/wheel via setuptools; install with `pip install .` (or `.[dev]` / `.[darwinian]`).

---

## Session Importers (Filesystem Integrations with External AI Tools)

All in `evolution/core/external_importers.py`; all read-only, all expose static `extract_messages()` returning normalized dicts.

### Claude Code

- **Class:** `ClaudeCodeImporter` (lines 157-209)
- **Source:** `~/.claude/history.jsonl` (`HISTORY_PATH` constant, line 165)
- **Format:** Flat JSONL of user inputs only (no assistant turns)
- **Tagged:** `"source": "claude-code"` (line 197)

### GitHub Copilot

- **Class:** `CopilotImporter` (lines 210-332)
- **Source:** `~/.copilot/session-state/<id>/events.jsonl` (`SESSION_DIR` constant, line 222)
- **Format:** Event stream JSONL with sibling `workspace.yaml` parsed by `_read_copilot_workspace` (line 260)
- **Tagged:** `"source": "copilot"` (lines 299, 321)

### Hermes Agent

- **Class:** `HermesSessionImporter` (line 334+)
- **Source:** `~/.hermes/sessions/*.json` (`SESSION_DIR` constant, lines 359-364)
- **Format:** Per-session JSON with full conversation history

### CLI Dispatch

- Entry point: `evolution/core/external_importers.py:729-785`
- Flags: `--source [claude-code|copilot|hermes|all] --skill <name> --model <model>`
- Default model for relevance scoring: `openrouter/google/gemini-2.5-flash`

### Secret Hygiene

All messages screened by `_contains_secret()` against `SECRET_PATTERNS` and silently dropped on match before reaching the LLM. See CONCERNS.md M5 for coverage gaps.

---

## Environment Variables

### Required (one of)

- `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, or any provider key consumed transitively by DSPy/LiteLLM
- Alternatively, set `api_key` in `evolution.yaml`

### Optional (all read in `evolution/core/config.py`)

- `HERMES_AGENT_REPO` (line 128) — overrides hermes-agent discovery
- `EVOLUTION_API_BASE` (line 91) — overrides `evolution.yaml` `api_base`
- `EVOLUTION_API_KEY` (line 94) — overrides `evolution.yaml` `api_key`
- `EVOLUTION_MODEL` (line 97) — Phase 12 single-model override (sets optimizer + eval + judge)

### Secret Storage Locations

- `evolution.yaml` — gitignored; preferred for `api_key`. **Plaintext on disk** (see CONCERNS.md H5)
- Shell env / `.env` — `.env` is gitignored but is **not auto-loaded** by the project

---

## Webhooks / Callbacks

- **None incoming** — no HTTP server runs as part of this project
- **None outgoing** beyond LLM API calls

---

## Files referenced

- `pyproject.toml`
- `evolution.yaml`
- `evolution.example.yaml`
- `.gitignore`
- `evolution/core/config.py`
- `evolution/core/external_importers.py`
- `evolution/core/dataset_builder.py`
- `evolution/core/fitness.py`
- `evolution/core/constraints.py`
- `evolution/skills/evolve_skill.py`
- `evolution/skills/skill_module.py`
- `evolution/tools/evolve_tool_descriptions.py`
- `evolution/tools/tool_module.py`
- `evolution/tools/tool_loader.py`
- `evolution/prompts/evolve_prompt_sections.py`
- `evolution/prompts/prompt_loader.py`
- `generate_report.py`

---

*Integrations analysis: 2026-05-06*
