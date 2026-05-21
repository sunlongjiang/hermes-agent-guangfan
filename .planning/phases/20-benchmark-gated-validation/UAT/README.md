# Phase 20 Plan 20-05 UAT — Partial 2026-05-21

## Command

```
env -u OPENAI_API_KEY python -m evolution.benchmarks.build_tblite_calibration \
  --runs 3 --benchmark-max-cost 50.0 --hermes-repo ~/.hermes/hermes-agent \
  --accept-stale-anchor
```

## Result — Fail-closed at D-16 watermark gate

```
Error: Insufficient benchmark budget: watermark $108.00 exceeds
--benchmark-max-cost $50.00. Either raise the cap or reduce --runs.
```

The Pre-flight Watermark check computed `0.40/task × 30 tasks × 3 runs = $36`
then applied a 3× safety multiplier → $108 watermark. With `--benchmark-max-cost
50.0`, the CLI **correctly refused to start** and exited cleanly.

## What this validates

Phase 20 ROADMAP SCs partially covered:
- ✓ SC #1 (`--benchmark` flag triggers TBLite path) — entered the
  calibration pipeline, executed pre-flight checks 1-3
- ✓ SC #2 (configurable threshold + fail-closed) — D-16 watermark gate
  fired correctly with explicit error message
- ⚠ SC #3 (benchmark results saved to output metrics) — NOT exercised
  because the run aborted before writing anchor.json

## What still blocks complete UAT

1. **Wave-1 placeholder task names**: `tblite_stratified_subset.json` was
   committed with placeholder names (`tblite-easy-01..tblite-extreme-03`)
   in Plan 20-01; Plan 20-05 was supposed to replace them with real
   TBLite task names. Without real names, the subprocess invocation
   would fail at the TBLite runner layer regardless of budget.
2. **Budget cap**: `--benchmark-max-cost 50` < 3× estimated cost. Needs
   `--benchmark-max-cost 120` to clear the watermark.

To complete the live calibration:
1. Replace placeholders in `datasets/prompts/tblite_stratified_subset.json`
   with real TBLite task names (manual research step — out of v2.0 scope).
2. Re-run with `--benchmark-max-cost 120`.
3. Expected wall clock: 30-90 min depending on TBLite task latency.

## Status

`PMPT-V2-03` requirement remains **partial** (human_needed). The fail-closed
safety gate is verified end-to-end; the success path (anchor production)
remains pending real task names + budget headroom.

This UAT did exercise:
- Pre-flight 1 (git tree state) — `--accept-stale-anchor` honored
- Pre-flight 2 (subset loading) — 30 tasks across 4 tiers loaded
- Pre-flight 3 (watermark) — D-16 budget check fired correctly
- Clean CLI exit (no stack trace) — error handling code path covered
