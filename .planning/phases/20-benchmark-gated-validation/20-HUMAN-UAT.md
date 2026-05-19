---
status: partial
phase: 20-benchmark-gated-validation
source: [20-VERIFICATION.md]
started: 2026-05-19T14:39:06.795569Z
updated: 2026-05-19T14:39:06.795569Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Live TBLite calibration run (Plan 20-05, Wave 4)
expected: |
`python -m evolution.benchmarks.build_tblite_calibration --runs 3 --benchmark-max-cost 50.0`
produces `datasets/prompts/tblite_anchor.json` with:
  - anchor_per_tier covering all 4 tiers (easy/medium/hard/extreme) each with n>=3, numeric mean+stdev
  - hermes_agent_commit matching `git rev-parse HEAD` of the hermes-agent checkout
  - dataset_revision_hash either real HF sha OR documented `unknown_v1.0` fail-open
  - tblite_estimated_cost_per_task_usd measured (likely 0.3-0.6)
  - calibration_timestamp / calibration_model / tblite_runner_version populated
Plus `datasets/prompts/tblite_stratified_subset.json` updated with REAL TBLite task names
replacing the Wave-1 `tblite-easy-01..tblite-extreme-03` placeholders; `_meta.placeholder`
flipped to false.
Then re-run `python -m evolution.prompts.evolve_prompt_sections --benchmark=tblite ...`
end-to-end against the hermes-agent checkout to confirm step 10.5 actually executes
TBLite subprocess + Risk_Score gating instead of fail-closing at the anchor-existence check.
result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps
