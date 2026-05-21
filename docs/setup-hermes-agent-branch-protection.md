# Setup: hermes-agent Branch Protection for Phase 22 Continuous Evolution Loop

**Phase 22 D-09 runbook.** Configures the receiving-side (`hermes-agent` repo) so PRs created by the
`evolution-loop` GH Actions workflow require human approval before merge.

This file is **not** executed automatically — `hermes-agent` branch protection is a permanent governance
setting and must be applied by a repo admin (you), not by a continuous-evolution worker. Once applied,
the three-layer gate is closed:

1. **Plan 01 (D-11):** `EVOLUTION_DEPLOY_MODE=production` blocks the worker from writing to
   hermes-agent source files at the Python layer.
2. **Plan 04 (D-04):** Loop runner pushes a branch + opens a draft-style PR via `gh` instead of
   merging directly.
3. **This runbook (D-09):** hermes-agent main is locked behind required PR review + CODEOWNERS;
   evolution-bot can open PRs but cannot self-approve them.

## Prerequisites

- Admin access to the `<owner>/hermes-agent` repository on GitHub.
- `gh` CLI v2.x installed locally, authenticated via `gh auth login` (verify with `gh auth status`).
- The GitHub username(s) of the human reviewer(s) — placeholders below say `YOUR_GITHUB_USERNAME`.

---

## Step 1 — Configure CODEOWNERS

Create or edit `.github/CODEOWNERS` in the `hermes-agent` repo with this content:

```text
# hermes-agent CODEOWNERS — Phase 22 V2-LOOP-01 human review gate.
#
# The evolution-bot account is INTENTIONALLY EXCLUDED from this file — it
# opens PRs against this repo via Plan 04 (gh CLI), but it cannot approve
# its own work. Reviewers below must be real humans.
#
# Replace YOUR_GITHUB_USERNAME with the actual GitHub login(s) — at least
# ONE; ideally two so PRs unblock when one reviewer is OOO.

*   @YOUR_GITHUB_USERNAME @OPTIONAL_SECOND_REVIEWER
```

Commit and push this file to `hermes-agent`'s `main` branch directly (you must do this BEFORE
enabling branch protection, otherwise step 2 will lock you out).

Verify the file is in place:

```bash
gh api repos/<owner>/hermes-agent/contents/.github/CODEOWNERS \
  | jq -r '.content' | base64 -d
```

The output should match what you committed.

---

## Step 2 — Apply branch protection (REST API)

Run this from any shell with `gh` authenticated. The `<<'JSON'` heredoc means the JSON body is
literal — no shell expansion — so you can paste-edit safely:

```bash
gh api -X PUT repos/<owner>/hermes-agent/branches/main/protection \
  --input - <<'JSON'
{
  "required_status_checks": null,
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": true,
    "required_approving_review_count": 1
  },
  "restrictions": null,
  "required_linear_history": false,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_conversation_resolution": true
}
JSON
```

### Field explanation

| Field | Value | Why |
|---|---|---|
| `required_status_checks` | `null` | Phase 22 v1 does NOT gate on hermes-agent CI. When you set up hermes-agent's own CI suite (e.g. an `import-boundary` job similar to Phase 21 D-18), revisit this field. |
| `enforce_admins` | `false` | Repo admins can bypass — useful for emergency manual override; keep `false` v1, tighten later if abuse appears. |
| `required_pull_request_reviews.required_approving_review_count` | `1` | At least one human approval before merge (D-09). |
| `required_pull_request_reviews.require_code_owner_reviews` | `true` | A CODEOWNERS-matched reviewer must be among the approvers — this is the lock that excludes evolution-bot. |
| `required_pull_request_reviews.dismiss_stale_reviews` | `true` | If the bot or anyone pushes new commits after approval, the approval resets — prevents review-then-quietly-rewrite attacks. |
| `required_conversation_resolution` | `true` | All review threads must resolve before merge — prevents silent overrides. |
| `allow_force_pushes` | `false` | Bot or human can't force-push over reviewed history. |
| `allow_deletions` | `false` | Main branch can't be deleted. |

---

## Step 3 — Verify the settings stuck

```bash
gh api repos/<owner>/hermes-agent/branches/main/protection \
  | jq '{
      review_count: .required_pull_request_reviews.required_approving_review_count,
      code_owner_required: .required_pull_request_reviews.require_code_owner_reviews,
      dismiss_stale: .required_pull_request_reviews.dismiss_stale_reviews,
      force_pushes_allowed: .allow_force_pushes.enabled,
      deletions_allowed: .allow_deletions.enabled,
      conversations_required: .required_conversation_resolution.enabled
    }'
```

Expected output:

```json
{
  "review_count": 1,
  "code_owner_required": true,
  "dismiss_stale": true,
  "force_pushes_allowed": false,
  "deletions_allowed": false,
  "conversations_required": true
}
```

If any field is missing or wrong, re-run Step 2.

---

## Step 4 — Test end-to-end

1. In the `evolution-self` repo, go to **Actions** → `evolution-loop` workflow → **Run workflow**.
2. Inputs:
   - `cli`: `skill`
   - `dry_run`: `false`
   - `no_pr`: `false`
   - `per_cli_timeout_seconds`: `900`
3. Wait for the workflow to finish (typically 5–15 min for skill alone).
4. Open the new PR in `hermes-agent` — branch name should match
   `evolution/auto-loop/<YYYYMMDD_HHMMSS>/skill`.
5. On the PR page, verify:
   - "Review required" banner visible
   - "Code owners required" listed under requirements
   - Labels `auto-loop` + `requires-human-review` applied
   - NOTICE in PR body contains `UNREVIEWED — DO NOT MERGE WITHOUT HUMAN REVIEW`
6. Close the PR without merging — this was a verification round-trip, not a real change.

---

## Rollback (rare)

If you need to lift branch protection temporarily (e.g. for a one-time emergency manual fix):

```bash
gh api -X DELETE repos/<owner>/hermes-agent/branches/main/protection
```

**Warning:** This removes ALL protections on `main`. After resolving the emergency, immediately
re-run Step 2 to restore. Consider documenting any emergency rollback in a CHANGELOG so the next
audit reviewer knows why protection was off for a window of time.

---

## FAQ

### Why is the evolution-bot account NOT in CODEOWNERS?

Per Phase 22 D-09: a bot account in CODEOWNERS would let the loop "approve" itself indirectly
(whoever holds the bot's token could). Excluding the evolution-bot forces every PR through a real human,
which is exactly the V2-LOOP-01 SC #3 contract ("Human review required before merge").

### Can I require two human reviewers for risky paths?

Yes — bump `required_approving_review_count` from `1` to `2`. Or use a path-scoped CODEOWNERS entry:

```text
/tools/        @reviewer-a @reviewer-b
/prompt_builder.py    @reviewer-a @reviewer-b
*              @reviewer-a
```

The repo will require approval from a code-owner of each modified path. Phase 23+ may automate
this via the deferred "loop-level cross-artifact regression gate".

### Why isn't `required_status_checks` set?

Phase 22 v1 does not register any CI check on hermes-agent — the gate is purely human review +
CODEOWNERS. When hermes-agent gains its own CI (the project's own test suite, an
import-boundary job like Phase 21 D-18 layer-1 pre-commit + layer-2 pytest, etc.), revisit
Step 2 and add the check names to `required_status_checks.contexts`.

### How do I add the evolution-bot account?

On GitHub: create a machine user (e.g. `evolution-bot-<yourorg>`), give it Read + PR-create scope
on `hermes-agent`, generate a Personal Access Token, and store the token as
`GH_PAT_HERMES_PUSH` in evolution-self's repo secrets (see Plan 05 workflow yaml). The evolution-bot
account does NOT need write access to main itself — branch protection allows ANY pusher to
create a branch as long as they don't try to merge into main directly.

---

*Phase 22 V2-LOOP-01 — D-09 runbook. Last reviewed: <fill in when applied>.*
