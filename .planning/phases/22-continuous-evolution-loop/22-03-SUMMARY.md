---
phase: 22-continuous-evolution-loop
plan: 03
status: complete
completed: 2026-05-21
key-files:
  created:
    - evolution/loop/run_loop.py
  modified:
    - evolution/loop/__init__.py
---

# Plan 22-03 Summary — run_loop.py orchestrator (D-06/D-07/D-08/D-10)

## Outcome

`python -m evolution.loop.run_loop` is the single entry point GH Actions
(Plan 22-05) will invoke. It does pure subprocess orchestration — no dspy,
no openevolve — and produces an audit-trail `run_summary.json` at
`output/loop/<loop_ts>/run_summary.json`.

## LoC + flags

- `evolution/loop/run_loop.py`: 519 lines including module docstring,
  dispatch tables, classifier helpers, per-CLI runner, main pipeline, and
  Click entry point.
- Click flags (6):
  - `--config <path>`
  - `--cli <name>` (repeatable; Choice from LOOP_CLI_NAMES)
  - `--dry-run`
  - `--no-pr`
  - `--per-cli-timeout <int>` (default 900s)
  - `--loop-output-dir <path>` (default `output/loop`)

## Dispatch tables — final shape

```python
CLI_DISPATCH = {
    "skill":             ["python", "-m", "evolution.skills.evolve_skill"],
    "tool_descriptions": ["python", "-m", "evolution.tools.evolve_tool_descriptions"],
    "tool_params":       ["python", "-m", "evolution.tools.evolve_tool_params"],
    "tool_reasoning":    ["python", "-m", "evolution.tools.evolve_tool_reasoning"],
    "prompt_sections":   ["python", "-m", "evolution.prompts.evolve_prompt_sections"],
    "code":              ["python", "-m", "evolution.code.evolve_code"],
}
CLI_OUTPUT_ROOT = {
    "skill":             "output",  # globs output/<skill_name>/<ts>/
    "tool_descriptions": "output/tools",
    "tool_params":       "output/tools",
    "tool_reasoning":    "output/tools_reasoning",
    "prompt_sections":   "output/prompts",
    "code":              "output/code",
}
CLI_MAX_COST_FLAG = {
    "skill":             None,    # env-only via EVOLUTION_MAX_COST_USD
    "tool_descriptions": None,    # env-only
    "tool_params":       "--max-cost-usd",
    "tool_reasoning":    "--max-cost-usd",
    "prompt_sections":   "--max-cost-usd",
    "code":              "--max-cost",
}
```

Parity verified at import time:
`set(CLI_DISPATCH) == set(CLI_OUTPUT_ROOT) == set(CLI_MAX_COST_FLAG) == set(LOOP_CLI_NAMES)`.

No CLI-flag-name deviations from the plan's CONTEXT.md table.

## Skill output-dir special handling

The skill CLI does not write to `output/skill/<ts>/`. It writes to
`output/<skill_name>/<ts>/` where `<skill_name>` comes from the skill the
operator chose (default `default-skill`). To detect its output, `run_loop`
snapshots **every** `output/<subdir>/` whose name is not in
`{tools, tools_reasoning, prompts, code, loop}`, runs the subprocess, and
diffs the post-state. The lexicographically-largest new child is treated as
the result dir.

## Holdout-gate classifier (D-10)

Two-layer check:

1. **Dir-name regex**: `^\d{8}_\d{6}$` → success;
   `^(FAILED|ABORTED)_\d{8}_\d{6}$` → failed; anything else → unknown.
2. **metrics.json override**: if `metrics.json` exists with explicit
   `holdout_gate_passed: bool`, that wins. If it disagrees with the dir
   name (success-pattern dir but `holdout_gate_passed: false`), the loop
   trusts metrics.json and downgrades status to `failed`. (evolve_code is
   currently the only CLI that writes this field; the others are
   dir-name-only.)

If no new dir appears at all → `status="crashed"`. If subprocess timed out
→ `status="timeout"`.

## How Plan 22-05 GH Actions yaml will invoke this

```yaml
jobs:
  loop:
    runs-on: ubuntu-latest
    timeout-minutes: 120
    env:
      EVOLUTION_DEPLOY_MODE: production   # fires Plan 22-01 worker guard
      EVOLUTION_API_KEY: ${{ secrets.EVOLUTION_API_KEY }}
      EVOLUTION_API_BASE: ${{ secrets.EVOLUTION_API_BASE }}
    steps:
      - uses: actions/checkout@v4
        with: { path: evolution-self }
      - uses: actions/checkout@v4
        with:
          repository: <owner>/hermes-agent
          path: hermes-agent
          token: ${{ secrets.HERMES_AGENT_PUSH_TOKEN }}
      - name: Set up Python
        uses: actions/setup-python@v5
        with: { python-version: '3.13' }
      - name: Install deps
        run: pip install -e ./evolution-self[code]
      - name: Run loop
        working-directory: ./evolution-self
        run: python -m evolution.loop.run_loop --no-pr  # or omit --no-pr
      - uses: actions/upload-artifact@v4
        with:
          name: run-summary-${{ github.run_id }}
          path: evolution-self/output/loop/**/run_summary.json
```

## Lazy-import note

`from evolution.loop.pr_creator import create_pr` is inside `_run_one_cli`,
not at module top — pr_creator is only loaded when a CLI actually succeeds
and the loop needs to create a PR. This means `--dry-run` and `--no-pr`
never load pr_creator, and a missing `gh` CLI binary doesn't break
`python -m evolution.loop.run_loop --help`.

## Verification

- `python -c "import evolution.loop.run_loop"` exits 0
- `python -m evolution.loop.run_loop --help` exits 0 and shows all 6 flags
- Full suite: **770 passed, 1 skipped, 1 xfailed in 61.01s** (no regression
  vs Wave 2 baseline). Plan 06 will add the unit tests for run_loop itself.
- Acceptance criteria spot-checks pass:
  - `grep -c "subprocess.run" run_loop.py` = 1 ✓
  - `grep -c "import openevolve\|import dspy" run_loop.py` = 0 ✓
  - `grep -c "from evolution.loop.pr_creator import" run_loop.py` = 1 ✓
  - `grep -c "_contains_secret" run_loop.py` = 2 (import + _safe_tail) ✓
  - `grep -c "LOOP_CLI_NAMES" run_loop.py` = 4 ✓
  - `grep -c "check=False" run_loop.py` = 1 ✓
  - `wc -l run_loop.py` = 519 (≥ 200) ✓

## Commits

- `4aa099f` feat(22-03): land run_loop.py orchestrator (D-06/D-07/D-08/D-10)

## Unblocks

- **22-05** (Wave 4): GH Actions yaml invokes `python -m evolution.loop.run_loop`.
- **22-06** (Wave 4): unit tests for `_run_one_cli` / `_find_new_dir` /
  classifier / per-CLI dispatch table will use `subprocess.run` mocks.

## Self-Check: PASSED

Module imports clean. --help exits 0. Full suite 770/770 green.
Dispatch tables in parity with LOOP_CLI_NAMES. Lazy import of pr_creator
keeps the dry-run/no-pr paths free of gh-CLI dependency. Zero new Python
deps. Zero deviation from plan's CLI flag table.
