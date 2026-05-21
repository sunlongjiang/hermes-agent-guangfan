---
phase: 22-continuous-evolution-loop
plan: "07"
subsystem: docs
tags: [branch-protection, governance, runbook, D-09, V2-LOOP-01]
dependency_graph:
  requires: []
  provides: [hermes-agent-branch-protection-runbook]
  affects: [hermes-agent-repo-governance]
tech_stack:
  added: []
  patterns: [gh-api-idempotent-PUT, CODEOWNERS-gate, branch-protection-REST-API]
key_files:
  created:
    - docs/setup-hermes-agent-branch-protection.md
  modified: []
decisions:
  - "CODEOWNERS explicitly excludes evolution-bot to enforce second-human review (D-09)"
  - "required_status_checks: null for Phase 22 v1 — CI gate deferred to when hermes-agent has its own suite"
  - "enforce_admins: false for emergency manual override capability; tighten in later phases if needed"
metrics:
  duration: "5 minutes"
  completed: "2026-05-21"
  tasks_completed: 1
  tasks_total: 1
  files_created: 1
  files_modified: 0
---

# Phase 22 Plan 07: Branch Protection Runbook Summary

**One-liner:** Step-by-step D-09 runbook for applying GitHub branch protection + CODEOWNERS to hermes-agent main, closing the three-layer human-review gate for the continuous evolution loop.

## What Was Built

Created `docs/setup-hermes-agent-branch-protection.md` — a 199-line, numbered runbook that guides a repo admin through configuring the receiving-side (hermes-agent) to require human approval before the evolution-loop PRs can be merged.

The runbook covers:
1. CODEOWNERS configuration with evolution-bot explicitly excluded (D-09 rationale)
2. One-shot `gh api -X PUT` command applying all required branch protection settings
3. Verification commands to confirm settings stuck
4. End-to-end test procedure using `workflow_dispatch` on `evolution-loop`
5. Rollback procedure (DELETE branch protection) with explicit warning
6. FAQ covering bot exclusion rationale, two-reviewer escalation, status-checks deferral, and bot account setup

## Runbook Status

**NEXT ACTION REQUIRED BY USER:** This runbook must be executed manually on the hermes-agent repository before Phase 22 achieves full SC #3 compliance. The evolution-loop worker (Plans 03/04/05) can create PRs, but only after this runbook is applied will those PRs be mechanically blocked from self-merge.

To apply: Follow `docs/setup-hermes-agent-branch-protection.md` Steps 1–4 after Phase 22 ships.

## Three-Layer Gate Architecture (D-09 context)

Once this runbook is applied, the complete gate is:
- **Layer 1 (Plan 01 D-11):** `EVOLUTION_DEPLOY_MODE=production` raises `PermissionError` on any direct write-back to hermes-agent source files.
- **Layer 2 (Plan 04 D-04):** Loop runner pushes a branch and opens a PR via `gh`, never merging directly to main.
- **Layer 3 (This runbook D-09):** hermes-agent main requires human approval + CODEOWNERS match before any PR can merge — evolution-bot excluded from CODEOWNERS, so it cannot self-approve.

## Deferred Items

- **Phase 23+ — Required status checks:** The runbook documents `required_status_checks: null` for Phase 22 v1. When hermes-agent gains its own CI suite (import-boundary job similar to Phase 21 D-18), the admin should re-run Step 2 with the `required_status_checks` field populated.
- **Phase 23+ — Loop-level cross-artifact regression gate:** Multiple evolve_* CLIs running simultaneously may produce conflicting changes. Phase 22 relies on per-CLI holdout gates; a `loop_regression_check.py` is a deferred enhancement.
- **Phase 23+ — Two-reviewer path-scoped CODEOWNERS:** FAQ section documents the path-scoped CODEOWNERS pattern for per-path escalation; the deferred "loop-level cross-artifact regression gate" idea from Phase 22 context is the natural follow-on.

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- [x] `docs/setup-hermes-agent-branch-protection.md` exists (199 lines, >= 80 required)
- [x] All grep acceptance criteria pass (verified in task execution)
- [x] Commit `7f67239` exists: `docs(22-07): add hermes-agent branch protection runbook (D-09)`
- [x] No unintended file deletions
