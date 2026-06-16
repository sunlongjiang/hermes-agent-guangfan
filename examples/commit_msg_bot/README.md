# Commit Message Bot — Dogfood Example

A real agent using the Agent Evolve SDK end-to-end. Demonstrates all three
text-source forms of `@evolvable_prompt` / `@evolvable_tool` plus the standard
`@evolvable_agent` decorator.

## Quick run

```bash
# Discover the agent (writes ~/.evolution/registry.json)
PYTHONPATH=. evolution discover examples.commit_msg_bot.bot

# Show registration table
evolution status --agent commit-msg-bot

# Generate the GitHub Actions scheduling workflow
evolution scaffold --backend gh-actions --output .github/workflows/ \
    --agent commit-msg-bot

# Verify drift detection
evolution scaffold --check --output .github/workflows/

# Trigger a dry-run optimizer (no real LLM calls)
evolution optimize --agent commit-msg-bot --dry-run

# Roll back an optimized artifact (revert to baseline)
evolution rollback --agent commit-msg-bot --artifact system
```

## What this exercises

| Decorator form | Where | Used for |
|---|---|---|
| `@evolvable_prompt(text=...)` (Form 1) | `system_prompt` | The main system prompt — explicit text param |
| `@evolvable_prompt` + return value (Form 2) | `few_shot_header` | Short helper prompt — clean function syntax |
| `@evolvable_tool` + docstring (Form 3) | `classify_diff` | Tool description — zero-ceremony Form 3 |

## Dogfood findings (2026-06-16)

Things that worked smoothly:
- Three decorator forms are intuitive — adding a new optimizable point feels
  like adding a method, not a config entry.
- Traces land in `~/.evolution/traces/<agent>/<date>.jsonl` immediately on
  first run; schema is complete (input, output, artifacts, signals, scores).
- `evolution status` table is concise and informative.
- The scaffolded GitHub Actions YAML is ready to use — cron uses an off-peak
  minute (`57 8 * * 1`), permissions are minimised (`contents: read` only when
  `apply!="pr"`).
- The full lifecycle works: baseline → write optimized → `resolve_text`
  returns optimized → mutate baseline → hash mismatch → silent fallback to
  the new baseline.
- `evolution rollback` deletes one optimized file in one command.

Pain points worth fixing in P1:
1. **`evolution discover` does not add CWD to `sys.path`.** Users need
   `PYTHONPATH=.` to import their own package. The `discover` CLI should
   prepend `os.getcwd()` to `sys.path` (or accept `--root` flag).
2. **Drift detection wording is confusing.** When the manifest hash is stale
   but the file matches what the registry would generate now, the row reads
   `status=CLEAN` with `detail="manifest stale but file matches registry"`.
   The detail contradicts the status verb. Consider renaming the status to
   `CLEAN_REGENERATED_MANIFEST` or splitting into a separate `STALE_MANIFEST`
   advisory.
3. **`SKIPPED_<ts>/` directory contains only `reason.txt`, no
   `run_summary.json`.** The GH Actions workflow uploads `output/sdk/<agent>/`
   as an artifact with `if-no-files-found: warn`, so SKIPPED runs trigger the
   warning. Writing a minimal `run_summary.json` with `trigger=skipped` would
   keep CI green.
4. **`output/sdk/<agent>/` defaults to `$CWD`, not `$EVOLUTION_HOME`.**
   Other artifacts (`registry.json`, `traces/`, `optimized/`) honour
   `EVOLUTION_HOME` but the optimizer's run output does not. This makes the
   "isolated dogfood directory" pattern leaky.

These are real, reproducible UX bugs found in 5 minutes of dogfooding —
exactly what this example was meant to surface.
