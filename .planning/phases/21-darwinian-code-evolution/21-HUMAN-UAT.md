---
status: partial
phase: 21-darwinian-code-evolution
source: [21-VERIFICATION.md]
started: 2026-05-20T11:30:00Z
updated: 2026-05-20T11:30:00Z
---

## Current Test

[awaiting human testing — requires live LLM API key + $1-5 budget]

## Tests

### 1. Live one-iteration openevolve smoke test (budget-gated)

```bash
python -m evolution.code.evolve_code \
    --component tools/ansi_strip.py \
    --iterations 1 \
    --max-cost 1.0 \
    --hermes-repo ~/.hermes/hermes-agent
```

expected: ONE of the two terminal states below:

**A. ACCEPT path:** exit 0; `output/code/<ts>/` contains
  - `component.py` (evolved candidate, possibly identical to baseline if no improvement found)
  - `NOTICE.md` containing literal `UNREVIEWED — DO NOT MERGE WITHOUT HUMAN REVIEW`
  - `metrics.json` with baseline + holdout fitness, `holdout_gate_passed: true`
  - `diff.txt` (may be empty if no change)
  - `eval_holdout.json`

**B. REJECT path:** exit 1; `output/code/FAILED_<ts>/` contains
  - same artifacts as ACCEPT
  - `metrics.json` with `holdout_gate_passed: false` and a real D-15 `reject_reason` (e.g. "holdout pytest X/Y", "size_component < 0.7", "ruff_score < 0.4")
  - NOT a Python TypeError / stack trace

Either A or B is a PASS. The failure mode we are guarding against is a TypeError or
ImportError reaching the surface — that would indicate the c9498f4 contract fix did
not propagate to a real openevolve subprocess invocation.

result: [pending]

## Summary

total: 1
passed: 0
issues: 0
pending: 1
skipped: 0
blocked: 0

## Gaps

(none yet — pending live human run)
