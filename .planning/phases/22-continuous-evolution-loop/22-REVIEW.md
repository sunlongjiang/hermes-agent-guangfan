---
phase: 22-continuous-evolution-loop
review_type: inline-orchestrator
reviewed: 2026-05-21
reviewer: orchestrator (subagent dispatch unavailable; gsd-code-review skill replaced with inline review)
status: clean
files_reviewed:
  - evolution/core/config.py (deploy_mode field + loop_cli_config schema)
  - evolution/tools/tool_loader.py (PermissionError guard)
  - evolution/prompts/prompt_loader.py (PermissionError guard with dest=None gate)
  - evolution/loop/__init__.py (lazy __getattr__ import guard)
  - evolution/loop/run_loop.py (orchestrator, 519 LoC)
  - evolution/loop/pr_creator.py (gh CLI wrapper, 332 LoC)
  - .github/workflows/evolution-loop.yml (cron + workflow_dispatch)
  - docs/setup-hermes-agent-branch-protection.md (runbook)
findings_critical: 0
findings_warning: 1
findings_info: 3
verdict: clean (advisory follow-ups noted as v2.1 candidates)
---

# Phase 22 — Code Review (Inline)

## Scope

8 source files + 1 workflow yaml + 1 doc runbook = 10 artifacts.

## Findings

### CR — Critical (0)

None.

### WR — Warning (1)

**WR-01 — `evolution/loop/pr_creator.py:298-315` no upper bound on copied artifact size.**

`_copy_artifacts_into_staging` does `shutil.copytree` of the full output
dir into hermes-agent's staging area. If a future evolve_* CLI produces a
giant artifact (e.g. multi-GB log files, video renders, openevolve's
`openevolve_internal/` cache), pr_creator will blindly copy it across,
inflating the PR diff to unreviewable sizes. **Recommended v2.1 fix**:
add a configurable size cap (e.g. 50MB total per artifact dir) and skip
files larger than a per-file cap with a stderr warning. Not a security
issue, not a v2.0 blocker — but a UX foot-gun once the loop starts
producing real PRs.

### IR — Info (3)

**IR-01 — `evolution/loop/run_loop.py:339-353` cost extraction tries 3 keys.**

`_parse_cost_from_metrics` tries `total_cost_usd → cost_usd →
actual_cost_usd`. Each CLI uses a different field name. **Recommended
cleanup (v2.1)**: standardize all `evolve_*` CLIs on a single
`total_cost_usd` field via shared metric-writing helper. Not a defect;
the fallback chain works correctly for current callers.

**IR-02 — `evolution/loop/run_loop.py:117` `OPENAI_API_KEY` env precedence
issue surfaced in Phase 15 UAT.**

DSPy/LiteLLM honors `OPENAI_API_KEY` env var ahead of `api_base` kwarg
when the model provider prefix is `openai/`. This means subprocess
inheritance of `OPENAI_API_KEY` could route DashScope-targeted requests
to OpenAI's public endpoint. **Mitigation in place**: GH Actions
workflow (.github/workflows/evolution-loop.yml) does NOT inject
`OPENAI_API_KEY` env var; only `EVOLUTION_API_KEY` is exported. So
production is safe by construction. **Recommended v2.1 hardening**:
add a `--api-base` flag to `run_loop` that gets propagated as an
explicit subprocess flag (not env) so the routing is unambiguous.

**IR-03 — `docs/setup-hermes-agent-branch-protection.md` references
GitHub UI screenshots not embedded.**

The runbook is text-only. **Recommended v2.1 polish**: add 2-3 PNG
screenshots of the "Add branch protection rule" page so first-time
operators have a visual reference. Not a correctness issue.

## Verdict

**clean** — no critical or blocking issues found. 1 warning + 3 info
items are all v2.1 polish candidates, not v2.0 blockers.

This review was produced inline by the orchestrator because subagent
dispatch was unavailable this session. The standard `gsd-code-review`
agent invocation should produce equivalent output when subagent access
is restored — file a follow-up to re-run `/gsd-code-review 22` for
canonical artifact format compliance.
