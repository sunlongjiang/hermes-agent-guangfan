---
phase: 22-continuous-evolution-loop
plan: 05
status: complete
completed: 2026-05-21
key-files:
  created:
    - .github/workflows/evolution-loop.yml
---

# Plan 22-05 Summary — GH Actions scheduler (D-01/D-02/D-11)

## Outcome

First-ever `.github/workflows/` file in this repo. It is the only piece
that connects Plan 22-03 `run_loop` + Plan 22-04 `pr_creator` to a real
production scheduler. INTEGRATIONS.md §CI/CD ("None detected") is now
resolved by this file.

## Required secrets

These four secrets must be configured under
**Settings → Secrets and variables → Actions** in the evolution-self repo
before the first cron tick:

| Secret | Purpose | Example |
|--------|---------|---------|
| `EVOLUTION_API_KEY` | LLM API key consumed by `EvolutionConfig.load()` env override at `config.py:204-228`. | `sk-...` (DashScope or OpenRouter format) |
| `EVOLUTION_API_BASE` | Optional API base URL override. | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| `HERMES_AGENT_REPO_URL` | Git URL of the hermes-agent repo. SSH and HTTPS forms both accepted; the workflow extracts `owner/repo` via sed. | `https://github.com/<owner>/hermes-agent` |
| `GH_PAT_HERMES_PUSH` | Personal Access Token with `repo` scope on hermes-agent. The default `GITHUB_TOKEN` cannot push to a different repo than the one hosting the workflow, hence the PAT. | `ghp_...` |

## Manual trigger (workflow_dispatch)

From the GitHub UI:

1. Repo → **Actions** tab
2. **evolution-loop** workflow → "Run workflow" button
3. Inputs:
   - **cli**: `all` (default) or one of the 6 names — runs only that CLI subset
   - **dry_run**: `false` (default). `true` adds `--dry-run` to every CLI and skips PR creation
   - **no_pr**: `false` (default). `true` runs CLIs normally but skips PR creation (CI smoke test)
   - **per_cli_timeout_seconds**: `900` (default = 15 min). Increase for slow CLIs

## First cron tick

Cron is `57 8 * * 1` (Monday 08:57 UTC). After this PR merges, the next
fire is the upcoming Monday at 08:57 UTC. To confirm before merging, use
`workflow_dispatch` with `dry_run=true, no_pr=true` to smoke-test the whole
pipeline end-to-end without producing PRs.

## D-11 connection (env → subprocess inheritance)

The job-level `env:` block sets `EVOLUTION_DEPLOY_MODE: production`. This
value:

1. Flows into the runner shell process environment.
2. Passes into `python -m evolution.loop.run_loop` via standard process
   inheritance.
3. `run_loop._run_one_cli` builds each subprocess's env with
   `os.environ.copy()`, so all six `evolve_*` CLIs see `EVOLUTION_DEPLOY_MODE=production`.
4. Inside any of those CLIs, if a code path accidentally calls
   `evolution.tools.tool_loader.write_back_description` or
   `evolution.prompts.prompt_loader.write_back_section(dest=None)`, the
   guards added in Plan 22-01 fire `PermissionError` BEFORE any file write.

In practice the loop runner never calls write-back (it only reads `output/`
and copies into hermes-agent's `evolution-loop/` staging dir via
`pr_creator`). The env var is defense-in-depth — if a future bug in any
CLI invokes write-back, the production gate crashes loud instead of
silently corrupting the hermes-agent base.

## Two-repo checkout topology

```
$GITHUB_WORKSPACE/
├── (evolution-self repo)         ← actions/checkout@v4 #1 (default token)
└── hermes-agent-checkout/        ← actions/checkout@v4 #2 (GH_PAT_HERMES_PUSH)
```

`HERMES_AGENT_REPO` env var is set to
`$GITHUB_WORKSPACE/hermes-agent-checkout` so `config.py:453
get_hermes_agent_path()` resolves it correctly.

## Verification

- 20/20 acceptance-criteria grep counts pass (all 1 or more, with
  `GH_PAT_HERMES_PUSH` count = 4 from env + 2 checkout uses + comment +
  GH_TOKEN line)
- `wc -l .github/workflows/evolution-loop.yml` = 145 (≥ 75) ✓
- `python -c "import yaml; yaml.safe_load(open('.github/workflows/evolution-loop.yml'))"` exits 0
  (yaml well-formed; the `on:` key parses as boolean `True` in YAML 1.1 —
  GitHub's parser handles this correctly)

## Commits

- `10128fb` ci(22-05): add evolution-loop GH Actions workflow (D-01/D-02/D-11)

## Unblocks

- Plan 22-06 (unit tests) — workflow yaml is now the artifact that Plan 06
  tests assert against (e.g. test_workflow_invokes_run_loop_subprocess).

## Self-Check: PASSED

YAML parses, all acceptance-criteria greps pass, 4 required secrets
documented inline, two-repo checkout topology + D-11 env inheritance chain
documented above. Zero Python code changes (Plan 22-03/04 did that).
