---
status: partial
phase: 17-joint-section-optimization
source: [17-VERIFICATION.md]
started: 2026-05-15T09:00:00Z
updated: 2026-05-15T09:10:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. End-to-end joint optimization on real hermes-agent prompt_builder.py (13 sections)
expected: joint_score >= roundrobin_baseline_score - EPSILON_PP on holdout, OR yellow warning triggers and both artifacts persist with metrics.json containing 5 new fields (mode/joint_score/roundrobin_baseline_score/epsilon_pp/joint_vs_roundrobin_delta_pp). Both `evolved_sections.json` and `roundrobin_baseline_evolved_sections.json` must exist in the same output directory.
result: [pending]

### 2. Soft-gate warning visibility in real-terminal stdout (rich console rendering)
expected: When joint regresses past EPSILON_PP, [yellow] warning containing 'review before deploying' is visible in a normal 80+ char terminal. When joint wins or ties, [green] success message appears. Exit code is 0 in both cases.
result: [pending]

### 3. WR-07 [ACTIVE:sid] selector tag — real-LM reflection signal quality (from 17-REVIEW-FIX)
expected: With the new `[ACTIVE:{sid}]:` tag prefixed to active section text in round-robin mode, GEPA reflection signals are equal or better than the un-tagged baseline (no degradation in fitness or convergence speed on a real LM run). Unit tests only verify the string format; only an end-to-end run with a real LLM can confirm reflection quality is preserved.
result: [pending]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps
