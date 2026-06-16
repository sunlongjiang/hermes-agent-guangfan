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

## Optimizer wiring findings (2026-06-16 real run)

After patching `_run_one_artifact` to call the real `optimize_artifact` (P1
wiring), a real optimization run against qwen-max + qwen-plus surfaced two
deeper bugs that the mocked test suite cannot catch. Both are real P1 fixes.

5. **`dspy.GEPA` is never reached — metric signature mismatch.**
   `build_composite_metric` returns a 2-arg callable `(example, prediction)`
   but `dspy.GEPA` requires a 5-arg metric `(gold, pred, trace, pred_name,
   pred_trace)`. Every run falls through the `except` block silently to
   MIPROv2. Confirmed by 3-of-3 artifacts logging `GEPA failed (GEPA metric
   must accept five arguments...); falling back to MIPROv2`. Fix: wrap the
   metric with a `*args`-tolerant adapter, or build a GEPA-shaped metric
   alongside the existing one.

6. **MIPROv2's instruction mutation is not propagated to `current_text`.**
   `optimize_artifact` extracts the candidate via
   `getattr(optimized_module, "current_text", artifact.baseline_text)`, but
   MIPROv2 (and GEPA) modify the inner `dspy.Predict.signature.instructions`,
   not `AgentModule.current_text`. As a result, all three artifacts in the
   2026-06-16 run wrote `optimized_text == baseline_text` byte-for-byte
   even when `status="improved"`. The score deltas (`baseline 0.316 →
   holdout 0.363` etc.) are just val/holdout sample variance on the
   baseline, not real improvement. Fix: extract the optimized text from
   the predict's signature, e.g.
   `optimized_module.predictor.signature.instructions` (exact path depends
   on how `AgentModule` wires the underlying predictor), and call
   `module.set_text(...)` before holdout evaluation.

Gate behaviour was correct end-to-end:
- Gate 1 (size/growth/secret/placeholder) never tripped (expected: candidate
  was identical to baseline).
- Gate 2 (holdout regression) **correctly rejected** `few_shot_header` when
  the holdout sample variance dropped its score below the baseline-tolerance
  threshold (`holdout 0.590 < 0.667`). This is the safety net working as
  designed.
- All three optimized files were written to `$EVOLUTION_HOME/optimized/`
  with valid `baseline_hash` and metadata; runtime fallback would work on
  drift.

Additional smaller findings from the real run:
7. **`OptimizationBudget.spent_usd` never increments.** All `cost_usd`
   fields in `run_summary.json` are `0.0` regardless of actual LLM spend.
   Real cost tracking needs to hook `dspy.LM.history` or instrument the
   judge / optimizer call sites.
8. **`evolution.yaml literal-key` warning fires per LM construction** —
   ~60 emissions per artifact for a single optimize run. Should be
   deduplicated after the first emit per process (e.g. a module-level
   `_warned` flag in `EvolutionConfig.load()`).
