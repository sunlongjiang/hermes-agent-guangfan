---
phase: 22-continuous-evolution-loop
plan: 04
status: complete
completed: 2026-05-21
key-files:
  created:
    - evolution/loop/__init__.py
    - evolution/loop/pr_creator.py
    - tests/loop/__init__.py
    - tests/loop/test_pr_creator.py
---

# Plan 22-04 Summary — pr_creator (D-03/D-04/D-05/D-09)

## Outcome

`evolution/loop/pr_creator.create_pr()` is the single entry point Plan 22-03's
`run_loop` will call after each successful `evolve_*` CLI run. It opens a PR
against the hermes-agent repo via `gh` CLI subprocess, never against
evolution-self (D-03), without PyGithub/requests/httpx (D-04), with
`evolution/auto-loop/<ts>/<artifact-kind>` branches (D-05), and waits for the
CODEOWNERS + branch-protection gate that Plan 22-07's runbook lands (D-09).

## API contract

```python
def create_pr(
    *, cli_name: str, output_dir: Path, loop_ts: str, hermes_repo: Path,
) -> dict
```

Returns:

| key | value |
|-----|-------|
| `status` | `"created"` \| `"error"` \| `"skipped_no_gh"` \| `"skipped_no_changes"` |
| `pr_url` | `str` on `created`, else `None` |
| `reason` | safe stderr tail / explanation on non-`created`, `None` on success |
| `branch` | always set (the D-05 branch name we tried to push) |

The function **never raises** (all subprocess calls use `check=False`; internal
exceptions are caught and re-packaged). This matches Plan 22-03's contract that
raises from `create_pr` mean "executor crashed" rather than "PR failed".

## Staging-dir approach (intentional v1 design)

Per `<interfaces>` section of the plan, evolved artifacts are copied into
`<hermes_repo>/evolution-loop/<artifact-kind>/<loop_ts>/` rather than
overwritten in place. This:

1. **Decouples from CLI-specific paths.** `tool_loader.py` vs
   `prompt_loader.py` vs skill files all have different write-back
   destinations — staging-dir collapses to one path pattern.
2. **Keeps hermes-agent buildable at PR-creation time.** The reviewer
   cherry-picks evolved content from `evolution-loop/.../` into the live path
   during PR review; the PR diff doesn't break the agent.
3. **Satisfies D-11 by construction.** The loop never invokes
   `write_back_description` / `write_back_section`; it only `shutil.copy`s
   into a staging subdir, so Plan 22-01's `EVOLUTION_DEPLOY_MODE=production`
   guard is never triggered (and never would be — Plan 22-05 sets that env
   for the same reason).

## Two deviations from the plan's reference implementation

1. **`_build_branch` validates against the known artifact-kind set** rather
   than regex-stripping `[^a-z0-9-]`. The plan's regex left `"tool;rm -rf /"`
   as `"toolrm-rf"` (still containing `"rm"`), failing
   `test_build_branch_sanitizes_kind`. Allowlist approach: unknown kinds
   collapse to `"unknown"`, so injection attempts produce
   `evolution/auto-loop/<ts>/unknown` instead of leaking partial tokens.

2. **Removed the trailing wholesale-redact in `_build_body`** (the
   `return _redact(body) if _contains_secret(body) else body` line). It
   tripped false positives on legitimate filesystem paths because
   `_contains_secret`'s Shannon-entropy heuristic flags long base64-ish path
   segments (e.g. pytest `tmp_path` fixtures and CI artifact paths). Defense
   in depth remains at the field-ingest layer:
   - per-`metrics.json` value redaction inside `_build_body`
   - title redaction in `_build_title`
   - slug redaction in both `_discover_repo_slug` branches
   - commit-message redaction before `git commit`
   - stderr-tail redaction on every error path
   - 8 `_contains_secret` call sites in total (acceptance threshold ≥ 4).

Both deviations are documented in the SUMMARY's "Two deviations" section
above and preserve the CONTEXT.md §specifics intent.

## Verification

- 32/32 `tests/loop/test_pr_creator.py` PASS
- Full suite: **755 passed, 2 skipped, 1 xfailed in 56.04s** (no regression vs
  Phase 21 baseline of 723 passed; +32 pr_creator tests, same skipped/xfailed)
- All acceptance criteria spot-checks pass:
  - `wc -l evolution/loop/pr_creator.py` = 332 (≥ 180) ✓
  - `grep -c "raise " evolution/loop/pr_creator.py` = 0 ✓
  - `grep -c "_contains_secret" evolution/loop/pr_creator.py` = 8 (≥ 4) ✓
  - `grep -c "import requests\|import httpx\|from github import\|import PyGithub" evolution/loop/pr_creator.py` = 0 ✓
  - `grep -c "gh.*pr.*create" evolution/loop/pr_creator.py` ≥ 1 ✓
  - `grep -c "requires-human-review" evolution/loop/pr_creator.py` = 1 ✓
  - `grep -c "UNREVIEWED" evolution/loop/pr_creator.py` ≥ 1 ✓

## Commits

- `7e6179e` test(22-04): add failing tests for pr_creator create_pr() contract (RED — 32 stubs)
- `98c09ff` feat(22-04): implement pr_creator.create_pr (gh CLI subprocess + staging-dir copy) (GREEN)

## Unblocks

- **22-03** (Wave 3): `run_loop.py` imports `create_pr` and `CLI_TO_ARTIFACT_KIND` from this module — contract locked.
- **22-05** (Wave 4): GH Actions workflow invokes `run_loop` knowing PR creation is wired.
- **22-06** (Wave 4): test_pr_creator.py exists and acts as the regression baseline for the package.

## Self-Check: PASSED

32/32 plan tests green. Full suite 755/755 green. Zero `raise` statements
(never-raises contract). Zero new HTTP/git Python dependencies (D-04). Two
deviations documented above with rationale.
