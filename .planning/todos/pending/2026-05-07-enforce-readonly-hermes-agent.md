---
created: 2026-05-07T07:53:18Z
title: Enforce read-only on hermes-agent (deploy_mode gate)
area: evolution-core
files:
  - evolution/core/config.py:120-145
  - evolution/tools/tool_loader.py:578
  - evolution/prompts/prompt_loader.py:182
---

## Problem

Architecture doc and CLAUDE.md both state hermes-agent is "read-only" — but the code path can write to it via `write_back_description` and the prompt loader's section replacement. These are intentional Phase 13/22 hooks (auto-PR loop), but they are not gated by an explicit "deploy mode" flag.

A typo, a stray script, or a future Phase 22 idempotency bug (Pitfall 13) could clobber `hermes-agent/tools/*.py` or `hermes-agent/agent/prompt_builder.py` before review.

- No `dry_run` parameter on `write_back_description` — it always writes.
- The hermes-agent path is resolved without verifying it's a git repo or that the working tree is clean.

## Solution

- Add `EvolutionConfig.deploy_mode: bool = False` flag. `write_back_description` and section write-back must assert `config.deploy_mode is True` or raise.
- Validate that `hermes_agent_path / ".git"` exists and `git status --porcelain` is clean before any write-back. Refuse to write to a dirty tree.
- Add a `--dry-run-write` flag that prints the diff but does not call `.write_text()`.

**Priority:** MED. Tracked under Phase 13 write-back integration + Phase 22 continuous loop hardening. Source: `.planning/codebase/CONCERNS.md` M6.
