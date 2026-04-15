# External Integrations

**Analysis Date:** 2026-04-15

## APIs & External Services

**LLM Providers (via DSPy `dspy.LM()`):**
- OpenAI API - Primary LLM provider for optimization and evaluation
  - SDK/Client: `openai>=1.0.0` (used transitively through DSPy)
  - Auth: `OPENAI_API_KEY` env var (managed by DSPy/LiteLLM)
  - Models used: `openai/gpt-4.1`, `openai/gpt-4.1-mini`
  - Usage: `evolution/core/fitness.py` (LLM-as-judge), `evolution/core/dataset_builder.py` (synthetic generation), `evolution/skills/evolve_skill.py` (optimization loop)

- OpenRouter - Alternative LLM routing service
  - SDK/Client: Accessed via DSPy's LiteLLM integration (no separate SDK)
  - Auth: `OPENROUTER_API_KEY` env var
  - Models used: `openrouter/google/gemini-2.5-flash` (default for external importers CLI)
  - Usage: `evolution/core/external_importers.py` line 739

- Any LiteLLM-compatible provider - DSPy's `dspy.LM()` accepts any LiteLLM model string
  - Example from Phase 1 validation: MiniMax M2.5 via OpenRouter

**Hermes Agent Repository (filesystem integration):**
- The hermes-agent repo is read from disk (never modified directly)
  - Discovery: `evolution/core/config.py` `get_hermes_agent_path()`
  - Priority: `HERMES_AGENT_REPO` env var > `~/.hermes/hermes-agent` > `../hermes-agent`
  - Reads: `skills/<category>/<skill>/SKILL.md` files
  - Implementation: `evolution/skills/skill_module.py` `find_skill()` and `load_skill()`

## Data Storage

**Databases:**
- None - No database used. All data is file-based.

**File Storage:**
- Local filesystem only
  - Eval datasets: `datasets/skills/<skill-name>/train.jsonl`, `val.jsonl`, `holdout.jsonl`
  - Eval datasets: `datasets/tools/` (placeholder, not yet used)
  - Evolution output: `output/<skill-name>/<timestamp>/` containing `evolved_skill.md`, `baseline_skill.md`, `metrics.json`
  - Reports: `reports/phase1_validation_report.pdf`

**Caching:**
- None at application level. DSPy may cache LLM calls internally.

## Authentication & Identity

**Auth Provider:**
- None - CLI tool, no user authentication
- LLM API keys managed via environment variables (standard for OpenAI/LiteLLM)

## External Data Sources (Session Importers)

The external importers in `evolution/core/external_importers.py` read local files from other AI tools:

**Claude Code:**
- Source: `~/.claude/history.jsonl`
- Format: JSONL with `display`, `timestamp`, `project`, `sessionId` fields
- Reads: User messages only (no assistant responses available)
- Implementation: `ClaudeCodeImporter` class (line 157)

**GitHub Copilot:**
- Source: `~/.copilot/session-state/<session-id>/events.jsonl`
- Format: JSONL stream of `user.message` / `assistant.message` events
- Also reads: `~/.copilot/session-state/<session-id>/workspace.yaml` for project context
- Implementation: `CopilotImporter` class (line 210)

**Hermes Agent Sessions:**
- Source: `~/.hermes/sessions/*.json`
- Format: JSON with OpenAI-format message list (user, assistant, tool roles)
- Implementation: `HermesSessionImporter` class (line 334)

**Hermes Skills (standalone CLI mode):**
- Source: `~/.hermes/skills/<skill-name>/SKILL.md`
- Used by: `_load_skill_text()` in `evolution/core/external_importers.py` line 696

## Monitoring & Observability

**Error Tracking:**
- None - Errors printed to console via `rich.console.Console`

**Logs:**
- Console output only via `rich` library (colored output, progress bars, tables)
- No structured logging framework

## CI/CD & Deployment

**Hosting:**
- Not deployed as a service. CLI tool run locally.

**CI Pipeline:**
- None detected (no `.github/workflows/`, no CI config files)

**Deployment model:**
- Evolution results are saved locally to `output/` directory
- Designed to create PRs against hermes-agent repo (`config.create_pr = True` in `evolution/core/config.py` line 44) but PR creation is not yet implemented in code

## Environment Configuration

**Required env vars:**
- LLM API key (one of): `OPENAI_API_KEY` or `OPENROUTER_API_KEY` (depends on chosen model string)
- `HERMES_AGENT_REPO` (optional) - Path to hermes-agent repo if not at standard location

**Optional env vars:**
- Any LiteLLM-supported provider env vars (e.g., `ANTHROPIC_API_KEY`)

**Secrets location:**
- `.env` file is in `.gitignore` but no `.env` file exists currently
- All secrets managed via environment variables

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None (PR creation is planned but not yet implemented)

## Security Features

**Secret Detection in Imported Data:**
- `evolution/core/external_importers.py` lines 45-70 define `SECRET_PATTERNS` regex
- Checks for: API keys (Anthropic, OpenRouter, OpenAI, GitHub, Slack, Notion, AWS), Bearer tokens, PEM private keys, password/secret/token assignments
- Applied via `_contains_secret()` to all imported session messages before including in datasets
- Task inputs capped at 2000 chars (`_validate_eval_example()` line 111)

---

*Integration audit: 2026-04-15*
